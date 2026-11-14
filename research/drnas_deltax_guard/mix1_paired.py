#!/usr/bin/env python3
"""DELTAX-GUARD MIX1 paired source-verified research.

New SHA-disjoint synthetic mixed families plus original SAT2024 retrospective
CNFs, using EXACTLY the frozen native DELTAX-GUARD1 executable from the
successful run 43596056826. Each CNF runs four serial modes on one logical
CPU. All credited SAT models satisfy ORIGINAL clauses and all credited
UNSAT results have independently verified original-CNF DRAT.

No speed claims or main promotion; UNKNOWN never becomes SAT/UNSAT evidence.
"""
import argparse,collections,hashlib,json,os,random,sys
from pathlib import Path

R=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(R/"research"))
sys.path.insert(0,str(R/"research/drnas_deltax_guard"))
from drnas_deltax_guard import paired as P
from mix1_sources import write as generate

ARMS=P.ARMS
SHARDS=4
CAP=5.0

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def manifest():
    p=R/"deltax_mix1_inputs/manifest.json"
    rows=json.loads(p.read_text())
    assert len(rows)==32 and len({r["sha256"] for r in rows})==32
    assert sum(r["source_kind"]=="synthetic" for r in rows)==24
    assert sum(r["source_kind"]=="sat2024_retrospective" for r in rows)==8
    for row in rows:
        assert sha((R/row["path"]).read_bytes())==row["sha256"],(
            "MIX_SOURCE_SHA_CHANGED",row["name"])
    return rows,sha(p.read_bytes())

def preflight():
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    rows=generate("deltax_mix1_inputs")
    chosen=[]
    for family in sorted({s["family"] for s in rows}):
        chosen.append(next(s for s in rows if s["family"]==family))
    assert len(chosen)>=7
    records=[]
    for s in chosen:
        for arm in ARMS:
            # Source/model/proof verified by frozen GUARD1 native paired
            # harness. The REAL36 cohort is retrospective, not blind.
            r=P.trial(s,arm,2.0,R/"deltax_mix1_preflight/raw")
            r["source_kind"]=s["source_kind"]
            records.append(r)
    assert len(records)==len(chosen)*len(ARMS)
    status=collections.defaultdict(set)
    for row in records:
        if row["verified"]:
            status[row["sha256"]].add(row["status"])
    assert all(len(v)<=1 for v in status.values()),"CONTRADICTORY_PREFLIGHT_CERTS"
    assert all(r["guard_invalid_source"]==0 and r["guard_clones_inconsistent"]==0
               for r in records),"PREFLIGHT_PROOF_OR_CLONE_SAFETY_ERROR"
    P.save(R/"deltax_mix1_preflight/report.json",{
        "status":"PASS","sources":len(rows),"preflight_sources":len(chosen),
        "preflight_trials":len(records),"verified":sum(r["verified"] for r in records),
        "retrospective_real_sources":8,"new_synthetic_sources":24,
        "source_manifest_sha256":manifest()[1],"one_cpu":True,
        "correctness_checked_original_cnf":True,
        "some_real_timeouts_allowed":True,
        "no_promotion":True})
    P.emit("DELTAX_MIX1_PREFLIGHT_PASS",{
        "sources":len(rows),"preflight_trials":len(records),
        "verified":sum(r["verified"] for r in records)})

