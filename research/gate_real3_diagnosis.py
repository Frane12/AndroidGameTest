#!/usr/bin/env python3
"""Post-hoc REAL3 diagnosis, NOT a blind/generalization benchmark.
Original REAL36 inputs and compiled binaries are reused byte-for-byte.
Independent fresh processes at caps 5 and 30; deadline-dependent gates need not
follow identical prefixes at different caps. Solver/proof costs stay separate.
No solver code, settings other than --time, learnt policy or input CNF is changed.
"""
from __future__ import annotations
import argparse, collections, hashlib, json, os, signal, statistics, subprocess, time
from pathlib import Path
import gate_real36 as B

CAPS=(5.0,30.0)
REPS=3
DEST=Path('real3_frozen')
TARGETS=(
 ('Break_unsat_06_07.xml.cnf.xz','8c94b7be135467462330cd4819c1d2acdbabd2c7f9290a6c53409186021a4bbf'),
 ('mrpp_4x4#12_12.cnf.xz','506d2496b260896d510a9fbbb4cd2f332478a49cd7efb9548db6b7830b10c2f8'),
 ('simon-r22-1.sanitized.cnf.xz','41c927b38e1217cfe82d77ccb92441a4b799f0c50935a0141845b0f1dd4ba42c'),
)
FIELDS=('conflicts','decisions','propagations','learnt','reduce_removed','restarts',
        'depth_probes','depth_conflicts','controller_probed_decisions',
        'controller_feedback','controller_positive','probe_seconds',
        'x45_probe_rounds','x45_interventions','x45_online_updates',
        'backdoor_checks','backdoor_sat','backdoor_unsat','backdoor_nogoods')

def dump(p,obj):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(obj,sort_keys=True,indent=2)+'\n')

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def freeze():
    original=json.loads((B.ROOT/'manifest.json').read_text())
    prior=json.loads((B.ROOT/'protocol.json').read_text())
    assert sha(B.ROOT/'manifest.json')==prior['manifest_sha256']
    selected=[]
    for idx,(name,digest) in enumerate(TARGETS):
        matches=[s for s in original if s['filename']==name and s['sha256']==digest]
        if len(matches)!=1: raise RuntimeError('Missing exact original source '+name)
        src=dict(matches[0]);src['diagnostic_id']=idx
        if sha(src['path'])!=digest: raise RuntimeError('Input checksum changed')
        n,clauses=B.parse_cnf(Path(src['path']).read_bytes())
        if (n,len(clauses))!=(src['nvars'],src['nclauses']):raise RuntimeError('Header mismatch')
        selected.append(src)
    binaries={a:{'path':p,'mode':m,'sha256':sha(p)} for a,(p,m) in B.ARMS.items()}
    dump(DEST/'manifest.json',selected)
    protocol={'design':'POST_HOC_DIAGNOSIS_NOT_UNSEEN_EVALUATION',
      'input_source_run':43387395060,'binary_source_run':43386621130,
      'caps_s':CAPS,'repetitions':REPS,'arms':binaries,'sources':3,'runs':126,
      'jobs':9,'manifest_sha256':sha(DEST/'manifest.json'),
      'prior_manifest_sha256':prior['manifest_sha256'],
      'same_logical_cpu_within_each_formula_repeat':True,
      'timing':'Process launch + GNU time wrapper + solver + parsing; verification separate',
      'deadline_caveat':'5s and 30s are independent runs; relative-deadline gates can change trajectories',
      'memory_caveat':'Native memories reset per process; no cross-formula training',
      'unsat_evidence':'Fresh reference-instance certificate checked by drat-trim, not a native DRNAS proof'}
    dump(DEST/'protocol.json',protocol)
    B.emit('REAL3_FROZEN',protocol)

