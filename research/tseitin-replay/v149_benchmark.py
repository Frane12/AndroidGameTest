"""V14.9 exact 2-SAT + sparse XOR3..6 prospective benchmark and proof replay.
Cases/seeds/limits are frozen by this file before the V14.9 benchmark starts.
Regression controls run original SC2026 inputs with unchanged hashes.
"""
import hashlib,itertools,json,os,random,resource,statistics,subprocess,sys,time
from pathlib import Path
sys.path.insert(0,"research/tseitin-replay")
from xor4_benchmark import write_cnf
from v147_subset_bench import verify_model,verify_affine_unsat,parity_rows
from proofcheck import dimacs
SOLVERS=("v149_budgeted","v147_subset_xor4","kissat_solver","cryptominisat5")
CAP=4.0
SEED=149261101
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,obj):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(obj,sort_keys=True,indent=2)+"\n")
def run(solver,path,cap=CAP):
    if solver=="cryptominisat5":args=["cryptominisat5","--threads=1",str(path.resolve())]
    elif solver.startswith("v14"):args=[str(Path("bin",solver).resolve()),str(path.resolve()),str(Path("bin/kissat_solver").resolve()),"0"]
    else:args=[str(Path("bin",solver).resolve()),str(path.resolve())]
    start=time.perf_counter()
    try: p=subprocess.run(args,text=True,capture_output=True,timeout=cap)
    except subprocess.TimeoutExpired:return dict(status="TIMEOUT",seconds=cap,route="timeout",model=[],answer={})
    seconds=time.perf_counter()-start
    if seconds>cap:return dict(status="TIMEOUT",seconds=cap,route="timeout",model=[],answer={})
    tags=[line.split("\t",1)[1] for line in p.stdout.splitlines() if line.startswith("DRNAS_HYBRID_RESULT\t")]
    if tags:
        assert len(tags)==1 and p.returncode==0,(solver,p.returncode,p.stdout[-500:],p.stderr[-200:])
        answer=json.loads(tags[0])
        return dict(status=answer["status"],seconds=seconds,route=answer["path"],model=answer.get("model",[]),answer=answer)
    status={10:"SAT",20:"UNSAT"}.get(p.returncode)
    assert status and "s "+("SATISFIABLE" if status=="SAT" else "UNSATISFIABLE") in p.stdout.splitlines(),(solver,p.returncode,p.stdout[-250:],p.stderr[-250:])
    model=[int(x) for line in p.stdout.splitlines() if line.startswith("v ") for x in line.split()[1:] if x!="0"]
    return dict(status=status,seconds=seconds,route="kissat_fallback" if solver.startswith("v14") else solver,model=model,answer={})
def verify_xor6_unsat(clauses,answer):
    assert answer["path"]=="affine_subset_xor6" and answer["status"]=="UNSAT"
    groups={}
    for c in clauses:
        if not 2<=len(c)<=6:continue
        key=tuple(sorted(map(abs,c)))
        if len(set(key))!=len(key):continue
        order=sorted(c,key=lambda x:abs(x))
        mask=sum(1<<i for i,lit in enumerate(order) if lit<0)
        groups.setdefault(key,set()).add(mask)
    rows=[]
    for key,patterns in sorted(groups.items()):
        width=len(key)
        rhs=int(0 in patterns)
        expected={m for m in range(1<<width) if (m.bit_count()%2)!=rhs}
        if patterns!=expected:continue
        related=[c for c in clauses if len(c)==width and tuple(sorted(map(abs,c)))==key]
        # local independent truth-table equivalence of the source block
        for bits in itertools.product((0,1),repeat=width):
            env=dict(zip(key,bits))
            actual=all(any(bool(env[abs(lit)])==(lit>0) for lit in c) for c in related)
            assert actual==(sum(bits)%2==rhs)
        rows.append((set(key),rhs))
    assert len(rows)==answer["equations"] and rows
    ids=answer["proof_rows"]
    assert ids and len(ids)==len(set(ids))
    vars=set();rhs=0
    for i in ids:
        assert 0<=i<len(rows)
        v,r=rows[i];vars.symmetric_difference_update(v);rhs^=r
    assert vars==set() and rhs==1
def verify_2sat_unsat(clauses,answer):
    assert answer["path"]=="two_sat_scc" and answer["status"]=="UNSAT"
    edges=set()
    for c in clauses:
        assert len(c) in (1,2)
        if len(c)==1:edges.add((-c[0],c[0]))
        else:edges.add((-c[0],c[1]));edges.add((-c[1],c[0]))
    v=answer["variable"]
    a,b=answer["implication_paths"]
    assert a[0]==v and a[-1]==-v and b[0]==-v and b[-1]==v
    for p in (a,b):
        assert len(p)>1
        for x,y in zip(p,p[1:]):assert (x,y) in edges
