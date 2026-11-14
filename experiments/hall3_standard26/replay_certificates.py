#!/usr/bin/env python3
"""Recreate original-CNF certificates locally; these are not CI timing samples."""
import hashlib,json,os,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent/'replayed_certificates'

def main():
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    OUT.mkdir(exist_ok=False)
    manifest=json.loads((ROOT/'research/hall3/manifest.json').read_text())
    records=[]
    for index in (1,18,19):
        s=manifest['sources'][index];cnf=ROOT/s['path'];cert=OUT/f'source-{index:02d}.json'
        assert hashlib.sha256(cnf.read_bytes()).hexdigest()==s['sha256']
        p=subprocess.run([str(ROOT/'build/drnas-hall3'),str(cnf),'--mode','core',
            '--time','15','--cf5-policy','B2L_32','--x5-no-minimize','--x5-no-retain',
            '--hall3','--pcmax-budget-ms','750','--pcmax-certificate',str(cert)],
            capture_output=True,text=True,timeout=16)
        assert p.returncode==20 and cert.exists(),(index,p.stdout,p.stderr)
        c=subprocess.run([sys.executable,str(ROOT/'research/pcmax_capacity/check_clause_hall.py'),
            str(cnf),str(cert)],capture_output=True,text=True,timeout=90)
        assert c.returncode==0,(index,c.stdout,c.stderr)
        check=json.loads(c.stdout)
        assert check['status']=='UNSAT_CLAUSE_HALL_CERTIFICATE_VERIFIED'
        records.append(dict(id=index,file_id=s['file_id'],family=s['family'],
            source_sha256=s['sha256'],certificate_sha256=hashlib.sha256(cert.read_bytes()).hexdigest(),
            certificate_file=cert.name,independent_check=check))
    report=dict(note='Local certificate replay from exact CI source bytes. No times here are used in the benchmark.',
        ci_run=43643413210,ci_source_commit='119d74530181b1a1b6bff2a40b0f17f929547990',
        local_binary_sha256=hashlib.sha256((ROOT/'build/drnas-hall3').read_bytes()).hexdigest(),records=records)
    (OUT/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(certificates=len(records),verified=True)))

if __name__=='__main__':main()
