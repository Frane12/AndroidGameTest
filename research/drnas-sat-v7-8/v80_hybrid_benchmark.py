#!/usr/bin/env python3
"""v8.0 retrospective multi-instance hybrid gate test on pinned official CNFs.

All modes use the same compiled solver and the exact SAME phase
hint helper and seed for each repeat. 60-second process cap, raw logs
preserved. This is a diagnostic of a previously selected case, not a
new holdout performance win.
"""
import argparse,csv,hashlib,json,random,statistics,subprocess,time
from collections import defaultdict
from pathlib import Path

MODES=("orig_v76","orig_v77","ca_plain","old_gate_with_observer",\
       "new_gate_with_observer","hybrid_gate_with_observer")
SOURCE_HASH='4ae685a11b5cecca76dc3d463481ce92'
SOURCE_SHA256='16b09f959320357facb6345950ba5e6528299fc488c07e99f084446148755158'
CAP=60
FIELDS=('case','source_sha256','repeat','seed','mode','status','wall_s','error',
        'total_us','probe_us','extension_us','resume_us','stage1','stage2',
        'first_budget','second_budget','hints','extended','resumed',
        'active_pre','active_256','redundant_pre','redundant_256','learned_delta',
        'threshold','observer','offered','short5','short_fraction','gate_reason','vars','clauses')
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
    p.add_argument('--outdir',required=True)
    p.add_argument('--repeats',type=int,default=2)
    a=p.parse_args()
    if not 1<=a.repeats<=5: raise ValueError('repeats must be between 1 and 5')
    sources=json.loads(Path(a.sources).read_text())
    if len(sources)!=2 or len({x['id'] for x in sources})!=2:
        raise RuntimeError('Expected the two fixed original official 2026 CNFs in this shard')
    out=Path(a.outdir);out.mkdir(parents=True,exist_ok=True)
    results=[]
    with (out/'v80_raw.csv').open('w',newline='',encoding='utf8') as f:
        writer=csv.DictWriter(f,fieldnames=FIELDS);writer.writeheader()
        for item in sources:
            cnf=Path(item['path'])
            digest=hashlib.sha256(cnf.read_bytes()).hexdigest()
            if digest!=item['sha256']:
                raise RuntimeError('CNF SHA256 mismatch: '+item['id'])
            if item['id']==SOURCE_HASH and digest!=SOURCE_SHA256:
                raise RuntimeError('Known regression CNF hash mismatch')
            for rep in range(a.repeats):
                seed=(7707000+rep*527+int(item['id'][:8],16))%2**32
                order=list(MODES)
                random.Random(80002026+int(item['id'][:8],16)+rep*733).shuffle(order)
                block=[]
                for mode in order:
                    d=execute(a.binary,cnf,mode,seed)
                    row={key:d.get(key,'') for key in FIELDS}
                    row.update(case=item['id'],source_sha256=digest,repeat=rep,seed=seed,mode=mode)
                    if row['status'] not in ('SAT','UNSAT','TIMEOUT','ERROR'):
                        raise RuntimeError('Unrecognized solver result '+str(row['status']))
                    results.append(row);block.append(row)
                    writer.writerow(row);f.flush()
                    print('V80',item['id'],rep,seed,mode,row['status'],
                          f"{float(row['wall_s']):.4f}s",
                          'extended',row['extended'],'reason',row['gate_reason'],flush=True)
                solved={r['status'] for r in block if r['status'] in ('SAT','UNSAT')}
                if len(solved)>1:
                    raise RuntimeError('CONTRADICTORY SAT/UNSAT answers: '+item['id'])
    cases=[]
    for item in sources:
        case_rows=[r for r in results if r['case']==item['id']]
        methods={}
        for mode in MODES:
            rows=[r for r in case_rows if r['mode']==mode]
            scored=[float(r['wall_s']) if r['status'] in ('SAT','UNSAT')
                    else 2*CAP for r in rows]
            methods[mode]=dict(median_par2_s=round(statistics.median(scored),5),
                solved=sum(r['status'] in ('SAT','UNSAT') for r in rows),
                timeouts=sum(r['status']=='TIMEOUT' for r in rows),
                errors=sum(r['status']=='ERROR' for r in rows),
                extend=[r['extended'] for r in rows],
                reasons=[r['gate_reason'] for r in rows],
                seconds=[round(float(r['wall_s']),5) for r in rows])
        old=methods['orig_v76']['median_par2_s']
        hybrid=methods['hybrid_gate_with_observer']['median_par2_s']
        cases.append(dict(case=item['id'],sha256=item['sha256'],
            comparison='retrospective: these 2026 sources were previously examined',
            methods=methods,hybrid_over_v76=round(hybrid/max(old,1e-9),4),
            regression_over_25pct=hybrid>old*1.25))
    payload=dict(version='v8.0-experimental',protocol='predeclared gate, fixed SHA256, paired seeds',
        cases=cases,probe_cap_seconds=CAP,
        limitations=[
            'Not a blind holdout or general speedup claim.',
            'Official 2026 CNFs come from a previously tested frozen set.',
            'Exported-clause length is not LBD and not all learned clauses.',
            'Results include wall-clock startup and parsing cost.',
            'Only SAT witnesses are explicitly checked by the native checker; UNSAT is a solver return.',
            'Timed out processes count as 2*CAP for PAR2 and are never called solved.',
            'v7.6 and v7.7 source blobs are never edited.'])
    (out/'v80_summary.json').write_text(json.dumps(payload,indent=2))
    lines=['# DRNAS v8.0 Hybrid Gate: retrospective original 2026 CNFs','',
        'Modes compare identical original DIMACS SHA256, CaDiCaL 3.0.1, seed and frozen original versions.',
        'NOT a blind holdout. Regression flags do not mean the solver is incorrect.','']
    for case in cases:
        lines += ['## CNF '+case['case'], 'SHA256: '+case['sha256'],
            '| Mode | Solved | PAR-2 median (s) | Extension |',
            '|---|---:|---:|---|']
        for mode,m in case['methods'].items():
            lines.append(f"| {mode} | {m['solved']}/{a.repeats} | {m['median_par2_s']:.3f} | {','.join(map(str,m['extend']))} |")
        lines += [f"Hybrid / frozen v7.6 PAR-2 ratio: {case['hybrid_over_v76']:.3f}",
            f"Regression over 25%: {case['regression_over_25pct']}",'']
    (out/'v80_report.md').write_text('\n'.join(lines))
    print('\n'.join(lines),flush=True)
    if any(r['status']=='ERROR' for r in results):
        raise RuntimeError('One or more modes returned ERROR; inspect raw CSV')

if __name__=='__main__':
    main()
