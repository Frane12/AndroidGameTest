#!/usr/bin/env python3
"""Aggregate EXACT 10 shuffled two-case official SATCompetition 2026 shards.
No missing shards, no duplicates, all eight true V7.5.1 methods retained.
"""
import argparse,csv,json,statistics,collections
from pathlib import Path
from benchmark import report,FIELDS,METHODS

def main():
    a=argparse.ArgumentParser()
    a.add_argument('--root',required=True)
    a.add_argument('--outdir',required=True)
    a=a.parse_args()
    root=Path(a.root);out=Path(a.outdir);out.mkdir(parents=True,exist_ok=True)
    files=sorted(root.glob('v751-sc26-shard*-results/v751_sc26/raw.csv'))
    assert len(files)==10,f'Expected all 10 shards, got {len(files)}: {files}'
    rows=[];sources={}
    for f in files:
        group=list(csv.DictReader(f.open(encoding='utf8',newline='')))
        assert len(group)==2*8*2,(f,len(group))
        for r in group:
            k=r['case']
            if k in sources and sources[k]!=str(f):raise RuntimeError('Duplicate official GBD ID '+k)
            sources[k]=str(f)
            row={}
            for key in FIELDS:
                value=r.get(key,'')
                if key in ('repeat','hints','limit_conflicts','stage1_status','resumed','variables','clauses'):
                    row[key]=int(value) if value else None
                elif key in ('elapsed_s','native_s','hint_us','stage1_us','stage2_us','cutoff_s'):
                    row[key]=float(value) if value else None
                else:row[key]=value
            rows.append(row)
    assert len(sources)==20 and len(rows)==20*8*2,(len(sources),len(rows))
    combined=report(rows,2,60.)
    combined.update(dict(
       collection='SAT Competition 2026 Main Track ORIGINAL official GBD IDs',
       selection='SAME twenty downloadable sources from previous run 41204322891',
       original_preselected=24,downloaded=20,excluded_oversized=4,
       version='DRNAS SAT V7.5.1',backend='CaDiCaL 3.0.1 unmodified in every arm',
       comparison='LOCAL 60s process cap / 120s PAR2 penalty; not official 5000s competition evaluation',
       official_result=False,
       no_unsat_proofs_checked=True,
       shards=10,
       rows=len(rows),
       error_runs=sum(bool(r['error']) for r in rows),
       completed_formulas=len(sources),
       raw_data_contains_all_runs=True))
    with (out/'all_raw.csv').open('w',newline='',encoding='utf8') as f:
        w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();w.writerows(rows)
    (out/'summary.json').write_text(json.dumps(combined,indent=2))
    lines=[
      '# DRNAS SAT V7.5.1 — real SAT Competition 2026 Main CNFs',
      '',
      '**Local independent reproduction, NOT official competition ranking.**',
      '20 identical official GBD instances re-used from run #41204322891, '
      'two repeats per method, local 60-second cap (PAR2 timeout penalty 120s).',
      'All eight original V7.5.1 modes, same unmodified CaDiCaL **3.0.1**.',
      '',
      '| Mode | Local PAR-2 sum of case medians (s) | Speed ratio vs CaDiCaL plain | Completed/40 | Faster cases |',
      '|---|---:|---:|---:|---:|',
    ]
    base=combined['modes']['plain']['par2_sum_case_medians_s']
    for method in METHODS:
        v=combined['modes'][method]
        lines.append(f"| {method} | {v['par2_sum_case_medians_s']:.3f} | "
                     f"{v['speedup_plain_over_mode']:.4f}x | "
                     f"{v['solved_runs']}/{v['total_runs']} | {v['faster_cases']} |")
    lines+=['','**Relative PAR-2 percentage vs plain:**']
    for method in METHODS[1:]:
        score=combined['modes'][method]['par2_sum_case_medians_s']
        lines.append(f"- {method}: {100*(1-score/base):+.3f}% (positive better).")
    lines+=['','**Coverage**',
       f"- 20 same previously downloaded official original CNF files; 4 of original 24 over size cap",
       f"- Error runs counted as timeout with a 120-second PAR-2 penalty: {combined['error_runs']}",
       '- All sources SHA256 authenticated to the previous official run.',
       '- Stage-1 256/1024 conflict probes resume the SAME solver and keep learned clauses.',
       '- plain/majority and two split_plain controls reveal hint vs resume overhead.',
       '- SAT models are checked by the native solver; UNSAT proofs are not independently verified.',
       '- This short-cap size-limited sample cannot establish superiority at official 5000-second conditions.',
       '- CaDiCaL 3.0.1 here differs from the older system libCaDiCaL in previous v1.0 study;',
       '  percentages between the two earlier experiments are NOT directly comparable.',
       '',
       '**Per-mode exploratory bootstrap 95% ratio intervals**',
    ]
    for mode,cint in combined['bootstrap_95pct_ratio'].items():
        lines.append(f'- {mode}: {cint[0]:.4f} to {cint[1]:.4f}')
    text='\n'.join(lines)+'\n'
    (out/'report.md').write_text(text)
    print(text,flush=True)

if __name__=='__main__':main()
