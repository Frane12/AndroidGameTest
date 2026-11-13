#!/usr/bin/env python3
"""DRNAS X4.3: 3,000 SOURCE-IDENTICAL CNFs, sequential paired learning cycles.

Two full cycles share an immutable SHA manifest. In cycle 1, X4.1 records
passive transitions while X4.1 CORE and X3 ADAPTIVE provide paired outcomes.
A regularized source-only router learns only from the TRAIN families; its
threshold is selected on VALIDATION families and frozen before cycle 2.
Cycle 2 reruns the EXACT SAME CNFs with both controls, the learned router, and
an explicitly labelled same-SHA memorization comparator. The memo comparator
is never called 'generalization' and has no role in model fitting.
No third-party SAT solver is linked or called by DRNAS.
"""
from __future__ import annotations
import argparse, collections, hashlib, json, math, os, pathlib, random, statistics, subprocess, sys, time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import drnas_x42_1000 as G

ROOT=pathlib.Path('drnas_x43_results')
X41=pathlib.Path('build/drnas-x41')
X3=pathlib.Path('build/drnas-x3')
SEED_ID='x43-3000-two-cycle-20261113-frozen-v1'
FAMILY_SIZE=300
SHARDS=12
CAP=3.0
FEATURES=['ln_vars','ln_clauses','density','fraction_4plus','fraction_neg',
          'degree_cv','top8_degree_share','max_degree_ratio','polarity_balance',
          'block20_cooccurrence','duplicate_fraction','binary_clause_fraction']
ARM_CORE='X41_CORE';ARM_ADAPT='X3_ADAPTIVE'


def emit(tag, value):
 print(tag+' '+json.dumps(value, sort_keys=True, separators=(',',':')),flush=True)


def sources_and_hash():
 # Exact X4.2 generator families; fresh seed namespace, 300 per family.
 G.ROOT=ROOT
 G.SAMPLE_HASH=SEED_ID
 generated=ROOT/'generated'
 sources=[G.gen_source(family,i,generated) for split,families in G.SPLITS.items()
          for family in families for i in range(FAMILY_SIZE)]
 for idx,source in enumerate(sources):source['global_id']=idx
 metadata=[{k:v for k,v in source.items() if k!='path'} for source in sources]
 manifest=json.dumps(metadata,sort_keys=True,separators=(',',':'))+'\n'
 ROOT.mkdir(parents=True,exist_ok=True)
 (ROOT/'frozen_manifest.json').write_text(manifest)
 manifest_sha=hashlib.sha256(manifest.encode()).hexdigest()
 expected={'train':1800,'validation':600,'holdout':600}
 if len(sources)!=3000 or len({s['sha256'] for s in sources})!=3000:
  raise RuntimeError('Expected 3000 unique CNF SHA')
 if dict(collections.Counter(s['split'] for s in sources))!=expected:
  raise RuntimeError('Training/validation/holdout wrong')
 fam=collections.defaultdict(set)
 for src in sources:fam[src['family']].add(src['split'])
 if any(len(v)!=1 for v in fam.values()):raise RuntimeError('Family leakage')
 return sources,manifest_sha


def extract_features(path, n, nclauses):
 """Source-content ONLY, no SHA, family, filename, outcomes or SAT witnesses."""
 degrees=[0]*n;plus=[0]*n;minus=[0]*n
 widths=collections.Counter(); dup=set(); repeats=0
 negative=0; literal_count=0; block_pairs=0; pair_total=0
 with pathlib.Path(path).open() as f:
  for raw in f:
   if not raw.strip() or raw.startswith(('c','p','%')):continue
   c=[int(v) for v in raw.split() if int(v)]
   if not c:continue
   widths[len(c)]+=1
   key=tuple(sorted(c))
   if key in dup:repeats+=1
   else:dup.add(key)
   for lit in c:
    v=abs(lit)-1
    degrees[v]+=1
    if lit>0:plus[v]+=1
    else:minus[v]+=1;negative+=1
    literal_count+=1
   for i in range(len(c)):
    for j in range(i+1,len(c)):
     pair_total+=1
     block_pairs+=(abs(c[i])-1)//20==(abs(c[j])-1)//20
 if sum(widths.values())!=nclauses:raise RuntimeError('Input count changed')
 mean_deg=literal_count/max(1,n)
 variance=sum((a-mean_deg)**2 for a in degrees)/max(1,n)
 pol=sum(abs(p-m)/(p+m) for p,m in zip(plus,minus) if p+m)/max(1,sum(p+m>0 for p,m in zip(plus,minus)))
 return [math.log1p(n),math.log1p(nclauses),nclauses/max(1,n),
         sum(v for w,v in widths.items() if w>=4)/max(1,nclauses),
         negative/max(1,literal_count),
         math.sqrt(variance)/max(1.,mean_deg),
         sum(sorted(degrees,reverse=True)[:8])/max(1,literal_count),
         max(degrees,default=0)/max(1.,mean_deg),pol,
         block_pairs/max(1,pair_total),repeats/max(1,nclauses),
         sum(v for w,v in widths.items() if w<=2)/max(1,nclauses)]


