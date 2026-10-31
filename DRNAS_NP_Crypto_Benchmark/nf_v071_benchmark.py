#!/usr/bin/env python3
"""Paired, zero-shot v0.7 evaluation: CaDiCaL vs NeuroFlow->CaDiCaL.

60 independently sourced CNFs from two publishers (frozen policy never
retuned on them), plus 36 NEW *separately labelled constructed* controls.
3 matched repetitions in rotating order. Total wall time includes:
Python parsing, NeuroFlow gates, Horn solver, CDCL subprocess startup and
SAT witness checks. Reference CryptoMiniSat result is independent.
"""
import csv,hashlib,json,random,statistics,subprocess,time
from pathlib import Path
from drnas_np_lab import normalize,read_dimacs,check
from nf_v071_prefix_gate import solve
from nf_v07_cadical_adapter import FROZEN_V062
ROOT=Path(__file__).resolve().parent
EXTERNAL=ROOT/'nf063_external'
OUTPUT=ROOT/'nf071_results'
CTRL=ROOT/'nf071_constructed_controls'
REPEATS=3
TIMEOUT=2.0
ARMS=('base','v07','prefix','force_horn')

def write_csv(path,rows):
    with path.open('w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]))
        writer.writeheader();writer.writerows(rows)

def controls():
    """NEW controls, not real-world evidence; always report separately."""
    CTRL.mkdir(exist_ok=True)
    rows=[]
    for n in (30,60,100):
        for case_kind in ('horn_sat','horn_unsat','near_horn'):
            for i in range(4):
                rng=random.Random(202610311733+int(n*113)+19*i+len(case_kind)*71)
                flips=[bool(rng.getrandbits(1)) for _ in range(n)]
                clauses=[]
                for _ in range(3*n):
                    vs=rng.sample(range(1,n+1),3)
                    head=rng.randrange(4)
                    clauses.append(tuple(v if pos==head else -v for pos,v in enumerate(vs)))
                if case_kind=='horn_unsat':
                    clauses.extend([(1,),(-1,)])
                if case_kind=='near_horn':
                    for _ in range(n//2):
                        a,b,c=rng.sample(range(1,n+1),3)
                        clauses.append((a,b,c))
                clauses=normalize(n,[tuple(-lit if flips[abs(lit)-1] else lit for lit in cl)
                                     for cl in clauses])
                case_id=f'control_{case_kind}_{n}_{i}'
                path=CTRL/(case_id+'.cnf')
                path.write_text('p cnf %d %d\n'%(n,len(clauses))
                    +''.join(' '.join(map(str,cl))+' 0\n' for cl in clauses))
                assert read_dimacs(path)==(n,clauses)
                rows.append(dict(case_id=case_id,family='constructed_'+case_kind,
                    publisher='DRNAS_constructed_controls',n=n,clauses=len(clauses),
                    path=path,source_sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    return rows

def external_cases():
    with (EXTERNAL/'manifest.csv').open(encoding='utf-8') as f:items=list(csv.DictReader(f))
    assert len(items)==60
    cases=[]
    for rec in items:
        if rec['fetch_status']!='READY':
            print('UNPARSEABLE SOURCE',rec['case_id'],rec['detail'],flush=True)
            continue
        path=EXTERNAL/(rec['case_id']+'.cnf')
        n,cs=read_dimacs(path)
        assert n==int(rec['variables']) and len(cs)==int(rec['clauses'])
        assert hashlib.sha256(path.read_bytes()).hexdigest()==rec['canonical_sha256']
        cases.append(dict(case_id=rec['case_id'],family=rec['source_group'],
            publisher=rec['publisher'],n=n,clauses=len(cs),path=path,
            source_sha256=rec['source_sha256']))
    return cases

def cms(path):
    try:
        r=subprocess.run(['cryptominisat5','--verb','0',str(path)],
            capture_output=True,text=True,timeout=8)
        if 's UNSATISFIABLE' in r.stdout:return 'UNSAT'
        if 's SATISFIABLE' in r.stdout:return 'SAT'
        return 'UNKNOWN'
    except subprocess.TimeoutExpired:
        return 'REFERENCE_TIMEOUT'

def main():
    OUTPUT.mkdir(exist_ok=True)
    actual=external_cases()
    manufactured=controls()
    cases=actual+manufactured
    random.Random(202610311734).shuffle(cases)
    print('CORPUS',len(actual),'external +',len(manufactured),'constructed',flush=True)
    print('SOLVER',subprocess.run(['cadical','--version'],capture_output=True,text=True).stdout.strip(),flush=True)
    results=[];source_rows=[]
    for index,c in enumerate(cases):
        path,n=c['path'],c['n']
        status=cms(path)
        source_rows.append(dict(case_id=c['case_id'],family=c['family'],
            publisher=c['publisher'],expected=status,variables=n,
            clauses=c['clauses'],source_sha256=c['source_sha256']))
        for repetition in range(REPEATS):
            start=(index+repetition)%len(ARMS)
            order=ARMS[start:]+ARMS[:start]
            for arm in order:
                r=solve(path,arm,n_hint=n,budget=TIMEOUT,policy=FROZEN_V062)
                if status in ('SAT','UNSAT') and r.status in ('SAT','UNSAT') and r.status!=status:
                    raise AssertionError(f"WRONG answer: {c['case_id']} {arm} {r.status}, CMS={status}")
                if r.status=='SAT' and r.witness_valid is not True:
                    raise AssertionError(f"INVALID SAT witness: {c['case_id']} {arm}")
                results.append(dict(case_id=c['case_id'],family=c['family'],publisher=c['publisher'],
                    group='external' if c['publisher']!='DRNAS_constructed_controls' else 'constructed',
                    n=n,repeat=repetition,arm=arm,expected=status,
                    status=r.status,elapsed_ms=round(r.milliseconds,4),
                    route=r.route,parse_ms=round(r.parse_ms,4),
                    screen_ms=round(r.screen_ms,4),horn_ms=round(r.horn_ms,4),
                    backend_ms=round(r.backend_ms,4),witness_valid=r.witness_valid))
        if (index+1)%10==0:
            print('DONE',index+1,'/',len(cases),'family',c['family'],'CMS',status,flush=True)
    write_csv(OUTPUT/'measurements.csv',results)
    write_csv(OUTPUT/'reference.csv',source_rows)
    # Count all statuses, including timeouts. Speed only when both finished.
    keyed={(r['case_id'],r['repeat'],r['arm']):r for r in results}
    summaries=[]
    groupings=sorted(set((r['group'],r['family']) for r in results))
    groupings.extend([('external','ALL'),('constructed','ALL'),('ALL','ALL')])
    for grp,family in groupings:
        selected=[x for x in cases if
            (grp=='ALL' or ('constructed' if x['publisher']=='DRNAS_constructed_controls' else 'external')==grp)
            and (family=='ALL' or x['family']==family)]
        ids={x['case_id'] for x in selected}
        rs=[r for r in results if r['case_id'] in ids]
        matched=[];valid_count=0
        for c in selected:
            cid=c['case_id']
            if source_rows[[x['case_id'] for x in source_rows].index(cid)]['expected'] not in ('SAT','UNSAT'):
                continue
            for repeat in range(REPEATS):
                a=keyed[(cid,repeat,'base')];b=keyed[(cid,repeat,'prefix')]
                if a['status']==b['status'] and a['status'] in ('SAT','UNSAT'):
                    matched.append((a['elapsed_ms'],b['elapsed_ms']))
        perarm={k:[r for r in rs if r['arm']==k] for k in ARMS}
        summarized=dict(group=grp,family=family,files=len(selected),
           reference_solved=sum(x['expected'] in ('SAT','UNSAT') for x in source_rows if x['case_id'] in ids),
           base_completed=sum(r['status'] in ('SAT','UNSAT') for r in perarm['base'])//REPEATS,
           prefix_completed=sum(r['status'] in ('SAT','UNSAT') for r in perarm['prefix'])//REPEATS,
           base_timeout=sum(r['status']=='TIMEOUT' for r in perarm['base'])//REPEATS,
           prefix_timeout=sum(r['status']=='TIMEOUT' for r in perarm['neuroflow'])//REPEATS,
           same_complete_pairs=len(matched),
           base_median_ms=round(statistics.median(x[0] for x in matched),4) if matched else '',
           prefix_median_ms=round(statistics.median(x[1] for x in matched),4) if matched else '',
           v07_median_ms=round(statistics.median(r['elapsed_ms'] for r in perarm['v07'] if r['status'] in ('SAT','UNSAT')),4) if any(r['status'] in ('SAT','UNSAT') for r in perarm['v07']) else '',
           mean_paired_gain_ms=round(statistics.mean(a-b for a,b in matched),4) if matched else '',
           median_paired_gain_ms=round(statistics.median(a-b for a,b in matched),4) if matched else '',
           adaptive_wins=sum(a>b for a,b in matched),
           horn_recognized=len({r['case_id'] for r in perarm['neuroflow'] if 'Horn' in r['route']}),
           stage1_skipped=len({r['case_id'] for r in perarm['neuroflow'] if r['route']=='stage1-skip'}),
           stage2_skipped=len({r['case_id'] for r in perarm['neuroflow'] if r['route']=='stage2-skip'}))
        summaries.append(summarized)
    write_csv(OUTPUT/'summary.csv',summaries)
    (OUTPUT/'policy.json').write_text(json.dumps(FROZEN_V062,indent=2))
    (OUTPUT/'protocol.json').write_text(json.dumps(dict(
       v='0.7.1',external_cases=len(actual),constructed_controls=len(manufactured),
       repetitions=REPEATS,wall_budget_seconds=TIMEOUT,exact_same_cdcl_binary=True,
       same_original_file_on_backend_fallback=True,neuro_policy='frozen v0.6.2 + deterministic conservative 32KiB prefix rejection',
       preprocessing_and_subprocess_included=True,
       proof='Every SAT model checked against original input; UNSAT status cross-checked with CMS if reference available',
       limitations='Comparison includes Python process/orchestration cost. Constructed positives never pooled as real-world success evidence. No general SAT claim.'),indent=2))
    print('FINAL_SUMMARY',flush=True)
    for row in summaries:print(json.dumps(row),flush=True)

if __name__=='__main__':main()
