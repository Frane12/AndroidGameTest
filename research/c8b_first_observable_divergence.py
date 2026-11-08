#!/usr/bin/env python3
"""DRNAS C8b — first OBSERVABLE inprocessing signal, not presumed causal first event.

Source-locked three C8 SAT originals and all 4 CaDiCaL elimination/vivification
factorial modes. Each snapshot starts a fresh unmodified CaDiCaL 1.7.3 process
and stops at a specified conflict cap. Do not call snapshots a continuous trace.
Coarse conflict grid + predeclared bisection to narrow first observed (a)
BVE attempts, (b) vivification attempts, and (c) divergence in CDCL cumulative
search counters between default and interventions. Bisection is bracketed by
observed adjacent coarse samples and is NOT proof of monotonicity; add
intermediate neighbor validation and never overstate a first exact internal event.

C8 full end-to-end SAT / PAR2 results are read from immutable old artifact,
not recomputed or mixed into bounded probe PAR2. No main modification.
"""
from __future__ import annotations
import argparse,collections,hashlib,json,os,pathlib,re,subprocess,time
import c8_bve_cdcl_trace as c8
import c7_standard_solver_bve_crosscheck as c7
import mre11b_prospective_benchmark as ref
import r195_native_cms_benchmark as cms

PROTO="DRNAS-C8B-3SHA-4ARM-FIRST-OBSERVABLE-5000-20000-SNAPSHOT-v1"
OUT=pathlib.Path("c8b_out")
PRIOR=pathlib.Path("c8b_c8_previous")
BUDGETS=(5000,6000,7000,8000,9000,10000,11000,12000,
         13000,14000,15000,16000,17500,20000)
MODES=c8.MODES
CAP=15.0
BINARY_PRECISION=25
SEARCH_METRICS=("decisions","propagations","restarts","learned","reductions",
                "deduplicated")
EVENT_METRICS=("elimtried","eliminated","elimres","vivifychecks","vivified",
               "vivifications","elimgates")
COUNTER_METRICS=SEARCH_METRICS+EVENT_METRICS+("conflicts",)
def need(ok,msg):
    if not ok:raise RuntimeError("C8B_FAIL_CLOSED "+str(msg))
def sources():
    ss=c8.sources()
    need(len(ss)==3 and len({c["sha256"] for c in ss})==3,
         "C8 three original SHA changed")
    return ss
def _probe(c,mode,budget,kind):
    need(mode in MODES and 5000<=budget<=20000,"unregistered bounded process")
    original=c["path"]
    need(c7.digest(original)==c["sha256"],"source original CNF drift")
    cmd=["/usr/bin/cadical",*c8.OPTIONS[mode],"-v","-c",str(budget),
         str(original.resolve())]
    t=time.perf_counter()
    try:
        run=subprocess.run(cmd,capture_output=True,text=True,errors="replace",
                           check=False,timeout=CAP)
    except subprocess.TimeoutExpired:
        run=None
    elapsed=time.perf_counter()-t
    status="DIAGNOSTIC_TIMEOUT";stats=None;events=[];verified=False
    if run is not None:
        status,model=ref.external_parse(run)
        need(status in ("UNKNOWN","SAT"),
             "unexpected result for selected original known SAT")
        if status=="SAT":
            cms.verify_model(original,model)
            verified=True
        stats,glue=c8.parse_stats(run.stdout)
        c8.validate_stats(stats,mode)
        for key in COUNTER_METRICS:
            need(key in stats,"missing actual CaDiCaL counter "+key)
        # Phase text is kept verbatim; many event logs have no conflict index
        # and must never be assigned an invented exact conflict timestamp.
        lines=run.stdout.splitlines()
        for line in lines:
            if not line.startswith("c ") or re.match(r"^c [A-Za-z_.-]+:",line):
                continue
            if re.search(r"(eliminat|vivif|simplif|probing|subsum|gating|reducing)",
                         line,re.I):
                events.append(line[:240])
        events=events[:60]
    if elapsed>CAP: status="DIAGNOSTIC_TIMEOUT";stats=None;events=[]
    return dict(protocol=PROTO,kind=kind,gbd=c["gbd"],
        source_sha256=c["sha256"],mode=mode,
        cap_conflicts=budget,status=status,
        SAT_model_verified=verified,
        wall_s=round(elapsed,6),counts=stats,
        selected_verbose_event_lines=events,
        bounded_diagnostic_not_PAR2=True,
        snapshot_is_new_process=True,
        no_independent_seed=True,
        build_sha=os.getenv("GITHUB_SHA","LOCAL"))
def same_search(a,b):
    if a["counts"] is None or b["counts"] is None:return None
    return all(a["counts"][k]==b["counts"][k] for k in SEARCH_METRICS)
