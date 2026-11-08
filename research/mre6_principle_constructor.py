#!/usr/bin/env python3
"""DRNAS MRE6 CPU feedback -> *mathematical research hypotheses* constructor.

Consumes completed SHA-pinned SQLite evidence; proposes which mathematical
representation interactions deserve future source-disjoint validation.
It does NOT activate candidates on unseen formulas and never uses target
runtime CPU to make an online solver choice.
"""
from __future__ import annotations
import argparse,collections,hashlib,json,pathlib,sqlite3,statistics

PROTO="DRNAS-MRE6-CPU-FEEDBACK-PRINCIPLE-CONSTRUCTOR-v1"
PRINCIPLE_FORMS={
 "a":("proof_certified_binary_implication","single implication A"),
 "b":("proof_certified_binary_implication","single implication B"),
 "both":("proof_certified_equivalence","two cooperating watched binary implications A+B"),
 "quotient":("proof_certified_equivalence_quotient","quotient b:=a with transported GF2 source XORs"),
 "quotient_no_xor":("proof_certified_equivalence_quotient","quotient b:=a; do not import certified source XOR rows"),
}
MIN_SOURCE_DISJOINT=3

def need(ok,msg):
    if not ok:raise RuntimeError("MRE6_CONSTRUCTOR_FAIL_CLOSED "+str(msg))

def generate(db_path,out):
    conn=sqlite3.connect(db_path)
    known={x[0] for x in conn.execute(
        "SELECT DISTINCT source_sha256 FROM observation WHERE split='holdout_seed_only'")}
    need(len(known)>=1,"missing original holdout CPU labels")
    pairs=conn.execute("""SELECT source_sha256,seed,
       cpu_interaction_s,quotient_benefit_no_xor_s,quotient_benefit_with_xor_s
       FROM quotient_xor_interaction ORDER BY source_sha256,seed""") if False else None
    # SQLite factorial ledger has one row per (source, seed, repeat)
    interaction=conn.execute("""SELECT source_sha256,seed,repeat,
       cpu_interaction_s,quotient_benefit_no_xor_s,quotient_benefit_with_xor_s
       FROM quotient_xor_interaction ORDER BY source_sha256,seed,repeat""").fetchall()
    need(len(interaction)>=8 and len({(x[1],x[2]) for x in interaction})>=8,
         "factorial CPU interaction not independently audited")
    hypotheses=[]
    for mode,(kind,label) in PRINCIPLE_FORMS.items():
        obs=conn.execute("""SELECT source_sha256,seed,cpu_saved_pct,
          watcher_pressure_pct,decision_savings_pct
          FROM cpu_feedback WHERE split='holdout_seed_only'
          AND principle_code=? ORDER BY seed""",(mode,)).fetchall()
        need(len(obs)>=4,"principle CPU label missing: "+mode)
        seed_cpu=collections.defaultdict(list)
        seed_watch=collections.defaultdict(list)
        for sha,seed,cpu,watch,dec in obs:
            seed_cpu[(sha,seed)].append(float(cpu))
            if watch is not None:seed_watch[(sha,seed)].append(float(watch))
        vals=[statistics.mean(x) for x in seed_cpu.values()]
        watch=[statistics.mean(x) for x in seed_watch.values()]
        source_count=len({sha for sha,seed in seed_cpu})
        wins=sum(v>0 for v in vals)
        label_state=("promising_for_new_source_validation"
               if wins==len(vals) and statistics.mean(vals)>3 else
               "regressive_or_seed_inconsistent")
        if mode=="quotient_no_xor":
            # Joint evidence must show the representation×XOR interaction,
            # not merely faster time relative to the XOR baseline.
            signed=[x[3] for x in interaction]
            need(all(x<0 for x in signed),"unexpected reversal in quotient/XOR interaction")
        else:signed=[]
        rec=dict(
           principle_code=mode,kind=kind,description=label,
           observed_formula_sources=source_count,
           distinct_seed_cases=len(vals),
           mean_native_cpu_saved_pct=round(statistics.mean(vals),4),
           worst_seed_native_cpu_saved_pct=round(min(vals),4),
           paired_seed_wins=wins,
           mean_global_watcher_pressure_pct=(
              round(statistics.mean(watch),4) if watch else None),
           representation_xor_interaction_mean_s=(
              round(statistics.mean(signed),6) if signed else None),
           observed_state=label_state,
           deployable_on_unseen_SAT=False,
           reason="only_one_reused_source_no_source_disjoint_validation")
        rec["hypothesis_id"]=hashlib.sha256(json.dumps(
             {"proto":PROTO,"kind":kind,"mode":mode,
              "formula_sha_set":sorted(known)},sort_keys=True).encode()
              ).hexdigest()
        hypotheses.append(rec)
    hypotheses.sort(key=lambda h:(h["paired_seed_wins"],
            h["worst_seed_native_cpu_saved_pct"],
            h["mean_native_cpu_saved_pct"]),reverse=True)
    outdata=dict(protocol=PROTO,source_count=len(known),
         minimum_source_disjoint_for_online_promotion=MIN_SOURCE_DISJOINT,
         all_hypotheses_sandbox_only=True,
         frozen_online_policy="xor",
         proposed_mathematical_interaction_rule=(
            "Use certified equivalence quotient with optional suppression "
            "of redundant imported source XOR; accept only after source-disjoint CPU proof"),
         numerical_feedback_is_offline_not_a_runtime_oracle=True,
         hypotheses=hypotheses)
    pathlib.Path(out).parent.mkdir(parents=True,exist_ok=True)
    pathlib.Path(out).write_text(json.dumps(outdata,indent=2,sort_keys=True)+"\n")
    conn.execute("""CREATE TABLE IF NOT EXISTS generated_principle_hypothesis(
       hypothesis_id TEXT PRIMARY KEY,principle_code TEXT NOT NULL,
       description TEXT NOT NULL,mean_cpu_saved_pct REAL NOT NULL,
       worst_seed_cpu_saved_pct REAL NOT NULL,observed_seed_wins INTEGER NOT NULL,
       observed_seed_cases INTEGER NOT NULL,training_source_count INTEGER NOT NULL,
       deployable INTEGER NOT NULL,provenance TEXT NOT NULL)""")
    for x in hypotheses:
        conn.execute("INSERT OR REPLACE INTO generated_principle_hypothesis VALUES (?,?,?,?,?,?,?,?,?,?)",
          (x["hypothesis_id"],x["principle_code"],x["description"],
           x["mean_native_cpu_saved_pct"],x["worst_seed_native_cpu_saved_pct"],
           x["paired_seed_wins"],x["distinct_seed_cases"],
           x["observed_formula_sources"],0,PROTO))
    conn.commit()
    conn.close()
    print("MRE6_PRINCIPLES_CONSTRUCTED",json.dumps(outdata,sort_keys=True),flush=True)

def selftest():
    need(MIN_SOURCE_DISJOINT>=3 and len(PRINCIPLE_FORMS)==5,
         "unsafe principle learning config")
    print("MRE6_CONSTRUCTOR_SELFTEST_PASS",PROTO,flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("selftest","generate"))
    p.add_argument("--db",default="mre6/principles.sqlite")
    p.add_argument("--out",default="mre6/generated_principles.json")
    args=p.parse_args()
    if args.action=="selftest":selftest()
    else:generate(args.db,args.out)
