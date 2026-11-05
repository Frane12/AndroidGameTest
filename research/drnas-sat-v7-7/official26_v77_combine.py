#!/usr/bin/env python3
"""Aggregate 10 unchanged official SATCompetition 2026 CNF shards.

Seven methods, 20 CNFs, two repeats; strict completeness,
full PAR-2 (2*60s penalty on errors/timeouts) plus per-case bootstraps.
"""
import argparse,csv,json,random,statistics
from pathlib import Path
from official26_v77_run import FIELDS,MODES,TIMEOUT

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--root',required=True)
    p.add_argument('--outdir',required=True)
    a=p.parse_args()
    root=Path(a.root);out=Path(a.outdir);out.mkdir(parents=True,exist_ok=True)
    files=sorted(root.glob('drnas-v77-sat26-shard*-results/v77_sc26/raw.csv'))
    assert len(files)==10, f'Need all 10 shards: got {len(files)}'
    rows=[];source={}
    for f in files:
        with f.open(newline='',encoding='utf8') as stream:
            data=list(csv.DictReader(stream))
        assert len(data)==2*2*len(MODES),(str(f),len(data))
        for record in data:
            key=record['case']
            assert key not in source or source[key]==str(f),'duplicate original formula across shards: '+key
            source[key]=str(f)
            rows.append(record)
    assert len(source)==20 and len(rows)==20*2*len(MODES)
    pivot={}
    for r in rows:
        key=(r['case'],int(r['repeat']),r['method'])
        assert key not in pivot,key
        pivot[key]=r
    assert len(pivot)==len(rows)
    for case in source:
        outcomes=set()
        for m in MODES:
            for rep in range(2):
                r=pivot[(case,rep,m)]
                if r['answer'] in ('SAT','UNSAT'):outcomes.add(r['answer'])
                else:assert r['answer'] in ('TIMEOUT','ERROR')
        assert len(outcomes)<=1,(case,outcomes)
    ids=sorted(source)
    def cost(case,mode):
        return statistics.median([
            float(pivot[(case,r,mode)]['elapsed_s'])
            if pivot[(case,r,mode)]['answer'] in ('SAT','UNSAT') else 2*TIMEOUT
            for r in range(2)])
    overall={}
    plain=sum(cost(case,'plain') for case in ids)
    for mode in MODES:
        score=sum(cost(case,mode) for case in ids)
        successes=sum(pivot[(c,r,mode)]['answer'] in ('SAT','UNSAT')
                      for c in ids for r in range(2))
        errors=sum(pivot[(c,r,mode)]['answer']=='ERROR'
                   for c in ids for r in range(2))
        faster=sum(cost(c,mode)<cost(c,'plain') for c in ids)
        improvements=[(cost(c,'plain')-cost(c,mode)) for c in ids]
        overall[mode]=dict(par2_sum_case_medians_s=round(score,5),
            par2_mean_per_case_s=round(score/20,5),
            percent_par2_improvement_vs_plain=round(100*(1-score/plain),4),
            speed_ratio_plain_over_mode=round(plain/score,6),
            completed_runs=successes,attempted_runs=40,
            errors=errors,timeouts=40-successes-errors,
            faster_cases=faster,slower_cases=sum(v<0 for v in improvements))
    rng=random.Random(20267777)
    intervals={}
    for mode in MODES[1:]:
        estimates=[]
        for i in range(1500):
            draw=[rng.choice(ids) for _ in ids]
            base=sum(cost(x,'plain') for x in draw)
            trial=sum(cost(x,mode) for x in draw)
            estimates.append(100*(1-trial/base))
        estimates.sort()
        intervals[mode]=[round(estimates[37],3),round(estimates[1462],3)]
    combined=dict(
        version='DRNAS SAT v7.7; frozen Learner learning(length) gate',
        benchmark='SAT Competition 2026 original Main Track CNFs (same 20 as research run 41204322891)',
        caDiCaL='arminbiere/cadical rel-3.0.1 unmodified',
        kissat='arminbiere/kissat rel-4.0.4 unmodified independent solver',
        exact_original_sha256_validated=True,
        competition_official_score=False,
        github_actions_hardware=True,full_official_main_track=False,
        sample_cases=20,attempts=280,repetitions=2,
        cutoff_s=TIMEOUT,par2_unsolved_penalty_s=120,
        no_external_unsat_proof_check=True,
        no_retraining_on_official_CNFs=True,
        source_caveat='20 previously selected accessible files out of 24; 4 original over-size, no replacement. Official full set 400 files and limit 5000s not reproduced.',
        models_check='CaDiCaL SAT assignments checked natively; Kissat SAT witness checked against original CNF when provided',
        modes=overall,bootstrap_95pct_improvement_percent=intervals)
    with (out/'all_raw.csv').open('w',newline='',encoding='utf8') as f:
        w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();w.writerows(rows)
    (out/'summary.json').write_text(json.dumps(combined,indent=2))
    table=['# DRNAS SAT v7.7 versus CaDiCaL 3.0.1 and Kissat 4.0.4',
        '','20 ORIGINAL SAT Competition 2026 Main CNFs; two repetitions, 60s per process;',
        'Local PAR-2 penalty 120s per unsolved/error attempt; same runner type.',
        'Not a SAT Competition official result, UNSAT proofs not externally checked.',
        '',
        '| Method | Local PAR-2 total (s) | Improvement vs plain | Completed/40 | Error runs |',
        '|---|---:|---:|---:|---:|']
    for m in MODES:
        v=overall[m]
        table.append(f"| {m} | {v['par2_sum_case_medians_s']:.4f} | "
                     f"{v['percent_par2_improvement_vs_plain']:+.3f}% | "
                     f"{v['completed_runs']}/40 | {v['errors']} |")
    table.extend(['','## Bootstrapped 95% exploratory improvement intervals, per CNF'])
    for m,ci in intervals.items():
        table.append(f'- {m}: [{ci[0]:+.3f}%, {ci[1]:+.3f}%]')
    table.extend(['','Every source hash, individual status, completion and error preserved.',
        'Independent Kissat comparison differs in algorithm and codebase; unlike CaDiCaL variants this does NOT isolate NeuroFlow overhead.',
        'Benchmark inputs were previously evaluated with DRNAS versions, so this is a fixed-source replication and NOT an untouched generalization holdout.'])
    (out/'report.md').write_text('\n'.join(table)+'\n')
    print('\n'.join(table),flush=True)
if __name__=='__main__':main()
