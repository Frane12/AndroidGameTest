#!/usr/bin/env python3
"""PCMAX SCALE5: precommitted complex source-identical vs structured CP-SAT experiment.
Generated synthetic connected scheduling; NOT a blind real-world benchmark.
Expected outcomes are NEVER passed to the solvers.
"""
from __future__ import annotations
import argparse
import collections
import hashlib
import json
import os
import random
import resource
import subprocess
import tempfile
import time
from pathlib import Path

def overlap(a, b, c, d):
    return a < d and c < b

def hall_case(bins, sat, seed, dense=False):
    rng=random.Random(seed)
    urgent=bins if sat else bins+1
    allowed=[]
    for j in range(urgent):
        allowed.append(list(range(bins)) if dense else sorted(set(rng.sample(range(bins),min(5,bins)))))
    for k in range(12):
        allowed.append(sorted(set([bins+k, rng.randrange(bins),bins+12+k%3])))
    clauses=[];entries=[];bybin=collections.defaultdict(list)
    for j,slots in enumerate(allowed):
        opts=[]
        for slot in slots:
            v=len(entries)+1
            entries.append({"job":j,"slot":slot,"var":v})
            opts.append(v)
            bybin[slot].append(v)
        clauses.append(opts)
        for i,a in enumerate(opts):
            for b in opts[i+1:]: clauses.append([-a,-b])
    for vs in bybin.values():
        for i,a in enumerate(vs):
            for b in vs[i+1:]: clauses.append([-a,-b])
    return {"kind":"hall","label":"SAT" if sat else "UNSAT","jobs":len(allowed),
            "slots":max(bybin)+1,"entries":entries,
            "clauses":clauses,"nvars":len(entries),"seed":seed}

