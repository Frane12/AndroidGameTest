#!/usr/bin/env python3
"""DRNAS R168 preregistered official SAT 2026 blind mixed GF2/CDCL benchmark.

Source selection is frozen in r168_blind_manifest.json AFTER the C++ binary
preblind success run 42151426617. Exact native binary SHA validated. On all
12 never-used-for-R167 GBD formulas, run same-binary CaDiCaL clean vs new
bidirectional GF2/CDCL (two repetitions, deterministic paired order, cap 20s).
No substitutions or cherry-picked sources. Missing data are INFRA. UNSAT via
CDCL is NOT independently LRAT/FRAT verified. Research only, not official rank.
"""
import argparse, collections, hashlib, json, os, pathlib, random, subprocess, sys, time
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import r167_blind2026 as transport
import r166_independent_verifier as independent

ROOT=pathlib.Path("r168")
transport.ROOT=ROOT
MANIFEST=ROOT/"blind-manifest.json"
MODES=("mixed","clean")
SHARDS=4

def check(ok,msg):
    if not ok:raise RuntimeError("R168_BLIND_AUDIT_FAIL "+msg)
def rd(path):return json.loads(pathlib.Path(path).read_text())
def wr(path,obj):
    pathlib.Path(path).write_text(json.dumps(obj,sort_keys=True,indent=2)+"\n")
def sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
def setup():
    m=rd(MANIFEST)
    check(m["protocol"]=="DRNAS-R168-2026-MAIN-BLIND-FROZEN-12-v1",
          "unexpected manifest protocol")
    check(len(m["selection"])==12 and m["repetitions"]==2 and
          m["cap_per_solver_s"]==20 and m["matrix_shards"]==SHARDS,"bad frozen parameters")
    previous=set(m["previous_r167_indices"])
    indices={x["index"] for x in m["selection"]}
    check(len(indices)==12 and not (indices&previous),"holdout overlaps old R167")
    check(len({c["gbd_md5"] for c in m["selection"]})==12,"duplicate GBD IDs")
    return m,m["selection"]
def pinned(binary):
    pin=rd(ROOT/"build-pin.json")
    m,_=setup()
    check(pin["source_commit"]==m["native_build_source_commit"],"wrong frozen native source commit")
    check(pin["binary_sha256"]==m["pinned_native_sha256"],"wrong native binary pin")
    check(sha(binary)==pin["binary_sha256"],"native executable drift")
    for path,key in [
       ("research/r168_native_mixed_gf2.cpp","native_cpp_sha256"),
       ("research/r168_proven_gf2_bridge.cpp","bridge_cpp_sha256"),
       ("research/r167_native_exact_gf2.cpp","r167_cpp_sha256"),
       ("research/r133c_native_gf2_cdcl_bridge.cpp","r133c_cpp_sha256")
    ]:
        check(sha(path)==pin[key],"C++ source changed after code freeze: "+path)
    return pin
def parse_model(output,path):
    lines=output.splitlines()
    model={}
    for line in lines:
        if not line.startswith("v "):continue
        for string in line[2:].split():
            lit=int(string)
            if not lit:continue
            k=abs(lit)
            check(k not in model or model[k]==(lit>0),"contradicting model bits")
            model[k]=lit>0
    variables,clauses=independent.read_dimacs(path)
    check(len(model)>=variables,"native SAT witness incomplete")
    for clause in clauses:
        check(any(model.get(abs(lit))==(lit>0) for lit in clause),
              "SAT witness violates original source CNF")
    return len(clauses)
