#!/usr/bin/env python3
"""R76: exact weighted TSP OPTIMIZATION vs pinned Kissat, not just one SAT decision.

Three frozen arms on same weighted graphs:
  R75 shared UB, 4 workers separately pinned to four CPUs;
  R75 shared UB, 4 workers competing on ONE CPU (resource-matched);
  pinned clean Kissat, ONE CPU, repeated exact SAT <= L thresholds.

Kissat knows only nearest-neighbor initial UB and a mathematically sound
1-tree LB, NOT the R75/held-karp optimum. Per-call CNF generation, process
startup, solver runtime, SAT witness validation and total wall are charged
against the SAME per-arm cap. Unproven timeout is reported unproven.
This is a benchmark of algorithms/encoding, not intrinsic Kissat superiority
or a fair claim of "same solver" runtime. No soft deferral.
"""
from __future__ import annotations
import argparse, hashlib, json, os, random, subprocess
import tempfile, time
from pathlib import Path
import drnas_r75_shared_route as drnas
import drnas_r72_tsp_sat as tsp
import r32p_real_satcomp26_benchmark as verify

PROTO="DRNAS-R76-TSP-OPTIMIZATION-VS-KISSAT-20261104-v1"
CASES=((12,"uniform"),(14,"cluster"),(16,"uniform"),(18,"cluster"))
MODES=("drnas_shared_1core","drnas_shared_4core","kissat_exact_1core")
REPS=2;SHARDS=len(CASES);CAP=20.0

def ck(ok,detail):
    if not ok:raise RuntimeError("R76_FAIL_CLOSED "+str(detail))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def one_tree_lb(d):
    """1-tree: MST on vertices 1..n-1, plus two distinct cheapest edges to 0."""
    n=len(d);ck(n>=4,"tiny graph")
    price={i:d[1][i] for i in range(2,n)}
    weight=0
    while price:
        j=min(price,key=lambda i:(price[i],i))
        weight+=price.pop(j)
        for k in price:
            if d[j][k]<price[k]:price[k]=d[j][k]
    first_two=sorted(d[0][1:])[:2]
    return weight+sum(first_two)

def parse_witness(output,n):
    vals={}
    for line in output.splitlines():
        if line.startswith("v "):
            for word in line[2:].split():
                v=int(word)
                if v:vals[abs(v)]=v>0
    ck(vals,"SAT with missing witness")
    tour=[]
    for t in range(n):
        cities=[i for i in range(n) if vals.get(1+t*n+i,False)]
        ck(len(cities)==1,"one-hot city selection wrong")
        tour.append(cities[0])
    return tour+[0]

def kissat_optimize(d,kissat,cap):
    """No optimum leakage: adaptively binary search using a real pinned Kissat."""
    start=time.monotonic()
    nearest,upper=drnas.nearest_neighbor(d)
    lower=one_tree_lb(d)
    ck(lower<=upper,"invalid 1-tree lower bound")
    initial=upper;best=nearest
    calls=[];encoded=0;solver_s=0.;prep_s=0.;proofs=0
    with tempfile.TemporaryDirectory(prefix="r76-kissat-") as td:
        while lower<upper and time.monotonic()-start<cap:
            bound=(lower+upper-1)//2
            before=time.monotonic()
            f=tsp.encode(d,bound)
            target=Path(td)/"decision.cnf"
            f.save(target)
            encode_elapsed=time.monotonic()-before
            prep_s+=encode_elapsed;encoded+=len(f.rows)
            remaining=cap-(time.monotonic()-start)
            if remaining<=.01:break
            cmdstart=time.monotonic()
            try:
                p=subprocess.run([str(kissat),str(target)],
                    capture_output=True,text=True,errors="replace",
                    timeout=remaining)
            except subprocess.TimeoutExpired:
                solver_s+=time.monotonic()-cmdstart
                calls.append(dict(bound=bound,answer="TIMEOUT",
                    clauses=len(f.rows),encode_s=round(encode_elapsed,6)))
                break
            solver_s+=time.monotonic()-cmdstart
            ck(p.returncode in (10,20),
               "Kissat crash rc="+str(p.returncode)+" stderr="+p.stderr[-250:])
            if p.returncode==10:
                verify.verify_sat_witness(target,p.stdout)
                route=parse_witness(p.stdout,len(d))
                drnas.validate(d,route,drnas.route_cost(d,route))
                cost=drnas.route_cost(d,route)
                ck(cost<=bound and cost<upper,"SAT tour violates threshold or fails improvement")
                upper=cost;best=route
                answer="SAT"
            else:
                lower=bound+1;proofs+=1
                answer="UNSAT"
            ck(lower<=upper,"bounds crossed")
            calls.append(dict(bound=bound,answer=answer,clauses=len(f.rows),
                encode_s=round(encode_elapsed,6),
                remaining_lb=lower,remaining_ub=upper))
    total=time.monotonic()-start
    proved=(lower==upper and total<=cap)
    drnas.validate(d,best,upper)
    return dict(mode="kissat_exact_1core",best=upper,tour=best,
        initial_upper=initial,proven_optimum=proved,
        elapsed_s=round(min(total,cap),6),
        wall_including_setup_s=round(total,6),
        cpu_cores=1,solver_calls=len(calls),unsat_proofs=proofs,
        sat_proofs=sum(x["answer"]=="SAT" for x in calls),
        encode_clauses_total=encoded,
        encode_s=round(prep_s,6),solve_s=round(solver_s,6),
        lower_bound=lower, upper_bound=upper,calls=calls)

