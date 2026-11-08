#!/usr/bin/env python3
"""DRNAS MRE4 P2: source-instrumented CMS native in-CDCL reason-event audit.

R28 safe route unchanged from MRE4 P1.
Five causal arms, original SHA-pinned source, same native seed each pair.
OTF Gauss OFF. Source-certified XOR imported without free guessed parity.
MRE1 proof-replayed short CNF lemmas capped at 2, MRE2 cheap BCP gate.
Native CMS patched at pinned upstream SHA to trace imported clause IDs in
actual binary/long watched propagators, not fake post-hoc CDCL differences.

Note: local reason event is *not necessarily a uniquely new implication*
relative to the counterfactual solver. Only paired shadow/active timing +
native events demonstrate their relevance, not unique SAT complexity claims.
"""
from __future__ import annotations
import argparse,collections,hashlib,json,os,pathlib,random,re,subprocess
import sys,tempfile,time
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import mre4_safe_causal as p1
import r195_native_cms_benchmark as r195
import mre1_cross_representation as mre1

PROTO="DRNAS-MRE4-P2-SOURCE-INSTRUMENTED-CMS51115-32SHA-5ARM-2REP-v1"
ROOT=pathlib.Path("mre4_p2")
MODES=p1.MODES
CAP=p1.CAP
SHARDS=p1.SHARDS
REPS=p1.REPS
SOURCE_VERIFICATION="SAT_ORIGINAL_CNF_CHECKED_NO_INDEPENDENT_UNSAT_LRAT"

REGEX=re.compile(
  r"^MRE4_NATIVE_TRACE tagged=(\d+) bin_units=(\d+) bin_conflicts=(\d+) "
  r"long_units=(\d+) long_conflicts=(\d+) nonroot_units=(\d+) "
  r"nonroot_conflicts=(\d+) events=(\d+)$",re.M)
FIELDS=("tagged","bin_units","bin_conflicts","long_units",
        "long_conflicts","nonroot_units","nonroot_conflicts","events")

def need(ok,msg):p1.need(ok,msg)
def save(path,item):p1.save(path,item)

def parse_trace(output):
    m=REGEX.search(output)
    need(m is not None,"instrumented CMS lacked genuine DRNAS watch telemetry")
    d=dict(zip(FIELDS,map(int,m.groups())))
    need(d["events"]==d["bin_units"]+d["bin_conflicts"]+
         d["long_units"]+d["long_conflicts"],"trace event accounting failed")
    need(d["nonroot_units"]+d["nonroot_conflicts"]<=d["events"],
         "nonroot events exceed all")
    return d

