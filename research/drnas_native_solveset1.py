#!/usr/bin/env python3
"""DRNAS Native SOLVESET1: qualify original source-SHA DIMACS with ONLY
our own standalone C++ CDCL (R3C plain), then freeze a *development*
benchmark cohort before any timed R1/R2B/R3C comparisons.

Screens previously frozen MIXAB4 easy6, MIXAB3 prospective12,
EQUIV10M5 reference easy/medium5. No third-party solver calls, period.
Results selected by our R3C solver ARE NOT blind; report screening bias.
"""
from __future__ import annotations
import argparse, collections, hashlib, json, os, pathlib, random, re, subprocess, time
import drnas_native_core_r2_test as independent

ROOT=pathlib.Path("mre_drnas_native_solveset1")
COHORTS=(
    ("MIXAB4_ref_easy6",pathlib.Path("mre_mixab4/manifest.json"),pathlib.Path("mre_mixab4/cases"),"original_cases",6),
    ("MIXAB3_source12",pathlib.Path("mre_mixab3/manifest.json"),pathlib.Path("mre_mixab3/cases"),"original_cases",12),
    ("EQUIV10M5_ref_easy_medium5",pathlib.Path("mre_equiv10m5/manifest.json"),pathlib.Path("mre_equiv9/cases"),"cases",5),
)
BINARIES={
    "r1":ROOT/"bin/drnas_native_core_r1",
    "r2b_gf2":ROOT/"bin/drnas_native_core_r2b",
    "r3c_plain":ROOT/"bin/drnas_native_core_r3c",
    "r3c_gf2":ROOT/"bin/drnas_native_core_r3c",
}
PREFIX={
    "r1":"DRNAS_NATIVE_R1_RESULT",
    "r2b_gf2":"DRNAS_NATIVE_R2B_RESULT",
    "r3c_plain":"DRNAS_NATIVE_R3C_RESULT",
    "r3c_gf2":"DRNAS_NATIVE_R3C_RESULT",
}
SOURCE_CAP=4.0
BENCH_CAP=5.0
REPS=2
MAX_SELECT=10
PROTO="DRNAS-NATIVE-SOLVESET1-23SHA-R3CPLAIN-SCREEN-4ARMS-2REPS-5S-ONECPU-v1"
def need(ok,msg):
    if not ok:raise RuntimeError("DRNAS_SOLVESET1_FAIL_CLOSED "+str(msg))
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def save(p,obj):
    p=pathlib.Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(obj,indent=2,sort_keys=True)+"\n")
def load(p):return json.loads(pathlib.Path(p).read_text())
def catalogue():
    rows=[]
    for cohort,manifest,folder,key,expected in COHORTS:
        need(manifest.is_file(),"missing original manifest "+str(manifest))
        m=load(manifest)
        cs=m[key]
        need(len(cs)==expected,"original source roster drift "+cohort)
        for c in cs:
            path=folder/c["filename"]
            need(path.is_file(),"missing original SHA input "+str(path))
            need(sha(path)==c["sha256"],"original CNF SHA mismatched "+cohort)
            n,clauses=independent.parse_dimacs(path)
            need(n>=0 and len(clauses)>0,"unexpected empty original CNF roster input")
            rows.append(dict(cohort=cohort,sha256=c["sha256"],
                             filename=c["filename"],original_path=str(path),
                             vars=n,clauses=len(clauses),
                             source_manifest_sha256=sha(manifest),
                             reference_band=c.get("reference_band"),
                             year=c.get("year")))
    need(len(rows)==23 and len({r["sha256"] for r in rows})==23,
         "expected 23 disjoint original SHA")
    rows.sort(key=lambda x:(x["cohort"],x["sha256"]))
    return rows