def first_bracket(records, pred, levels=BUDGETS):
    hit=[k for k in levels if pred(records[k])]
    if not hit:return None
    upper=hit[0]
    ix=levels.index(upper)
    lower=levels[ix-1] if ix>0 else None
    return [lower,upper]
def _refine(c,records,a,b,coarse,key,label):
    """Refine a bracket if it is locally false->true. No monotonic assumption claim."""
    if coarse is None or coarse[0] is None:return dict(
        coarse=coarse,refined=None,probes=0)
    lower,upper=coarse
    def predicate(budget):
        # One or both mode records may already be cached at a budget.
        for mode in (a,b):
            if mode is not None and budget not in records[mode]:
                records[mode][budget]=_probe(c,mode,budget,"adaptive_bracket_check")
        if b is None:
            x=records[a][budget]
            return x["counts"] is not None and x["counts"][key]>0
        aa=records[a][budget];bb=records[b][budget]
        return same_search(aa,bb) is False
    need(not predicate(lower),"false bracket endpoint unexpectedly positive "+label)
    need(predicate(upper),"true bracket endpoint unexpectedly negative "+label)
    measured=set()
    while upper-lower>BINARY_PRECISION:
        mid=(lower+upper)//2
        measured.add(mid)
        if predicate(mid):upper=mid
        else:lower=mid
    # Test adjacent midpoint and lower endpoint again via fresh independent
    # process rather than reuse cache to detect obvious outcome instability.
    final_upper=upper
    check=_probe(c,a,final_upper,"independent_boundary_recheck")
    check2=(_probe(c,b,final_upper,"independent_boundary_recheck")
            if b is not None else None)
    ok=(check["counts"] is not None and
        ((check["counts"][key]>0) if b is None else
         (same_search(check,check2) is False)))
    need(ok,"first-observable bracket not reproducible "+label)
    return dict(coarse=coarse,refined=[lower,upper],
                resolution_conflicts=upper-lower,
                extra_windows=len(measured),recheck_passed=ok)
def _prior_c8():
    f=PRIOR/"report.json"
    need(f.is_file(),"original C8 report missing")
    report=json.loads(f.read_text())
    need(report["full_trial_count"]==36 and
         report["diagnostic_trace_count"]==60 and
         report["source_SHA3"]==[c["sha256"] for c in sources()] and
         report["protocol"]==c8.PROTO,
         "previous C8 PAR2 reference changed")
    return report
def smoke():
    c=sources()[0]
    a=_probe(c,"default",5000,"smoke")
    b=_probe(c,"noelim",5000,"smoke")
    need(a["counts"] is not None and b["counts"] is not None and
         same_search(a,b) and a["counts"]["elimtried"]==0 and
         b["counts"]["elimtried"]==0,
         "C8 expected exact identical early CDCL first 5k missing")
    print("C8B_5K_FROZEN_SEARCH_PARITY_SMOKE_PASS",json.dumps(
        dict(source=c["gbd"],counts=a["counts"]),sort_keys=True),flush=True)
def shard(index):
    cc=sources()
    need(index in range(len(cc)),"invalid C8 source")
    c=cc[index];OUT.mkdir(exist_ok=True)
    records={mode:{} for mode in MODES}
    for budget in BUDGETS:
        for mode in MODES:
            row=_probe(c,mode,budget,"fixed_grid_snapshot")
            need(row["counts"] is not None,"fixed grid probe timed out")
            records[mode][budget]=row
            (OUT/("grid-%d.json"%index)).write_text(json.dumps(
                [records[m][b] for b in BUDGETS for m in MODES
                 if b in records[m]],indent=2,sort_keys=True)+"\n")
            print("C8B_GRID",json.dumps(dict(gbd=c["gbd"],mode=mode,
                budget=budget,status=row["status"],
                counters={k:row["counts"][k] for k in COUNTER_METRICS}),
                sort_keys=True),flush=True)
    bracket={}
    for mode in MODES:
        for key in ("elimtried","eliminated","vivifychecks","vivified"):
            bracket[mode+"."+key]=first_bracket(records[mode],
                 lambda x,k=key:x["counts"][k]>0)
    for mode in MODES:
        if mode=="default":continue
        bracket["default_vs_"+mode]=first_bracket(
            records["default"],
            lambda x,m=mode: same_search(x,records[m][x["cap_conflicts"]]) is False)
    # Refine the first BVE attempt, first vivification attempt and earliest
    # actual search-counter divergence on a preregistered mode subset.
    selected=[
        ("default_BVE_attempt","default",None,"elimtried",
             bracket["default.elimtried"]),
        ("default_vivify_attempt","default",None,"vivifychecks",
             bracket["default.vivifychecks"]),
        ("novivify_BVE_attempt","novivify",None,"elimtried",
             bracket["novivify.elimtried"]),
        ("default_vs_noelim","default","noelim",None,
             bracket["default_vs_noelim"]),
        ("default_vs_novivify","default","novivify",None,
             bracket["default_vs_novivify"])
    ]
    refined={}
    for label,a,b,key,coarse in selected:
        refined[label]=_refine(c,records,a,b,coarse,key,label)
        print("C8B_REFINED",json.dumps(dict(
            gbd=c["gbd"],kind=label,**refined[label]),sort_keys=True),
            flush=True)
    results=dict(protocol=PROTO,
        source_sha256=c["sha256"],gbd=c["gbd"],
        source_original_SHA_verified=True,
        source_prior_C8_full=42524944723,
        fixed_grid_budgets=list(BUDGETS),
        per_mode_grid={
            mode:[records[mode][k] for k in BUDGETS] for mode in MODES},
        first_coarse_observable=bracket,
        refined_observable_brackets=refined,
        negative_control_noelim_vs_noelim_novivify_all_grid_equal=
            all(same_search(records["noelim"][b],
                            records["noelim_novivify"][b]) is True
                for b in BUDGETS),
        causal_limitations=[
            "Each -c snapshot is a separate fresh solver process",
            "No exact per-variable BVE event order or reason was instrumented",
            "Earliest observed aggregate-counter change is not proof of cause",
            "CaDiCaL --no-elim indirectly affects vivification behavior",
            "No independent solver seeds; source cohort development, not blind"
        ])
    (OUT/("report-shard-%d.json"%index)).write_text(
        json.dumps(results,indent=2,sort_keys=True)+"\n")
    print("C8B_SHARD_PASS",index,len(BUDGETS)*len(MODES),flush=True)
