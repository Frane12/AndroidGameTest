#!/usr/bin/env python3
"""MIXAB6 top-two router confirmation on eight prospective official CNFs.
Five independent variants, 3 repetitions, 4 source shards x 5 arms,
12s E2E, 1 logical CPU per solver. Original SAT models and independent
original DRAT/LRAT or exact GF2 certificates; no two-core portfolio.

PRESELECTION NOTE: fresh sources are CaDiCaL-4s reference-easy screened
and hence NOT globally blind; no candidate arm used in selection.
"""
from __future__ import annotations
import argparse,collections,hashlib,json,os,pathlib,time
import drnas_mixab4_easy_lrat as ab4

ROOT=pathlib.Path("mre_mixab6")
SRC=ROOT/"cases"
PROTO="DRNAS-MIXAB6-BEST5-NEW8-3REPS-12S-ORIGINAL-CNF-1CPU-v1"
ARMS=("combo_budget","router_clauses","cms_plain","kissat_plain","combo_budget_placebo")
N=8
REPS=3
SHARDS=4
CAP=12.0
EXPECTED=N*REPS*len(ARMS)
PREV="mre_mixab4/manifest.json"

# Keep exactly one proven source selector and original-CNF backend; install
# new immutable experiment context BEFORE invoking either implementation.
ab4.ROOT=ROOT
ab4.SOURCE=SRC
ab4.e9.SOURCE=SRC
ab4.N=N
ab4.REPS=REPS
ab4.SHARDS=SHARDS
ab4.CAP=CAP
ab4.ARMS=ARMS
ab4.EXPECTED=EXPECTED
ab4.PROTO=PROTO
ab4.YEARS=("2024","2025","2023","2022","2021")
ab4.SALT="MIXAB6-20261110-NEW8-REFERENCE-EASY-CADICAL-ONLY-FROZEN"
# Pilot reached seven accepted source-only originals in 240 frozen candidates.
# Expand only the metadata/reference-selection search budget, not benchmark arms.
ab4.MAX_CANDIDATES=400
ab4.PRIOR_PATHS=tuple(ab4.PRIOR_PATHS)+(PREV,)
ab4.s2.REPS=max(ab4.s2.REPS,REPS)
ab4.e9.REPS=max(ab4.e9.REPS,REPS)

def need(cond,msg):
    if not cond:raise RuntimeError("MIXAB6_FAIL_CLOSED "+msg)
def save(path,data):
    path=pathlib.Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,sort_keys=True,indent=2)+"\n")
def load(path):return json.loads(pathlib.Path(path).read_text())
def code_sha():return ab4.sha(__file__)

def verify():
    m=ab4.verify()
    need(len(m["original_cases"])==N and m["trials"]==EXPECTED
         and m["arms"]==list(ARMS) and m["reps"]==REPS and m["shards"]==SHARDS
         and m["cap_s"]==CAP and m["protocol"]==PROTO
         and m["wrapper_sha256"]==code_sha()
         and m["reference_only_selection_biased"] is True,
         "frozen program or cohort changed")
    former=load(PREV)
    seen_sha={c["sha256"] for c in former["original_cases"]}
    seen_gbd={c["gbd"] for c in former["original_cases"]}
    need(not any(c["sha256"] in seen_sha or c["gbd"] in seen_gbd
                 for c in m["original_cases"]),"MIXAB4 original reused")
    return m

def freeze():
    need(pathlib.Path(PREV).is_file(),"missing MIXAB4 exclusion registry")
    ROOT.mkdir(parents=True,exist_ok=True)
    ab4.selftest()
    ab4.freeze()
    m=load(ROOT/"manifest.json")
    m["wrapper_sha256"]=code_sha()
    m["candidate_arms_precommitted"]=list(ARMS)
    m["selection_includes_reference_only_cadical_4s"]=True
    m["any_selected_original_from_previous_mixab4"]=False
    m["original_source_replay_strict"]=True
    m["one_logical_cpu_per_trial"]=True
    m["no_auto_promotion"]=True
    save(ROOT/"manifest.json",m)
    verify()
    print("MIXAB6_FROZEN "+json.dumps(dict(original_SHA=N,
        arms=len(ARMS),repetitions=REPS,trials=EXPECTED,
        independently_proven_UNSAT_sources=sum(
          bool(c["independent_lrat_proof_file"]) for c in m["original_cases"]),
        globally_blind=False,one_CPU=True),sort_keys=True),flush=True)

