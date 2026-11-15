#!/usr/bin/env python3
"""Frozen paired benchmark. Checker startup and execution count in the same cap."""
import argparse, collections, gzip, hashlib, json, os, platform, random, resource, shutil, signal, statistics, subprocess, sys, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
P=json.loads((HERE/'prespec.json').read_text())
OUT=ROOT/'math5_blind_results'
INPUTS=ROOT/'math5_blind_inputs'
BIN={'MATH5':'build/drnas-math5','MATH4':'build/drnas-math4-local','OFF':'build/drnas-math5','Kissat':'build/kissat','CaDiCaL':'build/cadical'}
CHECKERS={'drnas-math5-eo-xor-unit-v1':'research/math5/check_math5.py',
 'drnas-math4-xor-unit-v1':'research/math4/check_xor_units.py',
 'pcmax-clause-hall-v1':'research/pcmax_capacity/check_clause_hall.py',
 'pcmax-capacity-v1':'research/pcmax_capacity/check_capacity.py'}
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,d):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(d,indent=2,sort_keys=True)+'\n')
def emit(tag,d):print(tag+' '+json.dumps(d,sort_keys=True),flush=True)
def pin():
    cpu=min(os.sched_getaffinity(0));os.sched_setaffinity(0,{cpu});assert len(os.sched_getaffinity(0))==1
    return cpu
def model_check(cnf,log):
    values={}
    for line in log.read_text().splitlines():
        if not line.startswith('v '):continue
        for word in line[2:].split():
            lit=int(word)
            if not lit:continue
            if abs(lit) in values and values[abs(lit)]!=(lit>0):return False
            values[abs(lit)]=lit>0
    n=m=None;count=0;pending=False;satisfied=False
    with cnf.open() as f:
        for line in f:
            xs=line.split()
            if not xs or xs[0]=='c':continue
            if xs[0]=='p':
                if n is not None or len(xs)!=4 or xs[1]!='cnf':return False
                n,m=map(int,xs[2:])
                if any(v>n for v in values):return False
                continue
            if n is None:return False
            for token in xs:
                v=int(token)
                if abs(v)>n:return False
                if v:pending=True;satisfied=satisfied or (abs(v) in values and values[abs(v)]==(v>0))
                else:
                    if not satisfied:return False
                    count+=1;pending=False;satisfied=False
    return n is not None and not pending and count==m
def run(cmd,folder,limit):
    folder.mkdir(parents=True,exist_ok=False)
    def limits():
        resource.setrlimit(resource.RLIMIT_FSIZE,(P['proof_limit_bytes'],)*2)
        resource.setrlimit(resource.RLIMIT_AS,(P['memory_limit_bytes'],)*2)
    start=time.perf_counter();expired=False
    with (folder/'stdout.txt').open('w') as out,(folder/'stderr.txt').open('w') as err:
        proc=subprocess.Popen(cmd,stdout=out,stderr=err,start_new_session=True,preexec_fn=limits)
        while True:
            pid,status,usage=os.wait4(proc.pid,os.WNOHANG)
            if pid:break
            if time.perf_counter()-start>=limit:
                expired=True
                try:os.killpg(proc.pid,signal.SIGKILL)
                except ProcessLookupError:pass
                _,status,usage=os.wait4(proc.pid,0);break
            time.sleep(.001)
        proc.returncode=os.waitstatus_to_exitcode(status)
    return dict(rc=proc.returncode,expired=expired,wall_s=time.perf_counter()-start,
        cpu_s=usage.ru_utime+usage.ru_stime,maxrss_kib=usage.ru_maxrss,
        stdout=(folder/'stdout.txt').read_text(errors='replace'),stderr=(folder/'stderr.txt').read_text(errors='replace'))
def command(arm,cnf,proof,cert,cap):
    if arm in ('MATH5','MATH4','OFF'):
        cmd=[str(ROOT/BIN[arm]),str(cnf),'--mode','core','--time',str(cap),'--x5-no-minimize','--x5-no-retain','--cf5-policy','B2L_32','--proof',str(proof)]
        if arm!='OFF':cmd+=['--'+arm.lower(),'--pcmax-budget-ms',str(P['guard_budget_ms']),'--pcmax-certificate',str(cert)]
        return cmd
    if arm=='Kissat':return [str(ROOT/BIN[arm]),str(cnf),str(proof)]
    if arm=='CaDiCaL':return [str(ROOT/BIN[arm]),'-q','--no-binary',str(cnf),str(proof)]
    raise ValueError(arm)