def audit():
    prior=_prior_c8();s=sources()
    rows=[]
    for i,c in enumerate(s):
        f=OUT/("report-shard-%d.json"%i)
        need(f.is_file(),"missing finished source report")
        x=json.loads(f.read_text())
        need(x["source_sha256"]==c["sha256"] and
             x["gbd"]==c["gbd"] and x["protocol"]==PROTO,
             "source SHA mismatch")
        need(x["fixed_grid_budgets"]==list(BUDGETS),
             "budget change after execution")
        for mode in MODES:
            a=x["per_mode_grid"][mode]
            need(len(a)==len(BUDGETS) and
                 [y["cap_conflicts"] for y in a]==list(BUDGETS),
                 "partial mode grid")
            for y in a:
                need(y["source_sha256"]==c["sha256"] and
                     y["mode"]==mode and y["status"] in ("UNKNOWN","SAT"),
                     "missing or contradictory original SHA probe")
                c8.validate_stats(y["counts"],mode)
                need(y["status"]!="SAT" or y["SAT_model_verified"],
                     "SAT model not independently replayed on original CNF")
        for label,b in x["refined_observable_brackets"].items():
            if b["refined"]:
                lower,upper=b["refined"]
                need(lower<upper and upper-lower<=BINARY_PRECISION and
                     b["recheck_passed"],
                     "unverified conflict bracket "+label)
        rows.append(x)
    output=dict(protocol=PROTO,cohort="THREE prior C8 development SAT SHA, NOT blind",
        source_SHA=[c["sha256"] for c in s],
        source_count=len(s),snapshot_count=3*len(MODES)*len(BUDGETS),
        fixed_grid_budgets=list(BUDGETS),
        paired_factorial_modes=list(MODES),
        first_indicator_is_observed_not_proven_cause=True,
        cap_s_per_diagnostic=CAP,
        prior_C8_full_PAR2=prior["scores"],
        prior_C8_full_source_run=42524944723,
        derived_from_prior_C8_without_rerunning_real_E2E=True,
        all_SAT_witnesses_replayed_when_solved=True,
        three_source_results=rows,no_auto_promotion=True)
    (OUT/"report.json").write_text(
        json.dumps(output,indent=2,sort_keys=True)+"\n")
    print("C8B_FINAL",json.dumps(dict(
        protocol=PROTO,sources=len(rows),snapshot_count=output["snapshot_count"],
        first_indicators={x["gbd"]:x["refined_observable_brackets"]
                          for x in rows},
        parity_noelim_novivify={x["gbd"]:
            x["negative_control_noelim_vs_noelim_novivify_all_grid_equal"]
                 for x in rows},
        causal_limit="aggregate counters and fresh process; not a causal proof",
        validated_C8_full_PAR2=True
    ),sort_keys=True),flush=True)
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("verify","smoke","shard","audit"))
    p.add_argument("--shard",type=int,default=0)
    args=p.parse_args()
    if args.action=="verify":
        print("C8B_FROZEN_3SHA_PASS",len(sources()),flush=True)
    elif args.action=="smoke":smoke()
    elif args.action=="shard":shard(args.shard)
    else:audit()
