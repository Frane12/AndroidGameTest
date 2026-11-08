#!/usr/bin/env python3
"""DRNAS C10A structural Kissat/CaDiCaL portfolio research, no new solver runs.

Development: 19 C8D (15s) + 12 C9c (60s) source SHA (C9c 12 original
source CNFs, scanned with same 12k clause/1MiB prefix as C8D).
Precommitted 6 interpretable candidate rules, Kissat fallback, compare
PER-SOURCE PAR2 normalized by each source's original cap (15 or 60s).
LOFO independently trains on other 30 SHA; time cost of the 12k source
prefix scan charged *twice* (one per repetition). SAT/UNSAT truth and
individual trials were validated in C8D/C9c prior audited workflows.
Outcomes in both cohorts already seen: THIS IS NOT A BLIND HOLDOUT.
Production promotion is prohibited; C10B will test rule frozen here
against NEW official2026 SHA not in either training cohort.
"""
from __future__ import annotations
import collections,hashlib,json,pathlib,time
ROOT=pathlib.Path("c10a_out")
D8=pathlib.Path("c10a_prior_c8d")
D9=pathlib.Path("c10a_prior_c9c_final")/"c9c_out"
CNF=pathlib.Path("c10a_prior_c9c_sources")/"c9c_official"
PROTO="DRNAS-C10A-SOURCE31-STRUCTURAL-KISSAT-CADICAL-LOFO-v1"
P8="DRNAS-C8D-C7-BVE-EARLY-CDCL-19SHA-10ARM-2REP-15S-v1"
P9="DRNAS-C9C-OFFICIAL2026-12SHA-4ARM-2REP-60S-E2E-v1"
SCANNED_CLAUSES=12000
SCANNED_BYTES=1048576
CANDIDATES=(
 "kissat_always",
 "cadical_mid_nonhorn_2k",
 "cadical_large_binary_horn",
 "cadical_two_regions",
 "cadical_broad_mid_nonhorn",
 "cadical_broad_nonhorn",
)
def need(b,msg):
    if not b:raise RuntimeError("C10A_FAIL_CLOSED "+str(msg))
def digest(f):
    h=hashlib.sha256()
    with pathlib.Path(f).open("rb") as src:
        for part in iter(lambda:src.read(1<<20),b""):h.update(part)
    return h.hexdigest()
def scan(path):
    start=time.perf_counter()
    nvars=0;seen=set();obs=0;bin=0;horn=0;dups=0
    bytes_read=0;buf=[]
    with pathlib.Path(path).open("rb") as f:
        for l in f:
            bytes_read+=len(l)
            if bytes_read>SCANNED_BYTES or obs>=SCANNED_CLAUSES:break
            text=l.strip()
            if not text or text.startswith(b"c"):continue
            if text.startswith(b"p "):
                p=text.split()
                need(len(p)==4 and p[1]==b"cnf",
                     "unexpected DIMACS source header")
                nvars=int(p[2]);continue
            need(nvars>0,"missing source header")
            for item in text.split():
                val=int(item)
                if val:
                    need(0<abs(val)<=nvars,"literal exceeds original vars")
                    buf.append(val)
                    continue
                c=tuple(sorted(set(buf)));buf=[]
                obs+=1
                bin+=len(c)==2
                horn+=sum(x>0 for x in c)<=1
                dups+=c in seen
                seen.add(c)
                if obs>=SCANNED_CLAUSES:break
    need(nvars>0 and obs>0,"source prefix scan empty")
    return dict(nvars=nvars,observed=obs,
        binary_fraction=round(bin/obs,6),
        horn_fraction=round(horn/obs,6),
        duplicate_fraction=round(dups/obs,6),
        scan_truncated=(bytes_read>SCANNED_BYTES or obs>=SCANNED_CLAUSES),
        scan_cost_s=round(time.perf_counter()-start,6))
