#!/usr/bin/env python3
"""DRNAS EQUIV10M5: salvage ALL 5 exact SHA originals from failed EQUIV10M
reference-conditioned source-only screen. No source replacement or re-selection.
Independent one-CPU, 15s E2E benchmark, matched 5 arms x 2 seeds, strict PAR2.
SAT witness replay on original. UNSAT accepted only with independent original
Kissat + CaDiCaL 3.0.1 agreement (NO independent LRAT). Not globally blind.
"""
from __future__ import annotations
import argparse,collections,hashlib,json,os,pathlib,random,sys
import drnas_equiv9_prospective_seed_holdout as e9

ROOT=pathlib.Path("mre_equiv10m5")
SOURCE=pathlib.Path("mre_equiv10medium/manifest.json")
PROTO="DRNAS-EQUIV10M5-FROZEN-FIVE-SHA-SALVAGE-50E2E-v1"
ORIGINAL_PROTO="DRNAS-EQUIV10M-REFERENCE-CONDITIONED-NEW-8SHA-ONECPU-v1"
ARMS=("native1","native_altseed","native_split4","kissat1","cadical301_default")
CAP=15.0
REPS=2
SHARDS=5
COUNT=5
EXPECTED_BANDS={"easy":1,"medium":4}
ORIGINAL_SCRIPT=pathlib.Path("research/drnas_equiv10_reference_medium.py")

def need(ok,message):
    if not ok:raise RuntimeError("EQUIV10M5_FAIL_CLOSED "+str(message))
def dump(p,obj):
    p=pathlib.Path(p)
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(obj,indent=2,sort_keys=True)+"\n")
def load():
    e9.verify()
    m=json.loads(SOURCE.read_text())
    need(m["protocol"]==ORIGINAL_PROTO,"original EQUIV10M manifest drift")
    need(m["expected_cases"]==8 and m["original_source_count"]==COUNT and
        len(m["cases"])==COUNT and m["band_counts"]==EXPECTED_BANDS,
        "must use exact five selected SHA, original 4/4 failed screen")
    need(m["expected_trials"]==80 and m["reps"]==2 and m["caps_s"]==CAP,
        "frozen reference protocol changed")
    need(m["code_sha"]==e9.digest(ORIGINAL_SCRIPT) and
        m["prior_E9_manifest_sha"]==e9.digest(e9.ROOT/"manifest.json") and
        m["reference_solver_sha"]==e9.digest(e9.KISSAT),
        "historic code, manifest or Kissat SHA does not match")
    need(len(m["selection_trace"])==m["attempted"]==280,
        "cannot verify complete reference screening")
    ready=[x for x in m["selection_trace"] if x.get("reason")=="READY"]
    need(len(ready)==COUNT,"five READY entries are not exact screening cohort")
    need({x["sha256"] for x in ready}=={x["sha256"] for x in m["cases"]},
        "READY selection changed or missing")
    need(len({x["sha256"] for x in m["cases"]})==COUNT,"duplicate original SHA")
    for c in m["cases"]:
        src=e9.SOURCE/c["filename"]
        need(src.is_file() and e9.digest(src)==c["sha256"],
             "exact original CNF SHA drift "+c["sha256"])
        need(c["reference_band"] in EXPECTED_BANDS and
             c["reference_status"] in ("SAT","UNSAT"),"bad reference-only selection")
    need(collections.Counter(c["reference_band"] for c in m["cases"])==EXPECTED_BANDS,
         "grade mismatch")
    return m

def selftest():
    need(set(ARMS)<=set(e9.ARMS),"unknown solver arm")
    need(COUNT==SHARDS,"each shard must own one SHA")
    print("EQUIV10M5_SELFTEST_PASS",COUNT,len(ARMS),flush=True)

