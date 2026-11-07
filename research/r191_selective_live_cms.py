#!/usr/bin/env python3
"""R191: source-locked mixed XOR/CDCL live-feedback causal gate vs CryptoMiniSat.

Evidence protocol: R190 original frozen 25 known external +13 generated controls,
source SHA verification, two repeats and 8 arms, 12s end-to-end cap.
R191 selective policy is precommitted on source features only, no per-ID outcomes.
All SAT witnesses independently checked on original source CNF. CDCL UNSAT
without certified GF2 source contradiction is NOT independently LRAT verified.
"""
from __future__ import annotations
import argparse
import collections
import hashlib
import json
import pathlib
import random
import re
import statistics
import subprocess
import time

import r188_feedback_benchmark as r188
import r190_cms_mixed_benchmark as r190

ROOT=pathlib.Path("r191")
SOURCE=pathlib.Path("r189/frozen")
PROTO="DRNAS-R191-FROZEN-38-ADAPTIVE-LIVE-8ARM-v1"
CAP=12.0
REPS=2
SHARDS=12
MODES=(
  "cadical_clean", "r28_exact_router", "drnas_selective_gate",
  "drnas_live_short8", "drnas_live_shadow8", "drnas_r191_coupling",
  "cms_default", "cms_gauss_forced",
)
BINARIES={
 "cadical_clean":pathlib.Path("r189/r189-driver"),
 "r28_exact_router":pathlib.Path("r190_cms_mixed/r28"),
 "kissat404":pathlib.Path("built/bin/kissat_4_0_4"),
 "live":pathlib.Path("r188/r188-live"),
 "cms":pathlib.Path("/usr/bin/cryptominisat5"),
}
SOURCE_SHA=r190.SOURCE_MANIFEST_SHA

def need(ok,msg):
    if not ok:raise RuntimeError("R191_FAIL_CLOSED "+msg)

def sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()

def save(path,obj):
    path=pathlib.Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,sort_keys=True,indent=2)+"\n")

def verify_sources():
    need(sha(SOURCE/"manifest.json")==SOURCE_SHA,"38 original source manifest drift")
    need(sha("r189/r189-driver")==r190.R189_DRIVER_SHA,"CaDiCaL binary drift")
    m=json.loads((SOURCE/"manifest.json").read_text())
    cases=m["cases"]
    need(len(cases)==38 and sum(x["real"] for x in cases)==25,"source counts wrong")
    need(len({x["sha256"] for x in cases})==38,"duplicate source sha")
    for c in cases:
        need(sha(SOURCE/(c["id"]+".cnf"))==c["sha256"],"source file drift")
    for k,p in BINARIES.items():
        need(p.is_file(),"required binary missing: "+k+" "+str(p))
    pins=json.loads((ROOT/"pins.json").read_text())
    for p,h in pins.items():
        need(sha(p)==h,"binary pin mismatch: "+p)
    return cases

def coupling_signal(clauses,covered,rows):
    """Source-only structural decision, not trained/tuned on benchmark outcomes.

    Boundary = number of XOR variables that occur in residual CNF clauses.
    Residual contact = count of ORIGINAL residual clauses touching XOR vars.
    High coupling is hypothesis of useful live feedback, not guaranteed benefit.
    """
    xor_vars=set(v for vs,_,_ in rows for v in vs)
    residual=[c for i,c in enumerate(clauses) if i not in covered]
    touched=[c for c in residual if any(abs(l) in xor_vars for l in c)]
    shared={abs(l) for c in touched for l in c if abs(l) in xor_vars}
    score={
        "xor_rows":len(rows),
        "xor_vars":len(xor_vars),
        "residual_clauses":len(residual),
        "contact_clauses":len(touched),
        "shared_boundary_vars":len(shared),
        "contact_fraction":round(len(touched)/max(1,len(residual)),4),
    }
    score["live_eligible"]=(
        len(rows)>=2 and 8<=len(shared)
        and len(touched)>=24 and len(residual)>=24
        and 4*len(shared)>=len(xor_vars)
    )
    return score

