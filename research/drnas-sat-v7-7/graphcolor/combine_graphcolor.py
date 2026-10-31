#!/usr/bin/env python3
"""Strictly aggregate all benchmark shards; never drop slower/failed formulas.

Compare on the same fixed graph 3-color SAT CNFs, with all timeouts/errors
counted as PAR-2. Casewise median of two repetitions, bootstrap over graph
identities, not over within-graph repeats.
"""
import argparse,csv,json,random,statistics
from pathlib import Path
METHODS=('plain','quality_plain','quality_guided','quality_random','kissat404')
CAP=15.

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--root',required=True)
    p.add_argument('--outdir',required=True)
    args=p.parse_args()
    files=sorted(Path(args.root).glob('graphcolor-shard*-results/gc_results/raw.csv'))
    assert len(files)==6,(len(files),files)
    out=Path(args.outdir);out.mkdir(parents=True,exist_ok=True)
    data=[];per_shard={}
    for file in files:
        with file.open(newline='',encoding='utf8') as h:items=list(csv.DictReader(h))
        assert items
        per_shard[str(file)]=len(items);data+=items
    ids={r['case'] for r in data}
    assert len(ids)==58,(len(ids),'Graph Coloring holdout must contain exactly 58 original cases')
    assert len(data)==58*2*len(METHODS),(len(data),per_shard)
    pivot={}
    hashes={}
    for r in data:
        key=(r['case'],r['method'],int(r['rep']))
        assert key not in pivot,key
        pivot[key]=r
        if r['case'] in hashes:assert hashes[r['case']]==r['cnf_sha256']
        hashes[r['case']]=r['cnf_sha256']
        assert (int(r['vertices']),int(r['edges']))==(200,479)
        assert r['status'] in ('SAT','TIMEOUT','ERROR')
    for case in ids:
        for mode in METHODS:
            for rep in range(2):assert (case,mode,rep) in pivot
    def cost(case,mode):
        return statistics.median([float(pivot[(case,mode,rep)]['par2_seconds']) for rep in range(2)])
    ids=sorted(ids)
    plain=sum(cost(c,'plain') for c in ids)
    result={}
    for mode in METHODS:
        new=sum(cost(c,mode) for c in ids)
        nsolved=sum(pivot[(c,mode,rep)]['status']=='SAT' for c in ids for rep in range(2))
        errors=sum(pivot[(c,mode,rep)]['status']=='ERROR' for c in ids for rep in range(2))
        result[mode]=dict(par2_total_case_median_seconds=round(new,6),
          percent_par2_saving_vs_CaDiCaL=round(100*(1-new/plain),4),
          completed_runs=nsolved,total_runs=116,errors=errors,
          faster_cases=sum(cost(c,mode)<cost(c,'plain') for c in ids),
          slower_cases=sum(cost(c,mode)>cost(c,'plain') for c in ids),
          solved_cases=sum(all(pivot[(c,mode,i)]['status']=='SAT' for i in range(2)) for c in ids))
    rng=random.Random(7707777);boot={}
    for mode in METHODS[1:]:
        ratios=[]
        for _ in range(2000):
            draw=[rng.choice(ids) for __ in ids]
            a=sum(cost(c,'plain') for c in draw);b=sum(cost(c,mode) for c in draw)
            ratios.append(100*(1-b/a))
        ratios.sort()
        boot[mode]=[round(ratios[49],3),round(ratios[1949],3)]
    response=dict(experiment='DRNAS v7.7 vs same CaDiCaL and independent Kissat',
        dataset='58 original graph 3-color SATLIB flat200-479 CNF cases with certified graph equivalence',
        predeclared_60_total=60,smoke_pilots_not_in_holdout=2,benchmarked=58,
        per_case_repetitions=2,per_run_cap_sec=CAP,PAR2_timeout_penalty_s=2*CAP,
        all_58_SAT_expected=True,source_archive_SATLIB_SHA256='a27f57132377dc6be4fd11a938c78e6ec245e65fb33fa7a86579ef986c7c242b',
        not_official_competition_result=True,
        not_blind_holdout='Yes, SATLIB graph coloring public set used in earlier DRNAS work; graph-level fixed-source comparison',
        graph_format='Proven exact reconstruction from original CNF clauses: 200 nodes/479 edges/3-color decisions',
        zykovcolor='NOT_RUN unless the official ZykovColor build with Gurobi/Boost/Open-WBO/ExactColors/CliSAT can be provided. No made-up timings.',
        mechanisms='CaDiCaL 3.0.1 common core for plain/quality_plain/quality_guided/quality_random, Kissat 4.0.4 independent',
        results=result,bootstrap_case_resampled_95pct_saving_pct=boot,
        limitations='One SAT instance family with all graph problems known 3-colorable; different from full optimization/minimum-color proof, and not representative of all graph coloring.')
    with (out/'all_raw.csv').open('w',newline='',encoding='utf8') as f:
        w=csv.DictWriter(f,fieldnames=list(data[0]));w.writeheader();w.writerows(data)
    (out/'results.json').write_text(json.dumps(response,indent=2))
    lines=['# DRNAS SAT v7.7 vs CaDiCaL / Kissat on real graph coloring',
       '', '58 certified same-source three-color SATLIB flat200-479 graphs; 2 repetitions each.',
       '**ZykovColor requires separately installed Gurobi/Boost/Open-WBO/exactcolors and is not timed in the GitHub-hosted experiment.**',
       '', '| Method | Local PAR2, case-median sum (s) | Difference vs CaDiCaL | Solved/116 | Errors |',
       '|---|---:|---:|---:|---:|']
    for mode,d in result.items():
        lines.append(f"| {mode} | {d['par2_total_case_median_seconds']:.4f} | "
          f"{d['percent_par2_saving_vs_CaDiCaL']:+.3f}% | "
          f"{d['completed_runs']}/116 | {d['errors']} |")
    lines.extend(['','## 95% bootstrap uncertainty on percentage savings over CaDiCaL'])
    for mode,ci in boot.items():lines.append(f'- {mode}: [{ci[0]:+.3f}%, {ci[1]:+.3f}%]')
    lines.extend(['','## Interpretation',
       '- No official Graph Coloring competition ranking is claimed.',
       '- Same CNF identical data and same CaDiCaL binary isolates overhead of v7.7.',
       '- ZykovColor is a specialized graph solver: it must be tested as the SAME 3-color DECISION problem, not full chromatic-number optimization.',
       '- SAT model checked against the original input CNF by the native DRNAS variant; Kissat witness independently checked.',
       '- Every timeout and error counts as the full PAR-2 penalty; source files were fixed before measurements.',
       '- One family of public SATLIB graphs cannot show general performance across arbitrary graph coloring instances.'])
    report='\n'.join(lines)+'\n'
    (out/'report.md').write_text(report)
    print(report,flush=True)
if __name__=='__main__':main()
