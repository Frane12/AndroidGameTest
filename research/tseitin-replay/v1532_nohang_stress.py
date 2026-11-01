#!/usr/bin/env python3
"""Adversarial V15.3-vs-V15.3.1 no-hang validation (not a public SAT benchmark).
The generated SAT/UNSAT answers are CONSTRUCTIVELY guaranteed. Always verify
SAT models against original CNF and independent V15.3 UNSAT certificates.
A timeout is a test failure for the new solver, not an expected SAT result.
"""
import json,random,statistics,subprocess,time
from pathlib import Path
from v153_proof_checker import verify_certificate

OUT=Path("v1532-nohang-stress");OUT.mkdir(exist_ok=True)
SOLVERS={"v1531":Path("/tmp/v1531_nohang"),
         "v1532":Path("/tmp/v1532_prefix"),
         "kissat":Path("/tmp/kissat_solver")}
CAP=5
REPS=3
def emit(name,n,clauses,expected):
    p=OUT/(name+".cnf")
    p.write_text(f"p cnf {n} {len(clauses)}\n"+"".join(
        " ".join(map(str,cl))+" 0\n" for cl in clauses))
    return dict(name=name,path=p,n=n,clauses=clauses,expected=expected)

def cases():
    rng=random.Random(153120261101)
    out=[]
    # Unique 3-SAT supports: a known SAT model with variable 1 true.
    common=[]
    seen=set()
    while len(common)<3000:
        v,w=rng.sample(range(2,1000),2)
        key=tuple(sorted((1,v,w)))
        if key in seen:continue
        seen.add(key)
        common.append([1,(-v if rng.randrange(2) else v),
                          (-w if rng.randrange(2) else w)])
    out.append(emit("unique_3sat_3000",1000,common,"SAT"))
    # Heavy UP: unit x1 makes every 30-literal clause containing -x1
    # need inspection; x2 makes those clauses satisfied. New unit-work cap
    # must not give an unsound answer after partial processing.
    cl=[[1],[2]]
    for i in range(9000):
        vs=rng.sample(range(3,340),28)
        cl.append([-1,2]+[v if rng.randrange(2) else -v for v in vs])
    out.append(emit("up_heavy_9000_long",340,cl,"SAT"))
    # Unit conflict must remain certified even with a large irrelevant tail.
    cl=[[1],[-1]]
    for _ in range(4200):
        a,b,c=rng.sample(range(2,230),3)
        cl.append([1,a,b,c])
    out.append(emit("unit_contradiction_with_tail",230,cl,"UNSAT"))
    # Very wide variable range must bypass the structural algorithms.
    out.append(emit("vars_5001_guard",5001,[[1]],"SAT"))
    # Pigeonhole-shape-negative missing: do not activate expensive matching.
    cl=[]
    for i in range(200):
        st=1+4*i
        cl.append([st,st+1,st+2,st+3])
    out.append(emit("many_positive_no_hall_edges",800,cl,"SAT"))
    # Binary equivalent chain SAT, full assignment is all true.
    cl=[]
    for i in range(1,1000):
        cl.extend([[-i,i+1],[i,-(i+1)]])
    cl.append([1,2,3])
    out.append(emit("binary_chain_1000",1000,cl,"SAT"))
    # Unary chain forces x100, plus contradiction (UP proof).
    cl=[[1]]
    for i in range(1,100):cl.append([-i,i+1])
    cl.append([-100])
    out.append(emit("unit_chain_unsat",100,cl,"UNSAT"))
    # Plain random-like all-positive 3-SAT with 1 guaranteed SAT.
    cl=[[1]+rng.sample(range(2,250),2) for _ in range(2000)]
    out.append(emit("repeated_plain_3sat",250,cl,"SAT"))
    return out

def parse_output(stdout):
    payload=None
    for line in stdout.splitlines():
        if line.startswith("DRNAS_HYBRID_RESULT\t"):
            payload=json.loads(line.split("\t",1)[1])
            break
    if payload:return payload["status"],payload,payload.get("model",[])
    if "s UNSATISFIABLE" in stdout:return "UNSAT",None,[]
    if "s SATISFIABLE" in stdout:
        lits=[int(x) for line in stdout.splitlines() if line.startswith("v ")
              for x in line.split()[1:] if x!="0"]
        return "SAT",None,lits
    return "UNKNOWN",None,[]

def model_ok(c,model):
    assignment={}
    for lit in model:
        if not isinstance(lit,int) or lit==0 or abs(lit)>c["n"]:return False
        assignment[abs(lit)]=(lit>0)
    return bool(assignment) and all(any(assignment.get(abs(v))==(v>0)
                         for v in cl) for cl in c["clauses"])

def main():
    samples=cases()
    rows=[]
    for c in samples:
        for name,exe in SOLVERS.items():
            for rep in range(REPS):
                args=[str(exe),str(c["path"]),str(SOLVERS["kissat"]),"1"]
                if name=="kissat":args=args[:2]
                start=time.perf_counter()
                try:
                    p=subprocess.run(args,capture_output=True,text=True,timeout=CAP)
                    duration=time.perf_counter()-start
                    status,payload,model=parse_output(p.stdout)
                    valid=status==c["expected"] and (status!="SAT" or model_ok(c,model))
                    if status=="UNSAT" and name!="kissat":
                        valid=valid and verify_certificate(payload,c["clauses"])
                except subprocess.TimeoutExpired:
                    duration=CAP;status="TIMEOUT";valid=False
                row=dict(case=c["name"],solver=name,rep=rep,
                         seconds=round(duration,7),status=status,correct=valid)
                rows.append(row)
                # Old V15.3 may legitimately exceed the cap; the test asserts
                # the new guarded solver alone does not hang or misclassify.
                if name=="v1532" and not valid:
                    (OUT/"stress.json").write_text(json.dumps(rows,indent=2))
                    raise RuntimeError("V15.3.2 failed bounded stress: "+str(row))
    summary={}
    for name in SOLVERS:
        rr=[r for r in rows if r["solver"]==name]
        summary[name]=dict(correct=sum(r["correct"] for r in rr),
                           total=len(rr),timeout=sum(r["status"]=="TIMEOUT" for r in rr),
                           sum_case_medians=round(sum(statistics.median(
                           r["seconds"] for r in rr if r["case"]==c["name"])
                           for c in samples),6))
    (OUT/"stress.json").write_text(json.dumps({"summary":summary,"results":rows},indent=2))
    print("V1532_STRESS_PASS",json.dumps(summary,sort_keys=True),flush=True)
if __name__=="__main__":main()
