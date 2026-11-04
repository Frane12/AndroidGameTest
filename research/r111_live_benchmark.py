#!/usr/bin/env python3
"""R111: frozen regression: live GF2-CDCL vs root-CaDiCaL, clean, Kissat, CMS.

Precommitted regression formulas (previously used in R106/R110) plus two
distinct XOR SAT/UNSAT controls per shard. No claim of blind novelty.
Full wall-clock of every R107C prep + R111 native parsing, basis scanning,
reasons and CaDiCaL solve counted. SAT model verified against original CNF.
"""
import argparse,csv,hashlib,itertools,json,lzma,pathlib,random,subprocess,time,urllib.request
import sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import r106_verify_solver as checker
MODES=('cadical','kissat','cryptominisat','r107c_root','r111_live')

def fetch_all(out,shard):
    frozen=json.loads(pathlib.Path('research/r111_frozen_eval_manifest.json').read_text())
    r110=json.loads(pathlib.Path('research/r110_frozen_holdout_2025.json').read_text())
    r106=json.loads(pathlib.Path('research/r106_manifest.json').read_text())
    spec=frozen['shards'][shard]
    real=[]
    for prefix in spec['r110']:
        hit=[x for x in r110['shards'][shard] if x['name'].startswith(prefix)]
        if len(hit)!=1:raise RuntimeError('R111_FAIL_CLOSED missing R110 precommitted formula')
        x=hit[0]
        real.append(dict(name=x['name'],sha256=x['sha256'],bytes=x['bytes'],
                         expected=x['status'],url=x['url'],origin='R110_seen_2025'))
    old=[x for x in r106['cases'] if x[0].startswith(spec['r106'])]
    if len(old)!=1:raise RuntimeError('R111_FAIL_CLOSED R106 case not unique')
    name,expected,ident,sha,size=old[0]
    real.append(dict(name=name,sha256=sha,bytes=size,expected=expected,
                     url='https://benchmark-database.de/file/'+ident,origin='R106_seen_2025'))
    if len(real)!=3:raise RuntimeError('R111_CASE_COUNT')
    dest=out/'source';dest.mkdir(exist_ok=True,parents=True)
    for x in real:
        req=urllib.request.Request(x['url'],headers={'User-Agent':'DRNAS-R111-live-GF2/1.0'})
        with urllib.request.urlopen(req,timeout=90) as stream:blob=stream.read(20_000_000)
        if len(blob)>=20_000_000:raise RuntimeError('R111 compressed input cap exceeded')
        data=lzma.decompress(blob,memlimit=128*1024*1024)
        if len(data)!=x['bytes'] or hashlib.sha256(data).hexdigest()!=x['sha256']:
            raise RuntimeError('R111_SHA_VERIFICATION_FAILED '+x['name'])
        (dest/x['name']).write_bytes(data)
        print('R111_SHA_VERIFIED',shard,x['name'],x['sha256'],flush=True)
    def parity(vars,rhs):
        return [tuple(-v if (i>>j)&1 else v for j,v in enumerate(vars))
                for i in range(1<<len(vars)) if i.bit_count()%2!=rhs]
    # Contradiction-free source relationships: (a XOR b XOR c=0),
    # (a XOR b XOR d=0) imply c XOR d=0. Under c=1 propagate d=1.
    # Both controls deliberately force c via a unit literal.
    for expected in ('SAT','UNSAT'):
        clauses=(parity((1,2,3),0)+parity((1,2,4),0)+[(3,),(4 if expected=='SAT' else -4,)])
        name=f'r111_shard{shard}_derived_xor_{expected.lower()}.cnf'
        file=dest/name
        file.write_text(f'p cnf 4 {len(clauses)}\n'+''.join(
            ' '.join(map(str,c))+' 0\n' for c in clauses))
        real.append(dict(name=name,expected=expected,
                         sha256=hashlib.sha256(file.read_bytes()).hexdigest(),
                         bytes=file.stat().st_size,origin='controlled_xor_not_external'))
    (out/'frozen-inputs.json').write_text(json.dumps(
        dict(shard=shard,cap=frozen['cap_s'],repeats=frozen['repeats'],cases=real),indent=2)+'\n')
    return real

