#!/usr/bin/env python3
"""MRE6e: bounded, source-SHA-locked CDCL causal diagnostic.

The seven SAT2026 CNFs are frozen from MRE6b BEFORE MRE6d outcomes. This is
a DIAGNOSTIC re-use (not a new blind holdout). A conflict limit, not an
artificial timeout, makes CMS return its counters at an UNKNOWN result.
Only SAT plus independently checked original witness is a solved SAT case.
UNSAT is cross-checked with official status but has no independent LRAT.
"""
from __future__ import annotations
import argparse,collections,json,os,pathlib,random,re,statistics,subprocess,tempfile,time
import mre6d_paired as d
import mre6b_blind_freeze as freeze
import r195_native_cms_benchmark as r195

PROTO="DRNAS-MRE6E-LOCKED7-4ARMS-2CONFLICTCAPS-1REP-v1"
ROOT=pathlib.Path("mre6e")
MODES=d.MODES
LIMITS=(1000,5000)
REPS=1
CAP=6.0
SHARDS=4
PAT=re.compile(r"^R195_RESULT status=(SAT|UNSAT|BUDGET) conflicts=(\d+) decisions=(\d+) propagations=(\d+) source_rows=(\d+) derived_rows=(\d+)$",re.M)

def need(cond,reason):
    if not cond:raise RuntimeError("MRE6E_FAIL_CLOSED "+str(reason))

def parse(text):
    match=PAT.search(text)
    need(match is not None,"missing complete native CMS bounded verdict/counters")
    status=match[1]
    native=dict(conflicts=int(match[2]),decisions=int(match[3]),
                propagations=int(match[4]),source_rows=int(match[5]),
                derived_rows=int(match[6]))
    model={}
    for line in text.splitlines():
        if line.startswith("v "):
            for val in map(int,line[2:].split()):
                if val:
                    need(abs(val) not in model,"duplicate model literal")
                    model[abs(val)]=(val>0)
    if status=="SAT":need(bool(model),"SAT without complete model")
    else:need(not model,"UNKNOWN/UNSAT must not have SAT witness")
    return status,native,model

def trial(case,rep,mode,conflict_limit,binary):
    need(mode in MODES and conflict_limit in LIMITS,"arm/limit outside frozen design")
    source=d.ROOT/case["filename"]
    need(freeze.sha256(source.read_bytes())==case["sha256"],
         "original source SHA mismatch")
    start=time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="drnas-mre6e-") as temp:
        folder=pathlib.Path(temp)
        cnf,xor,n,gate,pr=d.build_arm(source,mode,folder)
        empty=folder/"empty.tsv"
        empty.write_text("")
        remaining=CAP-(time.perf_counter()-start)
        result="TIMEOUT"
        native=None
        verified=False
        process_wall=None
        if remaining>0.1:
            env=os.environ.copy()
            env["DRNAS_MAX_CONFLICTS"]=str(conflict_limit)
            t0=time.perf_counter()
            try:
                p=subprocess.run(
                    [str(pathlib.Path(binary).resolve()),str(pathlib.Path(cnf).resolve()),
                     str(pathlib.Path(xor).resolve()),str(empty.resolve()),
                     "source_xor_no_gauss",str(d.seed_of(case["sha256"],rep))],
                    text=True,capture_output=True,errors="replace",timeout=remaining,
                    env=env,check=False)
            except subprocess.TimeoutExpired:
                p=None
            process_wall=round(time.perf_counter()-t0,6)
            if p is not None:
                need(p.returncode==0,"native bridge failed: "+p.stderr[-1200:])
                result,native,model=parse(p.stdout)
                if result=="SAT":
                    if pr is not None:
                        model=(d.all_eq.reconstruct(model,pr["mapping"])
                               if "mapping" in pr else d.m6.reconstruct(model,pr))
                    r195.verify_model(source,model)
                    verified=True
                if result in ("SAT","UNSAT"):
                    need(result==case["original_verified_status"],
                         "CMS verdict disagrees with official original")
                if result=="BUDGET":
                    need(native["conflicts"]>0,"bounded unknown without CDCL conflicts")
        elapsed=time.perf_counter()-start
        if elapsed>=CAP:
            need(result=="TIMEOUT","real verified outcome exceeded total wall cap")
        return dict(protocol=PROTO,source_sha256=case["sha256"],
            official_gbd=case["gbd"],official_status=case["original_verified_status"],
            mode=mode,rep=rep,seed=d.seed_of(case["sha256"],rep),
            conflict_limit=conflict_limit,status=result,
            wall_s=round(elapsed,6),prep_s=gate["preprocessing_wall_s"],
            native_wall_s=process_wall,
            par2_s=round(elapsed if result in ("SAT","UNSAT") else 2*CAP,6),
            native=native,original_sat_witness_verified=verified,
            unsat_independent_LRAT=False,source_sha_verified=True,
            reduction_gate=gate,quotient_applied=bool(pr),
            original_clauses=case["clauses"],original_vars=case["vars"],
            pinned_CMS_source_commit=d.SOURCE_CMS_SHA,
            diagnostic_not_blind=True,github_sha=os.environ.get("GITHUB_SHA","local"))

def cases():
    freeze.verify()
    manifest=json.loads((d.ROOT/"manifest.json").read_text())
    need(len(manifest["cases"])==7 and manifest["statuses"]=={"SAT":4,"UNSAT":3},
         "frozen official cohort changed")
    return manifest["cases"]

