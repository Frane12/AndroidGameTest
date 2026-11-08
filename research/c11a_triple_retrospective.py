#!/usr/bin/env python3
"""C11a three-way source-header portfolio: development audit (NOT BLIND).

39 fixed original SHA: C8D 19 (15-second PAR2), C9c 12 (60-second),
C10b 8 (60-second), with SOURCE-ONLY nvars and original nclauses.
Results from independent previous GitHub audit artifacts, no solver reruns.
Do not combine different caps or claim held-out validation.
Chosen AFTER inspecting C10b 600-variable exception. No auto-promotion.
"""
import collections,json,pathlib
PROTO="DRNAS-C11A-39SHA-THREE-BACKEND-DEVELOPMENT-AUDIT-20261109-v1"
RULE="if 200<=nvars<=1500 and clauses/nvars<=60: cadical_noelim; elif nvars<=400 or clauses/nvars>=200 or (nvars>=25000 and clauses/nvars<=2): kissat; else: cadical"
ROOT=pathlib.Path("c11a_out")
C8=pathlib.Path("c11_dev_c8d/report.json")
C9=pathlib.Path("c11_dev_c9c/c9c_out/report.json")
C10=pathlib.Path("c11_dev_c10b/c10b_out/report.json")
MORPH=pathlib.Path("c11_dev_c10b/c10a_reference/report.json")
def need(ok,msg):
    if not ok:raise RuntimeError("C11A_FAIL_CLOSED "+str(msg))
def pick(n,m):
    d=m/n
    if 200<=n<=1500 and d<=60:return "cadical_noelim"
    if n<=400 or d>=200 or (n>=25000 and d<=2):return "kissat"
    return "cadical"
def analysis():
    a=json.loads(C8.read_text())
    b=json.loads(C9.read_text())
    c=json.loads(C10.read_text())
    mor=json.loads(MORPH.read_text())
    need(a["source_count"]==19 and a["full_trials"]==380
         and a["protocol"]=="DRNAS-C8D-C7-BVE-EARLY-CDCL-19SHA-10ARM-2REP-15S-v1","bad C8D")
    need(b["source_count"]==12 and b["full_trials"]==96
         and b["protocol"]=="DRNAS-C9C-OFFICIAL2026-12SHA-4ARM-2REP-60S-E2E-v1","bad C9c")
    need(c["original_source_count"]==8 and c["end_to_end_real_trials"]==64
         and c["protocol"]=="DRNAS-C10B-2026-12SHA-4ARM-2REPS-60S-REAL-PAR2-v1","bad C10b")
    need(mor["cases"]==31 and mor["protocol"]==
      "DRNAS-C10A-31SHA-STRUCTURAL-RETROSPECTIVE-CAUSAL-CONTEXT-v1","bad C10a morphology")
    shapes={v["sha256"]:v["source_features"] for v in mor["all_cases"]}
    output=[];scores=[]
    for label,rows,cap in (
        ("C8D_development",a["per_source"],15),
        ("C9c_development",b["per_source"],60),
        ("C10b_development",c["per_source"],60)):
        cohort=[];stats={mode:dict(solved=0,PAR2_s=0)
                           for mode in ("kissat","cadical","c10_old","c11_triple")}
        for x in rows:
            sha=x["sha256"]
            f=shapes.get(sha)
            if label=="C10b_development":
                n=x["nvars"];m=x["nclauses"]
            else:
                need(f is not None,"missing historical morphological SHA "+sha)
                n=f["nvars"];m=f["nclauses"]
            mode=pick(n,m)
            by=x.get("by_mode",x.get("modes"))
            need("kissat" in by and "cadical" in by,"missing reference")
            if mode=="cadical_noelim":
                chosen=by["c9_old"] if label=="C10b_development" else by[mode]
                if label=="C10b_development":need(n<=1500,"noelim wasn't measured on this source")
            else:chosen=by[mode]
            if label=="C10b_development":
                old=by["c10_structural"]
            else:
                base="kissat" if n<=400 or m/n>=200 or (n>=25000 and m/n<=2) else "cadical"
                old=by[base]
            score={"kissat":by["kissat"],"cadical":by["cadical"],
                   "c10_old":old,"c11_triple":chosen}
            for k,r in score.items():
                need(0<=r["solved"]<=2 and r["PAR2_s"]>0,"bad historical score")
                stats[k]["solved"]+=r["solved"]
                stats[k]["PAR2_s"]+=r["PAR2_s"]
            cohort.append(dict(sha256=sha,gbd=x["gbd"],nvars=n,nclauses=m,
                density=round(m/n,5),selected_backend=mode,
                gain_vs_Kissat_PAR2_s=round(by["kissat"]["PAR2_s"]-chosen["PAR2_s"],6),
                gain_vs_C10_PAR2_s=round(old["PAR2_s"]-chosen["PAR2_s"],6),
                C11_PAR2_s=chosen["PAR2_s"],C11_solved=chosen["solved"],
                Kissat_PAR2_s=by["kissat"]["PAR2_s"],Kissat_solved=by["kissat"]["solved"],
                C10_PAR2_s=old["PAR2_s"],C10_solved=old["solved"]))
        for x in stats.values():x["PAR2_s"]=round(x["PAR2_s"],6)
        biggest=max(cohort,key=lambda x:x["gain_vs_Kissat_PAR2_s"])
        summary=dict(cohort=label,cap_s=cap,source_count=len(rows),
            modes=stats,
            C11_speedup_vs_Kissat_x=round(stats["kissat"]["PAR2_s"]/stats["c11_triple"]["PAR2_s"],6),
            gain_excluding_largest_source_s=round(stats["kissat"]["PAR2_s"]-
                 stats["c11_triple"]["PAR2_s"]-biggest["gain_vs_Kissat_PAR2_s"],6),
            largest_gain_case_sha256=biggest["sha256"],
            regressed_vs_Kissat=sum(v["gain_vs_Kissat_PAR2_s"]<-.05 for v in cohort),
            selected=collections.Counter(v["selected_backend"] for v in cohort))
        scores.append(summary)
        output.extend([dict(source_cohort=label,**v) for v in cohort])
    need(len(output)==39 and len({v["sha256"] for v in output})==39,
         "39 original SHA sources not disjoint")
    report=dict(protocol=PROTO,cohorts=scores,all_cases=output,
         source_SHA_count=39,no_new_solver_execution=True,
         policy_frozen_for_C11b=RULE,selected_C11_rule_probes_after_C10b=True,
         development_after_observing_C10b_600variable_exception=True,
         trial_censoring_limits_NOT_combined=True,
         source_header_overhead_not_charged_in_retrospective=True,
         no_auto_promotion=True,
         next_step="C11b prospective new official2026 original SHA E2E")
    ROOT.mkdir(parents=True,exist_ok=True)
    (ROOT/"report.json").write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
    print("C11A_FINAL",json.dumps({k:v for k,v in report.items() if k!="all_cases"},sort_keys=True),flush=True)
if __name__=="__main__":analysis()