def choose(policy,f):
    n=f["nvars"];b=f["binary_fraction"];h=f["horn_fraction"]
    mid=(.08<=b<=.55 and h<.82 and n>=2000)
    large=(b>=.80 and h>=.90 and n>=10000)
    if policy=="kissat_always":pass
    elif policy=="cadical_mid_nonhorn_2k":
        if mid:return "cadical"
    elif policy=="cadical_large_binary_horn":
        if large:return "cadical"
    elif policy=="cadical_two_regions":
        if mid or large:return "cadical"
    elif policy=="cadical_broad_mid_nonhorn":
        if b<.55 and h<.8 and n>=1000:return "cadical"
    elif policy=="cadical_broad_nonhorn":
        if h<.82 and n>=1500:return "cadical"
    else:raise RuntimeError("invalid candidate policy")
    return "kissat"
def development():
    a=json.loads((D8/"report.json").read_text())
    b=json.loads((D9/"report.json").read_text())
    need(a["protocol"]==P8 and a["source_count"]==19 and
         a["full_trials"]==380 and a["status"]=="C8D_E2E_AUDIT_PASS",
         "C8D original 380 trial audit changed")
    need(b["protocol"]==P9 and b["source_count"]==12 and b["full_trials"]==96,
         "C9c original 96 trial audit changed")
    rows=[]
    for c in a["per_source"]:
        f=c["BVE_proxy"]
        need(f["observed"]>0 and f["scan_cost_s"]>=0,"C8D feature unavailable")
        rows.append(dict(sha256=c["sha256"],cohort="C8D-19SHA",
            original_cap_s=15,features=f,reference=dict(
                cadical=c["by_mode"]["cadical"],kissat=c["by_mode"]["kissat"])))
    manifest=json.loads((CNF/"manifest.json").read_text())
    bysha={x["sha256"]:x for x in manifest["cases"]}
    need(len(bysha)==12,"C9c 12 prior source manifest incomplete")
    for c in b["per_source"]:
        m=bysha[c["sha256"]]
        path=CNF/m["filename"]
        need(path.exists() and digest(path)==c["sha256"],
             "C9c original CNF SHA changed")
        f=scan(path)
        need(f["nvars"]==c["nvars"],"C9c prefix nvars differs")
        rows.append(dict(sha256=c["sha256"],cohort="C9c-official2026",
            original_cap_s=60,features=f,reference=dict(
                cadical=c["by_mode"]["cadical"],kissat=c["by_mode"]["kissat"])))
    need(len(rows)==31 and len({x["sha256"] for x in rows})==31,
         "dev 31 disjoint original SHAs missing")
    for x in rows:
        need(set(x["reference"])=={"cadical","kissat"},
             "missing standard solver in paired original")
        for m in ("cadical","kissat"):
            v=x["reference"][m]
            need(0<=v["solved"]<=2 and
                 0<=v["PAR2_s"]<=4*x["original_cap_s"]+1,
                 "bad reference score")
    return rows
def policy_result(policy,rows):
    by=[];gain=0;extra_solved=0;maxreg=0;selected=0
    for c in rows:
        mode=choose(policy,c["features"])
        if mode=="cadical":selected+=1
        fee=2*c["features"]["scan_cost_s"]/c["original_cap_s"]
        normalized_baseline=c["reference"]["kissat"]["PAR2_s"]/c["original_cap_s"]
        normalized_route=c["reference"][mode]["PAR2_s"]/c["original_cap_s"]+fee
        change=normalized_route-normalized_baseline
        gain-=change
        maxreg=max(maxreg,change)
        extra_solved+=c["reference"][mode]["solved"]-c["reference"]["kissat"]["solved"]
        by.append(dict(sha256=c["sha256"],cohort=c["cohort"],
            selected=mode,cap_s=c["original_cap_s"],
            kissat_normalized_PAR2=round(normalized_baseline,6),
            route_charged_normalized_PAR2=round(normalized_route,6),
            normalized_regression=round(change,6),
            solved_delta=c["reference"][mode]["solved"]-c["reference"]["kissat"]["solved"]))
    return dict(policy=policy,selected=selected,
        normalized_gain_vs_kissat=round(gain,6),
        solved_delta=extra_solved,
        worst_source_normalized_regression=round(maxreg,6),rows=by)
