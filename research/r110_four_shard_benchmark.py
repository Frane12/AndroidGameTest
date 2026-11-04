#!/usr/bin/env python3
"""R110: four independent SHA-frozen shards; six real SAT solving arms.

All attempts run on one pinned GitHub runner per shard; method order shuffled
by immutable input SHA, 2 repeats. R107C, R109, R110 each pay the complete
wall-clock preprocessing cost separately on EACH repeat. Timeouts PAR2=24 s.
"""
import argparse,csv,hashlib,json,lzma,pathlib,random,subprocess,time,urllib.request
import sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import r106_verify_solver as checker

MODES=('cadical','kissat','cryptominisat','drnas_r107c','drnas_r109','drnas_r110')
NATIVE=('drnas_r107c','drnas_r109','drnas_r110')
CAP=12.
REPEATS=2

def inputs(root,shard):
    full=json.loads(pathlib.Path('research/r110_frozen_holdout_2025.json').read_text())
    if full['fixed_timeout_seconds']!=CAP or full['repeats']!=REPEATS:
        raise RuntimeError('R110_FAIL_CLOSED benchmark settings changed')
    assert len(full['shards'])==4 and all(len(s)==4 for s in full['shards'])
    cases=full['shards'][shard]
    original=root/'sources';original.mkdir(parents=True,exist_ok=True)
    for case in cases:
        assert case['shard']==shard and case['bytes']<=24*1024*1024
        request=urllib.request.Request(case['url'],headers={'User-Agent':'DRNAS-R110/1.0 benchmark'})
        with urllib.request.urlopen(request,timeout=90) as stream:
            blob=stream.read(20*1024*1024+1)
        if len(blob)>20*1024*1024:raise RuntimeError('R110 compressed input exceeds cap')
        data=lzma.decompress(blob,memlimit=128*1024*1024)
        if len(data)!=case['bytes'] or hashlib.sha256(data).hexdigest()!=case['sha256']:
            raise RuntimeError('R110_FAIL_CLOSED wrong SHA/size '+case['name'])
        (original/case['name']).write_bytes(data)
        print('R110_SHA_VERIFIED',shard,case['name'],case['sha256'],len(data),flush=True)
    (root/'frozen-manifest.json').write_text(json.dumps(
        dict(shard=shard,cases=cases,cap=CAP,repeats=REPEATS,
             methods=MODES,preselected_before_execution=True),indent=2)+'\n')
    return cases

def preprocess(binary,source,dest,evidence,expected,cap):
    begin=time.perf_counter()
    try:
        proc=subprocess.run([binary,str(source),str(dest),str(evidence)],
                            capture_output=True,text=True,errors='replace',
                            timeout=max(.01,cap))
    except subprocess.TimeoutExpired:
        return dict(status='TIMEOUT',prep_s=cap,info=None,error='preprocessor timeout')
    elapsed=time.perf_counter()-begin
    if proc.returncode!=0:
        return dict(status='UNSUPPORTED',prep_s=elapsed,info=None,
                    error=(proc.stderr or proc.stdout)[-250:])
    try:
        diag=json.loads(evidence.read_text())
    except (ValueError,OSError) as exc:
        return dict(status='UNSUPPORTED',prep_s=elapsed,info=None,
                    error='unreadable evidence '+str(exc))
    if 'source_xors' not in diag or 'gf2_unsat' not in diag:
        raise RuntimeError('R110_FAIL_CLOSED missing evidence fields')
    if expected=='SAT' and diag['gf2_unsat']:
        raise RuntimeError('R110_FAIL_CLOSED UNSAT proof for officially SAT input')
    if not diag['gf2_unsat'] and source.read_bytes()!=dest.read_bytes():
        raise RuntimeError('R110_FAIL_CLOSED modified CNF without proof')
    if diag['gf2_unsat'] and checker.cnf_clauses(dest)[-1]!=():
        raise RuntimeError('R110_FAIL_CLOSED no empty clause in proof output')
    return dict(status='OK',prep_s=elapsed,info=diag,error='')

