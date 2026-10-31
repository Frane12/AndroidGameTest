#!/usr/bin/env python3
"""V8.7 guarded adaptive: new-seed test after inspecting V8.6 failures.
Guard is data-motivated and should be judged as exploratory, NOT an independent
confirmation of broad gains. Frozen legacy solver sources unchanged.
"""
import csv, hashlib, itertools, json, math, os, random, statistics, subprocess, time
from collections import defaultdict
from pathlib import Path

OUT=Path("blind-v88-results")/("shard-"+os.environ.get("SHARD","0"))
CAP=3.0
REPEATS=3
MODES=("ca_plain","orig_v76","orig_v76_plain","adaptive_two_checkpoint","adaptive_guarded_v87","lowlevel_v88","lowlevel_v88_no_hints")
EXPERIMENT="drnas-v88-lowlevel-30-blind-20261031-seed-v1"
SPECS=[("random3",n,0) for n in (180,195,210,225,240,255)]
SPECS += [("random4",n,0) for n in (105,115,125,135,145,155)]
SPECS += [("color3",n,0) for n in (250,280,310,340,370,400)]
SPECS += [("xor3",n,0) for n in (160,210,260,310,360,410)]
SPECS += [("pigeonhole",n,0) for n in (7,8,9,10,11,12)]

def random3(n,rng):
    m=round(n*4.26)
    rows=[]
    for _ in range(m):
        vs=rng.sample(range(1,n+1),3)
        rows.append([v if rng.randrange(2) else -v for v in vs])
    return n,rows,"unknown"

def random4(n,rng):
    rows=[]
    for _ in range(round(n*9.88)):
        vs=rng.sample(range(1,n+1),4)
        rows.append([v if rng.randrange(2) else -v for v in vs])
    return n,rows,"unknown"

def color3(n,rng):
    # Unplanted random graph, difficult coloring boundary.
    rows=[]
    for i in range(n):
        vs=[i*3+j+1 for j in range(3)]
        rows.append(vs)
        for x,y in itertools.combinations(vs,2):
            rows.append([-x,-y])
    for i in range(n):
        for j in range(i+1,n):
            if rng.random()<4.7/n:
                for col in range(3):
                    rows.append([-(i*3+col+1),-(j*3+col+1)])
    return 3*n,rows,"unknown"

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
    nv,rows,known={"random3":random3,"random4":random4,"color3":color3,"xor3":xor3,"pigeonhole":pigeonhole}[family](n,rng)
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
        p=subprocess.run(["./v88_lowlevel_probe",mode,str(cnf),str(seed)],
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
    manifest=[make_case(*item) for i,item in enumerate(SPECS) if i%5==int(os.environ.get("SHARD","0"))]
    assert len(manifest)==6
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
                    print("LOWLEVELV88",row["case"],rep,mode,result["status"],
                          round(result["wall_s"],5),"extended",result.get("extended",""),
                          "learned",result.get("learned_delta",""),flush=True)
    lines=["# DRNAS v8.8 low-level holdout, shard "+os.environ.get("SHARD","0"), "",
           "Frozen v7.6, CaDiCaL 3.0.1, v8.6 adaptive and v8.7 guarded matched controls.",
           "v8.8 uses integer public counters at 256/384 conflicts, no Learner callbacks.",
           "6 new hashed CNFs per shard; 3 repeats/mode, 3-second cap, pin one CPU.",
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
        if any(r["status"]=="ERROR" for r in block):
            contradictions.append(name+" error")
        med={}
        for mode in MODES:
            subset=[r for r in block if r["mode"]==mode]
            assert len(subset)==REPEATS
            cost=[float(r["wall_s"]) if r["status"] in ("SAT","UNSAT") else 2*CAP for r in subset]
            med[mode]=statistics.median(cost)
        lines.append("| "+name+" | "+" | ".join("%.4fs"%med[m] for m in MODES)+" |")
        for mode in ("lowlevel_v88","lowlevel_v88_no_hints"):
            for r in [r for r in block if r["mode"]==mode]:
                stats.append(dict(case=name,mode=mode,repeat=r["repeat"],
                    gate_reason=r.get("gate_reason",""),
                    learned_256=r.get("learned_delta",""),
                    learned_128=r.get("checkpoint_learned",""),
                    offered=r.get("offered",""),stage3=r.get("stage3",""),
                    second=r.get("second_budget",""),third=r.get("third_budget","")))
    (OUT/"summary.md").write_text("\n".join(lines)+"\n")
    (OUT/"gate_diagnostics.json").write_text(json.dumps(stats,indent=2))
    with open(os.environ.get("GITHUB_STEP_SUMMARY",str(OUT/"actions_summary.md")),"a") as fh:
        fh.write("\n".join(lines)+"\n")
    print("\n".join(lines),flush=True)
    if contradictions:raise RuntimeError(str(contradictions))

if __name__=="__main__":
    main()
