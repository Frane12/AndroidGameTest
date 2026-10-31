#!/usr/bin/env python3
"""V8.7 guarded adaptive: new-seed test after inspecting V8.6 failures.
Guard is data-motivated and should be judged as exploratory, NOT an independent
confirmation of broad gains. Frozen legacy solver sources unchanged.
"""
import csv, hashlib, itertools, json, math, os, random, statistics, subprocess, time
from collections import defaultdict
from pathlib import Path

OUT=Path("blind-v87-guarded-results")
CAP=3.0
REPEATS=3
MODES=("ca_plain","orig_v76","orig_v77","adaptive_two_checkpoint","adaptive_guarded_v87","adaptive_guarded_v87_no_hints","hybrid_gate_with_observer")
EXPERIMENT="drnas-v87-guarded-new-seeds-20261031-v1"
SPECS=[("random3",n,instance) for n in (190,210,230,250) for instance in (0,1)]
SPECS += [("color3",n,0) for n in (250,400)]
SPECS += [("xor3",n,0) for n in (220,280)]
SPECS += [("pigeonhole",n,0) for n in (8,9)]

def random3(n,rng):
    m=round(n*4.26)
    rows=[]
    for _ in range(m):
        vs=rng.sample(range(1,n+1),3)
        rows.append([v if rng.randrange(2) else -v for v in vs])
    return n,rows,"unknown"

def color3(n,rng):
    planted=[i%3 for i in range(n)]
    rng.shuffle(planted)
    rows=[]
    for i in range(n):
        vs=[i*3+j+1 for j in range(3)]
        rows.append(vs)
        for a,b in itertools.combinations(vs,2):
            rows.append([-a,-b])
    for i in range(n):
        for j in range(i+1,n):
            if planted[i]!=planted[j] and rng.random()<7.5/n:
                for color in range(3):
                    rows.append([-(i*3+color+1),-(j*3+color+1)])
    return 3*n,rows,"SAT-by-construction"

def xor3(n,rng):
    rows=[]
    # Random parity checks (3-XORSAT) with overlap and hidden variable relabeling.
    for _ in range(n+12):
        vs=rng.sample(range(1,n+1),3)
        parity=rng.randrange(2)
        for bits in itertools.product((0,1),repeat=3):
            if sum(bits)%2!=parity:
                rows.append([(-v if bit else v) for v,bit in zip(vs,bits)])
    return n,rows,"unknown"

def pigeonhole(n,rng):
    h=n-1; rows=[]
    var=lambda p,j: p*h+j+1
    for p in range(n):
        rows.append([var(p,j) for j in range(h)])
        for j,k in itertools.combinations(range(h),2):
            rows.append([-var(p,j),-var(p,k)])
    for j in range(h):
        for p,q in itertools.combinations(range(n),2):
            rows.append([-var(p,j),-var(q,j)])
    return n*h,rows,"UNSAT-by-pigeonhole-principle"