def trial(source,arm,rep,folder,cap=None):
    cap=P['cap_s'] if cap is None else cap
    cnf=ROOT/source['path'];assert sha(cnf)==source['sha256']
    folder.mkdir(parents=True,exist_ok=False);proof=folder/'proof.drat';cert=folder/'structural.json'
    start=time.perf_counter();result=run(command(arm,cnf,proof,cert,cap),folder/'solver',cap)
    status='TIMEOUT' if result['expired'] else 'UNKNOWN';verified=False;kind=None;check=None
    check_start=time.perf_counter();remaining=cap-(check_start-start)
    if not result['expired'] and result['rc'] in (10,20):
        answer='SATISFIABLE' if result['rc']==10 else 'UNSATISFIABLE'
        if ('s '+answer) not in result['stdout'].splitlines():status='INVALID_STATUS_CONTRACT'
        elif remaining<=0:status='CHECK_BUDGET_EXHAUSTED'
        else:
            checker=None
            if result['rc']==10:
                kind='MODEL';checker=[sys.executable,str(Path(__file__).resolve()),'model',str(cnf),str(folder/'solver/stdout.txt')]
                if cert.exists():status='INVALID_STALE_CERTIFICATE';checker=None
            elif cert.exists():
                try:
                    fmt=json.loads(cert.read_text()).get('format');checker_path=CHECKERS[fmt]
                    assert arm in ('MATH4','MATH5')
                    kind='STRUCTURAL_'+fmt
                    checker=[sys.executable,str(ROOT/checker_path),str(cnf),str(cert)]
                except (ValueError,KeyError,AssertionError):status='INVALID_CERTIFICATE_FORMAT'
            elif proof.exists() and proof.stat().st_size:
                kind='DRAT';checker=[str(ROOT/'build/drat-trim'),str(cnf),str(proof)]
            else:status='UNSAT_UNVERIFIED'
            remaining=cap-(time.perf_counter()-start)
            if checker and remaining>0:
                check=run(checker,folder/'checker',remaining)
                verified=not check['expired'] and check['rc']==0 and 'VERIFIED' in check['stdout']
                status=('SAT_VERIFIED' if result['rc']==10 else 'UNSAT_VERIFIED') if verified else ('CHECK_TIMEOUT' if check['expired'] else 'INVALID_PROOF_OR_MODEL')
            elif checker:status='CHECK_BUDGET_EXHAUSTED'
    elif not result['expired'] and result['rc'] not in (0,10,20):
        status='RESOURCE_LIMIT' if result['rc'] in (-9,-25,137,153) or 'bad_alloc' in result['stderr'] else 'SOLVER_ERROR'
    elapsed=time.perf_counter()-start;checkwall=time.perf_counter()-check_start if result['rc'] in (10,20) and not result['expired'] else 0
    accepted=verified and elapsed<=cap;strict=accepted and kind in ('MODEL','DRAT')
    telemetry=[]
    for l in result['stdout'].splitlines():
        if l.startswith('c PCMAX_CAPACITY '):
            try:telemetry.append(json.loads(l[len('c PCMAX_CAPACITY '):]))
            except ValueError:pass
    row=dict(id=source['id'],family=source['family'],file_id=source.get('file_id'),source_sha256=source['sha256'],arm=arm,rep=rep,
        status=status,verified=verified,accepted=accepted,strict_accepted=strict,certificate_kind=kind,
        solver_s=result['wall_s'],checker_s=checkwall,e2e_s=elapsed,solver_cpu_s=result['cpu_s'],maxrss_kib=result['maxrss_kib'],
        checker_cpu_s=check['cpu_s'] if check else None,checker_maxrss_kib=check['maxrss_kib'] if check else None,
        PAR2_s=elapsed if accepted else 2*cap,PAR2_strict_s=elapsed if strict else 2*cap,
        proof_bytes=proof.stat().st_size if proof.exists() else 0,guard=telemetry[-1] if telemetry else None,
        critical=status.startswith('INVALID') or status=='SOLVER_ERROR',command=command(arm,cnf,proof,cert,cap))
    if verified and ((result['rc']==10 and source.get('catalog_label')=='unsat') or (result['rc']==20 and source.get('catalog_label')=='sat')):
        row['catalog_disagreement']=True;row['critical']=True
    # Retain all complete verified proofs losslessly. Remove only incomplete trial scratch.
    if proof.exists():
        if verified:
            row['proof_sha256']=sha(proof)
            with proof.open('rb') as f,gzip.open(str(proof)+'.gz','wb',compresslevel=1) as g:shutil.copyfileobj(f,g)
        proof.unlink()
    save(folder/'result.json',row);emit('BLIND_TRIAL',row);return row
