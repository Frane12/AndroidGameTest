#!/usr/bin/env python3
"""MATH4 vs HALL3/CF7/Kissat/CaDiCaL, SHA-pinned Main Track proofs.

All scoring requires independent SAT model, DRAT or original-clause proof.
A proof checker runs separately and its time counts in primary E2E PAR2.
"""
import argparse, collections, hashlib, json, lzma, os, random, resource
import signal, subprocess, sys, time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'research'))
from drnas_x55_cpu_real36 import parse_cnf, check_sat
sys.path.insert(0,str(ROOT/'research/hall3'))
from collect import download, MAX_ARCHIVE, MAX_RAW
CAP=12.0
REPS=2
SHARDS=6
ARMS=('CF7_OFF','HALL3_ON','MATH4_ON','Kissat','CaDiCaL')
BIN={'CF7_OFF':'build/drnas-cf7-frozen','HALL3_ON':'build/drnas-math4',
     'MATH4_ON':'build/drnas-math4','Kissat':'build/kissat','CaDiCaL':'build/cadical'}
OUT=ROOT/'math4_results'

def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def save(path,obj):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,indent=2,sort_keys=True)+'\n')
def emit(tag,obj): print(tag+' '+json.dumps(obj,sort_keys=True),flush=True)
def pin():
    cpu=min(os.sched_getaffinity(0));os.sched_setaffinity(0,{cpu})
    assert len(os.sched_getaffinity(0))==1
    return cpu
def manifest(): return json.loads((ROOT/'research/hall3/manifest.json').read_text())

def prepare():
    cpu=pin();m=manifest();assert len(m['sources'])==24
    for s in m['sources']:
        p=ROOT/s['path'];p.parent.mkdir(parents=True,exist_ok=True)
        if not p.exists():
            archive=download(s['url'],MAX_ARCHIVE)
            assert hashlib.sha256(archive).hexdigest()==s['archive_sha256'], 'archive drift'
            raw=lzma.decompress(archive,memlimit=256*1024*1024) if archive.startswith(b'\xfd7zXZ\x00') else archive
            assert len(raw)<=MAX_RAW
            p.write_bytes(raw)
        assert sha(p)==s['sha256'], 'original CNF drift'
    names=sorted(set(BIN.values())|{'build/drat-trim','build/drnas-cf7-frozen'})
    protocol=dict(name='MATH4-CF7-ORIGINAL24-V1',cap_s=CAP,repetitions=REPS,
        shards=SHARDS,arms=ARMS,guard_budget_ms=750,source_count=24,
        expected_trials=24*REPS*len(ARMS),one_logical_cpu=True,prepare_cpu=cpu,
        binary_sha256={n:sha(ROOT/n) for n in names},
        manifest_sha256=sha(ROOT/'research/hall3/manifest.json'),
        verifier_sha256={n:sha(ROOT/n) for n in ['research/pcmax_capacity/check_clause_hall.py',
            'research/pcmax_capacity/check_capacity.py','research/math4/check_xor_units.py',
             'research/drnas_x55_cpu_real36.py']},
        repetitions_are_not_independent_sources=True,proof_limit_bytes=256*1024*1024,
        strict_score='SAT model or DRAT only; original-CNF structural-only UNSAT gets 2*cap',
        structural_score='SAT model, DRAT or independent original-CNF Hall/BDD certificate',
        timing='solver wall includes startup/parsing/guard/CDCL; verification separately and E2E score',
        selection_frozen_before_results=False,training=False,automatic_promotion=False)
    save(OUT/'protocol.json',protocol);emit('HALL3_READY',protocol)