def shard(idx,binary):
    need(0<=idx<SHARDS,"bad shard")
    data=cases()
    selected=[case for i,case in enumerate(data) if i%SHARDS==idx]
    need(bool(selected),"empty shard")
    ROOT.mkdir(parents=True,exist_ok=True)
    records=[]
    for case in selected:
        for rep in range(REPS):
            for cap in LIMITS:
                modes=list(MODES)
                random.Random(PROTO+case["sha256"]+str(rep)+str(cap)).shuffle(modes)
                for mode in modes:
                    row=trial(case,rep,mode,cap,binary)
                    records.append(row)
                    (ROOT/("shard-%d.json"%idx)).write_text(
                         json.dumps(records,sort_keys=True)+"\n")
                    print("MRE6E_TRIAL",json.dumps(row,sort_keys=True),flush=True)
    need(len(records)==len(selected)*REPS*len(LIMITS)*len(MODES),
         "incomplete diagnostic shard")
    print("MRE6E_SHARD_PASS",idx,len(selected),len(records),flush=True)

def audit():
    data=cases()
    pairs=collections.defaultdict(dict)
    records=[]
    for idx in range(SHARDS):
        path=ROOT/("shard-%d.json"%idx)
        need(path.exists(),"missing shard artifact")
        records.extend(json.loads(path.read_text()))
    need(len(records)==7*REPS*len(LIMITS)*len(MODES),
         "expected exactly 56 complete attempts")
    allowed={c["sha256"]:c for c in data}
    for row in records:
        c=allowed.get(row["source_sha256"])
        need(c is not None and row["official_gbd"]==c["gbd"],
             "unknown source")
        need(row["protocol"]==PROTO and row["diagnostic_not_blind"],
             "protocol/provenance mismatch")
        need(row["pinned_CMS_source_commit"]==d.SOURCE_CMS_SHA,
             "CMS source commit drift")
        need(row["source_sha_verified"],"SHA never validated")
        if row["status"]=="SAT":
            need(row["original_sat_witness_verified"],"unchecked model")
        if row["status"]=="UNSAT":
            need(c["original_verified_status"]=="UNSAT",
                 "UNSAT contradicts official original")
        if row["status"]=="BUDGET":
            need(row["native"] is not None and
                 row["native"]["conflicts"]>0,"missing bounded CDCL counters")
        key=(row["source_sha256"],row["rep"],row["conflict_limit"])
        need(row["mode"] not in pairs[key],"duplicate mode within pair")
        pairs[key][row["mode"]]=row
    need(len(pairs)==7*REPS*len(LIMITS),"missing source-limit pairs")
    for arms in pairs.values():
        need(set(arms)==set(MODES),"not all four modes paired")
        need(len({x["seed"] for x in arms.values()})==1,"paired seed mismatch")
        need(len({x["pinned_CMS_source_commit"] for x in arms.values()})==1,
             "different CMS libraries within pair")
    modes={}
    for limit in LIMITS:
        modes[str(limit)]={}
        for mode in MODES:
            rows=[x for x in records if x["mode"]==mode and x["conflict_limit"]==limit]
            counts=[x["native"] for x in rows if x["native"]]
            modes[str(limit)][mode]=dict(
                attempts=len(rows),solved=sum(r["status"] in ("SAT","UNSAT") for r in rows),
                budget_unknown=sum(r["status"]=="BUDGET" for r in rows),
                wall_timeout=sum(r["status"]=="TIMEOUT" for r in rows),
                par2_s=round(sum(r["par2_s"] for r in rows),6),
                wall_s=round(sum(r["wall_s"] for r in rows),6),
                median_prep_s=round(statistics.median(r["prep_s"] for r in rows),6),
                cdcl_samples=len(counts),
                median_conflicts=statistics.median(x["conflicts"] for x in counts) if counts else None,
                median_decisions=statistics.median(x["decisions"] for x in counts) if counts else None,
                median_propagations=statistics.median(x["propagations"] for x in counts) if counts else None)
    report=dict(protocol=PROTO,cohort="reused_MRE6b_official7_not_blind",
        official_original_count=7,comparisons=len(pairs),measurements=len(records),
        native="same CMS 5.11.15 patched library for all 4 arms",
        equal_shas_seeds_budgets=True,modes=modes,
        independent_unsat_LRAT=False,
        no_unverified_sat_verdicts=True,
        conflict_budget_unknown_is_not_a_solution=True,
        promotion_allowed=False)
    ROOT.mkdir(parents=True,exist_ok=True)
    (ROOT/"report.json").write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
    print("MRE6E_FINAL",json.dumps(report,sort_keys=True),flush=True)

def selftest():
    need(len(MODES)==4 and len(LIMITS)==2 and REPS==1 and CAP==6.0,
         "diagnostic design unexpectedly changed")
    a="R195_RESULT status=BUDGET conflicts=1000 decisions=2000 propagations=4000 source_rows=0 derived_rows=0\n"
    stat,native,model=parse(a)
    need(stat=="BUDGET" and native["conflicts"]==1000 and not model,
         "native unknown counter parser broken")
    d.selftest()
    print("MRE6E_SELFTEST_PASS",PROTO,flush=True)

if __name__=="__main__":
    a=argparse.ArgumentParser()
    a.add_argument("action",choices=("selftest","shard","audit"))
    a.add_argument("--shard",type=int,default=0)
    a.add_argument("--binary",default="mre6e/native")
    p=a.parse_args()
    if p.action=="selftest":selftest()
    elif p.action=="shard":shard(p.shard,p.binary)
    else:audit()