def solve(executable,source,original,expected,limit):
    if limit<=0:
        return dict(status='TIMEOUT',solver_s=0.,witness=False)
    start=time.perf_counter()
    try:
        p=subprocess.run([str(executable),str(source)],capture_output=True,
                         text=True,errors='replace',timeout=max(.01,limit))
    except subprocess.TimeoutExpired:
        return dict(status='TIMEOUT',solver_s=limit,witness=False)
    elapsed=time.perf_counter()-start
    status=checker.status(p.stdout,p.returncode)
    if status!=expected:
        raise RuntimeError(f'R110_FAIL_CLOSED solver status {status} contradicts '
                           f'known competition label {expected} on {original}')
    witness=False
    if status=='SAT':
        witness=checker.model_valid(p.stdout,checker.cnf_clauses(original))
        if not witness:
            raise RuntimeError('R110_FAIL_CLOSED unverified SAT model '+str(executable))
    if elapsed>limit:
        status='TIMEOUT'
    return dict(status=status,solver_s=elapsed,witness=witness)

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--shard',type=int,required=True,choices=range(4))
    p.add_argument('--out',required=True)
    for name in ('cadical','kissat','cms','r107c','r109','r110'):
        p.add_argument('--'+name,required=True)
    a=p.parse_args()
    root=pathlib.Path(a.out);root.mkdir(parents=True,exist_ok=True)
    cases=inputs(root,a.shard)
    binaries=dict(zip(MODES,(a.cadical,a.kissat,a.cms,a.r107c,a.r109,a.r110)))
    rows=[]
    for case in cases:
        source=root/'sources'/case['name']
        baseline_hash=case['sha256']
        for rep in range(REPEATS):
            order=list(MODES)
            random.Random(case['sha256']+str(rep)+'R110_FROZEN').shuffle(order)
            diagnostics={}
            for mode in order:
                prep_s=0.;diag=None;error=''
                dest=source
                pre_status='OK'
                if mode in NATIVE:
                    dest=root/'outputs'/mode/str(rep)/case['name']
                    dest.parent.mkdir(parents=True,exist_ok=True)
                    evidence=root/'evidence'/mode/str(rep)/(case['name']+'.json')
                    evidence.parent.mkdir(parents=True,exist_ok=True)
                    result=preprocess(binaries[mode],source,dest,evidence,
                                      case['status'],CAP)
                    pre_status=result['status'];prep_s=result['prep_s']
                    diag=result['info'];error=result['error']
                    if diag is not None:
                        diagnostics[mode]=diag
                if pre_status in ('UNSUPPORTED','TIMEOUT'):
                    result_status=pre_status;solver_s=0.;verified=False
                elif prep_s>=CAP:
                    result_status='TIMEOUT';solver_s=0.;verified=False
                else:
                    executable=(a.cadical if mode in NATIVE else binaries[mode])
                    attempt=solve(executable,dest,source,case['status'],CAP-prep_s)
                    result_status=attempt['status']
                    solver_s=attempt['solver_s'];verified=attempt['witness']
                total=prep_s+solver_s
                # Unsupported is a separate failure, penalized as unsolved in PAR2.
                row=dict(shard=a.shard,formula=case['name'],
                   family=case['family'],sha256=baseline_hash,
                   expected=case['status'],rep=rep,mode=mode,status=result_status,
                   prep_s=round(prep_s,6),solver_s=round(solver_s,6),
                   total_s=round(total,6),
                   PAR2_s=round(24. if result_status in ('TIMEOUT','UNSUPPORTED') else total,6),
                   xor_rows=diag.get('source_xors',None) if diag else None,
                   baseline_xors=diag.get('baseline_xors',None) if diag else None,
                   new_xors=diag.get('new_xors',None) if diag else None,
                   gf2_unsat=diag.get('gf2_unsat',None) if diag else None,
                   selector_enabled=diag.get('selector_enabled',None) if diag else None,
                   selector_gate=diag.get('gate',None) if diag else None,
                   truncated=diag.get('selector_truncated',None) if diag else None,
                   verified_sat=verified,error=error)
                rows.append(row)
                print('R110_TRIAL',json.dumps({k:row[k] for k in
                  ('shard','formula','rep','mode','status','total_s','prep_s',
                   'new_xors','selector_gate','error')}),flush=True)
            if 'drnas_r107c' in diagnostics:
                ref=diagnostics['drnas_r107c']
                for mode in ('drnas_r109','drnas_r110'):
                    if mode not in diagnostics:continue
                    obs=diagnostics[mode]
                    if (obs['baseline_xors']!=ref['source_xors']
                            or obs['source_xors']<ref['source_xors']):
                        raise RuntimeError('R110_FAIL_CLOSED loss of baseline XOR '+case['name'])
                    if ref['gf2_unsat'] and not obs['gf2_unsat']:
                        raise RuntimeError('R110_FAIL_CLOSED lost previously proven UNSAT')
            if hashlib.sha256(source.read_bytes()).hexdigest()!=baseline_hash:
                raise RuntimeError('R110_FAIL_CLOSED original source mutated')
        print('R110_CASE',case['name'],json.dumps({
            m:[(r['status'],r['total_s'],r['prep_s'])
                for r in rows if r['formula']==case['name'] and r['mode']==m]
            for m in MODES}),flush=True)
    if len(rows)!=4*6*REPEATS:
        raise RuntimeError('R110_FAIL_CLOSED missing paired measurements')
    with (root/'paired.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]))
        writer.writeheader();writer.writerows(rows)
    totals={}
    for mode in MODES:
        selected=[r for r in rows if r['mode']==mode]
        totals[mode]=dict(trials=len(selected),
            solved=sum(r['status'] in ('SAT','UNSAT') for r in selected),
            unsupported=sum(r['status']=='UNSUPPORTED' for r in selected),
            timed_out=sum(r['status']=='TIMEOUT' for r in selected),
            verified_sat=sum(r['verified_sat'] for r in selected),
            PAR2_s=round(sum(r['PAR2_s'] for r in selected),6),
            preprocessor_s=round(sum(r['prep_s'] for r in selected),6))
    by_formula={}
    for case in cases:
        subset=[r for r in rows if r['formula']==case['name']]
        by_formula[case['name']]={mode:dict(
            solved=sum(r['status'] in ('SAT','UNSAT') for r in subset if r['mode']==mode),
            PAR2_s=round(sum(r['PAR2_s'] for r in subset if r['mode']==mode),6))
            for mode in MODES}
    summary=dict(protocol='R110-FROZEN-4-PARALLEL-REAL-SAT2025-CROSS-SOLVER',
        shard=a.shard,real_cases=len(cases),trials=len(rows),cap_s=CAP,
        repeats=REPEATS,totals=totals,by_formula=by_formula,
        limitations=[
          'Originals are public 2025 competition samples, excluded from R106-R109, not proven globally unused or official 2026 blind holdout',
          'No result-dependent formula selection: sixteen names and original SHA256 frozen before runs',
          'R107C/R109/R110 are proven root-GF2 preprocessors followed by CaDiCaL; not complete CDCL<->GF2 integration',
          'External UNSAT outcomes are solver reported, not independently proof audited',
          'PAR2 doubles the 12-second timeout; it is not a real observed 24-second solve time',
          'All three DRNAS preprocessors independently timed per repetition; SHA verified original inputs',
          'Failures to process input reported as unsupported, penalized as unsolved'])
    (root/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print('R110_SHARD_COMPLETE_AUDIT',json.dumps(summary),flush=True)
if __name__=='__main__':main()
