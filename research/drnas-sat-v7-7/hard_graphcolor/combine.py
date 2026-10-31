#!/usr/bin/env python3
"""Complete, immutable 20-case DIMACS GraphColor competition-style summary.

Always include 60-second timeouts/errors as 120-second PAR2 penalties.
Separately identify SAT, UNSAT and unclassified cases from independently
consistent completed solves. Bootstrap by GRAPH (not by 40 correlated k
formulas), to avoid overstating the strength of statistics.
"""
import argparse,csv,json,random,statistics
from pathlib import Path
MODES=('plain','quality_plain','quality_guided','quality_random','kissat404')
CAP=60.

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--root',required=True)
    p.add_argument('--outdir',required=True)
    a=p.parse_args()
    all_files=sorted(Path(a.root).glob('dimacs-hardgraph-shard*-results/results/raw.csv'))
    assert len(all_files)==10,f'Expected exactly 10 shards; got {len(all_files)}'
    rows=[];shards={}
    for f in all_files:
        with f.open(newline='',encoding='utf8') as fd:r=list(csv.DictReader(fd))
        assert len(r)==2*2*len(MODES),(f,len(r))
        shards[str(f)]=len(r);rows+=r
    assert len(rows)==200
    seen={}
    for r in rows:
        key=(r['case'],r['method'],int(r['rep']))
        assert key not in seen,key
        seen[key]=r
    cases=sorted({r['case'] for r in rows})
    assert len(cases)==20 and len(seen)==len(rows)
    graph_by_case={}
    for c in cases:
        graph,kn=c.rsplit('.k',1)
        assert kn.isdigit()
        graph_by_case[c]=graph
        for mode in MODES:
            for rep in (0,1):
                assert (c,mode,rep) in seen
    graphs=sorted(set(graph_by_case.values()))
    assert len(graphs)==10
    labels={}
    for c in cases:
        answers={seen[(c,m,r)]['status'] for m in MODES for r in (0,1)
                 if seen[(c,m,r)]['status'] in ('SAT','UNSAT')}
        assert len(answers)<=1,('CONTRADICTORY OUTCOME',c,answers)
        labels[c]=next(iter(answers)) if answers else 'UNKNOWN'
    def cost(c,m):
        return statistics.median(float(seen[(c,m,r)]['par2_s']) for r in (0,1))
    def aggregation(group_cases):
        plain=sum(cost(c,'plain') for c in group_cases)
        scores={}
        for m in MODES:
            value=sum(cost(c,m) for c in group_cases)
            comp=sum(seen[(c,m,rep)]['status'] in ('SAT','UNSAT')
                     for c in group_cases for rep in (0,1))
            errors=sum(seen[(c,m,rep)]['status']=='ERROR'
                      for c in group_cases for rep in (0,1))
            scores[m]=dict(local_PAR2_sum_median_seconds=round(value,5),
                local_PAR2_mean_seconds=round(value/len(group_cases),5) if group_cases else None,
                percent_PAR2_improvement_vs_plain=round(100*(1-value/plain),4) if plain>0 else None,
                runs_completed=comp, runs_attempted=2*len(group_cases),
                errors=errors,timeout_runs=2*len(group_cases)-comp-errors,
                cases_faster=sum(cost(c,m)<cost(c,'plain') for c in group_cases),
                cases_slower=sum(cost(c,m)>cost(c,'plain') for c in group_cases))
        return scores
    result={label:aggregation([c for c in cases if labels[c]==label])
            for label in ('SAT','UNSAT','UNKNOWN')
            if any(labels[c]==label for c in cases)}
    result['ALL']=aggregation(cases)
    rng=random.Random(777766)
    confidence={}
    for m in MODES[1:]:
        vals=[]
        for _ in range(1600):
            sampled=[rng.choice(graphs) for i in range(len(graphs))]
            cs=[c for g in sampled for c in cases if graph_by_case[c]==g]
            base=sum(cost(c,'plain') for c in cs)
            val=sum(cost(c,m) for c in cs)
            vals.append(100*(1-val/base))
        vals.sort()
        confidence[m]=[round(vals[39],3),round(vals[1559],3)]
    report=dict(project='DRNAS V7.7 on 20 fixed k-colorability decisions of 10 DIMACS challenge graphs',
        sources='Pinned Kaluginaec/graph-coloring-instances original Git blobs, verified edge normalization',
        source_commit='83b4e11b5d83bcf44feb628d1e4f7a994de0a0cf',
        known_class_counts={x:sum(v==x for v in labels.values()) for x in ('SAT','UNSAT','UNKNOWN')},
        problem_classes=labels,cap_sec=CAP,PAR2_timeout_penalty_sec=2*CAP,
        graph_count=len(graphs),decision_count=len(cases),repetitions=2,
        solving_attempts=200,not_official_COMPETITION_result=True,
        models_verified='CaDiCaL SAT witness checked in native C++; Kissat SAT assignment checked against original CNF and .col graph',
        UNSAT_proof_verified_externally=False,
        known_graphs_not_blind=True,
        control_note='quality_plain and quality_random on same CaDiCaL 3.0.1 isolate observer/phase effects. Kissat 4.0.4 is independent strong reference.',
        confidence_resample_unit='10 distinct parent graphs, not 20 correlated k values nor 40 repeated outcomes',
        comparisons=result,bootstrap_95pct_percent_gain=confidence)
    output=Path(a.outdir);output.mkdir(parents=True,exist_ok=True)
    with (output/'all_raw.csv').open('w',newline='',encoding='utf8') as fd:
        w=csv.DictWriter(fd,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    (output/'summary.json').write_text(json.dumps(report,indent=2))
    text=['# DRNAS v7.7 — hard DIMACS graph-coloring benchmark',
      '',f'**{len(graphs)} source graphs, {len(cases)} predeclared k-color decisions, 60s timeout, 2 runs/method.**',
      'SAT/UNSAT truth is only assigned after methods finish, based on consistent completed solver results.',
      'A missing result is UNKNOWN, never assumed SAT or UNSAT.',
      '', '| Method | Local PAR-2 total (s) | Difference vs plain | Completed/40 | Errors |',
      '|---|---:|---:|---:|---:|']
    for mode in MODES:
        q=result['ALL'][mode]
        text.append(f"| {mode} | {q['local_PAR2_sum_median_seconds']:.3f} | "
           f"{q['percent_PAR2_improvement_vs_plain']:+.3f}% | "
           f"{q['runs_completed']}/40 | {q['errors']} |")
    text += ['','## Independently observed problem status',
       f"- SAT: {report['known_class_counts']['SAT']} /20",
       f"- UNSAT: {report['known_class_counts']['UNSAT']} /20",
       f"- UNKNOWN to every method: {report['known_class_counts']['UNKNOWN']} /20",
       '','## Exploratory bootstrap 95% range of PAR-2 % improvement over plain']
    for m,ci in confidence.items():text.append(f'- {m}: [{ci[0]:+.2f}%, {ci[1]:+.2f}%]')
    text += ['','## Limits',
      '- Public DIMACS graphs; not a blinded SAT Competition / graph coloring rank.',
      '- External UNSAT proofs not checked; cross-method completed SAT/UNSAT agreement enforced.',
      '- All errors/timeouts included with 120-second local PAR2 penalty.',
      '- Each graph appears at two fixed k values; bootstrap clusters by original graph.',
      '- Both CaDiCaL variants share exact same codebase; Kissat is an independent solver.',
      '- Does not measure ZykovColor (Gurobi licensed dependency absent on GitHub runners).']
    result_text='\n'.join(text)+'\n'
    (output/'report.md').write_text(result_text)
    print(result_text,flush=True)

if __name__=='__main__':main()
