#!/usr/bin/env python3
"""V15.2 independent second-seed Hall controls (new formulas), original V15.0 experimental Hall-deficiency SAT kernel vs V14.10 + Kissat + CMS.
Predeclared fixed seeds, nonuniform hard Hall-deficient bipartite instances,
SAT counterparts, redundant noise, and original official SC2026 regressions.
No input selection or adjustment based on V15.0 runtime/answer.
"""
import hashlib,json,os,random,resource,statistics,subprocess,sys,time
from pathlib import Path
sys.path.insert(0,"research/tseitin-replay")
sys.path.insert(0,"research/drnas-sat-v7-8")
from proofcheck import dimacs,verify_model
from official_shortlong_select import download_and_features
SEED=152261101
SOLVERS=("v150_hall","v1410_xor4","kissat_solver","cryptominisat5")
CAP=3.0
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(path,n,clauses):
    Path(path).write_text(f"p cnf {n} {len(clauses)}\n"+"".join(" ".join(map(str,c))+" 0\n" for c in clauses))
def save(path,obj):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(obj,indent=2,sort_keys=True)+"\n")
def make_case(slot,unsat):
    rng=random.Random(SEED+slot*13571+int(unsat)*6703)
    hard_rows=[10,12,14,16][slot]
    other_rows=[8,9,10,11][slot]
    restricted_holes=(hard_rows-2 if unsat else hard_rows+1)
    other_holes=other_rows+3
    rows=hard_rows+other_rows
    resources=restricted_holes+other_holes
    edges=[]
    # Disjoint demand rows; resource cliques imply at-most-one per resource.
    for r in range(rows):
        eligible=range(restricted_holes) if r<hard_rows else range(restricted_holes,resources)
        for h in eligible:edges.append((r,h))
    n=len(edges)
    assert n<4096
    shuffle=list(range(1,n+1));rng.shuffle(shuffle)
    var={e:shuffle[i] for i,e in enumerate(edges)}
    clauses=[];alo=[];negative=[]
    for r in range(rows):
        row=[var[(rr,h)] for rr,h in edges if rr==r]
        rng.shuffle(row);alo.append(row)
    for h in range(resources):
        members=[var[(r,hh)] for r,hh in edges if hh==h]
        for i,a in enumerate(members):
            for b in members[i+1:]:negative.append([-a,-b])
    rng.shuffle(alo);rng.shuffle(negative)
    clauses+=alo+negative
    # Logically weaker redundant clauses that do not change SAT/UNSAT.
    # Neither gate nor independent checker can rely on clause positions.
    weak=[]
    for i in range(min(72,len(negative))):
        ref=negative[i]
        extra=next(x for x in shuffle if x not in set(map(abs,ref)))
        weak.append(ref+[extra])
    for i in range(min(24,len(alo))):
        ref=alo[i]
        extra=next(x for x in shuffle if x not in set(map(abs,ref)))
        weak.append(ref+[extra])
    rng.shuffle(weak)
    clauses=weak[:16]+alo+negative+weak[16:]
    if slot%2:
        # Add separately satisfiable negative clauses on fresh variables.
        # They are ignored by the Hall recognizer but must be checked for SAT.
        for j in range(32):
            a=n+1+(j*3);clauses.append([-a,-(a+1),-(a+2)])
        n+=96
    # Important: SAT controls must remain SAT, not just an assumed label.
    return n,clauses,"UNSAT" if unsat else "SAT",dict(slot=slot,hard_rows=hard_rows,other_rows=other_rows,
             restricted_resources=restricted_holes,other_resources=other_holes,hall_deficient=unsat)
