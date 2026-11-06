#!/usr/bin/env python3
"""DRNAS R172 R153 exact XOR router + R166X source-certified mixed Gaussian/CDCL.

Fixed 25 previously seen ORIGINAL SHA CNFs, four same-CNF modes:
  clean          native CaDiCaL
  r153_router    pure exactly encoded XOR -> verified exact GF2; otherwise clean
  r166x_gauss    proof-certified Gaussian/CDCL if source rows/units, otherwise clean
  fused          exact pure-XOR first; otherwise certified Gaussian/CDCL or clean

Preprocessing AND router detection time are charged inside each per-arm cap.
Development replay, not blind; no claims about independent UNSAT LRAT.
"""
import argparse,hashlib,json,os,pathlib,random,statistics,subprocess,sys,time
sys.path.insert(0,str(pathlib.Path("research").resolve()))
import r166x_component_benchmark as base
import r164_pure_exact_gf2 as exact
import r166x_certified_gauss as gaussian

ROOT=pathlib.Path("r172")
base.ROOT=ROOT
base.FROZEN=ROOT/"frozen"
MODES=("clean","r153_router","r166x_gauss","fused")
REPS=2
SHARDS=5
PROTO="DRNAS-R172-R153-EXACT-ROUTER-R166X-CERTIFIED-GAUSS-20261106-v1"
def need(v,msg):
    if not v: raise RuntimeError("R172_FAIL_CLOSED "+str(msg))
def sha(path):return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
def rd(path):return json.loads(pathlib.Path(path).read_text())
def save(path,obj):
    p=pathlib.Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(obj,sort_keys=True,indent=2)+"\n")
def cases():
    m=rd(base.FROZEN/"manifest.json")
    out=sorted(m["cases"],key=lambda c:c["id"])
    need(len(out)==25 and len({c["sha256"] for c in out})==25,"expected frozen 25 distinct originals")
    for c in out:
        need(sha(base.FROZEN/(c["id"]+".cnf"))==c["sha256"],"CNF source SHA drift")
    return out

def capped_native(case,native_mode,cap,binary,prep,router_s=0.0):
    src=base.FROZEN/(case["id"]+".cnf")
    isgauss=native_mode=="gauss_cooldown"
    charge=prep["gauss_preprocessing_s"] if isgauss else 0.0
    unitfile=None
    if isgauss:
        tsv=ROOT/("gauss-"+case["id"])/"gauss.tsv"
        unitfile=ROOT/("gauss-"+case["id"])/"gauss-units.tsv"
        need(sha(tsv)==prep["gauss_rows_sha"] and sha(unitfile)==prep["gauss_units_sha"],
             "Gaussian proof TSV mutated")
    else:
        tsv=ROOT/"empty-rows.tsv"
        need(tsv.read_text()=="","clean control must have no injected rows")
    available=cap-charge-router_s
    if available<0.5:
        return dict(status="TIMEOUT",elapsed=round(charge+router_s,6),
            native_mode="budget_exhausted",native_s=0.0,source_rows=0,
            gauss_units=0,conflicts=None,decisions=None,
            native_reason_clauses=0,preprocess_s=round(charge,6))
    argv=[str(binary.resolve()),native_mode,str(src.resolve()),str(tsv.resolve()),str(available)]
    if isgauss:argv.append(str(unitfile.resolve()))
    start=time.perf_counter()
    try:
        proc=subprocess.run(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=available+12)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("R172_NATIVE_STUCK "+case["id"]) from exc
    wall=time.perf_counter()-start
    need(proc.returncode in (0,10,20),
        "native crashed: "+proc.stderr[-800:].decode(errors="replace"))
    txt,native,stats,rows,derived=base.parse_native(proc.stdout,native_mode)
    status={"SAT":"SAT","UNSAT":"UNSAT","UNKNOWN":"TIMEOUT"}[native["status"]]
    need(proc.returncode=={"SAT":10,"UNSAT":20,"TIMEOUT":0}[status],
         "exit code and result disagree")
    need(rows==(prep["gauss_source_rows"] if isgauss else 0),
         "native certified rows disagree")
    need(int(native.get("gauss_units",0))==(prep["gauss_units"] if isgauss else 0),
         "native GF2 units mismatch")
    need(abs(float(native["solver_s"])-wall)<0.9,"native elapsed clock differs from measured wall")
    if status=="SAT":
        need(native.get("source_sat_witness_checked")=="1","native SAT witness flag missing")
        base.sat_check(src,txt)
    return dict(status=status,elapsed=round(wall+charge+router_s,6),
         native_mode=native_mode,native_s=round(wall,6),source_rows=rows,
         gauss_units=int(native.get("gauss_units",0)),
         conflicts=stats.get("conflicts"),decisions=stats.get("decisions"),
         native_reason_clauses=int(native["reason_clauses_completed"]),
         preprocess_s=round(charge,6))

