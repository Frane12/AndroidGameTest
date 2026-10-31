#!/usr/bin/env python3
"""Independent v1.1 frozen native structural selector benchmark.

42 never-studied SHA-distinct third-party CNFs (30 Byt-Wyze, 12 hardware).
Training/freeze complete before fetching these files. All SAT assignments
verified by native C++; CryptoMiniSat is independent status oracle.
"""
import csv,hashlib,json,random,statistics,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parent
BIN=ROOT/'native_v110/drnas_nf110'
POLICY=ROOT/'native_v110/training/frozen_policy.txt'
DECISION=ROOT/'native_v110/training/frozen_decision.json'
DATA=ROOT/'nf110_holdout'
OUT=ROOT/'native_v110/results'
REPEATS=3;BUDGET_MS=2200
MODES=('base','auto','phase-majority','phase-selective')

def write(path,records):
    with path.open('w',newline='',encoding='utf8') as f:
        w=csv.DictWriter(f,fieldnames=list(records[0]));w.writeheader();w.writerows(records)

def oracle(path):
    try:
        p=subprocess.run(['cryptominisat5','--verb','0',str(path)],
                 capture_output=True,text=True,timeout=9)
        if 's UNSATISFIABLE' in p.stdout:return 'UNSAT'
        if 's SATISFIABLE' in p.stdout:return 'SAT'
        return 'UNKNOWN'
    except subprocess.TimeoutExpired:return 'REF_TIMEOUT'

def native(path,mode):
    args=[str(BIN),'--input',str(path),'--mode',mode,
          '--budget-ms',str(BUDGET_MS)]
    if mode=='auto':args+=['--policy',str(POLICY)]
    p=subprocess.run(args,capture_output=True,text=True,timeout=BUDGET_MS/1000+4)
    if p.returncode:raise RuntimeError(f'Native failure {path.name}/{mode}: {p.stderr[-1200:]}')
    r=json.loads(p.stdout.strip())
    assert r['status'] in ('SAT','UNSAT','UNKNOWN')
    assert r['status']!='SAT' or r['witness_valid'] is True
    return r

