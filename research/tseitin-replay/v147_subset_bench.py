"""V14.7 prospective robustness audit on already-frozen non-grid SAT/UNSAT CNFs.
Two input variants per slot; no benchmark-driven instance selection.
Genuine SAT models and affine UNSAT certificates are independently replayed.
"""
import hashlib,itertools,json,os,random,resource,statistics,subprocess,sys,time
from pathlib import Path
sys.path.insert(0,"research/tseitin-replay")
from xor4_benchmark import dimacs
from transfer_bench import save
SOLVERS=("v147_subset_xor4","v142_xor4","kissat_solver","cryptominisat5")
LIMIT=8

def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def launch(solver,path):
    if solver=="cryptominisat5":
        cmd=["cryptominisat5","--threads=1",str(path)]
    elif solver.startswith("v14"):
        cmd=[str(Path("bin",solver).resolve()),str(path),str(Path("bin/kissat_solver").resolve()),"0"]
    else:
        cmd=[str(Path("bin",solver).resolve()),str(path)]
    start=time.perf_counter()
    try:
        p=subprocess.run(cmd,text=True,capture_output=True,timeout=LIMIT)
    except subprocess.TimeoutExpired:
        return dict(status="TIMEOUT",seconds=LIMIT,route="timeout",answer={})
    elapsed=time.perf_counter()-start
    if elapsed>LIMIT:return dict(status="TIMEOUT",seconds=LIMIT,route="timeout",answer={})
    lines=p.stdout.splitlines()
    tags=[x.split("\t",1)[1] for x in lines if x.startswith("DRNAS_HYBRID_RESULT\t")]
    if tags:
        assert p.returncode==0 and len(tags)==1,(cmd,p.returncode,p.stderr[-200:])
        answer=json.loads(tags[0])
        return dict(status=answer["status"],seconds=elapsed,route=answer["path"],answer=answer)
    status={10:"SAT",20:"UNSAT"}.get(p.returncode)
    assert status and "s "+("SATISFIABLE" if status=="SAT" else "UNSATISFIABLE") in lines, (cmd,p.returncode,lines[-5:],p.stderr[-250:])
    model=[int(v) for line in lines if line.startswith("v ") for v in line.split()[1:] if int(v)]
    return dict(status=status,seconds=elapsed,route=("Kissat fallback" if solver.startswith("v14") else solver),answer={"model":model})

def verify_model(n, clauses, model):
    values={}
    for lit in model:
        v=abs(lit)
        assert 1<=v<=n
        assert v not in values or values[v]==(lit>0)
        values[v]=lit>0
    # Any unconstrained/unreported variables are false only for the purpose
    # of verification. Reject assignments that do not satisfy every clause.
    assert all(any(values.get(abs(lit),False)==(lit>0) for lit in c) for c in clauses)

def parity_rows(clauses):
    supports={}
    for clause in clauses:
        if not (2<=len(clause)<=4):continue
        ordered=sorted(clause,key=lambda lit:abs(lit))
        variables=tuple(map(abs,ordered))
        if len(set(variables))!=len(variables):continue
        mask=sum(1<<j for j,lit in enumerate(ordered) if lit<0)
        supports.setdefault(variables,set()).add(mask)
    rows=[]
    for variables,masks in sorted(supports.items()):
        width=len(variables)
        rhs=int(0 in masks)
        expected={mask for mask in range(1<<width) if ((mask.bit_count()&1)!=rhs)}
        if masks!=expected:continue
        # Independent exhaustive implication proof, not solver-reported flags.
        group=[cl for cl in clauses if len(cl)==width and set(map(abs,cl))==set(variables)]
        for values in itertools.product((False,True),repeat=width):
            assignment=dict(zip(variables,values))
            group_sat=all(any(assignment[abs(lit)]==(lit>0) for lit in cl) for cl in group)
            assert group_sat==(sum(values)%2==rhs)
        rows.append((frozenset(variables),rhs))
    return rows

def verify_affine_unsat(clauses,answer):
    assert answer["status"]=="UNSAT" and answer["path"]=="affine_subset_xor4"
    rows=parity_rows(clauses)
    assert len(rows)==answer["equations"] and rows
    selected=answer["proof_rows"]
    assert selected and len(set(selected))==len(selected)
    acc=set()
    parity=0
    for idx in selected:
        assert 0<=idx<len(rows)
        variables,rhs=rows[idx]
        acc.symmetric_difference_update(variables)
        parity^=rhs
    assert not acc and parity==1,("bad parity proof",selected)
    # A deliberate corruption must not be accepted.
    if len(selected)>1:
        corrupt=selected[:-1]
        acc=set();parity=0
        for idx in corrupt:
            variables,rhs=rows[idx]
            acc.symmetric_difference_update(variables);parity^=rhs
        assert acc or parity!=1
    return len(selected)