def prep_once(binary,src,dest,evidence,limit):
    started=time.perf_counter()
    try:
        p=subprocess.run([str(binary),str(src),str(dest),str(evidence)],
                         capture_output=True,text=True,timeout=max(.01,limit))
    except subprocess.TimeoutExpired:
        return dict(status='TIMEOUT',prep_s=limit,info=None,error='preprocessor timeout')
    elapsed=time.perf_counter()-started
    if p.returncode!=0:return dict(status='UNSUPPORTED',prep_s=elapsed,info=None,
                                    error=(p.stderr or p.stdout)[-400:])
    info=json.loads(evidence.read_text())
    if 'gf2_unsat' not in info:raise RuntimeError('R111 incomplete root evidence')
    if info['gf2_unsat'] and checker.cnf_clauses(dest)[-1]!=():
        raise RuntimeError('R111 invalid root UNSAT')
    if not info['gf2_unsat'] and src.read_bytes()!=dest.read_bytes():
        raise RuntimeError('R111 altered CNF without proof')
    return dict(status='OK',prep_s=elapsed,info=info,error='')

def solve(binary,mode,src,augmented,expected,limit):
    if mode=='r111_live':
        cmd=[str(binary),'live',str(src),str(augmented)]
    else:
        cmd=[str(binary),str(augmented if mode=='r107c_root' else src)]
    started=time.perf_counter()
    try:
        p=subprocess.run(cmd,capture_output=True,text=True,errors='replace',
                         timeout=max(.01,limit))
    except subprocess.TimeoutExpired:
        return dict(status='TIMEOUT',elapsed=limit,verified=False,metrics={})
    elapsed=time.perf_counter()-started
    if mode=='r111_live':
        stamp=[x.strip() for x in p.stdout.splitlines() if x.startswith('R111_RESULT ')]
        if len(stamp)!=1 or p.returncode not in (10,20):
            raise RuntimeError('R111 native failed '+p.stderr[-600:]+p.stdout[-500:])
        metrics={}
        for field in stamp[0].split()[1:]:
            if '=' in field:
                k,v=field.split('=',1)
                try:metrics[k]=float(v) if '.' in v else int(v)
                except ValueError:metrics[k]=v
        status='SAT' if p.returncode==10 else 'UNSAT'
        verified=(status=='SAT' and metrics.get('model_checked')==1)
    else:
        status=checker.status(p.stdout,p.returncode)
        verified=(status=='SAT' and checker.model_valid(p.stdout,checker.cnf_clauses(src)))
        metrics={}
    if status!=expected:
        raise RuntimeError('R111_FAIL_CLOSED solver status '+status+' != '+expected+' for '+str(src))
    if status=='SAT' and not verified:
        raise RuntimeError('R111_FAIL_CLOSED unverified SAT model '+str(src))
    if elapsed>limit:status='TIMEOUT'
    return dict(status=status,elapsed=elapsed,verified=verified,metrics=metrics)

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--shard',type=int,choices=range(4),required=True)
    p.add_argument('--out',required=True)
    for mode in ('cadical','kissat','cms','r107c','r111'):
        p.add_argument('--'+mode,required=True)
    a=p.parse_args()
    frozen=json.loads(pathlib.Path('research/r111_frozen_eval_manifest.json').read_text())
    cap=frozen['cap_s'];repeats=frozen['repeats']
    if cap!=10 or repeats!=2:raise RuntimeError('R111 changed evaluation settings')
    root=pathlib.Path(a.out);root.mkdir(parents=True,exist_ok=True)
    cases=fetch_all(root,a.shard)
    executables=dict(cadical=a.cadical,kissat=a.kissat,cryptominisat=a.cms,
                     r107c_root=a.cadical,r111_live=a.r111)
    rows=[]
    for case in cases:
        src=root/'source'/case['name']
        for rep in range(repeats):
            order=list(MODES)
            random.Random(case['sha256']+str(rep)+'R111').shuffle(order)
            for mode in order:
                prep_s=0.;info=None;error='';pre_status='OK'
                augmented=src
                if mode in ('r107c_root','r111_live'):
                    augmented=root/'derived'/mode/str(rep)/case['name']
                    augmented.parent.mkdir(parents=True,exist_ok=True)
                    evidence=root/'evidence'/mode/str(rep)/(case['name']+'.json')
                    evidence.parent.mkdir(parents=True,exist_ok=True)
                    pr=prep_once(a.r107c,src,augmented,evidence,cap)
                    prep_s=pr['prep_s'];info=pr['info'];error=pr['error'];pre_status=pr['status']
                    if case['expected']=='SAT' and info and info['gf2_unsat']:
                        raise RuntimeError('R111 root false UNSAT '+case['name'])
                if pre_status!='OK':
                    sol=dict(status=pre_status,elapsed=0.,verified=False,metrics={})
                elif prep_s>=cap:
                    sol=dict(status='TIMEOUT',elapsed=0.,verified=False,metrics={})
                else:
                    sol=solve(executables[mode],mode,src,augmented,case['expected'],cap-prep_s)
                elapsed=prep_s+sol['elapsed']
                row=dict(shard=a.shard,formula=case['name'],origin=case['origin'],
                         sha256=case['sha256'],expected=case['expected'],
                         rep=rep,mode=mode,status=sol['status'],
                         total_s=round(elapsed,6),prep_s=round(prep_s,6),
                         solver_s=round(sol['elapsed'],6),
                         PAR2_s=round(2*cap if sol['status'] in ('TIMEOUT','UNSUPPORTED') else elapsed,6),
                         gf2_source_rows=info.get('source_xors') if info else None,
                         gf2_root_proof=info.get('gf2_unsat') if info else None,
                         cdcl_live_units=sol['metrics'].get('live_units'),
                         cdcl_live_conflicts=sol['metrics'].get('live_conflicts'),
                         cdcl_live_scans=sol['metrics'].get('live_scans'),
                         activated_rows=sol['metrics'].get('activated_rows'),
                         budget_off=sol['metrics'].get('budget_off'),
                         verified_sat=sol['verified'],error=error)
                rows.append(row)
                print('R111_TRIAL',json.dumps({k:row[k] for k in
                  ('formula','rep','mode','status','total_s','prep_s','cdcl_live_units',
                   'cdcl_live_conflicts','activated_rows','error')}),flush=True)
            if hashlib.sha256(src.read_bytes()).hexdigest()!=case['sha256']:
                raise RuntimeError('R111_FAIL_CLOSED modified original formula')
        print('R111_CASE',case['name'],json.dumps({
             mode:[dict(status=r['status'],total=r['total_s'],
                       units=r['cdcl_live_units']) for r in rows
                 if r['formula']==case['name'] and r['mode']==mode]
             for mode in MODES}),flush=True)
    if len(rows)!=len(cases)*len(MODES)*repeats:
        raise RuntimeError('R111 missing paired trials')
    with (root/'paired.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]))
        w.writeheader();w.writerows(rows)
    totals={}
    for mode in MODES:
        subset=[r for r in rows if r['mode']==mode]
        totals[mode]=dict(trials=len(subset),
            solved=sum(r['status'] in ('SAT','UNSAT') for r in subset),
            PAR2_s=round(sum(r['PAR2_s'] for r in subset),6),
            timeouts=sum(r['status']=='TIMEOUT' for r in subset),
            unsupported=sum(r['status']=='UNSUPPORTED' for r in subset),
            verified_sat=sum(r['verified_sat'] for r in subset),
            propagated_units=sum(r['cdcl_live_units'] or 0 for r in subset),
            gf2_conflicts=sum(r['cdcl_live_conflicts'] or 0 for r in subset))
    audit=dict(protocol='R111-IPASIR-UP-CERTIFIED-LIVE-GF2-CDCL-REGRESSION',
      shard=a.shard,real_cases=sum(c['origin']!='controlled_xor_not_external' for c in cases),
      controlled_cases=sum(c['origin']=='controlled_xor_not_external' for c in cases),
      trials=len(rows),cap_s=cap,repeats=repeats,totals=totals,
      limitations=[
       'Previously seen public SAT Competition 2025 originals, not independent 2026 unseen test.',
       'GF2 live budget capped to 192 independently verified original 2..6 XOR rows / 1024 observed variables; no hidden-XOR mining in live stage.',
       'R107C preprocessing repeated and timed in each DRNAS arm; live native process time includes XOR extraction, basis updates and CaDiCaL solving.',
       'External UNSAT solver results not independently proof checked; exact XOR signatures sourced from immutable SHA verified original CNF.',
       'PAR2 20s for 10s timeout, not observed time.',
       'Four separate GitHub runners may differ; compare methods within a shard.'])
    (root/'summary.json').write_text(json.dumps(audit,indent=2)+'\n')
    print('R111_SHARD_COMPLETE_AUDIT',json.dumps(audit),flush=True)
if __name__=='__main__':main()
