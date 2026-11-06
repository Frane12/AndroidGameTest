#!/usr/bin/env python3
"""R166x: R165 frozen original-CNF multi-solver benchmark. Research, NOT blind."""
import argparse, collections, hashlib, json, os, pathlib, random, re, shutil, subprocess, sys, time
sys.path.insert(0, str(pathlib.Path("research").resolve()))
import r165_component_benchmark as native
import r164_pure_exact_gf2 as exact

ROOT=pathlib.Path("r166x")
SOURCE=pathlib.Path("r165/frozen")
MODES=("r165_exact_router",)+tuple(native.MODES)+("kissat404","cryptominisat","minisat","picosat")
REPS=2
SHARDS=5
PINNED_R165="f57e68640f576d2fe5ad541e343ba958d861d7ac1e5c7c37e0022ec3d088719e"
PINNED_R165_SOURCE="e5f1328c0f53eee6051da110cfae595440397251"

def need(x,why):
    if not x: raise RuntimeError("R166X_AUDIT_FAIL "+str(why))
def sha(p): return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def save(p,obj):
    p=pathlib.Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(obj,sort_keys=True,indent=2)+"\n")
def all_cases():
    manifest=json.loads((SOURCE/"manifest.json").read_text())
    cases=manifest["cases"]
    need(len(cases)==25 and len({c["sha256"] for c in cases})==25,"25 distinct R155 source CNFs required")
    for c in cases:
        need(sha(SOURCE/(c["id"]+".cnf"))==c["sha256"],"original source SHA mismatch "+c["id"])
    return sorted(cases,key=lambda c:c["sha256"])
def cap_for(c): return 30.0 if c["cohort"]=="mixed_residual" else 5.0
def par2(status,elapsed,cap): return round(2*cap if status=="TIMEOUT" else min(cap,elapsed),6)
def status_of(txt,code):
    if re.search(r"(?m)^\s*s\s+UNSATISFIABLE\b|^\s*UNSATISFIABLE\s*$",txt):return "UNSAT"
    if re.search(r"(?m)^\s*s\s+SATISFIABLE\b|^\s*SATISFIABLE\s*$",txt):return "SAT"
    if code==20:return "UNSAT"
    if code==10:return "SAT"
    return "UNKNOWN"
def check_witness(path, txt, minisat=False):
    n,clauses=exact.parse_dimacs(path)
    lines=txt.splitlines()
    tokens=[]
    for index,line in enumerate(lines):
        s=line.strip()
        if s.startswith("v ") or s.startswith("v\t"):
            tokens.extend(s.split()[1:])
        elif minisat and index>0 and re.match(r"^-?\d+(?:\s+-?\d+)*\s*$",s):
            tokens.extend(s.split())
    values={}
    for word in tokens:
        try: lit=int(word)
        except ValueError:continue
        if lit==0:continue
        need(0<abs(lit)<=n,"witness outside source variable range")
        need(abs(lit) not in values or values[abs(lit)]==(lit>0),"contradictory SAT model literals")
        values[abs(lit)]=(lit>0)
    need(values and all(any(values.get(abs(l))==(l>0) for l in clause) for clause in clauses),
         "SAT witness not valid for original SHA CNF")
    return True
def tool_cmd(mode,src,out):
    if mode=="kissat404":return [str((ROOT/"bin/kissat").resolve()),str(src.resolve())]
    if mode=="cryptominisat":return ["cryptominisat5",str(src.resolve())]
    if mode=="picosat":return ["picosat",str(src.resolve())]
    if mode=="minisat":return ["minisat","-verb=0",str(src.resolve()),str(out.resolve())]
    raise ValueError(mode)