def trial(case,path,mode,rep,binary,cap):
    proof=ROOT/(f'proof-{case["gbd_md5"]}-{rep}.json')
    proof.unlink(missing_ok=True)
    cmd=[str(binary.resolve()),str(path.resolve()),"--mode",mode,"--cap",str(cap)]
    if mode=="mixed":cmd+=["--proof",str(proof.resolve())]
    start=time.perf_counter()
    proc=subprocess.run(cmd,text=True,capture_output=True,timeout=cap+20)
    elapsed=time.perf_counter()-start
    check(proc.returncode in (0,10,20),
          "native failure "+proc.stderr[-1200:])
    lines=proc.stdout.splitlines()
    arr=[json.loads(line[len("R168_RESULT "):])
         for line in lines if line.startswith("R168_RESULT ")]
    check(len(arr)==1,"no complete native R168_RESULT line")
    d=arr[0]
    check(d["mode"]==mode and d["source_sha256"]==sha(path) and
          abs(d["cap_s"]-cap)<0.0001,"native case provenance/cap mismatch")
    check(proc.returncode=={"SAT":10,"UNSAT":20,"TIMEOUT":0}[d["status"]],
          "native return/status mismatch")
    check(d["gf2_disabled"]==0,"incremental GF2 invariant disabled")
    check("s "+{"SAT":"SATISFIABLE","UNSAT":"UNSATISFIABLE","TIMEOUT":"UNKNOWN"}[d["status"]] in lines,
          "malformed native SAT status line")
    if mode=="clean":
        check(d["route"].startswith("CDCL_CLEAN") and d["source_rows_imported"]==0,
              "clean baseline accidentally got GF2")
    else:
        check(d["route"] in ("MIXED_GF2_CDCL","CDCL_NO_CERTIFIED_XOR",
               "NATIVE_EXACT_GF2","MIXED_GF2_CDCL_OVER_CAP",
               "CDCL_NO_CERTIFIED_XOR_OVER_CAP","NATIVE_EXACT_GF2_OVER_CAP"),
              "unexpected R168 native route")
    gf2_cert=False
    if mode=="mixed" and d["route"]=="NATIVE_EXACT_GF2":
        check(proof.is_file(),"missing source GF2 certificate")
        verified=independent.verify(path,rd(proof))
        check(verified["status"]==d["status"],"independent XOR verification mismatch")
        gf2_cert=True
    else:check(not proof.exists(),"unexpected source proof on non-exact path")
    if d["status"]=="SAT":
        parse_model(proc.stdout,path)
    if elapsed>cap and d["status"]!="TIMEOUT":
        raise RuntimeError("wall cap exceeded without correct timeout status")
    return {
        "index":case["index"],"gbd_md5":case["gbd_md5"],"source_sha256":sha(path),
        "mode":mode,"repeat":rep,"status":d["status"],"route":d["route"],
        "cap_s":cap,"wall_s":round(elapsed,6),"native_wall_s":d["wall_s"],
        "par2_s":round(2*cap if d["status"]=="TIMEOUT" else elapsed,6),
        "detected_certified_rows":d["certified_rows"],
        "imported_rows":d["source_rows_imported"],
        "derived_rows":d["derived_rows"],
        "GF2_proposals":d["gf2_proposals"],
        "GF2_completed_reasons":d["gf2_completed_reasons"],
        "GF2_incremental_events":d["gf2_incremental_events"],
        "GF2_propagate_ns":d["gf2_propagate_ns"],
        "source_SAT_model_checked":d["status"]=="SAT",
        "independent_GF2_certificate":gf2_cert,
        "UNSAT_independently_proven":gf2_cert and d["status"]=="UNSAT"
    }