def shard(index):
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    rows,checksum=manifest()
    selected=[r for i,r in enumerate(rows) if i%SHARDS==index]
    root=R/f"deltax_mix1_shards/{index}"
    root.mkdir(parents=True,exist_ok=False)
    P.save(root/"manifest.json",{
        "shard":index,"source_manifest_sha256":checksum,
        "arms":ARMS,"cap_s":CAP,
        "binary_sha256":P.sha(P.BINARY),"drat_sha256":P.sha(P.DRAT),
        "one_cpu":sorted(os.sched_getaffinity(0)),
        "synthetic_new_sha_disjoint":True,
        "real_sat2024_retrospective":True,
        "blind_holdout":False,"promotion":False
    })
    with (root/"trials.jsonl").open("w") as f:
        for s in selected:
            arms=list(ARMS)
            random.Random(int(s["sha256"][:16],16)).shuffle(arms)
            for arm in arms:
                result=P.trial(s,arm,CAP,root/"raw")
                result["source_kind"]=s["source_kind"]
                f.write(json.dumps(result,sort_keys=True)+"\n")
                f.flush()
                P.emit("DELTAX_MIX1_TRIAL",{
                    "name":s["name"],"kind":s["source_kind"],
                    "family":s["family"],"arm":arm,
                    "status":result["status"],"verified":result["verified"],
                    "decisions":result["decisions"],"conflicts":result["conflicts"],
                    "guard_checks":result["guard_checks"],
                    "guard_accepted":result["guard_accepted"],
                    "guard_rejected":result["guard_rejected"],
                    "lemmas":result["deltax_lemmas"],
                    "causal_enqueues":result["causal_enqueues"]})
    P.emit("DELTAX_MIX1_SHARD_PASS",{
        "shard":index,"sources":len(selected),"trials":len(selected)*len(ARMS)})

