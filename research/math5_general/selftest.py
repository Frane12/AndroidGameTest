#!/usr/bin/env python3
"""Preflight on known controls only; never reads the blind input directory."""
import json, sys, tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import benchmark as b
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'math5_blind'))
from freeze import dimensions

def main():
    b.pin()
    with tempfile.TemporaryDirectory(prefix='math5-general-selftest-',dir=b.ROOT) as tmp:
        d=Path(tmp);sat=d/'sat.cnf';unsat=d/'unsat.cnf'
        sat.write_text('p cnf 2 2\n1 2 0\n-1 2 0\n')
        unsat.write_text('p cnf 2 4\n1 2 0\n-1 2 0\n1 -2 0\n-1 -2 0\n')
        model=d/'model.txt';model.write_text('s SATISFIABLE\nv 1 2 0\n');assert b.model_check(sat,model)
        model.write_text('s SATISFIABLE\nv 1 -2 0\n');assert not b.model_check(sat,model)
        model.write_text('s SATISFIABLE\nv 1 -1 2 0\n');assert not b.model_check(sat,model)
        model.write_text('s SATISFIABLE\nv 1 2 0\n');assert not b.model_check(unsat,model)
        assert dimensions(sat.read_bytes())==(2,2)
        try:dimensions(b'p cnf 2 2\n1 0\n')
        except ValueError:pass
        else:raise AssertionError('malformed CNF accepted')
        for i,(cnf,wanted) in enumerate([(sat,'SAT_VERIFIED'),(unsat,'UNSAT_VERIFIED')]):
            s=dict(id=i,family='CONTROL',path=str(cnf.relative_to(b.ROOT)),sha256=b.sha(cnf))
            for arm in b.P['arms']:
                row=b.trial(s,arm,0,d/f'{i}-{arm}',cap=5)
                assert row['status']==wanted and row['accepted'] and not row['critical'],row
                assert row['strict_accepted']==(row['certificate_kind'] in ('MODEL','DRAT')),row
                assert row['standard_accepted']==(row['certificate_kind'] in ('MODEL','DRAT','FRAT')),row
                if arm=='CMS' and wanted=='UNSAT_VERIFIED':
                    assert row['certificate_kind']=='FRAT' and row['standard_accepted'] and not row['strict_accepted'],row
        expired=b.run([sys.executable,'-c','import time;time.sleep(1)'],d/'timeout',.02)
        assert expired['expired'] and expired['rc']!=0
        count=list((b.ROOT/'math5_blind_inputs/cnf').glob('11-*.cnf'))
        assert len(count)==1 and b.sha(count[0])=='1049c754c083e68284c45df9826e3acc3200781cc406566c26e12f81a7a205e2'
        s=dict(id=21,family='KNOWN_COUNT_CONTROL',path=str(count[0]),sha256=b.sha(count[0]))
        row=b.trial(s,'MATH5',0,d/'known-count',cap=5)
        assert row['accepted'] and not row['strict_accepted'] and row['certificate_kind'].startswith('STRUCTURAL_'),row
        cert=d/'known-count/structural.json';proof=json.loads(cert.read_text());proof['source_sha256']='0'*64;cert.write_text(json.dumps(proof))
        rejected=b.run([sys.executable,str(b.ROOT/'research/math5/check_math5.py'),str(count[0]),str(cert)],d/'corrupt-check',5)
        assert rejected['rc']!=0 and not rejected['expired']
        # A missing or duplicated cell must not silently improve the aggregate.
        original_out,original_inputs=b.OUT,b.INPUTS
        try:
            b.OUT=d/'aggregate';b.INPUTS=d/'aggregate-inputs'
            b.OUT.mkdir();b.INPUTS.mkdir();(b.OUT/'shard-0').mkdir()
            sources=[dict(id=0,family='CONTROL',sha256='0'*64)]
            (b.INPUTS/'manifest.json').write_text(json.dumps(dict(sources=sources)))
            rows=[dict(id=0,family='CONTROL',source_sha256='0'*64,arm=a,rep=r,critical=False,
                verified=False,accepted=False,status='TIMEOUT',certificate_kind=None,guard=None,
                PAR2_s=20,PAR2_strict_s=20,PAR2_standard_s=20,solver_cpu_s=1,maxrss_kib=100)
                for r in range(b.P['repetitions']) for a in b.P['arms']]
            trials=b.OUT/'shard-0/trials.jsonl'
            for broken in (rows[:-1],rows+[rows[0]]):
                trials.write_text(''.join(json.dumps(r)+'\n' for r in broken))
                try:b.report()
                except AssertionError:pass
                else:raise AssertionError('Incomplete/duplicate matrix accepted')
            trials.write_text(''.join(json.dumps(r)+'\n' for r in rows));b.report()
            summary=json.loads((b.OUT/'summary.json').read_text())
            assert summary['trials']==18 and all(t['PAR2_s']==60 for t in summary['totals'].values())
            assert not summary['success_threshold_met']
        finally:b.OUT,b.INPUTS=original_out,original_inputs
        print('GENERAL_PREFLIGHT_PASS',flush=True)
if __name__=='__main__':main()