def external(c,mode,rep):
    src=SOURCE/(c["id"]+".cnf")
    cap=cap_for(c)
    out=ROOT/("model-"+c["id"]+"-"+mode+"-"+str(rep)+".txt")
    out.unlink(missing_ok=True)
    command=tool_cmd(mode,src,out)
    beg=time.perf_counter()
    try:
        p=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=cap)
        elapsed=time.perf_counter()-beg
    except subprocess.TimeoutExpired:
        return dict(status="TIMEOUT",elapsed=cap,par2=2*cap,cap=cap,
                    proof="CENSORED_TIMEOUT",sat_witness_verified=False)
    need(p.returncode in (0,10,20),"solver crashed: "+mode+" return="+str(p.returncode)+" stderr="+p.stderr[-500:].decode(errors="replace"))
    output=p.stdout.decode(errors="replace")
    model=out.read_text(errors="replace") if mode=="minisat" and out.exists() else output
    status=status_of(output+"\n"+model,p.returncode)
    need(status in ("SAT","UNSAT"),"solver did not provide interpretable SAT/UNSAT: "+mode+" "+output[-250:])
    valid=check_witness(src,model,minisat=(mode=="minisat")) if status=="SAT" else False
    return dict(status=status,elapsed=round(elapsed,6),par2=par2(status,elapsed,cap),cap=cap,
                proof="ORIGINAL_CNFSAT_WITNESS_CHECKED" if valid else "UNSAT_NO_INDEPENDENT_PROOF",
                sat_witness_verified=valid)
def router(c,rep,binary):
    src=SOURCE/(c["id"]+".cnf")
    cap=cap_for(c)
    beg=time.perf_counter()
    answer=exact.solve(src)
    classified=time.perf_counter()-beg
    need(answer["source_sha256"]==c["sha256"],"router original source mismatch")
    if answer["pure_exact"]:
        status=answer["status"]
        need(status in ("SAT","UNSAT"),"exact route invalid answer")
        return dict(status=status,elapsed=round(classified,6),
                    par2=par2(status,classified,cap),cap=cap,pure_exact=True,
                    proof=answer["proof"],sat_witness_verified=(status=="SAT"))
    need(answer["status"]=="NOT_PURE","mixed formula must be routed to CDCL")
    if classified>=cap:
        return dict(status="TIMEOUT",elapsed=cap,par2=2*cap,cap=cap,
                    pure_exact=False,proof="ROUTER_TIMEOUT",sat_witness_verified=False)
    rem=cap-classified
    empty=ROOT/"empty.tsv"
    start=time.perf_counter()
    try:
        p=subprocess.run([str(binary.resolve()),"clean",str(src.resolve()),str(empty.resolve()),str(rem)],
                         stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=rem+10)
    except subprocess.TimeoutExpired as err:
        raise RuntimeError("native CDCL fallback failed to honor cap "+c["id"]) from err
    elapsed=classified+time.perf_counter()-start
    need(p.returncode in (0,10,20),"R165 clean fallback crashed")
    txt=p.stdout.decode(errors="replace")
    match=re.search(r"(?m)^R165_RESULT mode=clean status=(SAT|UNSAT|UNKNOWN)\b",txt)
    need(match is not None,"R165 fallback native result missing")
    status={"SAT":"SAT","UNSAT":"UNSAT","UNKNOWN":"TIMEOUT"}[match[1]]
    need(p.returncode=={"SAT":10,"UNSAT":20,"TIMEOUT":0}[status],"native fallback status mismatch")
    if status=="SAT":native.sat_check(src,txt)
    return dict(status=status,elapsed=round(elapsed,6),par2=par2(status,elapsed,cap),
                cap=cap,pure_exact=False,router_classification_s=round(classified,6),
                proof="ORIGINAL_CNFSAT_WITNESS_CHECKED" if status=="SAT" else "NATIVE_UNSAT_NO_LRAT" if status=="UNSAT" else "CENSORED_TIMEOUT",
                sat_witness_verified=(status=="SAT"))
