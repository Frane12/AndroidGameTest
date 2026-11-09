#!/usr/bin/env python3
"""X6 known easy9 replay, selected by prior CMS and Kissat completion below 5s. Not unseen."""
import argparse, collections, hashlib, json, os, pathlib, random, re
import subprocess, tempfile, time
import mre_x6_shift_dose_causal as x6
import mre_x2_clause_order_causal as x2
import mre7_extended_easy_freeze as pool
import mre7_reference_easy_freeze as fetch
import mre6b_blind_freeze as prior

ROOT=pathlib.Path('mre_x6easy')
PROTO='DRNAS-X6-EASY9-9ARMS-2SEEDS-8S-E2E-20261109-v1'
SALT=PROTO+'-SOURCE-ONLY'
MODES=x6.MODES+('kissat',)
CAP=8.0
REPS=2
TARGET=9
SHARDS=9
YEARS=('2021','2022','2023')
def need(ok,msg):
    if not ok: raise RuntimeError('X6E_FAIL_CLOSED '+msg)
def sha(b):return hashlib.sha256(b).hexdigest()
def save(p,v):
    pathlib.Path(p).parent.mkdir(parents=True,exist_ok=True)
    pathlib.Path(p).write_text(json.dumps(v,indent=2,sort_keys=True)+'\n')
def seed(c,r):return int(sha((PROTO+'|'+c['sha256']+'|'+str(r)).encode())[:8],16) & 0x7fffffff
CHOSEN=[{"gbd":"fdfcd52a21824b7181d66672f283ba04","sha256":"7f25d0862e92fb60d957ea903ded020ec2b83b2ceec2ba4bf015bdcb1d4c3ac1","seeds":[2127078420,4090319451],"reference_status":"SAT","prior_cms_s":[1.212385,2.666609],"prior_kissat_s":[1.685622,1.683101]},{"gbd":"d0364ea3e1680c6da7e982e6b0264af6","sha256":"dcc69e102caecfe763e554b5d11285823a8907cd9493de9cf771e409676b8340","seeds":[3471685526,1056096750],"reference_status":"SAT","prior_cms_s":[0.148601,0.148876],"prior_kissat_s":[0.042107,0.042315]},{"gbd":"0297c2a35f116ffd5382aea5b421e6df","sha256":"ed070d2f6b9e3c4f918b5412413b94e806c06005c2c308b17bc6a25ad1ebf5af","seeds":[2665661596,3322179509],"reference_status":"UNSAT","prior_cms_s":[0.727511,0.76737],"prior_kissat_s":[0.699181,0.708089]},{"gbd":"578f9377bfbfcc6ea3a18eb630667956","sha256":"818eea0ab4e59102c589549d3ca487bf7c8a03e1e51644a126cba75a911e53de","seeds":[3435597931,4024547016],"reference_status":"SAT","prior_cms_s":[0.309721,0.306282],"prior_kissat_s":[0.607363,0.609233]},{"gbd":"037d21e060a2e3eab8b080aa84ceee75","sha256":"b84bff752c8292bacf847078d0fe2c2bf8ef86f429c08250e973a0525b607c39","seeds":[1389404847,671263007],"reference_status":"SAT","prior_cms_s":[0.656081,0.68701],"prior_kissat_s":[3.060984,3.042324]},{"gbd":"92d6795785d35d1dcc42b15dc0e933d0","sha256":"ead603b38fca048e96b4592c141bcd553856388479c1930042a1dfe176a44272","seeds":[1520292214,1416592863],"reference_status":"UNSAT","prior_cms_s":[1.032836,1.005142],"prior_kissat_s":[0.919634,0.884222]},{"gbd":"24b93d0bf941e4b050c9109e4cb7faf4","sha256":"d6397d0bf73b9901e8af7c694ec6abf86cd3ecca029c44884183b5236304dbdf","seeds":[2831739671,1979408778],"reference_status":"SAT","prior_cms_s":[0.202559,0.198795],"prior_kissat_s":[0.162729,0.161973]},{"gbd":"431bfb466be51ecd86b321b5cbce6d3c","sha256":"7b886432bf5f8c0e873e9bb0a01d32346e24380911d982573add2178a2a56fe6","seeds":[3297852564,944485550],"reference_status":"UNSAT","prior_cms_s":[0.259477,0.222686],"prior_kissat_s":[0.289908,0.294545]},{"gbd":"17039a3ed02ea12653ec5389e56dab50","sha256":"ae9ec25d79e840a6794724857b894bf47e595a17c5893170f38526a41380f472","seeds":[3924884132,3098083608],"reference_status":"UNSAT","prior_cms_s":[0.867482,0.845115],"prior_kissat_s":[0.20782,0.206603]}]
def freeze():
    ROOT.mkdir(exist_ok=True)
    manifest=pathlib.Path('prior7/mre7_easy/manifest.json')
    old=json.loads(manifest.read_text())
    source={c['gbd']:c for c in old['selected_cases']}
    selected=[]
    for fixed in CHOSEN:
        c=source[fixed['gbd']]
        src=pathlib.Path('prior7/mre7_easy')/c['filename']
        raw=src.read_bytes()
        need(sha(raw)==fixed['sha256']==c['sha256'],'original SHA mismatch')
        nv,clauses=x2.parse(src)
        dst=ROOT/c['filename'];dst.write_bytes(raw)
        selected.append(dict(c,**{k:v for k,v in fixed.items() if k not in c},duplicates=len(x6.x3.duplicates(clauses))))
    need(len(selected)==TARGET,'not nine fixed sources')
    save(ROOT/'manifest.json',dict(protocol=PROTO,cases=selected,modes=MODES,cap_s=CAP,reps=REPS,expected_trials=162,known_development_replay=True,not_unseen=True,selection='CMS and Kissat both solved both prior repeats below 5s; nine exact source SHAs fixed before X6 replay',prior_run=42505042425,parent_manifest_sha256=sha(manifest.read_bytes()),no_auto_promotion=True))
    print('X6E_FROZEN',len(selected),flush=True)