def trial(c,rep,arm):
    need(arm in ARMS and 0<=rep<REPS,"unknown candidate arm/rep")
    cpu=min(os.sched_getaffinity(0))
    os.sched_setaffinity(0,{cpu})
    t=time.perf_counter()
    pc0=time.process_time()
    child0=ab4.e9.x22.child_cpu()
    src=ab4.source(c)
    state=None;backend_called=False
    route="reference_only" if arm in ("cms_plain","kissat_plain") else "precommitted"
    if arm=="cms_plain":
        selected="cms"
    elif arm=="kissat_plain":
        selected="kissat"
    elif arm=="router_clauses":
        selected="cms" if c["clauses"]<=15000 else "kissat"
        route="frozen_clauses_le_15000_to_CMS"
    else:
        if ab4.shape_gate(c):
            state=ab4.budget_scan(src)
        selected="cms" if state and state["equations"]>=ab4.XOR_ROUTE_MIN else "kissat"
        route="complete_GF2_equations_ge_16_to_CMS"
    proved=bool(state and state["proved"])
    shortcut=proved and arm=="combo_budget"
    outcome="UNSAT" if shortcut else "TIMEOUT"
    witness=False;backend_status=None
    if not shortcut:
        left=CAP-(time.perf_counter()-t)
        if left>0.08:
            backend_called=True
            res=ab4.backend(c,rep,selected,left)
            outcome=res["status"]
            witness=res["SAT_original_witness_verified"]
            backend_status=res["status"]
    wall=time.perf_counter()-t
    if wall>=CAP:
        outcome="TIMEOUT";witness=False
    need(wall<=CAP+.25,"wall time beyond cap tolerance")
    need(outcome!="SAT" or witness,"SAT witness not checked on original")
    need(ab4.sha(src)==c["sha256"],"original CNF mutated")
    return dict(protocol=PROTO,sha256=c["sha256"],gbd=c["gbd"],
      rep=rep,arm=arm,cap_s=CAP,shard=-1,
      one_logical_CPU=True,pinned_logical_cpu=cpu,
      original_SHA_verified=True,one_solver_child_max=True,
      SAT_original_witness_verified=bool(witness if outcome=="SAT" else False),
      UNSAT_independent_GF2_certificate_verified=bool(shortcut),
      GF2_full_original_proof_validated=proved,
      UNSAT_independent_LRAT_emitted_by_compared_arm=False,
      status=outcome,selected_backend=selected,
      source_only_router=route,backend_called=backend_called,
      backend_status=backend_status,
      GF2_equations=state["equations"] if state else 0,
      GF2_scan_abstained=state["abstained"] if state else False,
      GF2_scan_s=state["probe_wall_s"] if state else 0,
      wall_E2E_s=round(wall,6),
      parent_CPU_s=round(time.process_time()-pc0,6),
      child_CPU_s=round(ab4.e9.x22.child_cpu()-child0,6))