def invoke(solver,path,cap=CAP):
    if solver=="cryptominisat5":cmd=["cryptominisat5","--threads=1",str(path.resolve())]
    elif solver=="kissat_solver":cmd=[str(Path("bin/kissat_solver").resolve()),str(path.resolve())]
    else:cmd=[str(Path("bin",solver).resolve()),str(path.resolve()),str(Path("bin/kissat_solver").resolve()),"0"]
    start=time.perf_counter()
    try:p=subprocess.run(cmd,text=True,capture_output=True,timeout=cap)
    except subprocess.TimeoutExpired:return dict(status="TIMEOUT",seconds=cap,path="timeout",payload=None,model=[])
    seconds=time.perf_counter()-start
    if seconds>cap:return dict(status="TIMEOUT",seconds=cap,path="timeout",payload=None,model=[])
    tags=[line.split("\t",1)[1] for line in p.stdout.splitlines() if line.startswith("DRNAS_HYBRID_RESULT\t")]
    if tags:
        assert p.returncode==0 and len(tags)==1,(solver,p.returncode,p.stderr[-200:])
        payload=json.loads(tags[0])
        status=payload["status"];route=payload["path"]
        model=payload.get("model",[])
    else:
        status={10:"SAT",20:"UNSAT"}.get(p.returncode)
        assert status and "s "+("SATISFIABLE" if status=="SAT" else "UNSATISFIABLE") in p.stdout.splitlines(),(solver,p.returncode,p.stdout[-200:],p.stderr[-250:])
        payload=None;route=("kissat_fallback" if solver.startswith("v") else solver)
        model=[int(x) for line in p.stdout.splitlines() if line.startswith("v ") for x in line.split()[1:] if x!="0"]
    return dict(status=status,seconds=round(seconds,7),path=route,payload=payload,model=model)
def verify_hall(clauses,payload):
    # Independent: no call into C++ extractor or Hall solver, only ORIGINAL CNF.
    assert payload["status"]=="UNSAT" and payload["path"]=="hall_deficiency_exact"
    ids=payload["hall_rows"];groups=payload["resource_groups"]
    assert ids and len(ids)==len(set(ids))
    assert len(groups)<len(ids) and len(groups)>=1
    required=[]
    for i in ids:
        assert isinstance(i,int) and 0<=i<len(clauses)
        c=clauses[i]
        assert len(c)>=2 and len(set(c))==len(c) and all(x>0 for x in c)
        required.extend(c)
    assert len(required)==len(set(required))
    flattened=[x for group in groups for x in group]
    assert all(group and len(group)==len(set(group)) and all(x>0 for x in group) for group in groups)
    assert len(flattened)==len(set(flattened))
    assert set(flattened)==set(required),(len(flattened),len(required))
    negative=set(tuple(sorted((-c[0],-c[1]))) for c in clauses if len(c)==2 and all(v<0 for v in c))
    for g in groups:
        for j,a in enumerate(g):
            for b in g[j+1:]:assert tuple(sorted((a,b))) in negative,(a,b)
    assert payload["deficiency"]==len(ids)-len(groups)
def check_model(n,clauses,model):
    assert model and len({abs(x) for x in model})==n
    verify_model(n,clauses,model)
def setup():
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    resource.setrlimit(resource.RLIMIT_AS,(3*1024**3,3*1024**3))
def measure(slot):
    setup();out=Path("out");out.mkdir()
    cases=[make_case(slot,False),make_case(slot,True)]
    reports=[]
    for k,(n,clauses,label,meta) in enumerate(cases):
        p=out/(f"case{k}.cnf");write(p,n,clauses)
        trials=[]
        for rep in range(2):
            order=list(SOLVERS)
            random.Random(SEED+slot*99+k*13+rep).shuffle(order)
            for solver in order:
                ans=invoke(solver,p)
                checked=False
                if ans["status"]=="SAT":
                    check_model(n,clauses,ans["model"]);checked=True
                if ans["path"]=="hall_deficiency_exact":
                    verify_hall(clauses,ans["payload"]);checked=True
                assert ans["status"] in (label,"TIMEOUT"),(slot,k,solver,ans["status"],label)
                item=dict(rep=rep,solver=solver,status=ans["status"],seconds=ans["seconds"],
                          route=ans["path"],independent_check=checked)
                trials.append(item)
                print("V150_TRIAL",slot,k,json.dumps(item,sort_keys=True),flush=True)
        reports.append(dict(case=k,n=n,m=len(clauses),label=label,features=meta,sha256=sha(p),trials=trials))
    save(out/"results.json",dict(slot=slot,cap=CAP,repeats=2,reports=reports))
    print("V150_SYNTH_PASS",slot,flush=True)