def trial(case,mode,rep,prep,binary):
    cap=30.0 if case["cohort"]=="mixed_residual" else 5.0
    src=base.FROZEN/(case["id"]+".cnf")
    route_s=0.0
    route="none"
    exact_answer=None
    if mode in ("r153_router","fused"):
        t=time.perf_counter()
        exact_answer=exact.solve(src)
        route_s=time.perf_counter()-t
        need(exact_answer["source_sha256"]==case["sha256"],"exact source changed")
        if exact_answer["pure_exact"]:
            need(exact_answer["status"] in ("SAT","UNSAT"),"pure XOR unresolved")
            route="exact_pure_xor"
            # exact.solve already independently validates SAT against original CNF,
            # UNSAT is verified XOR parity contradiction, NOT LRAT.
            result=dict(status=exact_answer["status"],elapsed=round(route_s,6),
                native_mode="none_exact",native_s=0.0,source_rows=exact_answer["xor_rows"],
                gauss_units=0,conflicts=None,decisions=None,
                native_reason_clauses=0,preprocess_s=0.0)
        else:
            need(exact_answer["status"]=="NOT_PURE","mixed falsely accepted as exact")
    if route!="exact_pure_xor":
        if mode in ("r166x_gauss","fused"):
            # Gate ONLY from independently certified source GF2 structure, never
            # source labels or previously observed per-instance benchmark speed.
            enabled=(prep["gauss_source_rows"]>0 or prep["gauss_units"]>0 or
                     prep["gauss_source_unsat"])
            route="certified_gaussian_cdcl" if enabled else "clean_no_certified_xor"
            native_mode="gauss_cooldown" if enabled else "clean"
        else:
            route="clean" if mode=="clean" else "router_mixed_fallback"
            native_mode="clean"
        result=capped_native(case,native_mode,cap,binary,prep,route_s)
        if mode in ("r166x_gauss","fused") and native_mode=="clean":
            # Even a negative structural detection incurs preprocessing cost,
            # and must not get free work or a hidden budget extension.
            result["elapsed"]=round(result["elapsed"]+prep["gauss_preprocessing_s"],6)
            result["preprocess_s"]=prep["gauss_preprocessing_s"]
    result.update(id=case["id"],sha256=case["sha256"],cohort=case["cohort"],
                  family=case.get("family",""),mode=mode,repeat=rep,
                  cap=cap,route=route,router_check_s=round(route_s,6),
                  pure_exact=bool(exact_answer["pure_exact"]) if exact_answer else None,
                  original_source_sha_verified=True,
                  proof=("ORIGINAL_SAT_CHECKED" if result["status"]=="SAT"
                         else "EXACT_GF2_CONTRADICTION_REPLAYED_NO_LRAT"
                         if route=="exact_pure_xor" and result["status"]=="UNSAT"
                         else "NATIVE_UNSAT_NO_INDEPENDENT_LRAT"
                         if result["status"]=="UNSAT" else "TIMEOUT"))
    result["par2"]=round(2*cap if result["status"]=="TIMEOUT"
                         else min(cap,result["elapsed"]),6)
    return result