def prepare():
    cpu=pin();m=json.loads((INPUTS/'manifest.json').read_text())
    assert m['prespec_sha256']==sha(HERE/'prespec.json')
    for path,h in P['source_hashes'].items():assert sha(ROOT/path)==h,('frozen_source_changed',path)
    for path,h in P['reference_hashes'].items():assert sha(ROOT/path)==h,('frozen_reference_changed',path)
    for s in m['sources']:assert sha(ROOT/s['path'])==s['sha256']
    files=set(BIN.values())|{'build/drat-trim'}|set(CHECKERS.values())|{'research/math5_blind/benchmark.py','research/math5_blind/freeze.py','research/math5_blind/prespec.json'}
    protocol=dict(prespec=P,manifest_sha256=sha(INPUTS/'manifest.json'),file_sha256={p:sha(ROOT/p) for p in sorted(files)},
        cpu=cpu,platform=platform.platform(),expected_trials=len(m['sources'])*P['repetitions']*len(P['arms']),
        repetitions_not_independent=True,automatic_promotion=False)
    save(OUT/'protocol.json',protocol);emit('BLIND_READY',dict(sources=len(m['sources']),trials=protocol['expected_trials'],protocol_sha256=sha(OUT/'protocol.json')))
def shard(index):
    pin();assert 0<=index<P['shards'];protocol=json.loads((OUT/'protocol.json').read_text())
    assert protocol['manifest_sha256']==sha(INPUTS/'manifest.json')
    for p,h in protocol['file_sha256'].items():assert sha(ROOT/p)==h
    sources=json.loads((INPUTS/'manifest.json').read_text())['sources'];dest=OUT/f'shard-{index}';dest.mkdir(exist_ok=False)
    with (dest/'trials.jsonl').open('w') as f:
        for s in sources:
            if s['id']%P['shards']!=index:continue
            order=list(P['arms']);random.Random(P['selection_seed']+str(s['id'])).shuffle(order)
            for rep in range(P['repetitions']):
                shift=rep%len(order)
                for arm in order[shift:]+order[:shift]:
                    row=trial(s,arm,rep,dest/f'{s["id"]:02d}-r{rep}-{arm}')
                    f.write(json.dumps(row,sort_keys=True)+'\n');f.flush()
    emit('BLIND_SHARD_COMPLETE',dict(shard=index))
