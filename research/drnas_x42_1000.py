#!/usr/bin/env python3
"""DRNAS X4.2: 1000 reproducible, clearly GENERATED planted SAT CNFs.

Not 1000 official/industrial originals. Exact 600/200/200 family-disjoint
training/validation/holdout split, frozen BEFORE solving. All SAT witnesses
independently checked against input; unfinished are censored. 4 CI shards.
No outcome-based formula selection and no online learned branching.
"""
from __future__ import annotations
import argparse, collections, hashlib, itertools, json, math, os
from pathlib import Path
import random, subprocess, sys, time

ROOT=Path('drnas_x42_results')
SOLVER=Path('build/drnas-x41')
SPLITS={
 'train':('planted_uniform','planted_balanced','planted_dense','planted_negation','planted_local20','planted_local40'),
 'validation':('planted_hubmix','planted_clausewidth'),
 'holdout':('planted_xoraugment','planted_redundant'),
}
FAMILIES={family:split for split,families in SPLITS.items() for family in families}
N_PER_FAMILY=100
SAMPLE_HASH='x42-source-spec-v1.2-20261113'

def emit(tag,item):print(tag+' '+json.dumps(item,sort_keys=True,separators=(',',':')),flush=True)

def seed_for(family,rep):
 return int.from_bytes(hashlib.sha256(f'{SAMPLE_HASH}:{family}:{rep}'.encode()).digest()[:8],'big')

