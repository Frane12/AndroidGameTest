#!/usr/bin/env python3
"""Original SAT2024 application encodings; unchanged COOP1, no cross-instance training."""
import argparse, collections, hashlib, json, lzma, os, pathlib, random, re, resource, signal, subprocess, sys, time
ROOT=pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'research/drnas_coop1'))
from synthetic import model_ok
ARCHIVE='https://zenodo.org/records/15095752/files/sat-competition-2024-main-benchmarks.zip?download=1'
ARMS=['X5_NO_MIN','COOP_OFF','COOP_ALGEBRA','Kissat','CaDiCaL','CryptoMiniSat']
BINS={'X5_NO_MIN':'drnas-x5','COOP_OFF':'drnas-coop1','COOP_ALGEBRA':'drnas-coop1','Kissat':'kissat','CaDiCaL':'cadical','CryptoMiniSat':'cryptominisat5'}
CONTROLS={
'asconhashv12_opt64_H5_M2-xEJ8F_m0_3_U5.c.cnf.xz':'e789f2a90e857bd26bbc9db1dea6d7e509e1391de3f7335e959f93c4fa57b9fc',
'asconhashv12_opt64_H6_M2-PgbpwX_m0_4_U1.c.cnf.xz':'95ad2982de832de5b47f0c6dbe6be62bca36e809b2fa1d6b977770e123e4f455',
'md5_48_1.cnf.xz':'c3e2ac82ab613b6c6d5d605820046f600d4c8cc35b123e1885e37c2a2f89b0a7',
'g2-slp-synthesis-aes-top30.cnf.xz':'67ee094770a2c735c05a0cadf79e7127c4294a9deeab72a6101b3e9e48a0ac0d'}

def parse(raw):
 n=None;expected=None;cs=[];pending=[]
 for line in raw.splitlines():
  line=line.strip()
  if not line or line.startswith(b'c'):continue
  if line.startswith(b'p '):
   v=line.split()
   if n is not None or len(v)!=4 or v[1]!=b'cnf':raise ValueError('bad header')
   n=int(v[2]);expected=int(v[3]);continue
  if line.startswith(b'%'):break
  if n is None:raise ValueError('missing header')
  for word in line.split():
   lit=int(word)
   if lit:
    if abs(lit)>n:raise ValueError('out of range')
    pending.append(lit)
   else:cs.append(pending);pending=[]
 if n is None or pending or len(cs)!=expected:raise ValueError('DIMACS mismatch')
 return n,cs

def xor_audit(cs):
 """Count explicit complete XOR encodings of width 2..4; not a full detector.
 An original clause blocks one assignment; a full parity class blocks 2^(k-1).
 This audit is outside measured solving and is never passed to any solver.
 """
 groups=collections.defaultdict(set)
 for c in cs:
  if not 2<=len(c)<=4 or len({abs(l) for l in c})!=len(c):continue
  cc=sorted(c,key=abs);support=tuple(map(abs,cc))
  bits=sum((l<0)<<i for i,l in enumerate(cc))
  groups[support].add(bits)
 counts=collections.Counter()
 for vs,masks in groups.items():
  for parity in (0,1):
   if sum(m.bit_count()%2==parity for m in masks)==1<<(len(vs)-1):
    counts[str(len(vs))]+=1
 return dict(sorted(counts.items()))

def selected(name):
 name=pathlib.PurePosixPath(name).name
 m=re.fullmatch(r'simon-r(\d+)-\d+\.sanitized\.cnf\.xz',name)
 return bool(m and 16<=int(m[1])<=21) or name in CONTROLS

