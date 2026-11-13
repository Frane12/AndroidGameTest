#!/usr/bin/env python3
"""Prospective paired one-CPU benchmark; proof checking included in the budget."""
import argparse,collections,hashlib,json,os,random,signal,subprocess,tempfile,time
from pathlib import Path
import drnas_x47_long_bench as B
ROOT=Path(__file__).resolve().parents[1]
ARMS=['CORE','X46_LEARNED','X5','X5_NO_MIN','X5_RETAIN','X5_RESTART']

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def emit(tag,x):print(tag+' '+json.dumps(x,sort_keys=True),flush=True)
def run(arm,source,cnf,td,a):
    proof=td/'proof.drat';rss=td/'rss.txt'
    proof.unlink(missing_ok=True);rss.unlink(missing_ok=True)
    if arm in ('Kissat','CaDiCaL','CMS'):
        binary=Path(getattr(a,{'Kissat':'kissat','CaDiCaL':'cadical','CMS':'cms'}[arm])).resolve()
        cmd=[str(binary),str(cnf),str(proof)] if arm!='CMS' else [str(binary),'--threads=1','--verb=0','--frat='+str(proof),str(cnf)]
    else:
        binary=ROOT/'build'/('frozen-proof' if arm in ('CORE','X46_LEARNED') else 'drnas-x5')
        cmd=[str(binary),str(cnf),'--mode','core','--stats','--time',str(a.cap),'--proof',str(proof)]
        if arm=='X46_LEARNED':cmd+=['--branch-at','4','--x46-conflicts','8','--x46-probe-ms','2.5','--x46-model',str(a.model.resolve())]
        if arm=='X5_NO_MIN':cmd+=['--x5-no-minimize']
        if arm=='X5_RETAIN':cmd+=['--x5-retain']
        if arm=='X5_RESTART':cmd+=['--x5-restarts']
    start=time.monotonic();output='';stderr='';status='TIMEOUT';verified=False
    try:
        p=subprocess.Popen([str(ROOT/'build/timed'),str(rss),*cmd],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True)
        try:output,stderr=p.communicate(timeout=a.cap)
        except subprocess.TimeoutExpired:
            os.killpg(p.pid,signal.SIGKILL);p.communicate();raise
        if p.returncode not in (0,10,20):raise RuntimeError((arm,p.returncode,stderr[-1800:]))
        status={0:'UNKNOWN',10:'SAT',20:'UNSAT'}[p.returncode]
    except subprocess.TimeoutExpired:pass
    solve=time.monotonic()-start;check_start=time.monotonic()
    if status=='SAT':
        verified=B.verify_model_on_original_text(source,output)
        if not verified:raise AssertionError(('invalid original-CNF witness',arm,source['sha256']))
        if source.get('cert')=='PHP_STRUCTURAL_CORE':raise AssertionError('false SAT')
    if status=='UNSAT':
        if source.get('cert')=='SAT_CONSTRUCTED_CHECK_WITNESS':raise AssertionError('false UNSAT')
        remaining=a.cap-(time.monotonic()-start)
        if remaining>0:
            try:
                verify_cmd=[str(a.frat.resolve()),'elab',str(proof),str(cnf),'-v'] if arm=='CMS' else [str(a.checker.resolve()),str(cnf),str(proof)]
                q=subprocess.run(verify_cmd,capture_output=True,text=True,timeout=remaining)
                verified=(q.returncode==0 and 'VERIFIED' in q.stdout.splitlines()) if arm=='CMS' else ('s VERIFIED' in q.stdout and (q.returncode==0 or 'c trivial UNSAT' in q.stdout))
                if not verified:raise AssertionError(('invalid independent DRAT proof',arm,q.stdout[-1000:]))
            except subprocess.TimeoutExpired:pass
    check=time.monotonic()-check_start;total=time.monotonic()-start
    accepted=verified and total<=a.cap
    stats={};extra={}
    for l in stderr.splitlines():
        if l.startswith('X41_STATS '):stats=json.loads(l[10:])
        if l.startswith('X5_STATS '):extra=json.loads(l[9:])
    peak=None
    if rss.exists():
        try:peak=int(rss.read_text().splitlines()[-1])
        except (ValueError,IndexError):pass
    return {'arm':arm,'status':status,'verified':verified,'accepted':accepted,'PAR2':total if accepted else 2*a.cap,'e2e_s':total,'solve_s':solve,'check_s':check,'maxrss_kib':peak,'conflicts':stats.get('conflicts'),'decisions':stats.get('decisions'),'x5':extra}

