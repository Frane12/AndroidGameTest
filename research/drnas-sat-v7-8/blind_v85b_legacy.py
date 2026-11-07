#!/usr/bin/env python3
"""V8.5B retrospective legacy-build comparison on exactly the V8.5 frozen CNFs.
The original case seeds and generator are intentionally unchanged: not a new blind holdout.
Frozen DRNAS v7.6 (previous best) and v7.7 vs CaDiCaL 3.0.1.
"""
import csv, hashlib, itertools, json, math, os, random, statistics, subprocess, time
from collections import defaultdict
from pathlib import Path

OUT=Path("blind-v85b-legacy-results")
CAP=4.0
REPEATS=5
MODES=("ca_plain","orig_v76","orig_v77","orig_v76_plain","hybrid_gate_with_observer")
EXPERIMENT="drnas-blind-v85-random3-new-seeds-20261031-v1"
SPECS=[("random3",n,instance) for n in (200,215,230,245) for instance in (0,1)]

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
        p=subprocess.run(["./v80_hybrid_probe",mode,str(cnf),str(seed)],
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
                "extended","resumed","gate_reason","active_256","resume_us","probe_us","extension_us","total_us","first_budget","second_budget"):
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
            "probe_us","extension_us","total_us","first_budget","second_budget"]
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
                    print("LEGACYV85B",row["case"],rep,mode,result["status"],
                          round(result["wall_s"],5),"extended",result.get("extended",""),
                          "learned",result.get("learned_delta",""),flush=True)
    lines=["# DRNAS v8.5B frozen legacy-build replay on exactly the V8.5 formulas", "",
      "Original V8.5 generator tag and seeds, same 8 original CNF bytes (hash in manifest), different benchmark run; code remains frozen.",
      "Five paired repeats, one CPU, 4 s per attempt, no parameter tuning or exclusions after case generation.",
      "Retrospective same-CNF replay after V8.5 results are known; NOT a new blind holdout, independent confirmation, or record.",
      "Primary comparison: CaDiCaL 3.0.1 plain versus frozen DRNAS v7.6 guided (previous best), and frozen v7.7 quality-guided.",
      "SAT witnesses are checked by the native C++ checker; UNSAT from random/xor cases lacks independent certificate.",
      "", "| Case | CaDiCaL | DRNAS v7.6 | DRNAS v7.7 | v7.6 no hints | v8.0 hybrid | v7.6 / Ca | v7.7 / Ca |",
      "|---|---:|---:|---:|---:|---:|---:|---:|"]
    family_results=defaultdict(list)
    v77_results=defaultdict(list)
    metrics=["# Per-case diagnostic metrics (medians over five repetitions)","", "The same original V8.5 formula bytes are regenerated; comparisons include process startup.", "", "| Case | Mode | Solved | Median wall s | Hints | Extended/5 | Learned delta | Offered clauses | Short <=5 fraction | Probe ms | Resume ms |", "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    good_pair=[]
    discrepancies=[]
    for case in manifest:
        name=Path(case["cnf"]).stem
        these=[row for row in rows if row["case"]==name]
        solved={x["status"] for x in these if x["status"] in ("SAT","UNSAT")}
        if len(solved)>1:discrepancies.append(name)
        if case["known_truth"]=="SAT-by-construction" and "UNSAT" in solved:discrepancies.append(name+" incorrect UNSAT")
        if case["known_truth"].startswith("UNSAT") and "SAT" in solved:discrepancies.append(name+" incorrect SAT")
        m={}
        for mode in MODES:
            block=[x for x in these if x["mode"]==mode]
            assert len(block)==REPEATS
            val=statistics.median(x["wall_s"] if x["status"] in ("SAT","UNSAT") else CAP*2 for x in block)
            m[mode]=(val,sum(x["status"] in ("SAT","UNSAT") for x in block))
        good_baseline=m["ca_plain"][1]==REPEATS and m["ca_plain"][0]>=0.10
        both=good_baseline and m["orig_v76"][1]==REPEATS
        both77=good_baseline and m["orig_v77"][1]==REPEATS
        ratio=m["ca_plain"][0]/m["orig_v76"][0] if both else None
        ratio77=m["ca_plain"][0]/m["orig_v77"][0] if both77 else None
        if ratio is not None:
            family_results[case["family"]].append(ratio);good_pair.append((name,ratio))
        if ratio77 is not None:
            v77_results[case["family"]].append(ratio77)
        fmt=lambda mode:"%.4f s (%d/%d)"%(m[mode][0],m[mode][1],REPEATS)
        lines.append("| "+name+" | "+" | ".join(fmt(mode) for mode in MODES)+
                     " | "+("%.2fx"%ratio if ratio is not None else "not measurable")+
                     " | "+("%.2fx"%ratio77 if ratio77 is not None else "not measurable")+" |")
        for mode in MODES:
            block=[x for x in these if x["mode"]==mode]
            num=lambda key: [float(x[key]) for x in block if x.get(key,"") not in ("",None)]
            med=lambda key,scale=1: ("%.2f"%(statistics.median(num(key))*scale)) if num(key) else "-"
            extended=sum(str(x.get("extended",""))=="1" for x in block)
            metrics.append("| "+name+" | "+mode+" | "+str(m[mode][1])+"/5 | "+
                 "%.4f"%m[mode][0]+" | "+med("hints")+" | "+str(extended)+
                 "/5 | "+med("learned_delta")+" | "+med("offered")+
                 " | "+med("short_fraction")+" | "+med("probe_us",0.001)+
                 " | "+med("resume_us",0.001)+" |")
    lines.extend(["", "## Predeclared interpretation", "",
     "Only paired solved cases with CaDiCaL median baseline >=0.10 s count toward timing ratios.",
     "A win means >1.25x; a loss means <0.8x; otherwise inconclusive. Timeouts are not wins.",
     "PAR2 uses 4 s for each timeout in the table. Family summaries are descriptive only.",
     ""])
    for family in sorted(set(c["family"] for c in manifest)):
        ratios=family_results[family]
        r77=v77_results[family]
        summarize=lambda rr,label: (label+": "+str(len(rr))+"/"+str(len(manifest))+" measurable; "+
            ("median baseline/DRNAS "+("%.3f"%statistics.median(rr))+"x; "+
             str(sum(r>1.25 for r in rr))+" wins, "+str(sum(r<0.8 for r in rr))+" losses"
             if rr else "no measurable paired cases"))
        lines.append("- "+family+" "+summarize(ratios,"v7.6"))
        lines.append("- "+family+" "+summarize(r77,"v7.7"))
    lines.append("")
    lines.append("Contradictions: "+(str(discrepancies) if discrepancies else "none detected; UNSAT certificates not checked"))
    lines.append("Retrospective comparison does not establish generalization. UNSAT proof certificates are not independently checked.")
    (OUT/"summary.md").write_text("\n".join(lines)+"\n")
    (OUT/"metrics.md").write_text("\n".join(metrics)+"\n")
    with open(os.environ.get("GITHUB_STEP_SUMMARY",str(OUT/"actions_summary.md")),"a") as f:
        f.write("\n".join(lines)+"\n")
    print("\n".join(lines),flush=True)
    if any(x["status"]=="ERROR" for x in rows) or discrepancies:
        raise RuntimeError("Errors/contradictions; inspect raw rows")
if __name__=="__main__":
    main()
