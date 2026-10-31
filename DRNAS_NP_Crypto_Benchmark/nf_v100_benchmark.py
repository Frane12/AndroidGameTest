#!/usr/bin/env python3
"""v1.0 frozen native auto-selector evaluation on 20 previously UNSEEN CNFs.

Reads only nf100_holdout after nf_v100_train wrote the frozen model.
Compares base vs auto vs forced majority/selective using SAME native CaDiCaL.
"""
import csv,hashlib,json,random,statistics,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parent
BIN=ROOT/'native_v100/drnas_nf100'
POLICY=ROOT/'native_v100/training/frozen_policy.txt'
FROZEN=ROOT/'native_v100/training/frozen_decision.json'
CORPUS=ROOT/'nf100_holdout'
OUT=ROOT/'native_v100/holdout_results'
METHODS=('base','auto','phase-majority','phase-selective')
MS_BUDGET=2300
REPS=3

def write(path,rows):
    with path.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]))
        w.writeheader();w.writerows(rows)

def oracle(path):
    try:
        p=subprocess.run(['cryptominisat5','--verb','0',str(path)],
                     capture_output=True,text=True,timeout=10)
        if 's UNSATISFIABLE' in p.stdout:return 'UNSAT'
        if 's SATISFIABLE' in p.stdout:return 'SAT'
        return 'UNKNOWN'
    except subprocess.TimeoutExpired:return 'REF_TIMEOUT'

def solve(path,mode):
    cmd=[str(BIN),'--input',str(path),'--mode',mode,
         '--budget-ms',str(MS_BUDGET)]
    if mode=='auto':cmd+=['--policy',str(POLICY)]
    p=subprocess.run(cmd,capture_output=True,text=True,timeout=MS_BUDGET/1000+4)
    if p.returncode:raise RuntimeError(f'{path.name}/{mode}: {p.stderr[-1000:]}')
    r=json.loads(p.stdout.strip())
    if r['status']=='SAT':assert r['witness_valid'] is True
    return r

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    assert POLICY.exists() and FROZEN.exists()
    decision=json.loads(FROZEN.read_text())
    assert decision['no_holdout_access'] is True
    with (CORPUS/'manifest.csv').open(encoding='utf-8') as f:manifest=list(csv.DictReader(f))
    assert len(manifest)==20 and len({m['original_sha256'] for m in manifest})==20
    random.Random(202611010001).shuffle(manifest)
    ref=[];rows=[]
    for i,x in enumerate(manifest):
        path=CORPUS/(x['id']+'.cnf')
        assert hashlib.sha256(path.read_bytes()).hexdigest()==x['normalized_sha256']
        expected=oracle(path)
        ref.append(dict(id=x['id'],source=x['original_path'],expected=expected,
            group=x['label'],n=x['n'],m=x['m']))
        for rep in range(REPS):
            j=(i+rep)%len(METHODS)
            for mode in METHODS[j:]+METHODS[:j]:
                result=solve(path,mode)
                if expected in ('SAT','UNSAT') and result['status'] in ('SAT','UNSAT'):
                    assert result['status']==expected,(x['original_path'],mode,result,expected)
                rows.append(dict(id=x['id'],group=x['label'],repeat=rep,
                    mode=mode,expected=expected,status=result['status'],
                    route=result['route'],selected=result['selected'],
                    total_ms=result['total_ms'],phase_ms=result['phase_ms'],
                    phase_count=result['phase_count'],parse_ms=result['parse_ms']))
        if (i+1)%5==0:print('HELDOUT',i+1,'/20',flush=True)
    write(OUT/'independent_reference.csv',ref)
    write(OUT/'raw_timings.csv',rows)
    pivot={(r['id'],r['repeat'],r['mode']):r for r in rows}
    grouped=[]
    for family in ('sat','unsat','ALL'):
        examples=[x for x in ref if family=='ALL' or x['group']==family]
        for method in METHODS[1:]:
            a_done=b_done=0
            diff=[];percent=[];base_times=[];new_times=[]
            improved_cases=0;paired_cases=0;by_engine={}
            for x in examples:
                per_case=[]
                for rep in range(REPS):
                    a=pivot[(x['id'],rep,'base')]
                    b=pivot[(x['id'],rep,method)]
                    a_done+=a['status'] in ('SAT','UNSAT')
                    b_done+=b['status'] in ('SAT','UNSAT')
                    if method=='auto':
                        by_engine[b['selected']]=by_engine.get(b['selected'],0)+1
                    if (x['expected'] in ('SAT','UNSAT') and
                        a['status']==b['status']==x['expected']):
                        base=float(a['total_ms']);new=float(b['total_ms'])
                        gain=base-new
                        per_case.append(gain);diff.append(gain)
                        percent.append(100*gain/base if base>0 else 0)
                        base_times.append(base);new_times.append(new)
                if per_case:
                    paired_cases+=1
                    improved_cases+=statistics.median(per_case)>0
            grouped.append(dict(group=family,method=method,cases=len(examples),
                ref_known=sum(x['expected'] in ('SAT','UNSAT') for x in examples),
                base_completed_runs=a_done,method_completed_runs=b_done,
                paired_completed_runs=len(diff),paired_cases=paired_cases,
                faster_cases=improved_cases,
                median_base_ms=round(statistics.median(base_times),4) if diff else '',
                median_method_ms=round(statistics.median(new_times),4) if diff else '',
                mean_paired_gain_ms=round(statistics.mean(diff),4) if diff else '',
                median_paired_gain_ms=round(statistics.median(diff),4) if diff else '',
                median_paired_relative_gain_pct=round(statistics.median(percent),3) if diff else '',
                aggregate_completed_time_gain_pct=round(100*(1-sum(new_times)/sum(base_times)),3) if diff else '',
                selected_engines=json.dumps(by_engine,sort_keys=True)))
    write(OUT/'summary.csv',grouped)
    (OUT/'protocol.json').write_text(json.dumps(dict(
        version='1.0',frozen_policy_decision=decision,
        comparison='native in-process CaDiCaL, same original clauses and C++ parser',
        labels='source labels not used in native model',
        test='20 fresh SHA-disjoint Byt-Wyze CNFs after 80 TRAIN formulas',
        repeats=REPS,wall_ms=MS_BUDGET,
        independent_oracle='CryptoMiniSat for status; each native SAT model checked',
        caution='Time metrics conditional on matched completed cases; completion reported separately. This is a small synthetic third-party corpus, not a universal SAT claim.'),indent=2))
    print('FINAL UNSEEN V1.0 RESULTS',flush=True)
    for row in grouped:print(json.dumps(row),flush=True)

if __name__=='__main__':main()
