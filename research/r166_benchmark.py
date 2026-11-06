#!/usr/bin/env python3
"""R166 short 25-original paired regression: clean vs auto (+ R164 incremental on mixed).

Reuses EXACT immutable R164 CaDiCaL 2.1.0 native binary, R155 SHA-pinned
real original CNFs. Auto route is an executable, not a retrospectively
selected minimum. All detection/preprocess/launcher times charged end-to-end
to auto; control native measured externally. Two deterministic repetitions.
Existing development data, NOT a blind or competition benchmark.
"""
import argparse
import collections
import hashlib
import json
import pathlib
import random
import subprocess
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import r164_component_benchmark as base
import r164_pure_exact_gf2 as pure
import r166_independent_verifier as independent

ROOT = pathlib.Path("r166")
base.ROOT = ROOT
base.FROZEN = ROOT / "frozen"
FROZEN_BINARY_SOURCE = "2ff07b3af7f98b9d822b9626d348c681297fd174"
REPS = 2
SHARDS = 5

def require(cond, why):
    if not cond: raise AssertionError("R166_AUDIT_FAIL " + why)

def cases():
    manifest = base.rd(ROOT / "frozen" / "manifest.json")
    require(len(manifest["cases"]) == 25, "25 original manifest cases required")
    arr = sorted(manifest["cases"], key=lambda c: (c["cohort"],c["id"]))
    require(len({c["sha256"] for c in arr}) == 25, "not unique 25 input formulas")
    for c in arr:
        require(base.h(ROOT / "frozen" / (c["id"]+".cnf")) == c["sha256"],
                "pinned original CNF changed")
    return arr

def cap_for(c):
    return 12.0 if c["cohort"] == "mixed_residual" else 5.0

def run_native(c, mode, binary, cap, prepared=None):
    require(mode in ("clean","direct_incremental"), "bad native mode")
    src = ROOT / "frozen" / (c["id"]+".cnf")
    require(base.h(src)==c["sha256"],"native input mutated")
    if mode == "clean":
        tsv = ROOT / "zero-rows.tsv"
        tsv.write_text("")
        charge = 0.0
    else:
        require(prepared is not None, "GF2 certification was not prepared")
        tsv = ROOT / ("full-"+c["id"]+".tsv")
        require(base.h(tsv)==prepared["full_tsv_sha"],"GF2 source rows drift")
        charge=prepared["preprocessing_s"]
    require(cap-charge>0.5,"preprocessing exhausted trial budget")
    start=time.perf_counter()
    p=subprocess.run([str(binary.resolve()), mode, str(src.resolve()),
                     str(tsv.resolve()), str(cap-charge)],
                     stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=cap+15)
    elapsed=time.perf_counter()-start+charge
    require(p.returncode in (0,10,20),"bad native return "+p.stderr[-600:].decode(errors="replace"))
    stdout,native,stats,nrows,derived=base.parse_native(p.stdout,mode)
    status={"SAT":"SAT","UNSAT":"UNSAT","UNKNOWN":"TIMEOUT"}[native["status"]]
    require(p.returncode=={"SAT":10,"UNSAT":20,"TIMEOUT":0}[status],"exit native status drift")
    require(nrows==(0 if mode=="clean" else prepared["full_rows"]),"wrong GF2 rows")
    if status=="SAT":
        require(native.get("source_sat_witness_checked")=="1","native SAT witness unchecked")
        base.sat_check(src,stdout)
    require(abs(float(native["solver_s"])-(elapsed-charge))<1,"native vs host timing mismatch")
    if elapsed>cap and status != "TIMEOUT":
        status="TIMEOUT"
    result=dict(
        id=c["id"],sha256=c["sha256"],cohort=c["cohort"],
        mode=mode,method="NATIVE_"+mode.upper(),status=status,
        cap_s=cap,wall_s=round(elapsed,6),
        par2_s=round(2*cap if status=="TIMEOUT" else elapsed,6),
        charged_prep_s=charge,source_rows=nrows,
        conflicts=stats["conflicts"],decisions=stats["decisions"],
        GF2_proposals=int(native["direct_proposals"]),
        GF2_completed_reasons=int(native["reason_clauses_completed"]),
        proof="NATIVE_SAT_MODEL_CHECKED" if status=="SAT" else
              "NATIVE_UNSAT_NO_LRAT" if status=="UNSAT" else "TIMEOUT")
    return result

