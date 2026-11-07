#!/usr/bin/env python3
"""Paired diagnosis of the v7.6 -> v7.7 slowdown on an EXACT 2026 CNF.

All 8 modes use the same compiled solver and the exact SAME phase
hint helper and seed for each repeat. 60-second process cap, raw logs
preserved. This is a diagnostic of a previously selected case, not a
new holdout performance win.
"""
import argparse,csv,hashlib,json,random,statistics,subprocess,time
from collections import defaultdict
from pathlib import Path

MODES=('orig_v76','orig_v77',
       'old_gate_with_observer','new_gate_with_observer',
       'force_extend_with_observer','force_stop_with_observer',
       'force_extend_no_observer','force_stop_no_observer')
SOURCE_HASH='4ae685a11b5cecca76dc3d463481ce92'
SOURCE_SHA256='16b09f959320357facb6345950ba5e6528299fc488c07e99f084446148755158'
CAP=60
FIELDS=('case','source_sha256','repeat','seed','mode','status','wall_s','error',
        'total_us','probe_us','extension_us','resume_us','stage1','stage2',
        'first_budget','second_budget','hints','extended','resumed',
        'active_pre','active_256','redundant_pre','redundant_256','learned_delta',
        'threshold','observer','offered','short5','short_fraction','vars','clauses')
