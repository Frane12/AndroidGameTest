#!/usr/bin/env python3
"""R79: single intervention (stronger exact degree bound) vs R75 and Concorde.

Unchanged R75 is the negative control; R79 adds only admissible degree-2
residual Hamiltonian path bound to old MST branch lower bound. Both keep
the identical live shared best-tour design. Compare on EXACT SAME TSPLIB95
EUC_2D sources as R77; official pinned Waterloo Concorde as 1-core reference.
Same source, same integer costs, same runner, 12s timeout, two repetitions.
"""
from __future__ import annotations
import argparse,hashlib,json,os,random,time
from pathlib import Path
import drnas_r77_tsplib_concorde as pilot
import drnas_r75_shared_route as r75
import drnas_r79_degree_bound as r79

PROTO="DRNAS-R79-ONE-DEGREE-BOUND-VS-CONCORDE-20261104-v1"
MODES=("r75_shared_1core","r79_degree_1core","concorde_exact_1core",
       "r79_degree_4core")
CASES=tuple(pilot.KNOWN)
REPS=2;CAP=12.0;SHARDS=len(CASES)

def ck(yes,why):
    if not yes:raise RuntimeError("R79_BENCH_FAIL_CLOSED "+str(why))
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def selftest():
    # Candidate checks stronger degree bound against exhaustive small continuations
    # and compares four-worker completion to true brute-force optimal tours.
    r79.selftest()
    print("R79_BENCH_SAFETY_SELFTEST_PASS",flush=True)

def freeze(folder):
    root=Path(folder)
    pilot.freeze(root)  # exact official same TSPLIB sources, coordinates, cost scaling
    m=json.loads((root/"manifest.json").read_text())
    ck(m["protocol"]==pilot.PROTO and len(m["cases"])==SHARDS,
       "R77 source freeze changed")
    m["protocol"]=PROTO;m["methods"]=list(MODES)
    m["cap_s"]=CAP;m["repeats"]=REPS;m["seed"]=7911042026
    m["parent_protocol"]=pilot.PROTO
    m["limitations"]=[
      "Same three public TSPLIB EUC_2D instances as R77; NOT blind",
      "Only R79 code intervention: max(original MST LB, degree-2 residual LB)",
      "R75 control is original unchanged Python algorithm, not a recreated baseline",
      "Degree lower-bound computation cost included in timed trial",
      "R75/R79 both retain live best-route sharing and original DFS order; no soft deferral",
      "One-core R75/R79: four worker processes pinned to one identical available CPU",
      "R79 four-core result is supplementary, not resource-matched with Concorde",
      "Original static 32-bit Concorde binary may differ in compilation and ISA",
      "Original TSPLIB route is checked for all claimed results",
      "Concorde PROVEN requires independently verified full tour and announced optimum",
      "TSPLIB known optima used for audit only, never given to any algorithm",
      "12s cap per attempt, two repetitions; small pilot cannot establish global superiority",
    ]
    (root/"manifest.json").write_text(json.dumps(m,indent=2)+"\n")
    for c in m["cases"]:
        ck(sha(root/c["file"])==c["sha256"],"source changed")
    print("R79_FROZEN_SAME_TSPLIB_AS_R77",
          [(z["name"],z["sha256"][:12]) for z in m["cases"]],flush=True)
    print("R79_FREEZE_PASS",sha(root/"manifest.json"),flush=True)

def run_method(d,cpus,mode,cap):
    ck(mode!="concorde_exact_1core" and mode in MODES,"wrong method")
    upgraded=mode.startswith("r79_degree_")
    impl=r79 if upgraded else r75
    assigned=cpus[:4] if mode=="r79_degree_4core" else [cpus[0]]*4
    begin=time.monotonic()
    v=impl.trial(d,"shared",assigned,cap)
    wall=time.monotonic()-begin
    return dict(mode=mode,best=v["best"],tour=v["tour"],
       initial_upper=v["initial_upper"],
       proven_optimum=bool(v["proven_optimum"] and wall<=cap),
       elapsed_s=round(min(wall,cap),6),actual_wall_s=round(wall,6),
       cores=4 if mode=="r79_degree_4core" else 1,
       workers_completed=v["finished_workers"],visited_nodes=v["nodes"],
       pruned_branches=v["pruned"],shared_updates=v["signals_sent"],
       degree_checks=v.get("degree_checked",0),
       degree_extra_prunes=v.get("degree_extra_pruned",0))