def checked_run(src, arm, cap, trans_dir=None):
 path=pathlib.Path(src['path'])
 if hashlib.sha256(path.read_bytes()).hexdigest()!=src['sha256']:
  raise RuntimeError('Original CNF SHA mismatch: '+src['formula_id'])
 if arm in ('X41_CORE','X41_TRACE'):
  cmd=[str(X41),str(path),'--mode','trace' if arm=='X41_TRACE' else 'core',
       '--time',str(cap),'--stats']
 else:
  cmd=[str(X3),str(path),'--mode','x3','--time',str(cap),'--stats']
 trace_path=None
 if arm=='X41_TRACE' and trans_dir is not None:
  trans_dir.mkdir(parents=True,exist_ok=True)
  trace_path=trans_dir/(src['sha256'][:24]+'.jsonl')
  cmd+=['--transitions',str(trace_path)]
 start=time.perf_counter()
 try:
  cp=subprocess.run(cmd,capture_output=True,text=True,timeout=cap+1.5)
 except subprocess.TimeoutExpired:
  cp=None
 elapsed=time.perf_counter()-start
 if cp and cp.returncode not in (0,10,20):
  raise RuntimeError(f'Native solver error {src["formula_id"]} {arm}: {cp.stderr[-500:]}')
 if cp and cp.returncode==20:
  raise RuntimeError('Native UNSAT contradicts mathematically planted SAT: '+src['formula_id'])
 status='UNKNOWN'
 if cp and cp.returncode==10:
  if not G.verify_sat(path,cp.stdout,src['nvars']):
   raise RuntimeError('SAT witness verification failed: '+src['formula_id'])
  if elapsed<=cap:status='SAT_VERIFIED'
 stats={}
 if cp:
  prefix='X41_STATS ' if arm.startswith('X41') else 'X3_STATS '
  for ln in cp.stderr.splitlines():
   if ln.startswith(prefix):stats=json.loads(ln[len(prefix):])
 record={'status':status,'e2e_s':round(elapsed,6),
         'PAR2_s':round(elapsed if status=='SAT_VERIFIED' else 2*cap,6),
         'decisions':stats.get('decisions'),'conflicts':stats.get('conflicts')}
 meta={'trace_rows':0,'verified_future_rows':0,'implied_sum':0,'conflict_samples':0,
       'mean_structural_gain':None,'sample_first':None}
 if trace_path and trace_path.exists():
  gains=[]
  with trace_path.open() as f:
   header=json.loads(next(f))
   if header.get('type')!='meta' or header.get('version')!=2:raise RuntimeError('Unexpected trace schema')
   for ln in f:
    row=json.loads(ln)
    if row.get('type')!='transition':raise RuntimeError('Bad transition')
    meta['trace_rows']+=1
    if status=='SAT_VERIFIED' and row.get('remaining_finish_wall_s') is not None:
     meta['verified_future_rows']+=1
    logic=row.get('logic',{});structure=row.get('structure',{})
    meta['implied_sum']+=max(0,int(logic.get('unit_propagations_under_assumptions',0)))
    meta['conflict_samples']+=bool(logic.get('conflict_under_assumptions',False))
    if 'delta_open_long' in structure:
     gains.append(structure['delta_open_long'])
    if meta['sample_first'] is None:
     meta['sample_first']={'before':row.get('before'),'after':row.get('after'),
                           'logic':logic,'structure':structure,
                           'remaining_finish_wall_s':row.get('remaining_finish_wall_s') if status=='SAT_VERIFIED' else None}
  if gains:meta['mean_structural_gain']=round(statistics.mean(gains),5)
  trace_path.unlink()
 return record,meta