def freeze(folder):
    root=Path(folder);root.mkdir(parents=True,exist_ok=True)
    cases=[]
    for n,kind in CASES:
        coords,d=drnas.make_graph(n,kind)
        nearest,upper=drnas.nearest_neighbor(d)
        lb=one_tree_lb(d)
        ck(lb<=upper,"bad LB")
        obj=dict(protocol=PROTO,n=n,kind=kind,coords=coords,
            distances=d,nearest_tour=nearest,initial_upper=upper,
            one_tree_lb=lb)
        name=f"r76_{n}_{kind}.json"
        p=root/name
        p.write_text(json.dumps(obj,sort_keys=True,separators=(',',':'))+"\n")
        cases.append(dict(name=name,sha256=sha(p),n=n,kind=kind,
            initial_upper=upper,one_tree_lb=lb))
        print("R76_FROZEN",name,"initial",upper,"sound_lb",lb,flush=True)
    m=dict(protocol=PROTO,cases=cases,reps=REPS,cap_s=CAP,
        shards=SHARDS,modes=list(MODES),
        kissat_binary_source_run=41684183452,
        notes=[
          "Kissat is a SAT solver; this benchmark includes TSP->SAT encoding and binary-search optimizer overhead",
          "Kissat gets same initial nearest-neighbor feasible upper bound but no DRNAS optimum",
          "Kissat SAT witness verified against generated CNF and original TSP route",
          "Kissat UNSAT no independent DRAT/LRAT; optimum cross-checked with DRNAS if proven",
          "DRNAS 1core uses four processes pinned to one physical core, including IPC overhead",
          "DRNAS 4core uses four distinct physical cores; not resource-equal to Kissat 1core",
          "One timed per-arm attempt includes DRNAS setup/IPC or Kissat encoding + restarts",
          "Synthetic coordinate graphs (n=12,14,16,18), not TSPLIB; only two repetitions",
          "R75 baseline has no soft deferral"
        ])
    (root/"manifest.json").write_text(json.dumps(m,indent=2)+"\n")
    (root/"source.sha256").write_text("".join(c["sha256"]+"  "+c["name"]+"\n"for c in cases))
    print("R76_FREEZE_PASS",len(cases),sha(root/"manifest.json"),flush=True)

def selftest(kissat=None):
    # Independently brute-force small graph and compare mathematically sound 1tree.
    import itertools
    for n in (5,6,7):
        d=drnas.make_graph(n,"uniform")[1]
        opt=min(drnas.route_cost(d,(0,)+p+(0,))
            for p in itertools.permutations(range(1,n)))
        ck(one_tree_lb(d)<=opt,"bad MST 1-tree bound")
        if kissat is not None:
            result=kissat_optimize(d,kissat,cap=12.)
            ck(result["proven_optimum"] and result["best"]==opt,
               "Kissat CNF exact optimization selftest wrong "+str(result))
    print("R76_1TREE_AND_KISSAT_EXACT_SELFTEST_PASS",flush=True)