def verify():
    m=json.loads((ROOT/'manifest.json').read_text())
    need(m['protocol']==PROTO and m['cap_s']==CAP and m['reps']==REPS and m['modes']==list(MODES),'protocol drift')
    need(len(m['cases'])==TARGET and len({c['sha256'] for c in m['cases']})==TARGET,'source cardinality')
    for c in m['cases']:
        b=(ROOT/c['filename']).read_bytes()
        need(len(b)==c['bytes'] and sha(b)==c['sha256'],'source drift')
    return m
def trial(c,rep,mode):
    src=ROOT/c['filename'];s=seed(c,rep)
    env=os.environ.copy();env.pop('DRNAS_MAX_CONFLICTS',None)
    status='TIMEOUT';model={};stats=None;prep=0.0
    with tempfile.TemporaryDirectory(dir=ROOT) as td:
        start=time.perf_counter();use=src
        if mode not in ('original','kissat'):
            nv,clauses=x2.parse(src)
            changed=x6.transform(clauses,mode)
            # Exact multiset certificate replay is part of E2E preprocessing.
            need(collections.Counter(clauses)==collections.Counter(changed),'multiset changed')
            use=pathlib.Path(td)/'ordered.cnf';x2.write(use,nv,changed)
        prep=time.perf_counter()-start
        p=None;remaining=CAP-prep
        if remaining>0:
            cmd=([str(pathlib.Path('built/bin/kissat_4_0_4').resolve()),'--seed='+str(s),str(use.resolve())] if mode=='kissat' else [str(pathlib.Path('mre_x4/bin/native').resolve()),str(use.resolve()),'x_native',str(s)])
            try:p=subprocess.run(cmd,capture_output=True,text=True,errors='replace',env=env,timeout=remaining)
            except subprocess.TimeoutExpired:pass
        elapsed=time.perf_counter()-start
        if p is not None:
            if mode=='kissat':
                need(p.returncode in (10,20),'Kissat failed '+p.stderr[-300:])
                status='SAT' if p.returncode==10 else 'UNSAT'
                need(('s SATISFIABLE' if status=='SAT' else 's UNSATISFIABLE') in p.stdout,'missing Kissat verdict')
                for line in p.stdout.splitlines():
                    if line.startswith('v '):
                        for l in map(int,line[2:].split()):
                            if l:
                                need(abs(l) not in model or model[abs(l)]==(l>0),'inconsistent model')
                                model[abs(l)]=l>0
            else:
                need(p.returncode==0,'CMS crashed '+p.stderr[-300:])
                gate=x6.x4.base.parse_gate(p.stdout,'x_native')
                need(not gate['applied'],'backend changed CNF')
                status,model,stats=x6.x4.base.cms.parsed_native(p.stdout)
        if elapsed>CAP or status not in ('SAT','UNSAT'):status='TIMEOUT'
        verified=False
        if status=='SAT':x6.x4.base.cms.verify_model(src,model);verified=True
    return dict(protocol=PROTO,gbd=c['gbd'],sha256=c['sha256'],rep=rep,seed=s,seed_policy='sha256_low31_repair_v2',mode=mode,status=status,elapsed_s=round(elapsed,6),preprocessing_s=round(prep,6),PAR2_s=round(elapsed if status in ('SAT','UNSAT') else 2*CAP,6),SAT_original_verified=verified,UNSAT_independent_LRAT=False,native_stats=stats,binary_sha256=sha(pathlib.Path('built/bin/kissat_4_0_4' if mode=='kissat' else 'mre_x4/bin/native').read_bytes()))
