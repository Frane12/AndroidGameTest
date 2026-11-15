#!/usr/bin/env python3
"""Freeze a newly built binary-default MATH5 before GENERAL100 measurement."""
import hashlib,json,os,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
PFILE=ROOT/'research/math5_general/prespec.json'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    assert not (ROOT/'math5_general_inputs').exists(), 'Cannot change a frozen experiment'
    assert not (ROOT/'math5_general_results').exists(), 'Cannot change a started experiment'
    p=json.loads(PFILE.read_text())
    # Reference solvers and MATH4 retain their independently pinned identities.
    for path,h in p['reference_hashes'].items():
        if path!='build/drnas-math5':assert sha(ROOT/path)==h,('reference_drift',path)
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    with tempfile.TemporaryDirectory() as tmp:
        d=Path(tmp);cnf=d/'case.cnf';proof=d/'proof.drat'
        cnf.write_text('p cnf 2 4\n1 2 0\n-1 2 0\n1 -2 0\n-1 -2 0\n')
        cmd=[str(ROOT/'build/drnas-math5'),str(cnf),'--mode','core','--time','3','--proof',str(proof)]
        run=subprocess.run(cmd,capture_output=True,timeout=5)
        assert run.returncode==20 and proof.read_bytes().startswith(b'a'), 'Default binary DRAT is mandatory'
        ck=subprocess.run([str(ROOT/'build/drat-trim'),str(cnf),str(proof)],capture_output=True,timeout=5)
        assert ck.returncode==0 and b'VERIFIED' in ck.stdout
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    p['reference_hashes']['build/drnas-math5']=sha(ROOT/'build/drnas-math5')
    files=set(p['source_hashes'])|{'research/math5_proofio/build.py','research/math5_proofio/build_legacy.py','research/math5_general/refresh_current.py'}
    p['source_hashes']={path:sha(ROOT/path) for path in sorted(files)}
    p.update(name='DRNAS-MATH5-GENERAL100-BINARY-DEFAULT',proof_format='binary DRAT (MATH5 and OFF)',
        frozen_solver_commit=commit,frozen_benchmark_commit=commit,
        reference='Fresh canonical MATH5 build with mandatory binary DRAT default; unchanged frozen MATH4, Kissat, CaDiCaL, CMS and checkers. All binaries frozen and hashed before trials.')
    PFILE.write_text(json.dumps(p,indent=2,sort_keys=True)+'\n')
    print('CURRENT_BINARY_DEFAULT_VERIFIED '+p['reference_hashes']['build/drnas-math5'])
if __name__=='__main__':main()