def read_output(output,kind,rc):
    if kind=="cadical_clean":
        m=re.search(r"^R182_STATUS status=(SAT|UNSAT|TIMEOUT)\b",output,re.M)
    elif kind=="live":
        m=re.search(r"^R166X_RESULT mode=\w+ status=(SAT|UNSAT|UNKNOWN)\b",output,re.M)
    else:
        m=re.search(r"^s\s+(UNSATISFIABLE|SATISFIABLE)\b",output,re.M)
    need(m is not None,"missing solver status; tail: "+output[-400:])
    status={"SATISFIABLE":"SAT","UNSATISFIABLE":"UNSAT","UNKNOWN":"TIMEOUT"}.get(m.group(1),m.group(1))
    if kind=="cadical_clean":need(rc==0,"unexpected driver return "+str(rc))
    else:need(rc in (0,10,20),"unexpected solver return "+str(rc))
    model={}
    if status=="SAT":
        for line in output.splitlines():
            if line.startswith("v "):
                for lit in map(int,line[2:].split()):
                    if not lit:continue
                    need(abs(lit) not in model or model[abs(lit)]==(lit>0),
                         "SAT model inconsistent assignment")
                    model[abs(lit)]=lit>0
        need(model,"SAT model missing")
    return status,model

def run_binary(case,mode,cmd,started,kind,rep):
    left=CAP-(time.perf_counter()-started)
    if left<=0.075:return "TIMEOUT",{},{"proof":"CAP"}
    try:
        p=subprocess.run(cmd,capture_output=True,timeout=left,
                         check=False)
    except subprocess.TimeoutExpired:
        return "TIMEOUT",{},{"proof":"CAP"}
    output=p.stdout.decode(errors="replace")+"\n"+p.stderr.decode(errors="replace")
    rawpath=ROOT/"raw"/f"shard-{int(case['_shard'])}"/f"{case['id']}-{mode}-{rep}.log"
    rawpath.parent.mkdir(parents=True,exist_ok=True)
    rawpath.write_text(output[-90000:])
    status,model=read_output(output,kind,p.returncode)
    stats=r188.stats(output) if kind=="live" else {}
    tel=r188.telemetry(output) if kind=="live" else {}
    return status,model,{"exit_code":p.returncode,"proof":"NO_INDEPENDENT_UNSAT_LRAT",
                         "bridge":tel,"solver_stats":stats}

def run_case(case,mode,rep,shard):
    source=SOURCE/(case["id"]+".cnf")
    need(sha(source)==case["sha256"],"original CNF drift")
    started=time.perf_counter()
    info={"selected":False,"decision":"direct","structural":{},
          "live_invoked":False,"injected_units":0,"source_gf2_proof":False,
          "proof":"NO_INDEPENDENT_UNSAT_LRAT"}
    path=source
    status=None;model={};g_source=None

    if mode in ("drnas_selective_gate","drnas_live_short8","drnas_live_shadow8","drnas_r191_coupling"):
        enable,reason,select_time=r188.route(source)
        info.update(selected=bool(enable),selector_reason=reason,
                    selector_s=round(select_time,6))
        if enable:
            n,clauses=r188.gf.dimacs(source)
            rows,covered=r188.ext.xor_source(clauses)
            info["source_rows"]=len(rows)
            gauss=r188.gf.gaussian(rows)
            if gauss["conflict"]:
                r188.gf.check_trace(rows,0,1,gauss["conflict_trace"])
                status="UNSAT"
                info.update(source_gf2_proof=True,proof="SOURCE_GF2_CONTRADICTION_REPLAYED",
                            decision="certified_unsat")
            else:
                if mode=="drnas_r191_coupling":
                    features=coupling_signal(clauses,covered,rows)
                    info["structural"]=features
                    active=bool(features["live_eligible"])
                    info["decision"]="live_short8" if active else "gate_units"
                else:
                    active=mode in ("drnas_live_short8","drnas_live_shadow8")
                    info["decision"]="live_short8" if active else "gate_units"
                if active and rows and time.perf_counter()-started<CAP-1.0:
                    tsv=ROOT/"derived"/mode/f"{case['id']}-{rep}.tsv"
                    fed=r188.save_rows(tsv,rows,clauses)
                    info["source_rows_exported"]=fed
                    if fed:
                        backend=("direct_full_feedback_shadow8" if mode=="drnas_live_shadow8"
                                 else "direct_full_feedback_budget8")
                        info["live_invoked"]=True
                        status,model,details=run_binary(
                            dict(case,**{"_shard":shard}),mode,
                            [str(BINARIES["live"].resolve()),backend,str(source.resolve()),
                             str(tsv.resolve()),str(max(0.01,CAP-(time.perf_counter()-started)))],
                            started,"live",rep)
                        info.update(details)
                if status is None and gauss["units"]:
                    dest=ROOT/"derived"/mode/f"{case['id']}-{rep}.cnf"
                    info["injected_units"]=r188.write_units(dest,n,clauses,gauss,rows)
                    path=dest

    if status is None:
        left=CAP-(time.perf_counter()-started)
        if left<=0.075:
            status="TIMEOUT"
        else:
            if mode=="r28_exact_router":
                cmd=[str(BINARIES["r28_exact_router"].resolve()),str(source.resolve()),
                     str(BINARIES["kissat404"].resolve())]
                kind="ordinary"
            elif mode in ("cms_default","cms_gauss_forced"):
                cmd=[str(BINARIES["cms"]), "--threads=1"]
                if mode=="cms_gauss_forced":
                    cmd.extend(("--maxnummatrices=5","--autodisablegauss=0"))
                cmd.append(str(source.resolve()))
                kind="ordinary"
            else:
                cmd=[str(BINARIES["cadical_clean"].resolve()),str(path.resolve()),str(left)]
                kind="cadical_clean"
            status,model,details=run_binary(dict(case,**{"_shard":shard}),mode,cmd,
                                            started,kind,rep)
            info.update(details)

    elapsed=time.perf_counter()-started
    if elapsed>=CAP:
        status="TIMEOUT"
        info["proof"]="CAP"
    if status=="SAT":
        _,original=r188.gf.dimacs(source)
        r188.gf.sat_check(original,model)
        info["proof"]="SAT_WITNESS_ORIGINAL_CNF_VERIFIED"
    need(status in ("SAT","UNSAT","TIMEOUT"),"unexpected result "+str(status))
    if case["expected"]!="UNKNOWN" and status!="TIMEOUT":
        need(status==case["expected"],"disagreement with calibrated source truth")
    rec={
        "id":case["id"],"sha256":case["sha256"],"real":case["real"],
        "family":case["family"],"suite":case["suite"],
        "rep":rep,"mode":mode,"status":status,
        "elapsed_s":round(min(CAP,elapsed),6),
        "par2_s":round(2*CAP if status=="TIMEOUT" else min(CAP,elapsed),6),
        **info,
    }
    return rec

