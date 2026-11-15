#!/usr/bin/env python3
"""Post-discovery focused 5s comparison on source21. Not a blind evaluation.
One logical CPU. E2E=solver+independent checker. Structural and strict proof
scores are deliberately separate. Temporary incomplete proof files are removed.
"""
from __future__ import annotations
import argparse, hashlib, json, os, platform, random, resource, subprocess, sys, time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from check_math5 import verify
CAP=5.0

def invoke(cmd,folder,limit):
    folder.mkdir(parents=True,exist_ok=False)
    def restrict():
        resource.setrlimit(resource.RLIMIT_FSIZE,(256*1024**2,256*1024**2))
        resource.setrlimit(resource.RLIMIT_AS,(4*1024**3,4*1024**3))
    start=time.perf_counter();expired=False
    with (folder/'stdout.txt').open('w') as out,(folder/'stderr.txt').open('w') as err:
        p=subprocess.Popen(cmd,stdout=out,stderr=err,preexec_fn=restrict)
        try:p.wait(timeout=limit)
        except subprocess.TimeoutExpired:p.kill();p.wait();expired=True
    return dict(rc=p.returncode,expired=expired,wall_s=time.perf_counter()-start,
                stdout=(folder/'stdout.txt').read_text(),stderr=(folder/'stderr.txt').read_text())

def main():
    a=argparse.ArgumentParser();a.add_argument('--work',type=Path,required=True);a.add_argument('--frozen',type=Path,required=True)
    a.add_argument('--out',type=Path,required=True);args=a.parse_args();args.out.mkdir(parents=True,exist_ok=False)
    cpu=min(os.sched_getaffinity(0));os.sched_setaffinity(0,{cpu})
    cnf=next((args.frozen/'hall3_inputs/cnf').glob('21-*.cnf')).resolve();raw=cnf.read_bytes()
    assert hashlib.sha256(raw).hexdigest()=='23702be6f54e7c6722880ea44f26ce4c7ca01791631cdfc8bce47c18615477c6'
    bins={'MATH4':args.work/'build/drnas-math4-local','MATH5':args.work/'build/drnas-math5',
          'Kissat':args.frozen/'build/kissat','CaDiCaL':args.frozen/'build/cadical'}
    protocol=dict(source_sha256=hashlib.sha256(raw).hexdigest(),source_file=cnf.name,cap_s=CAP,reps=2,
                  one_logical_cpu=cpu,post_discovery_not_holdout=True,structural_is_not_DRAT=True,
                  binaries={a:hashlib.sha256(p.read_bytes()).hexdigest() for a,p in bins.items()},
                  platform=platform.platform(),timing='wall solver plus fresh checker process',
                  proof_limit_bytes=256*1024**2)
    (args.out/'protocol.json').write_text(json.dumps(protocol,indent=2));rows=[]
    for rep in range(2):
        order=list(bins);random.Random(20261115+rep).shuffle(order)
        for arm in order:
            base=args.out/f'{rep}-{arm}';base.mkdir();proof=base/'proof.drat';cert=base/'structural.json'
            if arm in ('MATH4','MATH5'):
                cmd=[str(bins[arm].resolve()),str(cnf),'--mode','core','--time',str(CAP),
                     '--x5-no-minimize','--x5-no-retain','--cf5-policy','B2L_32',
                     '--'+arm.lower(),'--pcmax-budget-ms','750','--pcmax-certificate',str(cert.resolve()),'--proof',str(proof.resolve())]
            elif arm=='Kissat':cmd=[str(bins[arm].resolve()),str(cnf),str(proof.resolve())]
            else:cmd=[str(bins[arm].resolve()),'-q','--no-binary',str(cnf),str(proof.resolve())]
            result=invoke(cmd,base/'solver',CAP)
            status='TIMEOUT' if result['expired'] else 'UNKNOWN';accepted=False;kind=None;check_s=0
            if result['rc']==20 and not result['expired']:
                if cert.exists():
                    data=json.loads(cert.read_text());kind='STRUCTURAL_MATH5'
                    assert data['format']=='drnas-math5-eo-xor-unit-v1'
                    ck=invoke([sys.executable,str(Path(__file__).resolve().parent/'check_math5.py'),str(cnf),str(cert.resolve())],base/'checker',max(0.001,CAP-result['wall_s']))
                    assert ck['rc']==0 and not ck['expired'],('CHECK_FAILED',ck)
                else:
                    kind='DRAT';assert proof.exists()
                    ck=invoke([str((args.frozen/'build/drat-trim').resolve()),str(cnf),str(proof.resolve())],base/'checker',max(0.001,CAP-result['wall_s']))
                    assert ck['rc']==0 and 's VERIFIED' in ck['stdout'],ck
                check_s=ck['wall_s'];accepted=result['wall_s']+check_s<=CAP
                status='UNSAT_VERIFIED' if accepted else 'UNSAT_CHECK_OVER_BUDGET'
            elif result['rc']==10:raise AssertionError('FALSE SAT ON INDEPENDENTLY REFUTED ORIGINAL')
            elif not result['expired'] and result['rc'] not in (0,20):status='RESOURCE_LIMIT' if result['rc'] in (-25,-9) else 'ERROR'
            size=proof.stat().st_size if proof.exists() else 0
            row=dict(arm=arm,rep=rep,status=status,proof_kind=kind,verified=accepted,
                     solver_s=result['wall_s'],checker_s=check_s,e2e_s=result['wall_s']+check_s,
                     PAR2_structural_s=result['wall_s']+check_s if accepted else 2*CAP,
                     PAR2_strict_DRAT_s=result['wall_s']+check_s if accepted and kind=='DRAT' else 2*CAP,
                     incomplete_or_complete_proof_bytes=size)
            rows.append(row);print(json.dumps(row),flush=True)
            # Only incomplete local trial scratch; preserve all successful proofs.
            if not accepted and proof.exists():proof.unlink()
    out=dict(protocol=protocol,trials=rows,summary={a:dict(verified=sum(r['verified'] for r in rows if r['arm']==a),
           PAR2_structural_total_s=sum(r['PAR2_structural_s'] for r in rows if r['arm']==a),
           PAR2_strict_DRAT_total_s=sum(r['PAR2_strict_DRAT_s'] for r in rows if r['arm']==a)) for a in bins})
    (args.out/'results.json').write_text(json.dumps(out,indent=2));print(json.dumps(out['summary'],indent=2))
if __name__=='__main__':main()