def freeze():
    src=load()
    root=ROOT
    root.mkdir(parents=True,exist_ok=True)
    m=dict(protocol=PROTO,source_protocol=ORIGINAL_PROTO,
        source_manifest_sha256=e9.digest(SOURCE),
        source_selection_reference_only=True,
        source_original_screen_failed_quota_4_easy_4_medium=True,
        all_five_actual_READY_sources_included=True,
        no_source_reselection_after_frozen_screen=True,
        source_selection_not_globally_blind=True,
        source_years=sorted({c["year"] for c in src["cases"]}),
        exact_reference_bands=EXPECTED_BANDS,
        no_independent_UNSAT_LRAT=True,
        original_sha_verified=True,
        one_logical_CPU_per_solver=True,no_parallel_children=True,
        cap_s=CAP,arms=list(ARMS),reps=REPS,shards=SHARDS,
        cases=src["cases"],trial_count=COUNT*len(ARMS)*REPS,
        script_sha256=e9.digest(__file__),
        original_Kissat_sha256=e9.digest(e9.KISSAT),
        no_auto_promotion=True)
    dump(ROOT/"manifest.json",m)
    print("EQUIV10M5_FROZEN "+json.dumps(dict(source_count=COUNT,
        easy=1,medium=4,one_cpu=True,expected_trials=m["trial_count"],
        cap_s=CAP,selected_after_original_freeze=False),sort_keys=True),flush=True)

def verify():
    src=load()
    m=json.loads((ROOT/"manifest.json").read_text())
    need(m["protocol"]==PROTO and m["trial_count"]==50 and
         m["cap_s"]==CAP and m["arms"]==list(ARMS) and
         m["script_sha256"]==e9.digest(__file__) and
         m["source_manifest_sha256"]==e9.digest(SOURCE) and
         m["cases"]==src["cases"] and
         m["original_Kissat_sha256"]==e9.digest(e9.KISSAT),
         "EQUIV10M5 frozen manifest, code or binary drift")
    return m

def shard(idx):
    need(0<=idx<SHARDS,"invalid shard")
    m=verify()
    c=m["cases"][idx]
    rows=[]
    for rep in range(REPS):
        arms=list(ARMS)
        random.Random(c["sha256"]+"|E10M5|"+str(rep)).shuffle(arms)
        for arm in arms:
            r=e9.trial(c,rep,arm,CAP)
            need(r["sha256"]==c["sha256"] and
                 (r["status"]!="SAT" or r["SAT_original_witness_verified"]) and
                 r["child_starts"]<=2 and r["wall_E2E_s"]<=CAP+.08,
                 "original SAT SHA or budget validation failed")
            r["source_protocol"]=r["protocol"]
            r.update(protocol=PROTO,shard=idx,reference_band=c["reference_band"],
                     reference_Kissat_s=c["reference_Kissat_s"],
                     source_selection="unchanged 5-of-8 frozen EQUIV10M")
            rows.append(r)
            dump(ROOT/("shard-%d.json"%idx),rows)
            print("EQUIV10M5_TRIAL "+json.dumps(r,sort_keys=True),flush=True)
    need(len(rows)==REPS*len(ARMS),"incomplete paired SHA "+c["sha256"])
    print("EQUIV10M5_SHARD_PASS",idx,len(rows),flush=True)

