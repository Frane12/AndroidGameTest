#!/usr/bin/env python3
"""MRE6f: predeclared repeat of MRE6e's discovered case plus controls.

IMPORTANT: the positive candidate 2fcd8533 was observed in MRE6e.
This is a post-hoc development replication, NOT an unseen holdout.
All three original SAT2026 CNFs and the identical CMS shared library are pinned
by the complete upstream SHA-locked MRE6e artifacts.
"""
from __future__ import annotations
import argparse,collections,hashlib,json,math,os,pathlib,random,statistics
import mre6e_conflict_diagnostic as prior

PROTO="DRNAS-MRE6F-3-LOCKED-SAT2026-3SEEDS-2LIMITS-4ARMS-72-v1"
ROOT=pathlib.Path("mre6f")
CASE_LABELS={
 "2fcd8533":"MRE6E_POSTHOC_STRONG_QUOTIENT",
 "a45aefde":"MRE6E_SMALL_EQUALITY_CONTROL",
 "de8c42d5":"MRE6E_NO_EQUALITY_CONTROL",
}
LIMITS=(1000,5000)
REPS=3
MODES=prior.MODES

def need(ok,msg):
    if not ok:raise RuntimeError("MRE6F_FAIL_CLOSED "+str(msg))

def selected():
    data=prior.cases()
    groups={}
    for c in data:
        prefix=c["gbd"][:8]
        if prefix in CASE_LABELS:
            need(prefix not in groups,"ambiguous official ID prefix")
            groups[prefix]=c
    need(set(groups)==set(CASE_LABELS),"changed frozen seven-source cohort")
    return groups

def run_one(prefix,binary):
    cases=selected()
    c=cases[prefix]
    prior.PROTO=PROTO
    ROOT.mkdir(parents=True,exist_ok=True)
    records=[]
    for rep in range(REPS):
        for cap in LIMITS:
            order=list(MODES)
            random.Random(PROTO+c["sha256"]+str(rep)+str(cap)).shuffle(order)
            for mode in order:
                row=prior.trial(c,rep,mode,cap,binary)
                row["MRE6F_group"]=CASE_LABELS[prefix]
                row["MRE6F_posthoc"]=True
                row["MRE6F_prior_exploration_run"]=42499473274
                row["MRE6F_fixed_compiled_bridge_run"]=42499473274
                records.append(row)
                (ROOT/("case-%s.json"%prefix)).write_text(
                    json.dumps(records,sort_keys=True)+"\n")
                print("MRE6F_TRIAL",json.dumps(row,sort_keys=True),flush=True)
    need(len(records)==REPS*len(LIMITS)*len(MODES),"case missing trials")
    print("MRE6F_CASE_PASS",prefix,len(records),flush=True)

def geomean(values):
    return math.exp(statistics.mean(math.log(v) for v in values))