def shard(idx,binary):
    m,cases=setup()
    check(idx in range(SHARDS),"invalid shard")
    pin=pinned(binary)
    if hasattr(os,"sched_getaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    rows=[];sources=[];failures=[]
    for i,case in enumerate(cases):
        if i%SHARDS!=idx:continue
        source,path=transport.acquire(case,i)
        sources.append(source)
        print("R168_SOURCE",json.dumps(source,sort_keys=True),flush=True)
        if path is None:continue
        for rep in range(m["repetitions"]):
            modes=list(MODES)
            random.Random("R168-FROZEN-BLIND-"+case["gbd_md5"]+str(rep)).shuffle(modes)
            for mode in modes:
                try:
                    row=trial(case,path,mode,rep,binary,float(m["cap_per_solver_s"]))
                    rows.append(row)
                    print("R168_BLIND_TRIAL",json.dumps(row,sort_keys=True),flush=True)
                except Exception as exc:
                    err={"gbd_md5":case["gbd_md5"],"index":case["index"],
                         "mode":mode,"repeat":rep,"exception":str(exc)[:1000]}
                    failures.append(err)
                    print("R168_INFRA_OR_INVARIANT_FAILURE",json.dumps(err),flush=True)
                wr(ROOT/f"shard-{idx}.json",{
                    "shard":idx,"pin":pin,"sources":sources,
                    "trials":rows,"failures":failures})
    wr(ROOT/f"shard-{idx}.json",{
        "shard":idx,"pin":pin,"sources":sources,"trials":rows,"failures":failures})
    print("R168_BLIND_SHARD_PASS",idx,len(rows),len(failures),flush=True)
def audit():
    m,cases=setup()
    sources=[];rows=[];failures=[];pins=[]
    for idx in range(SHARDS):
        d=rd(ROOT/f"shard-{idx}.json")
        check(d["shard"]==idx,"shard mismatch")
        sources+=d["sources"];rows+=d["trials"];failures+=d["failures"]
        pins.append(d["pin"])
    check(len({p["binary_sha256"] for p in pins})==1 and
          all(p["binary_sha256"]==m["pinned_native_sha256"] for p in pins),
          "binary SHA mismatch across shards")
    check(len(sources)==12,"incomplete source selection")
    check({(c["index"],c["gbd_md5"]) for c in cases}==
          {(s["index"],s["gbd_md5"]) for s in sources},"source set changed")
    available={s["gbd_md5"]:s for s in sources if s["status"]=="SOURCE_OK"}
    keys=set()
    for r in rows:
        key=r["gbd_md5"],r["repeat"],r["mode"]
        check(key not in keys,"duplicate paired row")
        check(r["gbd_md5"] in available and
              available[r["gbd_md5"]]["source_sha256"]==r["source_sha256"],
              "original CNF SHA did not match its source")
        check(r["mode"] in MODES and r["repeat"] in (0,1),"trial dimension drift")
        check(abs(r["par2_s"]-
             (2*r["cap_s"] if r["status"]=="TIMEOUT" else r["wall_s"]))<1e-5,
              "invalid PAR2")
        keys.add(key)
    pairs=[]
    for c in cases:
        for rep in range(2):
            d={r["mode"]:r for r in rows
                if r["gbd_md5"]==c["gbd_md5"] and r["repeat"]==rep}
            if set(d)!=set(MODES):continue
            a,b=d["mixed"],d["clean"]
            check(not(a["status"]!="TIMEOUT" and b["status"]!="TIMEOUT" and
                  a["status"]!=b["status"]),"contradictory SAT/UNSAT")
            speedup=None
            if a["status"]!="TIMEOUT" and b["status"]!="TIMEOUT":
                speedup=round(b["wall_s"]/max(a["wall_s"],1e-6),3)
            lower=None
            if a["status"]!="TIMEOUT" and b["status"]=="TIMEOUT":
                lower=round(b["cap_s"]/max(a["wall_s"],1e-6),3)
            pairs.append({
              "index":c["index"],"gbd_md5":c["gbd_md5"],"repeat":rep,
              "mixed":a,"clean":b,
              "both_solved_speedup":speedup,
              "one_sided_timeout_speedup_lower_bound":lower})
    summary={}
    for mode in MODES:
        subset=[r for r in rows if r["mode"]==mode]
        summary[mode]={
            "trials":len(subset),
            "solved":sum(r["status"]!="TIMEOUT" for r in subset),
            "SAT":sum(r["status"]=="SAT" for r in subset),
            "UNSAT":sum(r["status"]=="UNSAT" for r in subset),
            "PAR2_s_all_completed":round(sum(r["par2_s"] for r in subset),4),
            "GF2_proposals":sum(r["GF2_proposals"] for r in subset),
            "GF2_completed_reasons":sum(r["GF2_completed_reasons"] for r in subset),
            "GF2_incremental_events":sum(r["GF2_incremental_events"] for r in subset),
            "source_exact_fastpaths":sum(r["route"]=="NATIVE_EXACT_GF2" for r in subset),
            "native_mixed_bridge_attempts":sum(r["route"]=="MIXED_GF2_CDCL" for r in subset),
        }
    comparable={mode:round(sum(p[mode]["par2_s"] for p in pairs),4)
                for mode in MODES}
    state="BLIND_AUDIT_PASS" if len(available)==12 and len(pairs)==24 and not failures else (
          "BLIND_PARTIAL_INFRA_OR_ERRORS" if pairs else "BLIND_NO_VALID_PAIRED_RESULTS")
    report={
        "status":state,
        "protocol":m["protocol"],
        "official_source":"SAT Competition 2026 Main official GBD",
        "official_source_list_git_blob_sha1":m["official_uri_git_blob_sha1"],
        "native_source_build_run":m["native_build_run"],
        "binary_sha256":pins[0]["binary_sha256"],
        "selected_count":12,
        "source_acquisition_success":len(available),
        "valid_matched_pairs":len(pairs),
        "caps":m["cap_per_solver_s"],
        "not_official_competition":True,
        "sources":sources,"failures":failures,"summary":summary,
        "paired_comparable_PAR2":comparable,"pairs":pairs,
        "limitations":[
          "Code and binary frozen before selecting these 12 official 2026 identifiers",
          "Short 20s caps and two repetitions do not equal official competition conditions",
          "Some official formulas may be too difficult to solve under this cap",
          "Independent SAT source witness checks; pure GF2 UNSAT parity replay, no LRAT/FRAT for mixed UNSAT",
          "GF2 completed reasons do not by themselves prove a runtime advantage",
          "Missing files and failed trials are never called algorithm timeout",
        ]
    }
    wr(ROOT/"blind-report.json",report)
    lines=["# R168 native GF2/CDCL official 2026 blind holdout","",
        f"Status: **{state}**; valid original sources {len(available)}/12; valid paired comparisons {len(pairs)}/24.",
        "Same binary CaDiCaL 2.1.0; per-run 20s; 2 repetitions; 4 parallel shards.",
        "",
        "| Mode | Trials | Solved | SAT | UNSAT | PAR2 | GF2 proposals | Completed reasons |",
        "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for mode in MODES:
        z=summary[mode]
        lines.append(f'| {mode} | {z["trials"]} | {z["solved"]} | {z["SAT"]} | {z["UNSAT"]} | {z["PAR2_s_all_completed"]} | {z["GF2_proposals"]} | {z["GF2_completed_reasons"]} |')
    lines.extend(["",
      f'Matched PAR2 mixed {comparable["mixed"]}, clean {comparable["clean"]}.',
      "", "## Matched original formulas"])
    for pair in pairs:
        a,b=pair["mixed"],pair["clean"]
        lines.append(f'- #{pair["index"]} run {pair["repeat"]} | GF2/CDCL {a["status"]} '
          f'{a["wall_s"]}s route={a["route"]} imported={a["imported_rows"]} '
          f'propagations={a["GF2_proposals"]} reasons={a["GF2_completed_reasons"]} '
          f'| clean {b["status"]} {b["wall_s"]}s')
    if failures:
        lines.extend(["","## Failures / infra",""])
        lines.extend("- "+str(f)[:270] for f in failures)
    lines.append("")
    lines.append("RESEARCH ONLY — not an official SAT Competition rank.")
    (ROOT/"blind-summary.md").write_text("\n".join(lines)+"\n")
    print("R168_BLIND_FINAL",json.dumps({
      "status":state,"sources":len(available),"valid_pairs":len(pairs),
      "summary":summary,"paired_comparable_PAR2":comparable},sort_keys=True),flush=True)
if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("action",choices=("shard","audit"))
    ap.add_argument("--shard",type=int,default=0)
    ap.add_argument("--binary",default="r168/native")
    a=ap.parse_args()
    if a.action=="shard":shard(a.shard,pathlib.Path(a.binary))
    else:audit()