def run_auto(c, binary, cap, repeat):
    src=ROOT/"frozen"/(c["id"]+".cnf")
    proof=ROOT/f'proof-{c["id"]}-{repeat}.json'
    cmd=[sys.executable,"research/r166_auto_solver.py",str(src.resolve()),
         "--native",str(binary.resolve()),"--cap",str(cap),
         "--proof-out",str(proof.resolve())]
    begin=time.perf_counter()
    p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=cap+15)
    elapsed=time.perf_counter()-begin
    require(p.returncode in (0,10,20),
            "R166 auto process failed "+p.stderr[-1200:].decode(errors="replace"))
    lines=p.stdout.decode(errors="replace").splitlines()
    data=[json.loads(line[len("R166_RESULT "):])
          for line in lines if line.startswith("R166_RESULT ")]
    require(len(data)==1,"missing complete R166_RESULT json in stdout")
    d=data[0]
    require(p.returncode=={"SAT":10,"UNSAT":20,"TIMEOUT":0}[d["status"]],
            "R166 result and process code differ")
    require(d["source_sha256"]==c["sha256"],"R166 auto changed formula")
    require(d["cap_s"]==cap,"R166 cap mismatch")
    require(any(x.startswith("s ") for x in lines),"R166 SAT output missing")
    if d["status"]=="SAT":
        require("s SATISFIABLE" in lines,"R166 SAT stdout mismatch")
    if d["status"]=="UNSAT":
        require("s UNSATISFIABLE" in lines,"R166 UNSAT stdout mismatch")
    if elapsed>cap and d["status"]!="TIMEOUT":
        d["status"]="TIMEOUT"
    audited=None
    if d["method"]=="EXACT_GF2_FASTPATH":
        require(proof.is_file(),"pure path without source certificate")
        audited=independent.verify(src,json.loads(proof.read_text()))
        require(audited["status"]==d["status"] or d["status"]=="TIMEOUT",
                "source proof/status mismatch")
    else:
        require(not proof.exists(),"non-exact route emitted false XOR certificate")
        require(not d["pure_exact"],"exact source diverted to fallback")
        require(d["method"] in ("CLEAN_CDCL_FALLBACK","CLEAN_CDCL_FALLBACK_OVER_CAP",
                 "DETECTION_CAP_EXCEEDED"),"wrong native fallback mode")
    return (dict(id=c["id"],sha256=c["sha256"],cohort=c["cohort"],mode="auto",
             method=d["method"],status=d["status"],cap_s=cap,
             wall_s=round(elapsed,6),
             par2_s=round(2*cap if d["status"]=="TIMEOUT" else elapsed,6),
             proof="INDEPENDENT_XOR_CERT_VERIFIED" if audited else d["certification"],
             exact=d["pure_exact"],covered=d["covered_clauses"],
             xor_rows=d["xor_rows"],checker=audited),proof if audited else None)

