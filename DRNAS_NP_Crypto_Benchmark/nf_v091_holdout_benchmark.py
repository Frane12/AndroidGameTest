#!/usr/bin/env python3
"""v0.9.1 independent Byt-Wyze HOLDOUT — frozen CaDiCaL::Solver::phase policy.

Never train or select on these results. The 20 CNFs were chosen by filename
before fetching or solving, excluding earlier v0.6.3-v0.9 cases.
"""
import csv,json,hashlib,random,statistics,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parent
DATA=ROOT/'nf091_holdout';OUT=ROOT/'native_v09/holdout_results'
EXE=ROOT/'native_v09/drnas_nf09'
BUDGET_MS=2500
REPEATS=3
METHODS=('base','phase-majority','phase-selective','phase-minority')

def write(p,rows):
    with p.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

def ref(path):
    try:
        p=subprocess.run(['cryptominisat5','--verb','0',str(path)],
                        capture_output=True,text=True,timeout=10)
        if 's UNSATISFIABLE' in p.stdout:return 'UNSAT'
        if 's SATISFIABLE' in p.stdout:return 'SAT'
        return 'UNKNOWN'
    except subprocess.TimeoutExpired:
        return 'REF_TIMEOUT'

def execute(path,mode):
    p=subprocess.run([str(EXE),'--input',str(path),
      '--mode',mode,'--budget-ms',str(BUDGET_MS)],
      capture_output=True,text=True,timeout=BUDGET_MS/1000+3)
    if p.returncode:
        raise RuntimeError(f'C++ crash {path} {mode}: {p.stderr[-1000:]}')
    d=json.loads(p.stdout.strip())
    assert d['status'] in ('SAT','UNSAT','UNKNOWN')
    assert d['status']!='SAT' or d['witness_valid'] is True
    return d

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    with (DATA/'manifest.csv').open(encoding='utf-8') as f:manifest=list(csv.DictReader(f))
    assert len(manifest)==20
    rng=random.Random(2026110420)
    rng.shuffle(manifest)
    measurements=[];references=[]
    for i,case in enumerate(manifest):
        path=DATA/(case['id']+'.cnf')
        assert hashlib.sha256(path.read_bytes()).hexdigest()==case['canonical_sha256']
        cms=ref(path)
        references.append(dict(id=case['id'],label=case['group'],source=case['source_name'],
            original_sha256=case['source_sha256'],reference=cms,n=case['n'],m=case['m']))
        for rep in range(REPEATS):
            j=(i+rep)%len(METHODS)
            sequence=METHODS[j:]+METHODS[:j]
            for method in sequence:
                d=execute(path,method)
                if cms in ('SAT','UNSAT') and d['status'] in ('SAT','UNSAT'):
                    assert cms==d['status'],(case['source_name'],method,cms,d)
                measurements.append(dict(id=case['id'],group=case['group'],
                    repeat=rep,mode=method,reference=cms,status=d['status'],
                    route=d['route'],total_ms=d['total_ms'],
                    solver_ms=d['solver_ms'],phase_ms=d['phase_ms'],
                    phase_count=d['phase_count']))
        if (i+1)%5==0:print('TESTED',i+1,'/20',flush=True)
    write(OUT/'references.csv',references)
    write(OUT/'raw_times.csv',measurements)
    ref_by_id={r['id']:r['reference'] for r in references}
    by={(r['id'],r['repeat'],r['mode']):r for r in measurements}
    summary=[]
    for grouping in ('sat','unsat','ALL'):
        chosen=[r for r in references if grouping=='ALL' or r['label']==grouping]
        for arm in METHODS[1:]:
            gains=[];case_gains=[];paired=0;complete_base=0;complete_arm=0
            for case in chosen:
                per_case=[]
                for rep in range(REPEATS):
                    a=by[(case['id'],rep,'base')];b=by[(case['id'],rep,arm)]
                    complete_base+=a['status'] in ('SAT','UNSAT')
                    complete_arm+=b['status'] in ('SAT','UNSAT')
                    if (ref_by_id[case['id']] in ('SAT','UNSAT') and
                        a['status']==b['status']==ref_by_id[case['id']]):
                        g=float(a['total_ms'])-float(b['total_ms'])
                        gains.append(g);per_case.append(g);paired+=1
                if per_case:case_gains.append(statistics.median(per_case))
            summary.append(dict(group=grouping,mode=arm,cases=len(chosen),
              references_known=sum(r['reference'] in ('SAT','UNSAT') for r in chosen),
              baseline_completed_runs=complete_base,mode_completed_runs=complete_arm,
              paired_completed=paired,
              pairwise_mean_gain_ms=round(statistics.mean(gains),3) if gains else '',
              pairwise_median_gain_ms=round(statistics.median(gains),3) if gains else '',
              case_median_gain_ms=round(statistics.median(case_gains),3) if case_gains else '',
              cases_faster=sum(x>0 for x in case_gains),
              cases_with_paired=len(case_gains)))
    write(OUT/'summary.csv',summary)
    (OUT/'protocol.json').write_text(json.dumps(dict(
       release='v0.9.1 independent confirmation: frozen v0.9 polarity hints',
       upstream='Byt-Wyze third-party synthetic SAT, pinned commit 0a150d63...',
       selection='10 SAT label + 10 UNSAT label, deterministic random from unseen filenames; no outcome cherry-pick',
       overlap_with_prior_16=0,repeats=REPEATS,budget_ms=BUDGET_MS,
       timings='native C++ in-process CaDiCaL, all parser/hint/solver overhead',
       reference='CryptoMiniSat status; results UNKNOWN excluded from paired timings but included in completed counts',
       inference='new data is only for independent evaluation, not choosing thresholds or fitting'),indent=2))
    print('INDEPENDENT HOLDOUT RESULTS',flush=True)
    for s in summary:print(json.dumps(s),flush=True)

if __name__=='__main__':main()
