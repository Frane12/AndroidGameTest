#!/usr/bin/env python3
"""DRNAS R190: original-CNF mixed-formula 9-arm comparison incl CryptoMiniSat.
Known historical R189 25 external + 13 synthetic controls, NOT blind.
Original source SHA-frozen before all modes. SAT witnesses checked on original.
R189 bridge evidence is proof-traced; external/CDCL UNSAT not LRAT verified.
Each attempt is capped inclusive of preprocessing; paired within source/rep/shard.
"""
from __future__ import annotations
import argparse, collections, csv, hashlib, json, pathlib, random, re
import statistics, subprocess, sys, time

import r189_short_inference as r189
import r188_feedback_benchmark as old

ROOT=pathlib.Path("r190_cms_mixed")
FROZEN=pathlib.Path("r189/frozen")
CAP=8.0
REPS=2
SHARDS=12
PROTO="DRNAS-R190-CMS-NATIVE-MIXED-38-9ARM-v1"
SOURCE_MANIFEST_SHA="3f0f67bea5547daa1ba07d9a1dba31d8d33f7d734db8eb6e8cae358a46c91ef3"
R189_DRIVER_SHA="f4ea8de92f8e1919c818bb85cc9863524ab440b138fde740a29795a666b9f405"
R189_MODES={
    "drnas_selective":"selective_gate",
    "drnas_hybrid4":"hybrid4",
    "drnas_shadow":"hybrid_shadow",
}
MODES=(
    "cadical21_clean",
    "kissat404_clean",
    "cms511_default",
    "cms511_gauss_forced",
    "cms511_gauss_off",
    "drnas_r28_router",
    "drnas_selective",
    "drnas_hybrid4",
    "drnas_shadow",
)
BINARIES={
    "cadical21_clean":pathlib.Path("r189/r189-driver"),
    "kissat404_clean":pathlib.Path("built/bin/kissat_4_0_4"),
    "cms511_default":pathlib.Path("/usr/bin/cryptominisat5"),
    "cms511_gauss_forced":pathlib.Path("/usr/bin/cryptominisat5"),
    "cms511_gauss_off":pathlib.Path("/usr/bin/cryptominisat5"),
    "drnas_r28_router":pathlib.Path("r190_cms_mixed/r28"),
}

def need(value,message):
    if not value: raise RuntimeError("R190_FAIL_CLOSED "+message)

def sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()

def save(path,x):
    p=pathlib.Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(x,sort_keys=True,indent=2)+"\n")

def frozen_cases():
    need(sha(FROZEN/"manifest.json")==SOURCE_MANIFEST_SHA,"R189 frozen manifest mismatch")
    m=json.loads((FROZEN/"manifest.json").read_text())
    cases=m["cases"]
    need(len(cases)==38 and len({c["sha256"] for c in cases})==38,
         "expected 38 unique sources")
    need(sum(c["real"] for c in cases)==25 and sum(not c["real"] for c in cases)==13,
         "cohort count mismatch")
    for c in cases:
        need(sha(FROZEN/(c["id"]+".cnf"))==c["sha256"],"CNF SHA drift")
    need(sha("r189/r189-driver")==R189_DRIVER_SHA,"frozen CaDiCaL driver drift")
    for name,p in BINARIES.items():
        need(p.is_file(),"solver missing: "+name+" "+str(p))
    return cases

def raw_command(mode,src):
    if mode=="cadical21_clean":
        return [str(BINARIES[mode].resolve()),str(src),str(CAP)]
    if mode=="kissat404_clean":
        return [str(BINARIES[mode].resolve()),str(src)]
    if mode=="cms511_default":
        return [str(BINARIES[mode]),"--threads=1",str(src)]
    if mode=="cms511_gauss_forced":
        return [str(BINARIES[mode]),"--threads=1",
               "--maxnummatrices=5","--autodisablegauss=0",str(src)]
    if mode=="cms511_gauss_off":
        return [str(BINARIES[mode]),"--threads=1","--maxnummatrices=0",str(src)]
    if mode=="drnas_r28_router":
        return [str(BINARIES[mode].resolve()),str(src),str(BINARIES["kissat404_clean"].resolve())]
    raise ValueError(mode)

def parse_status_and_model(raw,mode):
    if mode=="cadical21_clean":
        status_found=re.search(r"^R182_STATUS status=(SAT|UNSAT|TIMEOUT)\b",raw,re.M)
        status=status_found.group(1) if status_found else "ERROR"
    else:
        if re.search(r"^s\s+UNSATISFIABLE\b",raw,re.M):status="UNSAT"
        elif re.search(r"^s\s+SATISFIABLE\b",raw,re.M):status="SAT"
        else:status="ERROR"
    model={}
    if status=="SAT":
        for line in raw.splitlines():
            if line.startswith("v "):
                for v in map(int,line[2:].split()):
                    if not v:continue
                    need(abs(v) not in model or model[abs(v)]==(v>0),"duplicate disagreeing model literals")
                    model[abs(v)]=v>0
        need(bool(model),"SAT without witness")
    return status,model