def collect(out,local=None):
 raw_cases=[]
 if local:
  local=pathlib.Path(local);manifest=json.loads((local/'manifest.json').read_text())
  for c in manifest['cases']:
   if selected(c['source_file']):
    raw=(local/(c['sha256']+'.cnf')).read_bytes()
    assert hashlib.sha256(raw).hexdigest()==c['sha256']
    raw_cases.append((c['source_file'],raw))
 else:
  from remotezip import RemoteZip
  with RemoteZip(ARCHIVE,timeout=90) as z:
   candidates=sorted((e for e in z.infolist() if not e.is_dir() and selected(e.filename)),key=lambda e:e.filename)
   if not 2<=len(candidates)<=20:raise RuntimeError(('unexpected selection count',len(candidates)))
   for e in candidates:
    if e.file_size>4*1024**2:raise RuntimeError('compressed input too large')
    d=lzma.LZMADecompressor();raw=d.decompress(z.read(e),max_length=32*1024**2+1)
    if not d.eof or len(raw)>32*1024**2:raise RuntimeError('truncated/oversize input')
    raw_cases.append((e.filename,raw))
 cases=[];seen=set();case_dir=out/'cnf';case_dir.mkdir()
 for name,raw in sorted(raw_cases):
  sha=hashlib.sha256(raw).hexdigest();base=pathlib.PurePosixPath(name).name
  if base in CONTROLS and sha!=CONTROLS[base]:raise RuntimeError(('changed control input',base))
  if sha in seen:raise RuntimeError('duplicate original input')
  seen.add(sha);n,cs=parse(raw);eligible=n<=4096 and len(cs)<=12000
  family='simon' if base.startswith('simon-') else ('ascon' if base.startswith('ascon') else ('md5' if base.startswith('md5') else 'aes_synthesis'))
  cohort='active_simon' if family=='simon' else 'size_gate_control'
  if (cohort=='active_simon')!=eligible:raise RuntimeError('unexpected COOP1 size eligibility')
  (case_dir/(sha+'.cnf')).write_bytes(raw)
  case={'id':len(cases),'family':family,'cohort':cohort,'source_file':name,'sha256':sha,'vars':n,'clauses':len(cs),'bytes':len(raw),'size_gate_eligible':eligible,'explicit_xor_groups_by_width':xor_audit(cs)}
  cases.append(case);print('COOP1_REAL_SOURCE',json.dumps(case),flush=True)
 if sum(c['cohort']=='active_simon' for c in cases)<2:raise RuntimeError('too few original Simon instances')
 return cases

def command(arm,cnf,proof,cap):
 exe=str(ROOT/'build'/BINS[arm])
 if arm in ('X5_NO_MIN','COOP_OFF','COOP_ALGEBRA'):
  cmd=[exe,str(cnf),'--mode','core','--x5-no-minimize','--time',str(cap),'--stats','--proof',str(proof)]
  if arm!='X5_NO_MIN':cmd+=['--coop1',arm.removeprefix('COOP_').lower()]
  return cmd
 if arm=='CryptoMiniSat':return [exe,'--threads=1',str(cnf),str(proof)]
 return [exe,str(cnf),str(proof)]