def measure(a):
    root=Path(a.sources)
    m=json.loads((root/"manifest.json").read_text())
    ck(m["protocol"]==PROTO and m["methods"]==list(MODES)
       and m["cap_s"]==CAP and len(m["cases"])==SHARDS,"protocol mismatch")
    ck(0<=a.shard<SHARDS,"invalid shard")
    concorde=Path(a.concorde).resolve()
    ck(concorde.is_file() and os.access(concorde,os.X_OK),"missing official binary")
    cpus=sorted(os.sched_getaffinity(0))
    ck(len(cpus)>=4,"insufficient available CPUs")
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    (out/"meta.json").write_text(json.dumps(dict(
        protocol=PROTO,shard=a.shard,manifest_sha=sha(root/"manifest.json"),
        concorde_sha=sha(concorde),cpu_ids=cpus[:4]),indent=2)+"\n")
    rows=[]
    for c in m["cases"][a.shard::SHARDS]:
        source=(root/c["file"]).resolve()
        ck(sha(source)==c["sha256"],"source changed between benchmark arms")
        attrs,xy,d=pilot.parse_tsplib(source.read_bytes())
        initial_tour,initial_cost=r75.nearest_neighbor(d)
        ck(initial_cost==c["initial_upper"],"initial heuristic mismatches")
        for rep in range(REPS):
            choices=list(MODES)
            random.Random(int(hashlib.sha256(
                (c["sha256"]+str(rep)+PROTO).encode()).hexdigest(),16)).shuffle(choices)
            for mode in choices:
                previous=os.sched_getaffinity(0)
                try:
                    os.sched_setaffinity(0,
                         set(cpus[:4]) if mode=="r79_degree_4core" else {cpus[0]})
                    result=(pilot.run_concorde(d,source,concorde,cpus[0],CAP)
                            if mode=="concorde_exact_1core"
                            else run_method(d,cpus,mode,CAP))
                finally:
                    os.sched_setaffinity(0,previous)
                r75.validate(d,result["tour"],result["best"])
                ck(result["best"]<=initial_cost,"algorithm worsened initial route")
                ck(result["best"]>=c["known_optimum_for_audit"],
                   "invalid tour better than known optimum")
                if result["proven_optimum"]:
                    ck(result["best"]==c["known_optimum_for_audit"],
                       "claims wrong proven optimum")
                row=dict(instance=c["name"],source_sha=c["sha256"],
                         repeat=rep,**result)
                rows.append(row)
                (out/"rows.json").write_text(json.dumps(rows,indent=2)+"\n")
                print("R79_TRIAL",c["name"],rep,mode,
                      "cost",result["best"],
                      "PROVEN" if result["proven_optimum"] else "UNPROVEN",
                      "wall",result["elapsed_s"],
                      "degree_checks",result.get("degree_checks",0),
                      "extra_prunes",result.get("degree_extra_prunes",0),flush=True)
    ck(len(rows)==len(m["cases"][a.shard::SHARDS])*REPS*len(MODES),
       "incomplete paired trial")