def shard(idx,arm):
    m=verify()
    need(idx in range(SHARDS) and arm in ARMS,"matrix identity invalid")
    cs=[c for i,c in enumerate(m["original_cases"]) if i%SHARDS==idx]
    need(len(cs)==N//SHARDS,"source shard count")
    rows=[]
    for c in cs:
        for rep in range(REPS):
            x=trial(c,rep,arm);x["shard"]=idx
            rows.append(x)
            save(ROOT/f"shard-{idx}-{arm}.json",rows)
            print("MIXAB6_TRIAL "+json.dumps(x,sort_keys=True),flush=True)
    need(len(rows)==6,"expected 2 original SHA x 3 paired repetitions")
    print(f"MIXAB6_SHARD_PASS {idx} {arm} 6",flush=True)

def audit():
    m=verify()
    rows=[]
    for idx in range(SHARDS):
        for arm in ARMS:
            group=load(ROOT/f"shard-{idx}-{arm}.json")
            need(len(group)==6,"missing full arm-shard output")
            rows+=group
    expected={(c["sha256"],r,a) for c in m["original_cases"]
              for r in range(REPS) for a in ARMS}
    seen={(x["sha256"],x["rep"],x["arm"]) for x in rows}
    need(len(rows)==len(seen)==EXPECTED and seen==expected,
         "incomplete/double experimental paired matrix")
    proofed={c["sha256"] for c in m["original_cases"]
             if c["independent_lrat_proof_file"]}
    math={x["sha256"] for x in rows
          if x["UNSAT_independent_GF2_certificate_verified"]}
    answers=collections.defaultdict(set)
    for x in rows:
        need(x["protocol"]==PROTO and x["one_logical_CPU"]
             and x["original_SHA_verified"] and x["one_solver_child_max"]
             and x["cap_s"]==CAP and x["status"] in ("SAT","UNSAT","TIMEOUT")
             and 0<=x["wall_E2E_s"]<=CAP+.25
             and (x["status"]!="SAT" or x["SAT_original_witness_verified"]),
             "trial validation failure")
        if x["status"]!="TIMEOUT":answers[x["sha256"]].add(x["status"])
    need(all(len(v)<=1 for v in answers.values()),"contradictory original CNF answers")
    def accepted(x):
        return (x["status"]=="SAT" and x["SAT_original_witness_verified"]) or (
            x["status"]=="UNSAT" and x["sha256"] in proofed|math)
    def penalty(x):return x["wall_E2E_s"] if accepted(x) else 2*CAP
    def score(rr):
        return dict(runs=len(rr),solved=sum(accepted(x) for x in rr),
           verified_SAT=sum(x["status"]=="SAT" and accepted(x) for x in rr),
           original_DRAT_LRAT_verified_UNSAT=sum(
             x["status"]=="UNSAT" and x["sha256"] in proofed for x in rr),
           direct_GF2_UNSAT=sum(x["UNSAT_independent_GF2_certificate_verified"] for x in rr),
           unverified_UNSAT=sum(x["status"]=="UNSAT" and not accepted(x) for x in rr),
           timeouts=sum(x["status"]=="TIMEOUT" for x in rr),
           PAR2_s=round(sum(penalty(x) for x in rr),6),
           wall_s=round(sum(x["wall_E2E_s"] for x in rr),6),
           total_CPU_s=round(sum(x["parent_CPU_s"]+x["child_CPU_s"] for x in rr),6),
           scanned_Gf2_s=round(sum(x["GF2_scan_s"] for x in rr),6),
           cms_chosen=sum(x["selected_backend"]=="cms" for x in rr))
    keyed={(x["sha256"],x["rep"],x["arm"]):x for x in rows}
    def compare(a,b):
        diff=[penalty(keyed[(c["sha256"],rep,a)])-
              penalty(keyed[(c["sha256"],rep,b)])
              for c in m["original_cases"] for rep in range(REPS)]
        return dict(wins=sum(v<-.02 for v in diff),
            losses=sum(v>.02 for v in diff),ties=sum(abs(v)<=.02 for v in diff),
            net_PAR2_gain_s=round(-sum(diff),6),
            largest_positive_gain_s=round(-min(diff),6),
            largest_regression_s=round(max(diff),6))
    scores={a:score([x for x in rows if x["arm"]==a]) for a in ARMS}
    for a in ARMS:
        scores[a]["speedup_vs_CMS_PAR2_x"]=round(
             scores["cms_plain"]["PAR2_s"]/scores[a]["PAR2_s"],6)
        scores[a]["speedup_vs_Kissat_PAR2_x"]=round(
             scores["kissat_plain"]["PAR2_s"]/scores[a]["PAR2_s"],6)
    report=dict(protocol=PROTO,source_cases=N,attempts=EXPECTED,
        repetitions=REPS,source_new_to_loaded_prior_registries=True,
        globally_blind=False,reference_CaDiCaL_selection_biased=True,
        one_logical_cpu=True,no_parallel_solver_children=True,
        independent_original_UNSAT_DRAT_LRAT_source_SHA=sorted(proofed),
        independent_Gf2_original_UNSAT_source_SHA=sorted(math),
        original_SAT_witness_strict=True,no_auto_promotion=True,
        scores=scores,
        paired_vs_CMS={a:compare(a,"cms_plain") for a in ARMS if a!="cms_plain"},
        paired_vs_Kissat={a:compare(a,"kissat_plain") for a in ARMS if a!="kissat_plain"},
        combo_vs_placebo=compare("combo_budget","combo_budget_placebo"),
        combo_vs_router=compare("combo_budget","router_clauses"),
        per_shard={str(i):{a:score([x for x in rows if x["arm"]==a
            and x["shard"]==i]) for a in ARMS} for i in range(SHARDS)})
    save(ROOT/"report.json",report)
    print("MIXAB6_FINAL "+json.dumps(report,sort_keys=True),flush=True)

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("action",choices=("freeze","verify","shard","audit"))
    parser.add_argument("--shard",type=int,default=0)
    parser.add_argument("--arm",default=ARMS[0],choices=ARMS)
    args=parser.parse_args()
    if args.action=="shard":shard(args.shard,args.arm)
    else:
        globals()[args.action]()
        if args.action=="verify":print("MIXAB6_VERIFY_PASS",flush=True)