def run(case,cs,arm,rep,out,cap):
 cnf=out/'cnf'/(case['sha256']+'.cnf');stem=f'{case["id"]:03}_{rep}_{arm}'
 proof=out/(stem+'.drat');usage=out/(stem+'.usage');cmd=command(arm,cnf,proof,cap)
 measured=['/usr/bin/time','-f','%U %S %M','-o',str(usage),*cmd] if pathlib.Path('/usr/bin/time').exists() else cmd
 before=resource.getrusage(resource.RUSAGE_CHILDREN);start=time.perf_counter()
 p=subprocess.Popen(measured,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True)
 killed=False
 try:stdout,stderr=p.communicate(timeout=cap+0.15)
 except subprocess.TimeoutExpired:
  killed=True;os.killpg(p.pid,signal.SIGKILL);stdout,stderr=p.communicate()
 elapsed=time.perf_counter()-start;after=resource.getrusage(resource.RUSAGE_CHILDREN)
 (out/(stem+'.stdout')).write_text(stdout);(out/(stem+'.stderr')).write_text(stderr)
 rc=p.returncode;status='UNKNOWN';verified=False;check_start=time.perf_counter()
 if not killed and rc not in (0,10,20):raise RuntimeError(('SOLVER_ERROR',stem,rc,stderr[-1000:]))
 if not killed and rc==10:
  if not model_ok(case['vars'],cs,stdout):raise RuntimeError(('INVALID_MODEL',stem))
  status='SAT';verified=True
 elif not killed and rc==20:
  status='UNSAT'
  try:
   check=subprocess.run([str(ROOT/'build/drat-trim'),str(cnf),str(proof)],capture_output=True,text=True,timeout=60)
   (out/(stem+'.verification')).write_text(check.stdout+check.stderr)
   if 's VERIFIED' not in check.stdout:raise RuntimeError(('INVALID_PROOF',stem,check.stdout[-1000:]))
   verified=True
  except subprocess.TimeoutExpired:
   status='UNSAT_UNVERIFIED';(out/(stem+'.verification')).write_text('CHECKER_TIMEOUT_60s\n')
 check_s=time.perf_counter()-check_start
 stats={}
 for line in stderr.splitlines():
  if line.startswith(('COOP1_STATS ','X41_STATS ','X5_STATS ')):
   k,v=line.split(' ',1);stats[k]=json.loads(v)
 cpu_s=(after.ru_utime+after.ru_stime)-(before.ru_utime+before.ru_stime);rss=None
 if usage.exists():
  values=usage.read_text().splitlines()[-1].split()
  if len(values)==3:cpu_s=float(values[0])+float(values[1]);rss=int(values[2])
 accepted=verified and elapsed<=cap
 row={**case,'rep':rep,'arm':arm,'command':cmd,'cap_s':cap,'status':status,'verified':verified,'accepted':accepted,'returncode':rc,'externally_killed':killed,'solve_e2e_s':elapsed,'check_s':check_s,'verified_total_s':elapsed+check_s,'PAR2_s':elapsed if accepted else 2*cap,'cpu_s':cpu_s,'maxrss_kib':rss,'proof_bytes':proof.stat().st_size if proof.exists() else 0,'stats':stats}
 return row

def summarize(rows,arms):
 result={}
 for arm in arms:
  r=[x for x in rows if x['arm']==arm];co=[x['stats'].get('COOP1_STATS',{}) for x in r]
  result[arm]={'attempts':len(r),'accepted':sum(x['accepted'] for x in r),'SAT':sum(x['accepted'] and x['status']=='SAT' for x in r),'UNSAT':sum(x['accepted'] and x['status']=='UNSAT' for x in r),'PAR2_s':sum(x['PAR2_s'] for x in r),'check_s':sum(x['check_s'] for x in r),'lemmas':sum(x.get('lemmas',0) for x in co),'analysis_ms':sum(x.get('analysis_ms',0) for x in co),'blocks':sum(x.get('blocks',0) for x in co),'maxrss_kib':max((x['maxrss_kib'] or 0 for x in r),default=0) or None}
 return result