def audit():
    cases=selected()
    rows=[]
    for prefix in CASE_LABELS:
        file=ROOT/("case-%s.json"%prefix)
        need(file.exists(),"missing complete case file "+prefix)
        rows.extend(json.loads(file.read_text()))
    need(len(rows)==len(CASE_LABELS)*REPS*len(LIMITS)*len(MODES),
         "expected 72 complete paired attempts")
    paired=collections.defaultdict(dict)
    for r in rows:
        prefix=r["official_gbd"][:8]
        c=cases.get(prefix)
        need(c and r["source_sha256"]==c["sha256"],
             "source mismatch")
        need(r["protocol"]==PROTO and r["MRE6F_posthoc"] is True,
             "mislabeled post-hoc experiment")
        need(r["pinned_CMS_source_commit"]==prior.d.SOURCE_CMS_SHA,
             "pinned CMS source changed")
        need(r["MRE6F_group"]==CASE_LABELS[prefix],"wrong control label")
        need(r["source_sha_verified"],"missing SHA audit")
        need(r["conflict_limit"] in LIMITS and r["rep"] in range(REPS),
             "unlocked pair")
        if r["status"]=="SAT":
            need(r["original_sat_witness_verified"],"unchecked SAT")
        if r["status"]=="UNSAT":
            need(r["official_status"]=="UNSAT","UNSAT differs from official")
        if r["status"]=="BUDGET":
            need(r["native"] is not None and
                 r["native"]["conflicts"]>0,"no real CDCL counters")
        key=(prefix,r["rep"],r["conflict_limit"])
        need(r["mode"] not in paired[key],"duplicate mode")
        paired[key][r["mode"]]=r
    need(len(paired)==len(CASE_LABELS)*REPS*len(LIMITS),"incomplete matched group")
    for arms in paired.values():
        need(set(arms)==set(MODES),"missing arm")
        need(len({x["seed"] for x in arms.values()})==1,"different paired seeds")
    groups={}
    for prefix,label in CASE_LABELS.items():
        groups[prefix]={}
        for cap in LIMITS:
            candidates=[]
            for rep in range(REPS):
                a=paired[(prefix,rep,cap)]
                base=a["native_no_xor"]
                allmode=a["all_no_xor"]
                need(base["native"] and allmode["native"],
                     "missing native CDCL stats")
                pb=base["native"]["propagations"]
                pa=allmode["native"]["propagations"]
                candidates.append(dict(rep=rep,seed=base["seed"],
                    baseline_status=base["status"],all_status=allmode["status"],
                    baseline_conflicts=base["native"]["conflicts"],
                    all_conflicts=allmode["native"]["conflicts"],
                    original_clauses=base["original_clauses"],
                    transformed_clauses=allmode["reduction_gate"]["cnf_after"],
                    eliminated_variables=allmode["reduction_gate"].get("variables_eliminated",0),
                    propagations_baseline=pb,propagations_all=pa,
                    propagation_reduction_percent=round(100*(pb-pa)/pb,5) if pb else None,
                    decisions_baseline=base["native"]["decisions"],
                    decisions_all=allmode["native"]["decisions"],
                    baseline_wall_s=base["wall_s"],all_wall_s=allmode["wall_s"],
                    full_wall_speedup=round(base["wall_s"]/allmode["wall_s"],6),
                    native_wall_speedup=round(base["native_wall_s"]/allmode["native_wall_s"],6),
                    baseline_prep_s=base["prep_s"],all_prep_s=allmode["prep_s"]))
            groups[prefix][str(cap)]=dict(label=label,replications=candidates,
                all_three_wall_faster=sum(x["full_wall_speedup"]>1 for x in candidates)==REPS,
                geomean_full_wall_speedup=round(
                    geomean([x["full_wall_speedup"] for x in candidates]),6),
                geomean_native_wall_speedup=round(
                    geomean([x["native_wall_speedup"] for x in candidates]),6),
                median_propagation_reduction_percent=round(
                    statistics.median(x["propagation_reduction_percent"] for x in candidates),5))
    report=dict(protocol=PROTO,upstream_run=42499473274,measurements=len(rows),
        cases=3,reps_per_case=REPS,conflict_limits=list(LIMITS),
        posthoc_development_only=True,not_a_new_blind_holdout=True,
        same_original_SHA_and_seed_pairs=True,independent_UNSAT_LRAT=False,
        all_raw_attempts_audited=True,
        promotion_allowed=False,groups=groups)
    ROOT.mkdir(parents=True,exist_ok=True)
    (ROOT/"report.json").write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
    print("MRE6F_FINAL",json.dumps(report,sort_keys=True),flush=True)

def selftest():
    need(len(CASE_LABELS)==3 and REPS==3 and LIMITS==(1000,5000),
         "research protocol changed")
    prior.selftest()
    print("MRE6F_SELFTEST_PASS",PROTO,flush=True)

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("action",choices=("selftest","case","audit"))
    parser.add_argument("--prefix",choices=sorted(CASE_LABELS))
    parser.add_argument("--binary",default="mre6e/native")
    args=parser.parse_args()
    if args.action=="selftest":selftest()
    elif args.action=="case":
        need(args.prefix is not None,"case requires prefix")
        run_one(args.prefix,args.binary)
    else:audit()