def run(cmd,folder,limit):
    folder.mkdir(parents=True,exist_ok=True)
    stdout=folder/'stdout.txt';stderr=folder/'stderr.txt'
    def limits():
        resource.setrlimit(resource.RLIMIT_FSIZE,(256*1024*1024,256*1024*1024))
        resource.setrlimit(resource.RLIMIT_AS,(4*1024**3,4*1024**3))
    start=time.perf_counter();expired=False
    with stdout.open('w') as out,stderr.open('w') as err:
        p=subprocess.Popen(cmd,
            stdout=out,stderr=err,start_new_session=True,preexec_fn=limits)
        while True:
            pid,status,usage=os.wait4(p.pid,os.WNOHANG)
            if pid:
                p.returncode=os.waitstatus_to_exitcode(status)
                break
            if time.perf_counter()-start>=limit:
                expired=True
                try:os.killpg(p.pid,signal.SIGKILL)
                except ProcessLookupError:pass
                _,status,usage=os.wait4(p.pid,0)
                p.returncode=os.waitstatus_to_exitcode(status)
                break
            time.sleep(0.002)
    elapsed=time.perf_counter()-start
    cpu_s=usage.ru_utime+usage.ru_stime;rss=usage.ru_maxrss
    return dict(rc=p.returncode,expired=expired,elapsed=elapsed,cpu_s=cpu_s,
        maxrss_kib=rss,stdout=stdout.read_text(errors='replace'),stderr=stderr.read_text(errors='replace'))

def command(arm,cnf,proof,cert,cap=CAP):
    if arm in ('CF7_OFF','HALL3_ON','MATH4_ON'):
        cmd=[str(ROOT/BIN[arm]),str(cnf),'--mode','core','--time',str(cap),
            '--x5-no-minimize','--x5-no-retain','--cf5-policy','B2L_32','--proof',str(proof)]
        if arm=='HALL3_ON':cmd+=['--hall3','--pcmax-budget-ms','750','--pcmax-certificate',str(cert)]
        if arm=='MATH4_ON':cmd+=['--math4','--pcmax-budget-ms','750','--pcmax-certificate',str(cert)]
        return cmd
    if arm=='Kissat':return [str(ROOT/BIN[arm]),str(cnf),str(proof)]
    if arm=='CaDiCaL':return [str(ROOT/BIN[arm]),'-q','--no-binary',str(cnf),str(proof)]
    raise ValueError(arm)