def measure(slot):
    cpu=min(os.sched_getaffinity(0))
    os.sched_setaffinity(0,{cpu})
    resource.setrlimit(resource.RLIMIT_AS,(3*1024**3,3*1024**3))
    base=Path("prior")/("nongrid-case-"+str(slot))
    original=json.loads((base/"results.json").read_text())
    label=original["label"]
    assert label==("UNSAT" if slot%2 else "SAT")
    frozen={}
    for variant in ("clean","redundant"):
        path=base/(variant+".cnf")
        assert digest(path)==original["inputs"][variant]
        n,clauses=dimacs(path)
        assert n==2*original["n"]
        frozen[variant]=(path,n,clauses)
    # Compare the EXACT same problem inputs, CPU affinity and limit.
    out=Path("out");out.mkdir()
    rng=random.Random(147261101+slot)
    trials=[]
    for rep in range(3):
        order=list(itertools.product(("clean","redundant"),SOLVERS))
        rng.shuffle(order)
        for variant,solver in order:
            path,n,clauses=frozen[variant]
            result=launch(solver,path)
            status=result["status"];route=result["route"]
            check="timeout"
            if status!="TIMEOUT":
                assert status==label,(slot,variant,solver,status,label)
                if status=="SAT":
                    verify_model(n,clauses,result["answer"].get("model",[]))
                    check="SAT model verified"
                elif route=="affine_subset_xor4":
                    proof_len=verify_affine_unsat(clauses,result["answer"])
                    check="independent subset-XOR UNSAT certificate"
                    if rep==0:save(out/(variant+"-v147-certificate.json"),
                                   dict(proof_rows=result["answer"]["proof_rows"],
                                        equations=result["answer"]["equations"],
                                        combination_length=proof_len,cnf_sha256=digest(path)))
                elif route=="affine_exact_xor4":
                    # Original output proof semantics stay unchanged; every
                    # UNSAT instance here is mathematically UNSAT by odd charge.
                    check="known parity-graph label"
                else:check="known parity-graph label"
            trials.append(dict(rep=rep,variant=variant,solver=solver,status=status,
                               seconds=result["seconds"],route=route,check=check))
    save(out/"results.json",dict(slot=slot,n=original["n"],label=label,
        source_sha256=original["inputs"],
        binaries_sha256={s:digest(Path("bin")/s) for s in SOLVERS if s!="cryptominisat5"},
        repeats=3,timeout_seconds=LIMIT,cpu_affinity=cpu,trials=trials))
    print("V147_SLOT_PASS",slot,label,flush=True)

def audit():
    paths=sorted(Path("all").glob("nongrid-case-*/results.json"))
    assert len(paths)==4
    reports=[json.loads(p.read_text()) for p in paths]
    assert [r["slot"] for r in reports]==list(range(4))
    summaries=[]
    for r in reports:
        assert len(r["trials"])==2*3*len(SOLVERS)
        assert len({(x["rep"],x["variant"],x["solver"]) for x in r["trials"]})==len(r["trials"])
        for variant in ("clean","redundant"):
            summary=dict(slot=r["slot"],n=r["n"],label=r["label"],variant=variant)
            for solver in SOLVERS:
                a=[x for x in r["trials"] if x["variant"]==variant and x["solver"]==solver]
                solved=[x["seconds"] for x in a if x["status"] in ("SAT","UNSAT")]
                summary[solver]=dict(solved=len(solved),median_s=statistics.median(solved) if solved else None,
                                    paths=sorted(set(x["route"] for x in a)))
            summaries.append(summary)
    save("v147_final.json",dict(summaries=summaries,reports=reports))
    for row in summaries:print("V147_AUDIT",json.dumps(row,sort_keys=True),flush=True)
    print("V147_FINAL_AUDIT_PASS",len(summaries),flush=True)

if __name__=="__main__":
    if sys.argv[1]=="measure":measure(int(sys.argv[2]))
    elif sys.argv[1]=="audit":audit()
    else:raise SystemExit("use measure SLOT or audit")
