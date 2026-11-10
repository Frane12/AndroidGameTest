#!/usr/bin/env python3
"""DRNAS MIXAB5: ten preregistered router arms executed as independent Actions jobs.

Mechanism pilot on the six ALREADY SEEN MIXAB4 original CNFs, not a blind holdout.
All routes are deterministic source-metadata rules, before any CDCL call; strict
one logical CPU per arm, no multi-solver portfolios. Original SAT witnesses
are checked by MIXAB4; original UNSAT has independently replayed DRAT+LRAT
certificates in the frozen source artifact. Reusing prior certificates does NOT
mean each solver emitted its own proof; no promotion from this pilot.
"""
from __future__ import annotations
import argparse, collections, hashlib, json, os, pathlib, time
import drnas_mixab4_easy_lrat as ab4

ROOT=pathlib.Path("mre_mixab5")
PROTO="DRNAS-MIXAB5-SEEN6-10ARM-PARALLEL-SHARDED-1CPU-12S-PILOT-v1"
ARMS=("cms_plain","kissat_plain","combo_budget","combo_budget_placebo",
      "router_vars","router_bytes","router_dense","router_sparse",
      "router_clauses","router_union")
REPS=2
SHARDS=3
CAP=12.0
EXPECTED=6*REPS*len(ARMS)
BASELINE=ARMS[:4]

def need(ok,what):
    if not ok:raise RuntimeError("MIXAB5_FAIL_CLOSED "+what)
def sha(path):return ab4.sha(path)
def load(path):return json.loads(pathlib.Path(path).read_text())
def save(path,data):
    path=pathlib.Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,indent=2,sort_keys=True)+"\n")
def signature():
    return dict(code_sha=sha(__file__),
       predecessor_code_sha=sha("research/drnas_mixab4_easy_lrat.py"),
       predecessor_manifest_sha=sha(ab4.ROOT/"manifest.json"),
       cms_sha=sha(ab4.CMS),kissat_sha=sha(ab4.e9.KISSAT),
       gf2_sha=sha(ab4.gf.BIN),external_drat_sha=sha(ab4.DRAT),
       external_lrat_sha=sha(ab4.CHECKER))
def select_router(arm,c):
    n=int(c["vars"]);k=int(c["clauses"]);b=int(c["bytes"])
    need(n>0 and k>0 and b>0,"source-only routing metadata absent")
    if arm=="router_vars":flag=n<=1500
    elif arm=="router_bytes":flag=b<=1024*1024
    elif arm=="router_dense":flag=k>=6*n
    elif arm=="router_sparse":flag=k<=4*n
    elif arm=="router_clauses":flag=k<=15000
    elif arm=="router_union":flag=(n<=1500 or k>=8*n)
    else:raise RuntimeError("unknown preregistered router "+arm)
    return ("cms_plain" if flag else "kissat_plain"),dict(
      variables=n,clauses=k,bytes=b,clauses_per_var=round(k/n,5),
      decision="CMS" if flag else "Kissat",selection="source_only_frozen_rule")

def freeze():
    previous=ab4.verify()
    need(previous["source_count"]==6,"MIXAB4 six originals missing")
    need(tuple(ab4.ARMS)==("kissat_plain","cms_plain","gf2_budget_kissat",
         "combo_full","combo_budget","combo_budget_placebo"),
         "prior candidate interfaces changed")
    cs=sorted(previous["original_cases"],key=lambda c:c["sha256"])
    need(len({c["sha256"] for c in cs})==6,"duplicate original SHA")
    m=dict(protocol=PROTO,arms=list(ARMS),sources=6,reps=REPS,
      shards=SHARDS,cap_s=CAP,trials=EXPECTED,
      source_cases=cs,signatures=signature(),
      prior_MIXAB4_same_originals=True,not_globally_blind=True,
      no_automatic_production_promotion=True,one_logical_CPU_per_arm=True,
      independent_actions_matrix_per_arm=True,one_solver_child_at_a_time=True,
      external_reference_certificates_not_emitted_by_compared_solver=True,
      routing_rules_preregistered={
          "router_vars":"CMS iff vars <= 1500",
          "router_bytes":"CMS iff bytes <= 1 MiB",
          "router_dense":"CMS iff clauses >= 6*vars",
          "router_sparse":"CMS iff clauses <= 4*vars",
          "router_clauses":"CMS iff clauses <= 15000",
          "router_union":"CMS iff vars <= 1500 or clauses >= 8*vars"})
    save(ROOT/"manifest.json",m)
    verify()
    print("MIXAB5_FROZEN "+json.dumps(dict(sources=6,arms=len(ARMS),
         trials=EXPECTED,source_seen=True,parallel_matrix=True),sort_keys=True),flush=True)