def report():
    sources=json.loads((INPUTS/'manifest.json').read_text())['sources'];rows=[]
    for f in OUT.glob('shard-*/trials.jsonl'):rows.extend(json.loads(l) for l in f.read_text().splitlines())
    actual=[(r['id'],r['rep'],r['arm']) for r in rows]
    expected={(s['id'],rep,a) for s in sources for rep in range(P['repetitions']) for a in P['arms']}
    assert len(actual)==len(set(actual)) and set(actual)==expected,('incomplete_matrix',len(actual),len(expected))
    critical=[r for r in rows if r['critical']]
    pairs=[]
    for s in sources:
        rr=[r for r in rows if r['id']==s['id']];assert all(r['source_sha256']==s['sha256'] for r in rr)
        answers={r['status'] for r in rr if r['verified']}
        if len(answers)>1:critical.extend(rr)
        pairs.append(dict(id=s['id'],family=s['family'],means={a:sum(r['PAR2_s'] for r in rr if r['arm']==a)/P['repetitions'] for a in P['arms']}))
    totals={a:dict(trials=sum(r['arm']==a for r in rows),solved_sources=len({r['id'] for r in rows if r['arm']==a and r['accepted']}),
        accepted=sum(r['accepted'] for r in rows if r['arm']==a),structural=sum(r['accepted'] and str(r['certificate_kind']).startswith('STRUCTURAL') for r in rows if r['arm']==a),
        PAR2_s=sum(r['PAR2_s'] for r in rows if r['arm']==a),PAR2_strict_s=sum(r['PAR2_strict_s'] for r in rows if r['arm']==a),
        statuses=dict(collections.Counter(r['status'] for r in rows if r['arm']==a))) for a in P['arms']}
    reference=min(('Kissat','CaDiCaL'),key=lambda a:totals[a]['PAR2_s'])
    gain=1-totals['MATH5']['PAR2_s']/totals[reference]['PAR2_s']
    rng=random.Random(20261115);boots=[]
    for _ in range(5000):
        pp=[rng.choice(pairs) for _ in pairs];boots.append(1-sum(p['means']['MATH5'] for p in pp)/sum(p['means'][reference] for p in pp))
    boots.sort()
    no_proof=[r for r in rows if r['arm']=='MATH5' and r['guard'] and not r['guard'].get('verified',False)]
    overhead=[]
    for s in sources:
        m=[r for r in rows if r['id']==s['id'] and r['arm']=='MATH5']
        off=[r for r in rows if r['id']==s['id'] and r['arm']=='OFF']
        if all(r['accepted'] for r in m+off) and all(r['guard'] and not r['guard'].get('verified',False) for r in m):
            overhead.append(dict(id=s['id'],solver_time_ratio=statistics.median(r['solver_s'] for r in m)/statistics.median(r['solver_s'] for r in off)))
    summary=dict(status='COMPLETE' if not critical else 'COMPLETE_WITH_CRITICAL_FAILURE',sources=len(sources),trials=len(rows),totals=totals,
        best_reference=reference,primary_relative_improvement=gain,source_cluster_bootstrap_95=[boots[125],boots[4874]],
        success_threshold_met=not critical and gain>=.10,critical_trials=len(critical),pairs=pairs,
        guard_no_proof_trials=len(no_proof),guard_no_proof_module_total_s=sum(r['guard'].get('module_elapsed_s',0) for r in no_proof),
        solved_no_proof_overhead=overhead,median_solved_no_proof_ratio=statistics.median(r['solver_time_ratio'] for r in overhead) if overhead else None,
        automatic_promotion=False,blindness=P['blindness'])
    save(OUT/'summary.json',summary);(OUT/'trials.jsonl').write_text(''.join(json.dumps(r,sort_keys=True)+'\n' for r in rows))
    lines=['# MATH5 slijepi prospektivni test','',f'{len(sources)} originala, {P["repetitions"]} ponavljanja, {P["cap_s"]} s ukupno sa zasebnim provjerivačem, jedna logička jezgra po solveru.','',
        '| Solver | Riješeni izvori | Prihvaćena ponavljanja | Strukturna | PAR2 ukupno (s) | Strogi MODEL/DRAT PAR2 (s) |','|---|---:|---:|---:|---:|---:|']
    for a,t in totals.items():lines.append(f'| {a} | {t["solved_sources"]} | {t["accepted"]} | {t["structural"]} | {t["PAR2_s"]:.6f} | {t["PAR2_strict_s"]:.6f} |')
    lines+=['',f'MATH5 relativno poboljšanje prema {reference}: {100*gain:.3f}%; interval ponovnog uzorkovanja po izvorima: {[round(100*x,3) for x in summary["source_cluster_bootstrap_95"]]}.',
        f'Kritična odstupanja: {len(critical)}. Prag 10% zadovoljen: {summary["success_threshold_met"]}.','',P['blindness'],
        'Strukturni certifikati nisu DRAT/LRAT. Ponavljanja nisu neovisni izvori. Ovo nije službeni poredak natjecanja; nema automatske promocije.']
    (OUT/'README.md').write_text('\n'.join(lines)+'\n');emit('BLIND_FINAL',summary)
if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='model':
        try:ok=model_check(Path(sys.argv[2]),Path(sys.argv[3]))
        except (ValueError,OSError):ok=False
        print('MODEL VERIFIED' if ok else 'INVALID MODEL');raise SystemExit(0 if ok else 1)
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','shard','report']);p.add_argument('--index',type=int);a=p.parse_args()
    if a.action=='prepare':prepare()
    elif a.action=='shard':shard(a.index)
    else:report()