def original_model_ok(case,model):
    source=FROZEN/(case["id"]+".cnf")
    _,clauses=old.gf.dimacs(source)
    old.gf.sat_check(clauses,model)

def runner(case,mode,rep):
    source=FROZEN/(case["id"]+".cnf")
    need(sha(source)==case["sha256"],"source SHA drift during run")
    start=time.perf_counter()
    if mode in R189_MODES:
        r189.CAP=CAP
        r=r189.trial(case,R189_MODES[mode],rep,BINARIES["cadical21_clean"])
        # R189 trial already verifies SAT witness on source CNF and traces GF2 parents.
        status=r["status"]
        elapsed=float(r["elapsed_s"])
        details={k:r.get(k) for k in
                 ("proof","selected","route","xor_rows","units",
                  "injected_clauses","preprocessing_s","short_clauses","bridge_resolutions",
                  "conflicts","decisions","propagations")}
        need(status in ("SAT","UNSAT","TIMEOUT"),"R189 unknown status")
        if status=="SAT":
            need(r["proof"]=="SAT_WITNESS_ORIGINAL_CNF_VERIFIED","R189 model unchecked")
        if status=="UNSAT":
            details["independent_unsat_lrat"]=False
    else:
        cmd=raw_command(mode,source)
        try:
            p=subprocess.run(cmd,capture_output=True,text=True,
                             timeout=CAP,check=False,errors="replace")
            elapsed=time.perf_counter()-start
            output=p.stdout+"\n"+p.stderr
            status,model=parse_status_and_model(output,mode)
            if status=="SAT":
                original_model_ok(case,model)
            if status=="SAT":
                need(p.returncode in (0,10),"invalid SAT exit code "+str(p.returncode))
            if status=="UNSAT":
                need(p.returncode in (0,20),"invalid UNSAT exit code "+str(p.returncode))
            details={"exit_code":p.returncode,"model_literals":len(model),
                     "proof":("SAT_WITNESS_ORIGINAL_CNF_VERIFIED" if status=="SAT"
                               else "NO_INDEPENDENT_UNSAT_LRAT")}
            if mode=="drnas_r28_router":
                m=re.search(r"^c R28_ROUTE ([^\n]+)",output,re.M)
                details["r28_route"]=m.group(1) if m else None
            log=ROOT/"logs"/("shard-"+str(rep)) / (case["id"]+"-"+mode+".log")
            log.parent.mkdir(parents=True,exist_ok=True)
            log.write_text(output[-80000:])
        except subprocess.TimeoutExpired:
            elapsed=CAP;status="TIMEOUT"
            details={"proof":"CAP_TIMEOUT"}
        if elapsed>=CAP:
            status="TIMEOUT";elapsed=CAP
    if case["expected"]!="UNKNOWN" and status not in ("TIMEOUT","ERROR"):
        need(status==case["expected"],"SAT/UNSAT source truth disagreement")
    rec={
        "id":case["id"],"sha256":case["sha256"],"family":case["family"],
        "suite":case["suite"],"real":case["real"],"mode":mode,"rep":rep,
        "status":status,"elapsed_s":round(min(CAP,elapsed),6),
        "par2_s":round(2*CAP if status in ("TIMEOUT","ERROR")
                         else min(CAP,elapsed),6),
        **details,
    }
    return rec

def shard(idx):
    cases=frozen_cases()
    need(0<=idx<SHARDS,"invalid shard")
    rows=[]
    for c in cases[idx::SHARDS]:
        for rep in range(REPS):
            methods=list(MODES)
            random.Random(PROTO+c["sha256"]+str(rep)).shuffle(methods)
            for mode in methods:
                rec=runner(c,mode,rep)
                rows.append(rec)
                save(ROOT/f"shard-{idx}.json",rows)
                print("R190_TRIAL",json.dumps({k:rec.get(k) for k in (
                    "id","family","mode","rep","status","elapsed_s",
                    "xor_rows","injected_clauses","preprocessing_s","r28_route"
                )},sort_keys=True),flush=True)
    need(len(rows)==len(cases[idx::SHARDS])*REPS*len(MODES),"missing paired trials")
    print("R190_SHARD_PASS",idx,len(rows),flush=True)