def run_one(case,mode,rep,binary):
    source=r195.FROZEN/case["name"]
    begin=time.perf_counter()
    need(r195.digest(source)==case["sha256"],"input SHA altered")
    seed=int(hashlib.sha256((PROTO+case["sha256"]+str(rep)).encode()).hexdigest()[:8],16)
    source_rows,proofs,meta,fast_status,fast_proof=p1.prepare(source,mode)
    prep_s=time.perf_counter()-begin
    stat={};trace=None
    result="TIMEOUT"
    proof="CAP_TIMEOUT"
    if fast_status=="SAT":
        need(mode=="r28_safe" and fast_proof=="EXACT_CNFEQUIV_GAUSS_SAT_MODEL_CHECKED",
             "unproven R28 shortcut")
        result="SAT";proof=fast_proof
    else:
        remaining=CAP-(time.perf_counter()-begin)
        if remaining>0.1:
            with tempfile.TemporaryDirectory(prefix="mre4-p2-") as t:
                t=pathlib.Path(t)
                sourcefile=t/"source.tsv"
                lemmasfile=t/"certified.cnf-lemmas"
                mre1.write_xors(sourcefile,source_rows)
                lemmasfile.write_text(
                    "".join(" ".join(map(str,lemma["clause"]))+" 0\n"
                       for lemma in proofs))
                native_mode={
                  "cms_native":"cms_native",
                  "r28_safe":"cms_native",
                  "xor_no_otf":"mre4_trace_xor",
                  "crr_shadow":"mre4_trace_shadow",
                  "crr_active":"mre4_trace_active"
                }[mode]
                need(mode=="crr_active" or not proofs,"lemma imported outside active arm")
                if proofs:
                    need(meta.get("proof_replayed") is True and len(proofs)<=2,
                         "unsafe/unbounded active input")
                try:
                    cp=subprocess.run([
                          str(pathlib.Path(binary).resolve()),
                          str(source.resolve()),
                          str(sourcefile.resolve()),
                          str(lemmasfile.resolve()),
                          native_mode,str(seed)],
                        capture_output=True,text=True,
                        errors="replace",timeout=remaining,check=False)
                except subprocess.TimeoutExpired:
                    cp=None
                if cp is not None:
                    need(cp.returncode==0,"native CMS or SAT witness safety failure: "+
                         cp.stderr[-1200:])
                    result,model,stat=r195.parsed_native(cp.stdout)
                    trace=parse_trace(cp.stdout)
                    if mode!="crr_active":
                        need(trace["tagged"]==0 and trace["events"]==0,
                             "nonactive arm generated tagged events")
                    else:
                        need(trace["tagged"]<=len(proofs),
                             "native trace tagged more than imported lemmas")
                    if result=="SAT":
                        r195.verify_model(source,model)
                        proof="ORIGINAL_CNF_SAT_MODEL_CHECKED"
                    if result=="UNSAT":
                        proof="CMS_UNSAT_WITHOUT_INDEPENDENT_LRAT"
    elapsed=time.perf_counter()-begin
    if elapsed>=CAP:result="TIMEOUT";proof="CAP_TIMEOUT"
    if result!="TIMEOUT":
        need(case["expected"]==result,"reference verdict changed")
    row=dict(protocol=PROTO,source_sha256=case["sha256"],
        name=case["name"],cohort=case["cohort"],mode=mode,rep=rep,
        seed=seed,status=result,proof=proof,
        elapsed_s=round(elapsed,6),prep_s=round(prep_s,6),
        par2_s=round(2*CAP if result=="TIMEOUT" else elapsed,6),
        certified_derived=len(proofs),
        source_rows=len(source_rows),
        meta=meta,trace=trace,
        cms_conflicts=stat.get("conflicts"),
        cms_decisions=stat.get("decisions"),
        cms_propagations=stat.get("propagations"),
        upstream_cms_sha="3b709118fd08eb1d15f25e0e239dbc596f967b60",
        r28_safe_unchanged=True,
        all_native_otf_gauss_disabled=True,
        source_instrumented_cms_watch_events=(trace is not None),
        independent_unsat_lrat=False,
        reason_counterfactual_unique_implication_claim=False,
        commit=os.environ.get("GITHUB_SHA","local"))
    return row

def shard(k,binary):
    need(0<=k<SHARDS,"invalid shard")
    cs=r195.cases()
    need(len(cs)==32 and len({c["sha256"] for c in cs})==32,
         "unfrozen development cohort")
    for c in cs[k::SHARDS]:
        need(r195.digest(r195.FROZEN/c["name"])==c["sha256"],
             "source sha mismatch before measurement")
    vals=[]
    for case in cs[k::SHARDS]:
        for rep in range(REPS):
            arms=list(MODES)
            random.Random(PROTO+case["sha256"]+str(rep)).shuffle(arms)
            for mode in arms:
                item=run_one(case,mode,rep,binary)
                vals.append(item)
                save(ROOT/f"shard-{k}.json",vals)
                print("MRE4_P2_TRIAL",json.dumps({key:item[key] for key in (
                  "name","cohort","mode","rep","status","elapsed_s","par2_s",
                  "certified_derived","source_rows","trace",
                  "cms_conflicts","cms_decisions","cms_propagations")},
                  sort_keys=True),flush=True)
    need(len(vals)==len(cs[k::SHARDS])*REPS*len(MODES),"incomplete shard")
    print("MRE4_P2_SHARD_PASS",k,len(vals),flush=True)