def run_original(src,arm,cap):
    need(arm in BINARIES,"unknown OWN source-built SAT executable")
    logical=min(os.sched_getaffinity(0))
    os.sched_setaffinity(0,{logical})
    cmd=([str(BINARIES[arm].resolve()),str(src.resolve()),"--time",str(cap)]
         if arm=="r1" else
         [str(BINARIES[arm].resolve()),str(src.resolve()),"--mode",
          "plain" if arm=="r3c_plain" else "gf2","--time",str(cap)])
    begin=time.perf_counter()
    proc=subprocess.run(cmd,capture_output=True,text=True,timeout=cap+1.5)
    e2e=time.perf_counter()-begin
    need(proc.returncode in (0,10,20),
         "our native CDCL failed "+arm+" exit="+str(proc.returncode)+" "+proc.stderr[-500:])
    line=re.search(r"^c "+PREFIX[arm]+r" (.*)$",proc.stdout,re.M)
    need(line is not None,"missing native CDCL metrics "+arm)
    kv=dict(token.split("=",1) for token in line.group(1).split() if "=" in token)
    status=kv["status"]
    need(proc.returncode=={"SAT":10,"UNSAT":20,"UNKNOWN":0}[status],
         "exit and native SAT status disagree")
    need(kv.get("third_party_solver_calls")=="0","external SAT solver was invoked")
    n,clauses=independent.parse_dimacs(src)
    verified=False
    if status=="SAT":
        values={}
        for line in proc.stdout.splitlines():
            if line.startswith("v "):
                for lit in map(int,line[2:].split()):
                    if lit:
                        v=abs(lit)
                        need(v not in values,"duplicate variable in SAT certificate")
                        values[v]=lit>0
        need(len(values)==n and independent.satisfied(clauses,values),
             "SAT model did not satisfy full ORIGINAL CNF")
        verified=True
    need(e2e<=cap+1.0,"exceeded E2E process cap")
    return dict(arm=arm,status=status,model_original_verified=verified,
                original_UNSAT_independent_LRAT=False,
                solver_s=float(kv["solver_s"]),
                wall_E2E_s=round(e2e,6),cpu=logical,
                decisions=int(kv.get("decisions",0)),
                conflicts=int(kv.get("conflicts",0)),
                xor_derived_implications=int(kv.get("xor_derived_implications",0)),
                xor_reasons=int(kv.get("xor_reasons",0)),
                xor_checks=int(kv.get("xor_checks",0)),
                native_heap_pops=int(kv.get("heap_pops",0)),
                external_solver_calls=0)
def verify_prereq():
    for arm,path in BINARIES.items():
        need(path.is_file(),f"missing original source-built binary {arm}: {path}")
    return {arm:sha(path) for arm,path in BINARIES.items()}
def screen():
    ROOT.mkdir(parents=True,exist_ok=True)
    binary_sha=verify_prereq()
    roster=catalogue()
    # Write the source-frozen all-23 roster before running ANY candidate.
    save(ROOT/"source-23-sha.json",dict(protocol=PROTO,
         selection_before_screen="preexisting frozen source SHA and reference-only cohorts",
         cases=roster,screen_arm="r3c_plain",screen_cap_s=SOURCE_CAP,
         selection_bias="own solver success; development set, NOT blind",
         own_binary_sha256=binary_sha))
    results=[]
    for row in roster:
        src=pathlib.Path(row["original_path"])
        result=run_original(src,"r3c_plain",SOURCE_CAP)
        result.update(sha256=row["sha256"],cohort=row["cohort"],
                      vars=row["vars"],clauses=row["clauses"],
                      cap_s=SOURCE_CAP)
        results.append(result)
        save(ROOT/"screen-23-results.json",results)
        print("DRNAS_SOLVESET1_SCREEN_TRIAL "+json.dumps(result,sort_keys=True),flush=True)
    qualifies=[z for z in results if z["status"]=="SAT" and
               z["model_original_verified"] and z["wall_E2E_s"]<SOURCE_CAP]
    # Fixed development strata. Avoid selecting on the candidate R2B/R3C-GF2
    # speed or win and disclose that solvability was R3C-plain-conditioned.
    easy=sorted((z for z in qualifies if z["wall_E2E_s"]<0.20),
                key=lambda z:(z["wall_E2E_s"],z["sha256"]))[:4]
    nontrivial=sorted((z for z in qualifies if z["wall_E2E_s"]>=0.20),
                      key=lambda z:(-z["wall_E2E_s"],z["sha256"]))[:6]
    selected=easy+nontrivial
    need(len(selected)>=2,"fewer than two verified-SAT solvable originals")
    keys={x["sha256"] for x in selected}
    chosen=[r for r in roster if r["sha256"] in keys]
    need(len(keys)==len(chosen)==len(selected),"duplicate selected SHA")
    snapshot=dict(protocol=PROTO,source_cohort_count=23,
        screen_qualified_verified_SAT=len(qualifies),
        screen_raw_UNSAT_without_proof=sum(z["status"]=="UNSAT" for z in results),
        screen_timeout_count=sum(z["status"]=="UNKNOWN" for z in results),
        development_selection_not_blind=True,never_test_as_fresh_holdout=True,
        screening_succeeded_only_with_own_native_solver=True,
        screen_binary="r3c_plain",source_cap_s=SOURCE_CAP,
        matched_arms=list(BINARIES),paired_repetitions=REPS,
        benchmark_cap_s=BENCH_CAP,one_logical_CPU=True,
        immutable_binary_sha256=binary_sha,
        source_roster_sha256=sha(ROOT/"source-23-sha.json"),
        screening_result_sha256=sha(ROOT/"screen-23-results.json"),
        selected_originals=chosen,
        selected_screen_times={x["sha256"]:x["wall_E2E_s"] for x in selected})
    save(ROOT/"frozen-solvable-dev-manifest.json",snapshot)
    print("DRNAS_SOLVESET1_SCREEN_FINAL "+json.dumps(dict(
        source_originals=23,verified_SAT=len(qualifies),
        raw_UNSAT_no_proof=snapshot["screen_raw_UNSAT_without_proof"],
        timeouts=snapshot["screen_timeout_count"],
        frozen_dev_originals=len(chosen),
        frozen_easy=len(easy),frozen_nontrivial=len(nontrivial),
        selected_SHA=[r["sha256"] for r in chosen],
        not_blind=True),sort_keys=True),flush=True)