def verify():
    m=load(ROOT/"manifest.json")
    old=ab4.verify()
    need(m["protocol"]==PROTO and m["arms"]==list(ARMS)
         and m["source_cases"]==sorted(old["original_cases"],key=lambda c:c["sha256"])
         and m["sources"]==6 and m["reps"]==REPS and m["shards"]==SHARDS
         and m["cap_s"]==CAP and m["trials"]==EXPECTED
         and m["signatures"]==signature(),"manifests/protocol/bin SHA drift")
    for c in m["source_cases"]:ab4.source(c)
    return m

def trial(c,rep,arm):
    need(arm in ARMS and rep in range(REPS),"bad test arm/rep")
    t=time.perf_counter()
    if arm in BASELINE:
        base=arm;route=dict(decision="direct_or_prior_combo",selection="precommitted")
    else:
        base,route=select_router(arm,c)
    answer=ab4.one(c,rep,base)
    e=time.perf_counter()-t
    need(e<=CAP+.25,"end-to-end wall cap exceeded")
    need(answer["original_SHA_verified"] and answer["one_solver_child_max"]
         and answer["status"] in ("SAT","UNSAT","TIMEOUT"),
         "original SHA or one-CPU execution fail")
    need(answer["status"]!="SAT" or answer["SAT_original_witness_verified"],
         "invalid original SAT witness")
    answer.update(protocol=PROTO,arm=arm,selected_by_route=base,
         route_detail=route,wall_E2E_s=round(e,6),
         source_previously_benchmarked=True)
    return answer

def shard(index,arm):
    m=verify()
    need(index in range(SHARDS) and arm in ARMS,"invalid matrix identity")
    cases=[c for i,c in enumerate(m["source_cases"]) if i%SHARDS==index]
    need(len(cases)==2,"unbalanced shard")
    rows=[]
    for c in cases:
        for rep in range(REPS):
            result=trial(c,rep,arm)
            result["shard"]=index
            rows.append(result)
            save(ROOT/f"shard-{index}-{arm}.json",rows)
            print("MIXAB5_TRIAL "+json.dumps(result,sort_keys=True),flush=True)
    need(len(rows)==4,"shard incomplete")
    print(f"MIXAB5_SHARD_PASS {index} {arm} 4",flush=True)