def shard(index,binary):
    need(0<=index<SHARDS,"invalid shard index")
    need(binary.is_file(),"missing binary")
    pin=rd(ROOT/"build-pin.json")
    need(sha(binary)==pin["binary_sha256"],"native binary SHA drift")
    need(pin["source_commit"]==os.environ.get("GITHUB_SHA",pin["source_commit"]),
         "source SHA drift")
    if hasattr(os,"sched_getaffinity"):
        cs=os.sched_getaffinity(0)
        if cs:os.sched_setaffinity(0,{min(cs)})
    cs=cases();(ROOT/"empty-rows.tsv").write_text("")
    rows=[]
    for i,case in enumerate(cs):
        if i%SHARDS!=index:continue
        prep=base.prepare(case)
        for rep in range(REPS):
            order=list(MODES);random.Random(PROTO+case["sha256"]+str(rep)).shuffle(order)
            for mode in order:
                row=trial(case,mode,rep,prep,binary)
                rows.append(row);save(ROOT/f"shard-{index}.json",rows)
                print("R172_TRIAL",json.dumps({k:row[k] for k in
                    ("id","cohort","mode","repeat","status","route","elapsed","par2","router_check_s")},
                    sort_keys=True),flush=True)
    need(len(rows)==5*len(MODES)*REPS,"wrong shard trial count")
    print("R172_SHARD_PASS",index,len(rows),flush=True)