def audit():
    cases=frozen_cases(); rows=[];seen=set(); lookup={c["sha256"]:c for c in cases}
    for idx in range(SHARDS):
        p=ROOT/f"shard-{idx}.json"
        need(p.is_file(),"missing shard "+str(idx))
        shard_rows=json.loads(p.read_text())
        need(len(shard_rows)==len(cases[idx::SHARDS])*REPS*len(MODES),
             "shard count mismatch")
        for r in shard_rows:
            key=(r["sha256"],r["rep"],r["mode"])
            need(key not in seen,"duplicate trial");seen.add(key)
            need(r["sha256"] in lookup,"unknown source")
            need(r["id"]==lookup[r["sha256"]]["id"],"mismatched id")
            need(r["status"] in ("SAT","UNSAT","TIMEOUT"),"unexpected failure")
            need(abs(r["par2_s"]-(2*CAP if r["status"]=="TIMEOUT" else r["elapsed_s"]))<0.00002,
                 "PAR2 drift")
            rows.append(r)
    need(len(rows)==38*REPS*len(MODES)==684,"missing 9-arm trials")
    for c in cases:
        for rep in range(REPS):
            a=[r for r in rows if r["sha256"]==c["sha256"] and r["rep"]==rep]
            need({r["mode"] for r in a}==set(MODES),"missing source pairs")
            answers={r["status"] for r in a if r["status"]!="TIMEOUT"}
            need(len(answers)<=1,"SAT/UNSAT disagreement")
    groups={
        "all":cases,
        "external_original_25":[c for c in cases if c["real"]],
        "synthetic_reference_controls_13":[c for c in cases if not c["real"]],
    }
    for fam in sorted({c["family"] for c in cases if c["real"]}):
        groups["external:"+fam]=[c for c in cases if c["real"] and c["family"]==fam]
    summary={}
    for cohort,subset in groups.items():
        d={}
        allowed={c["sha256"] for c in subset}
        for mode in MODES:
            rr=[r for r in rows if r["sha256"] in allowed and r["mode"]==mode]
            d[mode]={"attempts":len(rr),
                      "solved":sum(r["status"] in ("SAT","UNSAT") for r in rr),
                      "sat":sum(r["status"]=="SAT" for r in rr),
                      "unsat":sum(r["status"]=="UNSAT" for r in rr),
                      "timeouts":sum(r["status"]=="TIMEOUT" for r in rr),
                      "par2_s":round(sum(r["par2_s"] for r in rr),6),
                      "total_elapsed_s":round(sum(r["elapsed_s"] for r in rr),6),
                      "median_s_solved":round(statistics.median(
                          r["elapsed_s"] for r in rr if r["status"]!="TIMEOUT"),6)
                          if any(r["status"]!="TIMEOUT" for r in rr) else None,
                      "preproc_s":round(sum(float(r.get("preprocessing_s") or 0) for r in rr),6)}
        base=d["cadical21_clean"]["par2_s"]
        summary[cohort]={"formulas":len(subset),"modes":d,
                         "cadical_par2_over_mode":{m:round(base/d[m]["par2_s"],5)
                                                       for m in MODES}}
    report={
        "protocol":PROTO,"status":"R190_AUDIT_PASS",
        "source_sha256":SOURCE_MANIFEST_SHA,
        "known_sources_not_blind":True,
        "real_originals_reused":25,"synthetic_controls_reused":13,
        "attempts":684,"repetitions":REPS,"cap_s":CAP,
        "SAT_models_checked_original":True,
        "CDCL_UNSAT_independent_LRAT_verified":False,
        "paired_same_original_SHA":True,
        "relative_speed_compare_within_shard_not_across_runners":True,
        "groups":summary,
    }
    save(ROOT/"report.json",report)
    save(ROOT/"all_trials.json",rows)
    with (ROOT/"summary.md").open("w") as f:
        f.write("# R190 — mixed original-CNF DRNAS vs CryptoMiniSat 9-arm 684 paired\n\n")
        f.write("**Developer/reused suite, NOT a new blind test.** Original 25 GBD external "
                "+ 13 generated controls, unchanged original SHA; two repetitions, "
                "8s end-to-end cap; 12 Linux runner shards. Original SAT witnesses checked. "
                "No independent UNSAT LRAT except R189 source GF2 trace. "
                "Different runner CPUs may cause time differences across shards.\n\n")
        f.write("| Cohort | Mode | Solved | PAR-2 s | CaDiCaL PAR-2 / mode | Timeouts |\n")
        f.write("|---|---|---:|---:|---:|---:|\n")
        for cohort in ("external_original_25","synthetic_reference_controls_13","all"):
            for mode,v in summary[cohort]["modes"].items():
                f.write(f"| {cohort} | {mode} | {v['solved']}/{v['attempts']} | "
                        f"{v['par2_s']} | {summary[cohort]['cadical_par2_over_mode'][mode]} | "
                        f"{v['timeouts']} |\n")
        f.write("\nNo promotion based on this already-exposed cohort alone.\n")
    print("R190_FINAL",json.dumps({k:summary[k] for k in
       ("external_original_25","synthetic_reference_controls_13","all")},
       sort_keys=True),flush=True)

def smoke():
    frozen_cases()
    r189.selftest()
    print("R190_SMOKE_PASS",flush=True)

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("action",choices=["smoke","shard","audit"])
    parser.add_argument("--shard",type=int,default=0)
    args=parser.parse_args()
    if args.action=="smoke":smoke()
    elif args.action=="shard":shard(args.shard)
    else:audit()