def summarize(rows,arms):
    totals={}
    for arm in arms:
        rr=[r for r in rows if r['arm']==arm]
        totals[arm]={'trials':len(rr),'solved':sum(r['accepted'] for r in rr),'SAT':sum(r['accepted'] and r['status']=='SAT' for r in rr),'UNSAT':sum(r['accepted'] and r['status']=='UNSAT' for r in rr),'PAR2_s':sum(r['PAR2'] for r in rr),'maxrss_completed_kib':max((r['maxrss_kib'] or 0 for r in rr),default=0),'rss_unavailable_trials':sum(r['maxrss_kib'] is None for r in rr),'conflicts':sum(r['conflicts'] or 0 for r in rr)}
    return totals

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--out',type=Path,required=True);p.add_argument('--count',type=int,default=48)
    p.add_argument('--offset',type=int,default=5200000);p.add_argument('--cap',type=float,default=2)
    p.add_argument('--repeats',type=int,default=2);p.add_argument('--shard',type=int,default=0);p.add_argument('--shards',type=int,default=1)
    p.add_argument('--model',type=Path,default=ROOT/'experiments/drnas_x5/frozen_models/frozen_cost_model.txt')
    p.add_argument('--checker',type=Path,default=ROOT/'build/drat-trim')
    p.add_argument('--arms',default=','.join(ARMS));p.add_argument('--official',action='store_true');p.add_argument('--local-sources',type=Path)
    p.add_argument('--frat',type=Path,default=ROOT/'build/frat-rs');p.add_argument('--kissat');p.add_argument('--cadical');p.add_argument('--cms')
    a=p.parse_args();arms=a.arms.split(',')
    assert a.cap>0 and a.repeats>=1 and a.count>0 and 0<=a.shard<a.shards
    assert a.offset>=5000000
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    a.out.mkdir(parents=True,exist_ok=False)
    if a.official:
        from drnas_x47_official_dedup import official_sources
        cases=official_sources(a.count)
    elif a.local_sources:
        cases=[]
        for f in sorted(a.local_sources.glob('*.cnf'))[:a.count]:
            text=f.read_text();h=next(l.split() for l in text.splitlines() if l.startswith('p cnf '))
            cases.append({'content':text,'nvars':int(h[2]),'nclauses':int(h[3]),'sha256':sha(f),'family':f.stem,'cert':'UNVERIFIED','source_path':str(f)})
    else:
        assert a.count%6==0
        cases=[B.make_synthetic(f,a.offset+i) for i in range(a.count//6) for f in B.SYNTH_FAMILIES]
    assert len(cases)==a.count and len({c['sha256'] for c in cases})==a.count
    cases=[s for i,s in enumerate(cases) if i%a.shards==a.shard]
    model_sha=sha(a.model) if 'X46_LEARNED' in arms else None
    manifest={'cohort':'official_retrospective' if a.official or a.local_sources else 'synthetic','count':len(cases),'total_count':a.count,'cap':a.cap,'repeats':a.repeats,'arms':arms,'source_offset':a.offset,'shard':a.shard,'shards':a.shards,'logical_cpus':list(os.sched_getaffinity(0)),'model_sha256':model_sha,'candidate_sha256':sha(ROOT/'src/drnas_x5.cpp'),'baseline_sha256':sha(ROOT/'src/drnas_x41.cpp'),'checker_sha256':sha(a.checker),'sources':[{k:v for k,v in s.items() if k not in ('content','clauses')} for s in cases]}
    (a.out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    rows=[]
    with tempfile.TemporaryDirectory() as tmp,(a.out/'trials.jsonl').open('w') as log:
        td=Path(tmp);cnf=td/'original.cnf'
        for i,s in enumerate(cases):
            cnf.write_text(s['content']);assert sha(cnf)==s['sha256']
            for rep in range(a.repeats):
                order=list(arms);random.Random(a.offset+i*31+rep).shuffle(order)
                for arm in order:
                    r=run(arm,s,cnf,td,a);r.update({'sha256':s['sha256'],'family':s['family'],'rep':rep,'shard':a.shard})
                    rows.append(r);log.write(json.dumps(r,sort_keys=True)+'\n');log.flush()
                    emit('X5_TRIAL',r)
            emit('X5_PROGRESS',{'completed':i+1,'sources':len(cases),'totals':summarize(rows,arms)})
    if model_sha:assert sha(a.model)==model_sha
    report={'cohort':manifest['cohort'],'sources':len(cases),'trials':len(rows),'totals':summarize(rows,arms),'by_family':{f:summarize([r for r in rows if r['family']==f],arms) for f in sorted({r['family'] for r in rows})}}
    (a.out/'report.json').write_text(json.dumps(report,indent=2)+'\n');emit('X5_FINAL',report)
if __name__=='__main__':main()
