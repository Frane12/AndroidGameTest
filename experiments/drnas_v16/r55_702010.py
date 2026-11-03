#!/usr/bin/env python3
"""R55 70/20/10 prospective pilot: priorities, NOT runtime mixture weights.
70% structural R49-certified pivot gate, 20% bounded certified GF(2),
10% passive runtime risk telemetry. No internal Kissat conflicts claimed.
Reuse R53's proven freeze/paired audit; exclude R53 registry itself.
"""
import argparse, csv, hashlib, io, json, os, random, resource, subprocess, sys
import tempfile, time
from pathlib import Path
import r53_fifty_fresh_triple as core
import r49_pivot_coherence_gate as r49
import r32t_certified_short_xor as xor

PROTO='DRNAS-R55-702010-FRESH-20261103-v1'
SALT='DRNAS-R55-70-20-10-FRESH-20261103'
MODES=('kissat_pinned','drnas_r49_gate','r55_struct','r55_xor',
       'r55_guarded','cadical_3_0_1')
CAP=30.0; XOR_LIMIT=2*1024*1024; FAST_SKIP=128*1024
REPS=2; SHARDS=4
old_trial=core.prior.trial
core.PROTO=PROTO;core.SALT=SALT;core.TARGET=8
core.REPS=REPS;core.SHARDS=SHARDS;core.CAP=CAP;core.MAX_TRIES=200
core.MODES=MODES;core.prior.CAP=CAP

def check(ok,msg):
    if not ok: raise RuntimeError('R55_FAIL_CLOSED '+str(msg))

def sha(p): return core.digest(p)

def limit(): resource.setrlimit(resource.RLIMIT_AS,(3*1024**3,3*1024**3))

def xor_certified(source,tmp,start):
    if Path(source).stat().st_size>XOR_LIMIT:
        return None,0,'xor_size_abstain'
    target=Path(tmp)/'xor.cnf';cert=Path(tmp)/'cert.json'
    args=['--original',str(source),'--augmented',str(target),'--certificate',str(cert)]
    path=str(Path(xor.__file__).resolve())
    for command in ('build','audit'):
        remaining=3.0-(time.monotonic()-start)
        if remaining<=0:return None,0,'xor_budget_abstain'
        try:
            p=subprocess.run([sys.executable,path,command]+args,timeout=remaining,
                             text=True,capture_output=True)
        except subprocess.TimeoutExpired:
            return None,0,'xor_timeout_abstain'
        check(p.returncode==0,'XOR certificate error: '+p.stderr[-240:])
    c=json.loads(cert.read_text())
    check(c['sha256_original']==sha(source) and c['sha256_augmented']==sha(target),
          'XOR original or rewritten SHA mismatch')
    return (target if c['added_clauses'] else None),c['added_clauses'],'xor_verified'

def trial(original,mode,binaries):
    if mode in ('kissat_pinned','drnas_r49_gate','cadical_3_0_1'):
        return old_trial(original,mode,binaries)
    start=time.monotonic();candidate=original;added=0;gate=False;xe=0
    choice='abstain';derived=0;dominance=0.;motifs=0
    with tempfile.TemporaryDirectory(prefix='r55-') as tmp:
        size=Path(original).stat().st_size
        if mode in ('r55_struct','r55_guarded') and size>=FAST_SKIP:
            plan=r49.compute_plan(original)
            derived=plan['derived'];dominance=plan['dominance']
            motifs=plan['trace'].get('motifs',0)
            if derived>=24 and dominance>=.80:
                clauses=plan['single_pivot_16'][:16]
                check(all(c in plan['clauses'] for c in clauses),'uncertified clause')
                if clauses:
                    candidate=Path(tmp)/'structure.cnf'
                    written=r49.r48.safe_rewrite(original,candidate,clauses)
                    check(written['added']==len(clauses),'rewrite failed')
                    added=len(clauses);gate=True;choice='certified_pivot16'
            if mode=='r55_guarded' and not gate and motifs:
                p,n,choice=xor_certified(original,tmp,start)
                if p is not None:candidate=p;added=n;xe=n
        elif mode=='r55_xor':
            p,n,choice=xor_certified(original,tmp,start)
            if p is not None:candidate=p;added=n;xe=n
        elif mode in ('r55_struct','r55_guarded'):
            choice='tiny_original_fast_abstain'
        prep=time.monotonic()-start;answer='TIMEOUT'
        if prep<CAP:
            try:
                p=subprocess.run([str(binaries['kissat_pinned']),str(candidate)],
                   timeout=CAP-prep,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                   text=True,errors='replace',preexec_fn=limit)
                check(p.returncode in (10,20),'Kissat returned '+str(p.returncode)+': '+p.stderr[-160:])
                answer='SAT' if p.returncode==10 else 'UNSAT'
                if answer=='SAT':core.r32p.verify_sat_witness(original,p.stdout)
            except subprocess.TimeoutExpired:pass
        elapsed=time.monotonic()-start
    if elapsed>=CAP:answer='TIMEOUT'
    wall=min(elapsed,CAP)
    return dict(mode=mode,answer=answer,wall_s=round(wall,6),
        par2_s=round(wall if answer!='TIMEOUT' else 2*CAP,6),
        prep_s=round(prep,6),added_clauses=added,r49_gate=gate,
        xor_equations=xe,derived=derived,dominance=dominance,motifs=motifs,
        decision=choice,early_conflict_signal='unobserved_passive_only')

core.prior.trial=trial