def audit():
    m=verify()
    rows=[]
    for idx,c in enumerate(m["cases"]):
        s=json.loads((ROOT/("shard-%d.json"%idx)).read_text())
        need(len(s)==REPS*len(ARMS),"incomplete shard "+str(idx))
        rows.extend(s)
        need({x["sha256"] for x in s}=={c["sha256"]} and
             {x["shard"] for x in s}=={idx},"shard source mismatch")
    expected={(c["sha256"],rep,arm) for c in m["cases"]
             for rep in range(REPS) for arm in ARMS}
    keys={(r["sha256"],r["rep"],r["arm"]) for r in rows}
    need(len(rows)==len(keys)==len(expected)==m["trial_count"] and
         keys==expected,"incomplete paired matrix or duplicates")
    group=collections.defaultdict(list)
    for r in rows:
        need(r["protocol"]==PROTO and r["cap_s"]==CAP and
             r["status"] in ("SAT","UNSAT","TIMEOUT") and
             r["wall_E2E_s"]<=CAP+.08 and
             (r["status"]!="SAT" or r["SAT_original_witness_verified"]),
             "trial protocol, original SHA SAT witness or cap mismatch")
        group[r["sha256"]].append(r)
    agreed=set()
    for sha,rr in group.items():
        sts={r["status"] for r in rr if r["status"]!="TIMEOUT"}
        need(len(sts)<=1,"SAT/UNSAT conflicting outputs "+sha)
        if (any(r["arm"]=="kissat1" and r["status"]=="UNSAT" for r in rr) and
            any(r["arm"]=="cadical301_default" and r["status"]=="UNSAT" for r in rr)):
            agreed.add(sha)
    def ok(r):
        return r["status"]=="SAT" or (r["status"]=="UNSAT" and r["sha256"] in agreed)
    def part(arr):
        return dict(n=len(arr),
           solved=sum(ok(x) for x in arr),
           SAT_original_model_verified=sum(x["status"]=="SAT" for x in arr),
           UNSAT_crosssolver_agreed_no_LRAT=sum(x["status"]=="UNSAT" and
                                                  x["sha256"] in agreed for x in arr),
           UNSAT_unconfirmed=sum(x["status"]=="UNSAT" and
                                 x["sha256"] not in agreed for x in arr),
           timeouts=sum(x["status"]=="TIMEOUT" for x in arr),
           PAR2_s=round(sum(x["wall_E2E_s"] if ok(x) else 2*CAP for x in arr),6),
           CPU_s=round(sum(x["child_CPU_s"] for x in arr),6),
           second_seed_SAT=sum(x["status"]=="SAT" and len(x["stages"])==2 for x in arr))
    scores={a:part([r for r in rows if r["arm"]==a]) for a in ARMS}
    ref=scores["kissat1"]["PAR2_s"]
    for s in scores.values():
        s["speedup_vs_kissat_PAR2_x"]=round(ref/s["PAR2_s"],6)
    per_shard={str(i):{a:part([r for r in rows if r["arm"]==a and
                           r["shard"]==i]) for a in ARMS} for i in range(SHARDS)}
    by={(r["sha256"],r["rep"],r["arm"]):r for r in rows}
    pairs={}
    for a in ARMS:
        if a=="kissat1":continue
        diffs=[]
        for c in m["cases"]:
            for rep in range(REPS):
                ra=by[(c["sha256"],rep,a)]
                rb=by[(c["sha256"],rep,"kissat1")]
                diffs.append((ra["wall_E2E_s"] if ok(ra) else 2*CAP)-
                             (rb["wall_E2E_s"] if ok(rb) else 2*CAP))
        pairs[a]=dict(wins=sum(x<-.02 for x in diffs),
                      losses=sum(x>.02 for x in diffs),
                      ties=sum(abs(x)<=.02 for x in diffs),
                      max_regression_s=round(max(diffs),6),
                      max_gain_s=round(min(diffs),6))
    report=dict(protocol=PROTO,original_source_count=COUNT,
        original_CNF_SHA_locked=True,sampling="reference-conditioned, not globally blind",
        original_E10M_freeze_failed_predefined_4_4_quota=True,
        uses_all_5_actual_selected_sources=True,
        original_reference_bands=EXPECTED_BANDS,
        strict_UNSAT_agreement_SHA=sorted(agreed),independent_UNSAT_LRAT=False,
        cap_s=CAP,one_logical_CPU=True,trial_count=len(rows),
        scores=scores,per_shard=per_shard,paired=pairs,
        per_formula={c["sha256"]:dict(reference_band=c["reference_band"],
            reference_Kissat_s=c["reference_Kissat_s"],
            arms={a:[dict(rep=x["rep"],status=x["status"],
                           wall_s=x["wall_E2E_s"]) for x in group[c["sha256"]]
                        if x["arm"]==a] for a in ARMS}) for c in m["cases"]})
    dump(ROOT/"report.json",report)
    print("EQUIV10M5_FINAL "+json.dumps(report,sort_keys=True),flush=True)
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("selftest","freeze","verify","shard","audit"))
    p.add_argument("--shard",type=int,default=0)
    a=p.parse_args()
    if a.action=="shard":shard(a.shard)
    else:
        globals()[a.action]()
        if a.action=="verify":print("EQUIV10M5_VERIFY_PASS",flush=True)