def interval_case(n, machines, sat, seed):
    rng=random.Random(seed)
    crew_count=machines//2
    jobs=[];cursor=[0]*crew_count
    for j in range(n):
        crew=(j*7+j//crew_count)%crew_count
        dur=rng.randint(2,4);setup=1
        machine=crew*2+rng.randint(0,1)
        t=cursor[crew]+rng.randint(0,1)
        cursor[crew]=t+dur+setup+rng.randint(0,1)
        jobs.append({"duration":dur,"setup":setup,"crew":crew,"machine":machine,
                     "planned":t,"urgent":False})
    horizon=max(cursor)+14
    maint={}
    for machine in range(machines):
        if machine%3==0:maint[machine]=(horizon-9,horizon-6)
    if not sat:
        # An overloaded time window on one crew: 8 * 3 > 16.
        # No preselected Hall witnesses are supplied to either solver.
        for k in range(8):
            jobs.append({"duration":3,"setup":1,"crew":0,"machine":k%2,
                         "planned":0,"urgent":True})
    entries=[];job_entries=collections.defaultdict(list)
    for j,job in enumerate(jobs):
        if job["urgent"]:
            machine_choices=[0,1]; starts=list(range(0,14,2))
        else:
            c=job["crew"]
            machine_choices=[2*c,2*c+1]
            if j%5==0:machine_choices.append(2*((c+1)%crew_count))
            starts=[job["planned"]+delta for delta in [-2,0,2]]
        for m in sorted(set(machine_choices)):
            for t in starts:
                if t<0 or t+job["duration"]+job["setup"]>horizon:continue
                if m in maint and overlap(t,t+job["duration"]+job["setup"],*maint[m]):
                    continue
                v=len(entries)+1
                e={"job":j,"machine":m,"crew":m//2,"start":t,"dur":job["duration"],
                   "occ":job["duration"]+job["setup"],"var":v}
                entries.append(e);job_entries[j].append(e)
        if not job_entries[j]:
            raise RuntimeError("empty placement domain")
        if not job["urgent"]:
            assert any(e["start"]==job["planned"] and e["machine"]==job["machine"]
                       for e in job_entries[j]), "lost known feasible witness"
    # Place only precedence edges compatible with the constructive SAT witness.
    order=sorted(range(n),key=lambda j:jobs[j]["planned"])
    prec=set()
    for k,a in enumerate(order):
        for offset in (3,11):
            if k+offset>=n:continue
            b=order[k+offset]
            if jobs[a]["planned"]+jobs[a]["duration"]<=jobs[b]["planned"]:
                prec.add((a,b))
    clauses=[]
    for j in range(len(jobs)):
        vars_=[e["var"] for e in job_entries[j]]
        clauses.append(vars_)
        for ia,a in enumerate(vars_):
            for b in vars_[ia+1:]:clauses.append([-a,-b])
    # Every cross-job temporal conflict is represented by the identical pairwise CNF.
    # Sweep through sorted starts, which avoids O(V^2) comparisons.
    for key in ("machine","crew"):
        groups=collections.defaultdict(list)
        for e in entries:groups[e[key]].append(e)
        for group in groups.values():
            group.sort(key=lambda e:e["start"])
            for i,a in enumerate(group):
                end=a["start"]+(a["occ"] if key=="machine" else a["dur"])
                for b in group[i+1:]:
                    if b["start"]>=end:break
                    if a["job"]==b["job"]:continue
                    if overlap(a["start"],end,b["start"],b["start"]+
                               (b["occ"] if key=="machine" else b["dur"])):
                        clauses.append([-a["var"],-b["var"]])
    for a,b in sorted(prec):
        for p in job_entries[a]:
            for q in job_entries[b]:
                if p["start"]+p["dur"]>q["start"]:
                    clauses.append([-p["var"],-q["var"]])
    # Source semantics are a conjunction, so removing exact repeated binary
    # clauses preserves equivalence and reduces overhead on both arms.
    seen=set();filtered=[]
    for c in clauses:
        if len(c)==2 and c[0]<0 and c[1]<0:
            pair=tuple(sorted(c))
            if pair in seen:continue
            seen.add(pair)
        filtered.append(c)
    return {"kind":"interval","label":"SAT" if sat else "UNSAT","jobs":len(jobs),
            "machines":machines,"horizon":horizon,"maintenance":maint,
            "precedence":sorted(prec),"entries":entries,"clauses":filtered,
            "nvars":len(entries),"seed":seed}

def dump_cnf(case, path):
    sha=hashlib.sha256()
    with path.open("wb") as f:
        def write(b):
            f.write(b);sha.update(b)
        write(f'p cnf {case["nvars"]} {len(case["clauses"])}\n'.encode())
        for clause in case["clauses"]:
            write((" ".join(map(str,clause))+" 0\n").encode())
    return sha.hexdigest()

def cp_solve(case, arm, budget):
    import ortools
    from ortools.sat.python import cp_model
    started=time.perf_counter()
    model=cp_model.CpModel()
    x=[None]+[model.NewBoolVar(f"x{i}") for i in range(1,case["nvars"]+1)]
    if arm=="raw":
        for cl in case["clauses"]:
            model.AddBoolOr([x[v] if v>0 else x[-v].Not() for v in cl])
    else:
        jobs=collections.defaultdict(list)
        for e in case["entries"]:jobs[e["job"]].append(e)
        for choices in jobs.values():
            model.AddExactlyOne([x[e["var"]] for e in choices])
        if case["kind"]=="hall":
            slots=collections.defaultdict(list)
            for e in case["entries"]:slots[e["slot"]].append(x[e["var"]])
            for vars_ in slots.values():
                model.AddAtMostOne(vars_)
        else:
            per_m=collections.defaultdict(list)
            per_crew=collections.defaultdict(list)
            for e in case["entries"]:
                lit=x[e["var"]]
                per_m[e["machine"]].append(model.NewOptionalFixedSizeIntervalVar(
                    e["start"],e["occ"],lit,f"m_{e['var']}"))
                per_crew[e["crew"]].append(model.NewOptionalFixedSizeIntervalVar(
                    e["start"],e["dur"],lit,f"c_{e['var']}"))
            for group in per_m.values():model.AddNoOverlap(group)
            for group in per_crew.values():model.AddNoOverlap(group)
            for a,b in case["precedence"]:
                model.Add(sum((e["start"]+e["dur"])*x[e["var"]] for e in jobs[a]) <=
                          sum(e["start"]*x[e["var"]] for e in jobs[b]))
    build=time.perf_counter()-started
    solver=cp_model.CpSolver()
    solver.parameters.num_search_workers=1
    solver.parameters.max_time_in_seconds=max(0.01,budget)
    # Time limit only constrains solver, but E2E includes model construction.
    status=solver.Solve(model)
    wall=time.perf_counter()-started
    answer=solver.StatusName(status)
    return {"status":answer,"e2e_s":round(wall,5),"build_s":round(build,5),
            "solve_wall_s":round(solver.WallTime(),5),
            "branches":int(solver.NumBranches()),"conflicts":int(solver.NumConflicts()),
            "ortools":ortools.__version__}

def native_solve(case, cnf, binary, budget, workdir):
    started=time.perf_counter()
    cert=workdir/"native_hall_cert.json"
    if cert.exists():cert.unlink()
    p=subprocess.run([str(binary),str(cnf),"--mode","core","--time",str(budget),
          "--pcmax-hall-only","--pcmax-hall-budget-ms",str(int(budget*900)),
          "--pcmax-certificate",str(cert)],text=True,capture_output=True,
          timeout=budget+15)
    wall=time.perf_counter()-started
    label="UNSAT" if p.returncode==20 else ("UNKNOWN" if p.returncode==0 else "ERROR")
    result={"status":label,"e2e_s":round(wall,5),"exit_code":p.returncode,
            "telemetry":[l for l in p.stdout.splitlines() if l.startswith("c PCMAX_HALL")][-1:]}
    if label=="UNSAT":
        if not cert.exists():raise RuntimeError("no certificate for structural UNSAT")
        check=subprocess.run(["python3",str(Path(__file__).parent/"verify_hall.py"),
                              str(cnf),str(cert)],capture_output=True,text=True,timeout=20)
        result["check_s"]=round(time.perf_counter()-started-wall,5)
        result["certificate_verified"]=check.returncode==0
        result["e2e_with_checker_s"]=round(time.perf_counter()-started,5)
        result["checker_details"]=check.stdout.strip()[-500:]
        if check.returncode!=0:raise RuntimeError("independent proof checker FAILED: "+check.stderr)
    return result

def experiment(name, out, arm, binary, budget):
    presets={
      "HALL_DENSE_UNSAT_32":("hall",32,False,True,4821),
      "HALL_SPARSE_UNSAT_800":("hall",800,False,False,4822),
      "HALL_SPARSE_SAT_800":("hall",800,True,False,4823),
      "HALL_SPARSE_UNSAT_1600":("hall",1600,False,False,4824),
      "WINDOW_SAT_80":("window",80,12,True,8721),
      "WINDOW_UNSAT_80":("window",80,12,False,8722),
      "WINDOW_SAT_200":("window",200,16,True,8723),
      "WINDOW_UNSAT_200":("window",200,16,False,8724),
      "WINDOW_UNSAT_400":("window",400,24,False,8725)
    }
    if name not in presets:raise ValueError("unlisted case")
    args=presets[name]
    case=hall_case(args[1],args[2],args[4],args[3]) if args[0]=="hall" else interval_case(args[1],args[2],args[3],args[4])
    out.mkdir(parents=True,exist_ok=True)
    cnf=out/(name+".cnf")
    sha=dump_cnf(case,cnf)
    metadata={k:v for k,v in case.items() if k not in ("clauses","entries")}
    metadata.update(name=name,sha256=sha,clauses=len(case["clauses"]),
                    vars=case["nvars"],domain_assignments=len(case["entries"]))
    (out/(name+".json")).write_text(json.dumps(metadata,indent=2,sort_keys=True))
    started=time.perf_counter()
    if arm=="native":
        res=native_solve(case,cnf,binary,budget,out)
    else:
        res=cp_solve(case,arm,budget)
    res.update(case=name,arm=arm,label=case["label"],sha256=sha,
               jobs=case["jobs"],vars=case["nvars"],clauses=len(case["clauses"]),
               total_driver_wall_s=round(time.perf_counter()-started,5))
    if res["status"] in ("OPTIMAL","FEASIBLE","INFEASIBLE"):
        got="SAT" if res["status"] in ("OPTIMAL","FEASIBLE") else "UNSAT"
        if got!=case["label"]:raise RuntimeError("WRONG RESULT "+name+":"+str(res))
    if res["status"]=="UNSAT" and case["label"]=="SAT":
        raise RuntimeError("WRONG UNSAT")
    print("COMPLEX_RESULT "+json.dumps(res,sort_keys=True),flush=True)
    (out/(name+"-"+arm+".json")).write_text(json.dumps(res,indent=2,sort_keys=True)+"\n")

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--case",required=True)
    ap.add_argument("--arm",choices=["native","raw","structured"],required=True)
    ap.add_argument("--out",type=Path,default=Path("results/complex5"))
    ap.add_argument("--binary",type=Path,default=Path("build/drnas-pcmax"))
    ap.add_argument("--budget",type=float,default=8.0)
    a=ap.parse_args()
    try:
        cpu=min(os.sched_getaffinity(0));os.sched_setaffinity(0,{cpu})
    except (AttributeError,OSError):pass
    experiment(a.case,a.out,a.arm,a.binary.resolve(),a.budget)