def drnas_mode(d,cpus,mode,cap):
    cores=cpus[:4] if mode=="drnas_shared_4core" else [cpus[0]]*4
    start=time.monotonic()
    output=drnas.trial(d,"shared",cores,cap=cap)
    total=time.monotonic()-start
    # Explicitly charge startup not counted by R75 trial's worker-clock field.
    return dict(mode=mode,best=output["best"],tour=output["tour"],
        initial_upper=output["initial_upper"],
        proven_optimum=output["proven_optimum"] and total<=cap,
        elapsed_s=round(min(total,cap),6),
        wall_including_setup_s=round(total,6),
        cpu_cores=4 if mode=="drnas_shared_4core" else 1,
        worker_elapsed_s=output["elapsed_s"],workers_completed=output["finished_workers"],
        visited_nodes=output["nodes"],pruned=output["pruned"],
        signals=output["signals_sent"])

def measure(a):
    root=Path(a.sources);m=json.loads((root/"manifest.json").read_text())
    ck(m["protocol"]==PROTO and m["cap_s"]==CAP
       and m["modes"]==list(MODES),"manifest mismatch")
    ck(0<=a.shard<SHARDS,"bad shard")
    binary=Path(a.kissat).resolve()
    ck(binary.is_file(),"missing pinned Kissat")
    cpus=sorted(os.sched_getaffinity(0))
    ck(len(cpus)>=4,"need at least 4 available runner cores")
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    (out/"meta.json").write_text(json.dumps(dict(
      protocol=PROTO,shard=a.shard,manifest_sha=sha(root/"manifest.json"),
      kissat_binary_sha=sha(binary),cpus=cpus[:4]),indent=2)+"\n")
    rows=[]
    for c in m["cases"][a.shard::SHARDS]:
        spec=root/c["name"]
        ck(sha(spec)==c["sha256"],"frozen source drift")
        case=json.loads(spec.read_text());d=case["distances"]
        ck(drnas.nearest_neighbor(d)[1]==c["initial_upper"] and
           one_tree_lb(d)==c["one_tree_lb"],"frozen bounds drift")
        for rep in range(REPS):
            order=list(MODES)
            random.Random(int(hashlib.sha256(
              (c["sha256"]+str(rep)+PROTO).encode()).hexdigest(),16)).shuffle(order)
            for mode in order:
                base=os.sched_getaffinity(0)
                try:
                    if mode=="kissat_exact_1core":
                        os.sched_setaffinity(0,{cpus[0]})
                        z=kissat_optimize(d,binary,CAP)
                    else:
                        os.sched_setaffinity(0,set(cpus[:4]))
                        z=drnas_mode(d,cpus,mode,CAP)
                finally:
                    os.sched_setaffinity(0,base)
                ck(z["mode"]==mode and z["initial_upper"]==c["initial_upper"],
                   "bad starting optimum or mode")
                drnas.validate(d,z["tour"],z["best"])
                ck(z["best"]<=c["initial_upper"],"worse than initial upper")
                row=dict(case=c["name"],source_sha=c["sha256"],rep=rep,**z)
                rows.append(row)
                (out/"rows.json").write_text(json.dumps(rows,indent=2)+"\n")
                print("R76_TRIAL",c["name"],"rep",rep,mode,"best",z["best"],
                    "PROVEN" if z["proven_optimum"] else "UNPROVEN",
                    "wall",z["elapsed_s"],"cpu_cores",z["cpu_cores"],
                    "kissat_calls",z.get("solver_calls",0),flush=True)
    ck(len(rows)==len(m["cases"][a.shard::SHARDS])*REPS*len(MODES),
       "incomplete runner")

