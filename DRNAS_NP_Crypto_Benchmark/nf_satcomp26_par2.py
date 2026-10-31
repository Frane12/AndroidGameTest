#!/usr/bin/env python3
"""A reproducible research miniature of SAT Competition 2026 scoring.

Uses actual official SATCompetition'26 Main selected GBD hashes, NEVER a
substitute file if an official download fails. Crucially, this is NOT a
competition-hosted result or official PAR-2 score: we cap each run at 12s
instead of the official 5000s and use different hardware.
"""
import csv,hashlib,json,random,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent
FOLDER=ROOT/'satcomp26_official'
POLICY=ROOT/'satcomp26_frozen_v100_policy.txt'
BIN=ROOT/'native_v100/drnas_nf100'
OUT=ROOT/'satcomp26_research_results'
CAP_SEC=12.
REPEATS=2
ARMS=('base','auto')

def csv_write(path,rows):
    with path.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]))
        w.writeheader();w.writerows(rows)

def run_solver(path,mode):
    command=[str(BIN),'--input',str(path),'--mode',mode,
             '--budget-ms',str(int(CAP_SEC*1000))]
    if mode=='auto':command+=['--policy',str(POLICY)]
    start=time.perf_counter()
    try:
        p=subprocess.run(command,capture_output=True,text=True,timeout=CAP_SEC+5)
        elapsed=time.perf_counter()-start
    except subprocess.TimeoutExpired:
        elapsed=time.perf_counter()-start
        return dict(status='EXTERNAL_TIMEOUT',total_sec=elapsed,
                    native_total_sec='',route='subprocess-timeout',
                    selected='unknown',phase_count='',phase_ms='')
    if p.returncode:
        return dict(status='ERROR',total_sec=elapsed,native_total_sec='',
                   route=f'exit-{p.returncode}: '+p.stderr[-180:].replace('\n',' '),
                   selected='unknown',phase_count='',phase_ms='')
    try:
        d=json.loads(p.stdout.strip())
    except ValueError:
        return dict(status='ERROR',total_sec=elapsed,native_total_sec='',
                   route='bad-json: '+p.stdout[:100],selected='unknown',
                   phase_count='',phase_ms='')
    status=d.get('status','ERROR')
    if status not in ('SAT','UNSAT','UNKNOWN'):status='ERROR'
    if status=='SAT' and d.get('witness_valid') is not True:
        raise AssertionError('Wrong SAT witness on official CNF '+str(path))
    return dict(status=status,total_sec=elapsed,
            native_total_sec=float(d['total_ms'])/1000,
            route=d['route'],selected=d.get('selected','unknown'),
            phase_count=d.get('phase_count',0),
            phase_ms=d.get('phase_ms',0))

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    with (FOLDER/'source_manifest.csv').open(encoding='utf-8') as f:
        manifest=list(csv.DictReader(f))
    assert len(manifest)==24
    cases=[r for r in manifest if r['status']=='READY']
    if not cases:raise RuntimeError('No official SAT Competition 2026 CNF was acquired')
    random.Random(2026103116).shuffle(cases)
    timings=[]
    for i,c in enumerate(cases):
        source=FOLDER/(f"sc26_{int(c['index']):03d}.cnf")
        assert hashlib.sha256(source.read_bytes()).hexdigest()==c['dimacs_sha256']
        for repeat in range(REPEATS):
            order=ARMS[(i+repeat)%2:]+ARMS[:(i+repeat)%2]
            results={}
            for mode in order:
                r=run_solver(source,mode)
                results[mode]=r
                timings.append(dict(gbd_id=c['gbd_id'],index=c['index'],rep=repeat,
                    mode=mode,source_sha256=c['dimacs_sha256'],
                    status=r['status'],wall_sec=round(r['total_sec'],6),
                    native_sec=r['native_total_sec'],
                    route=r['route'],selected=r['selected'],
                    phase_count=r['phase_count'],phase_ms=r['phase_ms']))
            base,auto=results['base'],results['auto']
            if base['status'] in ('SAT','UNSAT') and auto['status'] in ('SAT','UNSAT'):
                if base['status']!=auto['status']:
                    raise AssertionError(f'CONTRADICTORY solver outcomes on official CNF {c["gbd_id"]}: {base["status"]} vs {auto["status"]}')
        print('MEASURED OFFICIAL',i+1,'/',len(cases),c['gbd_id'],flush=True)
    csv_write(OUT/'raw_official_timings.csv',timings)
    pivot={(r['gbd_id'],r['rep'],r['mode']):r for r in timings}
    total=[r for r in manifest if r['status']!='READY']
    summary=[]
    for mode in ARMS:
        measured=[r for r in timings if r['mode']==mode]
        completed=[r for r in measured if r['status'] in ('SAT','UNSAT')]
        costs=[float(r['wall_sec']) if r['status'] in ('SAT','UNSAT') else 2*CAP_SEC
               for r in measured]
        par2=sum(costs)/len(costs)
        summary.append(dict(method=mode,
             official_list_size=400,
             randomly_preselected=24,
             downloaded_official_cnf_count=len(cases),
             unavailable_or_oversized_count=len(total),
             repetitions=REPEATS, cap_sec=CAP_SEC,
             completed_runs=len(completed),all_runs=len(measured),
             sat_runs=sum(r['status']=='SAT' for r in measured),
             unsat_runs=sum(r['status']=='UNSAT' for r in measured),
             unknown_runs=sum(r['status']=='UNKNOWN' for r in measured),
             error_runs=sum(r['status'] in ('ERROR','EXTERNAL_TIMEOUT') for r in measured),
             local_PAR2_seconds=round(par2,6),
             local_PAR2_sum_seconds=round(sum(costs),5)))
    csv_write(OUT/'scores.csv',summary)
    s={r['method']:r for r in summary}
    ratio=100*(1-s['auto']['local_PAR2_seconds']/s['base']['local_PAR2_seconds'])
    pair_gain=[]
    for c in cases:
        for rep in range(REPEATS):
            a=pivot[(c['gbd_id'],rep,'base')]
            b=pivot[(c['gbd_id'],rep,'auto')]
            if a['status'] in ('SAT','UNSAT') and b['status']==a['status']:
                pair_gain.append((a['wall_sec'],b['wall_sec']))
    (OUT/'methodological_note.json').write_text(json.dumps(dict(
       official_source='SAT Competition 2026 Main 400-hash published URI index',
       official_uri_source='https://github.com/satcompetition/2026/blob/main/downloads/track_main_2026.uri',
       subset='deterministic seed 20261031 selects 24 before any solver or download; inaccessible instances remain in manifest, never replaced',
       baseline='CaDiCaL via native DRNAS v1.0 executable, no phase hints',
       selected='identical CaDiCaL build and parser, frozen v1.0 majority polarity routing without retraining',
       score='PAR-2: each unsolved native run contributes twice the 12-second research cap',
       official_conditions=False,
       official_competition_timeout_seconds=5000,
       research_timeout_seconds=CAP_SEC,
       official_hardware=False,
       official_unsat_proof_checked=False,
       certificates_note='SAT models verified internally. UNSAT claims from CaDiCaL but no official UNSAT proof checking performed.',
       unavailable_selected_files=len(total),
       local_PAR2_relative_gain_percent=round(ratio,5),
       matched_completed_runs=len(pair_gain),
       median_paired_speed_gain_percent=(
         round(__import__('statistics').median((a-b)/a*100 for a,b in pair_gain),5)
         if pair_gain else None),
       limitation='LOCAL unofficial short-cap, size-limited subset; official 5000s rankings cannot be inferred',
       policy_sha256=hashlib.sha256(POLICY.read_bytes()).hexdigest()),indent=2))
    print('FINAL OFFICIAL-INSTANCE RESEARCH SCORES',flush=True)
    for r in summary:print(json.dumps(r),flush=True)
    print('LOCAL PAR2 RELATIVE IMPROVEMENT PERCENT:',round(ratio,4),flush=True)
    print('NOT OFFICIAL SAT COMPETITION SCORE; NO UNSAT PROOF VERIFICATION.',flush=True)

if __name__=='__main__':main()