def trial(source,arm,rep,folder,cap=CAP):
    cnf=ROOT/source['path'];assert sha(cnf)==source['sha256']
    folder.mkdir(parents=True,exist_ok=False)
    proof=folder/'proof.drat';cert=folder/'structural.json'
    result=run(command(arm,cnf,proof,cert,cap),folder/'solver',cap)
    status='TIMEOUT' if result['expired'] else 'UNKNOWN'
    verified=False;kind=None;check_s=0.0;check_rss=None
    check_start=time.perf_counter()
    if not result['expired'] and result['rc']==10:
        nv,clauses=parse_cnf(cnf.read_bytes())
        verified=check_sat(result['stdout'],clauses,nv)
        status='SAT_VERIFIED' if verified else 'INVALID_SAT'
        kind='MODEL'
        assert not cert.exists(), 'SAT with stale structural certificate'
    elif not result['expired'] and result['rc']==20:
        assert 's UNSATISFIABLE' in result['stdout'], 'wrong exit/status contract'
        if cert.exists():
            assert arm in ('HALL3_ON','MATH4_ON'), 'unexpected structural proof'
            data=json.loads(cert.read_text());fmt=data.get('format')
            if fmt=='pcmax-clause-hall-v1': checker='check_clause_hall.py';kind='STRUCTURAL_HALL'
            elif fmt=='pcmax-capacity-v1': checker='check_capacity.py';kind='STRUCTURAL_BDD'
            elif fmt=='drnas-math4-xor-unit-v1':checker='../math4/check_xor_units.py';kind='STRUCTURAL_GF2_UNIT'
            else: raise AssertionError('unsupported certificate format '+str(fmt))
            ck=run([sys.executable,str(ROOT/'research/pcmax_capacity'/checker),str(cnf),str(cert)],folder/'checker',90)
            verified=ck['rc']==0 and not ck['expired'] and 'VERIFIED' in ck['stdout']
        elif proof.exists() and proof.stat().st_size:
            kind='DRAT'
            ck=run([str(ROOT/'build/drat-trim'),str(cnf),str(proof)],folder/'checker',90)
            verified=ck['rc']==0 and not ck['expired'] and 's VERIFIED' in ck['stdout']
        else:ck=None
        if 'ck' in locals() and ck:
            check_rss=ck['maxrss_kib']
            if ck['expired']:status='UNSAT_CHECK_TIMEOUT'
            elif not verified:status='INVALID_UNSAT_PROOF'
        if verified:status='UNSAT_VERIFIED'
        elif status not in ('UNSAT_CHECK_TIMEOUT','INVALID_UNSAT_PROOF'):status='UNSAT_UNVERIFIED'
    elif result['rc'] not in (0,10,20) and not result['expired']:
        if result['rc'] in (137,153,-9,-25) or 'bad_alloc' in result['stderr']:
            status='RESOURCE_LIMIT'
        else:status='SOLVER_ERROR'
    check_s=time.perf_counter()-check_start if result['rc'] in (10,20) and not result['expired'] else 0.0
    certified_e2e=result['elapsed']+check_s
    accepted=verified and certified_e2e<=cap
    strict=accepted and kind in ('MODEL','DRAT')
    telemetry=[json.loads(l[len('c PCMAX_CAPACITY '):]) for l in result['stdout'].splitlines()
        if l.startswith('c PCMAX_CAPACITY ')]
    row=dict(id=source['id'],family=source['family'],source_sha256=source['sha256'],
        arm=arm,rep=rep,status=status,certificate_kind=kind,verified=verified,accepted=accepted,
        strict_accepted=strict,solve_wall_s=round(result['elapsed'],6),
        check_wall_s=round(check_s,6),certified_e2e_s=round(certified_e2e,6),
        cpu_s=result['cpu_s'],maxrss_kib=result['maxrss_kib'],checker_maxrss_kib=check_rss,
        PAR2_verified_s=round(certified_e2e if accepted else 2*cap,6),
        PAR2_strict_drat_s=round(certified_e2e if strict else 2*cap,6),
        PAR2_certified_e2e_s=round(certified_e2e if accepted and certified_e2e<=cap else 2*cap,6),
        proof_bytes=proof.stat().st_size if proof.exists() else 0,
        guard=telemetry[-1] if telemetry else None)
    if verified and status=='UNSAT_VERIFIED' and source['catalog_label']=='sat':
        raise AssertionError(('CRITICAL_CATALOG_SAT_VS_CERTIFIED_UNSAT',source['id'],arm))
    save(folder/'result.json',row);emit('MATH4_TRIAL',row)
    if status in ('INVALID_SAT','INVALID_UNSAT_PROOF','SOLVER_ERROR'):
        raise AssertionError((status,source['id'],arm,result['stderr'][-500:]))
    # Incomplete/timeout proofs do not establish anything. Keep all accepted evidence.
    if proof.exists() and not verified:proof.unlink()
    return row

def shard(index):
    pin();assert 0<=index<SHARDS
    protocol=json.loads((OUT/'protocol.json').read_text())
    assert protocol['manifest_sha256']==sha(ROOT/'research/hall3/manifest.json')
    for p,h in protocol['binary_sha256'].items():assert sha(ROOT/p)==h
    for p,h in protocol['verifier_sha256'].items():assert sha(ROOT/p)==h
    sources=[s for s in manifest()['sources'] if s['id']%SHARDS==index]
    dest=OUT/f'shard-{index}';dest.mkdir(exist_ok=False)
    results=[]
    with (dest/'trials.jsonl').open('w') as log:
        for s in sources:
            for rep in range(REPS):
                arms=list(ARMS);random.Random(2026111400+s['id']*31+rep).shuffle(arms)
                for arm in arms:
                    row=trial(s,arm,rep,dest/f'{s["id"]:02d}-r{rep}-{arm}')
                    results.append(row);log.write(json.dumps(row,sort_keys=True)+'\n');log.flush()
            answers={r['status'] for r in results if r['id']==s['id'] and r['verified']}
            assert len(answers)<=1, ('contradictory_verified_answers',s['id'])
    save(dest/'meta.json',dict(index=index,trials=len(results),source_ids=[s['id'] for s in sources]))
    emit('MATH4_SHARD_PASS',dict(index=index,trials=len(results)))