def freeze(a):
    # Deterministic interleaving among four official score strata; NEVER rank
    # by DRNAS times. Prior manifests include R53, R52 and R32u.
    raw=core.prior.fetch_bytes(core.prior.SCORES).decode()
    records=list(csv.DictReader(io.StringIO(raw)))
    pools={k:[] for k in ('sat_fast','unsat_fast','sat_mid','unsat_mid')}
    for x in records:
        if x.get('solverid')!='biere_cadical3[main]' or x.get('status') not in ('sat-verified','unsat-verified'):continue
        seconds=float(x['runtime']);band='fast' if seconds<10 else ('mid' if seconds<80 else None)
        if band is not None:
            name=('sat' if x['status']=='sat-verified' else 'unsat')+'_'+band
            pools[name].append(x['instanceid'])
    order=[]
    for k in pools:
        pools[k].sort(key=lambda g:hashlib.sha256((SALT+'|'+g).encode()).hexdigest())
    for i in range(max(map(len,pools.values()))):
        for k in pools:
            if i<len(pools[k]):order.append(pools[k][i])
    ranks={g:i for i,g in enumerate(order)}
    core.stamp=lambda s:(f'{ranks[s]:07d}' if s in ranks
                         else '9'+hashlib.sha256((SALT+'|'+s).encode()).hexdigest())
    core.freeze(a)
    path=Path(a.out)/'manifest.json';m=json.loads(path.read_text())
    m['selection']='interleaved official CaDiCaL SAT/UNSAT fast/mid strata, salted by ID; DRNAS outcomes unused'
    m['score_stratified']=True
    m['research_allocations']={'structural':70,'certified_xor':20,'passive_telemetry':10}
    m['allocation_is_runtime_weight']=False
    path.write_text(json.dumps(m,indent=2)+'\n')
    print('R55_FROZEN_NEW_REGISTERED_SOURCES_PASS',len(m['cases']))

def audit(a):
    # R55 paired artifacts are named r55-shard-N, not r53-shard-N.
    # Reuse the frozen R53 fail-closed SHA/PAR2 validator with its explicit prefix.
    a.shard_prefix='r55'
    core.audit(a)
    p=Path(a.out);data=json.loads(p.read_text())
    ids=list(data['per_instance']);rng=random.Random(20261103)
    ci={}
    for mode in ('drnas_r49_gate','r55_struct','r55_xor','r55_guarded'):
        samples=[]
        for _ in range(2000):
            draw=[ids[rng.randrange(len(ids))] for _ in ids]
            base=sum(data['per_instance'][g]['kissat_pinned']['sum_par2'] for g in draw)
            alt=sum(data['per_instance'][g][mode]['sum_par2'] for g in draw)
            samples.append(100*(1-alt/base))
        samples.sort();ci[mode]=[round(samples[49],3),round(samples[1950],3)]
    data['r55_ci95_pct_vs_kissat']=ci
    data['caveat']='R55 official-score-stratified pilot, not competition ranking; early CDCL conflicts NOT measured'
    p.write_text(json.dumps(data,indent=2)+'\n')
    # The shared R53 validator generates a legacy R53 header; label this R55 report accurately.
    report=Path(a.markdown)
    lines=report.read_text().splitlines()
    check(len(lines)>3,'missing core audit markdown')
    lines[0]='# DRNAS R55 70/20/10 prospective pilot — 8 registered-new SATComp2026 formulas'
    lines[1]='8 original 2026 CNFs, 2 randomized paired repeats, 6 solvers/methods, 30s inclusive cap (60s PAR-2 timeout).'
    lines[2]='Official CaDiCaL-score-stratified selection; not an official competition or global unseen guarantee.'
    report.write_text('\n'.join(lines)+'\n')
    with open(a.markdown,'a') as f:
        f.write('\nR55 70/20/10 allocation is RESEARCH PRIORITY, not runtime weights.\n')
        f.write('R55 R49/structural/XOR/guarded 95% paired instance-bootstrap CIs: '+json.dumps(ci)+'\n')
        f.write('Early CDCL conflicts not instrumented (10% passive work only).\n')
    print('R55_FINAL_AUDIT_PASS',json.dumps(data['summary'],sort_keys=True))

def selftest():
    r49.selftest()
    with tempfile.TemporaryDirectory() as t:
        source=Path(t)/'t.cnf';source.write_text('p cnf 3 2\n1 2 0\n-1 3 0\n')
        p=r49.compute_plan(source)
        check(p['derived']>0 and p['gate'] is False,'R49 toy guard')
        dst=Path(t)/'xor.cnf';cert=Path(t)/'xor.json'
        xor.build(source,dst,cert);xor.audit(source,dst,cert)
    print('R55_CERTIFIED_SELFTEST_PASS')

def main():
    p=argparse.ArgumentParser();subs=p.add_subparsers(dest='cmd',required=True)
    subs.add_parser('selftest')
    f=subs.add_parser('freeze');f.add_argument('--out',required=True);f.add_argument('--prior',required=True)
    m=subs.add_parser('measure')
    for name in ('sources','shard','out','kissat_pinned','cadical_3_0_1'):m.add_argument('--'+name,required=True)
    a=subs.add_parser('audit')
    for name in ('sources','combined','out','markdown'):a.add_argument('--'+name,required=True)
    args=p.parse_args()
    if args.cmd=='freeze':freeze(args)
    elif args.cmd=='measure':core.measure(args)
    elif args.cmd=='audit':audit(args)
    else:selftest()
if __name__=='__main__':main()