def aggregate():
    sources,checksum=manifest()
    records=[];manifests=[]
    for idx in range(SHARDS):
        root=R/f"deltax_mix1_downloads/deltax-mix1-shard-{idx}/deltax_mix1_shards/{idx}"
        manifests.append(json.loads((root/"manifest.json").read_text()))
        records.extend(json.loads(line) for line in
                       (root/"trials.jsonl").read_text().splitlines())
    expected={(s["sha256"],arm) for s in sources for arm in ARMS}
    actual=[(r["sha256"],r["arm"]) for r in records]
    assert len(records)==128 and len(set(actual))==len(actual) and set(actual)==expected
    for m in manifests:
        assert m["source_manifest_sha256"]==checksum
        assert tuple(m["arms"])==ARMS and m["cap_s"]==CAP
        assert len(m["one_cpu"])==1 and m["one_cpu"]==manifests[0]["one_cpu"]
        assert m["binary_sha256"]==manifests[0]["binary_sha256"]
        assert m["drat_sha256"]==manifests[0]["drat_sha256"]
        assert m["synthetic_new_sha_disjoint"] and m["real_sat2024_retrospective"]
        assert not m["blind_holdout"] and not m["promotion"]
    verdict=collections.defaultdict(set)
    for row in records:
        if row["verified"]:verdict[row["sha256"]].add(row["status"])
        assert row["guard_invalid_source"]==0 and row["guard_clones_inconsistent"]==0,(
            "SOUNDNESS_OR_CLONE_FAILURE",row["source"],row["arm"])
    assert all(len(v)<=1 for v in verdict.values()),"CONTRADICTORY_VERIFIED_VERDICT"
    bykey={(r["sha256"],r["arm"]):r for r in records}
    arms={}
    for arm in ARMS:
        rr=[r for r in records if r["arm"]==arm]
        arms[arm]={
            "trials":len(rr),
            "verified":sum(r["verified"] for r in rr),
            "sat_verified":sum(r["status"]=="SAT_VERIFIED" and r["verified"] for r in rr),
            "unsat_certified":sum(r["status"]=="UNSAT_CERTIFIED" and r["verified"] for r in rr),
            "unknown_or_unverified":sum(not r["verified"] for r in rr),
            "par2_verified_s":round(sum(r["par2_verified_s"] for r in rr),5),
            "decisions_observed_including_timeouts":sum(r["decisions"] or 0 for r in rr),
            "conflicts_observed_including_timeouts":sum(r["conflicts"] or 0 for r in rr),
            "guard_checked":sum(r["guard_checks"] for r in rr),
            "guard_approved":sum(r["guard_accepted"] for r in rr),
            "guard_vetoed":sum(r["guard_rejected"] for r in rr),
            "guard_budget_vetoes":sum(r["guard_budget_rejected"] for r in rr),
            "proof_clauses":sum(r["deltax_lemmas"] for r in rr),
            "causal_enqueues":sum(r["causal_enqueues"] for r in rr),
        }
    paired=[]
    for s in sources:
        rows={a:bykey[(s["sha256"],a)] for a in ARMS}
        comparability=all(rows[a]["verified"] for a in ("join","deltax","deltax-guard"))
        agree=len({rows[a]["status"] for a in ARMS if rows[a]["verified"]})<=1
        assert agree,("DIVERGENT_VERIFIED_VERDICTS",s["name"])
        pair={
            "name":s["name"],"family":s["family"],"kind":s["source_kind"],
            "source_sha256":s["sha256"],"comparable":comparability,
            "status":{a:rows[a]["status"] for a in ARMS},
            "decisions":{a:rows[a]["decisions"] for a in ARMS},
            "conflicts":{a:rows[a]["conflicts"] for a in ARMS},
            "guard_approved":rows["deltax-guard"]["guard_accepted"],
            "guard_vetoed":rows["deltax-guard"]["guard_rejected"],
            "deltax_injected":rows["deltax"]["deltax_lemmas"]
        }
        paired.append(pair)
    comparable=[p for p in paired if p["comparable"]]
    def count(metric,arm,reference,condition="<"):
        return sum(p[metric][arm]<p[metric][reference] if condition=="<"
                   else p[metric][arm]>p[metric][reference]
                   for p in comparable)
    family={}
    for s in sources:
        family.setdefault(s["family"],[]).append(s)
    family_summary={}
    for key,srcs in sorted(family.items()):
        ss={s["sha256"] for s in srcs}
        family_summary[key]={
            "sources":len(srcs),
            "kind":srcs[0]["source_kind"],
            "matched_verified":sum(p["comparable"] and p["source_sha256"] in ss for p in comparable),
            "guard_decision_better_than_join":sum(p["decisions"]["deltax-guard"]<p["decisions"]["join"]
                for p in comparable if p["source_sha256"] in ss),
            "guard_conflict_worse_than_join":sum(p["conflicts"]["deltax-guard"]>p["conflicts"]["join"]
                for p in comparable if p["source_sha256"] in ss),
            "guard_accepted":sum(bykey[(s["sha256"],"deltax-guard")]["guard_accepted"] for s in srcs),
            "guard_vetoed":sum(bykey[(s["sha256"],"deltax-guard")]["guard_rejected"] for s in srcs)
        }
    report={
        "status":"COMPLETE","sources":len(sources),"trials":len(records),
        "new_synthetic_sources":24,"retrospective_real2024_sources":8,
        "synthetic_families":5,
        "source_manifest_sha256":checksum,
        "single_logical_cpu_per_solver":True,"one_repeat":True,
        "source_disjoint_from_prior_hard28_synthetic":True,
        "blind_holdout":False,"solver_unchanged_from_guard1":True,
        "no_promotion":True,"no_general_speed_claim":True,
        "verified_only_compare":True,
        "arms":arms,"matched_all_three":len(comparable),
        "guard_decision_better_vs_join":count("decisions","deltax-guard","join"),
        "guard_decision_worse_vs_join":count("decisions","deltax-guard","join",">"),
        "guard_conflict_better_vs_join":count("conflicts","deltax-guard","join"),
        "guard_conflict_worse_vs_join":count("conflicts","deltax-guard","join",">"),
        "guard_conflict_better_vs_unguarded":count("conflicts","deltax-guard","deltax"),
        "guard_conflict_worse_vs_unguarded":count("conflicts","deltax-guard","deltax",">"),
        "family_summary":family_summary,"pairs":paired
    }
    P.save(R/"deltax_mix1_final/report.json",report)
    P.save(R/"deltax_mix1_final/trials.json",records)
    P.emit("DELTAX_MIX1_FINAL",{k:v for k,v in report.items() if k!="pairs"})

def main():
    p=argparse.ArgumentParser()
    p.add_argument("stage",choices=("preflight","shard","aggregate"))
    p.add_argument("--shard",type=int,default=0)
    args=p.parse_args()
    if args.stage=="preflight":preflight()
    elif args.stage=="shard":shard(args.shard)
    else:aggregate()

if __name__=="__main__":main()