def gen_source(family,rep,root):
 rng=random.Random(seed_for(family,rep))
 # Common intermediate-hardness scale; fixed from a tiny TRAIN-only pilot.
 # No formula is removed if the runtime is too short or exceeds the cap.
 n=220+(rep%10)*7
 density=4.20 + (rep%4)*0.10
 if family=='planted_dense':density+=0.30
 if family=='planted_clausewidth':density+=0.20
 if family=='planted_local20':density+=0.75
 if family=='planted_local40':density+=0.40
 if family=='planted_redundant':density+=0.15
 secret=[bool(rng.getrandbits(1)) for _ in range(n)]
 clauses=[]
 def satisfied(clause):return any(secret[abs(x)-1]==(x>0) for x in clause)
 def planted(vs):
  c=[rng.choice((-1,1))*v for v in vs]
  if not satisfied(c):c[rng.randrange(len(c))]*=-1
  assert satisfied(c)
  return c
 def draw_vars(i,width):
  if family=='planted_balanced' and i%2==0:
   v=(i%n)+1;return [v]+rng.sample([x for x in range(1,n+1) if x!=v],width-1)
  if family in ('planted_local20','planted_local40') and rng.random()<(0.20 if family=='planted_local20' else 0.40):
   block=20;idx=rng.randrange((n+block-1)//block);pool=list(range(idx*block+1,min(n,(idx+1)*block)+1))
   if len(pool)>=width:return rng.sample(pool,width)
  if family=='planted_hubmix' and rng.random()<0.15:
   hub=rng.randrange(1,1+min(12,n));return [hub]+rng.sample([x for x in range(1,n+1) if x!=hub],width-1)
  return rng.sample(range(1,n+1),width)
 m=int(n*density)
 for i in range(m):
  width=3
  if family=='planted_clausewidth' and i%11==0:width=4
  if family=='planted_negation' and i%5==0:
   v=draw_vars(i,width);c=planted(v)
   # Flip all signs in a planted clause only if still satisfied.
   other=[-x for x in c]
   if satisfied(other):c=other
  else:c=planted(draw_vars(i,width))
  clauses.append(c)
 if family=='planted_xoraugment':
  # Exact 3-variable parity clauses consistent with the planted witness.
  # Only a sparse percentage; otherwise a full parity subsystem can dominate.
  for _ in range(n//25):
   vs=rng.sample(range(1,n+1),3)
   p=sum(secret[v-1] for v in vs)%2
   for bits in itertools.product((0,1),repeat=3):
    if sum(bits)%2!=p:clauses.append([(-v if bit else v) for v,bit in zip(vs,bits)])
 if family=='planted_redundant':
  # Add a small number of logically redundant duplicates, not new sources.
  # The manifest labels this family as generated; SHA collision is forbidden.
  for c in clauses[:n//6]:clauses.append(list(c))
 if not all(satisfied(c) for c in clauses):raise AssertionError('planted SAT witness failed')
 root.mkdir(parents=True,exist_ok=True)
 path=root/(family+'_'+str(rep).zfill(3)+'.cnf')
 content=f'p cnf {n} {len(clauses)}\n'+''.join(' '.join(map(str,c))+' 0\n' for c in clauses)
 path.write_text(content)
 sha=hashlib.sha256(content.encode()).hexdigest()
 return dict(global_id=-1,formula_id=f'{family}:{rep:03d}',seed=seed_for(family,rep),sha256=sha,
             path=str(path),nvars=n,nclauses=len(clauses),family='GENERATED:'+family,
             split=FAMILIES[family],oracle='SAT_PLANTED_WITNESS',source_kind='GENERATED_NOT_OFFICIAL')

def make_manifest():
 root=ROOT/'generated'
 sources=[gen_source(family,i,root) for split,fs in SPLITS.items() for family in fs for i in range(N_PER_FAMILY)]
 if len(sources)!=1000:raise RuntimeError('expected 1000 distinct sources')
 if len({x['sha256'] for x in sources})!=len(sources):raise RuntimeError('duplicate SHA')
 for i,x in enumerate(sources):x['global_id']=i
 for split,fs in SPLITS.items():
  assert len([s for s in sources if s['split']==split])==len(fs)*N_PER_FAMILY
  assert all(s['family'].removeprefix('GENERATED:') in fs for s in sources if s['split']==split)
 manifest=[{k:v for k,v in s.items() if k!='path'} for s in sources]
 data=json.dumps(manifest,sort_keys=True,separators=(',',':'))+'\n'
 ROOT.mkdir(parents=True,exist_ok=True)
 (ROOT/'frozen_manifest.json').write_text(data)
 sha=hashlib.sha256(data.encode()).hexdigest()
 return sources,sha

def verify_sat(path,stdout,nvars):
 assn={}
 for line in stdout.splitlines():
  if not line.startswith('v '):continue
  for token in line[2:].split():
   a=int(token)
   if a==0:continue
   if abs(a) in assn:return False
   assn[abs(a)]=(a>0)
 if len(assn)!=nvars:return False
 n=0;count=0;clause=[]
 with Path(path).open() as f:
  for line in f:
   if line.startswith(('c','%')) or not line.strip():continue
   if line.startswith('p '):n=int(line.split()[2]);continue
   for tok in line.split():
    x=int(tok)
    if not x:
     if not any(assn[abs(y)]==(y>0) for y in clause):return False
     count+=1;clause=[]
    else:clause.append(x)
 return n==nvars and not clause and count>0

def run_one(src,cap,dir,keep_trace=True):
 path=Path(src['path'])
 if hashlib.sha256(path.read_bytes()).hexdigest()!=src['sha256']:raise RuntimeError('source hash changed')
 trace_path=dir/'traces'/(src['sha256'][:20]+'.jsonl')
 trace_path.parent.mkdir(parents=True,exist_ok=True)
 cmd=[str(SOLVER),str(path),'--mode','trace','--time',str(cap),'--stats','--transitions',str(trace_path)]
 t=time.monotonic()
 try:cp=subprocess.run(cmd,text=True,capture_output=True,timeout=cap+1.5)
 except subprocess.TimeoutExpired:cp=None
 elapsed=time.monotonic()-t
 if cp and cp.returncode not in (0,10,20):raise RuntimeError(f'X41 error {src["formula_id"]} return {cp.returncode}: {cp.stderr[-1500:]}')
 if cp and cp.returncode==20:raise RuntimeError('SAT witness contradicts native UNSAT output; audit required')
 status='UNKNOWN'
 if cp and cp.returncode==10:
  if not verify_sat(path,cp.stdout,src['nvars']):raise RuntimeError('invalid SAT witness: '+src['formula_id'])
  if elapsed<=cap:status='SAT_VERIFIED'
 rows=[]
 if trace_path.exists():
  with trace_path.open() as f:
   header=json.loads(next(f))
   if header.get('type')!='meta' or header.get('version')!=2:raise RuntimeError('bad trace schema')
   for l in f:
    x=json.loads(l)
    if x.get('type')!='transition':raise RuntimeError('bad event')
    label=(x.get('remaining_finish_wall_s') if status=='SAT_VERIFIED' else None)
    rows.append(dict(formula_id=src['formula_id'],sha256=src['sha256'],family=src['family'],
                     split=src['split'],nvars=src['nvars'],nclauses=src['nclauses'],
                     result=status,before=x['before'],after=x['after'],logic=x['logic'],
                     structure=x['structure'],label_remaining_wall_s=label,
                     label_is_retrospective_same_policy=True))
  trace_path.unlink()
 return dict(formula_id=src['formula_id'],sha256=src['sha256'],family=src['family'],split=src['split'],
             status=status,e2e_s=round(elapsed,6),PAR2_verified_s=round(elapsed if status=='SAT_VERIFIED' else 2*cap,6),
             wall_band='under_50ms' if status=='SAT_VERIFIED' and elapsed<.05 else 'target_50ms_to_3s' if status=='SAT_VERIFIED' and .05<=elapsed<=3 else 'unsolved_or_other',
             transition_samples=len(rows)),rows

def main():
 p=argparse.ArgumentParser()
 p.add_argument('--shard',type=int,required=True);p.add_argument('--shards',type=int,default=4)
 p.add_argument('--cap',type=float,default=3.0);p.add_argument('--dry-run',action='store_true')
 args=p.parse_args()
 if args.shards<1 or args.shard<0 or args.shard>=args.shards or not (0.1<=args.cap<=15):p.error('invalid shard/cap')
 if not args.dry_run and not SOLVER.is_file():p.error('missing build/drnas-x41')
 if hasattr(os,'sched_setaffinity'):os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
 sources,manifest_hash=make_manifest()
 shard_dir=ROOT/('shard_'+str(args.shard))
 shard_dir.mkdir(parents=True,exist_ok=True)
 expected=[s for s in sources if s['global_id']%args.shards==args.shard]
 if args.dry_run:
  print('X42_MANIFEST '+json.dumps(dict(count=len(sources),sha256=manifest_hash,shard=args.shard,
         shard_sources=len(expected),splits=dict(collections.Counter(x['split'] for x in sources))),sort_keys=True));return
 counts=collections.defaultdict(collections.Counter)
 total_transitions=0;duration=0
 with (shard_dir/'trials.jsonl').open('w') as trials,(shard_dir/'transitions.jsonl').open('w') as trans:
  for i,src in enumerate(expected,1):
   result,transitions=run_one(src,args.cap,shard_dir)
   trials.write(json.dumps(result,sort_keys=True)+'\n');trials.flush()
   for step in transitions:trans.write(json.dumps(step,separators=(',',':'))+'\n')
   trans.flush()
   total_transitions+=len(transitions);duration+=result['e2e_s']
   cnt=counts[src['split']];cnt['total']+=1;cnt['sat_verified']+=(result['status']=='SAT_VERIFIED')
   cnt['target_band']+=(result['wall_band']=='target_50ms_to_3s')
   cnt['too_easy']+=(result['wall_band']=='under_50ms')
   cnt['unknown']+=(result['status']=='UNKNOWN')
   cnt['par2_s']+=result['PAR2_verified_s']
   if i%10==0 or i==len(expected):emit('X42_PROGRESS',dict(shard=args.shard,done=i,total=len(expected),
      sat=sum(x['sat_verified'] for x in counts.values()),target=sum(x['target_band'] for x in counts.values()),transitions=total_transitions))
 summary=dict(shard=args.shard,shards=args.shards,manifest_sha256=manifest_hash,counts={k:dict(v) for k,v in counts.items()},
              sources=len(expected),transitions=total_transitions,e2e_s=round(duration,4),
              metadata='GENERATED 1000 planted SAT originals; source-family-disjoint; do not call official industrial originals')
 (shard_dir/'report.json').write_text(json.dumps(summary,indent=2,sort_keys=True)+'\n')
 emit('X42_SHARD_FINAL',summary)

if __name__=='__main__':main()