def shard(index,binary):
    arr=cases()
    require(0 <= index < SHARDS, "bad shard index")
    pin=base.rd(ROOT/"build-pin.json")
    require(pin["commit"]==FROZEN_BINARY_SOURCE,"R164 binary sourced from wrong source")
    require(base.h(binary)==pin["binary_sha256"],"R164 executable SHA mismatch")
    belong=[(i,c) for i,c in enumerate(arr) if i%SHARDS==index]
    rows=[];proofs=[]
    for i,c in belong:
        cap=cap_for(c)
        prepare=base.prepare(c) if c["cohort"]=="mixed_residual" else None
        for repeat in range(REPS):
            modes=["clean","auto"]
            if c["cohort"]=="mixed_residual":
                modes.append("direct_incremental")
            random.Random("R166-SELECTOR-V1-"+c["sha256"]+str(repeat)).shuffle(modes)
            for mode in modes:
                if mode=="auto":
                    z,p=run_auto(c,binary,cap,repeat)
                    if p is not None: proofs.append(p.name)
                else:
                    z=run_native(c,mode,binary,cap,prepare)
                z["repeat"]=repeat
                rows.append(z)
                base.wr(ROOT/f"shard-{index}.json",
                        {"index":index,"pin":pin,"trials":rows,"proof_files":proofs})
                print("R166_TRIAL",json.dumps({k:v for k,v in z.items() if k!="checker"},
                                             sort_keys=True),flush=True)
    require(len([r for r in rows if r["mode"]=="auto"])==len(belong)*REPS,
            "incomplete R166 auto results")
    print("R166_SHARD_PASS",index,len(belong),len(rows),flush=True)