def official(slot):
    setup();out=Path("out");out.mkdir()
    frozen=json.loads(Path("prior/v148-frozen-manifest.json").read_text())
    assert len(frozen["cases"])==6
    results=[]
    for c in frozen["cases"][slot*3:slot*3+3]:
        p=out/(c["id"]+".cnf")
        original=download_and_features(c["id"],p)
        assert original["sha256"]==c["sha256"]
        n,clauses=dimacs(p);trials=[]
        for rep in range(2):
            order=["v150_hall","v1410_xor4","kissat_solver"]
            random.Random(SEED+int(c["id"][:8],16)+rep).shuffle(order)
            for solver in order:
                ans=invoke(solver,p,3)
                checked=False
                if ans["status"]=="SAT":
                    check_model(n,clauses,ans["model"]);checked=True
                if ans["path"]=="hall_deficiency_exact":
                    verify_hall(clauses,ans["payload"]);checked=True
                assert ans["status"] in (c["label"],"TIMEOUT"),(solver,c["id"],ans["status"],c["label"])
                item=dict(rep=rep,solver=solver,status=ans["status"],seconds=ans["seconds"],
                          route=ans["path"],independent_check=checked)
                trials.append(item)
                print("V150_OFFICIAL_TRIAL",c["id"],json.dumps(item,sort_keys=True),flush=True)
        results.append(dict(case=c["id"],label=c["label"],sha256=sha(p),trials=trials))
        assert sha(p)==c["sha256"]
        p.unlink()
    save(out/"results.json",dict(slot=slot,cap=3,repeats=2,reports=results))
    print("V150_OFFICIAL_PASS",slot,flush=True)
def audit():
    allrows=[]
    for group,slots in (("synthetic",4),("official",2)):
        for slot in range(slots):
            p=Path("all")/(f"v150-{group}-{slot}")/"results.json"
            data=json.loads(p.read_text())
            assert data["slot"]==slot
            assert len(data["reports"])==(2 if group=="synthetic" else 3)
            for case in data["reports"]:
                attempts=case["trials"];assert len(attempts)==(8 if group=="synthetic" else 6)
                keys={(x["rep"],x["solver"]) for x in attempts}
                assert len(keys)==len(attempts)
                for row in attempts:
                    assert row["status"] in (case["label"],"TIMEOUT")
                    allrows.append(dict(group=group,slot=slot,case=case["case"],label=case["label"],**row))
    assert len(allrows)==4*2*2*4+2*3*2*3==100,len(allrows)
    reports=[]
    for group in ("synthetic","official"):
        for solver in SOLVERS:
            part=[x for x in allrows if x["group"]==group and x["solver"]==solver]
            if not part:continue
            vals=[x["seconds"] if x["status"]!="TIMEOUT" else 2*CAP for x in part]
            row=dict(group=group,solver=solver,attempts=len(part),
                     solved=sum(x["status"]!="TIMEOUT" for x in part),
                     check_count=sum(x["independent_check"] for x in part),
                     PAR2_mean_s=round(statistics.mean(vals),7),
                     paths=sorted(set(x["route"] for x in part)))
            reports.append(row)
            print("V150_AUDIT",json.dumps(row,sort_keys=True),flush=True)
    save("v150-final.json",dict(protocol="v150_Hall_matching_trial",all_results=allrows,summary=reports))
    print("V150_FINAL_AUDIT_PASS",len(allrows),flush=True)
if __name__=="__main__":
    if sys.argv[1]=="measure":measure(int(sys.argv[2]))
    elif sys.argv[1]=="official":official(int(sys.argv[2]))
    elif sys.argv[1]=="audit":audit()
    else:raise SystemExit("measure/official/audit")