def source_row(src, features):
 return {'id':src['global_id'],'sha256':src['sha256'],'formula_id':src['formula_id'],
         'split':src['split'],'family':src['family'],'features':features}


def assert_manifest(found,expected):
 if found!=expected:raise RuntimeError(f'Manifest mismatch (source changed): {found} != {expected}')


def run_cycle1(args):
 if not X41.is_file() or not X3.is_file():raise RuntimeError('Compile X41 and X3 first')
 srcs,sha=sources_and_hash()
 if args.manifest_sha:assert_manifest(sha,args.manifest_sha)
 subset=[s for s in srcs if s['global_id']%args.shards==args.shard]
 out=ROOT/f'cycle1_{args.shard}';out.mkdir(parents=True,exist_ok=True)
 totals=collections.Counter();t0=time.monotonic()
 with (out/'trials.jsonl').open('w') as f:
  for k,src in enumerate(subset,1):
   features=extract_features(src['path'],src['nvars'],src['nclauses'])
   # Rotate order by source id to reduce systematic CPU-frequency bias.
   order=[ARM_CORE,ARM_ADAPT]
   if src['global_id']%2:order.reverse()
   results={}
   for arm in order:
    results[arm]=checked_run(src,arm,args.cap)[0]
   observer,meta=checked_run(src,'X41_TRACE',args.cap,out/'tmp')[0:2]
   rec=source_row(src,features)
   rec.update(arms=results,observer=observer,trace=meta)
   f.write(json.dumps(rec,sort_keys=True,separators=(',',':'))+'\n');f.flush()
   totals['processed']+=1
   totals['core_sat']+=results[ARM_CORE]['status']=='SAT_VERIFIED'
   totals['adapt_sat']+=results[ARM_ADAPT]['status']=='SAT_VERIFIED'
   totals['trace_sat']+=observer['status']=='SAT_VERIFIED'
   totals['trace_rows']+=meta['trace_rows'];totals['future_labels']+=meta['verified_future_rows']
   totals['cpu_e2e_s']+=sum(v['e2e_s'] for v in results.values())+observer['e2e_s']
   if k%50==0:emit('X43_CYCLE1_PROGRESS',{'shard':args.shard,'done':k,'total':len(subset),**totals})
 summary={'cycle':1,'shard':args.shard,'shards':args.shards,'manifest_sha256':sha,
          'sources':len(subset),'cap_s':args.cap,'totals':dict(totals),
          'elapsed_wall_s':round(time.monotonic()-t0,3)}
 (out/'report.json').write_text(json.dumps(summary,indent=2)+'\n')
 emit('X43_CYCLE1_FINAL',summary)


def solve_linear(mat,target):
 n=len(target);a=[list(row)+[v] for row,v in zip(mat,target)]
 for i in range(n):
  idx=max(range(i,n),key=lambda j:abs(a[j][i]))
  if abs(a[idx][i])<1e-9:raise RuntimeError('Degenerate fit')
  a[i],a[idx]=a[idx],a[i]
  scale=a[i][i]
  for k in range(i,n+1):a[i][k]/=scale
  for j in range(n):
   if j==i:continue
   ratio=a[j][i]
   for k in range(i,n+1):a[j][k]-=ratio*a[i][k]
 return [a[i][-1] for i in range(n)]


