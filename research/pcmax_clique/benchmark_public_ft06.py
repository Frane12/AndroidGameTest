#!/usr/bin/env python3
"""External JSPLIB ft06: exact time-indexed CNF vs structured CP-SAT.
Source pinned to Git blob SHA; published optimum is 55. Research reference
benchmark, NOT a proprietary real-factory dataset or blind holdout.
"""
import argparse,hashlib,json,os,subprocess,time
from pathlib import Path
from collections import defaultdict

FT06_SHA="24430d17a2d6d6021c7c147419e123536098051f"
def parse(data):
    lines=[x.strip() for x in data.decode("ascii").splitlines() if x.strip() and not x.startswith("#")]
    n,m=map(int,lines[0].split())
    if n!=6 or m!=6 or len(lines)!=7:raise ValueError("unexpected external source")
    jobs=[]
    for line in lines[1:]:
        values=list(map(int,line.split()))
        if len(values)!=12:raise ValueError("invalid job line")
        steps=[(values[i],values[i+1]) for i in range(0,12,2)]
        if sorted(k for k,d in steps)!=list(range(6)) or min(d for k,d in steps)<=0:raise ValueError("invalid route")
        jobs.append(steps)
    return jobs

def domain(jobs,H):
    ops=[];byjob=[];bymachine=defaultdict(list)
    for j,steps in enumerate(jobs):
        total=sum(d for _,d in steps);used=0;sequence=[]
        for step,(machine,d) in enumerate(steps):
            row={"id":len(ops),"machine":machine,"dur":d,"early":used,"late":H-(total-used)}
            if row["late"]<row["early"]:raise ValueError("impossible horizon domain")
            ops.append(row);sequence.append(row);bymachine[machine].append(row);used+=d
        byjob.append(sequence)
    return ops,byjob,bymachine

def make_cnf(ops,byjob,bymachine):
    nextid=0;clauses=[];choices={}
    def new():
        nonlocal nextid
        nextid+=1;return nextid
    def add(*c):clauses.append(tuple(c))
    for o in ops:
        vars_=[(t,new()) for t in range(o["early"],o["late"]+1)]
        choices[o["id"]]=vars_;xs=[x for t,x in vars_]
        add(*xs) # at least one start
        if len(xs)>1:
            prev=new();add(-xs[0],prev)
            for x in xs[1:-1]:
                s=new();add(-x,s);add(-prev,s);add(-x,-prev);prev=s
            add(-xs[-1],-prev)
    # Exact source precedence and same-machine disjunctive constraints.
    for seq in byjob:
        for a,b in zip(seq,seq[1:]):
            for ta,xa in choices[a["id"]]:
                for tb,xb in choices[b["id"]]:
                    if tb<ta+a["dur"]:add(-xa,-xb)
    for machine,rows in bymachine.items():
        for i,a in enumerate(rows):
            for b in rows[i+1:]:
                for ta,xa in choices[a["id"]]:
                    for tb,xb in choices[b["id"]]:
                        if ta<tb+b["dur"] and tb<ta+a["dur"]:add(-xa,-xb)
    return nextid,clauses

def cp_solve(arm,ops,byjob,bymachine,nvars,clauses,budget):
    from ortools.sat.python import cp_model
    tick=time.perf_counter();model=cp_model.CpModel()
    if arm=="raw":
        x=[None]+[model.NewBoolVar("v"+str(i)) for i in range(1,nvars+1)]
        for cl in clauses:model.AddBoolOr([x[v] if v>0 else x[-v].Not() for v in cl])
    else:
        starts={};byres=defaultdict(list)
        for o in ops:
            t=model.NewIntVar(o["early"],o["late"],"t"+str(o["id"]))
            starts[o["id"]]=t
            byres[o["machine"]].append(model.NewFixedSizeIntervalVar(t,o["dur"],"itv"+str(o["id"])))
        for xs in byres.values():model.AddNoOverlap(xs)
        for seq in byjob:
            for a,b in zip(seq,seq[1:]):model.Add(starts[a["id"]]+a["dur"]<=starts[b["id"]])
    build=time.perf_counter()-tick
    solver=cp_model.CpSolver();solver.parameters.num_search_workers=1
    solver.parameters.max_time_in_seconds=budget
    status=solver.Solve(model)
    return {"status":solver.StatusName(status),"model_build_s":round(build,6),
            "solver_s":round(solver.WallTime(),6),
            "branches":solver.NumBranches(),"conflicts":solver.NumConflicts()}

def run(source,output,arm,H,budget,binary):
    data=source.read_bytes()
    blob=hashlib.sha1(("blob %d\0"%len(data)).encode()+data).hexdigest()
    if blob!=FT06_SHA:raise ValueError("unfrozen upstream source")
    output.mkdir(parents=True,exist_ok=True);started=time.perf_counter()
    jobs=parse(data);ops,byjob,bymachine=domain(jobs,H)
    nvars,clauses=make_cnf(ops,byjob,bymachine)
    cnf=output/"original.cnf"
    with cnf.open("w") as file:
        file.write(f"p cnf {nvars} {len(clauses)}\n")
        for cl in clauses:file.write(" ".join(map(str,cl))+" 0\n")
    encoding_s=round(time.perf_counter()-started,6)
    if arm in ("raw","structured"):result=cp_solve(arm,ops,byjob,bymachine,nvars,clauses,budget)
    else:
        argv=[str(binary),str(cnf),"--mode","core","--time",str(budget)]
        if arm=="native-clique":
            argv+=["--pcmax-clique-only","--pcmax-clique-budget-ms",str(int(budget*900)),
                   "--pcmax-certificate",str(output/"certificate.json")]
        p=subprocess.run(argv,text=True,capture_output=True,timeout=budget+10)
        (output/"native.log").write_text(p.stdout+"\n"+p.stderr)
        result={"status":{0:"UNKNOWN",10:"SAT",20:"UNSAT"}.get(p.returncode,"ERROR"),"exit_code":p.returncode}
    result.update(arm=arm,deadline=H,expected="SAT" if H>=55 else "UNSAT",
                  cnf_vars=nvars,cnf_clauses=len(clauses),
                  cnf_sha256=hashlib.sha256(cnf.read_bytes()).hexdigest(),
                  upstream_git_blob_sha1=blob,encoding_s=encoding_s,
                  e2e_s=round(time.perf_counter()-started,6))
    actual=result["status"]
    if actual in ("FEASIBLE","OPTIMAL","SAT"):actual="SAT"
    elif actual in ("INFEASIBLE","UNSAT"):actual="UNSAT"
    else:actual="UNKNOWN"
    if actual!="UNKNOWN" and actual!=result["expected"]:raise AssertionError("wrong SAT/UNSAT "+str(result))
    print("FT06_RESULT "+json.dumps(result,sort_keys=True),flush=True)
    (output/"result.json").write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--source",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--arm",choices=["raw","structured","native-clique","native-cdcl"],required=True)
    p.add_argument("--deadline",type=int,required=True)
    p.add_argument("--budget",type=float,default=8)
    p.add_argument("--binary",type=Path,default=Path("build/drnas-pcmax"))
    a=p.parse_args()
    try:os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    except (AttributeError,OSError):pass
    run(a.source,a.out,a.arm,a.deadline,a.budget,a.binary.resolve())
