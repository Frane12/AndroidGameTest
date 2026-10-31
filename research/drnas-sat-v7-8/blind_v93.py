#!/usr/bin/env python3
"""v9.3 zero-shot transfer: six new NP classes, with no retraining/tuning of frozen v9.2 selector."""
import csv, hashlib, itertools, json, math, os, random, statistics, subprocess, time
from collections import defaultdict
from pathlib import Path

OUT=Path("blind-v93-results")/("shard-"+os.environ.get("SHARD","0"))
CAP=3.0
REPEATS=3
MODES=("ca_plain","orig_v76","orig_v76_plain","v92_full_compat","v92_sparse","v92_structural")
EXPERIMENT="drnas-v93-six-unseen-np-classes-zeroshot-20261031-v1"
from v93_new_generators import GENS
SPECS=[("queens",n,0) for n in (8,10,12,14,16)]
SPECS += [("planted_clique",n,0) for n in (22,26,30,34,38)]
SPECS += [("latin_square",n,0) for n in (5,6,7,8,9)]
SPECS += [("subset_sum",n,0) for n in (10,12,14,16,18)]
SPECS += [("exact_cover",n,0) for n in (8,10,12,14,16)]
SPECS += [("circuit_miter",n,0) for n in (8,10,12,14,16)]

def make_case(family,n,instance):
    seed=int(hashlib.sha256((EXPERIMENT+":"+family+":"+str(n)+":"+str(instance)).encode()).hexdigest()[:16],16)
    rng=random.Random(seed)
    nv,rows,known=GENS[family](n,rng)
    # Blinded variable labels, randomized polarity, and clause order.
    perm=list(range(1,nv+1)); rng.shuffle(perm)
    flips=[rng.choice((-1,1)) for _ in range(nv)]
    rows=[[int(math.copysign(1,lit))*perm[abs(lit)-1]*flips[abs(lit)-1]
           for lit in clause] for clause in rows]
    rng.shuffle(rows)
    path=OUT/(family+"-"+str(n)+"-s"+str(instance)+".cnf")
    path.write_text("p cnf %d %d\n"%(nv,len(rows))+
                    "".join(" ".join(map(str,row))+" 0\n" for row in rows))
    return {"family":family,"size":n,"instance":instance,"vars":nv,"clauses":len(rows),
            "cnf":str(path),"sha256":hashlib.sha256(path.read_bytes()).hexdigest(),
            "known_truth":known,"generator_seed":seed}

def execute(case,mode,rep):
    cnf=Path(case["cnf"])
    if hashlib.sha256(cnf.read_bytes()).hexdigest()!=case["sha256"]:
        raise RuntimeError("input mutated "+str(cnf))
    seed=(830031+rep*527+int(case["sha256"][:8],16))%(2**32)
    start=time.perf_counter()
    try:
        p=subprocess.run(["./v92_early_structural",mode,str(cnf),str(seed)],
            capture_output=True,text=True,timeout=CAP,check=False)
    except subprocess.TimeoutExpired:
        return {"status":"TIMEOUT","wall_s":CAP,"seed":seed}
    wall=time.perf_counter()-start
    if p.returncode!=0:
        return {"status":"ERROR","wall_s":wall,"seed":seed,
                "error":("rc="+str(p.returncode)+" "+p.stderr[-300:])}
    lines=[x for x in p.stdout.splitlines() if x.startswith("DRNAS_CAUSAL\t")]
    if len(lines)!=1:
        return {"status":"ERROR","wall_s":wall,"seed":seed,"error":"bad output"}
    d={}
    for part in lines[0].split("\t")[1:]:
        k,v=part.split("=",1);d[k]=v
    result={"status":d["answer"],"wall_s":wall,"seed":seed}
    for key in ("v92_choice","v92_broad","v92_strong","v92_clause2","v92_clause3","v92_clause4","v92_maxwidth","v92_static_us","v91_phase_applied","v91_quality_signal","v90_learned_256","v90_lbd2_256","v90_lbd4_256","v90_lbd_sum_256","v90_props_256","v90_jumps_256","v90_jumpdepth_256","v90_conflicts_256","v90_backtracks_256","v90_learned_total","v90_lbd2_total","v90_props_total","cpu_256_ns","cpu_128_ns","cpu_total_ns","active_384","hints","learned_delta","threshold","offered","short5","short_fraction",
                "extended","resumed","gate_reason","active_256","resume_us","probe_us","extension_us","total_us","first_budget","second_budget","third_budget","stage3","adaptive_keep","checkpoint_learned","checkpoint_offered","checkpoint_short5","final_extension_us"):
        result[key]=d.get(key,"")
    return result