def graph(n,width,rng):
    assert n%2==0 and width in (3,4,5,6)
    edges=set()
    for k in range(1,1+width//2):
        for i in range(n):
            e=tuple(sorted((i,(i+k)%n)))
            edges.add(e)
    if width%2:
        for i in range(n//2):
            edges.add((i,i+n//2))
    edges=sorted(edges)
    assert len(edges)==n*width//2,len(edges)
    rng.shuffle(edges)
    supports=[[] for _ in range(n)]
    for j,(u,v) in enumerate(edges,1):supports[u].append(j);supports[v].append(j)
    assert all(len(group)==width for group in supports)
    return supports,len(edges)
def make_xor(slot,rep_case):
    width=(3,4,5,6)[slot]
    odd=rep_case%2==1
    scattered=rep_case//2==1
    n=(32,32,40,40)[slot]
    rng=random.Random(SEED+slot*10007+rep_case*59)
    groups,nvars=graph(n,width,rng)
    charge=[rng.randrange(2) for _ in range(n)]
    charge[0]=(sum(charge[1:])%2)^int(odd)
    blocks=[]
    for support,rhs in zip(groups,charge):
        block=[]
        for mask in range(1<<width):
            if mask.bit_count()%2!=rhs:
                c=[-v if (mask>>i)&1 else v for i,v in enumerate(support)]
                rng.shuffle(c);block.append(c)
        blocks.append(block)
    rng.shuffle(blocks)
    originals=[c for block in blocks for c in block]
    if scattered:rng.shuffle(originals)
    # Exactly redundant weakening of source XOR clauses: all SAT models
    # of the source remain valid, UNSAT is preserved. 7-literal distractors
    # ahead of the genuine XOR clauses break V14.7's fixed first384 gate.
    filler=[]
    for j in range(400):
        origin=originals[j%len(originals)]
        others=[v for v in range(1,nvars+1) if v not in set(map(abs,origin))]
        extra=rng.sample(others,7-len(origin))
        filler.append(origin+extra)
    return nvars,filler+originals,("UNSAT" if odd else "SAT"),dict(width=width,scattered=scattered,noise=400,n=n)
def make_2sat(case):
    rng=random.Random(SEED+889*case)
    n=120;target={v:rng.randrange(2) for v in range(1,n+1)}
    clauses=[]
    for i in range(400):
        a,b=rng.sample(range(1,n+1),2)
        la=(a if target[a] else -a)
        lb=b if rng.randrange(2) else -b
        if rng.randrange(2):la,lb=lb,la
        clauses.append([la,lb])
    if case==1:
        clauses+=[[1],[-1]]
        label="UNSAT"
    else:label="SAT"
    if case==2:clauses.append([1,2,3])  # mixed: must retain fallback
    return n,clauses,label,dict(kind="2sat",mixed=case==2)
def measure(slot):
    out=Path("out");out.mkdir(exist_ok=True)
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    resource.setrlimit(resource.RLIMIT_AS,(3*1024**3,3*1024**3))
    cases=[make_xor(slot,i) for i in range(4)] if slot<4 else [make_2sat(i) for i in range(3)]
    reports=[]
    for i,(n,clauses,label,meta) in enumerate(cases):
        path=out/("case-"+str(i)+".cnf")
        write_cnf(path,n,clauses)
        rows=[]
        for rep in range(2):
            order=list(SOLVERS)
            random.Random(SEED+slot*611+i*7+rep).shuffle(order)
            for solver in order:
                result=run(solver,path)
                status=result["status"];checked=False
                assert status in (label,"TIMEOUT"),(slot,i,solver,result)
                if status=="SAT":
                    verify_model(n,clauses,result["model"]);checked=True
                elif result["route"]=="affine_subset_xor6":
                    verify_xor6_unsat(clauses,result["answer"]);checked=True
                elif result["route"]=="affine_subset_xor4":
                    verify_affine_unsat(clauses,result["answer"]);checked=True
                elif result["route"]=="two_sat_scc":
                    verify_2sat_unsat(clauses,result["answer"]);checked=True
                row=dict(solver=solver,rep=rep,status=status,seconds=round(result["seconds"],7),route=result["route"],proof_checked=checked)
                rows.append(row)
                print("V149_TRIAL",slot,i,json.dumps(row,sort_keys=True),flush=True)
        reports.append(dict(case=i,sha256=sha(path),label=label,variables=n,clauses=len(clauses),meta=meta,trials=rows))
    save(out/"results.json",dict(slot=slot,cap=CAP,reps=2,reports=reports))
    print("V149_SLOT_PASS",slot,len(reports),flush=True)
def official(slot):
    from official_shortlong_select import download_and_features
    out=Path("out");out.mkdir(exist_ok=True)
    manifest=json.loads(Path("prior/v148-frozen-manifest.json").read_text())
    assert len(manifest["cases"])==6
    resource.setrlimit(resource.RLIMIT_AS,(3*1024**3,3*1024**3))
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    reports=[]
    for case in manifest["cases"][slot*2:slot*2+2]:
        p=out/(case["id"]+".cnf")
        source=download_and_features(case["id"],p)
        assert source["sha256"]==case["sha256"]
        n,clauses=dimacs(p);rows=[]
        for rep in range(2):
            ss=("v149_budgeted","v147_subset_xor4","kissat_solver")
            order=list(ss);random.Random(SEED+int(case["id"][:8],16)+rep).shuffle(order)
            for solver in order:
                result=run(solver,p,12.0)
                status=result["status"];checked=False
                assert status in (case["label"],"TIMEOUT"),(case["id"],solver,status)
                if status=="SAT":
                    verify_model(n,clauses,result["model"]);checked=True
                elif result["route"]=="affine_subset_xor6":
                    verify_xor6_unsat(clauses,result["answer"]);checked=True
                elif result["route"]=="affine_subset_xor4":
                    verify_affine_unsat(clauses,result["answer"]);checked=True
                elif result["route"]=="two_sat_scc":
                    verify_2sat_unsat(clauses,result["answer"]);checked=True
                row=dict(solver=solver,rep=rep,status=status,seconds=round(result["seconds"],7),route=result["route"],proof_checked=checked)
                rows.append(row)
                print("V149_OFFICIAL_TRIAL",case["id"],json.dumps(row,sort_keys=True),flush=True)
        reports.append(dict(case=case["id"],sha256=sha(p),label=case["label"],trials=rows))
        assert sha(p)==case["sha256"]
        p.unlink()
    save(out/"results.json",dict(slot=slot,official=True,cap=12.0,reps=2,reports=reports))
    print("V149_OFFICIAL_SLOT_PASS",slot,len(reports),flush=True)
def audit():
    rows=[]
    for slot in range(8):
        name=("official" if slot>=5 else "synthetic")
        folder=Path("all")/(f"v149-{name}-{slot-5 if slot>=5 else slot}")
        p=folder/"results.json"
        data=json.loads(p.read_text())
        assert data["slot"]==(slot-5 if slot>=5 else slot)
        assert len(data["reports"])==(2 if slot>=5 else 3 if slot==4 else 4)
        for case in data["reports"]:
            target=case["label"];attempts=case["trials"]
            assert len(attempts)==(6 if slot>=5 else 8)
            for row in attempts:
                assert row["status"] in (target,"TIMEOUT")
                rows.append(dict(group=name,slot=slot,case=case["case"],label=target,meta=case.get("meta"),**row))
    summary=[]
    for group in ("synthetic","official"):
        rr=[r for r in rows if r["group"]==group]
        for solver in SOLVERS:
            subset=[r for r in rr if r["solver"]==solver]
            if not subset:continue
            cap=12.0 if group=="official" else CAP
            valid=[x["seconds"] for x in subset if x["status"]!="TIMEOUT"]
            par2=[x["seconds"] if x["status"]!="TIMEOUT" else 2*cap for x in subset]
            report=dict(group=group,solver=solver,attempts=len(subset),solved=len(valid),
                        independently_checked=sum(x["proof_checked"] for x in subset),
                        median_s=round(statistics.median(valid),6) if valid else None,
                        par2_s=round(statistics.mean(par2),6),
                        paths=sorted(set(x["route"] for x in subset)))
            summary.append(report)
            print("V149_AUDIT",json.dumps(report,sort_keys=True),flush=True)
    save("v149-final.json",dict(protocol="V14.9-budgeted-XOR6-and-2SAT",reports=summary,trials=rows))
    print("V149_FINAL_AUDIT_PASS",len(rows),flush=True)
if __name__=="__main__":
    if sys.argv[1]=="measure":measure(int(sys.argv[2]))
    elif sys.argv[1]=="official":official(int(sys.argv[2]))
    elif sys.argv[1]=="audit":audit()
    else:raise SystemExit("use measure / official / audit")