def report():
    rows=[]
    for f in OUT.glob('shard-*/trials.jsonl'):
        rows.extend(json.loads(l) for l in f.read_text().splitlines())
    expected={(s['id'],r,a) for s in manifest()['sources'] for r in range(REPS) for a in ARMS}
    actual=[(r['id'],r['rep'],r['arm']) for r in rows]
    assert len(actual)==len(set(actual)) and set(actual)==expected, ('incomplete_matrix',len(actual),len(expected))
    for s in manifest()['sources']:
        rr=[r for r in rows if r['id']==s['id']]
        assert all(r['source_sha256']==s['sha256'] for r in rr)
        assert len({r['status'] for r in rr if r['verified']})<=1
    totals=[]
    for arm in ARMS:
        rr=[r for r in rows if r['arm']==arm]
        totals.append(dict(arm=arm,trials=len(rr),accepted=sum(r['accepted'] for r in rr),
            strict_accepted=sum(r['strict_accepted'] for r in rr),
            solved_sources=len({r['id'] for r in rr if r['accepted']}),
            structural=sum(r['accepted'] and str(r['certificate_kind']).startswith('STRUCTURAL') for r in rr),
            PAR2_verified_s=sum(r['PAR2_verified_s'] for r in rr),
            PAR2_strict_drat_s=sum(r['PAR2_strict_drat_s'] for r in rr),
            PAR2_certified_e2e_s=sum(r['PAR2_certified_e2e_s'] for r in rr)))
    pairs=[]
    for s in manifest()['sources']:
        rr=[r for r in rows if r['id']==s['id']]
        sums={a:sum(r['PAR2_verified_s'] for r in rr if r['arm']==a)/REPS for a in ARMS}
        pairs.append(dict(id=s['id'],family=s['family'],PAR2_mean=sums,
            guard_delta_s=sums['HALL3_ON']-sums['MATH4_ON']))
    rng=random.Random(20261114);deltas=[p['guard_delta_s'] for p in pairs]
    boot=sorted(sum(rng.choice(deltas) for _ in deltas)/len(deltas) for _ in range(5000))
    summary=dict(status='COMPLETE',sources=24,trials=len(rows),totals=totals,
        paired_mean_PAR2_improvement_s=sum(deltas)/len(deltas),
        source_cluster_bootstrap_95_s=[boot[125],boot[4874]],pairs=pairs,
        structural_is_not_drat=True,automatic_promotion=False)
    save(OUT/'summary.json',summary)
    lines=['# MATH4 + HALL3/CF7: SAT Competition 2026 Main subset','',
        '24 original CNFs, 12 families, 2 repeats, 12 s, one logical CPU per sequential trial.',
        'SAT models and DRAT proofs are independently checked. Structural certificates are reported separately.',
        '', '| Arm | Solved sources | Accepted trials | Structural | Verified PAR2 sum | Strict MODEL/DRAT PAR2 |',
        '|---|---:|---:|---:|---:|---:|']
    for t in totals:lines.append(f'| {t["arm"]} | {t["solved_sources"]} | {t["accepted"]} | {t["structural"]} | {t["PAR2_verified_s"]:.3f} | {t["PAR2_strict_drat_s"]:.3f} |')
    lines+=['',f'Paired mean HALL3_ON minus MATH4_ON: {summary["paired_mean_PAR2_improvement_s"]:.6f} s per source; source-cluster 95% interval {summary["source_cluster_bootstrap_95_s"]}.',
        '', 'This is a preselected 24-CNF retrospective subset, not an official competition ranking or independent blinded holdout. No automatic promotion.']
    (OUT/'README.md').write_text('\n'.join(lines)+'\n')
    emit('MATH4_FINAL',summary)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','shard','report']);p.add_argument('--index',type=int)
    a=p.parse_args()
    if a.action=='prepare':prepare()
    elif a.action=='shard':shard(a.index)
    else:report()