def freeze_verified():
    m=load(ROOT/"frozen-solvable-dev-manifest.json")
    need(m["protocol"]==PROTO and m["immutable_binary_sha256"]==verify_prereq(),
         "binary changed after dev selection")
    need(m["source_roster_sha256"]==sha(ROOT/"source-23-sha.json") and
         m["screening_result_sha256"]==sha(ROOT/"screen-23-results.json"),
         "screening data or source roster mutated")
    roster={r["sha256"]:r for r in catalogue()}
    for row in m["selected_originals"]:
        need(row["sha256"] in roster and roster[row["sha256"]]==row,
             "selected source SHA no longer matches source-only roster")
    return m
def benchmark():
    m=freeze_verified()
    records=[]
    for row in m["selected_originals"]:
        src=pathlib.Path(row["original_path"])
        for rep in range(REPS):
            arms=list(BINARIES)
            random.Random(row["sha256"]+"|SOLVESET1|"+str(rep)).shuffle(arms)
            for arm in arms:
                result=run_original(src,arm,BENCH_CAP)
                result.update(source_SHA=row["sha256"],cohort=row["cohort"],
                              rep=rep,cap_s=BENCH_CAP,development_not_blind=True)
                records.append(result)
                save(ROOT/"paired-original-trials.json",records)
                print("DRNAS_SOLVESET1_PAIRED_TRIAL "+
                      json.dumps(result,sort_keys=True),flush=True)
    require_expected=len(m["selected_originals"])*len(BINARIES)*REPS
    need(len(records)==require_expected,"missing paired attempts")
    audit()
def audit():
    m=freeze_verified()
    records=load(ROOT/"paired-original-trials.json")
    selected={r["sha256"] for r in m["selected_originals"]}
    expected={(sha,arm,rep) for sha in selected for arm in BINARIES
              for rep in range(REPS)}
    got=[(r["source_SHA"],r["arm"],r["rep"]) for r in records]
    need(len(got)==len(expected) and set(got)==expected,
         "paired original record count or SHA incorrect")
    arms={}
    for arm in BINARIES:
        rs=[r for r in records if r["arm"]==arm]
        arms[arm]=dict(trials=len(rs),
            original_SAT_witness_verified=sum(x["model_original_verified"] for x in rs),
            original_UNSAT_no_independent_proof=sum(x["status"]=="UNSAT" for x in rs),
            timeouts=sum(x["status"]=="UNKNOWN" for x in rs),
            strict_PAR2_s=round(sum(x["wall_E2E_s"]
                   if x["status"]=="SAT" and x["model_original_verified"]
                   else 2*BENCH_CAP for x in rs),6),
            sum_solver_s=round(sum(x["solver_s"] for x in rs),6),
            sum_E2E_s=round(sum(x["wall_E2E_s"] for x in rs),6),
            derived_GF2_implications=sum(x["xor_derived_implications"] for x in rs))
    per_sha={}
    for r in m["selected_originals"]:
        sha_val=r["sha256"]
        per_sha[sha_val]={arm:[
             dict(status=x["status"],solver_s=x["solver_s"],
                  E2E_s=x["wall_E2E_s"],rep=x["rep"],
                  original_model_verified=x["model_original_verified"])
             for x in records if x["arm"]==arm and x["source_SHA"]==sha_val]
             for arm in BINARIES}
    result=dict(protocol=PROTO,source_count=23,
        verified_SAT_development_selection=len(selected),
        no_blind_holdout=True,
        screening_conditioned_on_native_r3c_plain=True,
        note="Strict PAR2 excludes independent-UNSAT-unproved source cases",
        original_sha_locked=True,same_one_logical_CPU=True,
        benchmark_cap_s=BENCH_CAP,arms=arms,per_original_SHA=per_sha,
        source_manifest=m)
    save(ROOT/"final-audit.json",result)
    print("DRNAS_SOLVESET1_FINAL "+json.dumps(
        {k:v for k,v in result.items() if k not in ("per_original_SHA","source_manifest")},
        sort_keys=True),flush=True)
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("stage",choices=("screen","bench","audit"))
    a=ap.parse_args()
    if a.stage=="screen":screen()
    elif a.stage=="bench":benchmark()
    else:audit()
if __name__=="__main__":main()