def shard(idx):
    cases=verify_sources()
    need(0<=idx<SHARDS,"bad shard")
    records=[]
    for c in cases[idx::SHARDS]:
        for rep in range(REPS):
            modes=list(MODES)
            random.Random(PROTO+c["sha256"]+str(rep)).shuffle(modes)
            for mode in modes:
                x=run_case(c,mode,rep,idx)
                records.append(x)
                save(ROOT/f"shard-{idx}.json",records)
                print("R191_TRIAL",json.dumps({k:x.get(k) for k in (
                    "id","family","mode","rep","status","elapsed_s",
                    "selected","decision","source_rows","live_invoked","bridge",
                )},sort_keys=True),flush=True)
    need(len(records)==len(cases[idx::SHARDS])*REPS*len(MODES),"partial shard")
    print("R191_SHARD_PASS",idx,len(records),flush=True)

def audit():
    cases=verify_sources()
    records=[]
    seen=set()
    for i in range(SHARDS):
        p=ROOT/f"shard-{i}.json"
        need(p.is_file(),"missing shard "+str(i))
        raw=json.loads(p.read_text())
        need(len(raw)==len(cases[i::SHARDS])*REPS*len(MODES),"shard record count mismatch")
        for rec in raw:
            k=(rec["sha256"],rec["rep"],rec["mode"])
            need(k not in seen,"duplicate source/rep/mode")
            seen.add(k)
            need(rec["status"] in ("SAT","UNSAT","TIMEOUT"),"unexpected solver result")
            need(abs(rec["par2_s"]-(2*CAP if rec["status"]=="TIMEOUT"
                                    else rec["elapsed_s"]))<.00001,"PAR2 drift")
            records.append(rec)
    need(len(records)==38*REPS*len(MODES)==608,"incomplete 608 paired")
    for c in cases:
        for rep in range(REPS):
            subset=[x for x in records if x["sha256"]==c["sha256"] and x["rep"]==rep]
            need({x["mode"] for x in subset}==set(MODES),"missing arms on pair")
            answers={x["status"] for x in subset if x["status"]!="TIMEOUT"}
            need(len(answers)<=1,"SAT/UNSAT contradictory outputs")
    groups={
        "all":cases,
        "external_original_25":[x for x in cases if x["real"]],
        "synthetic_reference_13":[x for x in cases if not x["real"]],
    }
    for fam in sorted({x["family"] for x in cases if x["real"]}):
        groups["external:"+fam]=[x for x in cases if x["real"] and x["family"]==fam]
    summary={}
    for group,cohort in groups.items():
        sha_set={x["sha256"] for x in cohort}
        modes={}
        for mode in MODES:
            rr=[x for x in records if x["sha256"] in sha_set and x["mode"]==mode]
            modes[mode]={
                "attempts":len(rr),
                "solved":sum(x["status"]!="TIMEOUT" for x in rr),
                "sat":sum(x["status"]=="SAT" for x in rr),
                "unsat":sum(x["status"]=="UNSAT" for x in rr),
                "timeouts":sum(x["status"]=="TIMEOUT" for x in rr),
                "par2_s":round(sum(x["par2_s"] for x in rr),6),
                "live_invoked":sum(bool(x.get("live_invoked")) for x in rr),
                "source_gf2_proofs":sum(bool(x.get("source_gf2_proof")) for x in rr),
                "feedback_exported":sum((x.get("bridge") or {}).get("feedback_clauses_consumed",0) for x in rr),
                "feedback_candidates":sum((x.get("bridge") or {}).get("feedback_candidates",0) for x in rr),
                "propagate_calls":sum((x.get("bridge") or {}).get("propagate_calls",0) for x in rr),
                "coupling_gate_active":sum(x.get("decision")=="live_short8" for x in rr),
            }
        summary[group]={"formulas":len(cohort),"modes":modes}
    report={
        "protocol":PROTO,"status":"R191_AUDIT_PASS",
        "frozen_original_sha":SOURCE_SHA,
        "known_source_benchmark_not_blind":True,
        "source_only_gate_precommitted":True,
        "attempts":len(records),"repetitions":REPS,"wall_cap_s":CAP,
        "original_SAT_models_checked":True,
        "independent_UNSAT_LRAT":False,
        "causal_comparison":"direct_full_feedback_budget8 vs direct_full_feedback_shadow8",
        "groups":summary,
    }
    save(ROOT/"report.json",report)
    save(ROOT/"all-trials.json",records)
    with (ROOT/"summary.md").open("w") as f:
        f.write("# DRNAS R191: source-adaptive live XOR/CDCL vs CryptoMiniSat\n\n")
        f.write("38 reused R189/R190 sources, NOT blind: 25 external originals, 13 synthetic controls. "
                "12s end-to-end wall cap, two randomized paired repetitions per formula, "
                "8 arms (608 trials), all SHA-checked. SAT models checked against original CNF. "
                "CDCL UNSAT without GF2 proof lacks independent LRAT.\n\n")
        f.write("| Cohort | Solver | Solved | PAR-2 s | Live calls | Consumed feedback |\n")
        f.write("|---|---|---:|---:|---:|---:|\n")
        for group in ("external_original_25","synthetic_reference_13","all"):
            for mode,v in summary[group]["modes"].items():
                f.write(f"| {group} | {mode} | {v['solved']}/{v['attempts']} "
                        f"| {v['par2_s']} | {v['live_invoked']} | {v['feedback_exported']} |\n")
        f.write("\nDo not promote R191 on these reused/development cases alone.\n")
    print("R191_FINAL",json.dumps({
        k:summary[k] for k in ("external_original_25","synthetic_reference_13","all")
    },sort_keys=True),flush=True)

def selftest():
    # None of these hand-checked signals depend on benchmark outcomes.
    a=[(1,2,3),(2,3,4)]
    rows=[(t,0,0) for t in a]
    assert not coupling_signal([[1,4]]*4,set(),rows)["live_eligible"]
    rows=[(tuple(range(1,11)),0,0),(tuple(range(1,11)),1,0)]
    cl=[[i,11] for i in range(1,11)]*3
    assert coupling_signal(cl,set(),rows)["live_eligible"]
    assert not coupling_signal(cl,set(range(len(cl))),rows)["live_eligible"]
    verify_sources()
    print("R191_SELFTEST_PASS",flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=["selftest","shard","audit"])
    p.add_argument("--shard",type=int,default=0)
    args=p.parse_args()
    if args.action=="selftest":selftest()
    elif args.action=="shard":shard(args.shard)
    else:audit()
