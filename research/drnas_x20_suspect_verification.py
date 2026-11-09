#!/usr/bin/env python3
"""X20 independent-solver follow-up for X19's unverified UNSAT claim.

DO NOT claim a certified UNSAT proof. This only obtains independent reference
solver statuses with a larger clock cap; SAT witnesses are replayed on the exact
original SHA. A solved SAT contradicting X19 UNSAT is an audit failure.
"""
from __future__ import annotations
import hashlib
import json
import os
import pathlib
import resource
import subprocess
import time
import signal

ROOT=pathlib.Path('mre_x19')
REPORT=pathlib.Path('mre_x20/suspect-independent-longcap.json')
SUSPECT_SHA='d677593932dd' # accepted only by full X19 manifest SHA check below
CAP_S=75.0

def need(ok,why):
    if not ok:raise RuntimeError('X20_SUSPECT_FAIL_CLOSED '+str(why))

def sha(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for chunk in iter(lambda:f.read(1048576),b''):h.update(chunk)
    return h.hexdigest()

def verify_sat(src,out):
    # Replay every original clause, not only the UNSAT-derived reduced CNF.
    from drnas_x18_selective import x11
    model={}
    for line in out.splitlines():
        if not line.startswith('v '):continue
        for lit in map(int,line[2:].split()):
            if not lit:continue
            v=abs(lit)
            need(v not in model or model[v]==(lit>0),'contradictory SAT model')
            model[v]=(lit>0)
    need(bool(model),'missing SAT assignment')
    x11.x9.x6.x4.base.cms.verify_model(src,model)

def run(label,cmd,src):
    start=time.perf_counter()
    p=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                       start_new_session=True,text=True,errors='replace')
    try:out,err=p.communicate(timeout=CAP_S);timed=False
    except subprocess.TimeoutExpired:
        timed=True
        try:os.killpg(p.pid,signal.SIGKILL)
        except ProcessLookupError:pass
        out,err=p.communicate()
    seconds=time.perf_counter()-start
    if timed:status='TIMEOUT'
    else:
        need(p.returncode in (10,20),
             f'{label} abnormal termination {p.returncode}: {err[-400:]}')
        status='SAT' if p.returncode==10 else 'UNSAT'
        need(('s SATISFIABLE' if status=='SAT' else 's UNSATISFIABLE') in out,
             'status text and exit code inconsistent')
        if status=='SAT':verify_sat(src,out)
    return dict(backend=label,status=status,elapsed_s=round(seconds,6),
                timeout_cap_s=CAP_S,sat_original_witness_verified=status=='SAT',
                UNSAT_independent_LRAT=False,return_code=p.returncode if not timed else None)

def main():
    mf=json.loads((ROOT/'manifest.json').read_text())
    need(mf['expected_trials']==144 and len(mf['cases'])==12,'X19 source registry invalid')
    cases=[c for c in mf['cases'] if c['sha256'].startswith(SUSPECT_SHA)]
    need(len(cases)==1,'X19 anomaly SHA missing/ambiguous')
    c=cases[0];src=ROOT/c['filename']
    need(src.is_file() and sha(src)==c['sha256'],'X19 original SHA mismatch')
    kissat=pathlib.Path('built/bin/kissat_4_0_4').resolve()
    need(kissat.is_file(),'pinned reference Kissat not restored')
    cadical=pathlib.Path('/usr/bin/cadical')
    need(cadical.is_file(),'pinned reference CaDiCaL not installed')
    report=dict(protocol='DRNAS-X20-SUSPECT-LONGCAP-CROSSSOLVER-v1',
                X19_original_sha256=c['sha256'],gbd=c['gbd'],
                previous_observation='X19 Asym2 and Select2 reported UNSAT within 12s but independent references timed out',
                independent_LRAT=False,reference_solver_agreement_only=True)
    results=[]
    for label,cmd in (
        ('kissat_4_0_4',[str(kissat),'--seed=146912',str(src.resolve())]),
        ('cadical_apt',[str(cadical),str(src.resolve())])
    ):
        r=run(label,cmd,src)
        results.append(r)
        report['results']=results
        REPORT.parent.mkdir(exist_ok=True,parents=True)
        REPORT.write_text(json.dumps(report,sort_keys=True,indent=2)+'\n')
        print('X20_SUSPECT_REFERENCE',json.dumps(r,sort_keys=True),flush=True)
        need(r['status']!='SAT','VERIFIED SAT WOULD CONTRADICT X19 UNSAT CLAIM')
    report['independent_UNSAT_agreement']=len(results)==2 and all(r['status']=='UNSAT' for r in results)
    report['still_unverified']=not report['independent_UNSAT_agreement']
    REPORT.write_text(json.dumps(report,sort_keys=True,indent=2)+'\n')
    print('X20_SUSPECT_FINAL',json.dumps(report,sort_keys=True),flush=True)

if __name__=='__main__':main()