def shard(idx):
    m=verify();need(idx in range(SHARDS),'bad shard');c=m['cases'][idx];rows=[]
    for rep in range(REPS):
        order=list(MODES);random.Random(seed(c,rep)).shuffle(order)
        for mode in order:
            r=trial(c,rep,mode);rows.append(r)
            save(ROOT/('shard-%d.json'%idx),rows)
            print('X6E_TRIAL',json.dumps(r,sort_keys=True),flush=True)
    need(len(rows)==18,'short shard');print('X6E_SHARD_PASS',idx,18,flush=True)
def audit():
    m=verify();rows=[];seen=set();bysha={c['sha256']:c for c in m['cases']}
    for i in range(SHARDS):rows+=json.loads((ROOT/('shard-%d.json'%i)).read_text())
    need(len(rows)==162,'missing trials')
    for r in rows:
        c=bysha.get(r['sha256']);need(c and c['gbd']==r['gbd'],'unknown source')
        need(r['protocol']==PROTO and r['rep'] in range(REPS) and r['mode'] in MODES and r['seed']==seed(c,r['rep']),'not paired')
        k=(r['sha256'],r['rep'],r['mode']);need(k not in seen,'duplicate trial');seen.add(k)
        need(r['status'] in ('SAT','UNSAT','TIMEOUT'),'bad verdict')
        need(r['status']!='SAT' or r['SAT_original_verified'],'no witness')
        need(r['status']!='TIMEOUT' or r['PAR2_s']==16,'bad penalty')
        need(r['status']=='TIMEOUT' or (r['elapsed_s']<=CAP and r['PAR2_s']==r['elapsed_s']),'bad solved time')
    per_source=[]
    for c in m['cases']:
        rs=[r for r in rows if r['sha256']==c['sha256']]
        verdicts={r['status'] for r in rs if r['status']!='TIMEOUT'}
        need(len(verdicts)<=1,'SAT/UNSAT contradiction')
        kissat_unsat=any(r['mode']=='kissat' and r['status']=='UNSAT' for r in rs)
        cms_unsat=any(r['mode']!='kissat' and r['status']=='UNSAT' for r in rs)
        for r in rs:
            r['UNSAT_cross_solver_agreement_no_LRAT']=(r['status']=='UNSAT' and kissat_unsat and cms_unsat)
            r['accepted_solved']=r['status']=='SAT' or r['UNSAT_cross_solver_agreement_no_LRAT']
            if not r['accepted_solved']:r['PAR2_s']=16.0
        per_source.append(dict(gbd=c['gbd'],sha256=c['sha256'],PAR2_s={mode:round(sum(r['PAR2_s'] for r in rs if r['mode']==mode),6) for mode in MODES},solved={mode:sum(r['accepted_solved'] for r in rs if r['mode']==mode) for mode in MODES}))
    scores={}
    for mode in MODES:
        rs=[r for r in rows if r['mode']==mode]
        scores[mode]=dict(n=len(rs),solved=sum(r['accepted_solved'] for r in rs),PAR2_s=round(sum(r['PAR2_s'] for r in rs),6))
    for mode,v in scores.items():
        v['speedup_vs_original']=round(scores['original']['PAR2_s']/v['PAR2_s'],6)
        v['speedup_vs_kissat']=round(scores['kissat']['PAR2_s']/v['PAR2_s'],6)
    by_shard=[dict(shard=i,gbd=m['cases'][i]['gbd'],PAR2_s=per_source[i]['PAR2_s'],solved=per_source[i]['solved']) for i in range(SHARDS)]
    out=dict(protocol=PROTO,source_count=9,trials=162,cap_s=CAP,repetitions=REPS,score=scores,per_source=per_source,per_shard=by_shard,preprocessing_included=True,no_bounded_diagnostics=True,UNSAT_independent_LRAT=False,UNSAT_requires_cross_solver_for_scoring=True,globally_exhaustive_history_not_guaranteed=True,no_auto_promotion=True,rows=rows)
    save(ROOT/'report.json',out)
    print('X6E_FINAL',json.dumps({k:v for k,v in out.items() if k not in ('rows','per_source','per_shard')},sort_keys=True),flush=True)
def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=('freeze','verify','shard','audit','selftest'));p.add_argument('--shard',type=int,default=0);a=p.parse_args()
    if a.action=='freeze':freeze()
    elif a.action=='verify':verify();print('X6E_VERIFY_PASS',flush=True)
    elif a.action=='shard':shard(a.shard)
    elif a.action=='selftest':x6.install();x6.x4.selftest();print('X6E_SELFTEST_PASS',flush=True)
    else:audit()
if __name__=='__main__':main()