def audit(a):
    root=Path(a.sources);m=json.loads((root/"manifest.json").read_text())
    ck(m["protocol"]==PROTO and len(m["cases"])==SHARDS,"manifest")
    rows=[];seen=set();bins=set()
    for shard in range(SHARDS):
        f=Path(a.combined)/f"r76-shard-{shard}"/"results"
        meta=json.loads((f/"meta.json").read_text())
        ck(meta["protocol"]==PROTO and meta["shard"]==shard and
           meta["manifest_sha"]==sha(root/"manifest.json"),"source SHA cross-shard")
        bins.add(meta["kissat_binary_sha"])
        part=json.loads((f/"rows.json").read_text())
        ck(len(part)==len(m["cases"][shard::SHARDS])*REPS*len(MODES),
           "missing trials")
        for z in part:
            key=(z["case"],z["rep"],z["mode"])
            ck(key not in seen,"duplicate row");seen.add(key)
            c=next(c for c in m["cases"] if c["name"]==z["case"])
            ck(z["source_sha"]==c["sha256"] and z["mode"] in MODES,
               "mixed case or wrong mode")
            d=json.loads((root/c["name"]).read_text())["distances"]
            drnas.validate(d,z["tour"],z["best"])
            ck(z["cpu_cores"]==(4 if z["mode"]=="drnas_shared_4core" else 1),
               "core resource mismatch")
        rows.extend(part)
    ck(len(bins)==1 and len(rows)==SHARDS*REPS*len(MODES),"incomplete frozen audit")
    for c in m["cases"]:
        for rep in range(REPS):
            grp=[z for z in rows if z["case"]==c["name"] and z["rep"]==rep]
            proven={z["best"] for z in grp if z["proven_optimum"]}
            ck(len(proven)<=1,"CONFLICTING PROVEN OPTIMAL TOURS")
            if proven:
                ck(all(z["best"]>=next(iter(proven)) for z in grp),
                   "valid route shorter than proven optimum")
    summary={}
    for mode in MODES:
        part=[z for z in rows if z["mode"]==mode]
        summary[mode]=dict(attempts=len(part),
            proven=sum(z["proven_optimum"] for z in part),
            total_wall_s=round(sum(z["elapsed_s"] for z in part),6),
            total_PAR2_s=round(sum(z["elapsed_s"] if z["proven_optimum"]
                  else 2*CAP for z in part),6),
            kissat_solver_calls=sum(z.get("solver_calls",0) for z in part),
            total_best_length=sum(z["best"] for z in part),
            cores_per_trial=4 if mode=="drnas_shared_4core" else 1)
    report=dict(protocol=PROTO,binary_sha=next(iter(bins)),
        summary=summary,rows=rows,limitations=m["notes"])
    Path(a.json).write_text(json.dumps(report,indent=2)+"\n")
    lines=["# DRNAS R76: R75 route sharing vs pinned clean Kissat optimizing exact TSP",
      "Kissat is given the same nearest-neighbor feasible route upper bound, "+
      "then dynamically searches strictly better route costs with exact SAT threshold decisions.",
      "No optimum given upfront. Proof = lower bound meets upper bound without timeout.",
      "| Solver/method | Cores | Proven / 8 | Total wall s | PAR2 s | SAT calls |",
      "|---|---:|---:|---:|---:|---:|"]
    for mode in MODES:
        x=summary[mode];lines.append(f"| {mode} | {x['cores_per_trial']} | {x['proven']}/8 | {x['total_wall_s']:.3f} | {x['total_PAR2_s']:.3f} | {x['kissat_solver_calls']} |")
    lines+=["","| Cities | Kind | Rep | R75-1c | R75-4c | Kissat-1c |",
            "|---:|---|---:|---|---|---|"]
    for c in m["cases"]:
        for rep in range(REPS):
            group={z["mode"]:z for z in rows if z["case"]==c["name"] and z["rep"]==rep}
            def fmt(mode):
                z=group[mode];state="PROVEN" if z["proven_optimum"] else "UNPROVEN"
                return f"{z['best']} / {z['elapsed_s']:.3f}s ({state})"
            lines.append(f"| {c['n']} | {c['kind']} | {rep} | "+
               " | ".join(fmt(mode) for mode in MODES)+" |")
    lines+=["","## Comparison limitations"]+["- "+s for s in m["notes"]]
    Path(a.md).write_text("\n".join(lines)+"\n")
    print("R76_FINAL_AUDIT_PASS",json.dumps(summary,sort_keys=True),flush=True)

def main():
    p=argparse.ArgumentParser()
    subs=p.add_subparsers(dest="action",required=True)
    c=subs.add_parser("selftest");c.add_argument("--kissat",required=True)
    x=subs.add_parser("freeze");x.add_argument("--out",required=True)
    x=subs.add_parser("measure")
    for name in ("sources","out","kissat"):x.add_argument("--"+name,required=True)
    x.add_argument("--shard",type=int,required=True)
    x=subs.add_parser("audit")
    for name in ("sources","combined","json","md"):x.add_argument("--"+name,required=True)
    a=p.parse_args()
    {"selftest":lambda:selftest(Path(a.kissat).resolve()),
     "freeze":lambda:freeze(a.out),
     "measure":lambda:measure(a),
     "audit":lambda:audit(a)}[a.action]()
if __name__=="__main__":main()