def train_model(allrows,manifest_sha):
 train=[r for r in allrows if r['split']=='train']
 val=[r for r in allrows if r['split']=='validation']
 if len(train)!=1800 or len(val)!=600:raise RuntimeError('Unexpected split for model fitting')
 cols=len(FEATURES)
 centers=[];scales=[]
 for j in range(cols):
  values=sorted(r['features'][j] for r in train)
  centers.append(statistics.median(values))
  scales.append(max(.03,values[int(.75*(len(values)-1))]-values[int(.25*(len(values)-1))]))
 def norm(x):return [max(-5,min(5,(a-c)/s)) for a,c,s in zip(x,centers,scales)]
 X=[];Y=[]
 for r in train:
  a=r['arms'][ARM_CORE]['PAR2_s'];b=r['arms'][ARM_ADAPT]['PAR2_s']
  X.append([1.]+norm(r['features']))
  Y.append(max(-5.,min(5.,math.log((a+.005)/(b+.005)))))
 p=cols+1;A=[[0.0]*p for _ in range(p)];B=[0.0]*p
 for x,y in zip(X,Y):
  for i in range(p):
   B[i]+=x[i]*y
   for j in range(p):A[i][j]+=x[i]*x[j]
 for i in range(1,p):A[i][i]+=40.0
 A[0][0]+=1.0
 weights=solve_linear(A,B)
 model={'schema':1,'kind':'source_only_global_ridge_router',
        'features':FEATURES,'centers':centers,'scales':scales,'weights':weights,
        'threshold':None,'policy':None,'manifest_sha256':manifest_sha,
        'trained_on_split':'train','tuned_on_split':'validation',
        'train_count':len(train),'validation_count':len(val),'holdout_count':600,
        'uses_source_sha':False,'uses_family_id':False,
        'no_per_formula_memo_for_learned_policy':True,'regularization':40.0}
 # Threshold/policy selection ONLY on validation; no holdout results touched.
 policies=['always_core','always_adaptive']+[f'threshold:{v:.2f}' for v in (-.05,0,.05,.10,.20,.35)]
 candidates=[]
 for pol in policies:
  cost=0;solved=0;selected=collections.Counter()
  for r in val:
   arm=choose_arm(model,r['features'],policy=pol)
   selected[arm]+=1
   trial=r['arms'][arm]
   cost+=trial['PAR2_s'];solved+=trial['status']=='SAT_VERIFIED'
  candidates.append({'policy':pol,'PAR2_s':round(cost,5),'solved':solved,'choices':dict(selected)})
 # Tie break is deterministic, prefer safe core if differences negligible.
 best=min(enumerate(candidates),key=lambda z:(z[1]['PAR2_s'],z[0]))[1]
 model['policy']=best['policy'];model['validation_candidates']=candidates
 return model


def choose_arm(model,features,policy=None):
 if policy is None:policy=model['policy']
 if policy=='always_core':return ARM_CORE
 if policy=='always_adaptive':return ARM_ADAPT
 if not policy.startswith('threshold:'):raise ValueError('Invalid policy')
 z=[max(-5,min(5,(a-c)/sc)) for a,c,sc in zip(features,model['centers'],model['scales'])]
 score=model['weights'][0]+sum(a*b for a,b in zip(z,model['weights'][1:]))
 return ARM_ADAPT if score>float(policy.split(':')[1]) else ARM_CORE


def read_one_cycle(folder,kind,shards,source_count,sha=None):
 rows=[];d=pathlib.Path(folder)
 for i in range(shards):
  path=d/f'{kind}-{i}'/'trials.jsonl'
  report_path=path.parent/'report.json'
  if not path.is_file() or not report_path.is_file():raise RuntimeError(f'Missing {path}')
  report=json.loads(report_path.read_text())
  if report['shard']!=i or report['sources']!=source_count//shards or report['shards']!=shards:
   raise RuntimeError('Wrong shard metadata')
  if sha and report['manifest_sha256']!=sha:raise RuntimeError('Manifest SHA changed')
  for ln in path.read_text().splitlines():rows.append(json.loads(ln))
 if len(rows)!=source_count or len({r['sha256'] for r in rows})!=source_count:
  raise RuntimeError('Duplicate or missing original source')
 if len({r['formula_id'] for r in rows})!=source_count:raise RuntimeError('Duplicate formula ID')
 return rows


