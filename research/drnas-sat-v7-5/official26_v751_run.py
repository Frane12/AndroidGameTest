#!/usr/bin/env python3
"""SAT Competition 2026 original-instance, extended-60s, EXACT DRNAS V7.5.1.

Runs all EIGHT matched controls unchanged from SATLIB v7.5.1:
plain, majority, split_plain256/1024, guided256/1024, random256/1024.
Each mode: same CaDiCaL 3.0.1 / source / flags, two order-shuffled repeats.
Local PAR-2 has 120s timeout penalty; not the official 5000s score.
"""
import argparse,csv,hashlib,json,random,time
from pathlib import Path
import benchmark as v751
FIELDS=v751.FIELDS
METHODS=v751.METHODS

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--binary',required=True)
    p.add_argument('--sources',required=True)
    p.add_argument('--outdir',required=True)
    p.add_argument('--timeout',type=float,default=60.)
    p.add_argument('--repeats',type=int,default=2)
    a=p.parse_args()
    assert a.timeout==60. and a.repeats==2
    sources=json.loads(Path(a.sources).read_text())
    assert len(sources)==2
    output=Path(a.outdir);output.mkdir(parents=True,exist_ok=True)
    rows=[];known={}
    with (output/'raw.csv').open('w',newline='',encoding='utf8') as f:
        writer=csv.DictWriter(f,fieldnames=FIELDS)
        writer.writeheader()
        for i,c in enumerate(sources):
            cnf=Path(c['path'])
            actual=hashlib.sha256(cnf.read_bytes()).hexdigest()
            assert actual==c['sha256']
            case=c['id'];truth=None
            for rep in range(a.repeats):
                order=list(METHODS)
                random.Random(2026751+int(case[:8],16)*2+rep*13297).shuffle(order)
                for method in order:
                    seed=(7512026+int(case[:8],16)+rep*1337)%4294967296
                    start=time.perf_counter()
                    try:
                        result=v751.execute(a.binary,method,cnf,seed,a.timeout)
                    except Exception as exc:
                        result=dict(answer='TIMEOUT',elapsed_s=a.timeout,native_s=None,
                                   error='ERROR:'+type(exc).__name__+':'+str(exc)[:180])
                    measured=time.perf_counter()-start
                    answer=result['answer']
                    if answer in ('SAT','UNSAT'):
                        if truth and answer!=truth:
                            raise RuntimeError('Conflicting SAT/UNSAT answers on official instance '+case+
                                f': prior {truth} vs {answer} in {method}')
                        truth=answer
                    record={key:result.get(key,'') for key in FIELDS}
                    record.update(case=case,family='OfficialMain2026',answer_expected='UNKNOWN',
                          method=method,repeat=rep,cutoff_s=a.timeout)
                    rows.append(record)
                    writer.writerow(record);f.flush()
                    print('TRIAL',case,rep,method,answer,
                          round(float(record['elapsed_s']),3),'sec',
                          'ERROR='+str(record['error'])[:80],flush=True)
            known[case]=truth or 'UNSOLVED'
            print('CASE',i+1,'/2',case,'observed',known[case],flush=True)
    summary=v751.report(rows,a.repeats,a.timeout)
    summary.update(dict(
        benchmark='SAT Competition 2026 Main original selected official CNFs',
        research_local_par2=True,competition_official_result=False,
        official_2026_time_limit_s=5000,local_time_limit_s=60,
        caDiCaL_source='arminbiere/cadical rel-3.0.1 unchanged',
        drnas_version='7.5.1 exact staged conflict probes',
        source_previous_run=41204322891,
        exact_original_CNF_sha256_verified=True,
        no_independent_unsat_proof_check=True,
        source_statuses=known,
        errors=sum(bool(r['error']) for r in rows),
        score_notes=[
            'Every one of the eight modes has two same-source randomized-order attempts.',
            'Old 20 exact official formula IDs with previous SHA256, no retuning or resampling.',
            'Local 60-second process cutoff; PAR-2=120 seconds for unresolved/failed attempts.',
            'CaDiCaL 3.0.1 BOTH plain and all experimental methods; cannot compare directly to previous older CaDiCaL 1.x baseline.',
            'No separate official UNSAT proof checker; only cross-mode consistency and every SAT-model native clause check.'
        ]))
    (output/'summary.json').write_text(json.dumps(summary,indent=2))
    print('SHARD SUMMARY',json.dumps({m:summary['modes'][m] for m in METHODS}),flush=True)

if __name__=='__main__':main()