def timed_run(src,arm,cap,logs):
    binary,mode=B.ARMS[arm]
    cmd=([binary,src['path'],'--mode',mode,'--time',str(cap),'--stats'] if mode else [binary,'-q',src['path']])
    paths={k:logs/(arm+'_'+str(int(cap))+'.'+k) for k in ('out','err','usage')}
    cmd=['/usr/bin/time','-f','%U %S %M','-o',str(paths['usage'])]+cmd
    start=time.perf_counter();expired=False
    with paths['out'].open('w') as out, paths['err'].open('w') as err:
        p=subprocess.Popen(cmd,stdout=out,stderr=err,start_new_session=True)
        try:p.wait(timeout=cap+0.25)
        except subprocess.TimeoutExpired:
            expired=True
            try:os.killpg(p.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            p.wait()
    wall=time.perf_counter()-start
    stdout=paths['out'].read_text(errors='replace');stderr=paths['err'].read_text(errors='replace')
    stats={};gates={};usage=None
    for line in stderr.splitlines():
        if ' ' not in line:continue
        prefix,body=line.split(' ',1)
        if prefix.endswith(('_STATS','_GATE')):
            try:obj=json.loads(body)
            except json.JSONDecodeError:continue
            if prefix.endswith('_STATS'):stats=obj
            else:gates[prefix]=obj
    if paths['usage'].exists():
        for line in paths['usage'].read_text().splitlines():
            bits=line.split()
            if len(bits)==3:
                try:usage={'user_cpu_s':float(bits[0]),'system_cpu_s':float(bits[1]),'maxrss_kib':int(bits[2])}
                except ValueError:pass
    reported='TIMEOUT' if expired else 'UNKNOWN';check=0.0
    if not expired and p.returncode==10:
        n,clauses=B.parse_cnf(Path(src['path']).read_bytes())
        tick=time.perf_counter();valid=B.verify_sat(stdout,n,clauses);check=time.perf_counter()-tick
        reported='SAT_WITNESS_VERIFIED' if valid else 'WRONG_SAT'
    elif not expired and p.returncode==20:reported='UNSAT_UNVERIFIED'
    elif not expired and p.returncode!=0:reported='SOLVER_ERROR'
    return {'arm':arm,'cap_s':cap,'reported':reported,'returncode':p.returncode,
      'process_wall_s':wall,'within_cap':wall<=cap,'witness_check_s':check,
      'stats':stats,'gates':gates,'usage':usage,'raw_output_prefix':str(logs/(arm+'_'+str(int(cap))))}

def finalize(row,cert,has_sat):
    row['incorrect']=row['reported']=='WRONG_SAT' or (has_sat and row['reported']=='UNSAT_UNVERIFIED')
    row['verified_answer']=row['reported']=='SAT_WITNESS_VERIFIED' or (row['reported']=='UNSAT_UNVERIFIED' and cert.get('verified',False))
    row['accepted']=row['verified_answer'] and row['within_cap'] and not row['incorrect']
    row['PAR2_s']=row['process_wall_s'] if row['accepted'] else 2*row['cap_s']
    row['evidence']='SAT_WITNESS' if row['reported']=='SAT_WITNESS_VERIFIED' else 'REFERENCE_INSTANCE_UNSAT_CERTIFICATE' if row['verified_answer'] else 'NONE'
    return row

def run_shard(idx):
    if idx not in range(9):raise ValueError('Invalid shard')
    protocol=json.loads((DEST/'protocol.json').read_text())
    if sha(DEST/'manifest.json')!=protocol['manifest_sha256']:raise RuntimeError('Manifest drift')
    case,rep=divmod(idx,REPS);src=json.loads((DEST/'manifest.json').read_text())[case]
    if sha(src['path'])!=src['sha256']:raise RuntimeError('Source drift')
    for a,(p,m) in B.ARMS.items():
        if sha(p)!=protocol['arms'][a]['sha256']:raise RuntimeError('Binary drift '+a)
    out=Path('real3_stage')/str(idx);logs=out/'logs';logs.mkdir(parents=True,exist_ok=True)
    jobs=[(cap,arm) for cap in CAPS for arm in B.ARMS]
    if (case+rep)%2:jobs.reverse()
    shift=(case+rep*3)%len(jobs);jobs=jobs[shift:]+jobs[:shift]
    rows=[]
    for cap,arm in jobs:
        row=timed_run(src,arm,cap,logs)
        row.update(id=case,original_id=src['id'],sha256=src['sha256'],filename=src['filename'],family=src['family'],rep=rep,shard=idx)
        rows.append(row)
        B.emit('REAL3_TRIAL',row)
        dump(out/'partial.json',rows)
    cert=B.certify_unsat(src['path']) if any(r['reported']=='UNSAT_UNVERIFIED' for r in rows) else {'verified':False,'audit_wall_s':0.0}
    cert['sha256']=src['sha256'];has_sat=any(r['reported']=='SAT_WITNESS_VERIFIED' for r in rows)
    if cert['verified'] and has_sat:raise RuntimeError('Proof / SAT witness contradiction')
    for row in rows:finalize(row,cert,has_sat)
    dump(out/'certificate.json',cert)
    (out/'trials.jsonl').write_text(''.join(json.dumps(r,sort_keys=True)+'\n' for r in rows))
    report={'shard':idx,'rows':len(rows),'manifest_sha256':protocol['manifest_sha256'],
      'cpu_affinity':sorted(os.sched_getaffinity(0)),'cpu_model':next((s for s in Path('/proc/cpuinfo').read_text().splitlines() if s.startswith('model name')),''),
      'incorrect':sum(r['incorrect'] for r in rows),'solver_errors':sum(r['reported']=='SOLVER_ERROR' for r in rows)}
    dump(out/'report.json',report);B.emit('REAL3_SHARD_FINAL',report)
    if report['incorrect'] or report['solver_errors']:raise RuntimeError('Answer/error audit failed')

def summarize(rows):
    return {'attempts':len(rows),'accepted':sum(r['accepted'] for r in rows),
      'verified_SAT':sum(r['accepted'] and r['reported']=='SAT_WITNESS_VERIFIED' for r in rows),
      'reference_certified_UNSAT':sum(r['accepted'] and r['reported']=='UNSAT_UNVERIFIED' for r in rows),
      'median_process_wall_s':statistics.median(r['process_wall_s'] for r in rows),
      'PAR2_sum_s':sum(r['PAR2_s'] for r in rows),
      'stats_median':{k:statistics.median(r['stats'].get(k,0) for r in rows) for k in FIELDS},
      'maxrss_median_kib':statistics.median(r['usage']['maxrss_kib'] for r in rows if r['usage']) if any(r['usage'] for r in rows) else None}

def finish():
    protocol=json.loads((DEST/'protocol.json').read_text());manifest=json.loads((DEST/'manifest.json').read_text())
    if sha(DEST/'manifest.json')!=protocol['manifest_sha256']:raise RuntimeError('Manifest changed')
    rows=[];certs=[];env=[]
    for idx in range(9):
        path=Path('real3_downloads')/f'gate-real3-{idx}'
        report=json.loads((path/'report.json').read_text())
        if report['manifest_sha256']!=protocol['manifest_sha256'] or report['rows']!=14:raise RuntimeError('Shard mismatch')
        if len(report['cpu_affinity'])!=1:raise RuntimeError('Not single logical CPU')
        env.append(report);certs.append(json.loads((path/'certificate.json').read_text()))
        rows.extend(json.loads(s) for s in (path/'trials.jsonl').read_text().splitlines())
    expected={(s['sha256'],rep,cap,arm) for s in manifest for rep in range(REPS) for cap in CAPS for arm in B.ARMS}
    actual={(r['sha256'],r['rep'],r['cap_s'],r['arm']) for r in rows}
    if len(rows)!=len(expected) or actual!=expected:raise RuntimeError('Missing or duplicate trials')
    for r in rows:
        src=manifest[r['id']]
        if src['sha256']!=r['sha256'] or src['filename']!=r['filename']:raise RuntimeError('Metadata mismatch')
        recompute=r['process_wall_s'] if r['accepted'] else 2*r['cap_s']
        if abs(recompute-r['PAR2_s'])>1e-8:raise RuntimeError('PAR2 mismatch')
    families={s['filename']:{str(int(cap)):{a:summarize([r for r in rows if r['sha256']==s['sha256'] and r['cap_s']==cap and r['arm']==a]) for a in B.ARMS} for cap in CAPS} for s in manifest}
    report={'status':'COMPLETE','protocol':protocol,'results':families,'environments':env,'certificates':certs,
      'incorrect':sum(r['incorrect'] for r in rows),'solver_errors':sum(r['reported']=='SOLVER_ERROR' for r in rows),
      'limitations':['Three deliberately selected diagnostic formulas are not a new blind benchmark.',
        'Fresh processes at each deadline; gate time budgets may change trajectories across deadlines.',
        'Reference certificate proves the instance, not correctness of native UNSAT reasoning.',
        'Search counters from timeouts are censored; smaller counters alone do not prove efficient search.']}
    out=Path('real3_final');out.mkdir(exist_ok=True)
    dump(out/'report.json',report)
    (out/'paired_trials.jsonl').write_text(''.join(json.dumps(r,sort_keys=True)+'\n' for r in sorted(rows,key=lambda r:(r['id'],r['rep'],r['cap_s'],r['arm']))))
    lines=['# GATE REAL3: unchanged native binaries, 5s vs 30s diagnosis','',
      'Post-hoc diagnostic subset: Break UNSAT, MRPP UNSAT, SIMON SAT. Three repeats. No source or solver changes.','',
      '| Formula | Cap | Arm | Verified/3 | Median wall seconds | PAR2 sum | Median conflicts | Median probe seconds |',
      '|---|---:|---|---:|---:|---:|---:|---:|']
    for name,caps in families.items():
        for cap,arms in caps.items():
            for arm,v in arms.items():
                lines.append(f"| {name} | {cap} | {arm} | {v['accepted']}/3 | {v['median_process_wall_s']:.6f} | {v['PAR2_sum_s']:.5f} | {v['stats_median']['conflicts']} | {v['stats_median']['probe_seconds']:.6f} |")
    lines+=['','Counter and gate telemetry plus raw process logs are included in the shard artifacts.','']+report['limitations']
    text='\n'.join(lines)+'\n';(out/'summary.md').write_text(text)
    if os.getenv('GITHUB_STEP_SUMMARY'):Path(os.environ['GITHUB_STEP_SUMMARY']).write_text(text)
    B.emit('REAL3_FINAL',report)
    if report['incorrect'] or report['solver_errors']:raise RuntimeError('Correctness audit failed')

def selftest():
    B.selftest()
    for cap in CAPS:
        base={'reported':'UNSAT_UNVERIFIED','within_cap':True,'process_wall_s':0.1,'cap_s':cap}
        assert finalize(dict(base),{'verified':False},False)['PAR2_s']==2*cap
        assert finalize(dict(base),{'verified':True},False)['accepted']
        assert not finalize(dict(base),{'verified':True},True)['accepted']
    assert len(TARGETS)*len(CAPS)*REPS*len(B.ARMS)==126
    B.emit('REAL3_SELFTEST_PASS',{'deadline_accounting':True,'unverified_unsat_rejected':True,'runs':126})

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['freeze','shard','finish','selftest']);p.add_argument('--shard',type=int,default=0);a=p.parse_args()
    if a.stage=='freeze':freeze()
    elif a.stage=='shard':run_shard(a.shard)
    elif a.stage=='finish':finish()
    else:selftest()