def fit(args):
 rows=read_one_cycle(args.cycle1_dir,'x43-cycle1',args.shards,3000,args.manifest_sha)
 sha=args.manifest_sha or hashlib.sha256(json.dumps(sorted(r['sha256'] for r in rows)).encode()).hexdigest()
 if args.manifest_sha is None:
  # Need original manifest SHA for cycle 2, not an ad-hoc source set digest.
  sha=json.loads((pathlib.Path(args.cycle1_dir)/'x43-cycle1-0'/'report.json').read_text())['manifest_sha256']
 if any(json.loads((pathlib.Path(args.cycle1_dir)/f'x43-cycle1-{i}'/'report.json').read_text())['manifest_sha256']!=sha for i in range(args.shards)):
  raise RuntimeError('Mismatched input manifests')
 model=train_model(rows,sha)
 output=pathlib.Path(args.model_dir);output.mkdir(parents=True,exist_ok=True)
 (output/'model.json').write_text(json.dumps(model,indent=2,sort_keys=True)+'\n')
 # Per-formula best *observed* arm for diagnostic only. Unlike the model,
 # this is SHA-specific memorization and NOT evidence of generalization.
 with (output/'memo.jsonl').open('w') as f:
  for r in rows:
   a,b=(r['arms'][ARM_CORE]['PAR2_s'],r['arms'][ARM_ADAPT]['PAR2_s'])
   selected=ARM_CORE if a<=b else ARM_ADAPT
   f.write(json.dumps({'sha256':r['sha256'],'choice':selected})+'\n')
 counts=collections.Counter()
 for r in rows:
  counts[r['split']]+=1
 model['cycle1_split_counts']=dict(counts)
 emit('X43_MODEL_FROZEN',{'policy':model['policy'],'manifest_sha256':sha,
                          'train_sources':1800,'validation_sources':600,
                          'holdout_sources':600,
                          'validation_candidates':model['validation_candidates']})


def read_memo(path):
 mem={}
 for ln in pathlib.Path(path).read_text().splitlines():
  row=json.loads(ln)
  if row['sha256'] in mem:raise RuntimeError('Duplicate memo SHA')
  mem[row['sha256']]=row['choice']
 if len(mem)!=3000:raise RuntimeError('Incomplete memo')
 return mem


def run_cycle2(args):
 if not X41.is_file() or not X3.is_file():raise RuntimeError('Compile X41 and X3 first')
 model=json.loads(pathlib.Path(args.model_dir,'model.json').read_text())
 memo=read_memo(pathlib.Path(args.model_dir,'memo.jsonl'))
 sources,sha=sources_and_hash()
 assert_manifest(sha,model['manifest_sha256'])
 subset=[s for s in sources if s['global_id']%args.shards==args.shard]
 out=ROOT/f'cycle2_{args.shard}';out.mkdir(parents=True,exist_ok=True)
 totals=collections.Counter();t0=time.monotonic()
 with (out/'trials.jsonl').open('w') as f:
  for k,src in enumerate(subset,1):
   # Each arm is a fresh process; rotate the execution order to reduce
   # cache/CPU-frequency confounding for the learned-vs-baseline comparison.
   feature_started=time.perf_counter()
   features=extract_features(src['path'],src['nvars'],src['nclauses'])
   chosen=choose_arm(model,features)
   policy_cpu_s=time.perf_counter()-feature_started
   m=memo[src['sha256']]
   order=['CORE','ADAPTIVE','LEARNED','MEMO']
   shift=src['global_id']%len(order)
   order=order[shift:]+order[:shift]
   results={};learned=None;memorized=None
   for label in order:
    if label=='CORE':results[ARM_CORE]=checked_run(src,ARM_CORE,args.cap)[0]
    elif label=='ADAPTIVE':results[ARM_ADAPT]=checked_run(src,ARM_ADAPT,args.cap)[0]
    elif label=='LEARNED':
     run=checked_run(src,chosen,args.cap)[0]
     # Charge the source-only scan and model inference to learned E2E.
     full=run['e2e_s']+policy_cpu_s
     status='SAT_VERIFIED' if run['status']=='SAT_VERIFIED' and full<=args.cap else 'UNKNOWN'
     learned={'status':status,'e2e_s':round(full,6),
              'PAR2_s':round(full if status=='SAT_VERIFIED' else args.cap*2,6),
              'choice':chosen,'model_scan_s':round(policy_cpu_s,6)}
    else:
     memorized=checked_run(src,m,args.cap)[0]
     memorized['choice']=m
   assert learned is not None and memorized is not None and len(results)==2
   # MEMO uses exact source-SHA lookups and is explicitly diagnostic ONLY.
   rec=source_row(src,features)
   rec.update(controls=results,learned=learned,memorized=memorized)
   f.write(json.dumps(rec,sort_keys=True,separators=(',',':'))+'\n');f.flush()
   totals['processed']+=1
   totals['core_sat']+=results[ARM_CORE]['status']=='SAT_VERIFIED'
   totals['adaptive_sat']+=results[ARM_ADAPT]['status']=='SAT_VERIFIED'
   totals['learned_sat']+=learned['status']=='SAT_VERIFIED'
   totals['memo_sat']+=memorized['status']=='SAT_VERIFIED'
   totals['learned_core']+=(chosen==ARM_CORE)
   totals['policy_cost_s']+=policy_cpu_s
   totals['e2e_s']+=sum(v['e2e_s'] for v in results.values())+learned['e2e_s']+memorized['e2e_s']
   if k%50==0:emit('X43_CYCLE2_PROGRESS',{'shard':args.shard,'done':k,'total':len(subset),**totals})
 summary={'cycle':2,'shard':args.shard,'shards':args.shards,'manifest_sha256':sha,
          'model_policy':model['policy'],'sources':len(subset),'cap_s':args.cap,
          'totals':dict(totals),'elapsed_wall_s':round(time.monotonic()-t0,3)}
 (out/'report.json').write_text(json.dumps(summary,indent=2)+'\n')
 emit('X43_CYCLE2_FINAL',summary)


