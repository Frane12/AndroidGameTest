#!/usr/bin/env python3
import select
import argparse,hashlib,json,os,random,signal,subprocess,tempfile,time
from pathlib import Path
import drnas_x5_bench as F
from drnas_x5_mix96 import source
B=F.B;ROOT=F.ROOT;sha=F.sha;emit=F.emit;summarize=F.summarize
ARMS=['X5','X5_NO_MIN','X51_PASSIVE','X51_BOUNDED','X51_ADAPTIVE','Kissat']
def run(arm,source,cnf,td,a):
    proof=td/'proof.drat';rss=td/'rss.txt'
    proof.unlink(missing_ok=True);rss.unlink(missing_ok=True)
    if arm in ('Kissat','CaDiCaL','CMS'):
        binary=Path(getattr(a,{'Kissat':'kissat','CaDiCaL':'cadical','CMS':'cms'}[arm])).resolve()
        cmd=[str(binary),str(cnf),str(proof)] if arm!='CMS' else [str(binary),'--threads=1','--verb=0','--frat='+str(proof),str(cnf)]
    else:
        binary=ROOT/'build'/('frozen-proof' if arm in ('CORE','X46_LEARNED') else ('drnas-x51' if arm.startswith('X51_') else 'drnas-x5'))
        cmd=[str(binary),str(cnf),'--mode','core','--stats','--time',str(a.cap),'--proof',str(proof)]
        if arm=='X46_LEARNED':cmd+=['--branch-at','4','--x46-conflicts','8','--x46-probe-ms','2.5','--x46-model',str(a.model.resolve())]
        if arm.startswith('X51_'):cmd+=['--x51-telemetry']
        if arm=='X51_BOUNDED':cmd+=['--x51-bounded']
        if arm=='X51_ADAPTIVE':cmd+=['--x51-adaptive']
        if arm=='X5_NO_MIN':cmd+=['--x5-no-minimize']
        if arm=='X5_RETAIN':cmd+=['--x5-retain']
        if arm=='X5_RESTART':cmd+=['--x5-restarts']
    start=time.monotonic();output='';stderr='';status='TIMEOUT';verified=False
    with (td/'stdout.log').open('w+') as out,(td/'stderr.log').open('w+') as err:
        p=subprocess.Popen([str(ROOT/'build/timed'),str(rss),*cmd],stdout=out,stderr=err,text=True,start_new_session=True)
        pidfd=os.pidfd_open(p.pid)
        try:
            ready,_,_=select.select([pidfd],[],[],max(0,a.cap-(time.monotonic()-start)))
            if ready:
                p.wait()
                if p.returncode not in (0,10,20):
                    err.seek(0);raise RuntimeError((arm,p.returncode,err.read()[-1800:]))
                status={0:'UNKNOWN',10:'SAT',20:'UNSAT'}[p.returncode]
            else:
                os.killpg(p.pid,signal.SIGKILL);p.wait()
        finally:os.close(pidfd)
        out.seek(0);output=out.read();err.seek(0);stderr=err.read()
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
    stats={};extra={};telemetry=[]
    for l in stderr.splitlines():
        if l.startswith('X51_STATS '):
            try:telemetry.append(json.loads(l[10:]))
            except json.JSONDecodeError:pass # killed while emitting final partial line
        try:
            if l.startswith('X41_STATS '):stats=json.loads(l[10:])
            if l.startswith('X5_STATS '):extra=json.loads(l[9:])
        except json.JSONDecodeError:pass
    peak=None
    if rss.exists():
        try:peak=int(rss.read_text().splitlines()[-1])
        except (ValueError,IndexError):pass
    return {'arm':arm,'status':status,'verified':verified,'accepted':accepted,'PAR2':total if accepted else 2*a.cap,'e2e_s':total,'solve_s':solve,'check_s':check,'maxrss_kib':peak,'conflicts':stats.get('conflicts'),'decisions':stats.get('decisions'),'x5':extra,'solver_stats':stats,'telemetry':telemetry}

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True)
    p.add_argument('--split',choices=('diagnostic','holdout','smoke'),default='diagnostic')
    p.add_argument('--cap',type=float,default=5);p.add_argument('--repeats',type=int,default=3)
    p.add_argument('--per-family',type=int,default=15);p.add_argument('--offset',type=int,default=9900000)
    p.add_argument('--shard',type=int,default=0);p.add_argument('--shards',type=int,default=1)
    p.add_argument('--arms',default=','.join(ARMS))
    p.add_argument('--model',type=Path,default=F.ROOT/'experiments/drnas_x5/frozen_models/frozen_cost_model.txt')
    p.add_argument('--checker',type=Path,default=F.ROOT/'build/drat-trim');p.add_argument('--frat',type=Path,default=F.ROOT/'build/frat-rs')
    p.add_argument('--kissat',default='build/kissat');p.add_argument('--cadical',default='build/cadical');p.add_argument('--cms',default='build/cms')
    a=p.parse_args();assert a.cap>0 and a.repeats>=1 and a.per_family>0 and 0<=a.shard<a.shards
    arms=a.arms.split(',');os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    FAMILIES=('cardinality','xor','random4')
    cases=[source(f,a.offset+i) for f in FAMILIES for i in range(a.per_family)]
    assert len({s['sha256'] for s in cases})==len(cases)
    if a.split!='smoke':
        protocol=json.loads((ROOT/'experiments/drnas_x51/protocol.json').read_text())
        assert {s['sha256'] for s in cases}=={s['sha256'] for s in protocol['sources'][a.split]}
    total=len(cases);random.Random(961113).shuffle(cases);cases=cases[a.shard::a.shards]
    a.out.mkdir(parents=True,exist_ok=False);(a.out/'sources').mkdir()
    manifest={'cohort':a.split,'count':len(cases),'total_count':total,'cap':a.cap,'repeats':a.repeats,'arms':arms,
      'source_offset':a.offset,'shard':a.shard,'shards':a.shards,'logical_cpus':list(os.sched_getaffinity(0)),
      'model_sha256':F.sha(a.model),'frozen_x5_sha256':F.sha(F.ROOT/'src/drnas_x5.cpp'),'generator_sha256':F.sha(F.ROOT/'research/drnas_x5_mix96.py'),'binary_sha256':{n:F.sha(F.ROOT/'build'/n) for n in ('drnas-x5','drnas-x51','kissat','drat-trim')},'candidate_sha256':F.sha(F.ROOT/'src/drnas_x51.cpp'),
      'baseline_sha256':F.sha(F.ROOT/'src/drnas_x41.cpp'),'checker_sha256':F.sha(a.checker),
      'sources':[{k:v for k,v in s.items() if k!='content'} for s in cases]}
    (a.out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');rows=[]
    with tempfile.TemporaryDirectory() as tmp,(a.out/'trials.jsonl').open('w') as log:
        td=Path(tmp)
        for i,s in enumerate(cases):
            cnf=a.out/'sources'/(s['sha256']+'.cnf');cnf.write_text(s['content']);assert F.sha(cnf)==s['sha256']
            for rep in range(a.repeats):
                order=list(arms);random.Random(a.offset+i*31+rep).shuffle(order)
                for arm in order:
                    r=run(arm,s,cnf.resolve(),td,a)
                    if s['expected_status']!='UNKNOWN' and r['status'] in ('SAT','UNSAT'):assert r['status']==s['expected_status'],('wrong result',arm,s['sha256'])
                    r.update({'sha256':s['sha256'],'family':s['family'],'rep':rep,'shard':a.shard,'level':s['level']})
                    rows.append(r);log.write(json.dumps(r,sort_keys=True)+'\n');log.flush();F.emit('X51_TRIAL',r)
            F.emit('X51_PROGRESS',{'completed':i+1,'sources':len(cases),'shard':a.shard})
    assert F.sha(a.model)==manifest['model_sha256']
    r={'cohort':a.split,'sources':len(cases),'trials':len(rows),'totals':F.summarize(rows,arms),
       'by_family':{f:F.summarize([r for r in rows if r['family']==f],arms) for f in FAMILIES if any(r['family']==f for r in rows)}}
    (a.out/'report.json').write_text(json.dumps(r,indent=2)+'\n');F.emit('X51_FINAL',r)
if __name__=='__main__':main()
