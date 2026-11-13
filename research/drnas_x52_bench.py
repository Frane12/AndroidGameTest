#!/usr/bin/env python3
import argparse,hashlib,json,os,random,select,shutil,signal,subprocess,tempfile,time
from pathlib import Path
import drnas_x5_bench as B
from drnas_x5_mix96 import source
ROOT=B.ROOT;ARMS=['X5','X52_OFF','X52_DELETE','Kissat']

def execute(cmd,td,name,limit):
    rss=td/(name+'.rss');rss.unlink(missing_ok=True)
    with (td/(name+'.out')).open('w+') as out,(td/(name+'.err')).open('w+') as err:
        p=subprocess.Popen([str(ROOT/'build/timed'),str(rss),*cmd],stdout=out,stderr=err,text=True,start_new_session=True)
        fd=os.pidfd_open(p.pid)
        try:
            ready,_,_=select.select([fd],[],[],max(0,limit))
            if not ready:os.killpg(p.pid,signal.SIGKILL)
            p.wait()
        finally:os.close(fd)
        out.seek(0);stdout=out.read();err.seek(0);stderr=err.read()
    peak=int(rss.read_text().splitlines()[-1]) if rss.exists() else None
    return p.returncode,stdout,stderr,not bool(ready),peak

def run(arm,s,cnf,td,cap):
    proof=td/'proof.drat';proof.unlink(missing_ok=True)
    if arm=='Kissat':cmd=[str(ROOT/'build/kissat'),str(cnf),str(proof)]
    else:
        cmd=[str(ROOT/'build'/('drnas-x5' if arm=='X5' else 'drnas-x52')),str(cnf),'--mode','core','--stats','--time',str(cap),'--proof',str(proof)]
        if arm=='X52_DELETE':cmd+=['--x52-proof-deletions']
    start=time.monotonic();rc,out,err,timeout,rss=execute(cmd,td,'solve',cap)
    solve=time.monotonic()-start
    if not timeout and rc not in (0,10,20):raise RuntimeError((arm,rc,err[-1000:]))
    status='TIMEOUT' if timeout else {0:'UNKNOWN',10:'SAT',20:'UNSAT'}[rc]
    verified=False;check_rss=None;check_timeout=False;check_start=time.monotonic()
    if status=='SAT':
        verified=B.B.verify_model_on_original_text(s,out);assert verified,('invalid SAT',arm)
    if status in ('SAT','UNSAT') and s['expected_status']!='UNKNOWN':assert status==s['expected_status']
    if status=='UNSAT':
        remaining=cap-(time.monotonic()-start)
        if remaining>0:
            qr,qo,qe,check_timeout,check_rss=execute([str(ROOT/'build/drat-trim'),str(cnf),str(proof)],td,'check',remaining)
            if not check_timeout:
                verified='s VERIFIED' in qo and (qr==0 or 'c trivial UNSAT' in qo)
                assert verified,('invalid proof',arm,qo[-1500:],qe)
        else:check_timeout=True
    check=time.monotonic()-check_start;total=time.monotonic()-start
    st={}
    for l in err.splitlines():
        if l.startswith('X41_STATS '):
            try:st=json.loads(l[10:])
            except json.JSONDecodeError:pass
    # Audit hashes and line counts are metadata collected AFTER timed certification.
    additions=hashlib.sha256();deleted=0
    if arm!='Kissat' and proof.exists():
        with proof.open('rb') as f:
            for line in f:
                if line.startswith(b'd '):deleted+=1
                else:additions.update(line)
    accepted=verified and total<=cap
    return {'arm':arm,'status':status,'verified':verified,'accepted':accepted,'PAR2':total if accepted else 2*cap,
        'e2e_s':total,'solve_s':solve,'check_s':check,'check_timeout':check_timeout,'checker_maxrss_kib':check_rss,
        'maxrss_kib':rss,'conflicts':st.get('conflicts'),'decisions':st.get('decisions'),'solver_stats':st,
        'proof_bytes':proof.stat().st_size if proof.exists() else 0,'proof_deletions':deleted if arm!='Kissat' else None,'addition_sha256':additions.hexdigest() if arm!='Kissat' else None}

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--shard',type=int,default=0);p.add_argument('--shards',type=int,default=3)
    a=p.parse_args();assert 0<=a.shard<a.shards
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    cases=[source(f,10600002+i) for f in ('cardinality','xor','random4') for i in range(8)]
    for s in cases:s['cohort']='fresh24'
    known=source('cardinality',9900004);known['cohort']='known_replay';cases.append(known)
    protocol=json.loads((ROOT/'experiments/drnas_x52/protocol.json').read_text())
    assert {s['sha256'] for s in cases}=={s['sha256'] for s in protocol['sources']}
    assert len({s['sha256'] for s in cases})==25
    random.Random(521113).shuffle(cases);cases=cases[a.shard::a.shards]
    a.out.mkdir(parents=True,exist_ok=False);(a.out/'sources').mkdir();(a.out/'proofs').mkdir()
    manifest={'count':len(cases),'total_count':25,'cap':5,'repeats':3,'shard':a.shard,'shards':a.shards,'arms':ARMS,
        'logical_cpus':list(os.sched_getaffinity(0)),'sources':[{k:v for k,v in s.items() if k!='content'} for s in cases],
        'source_hashes':{f:B.sha(ROOT/f) for f in ('src/drnas_x5.cpp','src/drnas_x52.cpp','research/drnas_x5_mix96.py','experiments/drnas_x52/protocol.json')},
        'binary_hashes':{f:B.sha(ROOT/'build'/f) for f in ('drnas-x5','drnas-x52','kissat','drat-trim','timed')}}
    (a.out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    with tempfile.TemporaryDirectory() as td,(a.out/'trials.jsonl').open('w') as log:
        td=Path(td)
        for i,s in enumerate(cases):
            cnf=a.out/'sources'/(s['sha256']+'.cnf');cnf.write_text(s['content']);assert B.sha(cnf)==s['sha256']
            for rep in range(3):
                order=ARMS.copy();random.Random(521113+i*31+rep).shuffle(order)
                for arm in order:
                    r=run(arm,s,cnf.resolve(),td,5)
                    r.update({k:s[k] for k in ('sha256','family','level','cohort')});r.update({'rep':rep,'shard':a.shard})
                    if s['cohort']=='known_replay' and rep==0 and (td/'proof.drat').exists():shutil.copyfile(td/'proof.drat',a.out/'proofs'/(arm+'.drat'))
                    log.write(json.dumps(r,sort_keys=True)+'\n');log.flush();B.emit('X52_TRIAL',r)
            B.emit('X52_PROGRESS',{'completed':i+1,'sources':len(cases),'shard':a.shard})
if __name__=='__main__':main()