def audit():
    m=verify()
    rows=[]
    for i in range(SHARDS):
        for arm in ARMS:
            rs=load(ROOT/f"shard-{i}-{arm}.json")
            need(len(rs)==4,"missing/incomplete shard/arm")
            rows.extend(rs)
    expected={(c["sha256"],r,a) for c in m["source_cases"]
              for r in range(REPS) for a in ARMS}
    actual={(x["sha256"],x["rep"],x["arm"]) for x in rows}
    need(len(rows)==len(actual)==EXPECTED and actual==expected,
         "missing, repeated or unknown arm/rep/original SHA")
    externally_verified={c["sha256"] for c in m["source_cases"]
         if c["independent_lrat_proof_file"]}
    math={x["sha256"] for x in rows
         if x["UNSAT_independent_GF2_certificate_verified"]}
    for x in rows:
        need(x["protocol"]==PROTO and x["original_SHA_verified"]
           and x["one_solver_child_max"] and x["cap_s"]==CAP
           and 0<=x["wall_E2E_s"]<=CAP+.25
           and x["status"] in ("SAT","UNSAT","TIMEOUT")
           and (x["status"]!="SAT" or x["SAT_original_witness_verified"]),
           "invalid result or budget")
    for c in m["source_cases"]:
        outcomes={x["status"] for x in rows if x["sha256"]==c["sha256"]
              and x["status"]!="TIMEOUT"}
        need(len(outcomes)<=1,"SAT vs UNSAT conflict on identical original")
    def accepted(x):
        return (x["status"]=="SAT" and x["SAT_original_witness_verified"]) or (
          x["status"]=="UNSAT" and x["sha256"] in externally_verified|math)
    def penalty(x):return x["wall_E2E_s"] if accepted(x) else 2*CAP
    def scores(data):
        return dict(attempts=len(data),solved=sum(accepted(x) for x in data),
          SAT_verified=sum(x["status"]=="SAT" and accepted(x) for x in data),
          UNSAT_external_DRAT_LRAT=sum(x["status"]=="UNSAT"
            and x["sha256"] in externally_verified for x in data),
          UNSAT_mathematical_GF2=sum(x["UNSAT_independent_GF2_certificate_verified"]
                                  for x in data),
          UNSAT_unverified=sum(x["status"]=="UNSAT" and not accepted(x) for x in data),
          timeouts=sum(x["status"]=="TIMEOUT" for x in data),
          PAR2_s=round(sum(penalty(x) for x in data),6),
          wall_s=round(sum(x["wall_E2E_s"] for x in data),6),
          route_cms=sum(x["selected_backend"]=="cms" for x in data))
    keyed={(x["sha256"],x["rep"],x["arm"]):x for x in rows}
    def compare(a,b):
        diffs=[penalty(keyed[(c["sha256"],r,a)])-
              penalty(keyed[(c["sha256"],r,b)])
             for c in m["source_cases"] for r in range(REPS)]
        return dict(wins=sum(d<-.02 for d in diffs),
           losses=sum(d>.02 for d in diffs),ties=sum(abs(d)<=.02 for d in diffs),
           net_PAR2_gain_s=round(-sum(diffs),6),
           worst_regression_s=round(max(diffs),6),
           best_gain_s=round(min(diffs),6))
    total={a:scores([x for x in rows if x["arm"]==a]) for a in ARMS}
    for a in ARMS:
        total[a]["speedup_vs_CMS_PAR2_x"]=round(
            total["cms_plain"]["PAR2_s"]/total[a]["PAR2_s"],6)
        total[a]["speedup_vs_Kissat_PAR2_x"]=round(
            total["kissat_plain"]["PAR2_s"]/total[a]["PAR2_s"],6)
    report=dict(protocol=PROTO,source_count=6,trials=EXPECTED,
      source_already_seen=True,globally_blind=False,one_logical_CPU=True,
      no_parallel_solver_children=True,
      reference_certificates_not_own_solver_proofs=True,
      strict_original_SAT_witness=True,
      independent_external_original_UNSAT_DRAT_LRAT_SHA=sorted(externally_verified),
      direct_GF2_proof_SHA=sorted(math),scores=total,
      paired_vs_CMS={a:compare(a,"cms_plain") for a in ARMS if a!="cms_plain"},
      paired_vs_Kissat={a:compare(a,"kissat_plain") for a in ARMS if a!="kissat_plain"},
      causal_combo_vs_placebo=compare("combo_budget","combo_budget_placebo"),
      per_shard={str(i):{a:scores([x for x in rows if x["arm"]==a
                 and x["shard"]==i]) for a in ARMS} for i in range(SHARDS)})
    save(ROOT/"report.json",report)
    print("MIXAB5_FINAL "+json.dumps(report,sort_keys=True),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("freeze","verify","shard","audit"))
    p.add_argument("--shard",type=int,default=0)
    p.add_argument("--arm",type=str,default=ARMS[0])
    args=p.parse_args()
    if args.action=="shard":shard(args.shard,args.arm)
    else:
        globals()[args.action]()
        if args.action=="verify":print("MIXAB5_VERIFY_PASS",flush=True)
