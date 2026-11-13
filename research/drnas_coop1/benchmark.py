#!/usr/bin/env python3
"""Frozen synthetic A/B: paired arms, serial single CPU, verified PAR2."""
import argparse,hashlib,json,os,pathlib,random,subprocess,time,statistics,signal,resource
from synthetic import FAMILIES,make,text,model_ok
ROOT=pathlib.Path(__file__).resolve().parents[2]
ARMS=['X5_NO_MIN','COOP_OFF','COOP_OBSERVE','COOP_ALGEBRA','COOP_ON']

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--cap',type=float,default=1);ap.add_argument('--repeats',type=int,default=2)
 ap.add_argument('--scale',choices=['smoke','stress'],default='smoke')
 ap.add_argument('--out',default='coop1_results');a=ap.parse_args()
 cpu=min(os.sched_getaffinity(0));os.sched_setaffinity(0,{cpu})
 out=ROOT/a.out;out.mkdir(parents=True,exist_ok=False);casesdir=out/'cnf';casesdir.mkdir()
 cases=[]
 for family in FAMILIES:
  for level in range(3):
   for sample in range(2):
    seed=(1713119 if a.scale=="stress" else 713119)+FAMILIES.index(family)*1000+level*100+sample
    n,cs,expected=make(family,level,seed,a.scale);source=text(n,cs);sha=hashlib.sha256(source.encode()).hexdigest()
    case={'id':len(cases),'family':family,'level':level,'seed':seed,'n':n,'clauses':len(cs),'expected':expected,'sha256':sha}
    (casesdir/f'{case["id"]:03}.cnf').write_text(source);cases.append((case,cs))
 manifest={'scale':a.scale,'purpose':'synthetic mechanism-discovery benchmark, NOT real-formula or blind generalization evidence','cpu':cpu,'cap_s':a.cap,'repeats':a.repeats,'arms':ARMS,'cases':[c for c,_ in cases],
 'binaries':{x:hashlib.sha256((ROOT/'build'/x).read_bytes()).hexdigest() for x in ['drnas-coop1','drnas-x5','drat-trim']},
 'generator_sha256':hashlib.sha256(pathlib.Path(__file__).with_name('synthetic.py').read_bytes()).hexdigest()}
 (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
 print('COOP1_START',json.dumps({'cases':len(cases),'trials':len(cases)*a.repeats*len(ARMS),'cpu':cpu,'cap':a.cap}),flush=True)
 trials=[];answers={};log=(out/'trials.jsonl').open('w')
 for case,cs in cases:
  cnf=casesdir/f'{case["id"]:03}.cnf'
  for rep in range(a.repeats):
   order=ARMS.copy();random.Random(913119+case['id']*11+rep).shuffle(order)
   for arm in order:
    stem=f'{case["id"]:03}_{rep}_{arm}';proof=out/(stem+'.drat');usage=out/(stem+'.usage')
    binary='drnas-x5' if arm=='X5_NO_MIN' else 'drnas-coop1'
    cmd=[str(ROOT/'build'/binary),str(cnf),'--mode','core','--x5-no-minimize','--time',str(a.cap),'--stats','--proof',str(proof)]
    if arm!='X5_NO_MIN':cmd+=['--coop1',arm.removeprefix('COOP_').lower()]
    start=time.perf_counter();stdout='';stderr='';rc=0
    before=resource.getrusage(resource.RUSAGE_CHILDREN)
    measured_cmd=['/usr/bin/time','-f','%U %S %M','-o',str(usage),*cmd] if pathlib.Path('/usr/bin/time').exists() else cmd
    q=subprocess.Popen(measured_cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True)
    try:
     stdout,stderr=q.communicate(timeout=a.cap+0.5);rc=q.returncode
    except subprocess.TimeoutExpired:
     os.killpg(q.pid,signal.SIGKILL);stdout,stderr=q.communicate();rc=0
    elapsed=time.perf_counter()-start
    after=resource.getrusage(resource.RUSAGE_CHILDREN)
    (out/(stem+'.stdout')).write_text(stdout);(out/(stem+'.stderr')).write_text(stderr)
    if rc not in (0,10,20):raise RuntimeError((stem,rc,stderr))
    status='UNKNOWN';verified=False;check_start=time.perf_counter()
    if rc==10:
     if not model_ok(case['n'],cs,stdout):raise RuntimeError(('INVALID_MODEL',stem))
     status='SAT';verified=True
    elif rc==20:
     q=subprocess.run([str(ROOT/'build/drat-trim'),str(cnf),str(proof)],capture_output=True,text=True,timeout=30)
     (out/(stem+'.verification')).write_text(q.stdout+q.stderr)
     if 's VERIFIED' not in q.stdout:raise RuntimeError(('INVALID_PROOF',stem,q.stdout,q.stderr))
     status='UNSAT';verified=True
    check_s=time.perf_counter()-check_start
    if verified:
     expected=case['expected']
     if expected is not None and (status=='SAT')!=expected:raise RuntimeError(('EXPECTED_MISMATCH',stem))
     if case['id'] in answers and answers[case['id']]!=status:raise RuntimeError(('CONTRADICTION',stem))
     answers[case['id']]=status
    accepted=verified and elapsed<=a.cap
    cpu_s=(after.ru_utime+after.ru_stime)-(before.ru_utime+before.ru_stime);rss=None
    if usage.exists():
     vals=usage.read_text().splitlines()[-1].split()
     if len(vals)==3:cpu_s=float(vals[0])+float(vals[1]);rss=int(vals[2])
    stats={}
    for line in stderr.splitlines():
     if line.startswith(('COOP1_STATS ','X41_STATS ','X5_STATS ')):
      stats[line.split(' ',1)[0]]=json.loads(line.split(' ',1)[1])
    trial={**case,'rep':rep,'arm':arm,'status':status,'verified':verified,'accepted':accepted,'e2e_s':elapsed,'PAR2_s':elapsed if accepted else 2*a.cap,'check_s':check_s,'cpu_s':cpu_s,'maxrss_kib':rss,'proof_bytes':proof.stat().st_size if proof.exists() else 0,'stats':stats}
    trials.append(trial);log.write(json.dumps(trial)+'\n');log.flush()
  print('COOP1_PROGRESS',json.dumps({'completed':case['id']+1,'total':len(cases),'trials':len(trials)}),flush=True)
 log.close()
 def summarize(rows):
  result={}
  for arm in ARMS:
   rr=[x for x in rows if x['arm']==arm]
   co=[x['stats'].get('COOP1_STATS',{}) for x in rr]
   result[arm]={'attempts':len(rr),'verified':sum(x['verified'] for x in rr),'accepted':sum(x['accepted'] for x in rr),'SAT':sum(x['accepted'] and x['status']=='SAT' for x in rr),'UNSAT':sum(x['accepted'] and x['status']=='UNSAT' for x in rr),'PAR2_s':sum(x['PAR2_s'] for x in rr),'maxrss_kib':(max((x['maxrss_kib'] or 0) for x in rr) or None),
    'lemmas':sum(x.get('lemmas',0) for x in co),'conditioned':sum(x.get('conditioned',0) for x in co),'applied_hints':sum(x.get('applied_hints',0) for x in co),'analysis_ms':sum(x.get('analysis_ms',0) for x in co)}
  return result
 report={'status':'COMPLETE','promotion':False,'scope':manifest['purpose'],'overall':summarize(trials),'families':{f:summarize([x for x in trials if x['family']==f]) for f in FAMILIES}}
 (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
 print('COOP1_FINAL',json.dumps(report),flush=True)
if __name__=='__main__':main()