def audit():
    cs=cases();rows=[];keys=set()
    for idx in range(SHARDS):
        data=rd(ROOT/f"shard-{idx}.json")
        need(len(data)==5*len(MODES)*REPS,"shard incomplete")
        for v in data:
            key=(v["sha256"],v["repeat"],v["mode"])
            need(key not in keys,"duplicated attempt")
            keys.add(key);rows.append(v)
    need(len(rows)==25*REPS*len(MODES)==200,"expected 200 attempts")
    statuses={}
    for c in cs:
        source=base.FROZEN/(c["id"]+".cnf")
        need(sha(source)==c["sha256"],"audit source SHA mismatch")
        prep=rd(ROOT/("prep-"+c["id"]+".json"))
        ev=rd(ROOT/("cert-"+c["id"]+".json"))
        base.independent_cert(c,ev)
        need(prep["source_sha256"]==c["sha256"],"source GF2 preprocessing drift")
        gd=ROOT/("gauss-"+c["id"])
        need(sha(gd/"gauss-cert.json")==prep["gauss_certificate_sha"],
             "gaussian certificate hash mismatch")
        need(gaussian.replay(source,ev,gd/"gauss-cert.json",gd/"gauss.tsv",gd/"gauss-units.tsv"),
             "source Gaussian proof independently failed")
        matching=[z for z in rows if z["id"]==c["id"]]
        need(len(matching)==REPS*len(MODES),"missing paired same-source arms")
        alive={z["status"] for z in matching if z["status"]!="TIMEOUT"}
        need(len(alive)<=1,"contradictory SAT and UNSAT")
        for rep in range(REPS):
            arms={z["mode"]:z for z in matching if z["repeat"]==rep}
            need(set(arms)==set(MODES),"incomplete arm mapping")
            need(arms["fused"]["route"]==arms["r153_router"]["route"]=="exact_pure_xor"
                 if arms["r153_router"]["route"]=="exact_pure_xor" else
                 arms["fused"]["route"] in ("certified_gaussian_cdcl","clean_no_certified_xor"),
                 "fused route invalid")
            for z in arms.values():
                need(z["sha256"]==c["sha256"] and z["cap"]==(30 if c["cohort"]=="mixed_residual" else 5),
                     "paired source or cap changed")
                need(abs(z["par2"]-(2*z["cap"] if z["status"]=="TIMEOUT"
                      else min(z["cap"],z["elapsed"])))<1e-4,"PAR2 invalid")
                need(z["status"]!="SAT" or z["proof"]=="ORIGINAL_SAT_CHECKED",
                     "SAT evidence absent")
        statuses[c["id"]]=sorted(alive)
    summary={}
    for mode in MODES:
        sub=[z for z in rows if z["mode"]==mode]
        summary[mode]=dict(trials=len(sub),solved=sum(z["status"]!="TIMEOUT" for z in sub),
            SAT=sum(z["status"]=="SAT" for z in sub),
            UNSAT=sum(z["status"]=="UNSAT" for z in sub),
            PAR2_s=round(sum(z["par2"] for z in sub),6),
            wall_s=round(sum(z["elapsed"] for z in sub),6),
            routes={route:sum(z["route"]==route for z in sub) for route in sorted({z["route"] for z in sub})},
            exact_pure=sum(z["route"]=="exact_pure_xor" for z in sub),
            native_gauss=sum(z["native_mode"]=="gauss_cooldown" for z in sub),
            clean_fallback=sum(z["native_mode"]=="clean" for z in sub))
    pairs=[]
    for c in cs:
        for rep in range(REPS):
            arms={z["mode"]:z for z in rows if z["id"]==c["id"] and z["repeat"]==rep}
            for mode in MODES[1:]:
                x=arms["clean"];y=arms[mode]
                both=x["status"]!="TIMEOUT" and y["status"]!="TIMEOUT"
                pairs.append(dict(id=c["id"],repeat=rep,variant=mode,
                  baseline_status=x["status"],variant_status=y["status"],
                  uncensored_speedup=(round(x["elapsed"]/y["elapsed"],5) if both and y["elapsed"]>0 else None),
                  delta_PAR2_s=round(x["par2"]-y["par2"],6)))
    report=dict(status="R172_RESEARCH_PAIRED_AUDIT_PASS_NOT_BLIND",
        protocol=PROTO,formulas=len(cs),attempts=len(rows),
        known_development_sources=True,single_binary_SHA=rd(ROOT/"build-pin.json")["binary_sha256"],
        independent_source_certificates=True,original_SAT_witnesses_checked=True,
        independent_UNSAT_LRAT=False,summary=summary,paired=pairs,records=rows,
        caveats=["Original 25 seen R155 sources, NOT blind holdout",
          "Only finite speedups where BOTH methods actually solve",
          "Preprocessing and exact screening charged inside each cap",
          "Source XOR UNSAT proof replayed but not independent LRAT",
          "Same native binary SHA within run; host CPU may differ by shard",
          "Gaussian activation is structural proof-gated; not prefit to benchmark win labels"])
    save(ROOT/"report.json",report)
    with (ROOT/"summary.md").open("w") as f:
        f.write("# R172 — R153 exact router + R166x certified Gaussian/CDCL\n\n")
        f.write("25 previously seen original SHA CNFs; 200 paired arms, 2 repeats, 5s / 30s cap. NOT BLIND.\n\n")
        f.write("| Mode | Solved | PAR2 s | Exact routes | Gaussian runs | Clean fallback |\n")
        f.write("|---|---:|---:|---:|---:|---:|\n")
        for k,v in summary.items():
            f.write(f'| {k} | {v["solved"]}/{v["trials"]} | {v["PAR2_s"]:.5f} | {v["exact_pure"]} | {v["native_gauss"]} | {v["clean_fallback"]} |\n')
        f.write("\nNo world record or blind win assertion. UNSAT not LRAT-certified.\n")
    print("R172_FINAL",json.dumps(dict(formulas=25,attempts=len(rows),status=report["status"],
                  summary=summary),sort_keys=True),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("shard","audit"))
    p.add_argument("--shard",type=int,default=0)
    p.add_argument("--binary",default="r172/r172-native")
    args=p.parse_args()
    shard(args.shard,pathlib.Path(args.binary)) if args.action=="shard" else audit()