def verify_inputs(binary):
    need(binary.is_file(),"R165 frozen binary missing")
    pin=json.loads(pathlib.Path("r165/build-pin.json").read_text())
    need(pin["binary_sha256"]==PINNED_R165==sha(binary),"R165 frozen SHA drift")
    need(pin["commit"]==PINNED_R165_SOURCE,"R165 source drift")
    need((ROOT/"bin/kissat").is_file(),"Kissat missing")
    need((ROOT/"kissat-pin.json").is_file(),"Kissat pin missing")
    for name in ("cryptominisat5","minisat","picosat"):
        need(shutil.which(name),"reference executable missing: "+name)
    (ROOT/"empty.tsv").write_text("")
def shard(idx,binary):
    need(idx in range(SHARDS),"invalid shard number")
    if hasattr(os,"sched_getaffinity"):
        mask=os.sched_getaffinity(0)
        if mask:os.sched_setaffinity(0,{min(mask)})
    cases=all_cases();verify_inputs(binary)
    selected=[c for j,c in enumerate(cases) if j%SHARDS==idx]
    need(len(selected)==5,"expected five cases per shard")
    results=[]
    for c in selected:
        prep=native.prepare(c)
        for rep in range(REPS):
            order=list(MODES)
            random.Random("R166X-SHUFFLE-"+c["sha256"]+"-"+str(rep)).shuffle(order)
            for mode in order:
                if mode=="r165_exact_router": r=router(c,rep,binary)
                elif mode in native.MODES:
                    raw=native.trial(c,mode,rep,prep,binary)
                    r=dict(status=raw["status"],elapsed=raw["elapsed"],par2=raw["par2"],
                           cap=raw["cap"],proof=raw["proof"],
                           sat_witness_verified=(raw["status"]=="SAT"),
                           native_stats=raw["native_stats"],
                           charged_preprocess_s=raw["charged_preprocess_s"],
                           proposed_GF2=raw["direct_proposals"],
                           completed_reasons=raw["reason_clauses_completed"])
                else:r=external(c,mode,rep)
                row=dict(id=c["id"],sha256=c["sha256"],family=c["family"],
                         cohort=c["cohort"],mode=mode,rep=rep,**r)
                need(row["status"] in ("SAT","UNSAT","TIMEOUT"),"invalid status")
                results.append(row)
                save(ROOT/f"shard-{idx}.json",results)
                print("R166X_TRIAL",json.dumps({k:row[k] for k in ("id","cohort","mode","rep","status","elapsed","cap","par2","sat_witness_verified")},sort_keys=True),flush=True)
    need(len(results)==5*REPS*len(MODES),"incomplete shard")
    print("R166X_SHARD_PASS",idx,len(results),flush=True)