def make_case(family,n,instance):
    seed=int(hashlib.sha256((EXPERIMENT+":"+family+":"+str(n)+":"+str(instance)).encode()).hexdigest()[:16],16)
    rng=random.Random(seed)
    nv,rows,known={"random3":random3,"color3":color3,"xor3":xor3,"pigeonhole":pigeonhole}[family](n,rng)
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
        p=subprocess.run(["./v87_guarded_probe",mode,str(cnf),str(seed)],
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
    for key in ("hints","learned_delta","threshold","offered","short5","short_fraction",
                "extended","resumed","gate_reason","active_256","resume_us","probe_us","extension_us","total_us","first_budget","second_budget","third_budget","stage3","adaptive_keep","checkpoint_learned","checkpoint_offered","checkpoint_short5","final_extension_us"):
        result[key]=d.get(key,"")
    return result

def main():
    OUT.mkdir(exist_ok=True)
    affinity=os.sched_getaffinity(0)
    os.sched_setaffinity(0,{min(affinity)})
    manifest=[make_case(*item) for item in SPECS]
    (OUT/"manifest.json").write_text(json.dumps({"version":EXPERIMENT,
        "cap_s":CAP,"repeats":REPEATS,"modes":MODES,"cases":manifest},indent=2))
    rows=[]
    fields=["family","size","case","sha256","mode","repeat","status","wall_s",
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
                    print("GUARDEDV87",row["case"],rep,mode,result["status"],
                          round(result["wall_s"],5),"extended",result.get("extended",""),
                          "learned",result.get("learned_delta",""),flush=True)
    lines=["# DRNAS v8.7 guarded adaptive new-seed exploratory benchmark","",
           "Frozen DRNAS v7.6 / v7.7 and CaDiCaL 3.0.1 vs V8.6 and guarded V8.7.",
           "14 new deterministically seeded CNFs, one CPU, three repeats per mode, 3-second cap.",
           "Guard designed AFTER inspecting V8.6 on a different sample; this is a new-seed follow-up, not independent validation.",
           "SAT witness checked by native C++; UNSAT certificates NOT independently validated.",
           "Ratios are meaningful only if BOTH solvers solved all 3 repeats and CaDiCaL >=0.10 seconds.",
           "Speedup >1.25x counts win and <0.8x counts loss; timeouts never count as wins.","",
           "| Instance | CaDiCaL | V7.6 | V7.7 | V8.6 | V8.7 Guarded | V8.7 no hints | V8.0 hybrid | Ca/V8.7 | V7.6/V8.7 |",
           "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    metrics=["# V8.7 Guarded checkpoint diagnostics","","All fields are medians of numeric observations over three paired runs.",
             "| Instance | Mode | Solved | First-256 learned | First-256 offered | Short <=5 | 128-conflict learned | 128-conflict offered | 128-conflict short<=5 | First extend | Continue 640 | Gate reason |",
             "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|"]
    discrepancies=[]
    ratios=defaultdict(lambda:defaultdict(list))
    for case in manifest:
        name=Path(case["cnf"]).stem
        these=[row for row in rows if row["case"]==name]
        answer={x["status"] for x in these if x["status"] in ("SAT","UNSAT")}
        if len(answer)>1:discrepancies.append(name+" SAT/UNSAT mismatch")
        if case["known_truth"]=="SAT-by-construction" and "UNSAT" in answer:
            discrepancies.append(name+" wrong UNSAT on planted SAT")
        if case["known_truth"].startswith("UNSAT") and "SAT" in answer:
            discrepancies.append(name+" wrong SAT on pigeonhole")
        stats={}
        for mode in MODES:
            block=[r for r in these if r["mode"]==mode]
            assert len(block)==REPEATS
            solved=sum(x["status"] in ("SAT","UNSAT") for x in block)
            median=statistics.median(float(x["wall_s"]) if x["status"] in ("SAT","UNSAT") else 2*CAP for x in block)
            stats[mode]=(median,solved)
            num=lambda key:[float(x[key]) for x in block if x.get(key,"") not in ("",None)]
            med=lambda key:("%.0f"%statistics.median(num(key))) if num(key) else "-"
            ext=sum(str(x.get("extended",""))=="1" for x in block)
            keep=sum(str(x.get("adaptive_keep",""))=="1" for x in block)
            reason=block[0].get("gate_reason","-")
            metrics.append("| "+name+" | "+mode+" | "+str(solved)+"/3 | "+
                med("learned_delta")+" | "+med("offered")+" | "+med("short5")+
                " | "+med("checkpoint_learned")+" | "+med("checkpoint_offered")+
                " | "+med("checkpoint_short5")+" | "+str(ext)+"/3 | "+str(keep)+"/3 | "+reason+" |")
        valid=stats["ca_plain"][1]==REPEATS and stats["ca_plain"][0]>=0.10
        adaptive_full=stats["adaptive_guarded_v87"][1]==REPEATS
        v76_full=stats["orig_v76"][1]==REPEATS
        ratio_ca=stats["ca_plain"][0]/stats["adaptive_guarded_v87"][0] if valid and adaptive_full else None
        ratio_v76=stats["orig_v76"][0]/stats["adaptive_guarded_v87"][0] if v76_full and adaptive_full and stats["orig_v76"][0]>=0.10 else None
        if ratio_ca is not None:ratios[case["family"]]["ca"].append(ratio_ca)
        if ratio_v76 is not None:ratios[case["family"]]["v76"].append(ratio_v76)
        fmt=lambda mode:"%.4f s (%d/3)"%stats[mode]
        lines.append("| "+name+" | "+" | ".join(fmt(m) for m in MODES)+
                     " | "+("%.2fx"%ratio_ca if ratio_ca is not None else "n/a")+
                     " | "+("%.2fx"%ratio_v76 if ratio_v76 is not None else "n/a")+" |")
    lines+=["","## Frozen interpretation",""]
    for family in sorted(set(c["family"] for c in manifest)):
        for baseline in ("ca","v76"):
            rr=ratios[family][baseline]
            lines.append("- "+family+" "+baseline+": "+str(len(rr))+" qualifying; "+
                ("median %.3fx, %d wins >1.25x, %d losses <0.8x"%(
                    statistics.median(rr),sum(v>1.25 for v in rr),sum(v<0.8 for v in rr))
                if rr else "no qualifying pairs"))
    lines+=["","Contradictions: "+(str(discrepancies) if discrepancies else "none detected; UNSAT certificates not validated"),
            "This guard was designed after V8.6 outcomes; benchmark is exploratory, not an independent world-record claim.",
            "A speedup here does not establish generalization or statistical significance."]
    (OUT/"summary.md").write_text("\n".join(lines)+"\n")
    (OUT/"metrics.md").write_text("\n".join(metrics)+"\n")
    with open(os.environ.get("GITHUB_STEP_SUMMARY",str(OUT/"actions_summary.md")),"a") as f:
        f.write("\n".join(lines)+"\n")
    print("\n".join(lines),flush=True)
    if any(x["status"]=="ERROR" for x in rows) or discrepancies:
        raise RuntimeError("Errors/contradictions; inspect raw CSV")

if __name__=="__main__":
    main()
