#!/usr/bin/env python3
"""R107B proof-carrying GF2-CaDiCaL versus R105 and three world baselines, 2025 real CNFs."""
import csv,json,pathlib,random,subprocess,time,sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import r106_verify_solver as checker
MODES=['cadical','kissat','cryptominisat','drnas_r105','drnas_r107b']
CAP=15.0
def measure(binary,cnf,original,expected,allowed):
    start=time.perf_counter()
    try:
        p=subprocess.run([str(binary),str(cnf)],capture_output=True,text=True,
                         errors='replace',timeout=max(.01,allowed))
    except subprocess.TimeoutExpired:
        return 'TIMEOUT',allowed,False
    elapsed=time.perf_counter()-start
    outcome=checker.status(p.stdout,p.returncode)
    if outcome!=expected:
        raise RuntimeError('R106 result contradicts original 2025 label: '+str(cnf))
    checked=outcome=='SAT' and checker.model_valid(p.stdout,original)
    if outcome=='SAT' and not checked:
        raise RuntimeError('R106 SAT witness missing/invalid: '+str(cnf)+' '+str(binary))
    if elapsed>allowed:outcome='TIMEOUT'
    return outcome,elapsed,checked
def main():
    if len(sys.argv)!=5:raise SystemExit('usage: R106.py OUT CADICAL KISSAT CRYPTOMINISAT')
    out=pathlib.Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=True)
    binaries=dict(zip(MODES[:3],sys.argv[2:]))
    binaries['drnas_r105']=binaries['cadical']
    binaries['drnas_r107b']=binaries['cadical']
    manifest=json.loads((out/'manifest.json').read_text())
    records=[]
    for x in manifest:
        src=out/'source'/x['name'];clauses=checker.cnf_clauses(src)
        dest=out/'r105'/x['name'];dest.parent.mkdir(exist_ok=True)
        ev=out/'proofs'/(x['name']+'.json');ev.parent.mkdir(exist_ok=True)
        t=time.perf_counter()
        cmd=['python3','research/r105_gf2_contradiction_only.py','export',
             '--cnf',str(src),'--out',str(dest),'--evidence',str(ev)]
        try:
            p=subprocess.run(cmd,capture_output=True,text=True,timeout=60)
            prep=time.perf_counter()-t
            if p.returncode:raise RuntimeError(p.stderr[-900:])
            cert=json.loads(ev.read_text())
            if cert['sha256']!=x['sha256'] or (cert['contradiction'] and x['expected']=='SAT'):
                raise RuntimeError('R106 fail-closed wrong certificate')
            supported=True;reason=''
        except (subprocess.TimeoutExpired,RuntimeError) as exc:
            supported=False;prep=CAP;reason=str(exc)[:200]
            cert=dict(original_xors=0,contradiction=False)
        r107b_dest=out/'r107b'/x['name']
        r107b_dest.parent.mkdir(exist_ok=True)
        r107b_evidence=out/'proofs_r107b'/(x['name']+'.json')
        r107b_evidence.parent.mkdir(exist_ok=True)
        r107b_start=time.perf_counter()
        try:
            r107b_proc=subprocess.run(
                ['python3','research/r107b_certified_cadical.py','export',
                 '--cnf',str(src),'--out',str(r107b_dest),
                 '--evidence',str(r107b_evidence)],
                capture_output=True,text=True,timeout=90)
            r107b_prep=time.perf_counter()-r107b_start
            if r107b_proc.returncode:
                raise RuntimeError('R107B certificate process error: '+r107b_proc.stderr[-800:])
            r107b_cert=json.loads(r107b_evidence.read_text())
            if r107b_cert['source_sha256']!=x['sha256']:
                raise RuntimeError('R107B input digest mismatch')
            if r107b_cert['gf2_unsat'] and x['expected']=='SAT':
                raise RuntimeError('R107B unsound proof on known SAT')
            r107b_supported=True;r107b_reason=''
        except (subprocess.TimeoutExpired,RuntimeError) as error:
            r107b_supported=False;r107b_prep=CAP;r107b_reason=str(error)[:200]
            r107b_cert={'source_xors':0,'gf2_unsat':False,'proof_length':0}
            print('R107B_UNSUPPORTED',x['name'],r107b_reason,flush=True)
        for rep in range(2):
            modes=MODES[:];random.Random(x['sha256']+str(rep)+'R106').shuffle(modes)
            for mode in modes:
                charge=(prep if mode=='drnas_r105' else
                        r107b_prep if mode=='drnas_r107b' else 0.)
                if (mode=='drnas_r105' and not supported) or (
                        mode=='drnas_r107b' and not r107b_supported):
                    outcome='UNSUPPORTED';solver_s=0.;checked=False
                elif charge>=CAP:
                    outcome='TIMEOUT';solver_s=0.;checked=False
                else:
                    cnf=(dest if mode=='drnas_r105' else
                         r107b_dest if mode=='drnas_r107b' else src)
                    outcome,solver_s,checked=measure(binaries[mode],cnf,clauses,
                                                    x['expected'],CAP-charge)
                total=charge+solver_s
                records.append(dict(formula=x['name'],sha256=x['sha256'],rep=rep,mode=mode,
                    expected=x['expected'],status=outcome,solver_s=round(solver_s,6),
                    prep_s=round(charge,6),total_s=round(total,6),
                    par2_s='' if outcome=='UNSUPPORTED' else
                      round(30 if outcome=='TIMEOUT' else total,6),
                    xor_rows=(r107b_cert['source_xors'] if mode=='drnas_r107b' else cert['original_xors']),
                    gf2_proof=(r107b_cert['gf2_unsat'] if mode=='drnas_r107b' else cert['contradiction']),
                    proof_length=(r107b_cert.get('proof_length',0) if mode=='drnas_r107b' else
                                  len(cert.get('proof_original_row_ids',[]))),
                    sat_verified=checked,unsupported_reason=(
                       r107b_reason if mode=='drnas_r107b' else reason
                       ) if outcome=='UNSUPPORTED' else ''))
        print('R107B_CASE',x['name'],'GF2_R105',cert['contradiction'],
              'GF2_R107B',r107b_cert['gf2_unsat'],'xor_R105',cert['original_xors'],
              'xor_R107B',r107b_cert['source_xors'],
              'prep_R105',round(prep,5),'prep_R107B',round(r107b_prep,5),'results',json.dumps({m:[
                (r['status'],r['total_s']) for r in records
                if r['formula']==x['name'] and r['mode']==m] for m in MODES}),flush=True)
    if len(records)!=len(manifest)*2*len(MODES):raise RuntimeError('missing trials')
    with (out/'paired.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(records[0]));w.writeheader();w.writerows(records)
    summary={}
    for mode in MODES:
        rs=[r for r in records if r['mode']==mode]
        summary[mode]=dict(trials=len(rs),solved=sum(r['status'] in ('SAT','UNSAT') for r in rs),
          timeouts=sum(r['status']=='TIMEOUT' for r in rs),
          unsupported=sum(r['status']=='UNSUPPORTED' for r in rs),
          par2_s=round(sum(float(r['par2_s']) for r in rs if r['par2_s']!=''),6),
          verified_sat=sum(r['sat_verified'] for r in rs))
    audit=dict(protocol='R107B-PUBLIC-SATCOMP2025-PROOF-CARRYING-CADICAL',
        cases=len(manifest),trials=len(records),cap_s=CAP,summary=summary,
        notes='Not verified globally unseen nor official 2026. All original CNFs SHA checked. R105 charged preparation; only complete 3-XOR signatures; external UNSAT not proof verified. Incompatible R105 cases reported as unsupported.')
    (out/'summary.json').write_text(json.dumps(audit,indent=2))
    print('R107B_COMPLETE_AUDIT',json.dumps(audit),flush=True)
if __name__=='__main__':main()