def pick(train):
    data=[policy_result(policy,train) for policy in CANDIDATES]
    viable=[x for x in data if
        x["policy"]=="kissat_always" or
        (x["selected"]>=3 and x["selected"]<=len(train)*.6 and
         x["solved_delta"]>=0 and
         x["worst_source_normalized_regression"]<=.55 and
         x["normalized_gain_vs_kissat"]>=1.0)]
    need(viable,"always-Kissat must survive admissibility")
    viable.sort(key=lambda x:(-x["normalized_gain_vs_kissat"],CANDIDATES.index(x["policy"])))
    return viable[0],data
def audit():
    rows=development()
    results=[]
    for i,c in enumerate(rows):
        train=[x for x in rows if x["sha256"]!=c["sha256"]]
        need(len(train)==30,"LOFO formula leaked")
        picked,_=pick(train)
        result=policy_result(picked["policy"],[c])
        results.append(dict(sha256=c["sha256"],cohort=c["cohort"],
            trained_without_test_formula=True,
            policy=picked["policy"],
            **{k:v for k,v in result.items() if k not in ("rows","policy")},
            test=result["rows"][0]))
    chosen,grid=pick(rows)
    baseline=sum(x["reference"]["kissat"]["PAR2_s"]/x["original_cap_s"]
                 for x in rows)
    lofo=sum(x["test"]["route_charged_normalized_PAR2"] for x in results)
    model_gain=baseline-lofo
    lofo_reg=sum(x["test"]["normalized_regression"]>.05 for x in results)
    lofo_wins=sum(x["test"]["normalized_regression"]<-.05 for x in results)
    aggregate=dict(protocol=PROTO,development_cannot_claim_blind=True,
        original_SHA_count=31,cohorts=["C8D-19SHA","C9c-official2026"],
        source_prefix_limit_clauses=SCANNED_CLAUSES,
        source_prefix_limit_bytes=SCANNED_BYTES,
        C8D_real_prior_trials=380,C9c_real_prior_trials=96,
        no_new_solver_timings=True,
        frozen_candidate_rules=list(CANDIDATES),
        min_source_group_LOFO_train=30,
        normalized_for_different_15s_and_60s_caps=True,
        charge_source_scan_twice_per_formula=True,
        kissat_normalized_PAR2=round(baseline,6),
        lofo_normalized_PAR2=round(lofo,6),
        lofo_speedup_vs_kissat_x=round(baseline/lofo,6),
        lofo_normalized_gain=round(model_gain,6),
        lofo_winning_formulas=lofo_wins,lofo_regressed_formulas=lofo_reg,
        lofo_min_single_source_gain=round(-max(x["test"]["normalized_regression"]
                                               for x in results),6),
        candidate_grid=[{k:v for k,v in d.items() if k!="rows"} for d in grid],
        frozen_policy=chosen["policy"],
        frozen_policy_dev_normalized_gain=chosen["normalized_gain_vs_kissat"],
        no_auto_promotion=True,
        followup="new SHA-source-only freeze and real 60s Kissat/CaDiCaL/routed E2E")
    ROOT.mkdir(exist_ok=True)
    (ROOT/"report.json").write_text(json.dumps(
        dict(**aggregate,lofo_cases=results),indent=2,sort_keys=True)+"\n")
    print("C10A_FINAL",json.dumps(aggregate,sort_keys=True),flush=True)
    for r in results:
        print("C10A_LOFO",json.dumps(dict(sha256=r["sha256"],cohort=r["cohort"],
             policy=r["policy"],selected=r["test"]["selected"],
             gain=-r["test"]["normalized_regression"]),sort_keys=True),flush=True)
if __name__=="__main__":
    audit()
