#!/usr/bin/env python3
"""DRNAS NeuroFlow v0.6.3 zero-shot EXTERNAL benchmark.

Frozen v0.6.2 policy learned ONLY from SATLIB+constructed previous runs;
there is no tuning against the third-party datasets.
Compare same original DIMACS CNF: DRNAS, fixed NeuroFlow, forced Horn probe,
and old 17-feature policy; CryptoMiniSat independently validates statuses.
"""
import csv,json,random,statistics,subprocess,traceback,time
from pathlib import Path
from drnas_np_lab import read_dimacs,check
from nf_v062_hornfast import run as nf_run
from nf_v06_multifeature import run as nf_v06

ROOT=Path(__file__).resolve().parent
CORPUS=ROOT/'nf063_external'
DEST=ROOT/'nf063_results'
BUDGET=0.75
REPEATS=3
# INDEPENDENTLY FIXED before fetching sources; exact training outcome v0.6.2.
FROZEN={'enabled':True,'min_n':30,'minority_min':0.13,'minority_max':0.28,
        'unit_max':0.0,'defect_max':0.1,'pair_budget_ms':12.0}
VARIANTS=['base','adaptive','force','old-v06']

def write(path,records):
    with path.open('w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=list(records[0]))
        writer.writeheader();writer.writerows(records)

def reference(path):
    t=time.perf_counter()
    try:
        p=subprocess.run(['cryptominisat5','--verb','0',str(path)],
             capture_output=True,text=True,timeout=7)
        st='UNSAT' if 's UNSATISFIABLE' in p.stdout else 'SAT' if 's SATISFIABLE' in p.stdout else 'REF_ERROR'
        return st,round(1000*(time.perf_counter()-t),4)
    except subprocess.TimeoutExpired:
        return 'REF_TIMEOUT',round(1000*(time.perf_counter()-t),4)

def execute(n,cnf,method):
    start=time.perf_counter()
    try:
        if method=='old-v06':
            # v0.6 selected global OFF but wrongly computed its full features.
            r=nf_v06(n,cnf,'learned',{'selection':{'disabled':True}},budget=BUDGET)
            status,model,route,elapsed=r.status,r.assignment,r.method,r.ms
            gate=r.feature_ms
        else:
            r=nf_run(n,cnf,method,FROZEN,budget=BUDGET)
            status,model,route,elapsed=r.status,r.model,r.route,r.ms
            gate=r.first_ms+r.defect_ms
        if status=='SAT' and (model is None or not check(cnf,model)):
            raise AssertionError('INVALID SAT assignment: '+method)
        return dict(status=status,elapsed_ms=round(elapsed,4),route=route,gate_ms=round(gate,4))
    except Exception as ex:
        return dict(status='ERROR',elapsed_ms=round(1000*(time.perf_counter()-start),4),
                    route=type(ex).__name__+': '+str(ex)[:90],gate_ms=0.0)

def run():
    DEST.mkdir(exist_ok=True)
    with (CORPUS/'manifest.csv').open(encoding='utf-8') as f:manifest=list(csv.DictReader(f))
    assert len(manifest)==60
    cases=[]
    for row in manifest:
        if row['fetch_status']!='READY':
            continue
        filename=CORPUS/(row['case_id']+'.cnf')
        n,cnf=read_dimacs(filename)
        assert n==int(row['variables']) and len(cnf)==int(row['clauses'])
        cases.append(dict(row=row,filename=filename,n=n,cnf=cnf))
    random.Random(2026103107).shuffle(cases)
    source_rows=[];measurements=[];wrong=0
    for index,case in enumerate(cases):
        source=case['row']
        ref,reference_ms=reference(case['filename'])
        source_rows.append(dict(case_id=source['case_id'],source_group=source['source_group'],
            source_url=source['source_url'],variables=case['n'],clauses=len(case['cnf']),
            CMS_status=ref,CMS_process_ms=reference_ms))
        for rep in range(REPEATS):
            shift=(index+rep)%4
            order=VARIANTS[shift:]+VARIANTS[:shift]
            results={variant:execute(case['n'],case['cnf'],variant) for variant in order}
            if ref in ('SAT','UNSAT'):
                for variant,r in results.items():
                    if r['status'] in ('SAT','UNSAT') and r['status']!=ref:
                        wrong+=1;raise AssertionError(f"Wrong solver result for {source['case_id']} {variant}: {r['status']} vs CMS {ref}")
            for variant,r in results.items():
                measurements.append(dict(case_id=source['case_id'],
                    source_group=source['source_group'],rep=rep,solver=variant,
                    expected_CMS=ref,solver_status=r['status'],
                    elapsed_ms=r['elapsed_ms'],gate_ms=r['gate_ms'],route=r['route']))
        if (index+1)%10==0:
            print('EVALUATED',index+1,'/',len(cases),'CMS',ref,flush=True)
    if measurements:write(DEST/'raw_timings.csv',measurements)
    if source_rows:write(DEST/'independent_reference.csv',source_rows)
    summary=[]
    groups=sorted({x['source_group'] for x in source_rows})+['ALL']
    for group in groups:
        ids={x['case_id'] for x in source_rows if group=='ALL' or x['source_group']==group}
        valid_ref={x['case_id'] for x in source_rows if x['case_id'] in ids and x['CMS_status'] in ('SAT','UNSAT')}
        paired=[]
        methods={}
        for method in VARIANTS:
            data=[r for r in measurements if r['case_id'] in valid_ref and r['solver']==method]
            methods[method]=data
        by={(r['case_id'],r['rep'],r['solver']):r for r in measurements}
        for cid in valid_ref:
            for rep in range(REPEATS):
                a=by.get((cid,rep,'base'));b=by.get((cid,rep,'adaptive'))
                if a and b and a['solver_status']==b['solver_status'] and a['solver_status'] in ('SAT','UNSAT'):
                    paired.append(a['elapsed_ms']-b['elapsed_ms'])
        baseline=[r['elapsed_ms'] for r in methods['base'] if r['solver_status'] in ('SAT','UNSAT')]
        adaptive=[r['elapsed_ms'] for r in methods['adaptive'] if r['solver_status'] in ('SAT','UNSAT')]
        forced=[r['elapsed_ms'] for r in methods['force'] if r['solver_status'] in ('SAT','UNSAT')]
        selected={r['case_id'] for r in methods['adaptive'] if 'Horn' in r['route']}
        summary.append(dict(group=group,files=len(ids),CMS_known=len(valid_ref),
             baseline_solved=sum(r['solver_status'] in ('SAT','UNSAT') for r in methods['base'])//REPEATS,
             adaptive_solved=sum(r['solver_status'] in ('SAT','UNSAT') for r in methods['adaptive'])//REPEATS,
             baseline_median_ms=round(statistics.median(baseline),4) if baseline else '',
             adaptive_median_ms=round(statistics.median(adaptive),4) if adaptive else '',
             forced_median_ms=round(statistics.median(forced),4) if forced else '',
             paired_count=len(paired),
             paired_gain_mean_ms=round(statistics.mean(paired),4) if paired else '',
             paired_gain_median_ms=round(statistics.median(paired),4) if paired else '',
             paired_wins=sum(x>0 for x in paired),recognized_cases=len(selected),
             stage1_rejected=len({r['case_id'] for r in methods['adaptive'] if r['route']=='skip-first'}),
             stage2_rejected=len({r['case_id'] for r in methods['adaptive'] if r['route']=='skip-defect'})))
    write(DEST/'summary.csv',summary)
    (DEST/'frozen_external_policy.json').write_text(json.dumps(FROZEN,indent=2))
    (DEST/'protocol.json').write_text(json.dumps(dict(
       external_publishers=['Tractables/cnfs','Byt-wyze-technology/sat-instances-library'],
       selected_external_files=len(manifest),parsed_external_files=len(cases),
       variant='v0.6.2 previously frozen zero-shot, NOT retuned on external test',
       repeats=REPEATS,budget_seconds=BUDGET,
       any_wrong_statuses=wrong,
       all_SAT_assignments_verified=True,
       cms='Cryptominisat checks statuses; process time not comparable to Python in-process',
       restricted='Only matched completed solver pairs in speed estimates; timeouts reported separately',
       selection='fixed seeds and source sizes before solving; no post-outcome selection'),indent=2))
    print('FINAL SUMMARY',flush=True)
    for r in summary:print(json.dumps(r),flush=True)
    print('SOURCE DOWNLOAD VALIDITY:',{v:sum(x['fetch_status']==v for x in manifest)
        for v in sorted(set(x['fetch_status'] for x in manifest))},flush=True)
    print('REFERENCE STATUS:',{v:sum(x['CMS_status']==v for x in source_rows)
        for v in sorted(set(x['CMS_status'] for x in source_rows))},flush=True)

if __name__=='__main__':run()