def execute(binary,cnf,mode,seed):
    start=time.perf_counter()
    try:
        result=subprocess.run([str(binary),mode,str(cnf),str(seed)],
            capture_output=True,text=True,check=False,timeout=CAP)
    except subprocess.TimeoutExpired:
        return dict(status='TIMEOUT',wall_s=CAP,error='')
    elapsed=time.perf_counter()-start
    if result.returncode!=0:
        return dict(status='ERROR',wall_s=elapsed,
                    error=f'C++ exit={result.returncode}: {result.stderr[-450:]}')
    vals=[line for line in result.stdout.splitlines()
          if line.startswith('DRNAS_CAUSAL\t')]
    if len(vals)!=1:
        return dict(status='ERROR',wall_s=elapsed,
                    error='Expected exactly one DRNAS_CAUSAL output: '+result.stdout[-350:])
    try:
        cells=[x.split('=',1) for x in vals[0].split('\t')[1:]]
        if any(len(c)!=2 for c in cells):
            raise ValueError('malformed machine-readable token')
        obj=dict(cells)
        if obj['mode']!=mode or obj['answer'] not in ('SAT','UNSAT'):
            raise ValueError('answer/mode inconsistent')
        obj['status']=obj.pop('answer')
        obj['wall_s']=elapsed
        obj['error']=''
        return obj
    except Exception as e:
        return dict(status='ERROR',wall_s=elapsed,error=str(e)[:350])

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--sources',required=True)
    p.add_argument('--binary',required=True)
    p.add_argument('--case-id',required=True)
    p.add_argument('--outdir',required=True)
    p.add_argument('--repeats',type=int,default=3)
    a=p.parse_args()
    assert a.repeats in (2,3)
    items=json.loads(Path(a.sources).read_text())
    target=[e for e in items if e['id']==a.case_id]
    assert len(target)==1,(a.case_id,[e['id'] for e in items])
    e=target[0]
    cnf=Path(e['path'])
    actual=hashlib.sha256(cnf.read_bytes()).hexdigest()
    assert actual==e['sha256']
    if e['id']==SOURCE_HASH:
        assert actual==SOURCE_SHA256,'Exact winning official CNF hash no longer matches'
    else:
        assert e['id']=='0c9da400944b002f90fd385d4fdab385'
    output=Path(a.outdir)
    output.mkdir(parents=True,exist_ok=True)
    data=[]
    with (output/'causal_raw.csv').open('w',newline='',encoding='utf8') as f:
        writer=csv.DictWriter(f,fieldnames=FIELDS);writer.writeheader()
        for repeat in range(a.repeats):
            seed=(7707000+repeat*527+int(a.case_id[:8],16))%2**32
            order=list(MODES)
            random.Random(78002026+int(a.case_id[:8],16)+repeat*733).shuffle(order)
            for mode in order:
                d=execute(a.binary,cnf,mode,seed)
                row={key:d.get(key,'') for key in FIELDS}
                row.update(case=a.case_id,source_sha256=actual,
                           repeat=repeat,seed=seed,mode=mode)
                if row['status'] not in ('SAT','TIMEOUT','ERROR'):
                    raise RuntimeError('Unexpected UNSAT contradiction or missing status')
                data.append(row)
                writer.writerow(row);f.flush()
                print('CAUSAL',a.case_id,'rep',repeat,'seed',seed,
                  mode,row['status'],f"{float(row['wall_s']):.4f}s",
                  'stage1',row.get('stage1',''), 'stage2',row.get('stage2',''),
                  'extend',row.get('extended',''),
                  'learned',row.get('learned_delta',''),
                  'threshold',row.get('threshold',''),
                  'offered',row.get('offered',''),
                  'short5',row.get('short5',''),
                  'error',str(row['error'])[:140],flush=True)
    by=defaultdict(list)
    for row in data:by[row['mode']].append(row)
    summary={}
    for mode in MODES:
        rows=by[mode]
        complete=[r for r in rows if r['status']=='SAT']
        costs=[float(r['wall_s']) if r['status']=='SAT' else 2*CAP for r in rows]
        summary[mode]=dict(repeats=len(rows),
          completed_SAT=len(complete),
          timeouts=sum(r['status']=='TIMEOUT' for r in rows),
          errors=sum(r['status']=='ERROR' for r in rows),
          local_par2_median_s=round(statistics.median(costs),5),
          times_s=[round(float(r['wall_s']),5) for r in rows],
          extended=[r['extended'] for r in rows],
          stage1=[r['stage1'] for r in rows],
          stage2=[r['stage2'] for r in rows],
          first_probe_us=[r['probe_us'] for r in rows],
          phase_hints=[r['hints'] for r in rows],
          clause_offers=[r['offered'] for r in rows],
          short_fraction=[r['short_fraction'] for r in rows],
          learned_delta=[r['learned_delta'] for r in rows],
          retained_threshold=[r['threshold'] for r in rows])
    ref=summary['orig_v76']['local_par2_median_s']
    v77=summary['orig_v77']['local_par2_median_s']
    summary_object=dict(
        purpose='Causal v7.6 preservation and v7.7 learner/policy slowdown ablation',
        case=a.case_id,sha256=actual,repeat_seed_formula='(7707000 + repeat*527 + int(gbd_hash[:8],16)) mod 2**32',
        original_versions_unmodified=True,case_previously_examined=True,
        old_CaDiCaL='arminbiere/cadical rel-3.0.1, rebuilt without edits',
        timeout_seconds=CAP,diagnostic_methods=list(MODES),
        aggregate=summary,relative_v76_over_v77=round(v77/max(ref,1e-8),4),
        limitations=[
          'Selected source is an exploratory regression case, not an unseen validation set.',
          'Use exact same original benchmark input SHA256 and original mode sources.',
          'Learner observes only clauses offered for external export, not all learned clauses.',
          'Replacing the original v7.6 gate with a forced gate or an observer is a diagnostic only.',
          'The copied A/B implementations require comparison against the untouched orig_v76 and orig_v77 in each repeat; they are not replacements.',
          'Times include GitHub hosted-runners process launch and DIMACS file reading.',
          'Three repeated timings per case do not establish population-level performance.',
          'SAT witnesses checked by original CaDiCaL native check_sat_model call.'
        ])
    (output/'causal_summary.json').write_text(json.dumps(summary_object,indent=2))
    lines=['# DRNAS v7.8 regression analysis: preserve actual v7.6',
        '', f'Official 2026 CNF ID: \`{a.case_id}\`',
        f'Source SHA256: \`{actual}\`',
        '', '| Diagnostic mode | Solved | PAR-2 median (s) | First checkpoint extended? |',
        '|---|---:|---:|---|']
    for mode in MODES:
        s=summary[mode]
        lines.append(f"| {mode} | {s['completed_SAT']}/{s['repeats']} | "
                     f"{s['local_par2_median_s']:.3f} | "
                     f"{', '.join(str(x) for x in s['extended'])} |")
    lines+=['',
       '## What is preserved',
       '- \`orig_v76\` calls untouched original \`run76(f,"adaptive_guided",seed)\`.',
       '- \`orig_v77\` calls untouched original \`solve77(f,"quality_guided",seed)\`.',
       '- Same CaDiCaL release, same \`add_phase_hints\` helper, same CNF, same seed per repeat.',
       '- Explicit controls independently vary (a) the external Learner observer and (b) the 256->768 conflict gate.',
       '- Inspect the raw CSV for clause-size distribution, redundant-clause deltas, extension choices and probe/resume times.',
       '',
       'This **does not claim** a causal explanation until A/B runs reproduce the original timing gap.',
       'All numbers here are targeted debugging, not an independent holdout.']
    report='\n'.join(lines)+'\n'
    (output/'causal_report.md').write_text(report)
    print(report,flush=True)
if __name__=='__main__':main()