def main():
    assert POLICY.exists() and DECISION.exists()
    decision=json.loads(DECISION.read_text())
    assert decision['version']=='v1.1' and decision['no_new_holdout_access'] is True
    with (DATA/'manifest.csv').open(encoding='utf8') as f:manifest=list(csv.DictReader(f))
    assert len(manifest)==42 and len({r['original_sha256'] for r in manifest})==42
    assert sum(r['publisher']=='Byt-wyze-technology/sat-instances-library' for r in manifest)==30
    assert sum(r['publisher']=='Tractables/cnfs' for r in manifest)==12
    OUT.mkdir(parents=True,exist_ok=True)
    random.Random(202611031133).shuffle(manifest)
    reference=[];raw=[]
    for i,c in enumerate(manifest):
        path=DATA/(c['id']+'.cnf')
        assert hashlib.sha256(path.read_bytes()).hexdigest()==c['canonical_sha256']
        truth=oracle(path)
        reference.append(dict(id=c['id'],group=c['source_group'],publisher=c['publisher'],
               source_url=c['source_url'],original_sha256=c['original_sha256'],
               reference=truth,n=c['n'],m=c['m']))
        for rep in range(REPEATS):
            offset=(i+rep)%len(MODES)
            for mode in MODES[offset:]+MODES[:offset]:
                r=native(path,mode)
                if truth in ('SAT','UNSAT') and r['status'] in ('SAT','UNSAT'):
                    assert r['status']==truth,(c['id'],mode,truth,r)
                raw.append(dict(id=c['id'],group=c['source_group'],publisher=c['publisher'],
                   repeat=rep,mode=mode,reference=truth,status=r['status'],
                   route=r['route'],selected=r['selected'],
                   total_ms=r['total_ms'],solver_ms=r['solver_ms'],
                   parse_ms=r['parse_ms'],phase_ms=r['phase_ms'],
                   phase_count=r['phase_count'],witness_valid=r['witness_valid']))
        if (i+1)%7==0:print('HELDOUT',i+1,'/42',flush=True)
    write(OUT/'independent_reference.csv',reference)
    write(OUT/'raw_times.csv',raw)
    look={(r['id'],r['repeat'],r['mode']):r for r in raw}
    summary=[]
    groups=sorted({r['group'] for r in reference})+['BytWyze_all','Hardware_all','ALL']
    for group in groups:
        selected=[r for r in reference if
           group=='ALL' or r['group']==group or
           (group=='BytWyze_all' and r['publisher']=='Byt-wyze-technology/sat-instances-library') or
           (group=='Hardware_all' and r['publisher']=='Tractables/cnfs')]
        for mode in MODES[1:]:
            pairs=[];all_cases=[];completion_baseline=completion_method=0
            engines={};timeouts_base=timeouts_method=0;relative=[];cost=[]
            for c in selected:
                case_diffs=[]
                for rep in range(REPEATS):
                    a=look[(c['id'],rep,'base')]
                    b=look[(c['id'],rep,mode)]
                    aok=a['status'] in ('SAT','UNSAT')
                    bok=b['status'] in ('SAT','UNSAT')
                    completion_baseline+=aok;completion_method+=bok
                    timeouts_base+=not aok;timeouts_method+=not bok
                    if mode=='auto':
                        engines[b['selected']]=engines.get(b['selected'],0)+1
                    if c['reference'] not in ('SAT','UNSAT'):continue
                    if aok and bok and a['status']==b['status']==c['reference']:
                        av=float(a['total_ms']);bv=float(b['total_ms'])
                        pairs.append((av,bv))
                        case_diffs.append(av-bv)
                        relative.append(100*(av-bv)/av if av>0 else 0)
                    # Include failures in unconditional capped utility.
                    if aok and bok:cost.append(max(-250,min(250,a['total_ms']-b['total_ms'])))
                    elif aok and not bok:cost.append(-600)
                    elif bok and not aok:cost.append(400)
                    else:cost.append(0)
                if case_diffs:all_cases.append(statistics.median(case_diffs))
            diffs=[a-b for a,b in pairs]
            summary.append(dict(group=group,mode=mode,files=len(selected),
              reference_known=sum(r['reference'] in ('SAT','UNSAT') for r in selected),
              baseline_completed_runs=completion_baseline,mode_completed_runs=completion_method,
              baseline_unknown_runs=timeouts_base,mode_unknown_runs=timeouts_method,
              paired_complete_runs=len(pairs),paired_cases=len(all_cases),
              cases_faster=sum(v>0 for v in all_cases),
              paired_base_median_ms=round(statistics.median(a for a,b in pairs),4) if pairs else '',
              paired_mode_median_ms=round(statistics.median(b for a,b in pairs),4) if pairs else '',
              paired_mean_gain_ms=round(statistics.mean(diffs),4) if diffs else '',
              paired_median_gain_ms=round(statistics.median(diffs),4) if diffs else '',
              paired_relative_median_gain_pct=round(statistics.median(relative),3) if relative else '',
              paired_total_runtime_gain_pct=round(100*(1-sum(b for a,b in pairs)/sum(a for a,b in pairs)),3) if pairs else '',
              capped_utility_mean_ms=round(statistics.mean(cost),3) if cost else '',
              selected_engines=json.dumps(engines,sort_keys=True)))
    write(OUT/'summary.csv',summary)
    (OUT/'protocol.json').write_text(json.dumps(dict(
         version='v1.1',frozen_policy=decision,
         external_holdout_files=42,
         separately_preselected=30,
         truly_new_hardware_files=12,
         no_train_test_filename_overlap=True,
         repetitions=REPEATS,per_run_budget_ms=BUDGET_MS,
         exact_backend='Same native in-process libCaDiCaL; no SAT labels at inference',
         reference='CryptoMiniSat independent when reference solves',
         metric='Paired same-case timing and ALL completion counts; do not confuse difference of marginal medians with percent gain',
         warning='Sample chosen from two known public publishers; results still require independent replication'),indent=2))
    print('FINAL 42-CNF INDEPENDENT V1.1 RESULT',flush=True)
    for r in summary:print(json.dumps(r),flush=True)

if __name__=='__main__':main()