def audit():
    cs=r195.cases()
    known={c["sha256"]:c for c in cs}
    bypair=collections.defaultdict(dict)
    rows=[]
    for i in range(SHARDS):
        vals=json.loads((ROOT/f"shard-{i}.json").read_text())
        need(len(vals)==len(cs[i::SHARDS])*REPS*len(MODES),"incomplete shard")
        rows+=vals
    need(len(rows)==320,"not 320 source-paired original CNF trials")
    for r in rows:
        need(r["source_sha256"] in known,"unfamiliar source hash")
        need(r["name"]==known[r["source_sha256"]]["name"],"source identity mismatch")
        need(r["protocol"]==PROTO and r["all_native_otf_gauss_disabled"],
             "unsafe native configuration")
        need(r["independent_unsat_lrat"] is False,"unverified UNSAT proof claim")
        if r["status"]=="SAT":
            need(r["proof"] in ("EXACT_CNFEQUIV_GAUSS_SAT_MODEL_CHECKED",
                                 "ORIGINAL_CNF_SAT_MODEL_CHECKED"),"unchecked SAT")
        k=(r["source_sha256"],r["rep"])
        need(r["mode"] not in bypair[k],"duplicated arm")
        bypair[k][r["mode"]]=r
        need(abs(r["par2_s"]-(2*CAP if r["status"]=="TIMEOUT"
                               else r["elapsed_s"]))<1e-5,"PAR2 mismatch")
        if r["trace"] is not None:
            trace=r["trace"]
            need(trace["events"]==sum(trace[q] for q in (
                "bin_units","bin_conflicts","long_units","long_conflicts")),
                "native trace wrong accounting")
            if r["mode"]!="crr_active":
                need(trace["tagged"]==0 and trace["events"]==0,"shadow active tagging")
        if r["mode"]=="crr_active" and r["certified_derived"]>0:
            need(r["meta"]["proof_replayed"] and r["certified_derived"]<=2,
                 "uncertified clauses active")
    need(len(bypair)==64,"missing paired source/seed")
    for modes in bypair.values():
        need(set(modes)==set(MODES),"missing same-source 5-arm comparison")
        need(len({x["status"] for x in modes.values()
            if x["status"]!="TIMEOUT"})<=1,"SAT/UNSAT disagreement")
    totals={}
    for cohort in ("reused_official_2026","reused_synthetic_controls",
                   "new_mixed_xor_cnf","all"):
        eligible=[r for r in rows if r["cohort"]==cohort or cohort=="all"]
        totals[cohort]={}
        for mode in MODES:
            a=[r for r in eligible if r["mode"]==mode]
            totals[cohort][mode]=dict(n=len(a),
                solved=sum(r["status"]!="TIMEOUT" for r in a),
                par2_s=round(sum(r["par2_s"] for r in a),6),
                prep_s=round(sum(r["prep_s"] for r in a),6),
                active_lemmas=sum(r["certified_derived"] for r in a),
                actual_native_tagged=sum((r["trace"] or {}).get("tagged",0) for r in a),
                actual_native_units=sum((r["trace"] or {}).get("bin_units",0)+
                                   (r["trace"] or {}).get("long_units",0) for r in a),
                actual_native_conflicts=sum((r["trace"] or {}).get("bin_conflicts",0)+
                                 (r["trace"] or {}).get("long_conflicts",0) for r in a),
                nonroot_units=sum((r["trace"] or {}).get("nonroot_units",0) for r in a),
                no_trace_due_to_R28_fast_sat=sum(r["meta"]["route"]=="r28_pure_sat" for r in a))
    active=totals["all"]["crr_active"]
    shadow=totals["all"]["crr_shadow"]
    promotion=(active["par2_s"]<shadow["par2_s"]
       and active["actual_native_units"]+active["actual_native_conflicts"]>0
       and totals["reused_official_2026"]["crr_active"]["actual_native_units"]+
           totals["reused_official_2026"]["crr_active"]["actual_native_conflicts"]>0)
    report=dict(status="MRE4_P2_AUDIT_PASS",protocol=PROTO,
        source_count=32,attempts=len(rows),totals=totals,
        source_instrumented_actual_watch_reason_events=True,
        full_wall_including_preparation=True,
        original_SAT_witness_checked=True,independent_UNSAT_LRAT=False,
        source_was_development_previously_used_NOT_blind=True,
        branch_promoted=promotion,strict_promotion_requires_new_blind_holdout=True,
        no_claim_of_unique_counterfactual_implication=True,
        drnas_R28_safe_preserved=True,all_otf_gauss_disabled=True,
        causal_rule="active must beat same-prep shadow; usage event alone is not speed evidence")
    save(ROOT/"report.json",report);save(ROOT/"all-trials.json",rows)
    print("MRE4_P2_FINAL",json.dumps(report,sort_keys=True),flush=True)

def selftest():
    need(MODES==("cms_native","r28_safe","xor_no_otf","crr_shadow","crr_active"),
         "R28 lost or arm shifted")
    need(32*REPS*len(MODES)==320,"paired counts changed")
    good="MRE4_NATIVE_TRACE tagged=2 bin_units=3 bin_conflicts=1 long_units=0 long_conflicts=0 nonroot_units=2 nonroot_conflicts=1 events=4"
    need(parse_trace(good)["events"]==4,"trace parser")
    print("MRE4_P2_SELFTEST_PASS",PROTO,flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("selftest","shard","audit"))
    p.add_argument("--shard",type=int,default=0)
    p.add_argument("--binary",default="mre4_p2/mre4_instrumented_cms")
    a=p.parse_args()
    if a.action=="selftest":selftest()
    elif a.action=="shard":shard(a.shard,a.binary)
    else:audit()