def audit():
    cases=all_cases()
    records=[]
    for idx in range(SHARDS):
        file=ROOT/f"shard-{idx}.json"
        need(file.exists(),"missing shard "+str(idx))
        records+=json.loads(file.read_text())
    need(len(records)==25*REPS*len(MODES),"trial count mismatch")
    keys={(r["sha256"],r["rep"],r["mode"]) for r in records}
    need(len(keys)==len(records),"duplicate comparison")
    for c in cases:
        subset=[r for r in records if r["sha256"]==c["sha256"]]
        need(len(subset)==REPS*len(MODES),"formula missing comparison "+c["id"])
        need({r["cohort"] for r in subset}=={c["cohort"]},"cohort drift")
        answers={r["status"] for r in subset if r["status"]!="TIMEOUT"}
        need(len(answers)<=1,"conflicting SAT/UNSAT on "+c["id"])
        need(all(r["status"]!="SAT" or r["sat_witness_verified"] for r in subset),"unverified SAT witness "+c["id"])
        for r in subset:
            need(abs(r["par2"]-par2(r["status"],r["elapsed"],r["cap"]))<0.0001,"PAR2 calculation")
    summary={}
    for cohort in ["all"]+sorted({c["cohort"] for c in cases}):
        arr=[r for r in records if cohort=="all" or r["cohort"]==cohort]
        summary[cohort]={}
        for mode in MODES:
            rows=[r for r in arr if r["mode"]==mode]
            summary[cohort][mode]=dict(trials=len(rows),
                solved=sum(r["status"]!="TIMEOUT" for r in rows),
                sat=sum(r["status"]=="SAT" for r in rows),
                unsat=sum(r["status"]=="UNSAT" for r in rows),
                PAR2_s=round(sum(r["par2"] for r in rows),6),
                wall_s=round(sum(r["elapsed"] for r in rows),6),
                median_wall_s=round(sorted(r["elapsed"] for r in rows)[len(rows)//2],6))
    paired=[]
    for mode in MODES:
        if mode=="clean":continue
        joint=[]
        for c in cases:
            for rep in range(REPS):
                clean=next(r for r in records if r["sha256"]==c["sha256"] and r["rep"]==rep and r["mode"]=="clean")
                other=next(r for r in records if r["sha256"]==c["sha256"] and r["rep"]==rep and r["mode"]==mode)
                if clean["status"]!="TIMEOUT" and other["status"]!="TIMEOUT":
                    joint.append(clean["elapsed"]/max(other["elapsed"],1e-9))
        paired.append(dict(mode=mode,uncensored_pairs=len(joint),
                           median_speedup_vs_clean=round(sorted(joint)[len(joint)//2],5) if joint else None))
    obj=dict(status="R166X_COMPLETE_RESEARCH_ONLY_NOT_BLIND",R165_binary_sha=PINNED_R165,
             R165_source_sha=PINNED_R165_SOURCE,kissat_pin=json.loads((ROOT/"kissat-pin.json").read_text()),
             formulas=25,attempts=len(records),repetitions=REPS,shards=SHARDS,
             modes=list(MODES),summary=summary,paired_uncensored=paired,records=records,
             notes=["Original R155 development CNFs; NOT previously unseen, not world ranking.",
               "PAR2 is 2*cap for each TIMEOUT; censored speedup is NOT an exact speed ratio.",
               "All source CNFs SHA verified; independent SAT models checked; UNSAT no LRAT except GF2 internal parity certificate.",
               "R165 direct modes charge source GF2 preprocessing at every attempt; routed exact includes detection cost.",
               "External solvers get identical per-formula wall-time caps, one CPU affinity and shuffled within-shard order.",
               "Shards may use different runner CPUs; pair comparisons are only within same source and runner."])
    save(ROOT/"report.json",obj)
    with open(ROOT/"summary.md","w") as f:
        f.write("# R166x — R165 vs Kissat 4.0.4, CaDiCaL 2.1.0, CryptoMiniSat, MiniSat, PicoSAT\n\n")
        f.write("25 original, SHA-verified R155 CNFs; two repeats, 5 parallel shards. RESEARCH ONLY, not blind.\n\n")
        f.write("| Solver/mode | Solved | PAR2 s | Measured wall s |\n|---|---:|---:|---:|\n")
        for mode in MODES:
            d=summary["all"][mode]
            f.write(f'| {mode} | {d["solved"]}/{d["trials"]} | {d["PAR2_s"]:.3f} | {d["wall_s"]:.3f} |\n')
        f.write("\n*No exact speedup can be inferred where a solver timed out.*\n")
    print("R166X_FINAL",json.dumps({"status":obj["status"],"formulas":25,"attempts":len(records),
      "summary":summary["all"],"paired_uncensored":paired},sort_keys=True),flush=True)
if __name__=="__main__":
    arg=argparse.ArgumentParser()
    arg.add_argument("task",choices=("shard","audit"))
    arg.add_argument("--shard",type=int,default=0)
    arg.add_argument("--binary",default="r165/r165-native")
    a=arg.parse_args()
    if a.task=="shard":shard(a.shard,pathlib.Path(a.binary))
    else:audit()