def audit(a):
    root=Path(a.sources)
    m=json.loads((root/"manifest.json").read_text())
    ck(m["protocol"]==PROTO and len(m["cases"])==SHARDS,"wrong manifest")
    total=[];seen=set();binary_shas=set()
    for i in range(SHARDS):
        fold=Path(a.combined)/f"r79-shard-{i}"/"results"
        meta=json.loads((fold/"meta.json").read_text())
        ck(meta["protocol"]==PROTO and meta["shard"]==i and
           meta["manifest_sha"]==sha(root/"manifest.json"),
           "wrong or mixed manifest")
        ck(len(meta["cpu_ids"])==4,"four CPU IDs not recorded")
        binary_shas.add(meta["concorde_sha"])
        rr=json.loads((fold/"rows.json").read_text())
        ck(len(rr)==len(m["cases"][i::SHARDS])*REPS*len(MODES),
           "missing runner output")
        for z in rr:
            key=(z["instance"],z["repeat"],z["mode"])
            ck(key not in seen and z["mode"] in MODES,"duplicate or unknown")
            seen.add(key)
            c=next(v for v in m["cases"] if v["name"]==z["instance"])
            ck(z["source_sha"]==c["sha256"],"input differs")
            _,_,d=pilot.parse_tsplib((root/c["file"]).read_bytes())
            r75.validate(d,z["tour"],z["best"])
            ck(z["best"]>=c["known_optimum_for_audit"],"below proven known optimum")
            ck(z["cores"]==(4 if z["mode"]=="r79_degree_4core" else 1),
               "resource mismatch")
            if z["proven_optimum"]:
                ck(z["best"]==c["known_optimum_for_audit"],
                   "proven wrong optimum")
        total+=rr
    ck(len(binary_shas)==1 and len(total)==len(m["cases"])*REPS*len(MODES),
       "missing rows or mixed binaries")
    summary={}
    for mode in MODES:
        z=[x for x in total if x["mode"]==mode]
        summary[mode]=dict(attempts=len(z),
           proven=sum(x["proven_optimum"] for x in z),
           total_wall_s=round(sum(x["elapsed_s"] for x in z),6),
           total_PAR2_s=round(sum(x["elapsed_s"] if x["proven_optimum"]
                             else 2*CAP for x in z),6),
           total_best_length=sum(x["best"] for x in z),
           total_visited_nodes=sum(x.get("visited_nodes",0) for x in z),
           total_degree_checks=sum(x.get("degree_checks",0) for x in z),
           extra_degree_prunes=sum(x.get("degree_extra_prunes",0) for x in z),
           cores=4 if mode=="r79_degree_4core" else 1)
    report=dict(protocol=PROTO,binary_sha=next(iter(binary_shas)),
       summary=summary,rows=total,limitations=m["limitations"])
    Path(a.json).write_text(json.dumps(report,indent=2)+"\n")
    lines=["# DRNAS R79: one stronger exact lower bound vs R75 and real Concorde",
      "Same official TSPLIB sources as R77; no soft deferral, no new learned heuristics.",
      "Every proof verified by original tour and known independently published optimum.",
      "| Algorithm | Cores | Proven / 6 | Total wall s | PAR2 s | Visited nodes | Extra degree prunes |",
      "|---|---:|---:|---:|---:|---:|---:|"]
    for mode in MODES:
        q=summary[mode]
        lines.append(f"| {mode} | {q['cores']} | {q['proven']}/{q['attempts']} | "+
           f"{q['total_wall_s']:.3f} | {q['total_PAR2_s']:.3f} | "+
           f"{q['total_visited_nodes']} | {q['extra_degree_prunes']} |")
    lines+=["","| Instance | Published optimum | Repeat | R75 1core | R79 1core | Concorde 1core | R79 4core |",
             "|---|---:|---:|---|---|---|---|"]
    for case in m["cases"]:
        for rep in range(REPS):
            group={x["mode"]:x for x in total if x["instance"]==case["name"] and x["repeat"]==rep}
            def fmt(mode):
                v=group[mode]
                return f"{v['best']} / {v['elapsed_s']:.3f}s ({'PROVEN' if v['proven_optimum'] else 'unproven'})"
            lines.append(f"| {case['name']} | {case['known_optimum_for_audit']} | {rep} | "+
                 " | ".join(fmt(mode) for mode in MODES)+" |")
    lines+=["","## Limitations"]+["- "+s for s in m["limitations"]]
    Path(a.md).write_text("\n".join(lines)+"\n")
    print("R79_FINAL_AUDIT_PASS",json.dumps(summary,sort_keys=True),flush=True)

def main():
    p=argparse.ArgumentParser()
    subs=p.add_subparsers(dest="task",required=True)
    subs.add_parser("selftest")
    x=subs.add_parser("freeze");x.add_argument("--out",required=True)
    x=subs.add_parser("measure")
    for v in ("sources","concorde","out"):x.add_argument("--"+v,required=True)
    x.add_argument("--shard",type=int,required=True)
    x=subs.add_parser("audit")
    for v in ("sources","combined","json","md"):x.add_argument("--"+v,required=True)
    a=p.parse_args()
    {"selftest":lambda:selftest(),"freeze":lambda:freeze(a.out),
     "measure":lambda:measure(a),"audit":lambda:audit(a)}[a.task]()
if __name__=="__main__":main()