def preflight(out,arms):
 # Nontrivial UNSAT pigeonhole proof and SAT mixed-sign model; excluded from benchmark.
 out.mkdir();(out/'cnf').mkdir()
 sat=[[1,2],[-1,3],[-2,-3]]
 v=lambda p,h:p*3+h+1
 unsat=[[v(p,h) for h in range(3)] for p in range(4)]+[[-v(p,h),-v(q,h)] for h in range(3) for p in range(4) for q in range(p)]
 rows=[]
 for i,(n,cs,expected) in enumerate([(3,sat,'SAT'),(12,unsat,'UNSAT')]):
  raw=(f'p cnf {n} {len(cs)}\n'+''.join(' '.join(map(str,c))+' 0\n' for c in cs)).encode();sha=hashlib.sha256(raw).hexdigest()
  (out/'cnf'/(sha+'.cnf')).write_bytes(raw)
  case={'id':i,'sha256':sha,'vars':n,'family':'preflight'}
  for arm in arms:
   r=run(case,cs,arm,0,out,3)
   if not r['verified'] or r['status']!=expected:raise RuntimeError(('PREFLIGHT_FAILED',arm,r['status']))
   rows.append(r)
 (out/'report.json').write_text(json.dumps(rows,indent=2)+'\n')
 print('COOP1_REAL_PREFLIGHT PASS',flush=True)

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--out',default='coop1_real_results');ap.add_argument('--local-inputs');ap.add_argument('--native-only',action='store_true');ap.add_argument('--cap',type=float,default=5);ap.add_argument('--repeats',type=int,default=3);ap.add_argument('--active-only',action='store_true');a=ap.parse_args()
 if a.cap<=0 or a.repeats<1:raise ValueError('invalid limits')
 arms=ARMS[:3] if a.native_only else ARMS
 cpu=min(os.sched_getaffinity(0));os.sched_setaffinity(0,{cpu})
 out=ROOT/a.out;out.mkdir(parents=True,exist_ok=False)
 preflight(out/'preflight',arms)
 cases=collect(out,a.local_inputs)
 if a.active_only:cases=[c for c in cases if c['cohort']=='active_simon']
 manifest={'source':'SAT Competition 2024 Main original CNF bytes','archive':ARCHIVE,'selection':'All archive Simon r16..r21 entries, based only on filename/round count; plus 4 SHA-pinned large controls. Local mode only includes previously downloaded members.','known_blind':False,'training':'none; every trial a fresh process; ordinary CDCL clause learning enabled in all arms','local_subset':bool(a.local_inputs),'cpu':cpu,'arms':arms,'active_cap_s':a.cap,'active_repeats':a.repeats,'control_cap_s':1,'control_repeats':1,'metric':'Verified PAR2 uses solver wall time including startup, parse, proof emission, excluding independent checking (reported separately). Missed cap/unknown/unverified=2*cap. Do not pool cohorts with different caps.','cases':cases,'binaries':{b:hashlib.sha256((ROOT/'build'/b).read_bytes()).hexdigest() for b in sorted(set(BINS[x] for x in arms)|{'drat-trim'})}}
 (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
 print('COOP1_REAL_START',json.dumps({k:manifest[k] for k in ('cpu','arms','active_cap_s','active_repeats','control_cap_s','control_repeats')}),flush=True)
 rows=[];answers={}
 with (out/'trials.jsonl').open('w') as log:
  for c in cases:
   raw=(out/'cnf'/(c['sha256']+'.cnf')).read_bytes();assert hashlib.sha256(raw).hexdigest()==c['sha256']
   n,cs=parse(raw);assert n==c['vars']
   cap=a.cap if c['cohort']=='active_simon' else 1
   reps=a.repeats if c['cohort']=='active_simon' else 1
   for rep in range(reps):
    order=arms.copy();random.Random(c['sha256']+str(rep)).shuffle(order)
    for arm in order:
     row=run(c,cs,arm,rep,out,cap)
     if row['verified']:
      if c['sha256'] in answers and answers[c['sha256']]!=row['status']:raise RuntimeError('VERIFIED_CONTRADICTION')
      answers[c['sha256']]=row['status']
     rows.append(row);log.write(json.dumps(row)+'\n');log.flush()
     print('COOP1_REAL_TRIAL',json.dumps(row),flush=True)
 report={'status':'COMPLETE','promotion':False,'cohorts':{group:summarize([r for r in rows if r['cohort']==group],arms) for group in sorted({c['cohort'] for c in cases})},'cases':{c['source_file']:summarize([r for r in rows if r['sha256']==c['sha256']],arms) for c in cases},'limitations':['Application-derived reduced-round cipher encodings; not full-strength cryptanalysis or a representative industrial suite.','Development diagnostic, not blind holdout.','Large controls are outside current COOP1 size gate; their results do not measure active cooperation.','Repeated timings are not independent new formulas; no significance claim from a few correlated Simon instances.','Proof-producing reference configurations; not a comparison against separately tuned no-proof modes.']}
 (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
 print('COOP1_REAL_FINAL',json.dumps(report),flush=True)
if __name__=='__main__':main()
