"""Measure all other SC2024 main-track 'tseitin-formulas' on one core."""
import csv,hashlib,io,itertools,json,os,random,resource,subprocess,sys,time,urllib.request,zipfile
from collections import defaultdict
from pathlib import Path
from proofcheck import dimacs,check_hidden,check_whole,verify_model,rhs_of
sys.path.insert(0,'research/drnas-sat-v7-8')
from official_shortlong_select import download_and_features
from v145_blind_bench import verify_propagated_parity
from v1311_local_xor import extract,proof_valid
root='https://raw.githubusercontent.com/satcompetition/2024/fa06f42b914ec155b2120aef936ce9305a3e4128/downloads/'
def pinned(file,sha):
    raw=urllib.request.urlopen(root+file,timeout=60).read()
    assert hashlib.sha256(raw).hexdigest()==sha
    return raw
def global_contradiction(cs):
    groups=defaultdict(list)
    for c in cs:groups[tuple(sorted(map(abs,c)))].append(c)
    remaining=set();rhs=0
    for support,clauses in groups.items():
        if len(support)>6 or len(set(support))!=len(support):return False
        allowed=0
        for bits in itertools.product((False,True),repeat=len(support)):
            env=dict(zip(support,bits))
            if all(any(env[abs(x)]==(x>0) for x in c) for c in clauses):
                allowed |= 1<<sum((int(b)<<i) for i,b in enumerate(bits))
        mask_even=sum(1<<i for i in range(1<<len(support)) if i.bit_count()%2==0)
        mask_all=(1<<(1<<len(support)))-1
        if allowed not in (mask_even,mask_even^mask_all):return False
        rhs^=int(allowed!=mask_even);remaining.symmetric_difference_update(support)
    return not remaining and rhs==1

def history():
    histories=[('prior131','v13_manifest.json'),('prior-mini','official_mini_manifest.json'),
        ('prior-v100','v100_manifest.json'),('prior-v132','v132_manifest.json'),
        ('prior-v138','v138_manifest.json'),('prior-v139','v139_selector.json'),
        ('prior-v1313','v1313_30_manifest.json'),('prior-v1316','v1313_30_manifest.json'),
        ('prior-v143','v143_new30_source.json'),('prior-v144','v144_new30_source.json'),
        ('prior-v145','v145_new30_source.json')]
    ids,shas=set(),set()
    for folder,name in histories:
        [path]=Path(folder).rglob(name)
        cases=json.loads(path.read_text())['cases']
        ids.update(c['id'] for c in cases);shas.update(c['sha256'] for c in cases)
    assert len(ids)>=326 and len(shas)>=326
    return ids,shas
def bench():
    meta=pinned('meta.csv','c8703ab84f28b4369c96bbdfd3d6cc0f00b0b5212bc58cd2d5d7eca48cafc0ce')
    zipped=pinned('detailed_results.zip','dfdf1d515fc95e95d3b76f907a2ce67932af1f8905f90c3dd7f743ea6c2b751a')
    table=csv.DictReader(io.StringIO(zipfile.ZipFile(io.BytesIO(zipped)).read('detailed_main.csv').decode()))
    labels={r['hash']:r['vresult'].upper() for r in table}
    prior_ids,prior_shas=history()
    frozen=[]
    for line in meta.decode().splitlines()[1:]:
        case,name,family,*_=line.split()
        if family!='tseitin-formulas' or case=='c69c5163c9087ffe770743bd4cdafcc9':continue
        path=Path(case+'.cnf')
        info=download_and_features(case,path)
        frozen.append(dict(id=case,name=name,sha256=info['sha256'],official=labels[case],
                          seen=case in prior_ids or info['sha256'] in prior_shas))
    assert len(frozen)==4
    Path('external_manifest.json').write_text(json.dumps(frozen,indent=2))
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    resource.setrlimit(resource.RLIMIT_AS,(3*1024**3,3*1024**3))
    rng=random.Random(174120261101)
    trials=[]
    for rep in range(2):
        for c in (frozen if not rep else reversed(frozen)):
            p=Path(c['id']+'.cnf')
            assert hashlib.sha256(p.read_bytes()).hexdigest()==c['sha256']
            n,cs=dimacs(p)
            proof=global_contradiction(cs)
            modes=['v142_fastgate','v145_native','kissat_solver'];rng.shuffle(modes)
            for m in modes:
                args=['bin/'+m,str(p)]
                if m!='kissat_solver':args+=['bin/kissat_solver','0']
                status='TIMEOUT';route='timeout';s=8;checked=False
                start=time.monotonic()
                try:
                    op=subprocess.run(args,timeout=8,text=True,capture_output=True)
                    elapsed=time.monotonic()-start
                    if elapsed<=8:
                        s=elapsed
                        tags=[x for x in op.stdout.splitlines() if x.startswith('DRNAS_') and '_RESULT\t' in x]
                        if tags:
                            assert op.returncode==0 and len(tags)==1
                            a=json.loads(tags[0].split('\t')[1])
                            status=a['status'];route=a['path']
                            if route=='hidden_parity_gf2':check_hidden(cs,a['proof'])
                            elif route=='affine_exact':check_whole(n,cs,a)
                            elif route=='propagated_hidden_parity':assert verify_propagated_parity(p,a['proof'],a['unit_steps'])
                            elif route=='local_xor_verified':
                                _,_,eq,diag=extract(p)
                                assert diag['extraction_complete'] and proof_valid(eq,a['proof_equation_indices'],(),1)
                            else:raise ValueError(route)
                            checked=True
                        else:
                            status={10:'SAT',20:'UNSAT'}[op.returncode];route='Kissat'
                            if status=='SAT':
                                verify_model(n,cs,[int(l) for x in op.stdout.splitlines() if x.startswith('v ') for l in x.split()[1:]])
                                checked=True
                            elif proof:checked=True
                        assert c['official'] in (status,'UNKNOWN')
                except subprocess.TimeoutExpired:pass
                row=dict(name=c['name'],mode=m,rep=rep,status=status,path=route,seconds=s,checked=checked,independent_global_xor_unsat=proof)
                trials.append(row);print(row,flush=True)
    Path('external_trials.json').write_text(json.dumps(trials,indent=2))
if __name__=='__main__':bench()