def audit():
    arr=cases()
    rows=[];pins=[];keys=set()
    for index in range(SHARDS):
        d=base.rd(ROOT/f"shard-{index}.json")
        require(d["index"]==index,"shard metadata mismatch")
        pins.append(d["pin"])
        for z in d["trials"]:
            c=next((c for c in arr if c["id"]==z["id"]),None)
            require(c is not None and c["sha256"]==z["sha256"],"source SHA mismatch in results")
            require(z["cap_s"]==cap_for(c),"source cap changed")
            key=(z["id"],z["repeat"],z["mode"])
            require(key not in keys,"duplicated trial")
            keys.add(key)
            require(abs(z["par2_s"]-(2*z["cap_s"] if z["status"]=="TIMEOUT"
                                   else z["wall_s"]))<0.00002,"PAR2 score invalid")
            if z["mode"]=="auto" and z["method"]=="EXACT_GF2_FASTPATH":
                path=ROOT/f'proof-{z["id"]}-{z["repeat"]}.json'
                require(path.is_file(),"missing exact source proof in final audit")
                res=independent.verify(ROOT/"frozen"/(z["id"]+".cnf"),base.rd(path))
                require(res["status"]==z["status"],"independent source proof status differs")
            rows.append(z)
    require(len({p["binary_sha256"] for p in pins})==1 and
            all(p["commit"]==FROZEN_BINARY_SOURCE for p in pins),"binary drift across shards")
    require(len(arr)==25 and len(rows)==25*REPS*2+4*REPS,
            "wrong 25-case trial count")
    pairs=[]
    for c in arr:
        for repeat in range(REPS):
            d={z["mode"]:z for z in rows if z["id"]==c["id"] and z["repeat"]==repeat}
            require("auto" in d and "clean" in d,"missing clean/auto pair")
            require(("direct_incremental" in d)==(c["cohort"]=="mixed_residual"),
                    "wrong incremental coverage")
            outputs={z["status"] for z in d.values() if z["status"]!="TIMEOUT"}
            require(len(outputs)<=1,"contradictory SAT/UNSAT outcome")
            clean,auto=d["clean"],d["auto"]
            ratio=None
            lower_bound=None
            if clean["status"]!="TIMEOUT" and auto["status"]!="TIMEOUT":
                ratio=round(clean["wall_s"]/max(auto["wall_s"],0.000001),3)
            elif clean["status"]=="TIMEOUT" and auto["status"]!="TIMEOUT":
                lower_bound=round(clean["cap_s"]/max(auto["wall_s"],0.000001),3)
            pairs.append(dict(id=c["id"],cohort=c["cohort"],repeat=repeat,
                              modes=d,fully_solved_speedup=ratio,
                              timeout_speedup_lower_bound=lower_bound))
    cohorts=sorted({c["cohort"] for c in arr})
    summary={}
    for cohort in ["all"]+cohorts:
        summary[cohort]={}
        for mode in ("clean","auto","direct_incremental"):
            selected=[z for z in rows if z["mode"]==mode and
                      (cohort=="all" or z["cohort"]==cohort)]
            if not selected: continue
            summary[cohort][mode]=dict(
                attempts=len(selected),
                solved=sum(z["status"]!="TIMEOUT" for z in selected),
                PAR2_s=round(sum(z["par2_s"] for z in selected),5),
                status_counts=dict(collections.Counter(z["status"] for z in selected)),
                source_fastpaths=sum(z["method"]=="EXACT_GF2_FASTPATH" for z in selected),
                clean_fallbacks=sum(z["method"]=="CLEAN_CDCL_FALLBACK" for z in selected))
    report=dict(status="AUDIT_PASS_RESEARCH_ONLY",not_blind=True,
                formulas=25,repetitions=2,trials=len(rows),source_run=42112755104,
                base_native_run=42145404351,
                binary_sha256=pins[0]["binary_sha256"],caps={"mixed_residual":12,"others":5},
                summary=summary,pairs=pairs,claims_policy=
                "No speedup claim when both TIMEOUT; timeout lower bounds on exact solves only",
                limitations=["Previously seen 25 R155 original CNFs; NOT blind holdout",
                 "R166 fast-path is a Python executable dispatcher, not fused native GF2",
                 "Mixed fallback always clean CaDiCaL; R164 incremental is measured separately",
                 "Fast-path UNSAT independently replays parity proof but not LRAT/FRAT",
                 "Timeout lower bound is NOT measured competition speedup",
                 "Two repeats insufficient for published speed claims"])
    base.wr(ROOT/"report.json",report)
    totals=summary["all"]
    lines=["# DRNAS R166 auto XOR / safe fallback: audited development test","",
           "25 original SHA-256 pinned CNFs, 2 repetitions, clean and auto on all,",
           "R164 direct_incremental on 4 mixed CNFs only.","",
           "| Mode | Solved | PAR2 seconds | Exact fastpaths | CDCL fallbacks |",
           "|---|---:|---:|---:|---:|"]
    for mode in ("clean","auto","direct_incremental"):
        s=totals[mode]
        lines.append(f'| {mode} | {s["solved"]}/{s["attempts"]} | {s["PAR2_s"]:.3f} | {s["source_fastpaths"]} | {s["clean_fallbacks"]} |')
    lines.extend(["","## Cohorts",""])
    for co in cohorts:
        a=summary[co]
        lines.append(f'- {co}: '+", ".join(
          f'{mode} {a[mode]["solved"]}/{a[mode]["attempts"]} PAR2={a[mode]["PAR2_s"]:.3f}s'
          for mode in a))
    lbs=[p["timeout_speedup_lower_bound"] for p in pairs
         if p["timeout_speedup_lower_bound"] is not None]
    lines.extend(["",f"Clean TIMEOUT vs exact AUTO solved pairs: {len(lbs)}.",
                  f"Timeout speedup lower bound min: {min(lbs) if lbs else 'N/A'}x.",
                  "", "RESEARCH ONLY. NOT BLIND. Exact source model/UNSAT row proof replay verified."])
    (ROOT/"summary.md").write_text("\n".join(lines)+"\n")
    print("R166_FINAL",json.dumps({"status":report["status"],
      "formulas":25,"trials":len(rows),"summary":totals,
      "timeout_lower_bound_min":min(lbs) if lbs else None},sort_keys=True),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("shard","audit"))
    p.add_argument("--shard",type=int,default=0)
    p.add_argument("--binary",default="r166/r164-native")
    args=p.parse_args()
    if args.action=="shard":
        shard(args.shard,pathlib.Path(args.binary))
    else:
        audit()