def main():
    OUT.mkdir(exist_ok=True)
    affinity=os.sched_getaffinity(0)
    os.sched_setaffinity(0,{min(affinity)})
    manifest=[make_case(*item) for i,item in enumerate(SPECS) if i%5==int(os.environ.get("SHARD","0"))]
    assert len(manifest)==6
    (OUT/"manifest.json").write_text(json.dumps({"version":EXPERIMENT,
        "cap_s":CAP,"repeats":REPEATS,"modes":MODES,"cases":manifest},indent=2))
    rows=[]
    fields=["family","size","case","sha256","mode","repeat","status","wall_s","v92_choice","v92_broad","v92_strong","v92_clause2","v92_clause3","v92_clause4","v92_maxwidth","v92_static_us","v91_phase_applied","v91_quality_signal","v90_learned_256","v90_lbd2_256","v90_lbd4_256","v90_lbd_sum_256","v90_props_256","v90_jumps_256","v90_jumpdepth_256","v90_conflicts_256","v90_backtracks_256","v90_learned_total","v90_lbd2_total","v90_props_total","cpu_256_ns","cpu_128_ns","cpu_total_ns","active_384",
            "seed","error","hints","learned_delta","threshold","offered","short5",
            "short_fraction","extended","resumed","gate_reason","active_256","resume_us",
            "probe_us","extension_us","total_us","first_budget","second_budget",
            "third_budget","stage3","adaptive_keep","checkpoint_learned",
            "checkpoint_offered","checkpoint_short5","final_extension_us"]
    with (OUT/"raw.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fields);w.writeheader()
        for case in manifest:
            for rep in range(REPEATS):
                order=list(MODES)
                random.Random(case["generator_seed"]+rep*941).shuffle(order)
                for mode in order:
                    result=execute(case,mode,rep)
                    row=dict(family=case["family"],size=case["size"],
                        case=Path(case["cnf"]).stem,sha256=case["sha256"],
                        mode=mode,repeat=rep,**result)
                    rows.append(row);w.writerow(row);f.flush()
                    print("ZEROSHOTV93",row["case"],rep,mode,result["status"],
                          round(result["wall_s"],5),"extended",result.get("extended",""),
                          "learned",result.get("learned_delta",""),flush=True)
    lines=["# DRNAS v9.3 FROZEN v9.2 selector on six previously UNSEEN NP classes, shard "+os.environ.get("SHARD","0"), "",
           "CaDiCaL 3.0.1 separate instrumentation checkout; legacy V7.6 source unchanged, all modes use identical instrumented solver library.",
           "The three v9.2 modes preserve original v7.6 checkpoint schedule; only before-first-conflict hints change.",
           "NO policy tuning: frozen v9.2 selector and v7.6 controls, six new families and truth by construction.",
           "6 independently new classes per shard, three repeats per mode, 3-second cap and full PAR2 accounting."
           "Unsolved cases cost PAR2=6 seconds; no world-record claims.", "",
           "| Case | "+ " | ".join(MODES)+" |", "|"+"---|"*(len(MODES)+1)]
    contradictions=[]
    stats=[]
    for case in manifest:
        name=Path(case["cnf"]).stem
        block=[r for r in rows if r["case"]==name]
        observed={r["status"] for r in block if r["status"] in ("SAT","UNSAT")}
        if len(observed)>1:contradictions.append(name+" conflicting SAT/UNSAT")
        if case["known_truth"].startswith("UNSAT") and "SAT" in observed:
            contradictions.append(name+" wrong SAT")
        if case["known_truth"]=="SAT-by-construction" and "UNSAT" in observed:
            contradictions.append(name+" wrong UNSAT on planted SAT")
        if any(r["status"]=="ERROR" for r in block):
            contradictions.append(name+" error")
        med={}
        for mode in MODES:
            subset=[r for r in block if r["mode"]==mode]
            assert len(subset)==REPEATS
            cost=[float(r["wall_s"]) if r["status"] in ("SAT","UNSAT") else 2*CAP for r in subset]
            med[mode]=statistics.median(cost)
        lines.append("| "+name+" | "+" | ".join("%.4fs"%med[m] for m in MODES)+" |")
        for mode in ("v92_full_compat","v92_sparse","v92_structural"):
            for r in [r for r in block if r["mode"]==mode]:
                stats.append(dict(case=name,mode=mode,repeat=r["repeat"],
                    gate_reason=r.get("gate_reason",""),
                    selected=r.get("v92_choice",""),broad=r.get("v92_broad",""),
                    strong=r.get("v92_strong",""),static_us=r.get("v92_static_us",""),
                    learned_256=r.get("learned_delta",""),
                    learned_128=r.get("checkpoint_learned",""),
                    offered=r.get("offered",""),stage3=r.get("stage3",""),
                    cpu_256_ns=r.get("cpu_256_ns",""),cpu_128_ns=r.get("cpu_128_ns",""),
                    cpu_total_ns=r.get("cpu_total_ns",""),active_384=r.get("active_384",""),
                    second=r.get("second_budget",""),third=r.get("third_budget",""),
                    **{k:r.get(k,"") for k in ["v90_learned_256","v90_lbd2_256","v90_lbd4_256","v90_lbd_sum_256","v90_props_256","v90_jumps_256","v90_jumpdepth_256","v90_conflicts_256","v90_backtracks_256","v90_learned_total","v90_lbd2_total","v90_props_total"]}))
    # The v92_full_compat arm must use the SAME phase count and schedule
    # as original v7.6 guided, but tiny timing differences are expected.
    for case in manifest:
        name=Path(case["cnf"]).stem
        for rep in range(REPEATS):
            paired=[r for r in rows if r["case"]==name and int(r["repeat"])==rep
                    and r["mode"] in ("orig_v76","v92_full_compat")]
            assert len(paired)==2
            if any(r["status"] in ("TIMEOUT","ERROR") for r in paired):
                continue
            a,b=paired
            # The original frozen V7.6 intentionally leaves threshold,
            # active_256 and learned_delta zero if the FIRST 256-conflict
            # solve returned SAT/UNSAT immediately. The v9.2 diagnostic
            # populates these read-only counters even on early completion.
            # Compare them only when V7.6 actually entered its extension gate.
            compare=["hints","extended","second_budget"]
            if str(a.get("threshold","")) not in ("","0"):
                compare+=["learned_delta","active_256","threshold"]
            for k in compare:
                if str(a.get(k,""))!=str(b.get(k,"")):
                    raise RuntimeError("v92 full vs frozen v7.6 parity mismatch "+
                                       name+" rep "+str(rep)+" "+k)
    (OUT/"summary.md").write_text("\n".join(lines)+"\n")
    (OUT/"gate_diagnostics.json").write_text(json.dumps(stats,indent=2))
    with open(os.environ.get("GITHUB_STEP_SUMMARY",str(OUT/"actions_summary.md")),"a") as fh:
        fh.write("\n".join(lines)+"\n")
    print("\n".join(lines),flush=True)
    if contradictions:raise RuntimeError(str(contradictions))

if __name__=="__main__":
    main()