def summarize(rows,field,split):
 arr=[r for r in rows if r['split']==split]
 def get(r):
  parts=field.split('.')
  x=r
  for p in parts:x=x[p]
  return x
 vals=[get(r) for r in arr]
 done=sum(v['status']=='SAT_VERIFIED' for v in vals)
 par2=sum(v['PAR2_s'] for v in vals)
 e2e=sum(v['e2e_s'] for v in vals)
 return {'sources':len(vals),'SAT_verified':done,'UNKNOWN':len(vals)-done,
         'PAR2_s':round(par2,5),'total_E2E_s':round(e2e,5)}


def finish(args):
 model=json.loads(pathlib.Path(args.model_dir,'model.json').read_text())
 first=read_one_cycle(args.cycle1_dir,'x43-cycle1',args.shards,3000,model['manifest_sha256'])
 second=read_one_cycle(args.cycle2_dir,'x43-cycle2',args.shards,3000,model['manifest_sha256'])
 a={r['sha256']:r for r in first}
 if set(a)!={r['sha256'] for r in second}:raise RuntimeError('Cycle 2 uses different SHA inputs')
 for r in second:
  prev=a[r['sha256']]
  if r['formula_id']!=prev['formula_id'] or r['split']!=prev['split'] or r['family']!=prev['family']:
   raise RuntimeError('Cycle pairing mismatch')
  choice=choose_arm(model,r['features'])
  if r['learned']['choice']!=choice:raise RuntimeError('Router model drift')
 splits={}
 for split in ('train','validation','holdout'):
  metrics={
   'cycle1_core':summarize(first,'arms.X41_CORE',split),
   'cycle1_adaptive':summarize(first,'arms.X3_ADAPTIVE',split),
   'cycle1_trace':summarize(first,'observer',split),
   'cycle2_core':summarize(second,'controls.X41_CORE',split),
   'cycle2_adaptive':summarize(second,'controls.X3_ADAPTIVE',split),
   'cycle2_learned':summarize(second,'learned',split),
   'cycle2_memo_same_SHA':summarize(second,'memorized',split),
  }
  num=[r for r in first if r['split']==split]
  q=[r for r in second if r['split']==split]
  counts=collections.Counter(r['learned']['choice'] for r in q)
  metrics['learned_choices']=dict(counts)
  metrics['trace_samples']=sum(r['trace']['trace_rows'] for r in num)
  metrics['future_labeled_trace_samples']=sum(r['trace']['verified_future_rows'] for r in num)
  metrics['model_scan_total_s']=round(sum(r['learned']['model_scan_s'] for r in q),5)
  metrics['family_names']=sorted({r['family'] for r in q})
  def compare(base,challenger):
   wins=loss=ties=0
   for r in q:
    z=r[base]['PAR2_s'] if '.' not in base else r[base.split('.')[0]][base.split('.')[1]]['PAR2_s']
    p=r[challenger]['PAR2_s'] if '.' not in challenger else r[challenger.split('.')[0]][challenger.split('.')[1]]['PAR2_s']
    if p<z-.002:wins+=1
    elif p>z+.002:loss+=1
    else:ties+=1
   return {'faster_pairs':wins,'slower_pairs':loss,'ties':ties}
  metrics['learned_vs_same_cycle_core_pairs']=compare('controls.X41_CORE','learned')
  metrics['learned_vs_same_cycle_adaptive_pairs']=compare('controls.X3_ADAPTIVE','learned')
  splits[split]=metrics
 families={}
 for f in sorted({r['family'] for r in second}):
  subset=[r for r in second if r['family']==f]
  stats={}
  for arm,fn in [('CORE',lambda r:r['controls'][ARM_CORE]),('ADAPTIVE',lambda r:r['controls'][ARM_ADAPT]),
                 ('LEARNED',lambda r:r['learned']),('MEMO',lambda r:r['memorized'])]:
   v=[fn(r) for r in subset]
   stats[arm]={'solved':sum(x['status']=='SAT_VERIFIED' for x in v),'PAR2_s':round(sum(x['PAR2_s'] for x in v),4)}
  families[f]=stats
 report={'status':'COMPLETE','sources':3000,'cycle1_processed':len(first),'cycle2_processed':len(second),
         'source_SHA_set_identical':True,'manifest_sha256':model['manifest_sha256'],
         'generation':'GENERATED planted SAT, not original industrial instances',
         'cap_s':args.cap,'shards':args.shards,'model':{'policy':model['policy'],
          'training_sources':1800,'validation_sources':600,'untouched_family_holdout':600,
          'validation_candidates':model['validation_candidates'],
          'features':model['features'],'no_source_id_or_sha':True},
         'split_results':splits,'family_results':families,
         'limits':('Identical formula replay is not an unseen benchmark; memo arm reuses per-SHA '
                   'best observed strategy solely as a diagnostic. Learned arm uses train-only '
                   'global model selected by validation, never source SHA. Predicting strategy '
                   'does not establish distance to SAT or a causal benefit of individual decisions. '
                   'Training/data generation and baseline comparisons consume CPU and are not '
                   'amortized by one repeat; report their cost separately. UNKNOWN costs 2*cap. '
                   'SAT witnesses independently verified; all planted SAT.')}
 dest=pathlib.Path(args.out);dest.mkdir(parents=True,exist_ok=True)
 (dest/'report.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
 with (dest/'paired_trials.jsonl').open('w') as f:
  for r in second:
   prev=a[r['sha256']]
   f.write(json.dumps({'sha256':r['sha256'],'split':r['split'],'family':r['family'],
     'cycle1':{'core':prev['arms'][ARM_CORE], 'adaptive':prev['arms'][ARM_ADAPT], 'trace':prev['observer']},
     'cycle2':{'core':r['controls'][ARM_CORE],'adaptive':r['controls'][ARM_ADAPT],
               'learned':r['learned'],'memorized':r['memorized']}})+'\n')
 emit('X43_FINAL',{'status':'COMPLETE','sources':3000,'cycle1':len(first),'cycle2':len(second),
                   'source_SHA_set_identical':True,'split_results':splits,
                   'policy':model['policy'],'limitations':report['limits']})


def main():
 ap=argparse.ArgumentParser()
 ap.add_argument('stage',choices=['freeze','cycle1','fit','cycle2','finish'])
 ap.add_argument('--shard',type=int,default=0);ap.add_argument('--shards',type=int,default=SHARDS)
 ap.add_argument('--cap',type=float,default=CAP)
 ap.add_argument('--manifest-sha',default='')
 ap.add_argument('--cycle1-dir',default='x43_cycle1_downloads')
 ap.add_argument('--cycle2-dir',default='x43_cycle2_downloads')
 ap.add_argument('--model-dir',default='x43_model')
 ap.add_argument('--out',default='x43_final')
 args=ap.parse_args()
 if args.shards!=SHARDS or args.shard not in range(args.shards) or args.cap!=CAP:
  ap.error('Frozen protocol: shards=12, cap=3 seconds')
 if hasattr(os,'sched_setaffinity') and args.stage.startswith('cycle'):
  os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
 if args.stage=='freeze':
  sources,sha=sources_and_hash()
  emit('X43_MANIFEST',{'sources':len(sources),'sha256':sha,'cycle_count':2,
                        'split_counts':dict(collections.Counter(s['split'] for s in sources)),
                        'source_kind':'GENERATED_NOT_OFFICIAL'})
  pathlib.Path('x43_manifest_sha.txt').write_text(sha+'\n')
 elif args.stage=='cycle1':run_cycle1(args)
 elif args.stage=='fit':fit(args)
 elif args.stage=='cycle2':run_cycle2(args)
 elif args.stage=='finish':finish(args)

if __name__=='__main__':main()