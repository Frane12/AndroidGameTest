#!/usr/bin/env python3
"""DMD4test: decision/conflict causal comparison of proof-checked ANF clauses on real CaDiCaL CDCL.

Local ANF lemmas from unchanged DMD1 pass independent exhaustive source-bag
proof replay. DMD2 live UP novelty gate can select a subset. Live observer
counts lemma unit opportunities on REAL solver assignment/backtrack callbacks,
but this is only OBSERVATIONAL, not proof of a new propagation. Active arms
add source-consequent clauses to native CaDiCaL before solving.
Seven arms, 24 REUSED official CNFs plus 4 synthetic controls x 2 repeats:
392 single-logical-CPU full E2E attempts, cap 8 s per arm. No independent LRAT.
Same-CNF and same-rep active vs shadow control only qualifies when the exact
candidate lemma signature matches; observed-only placebo isolates callback overhead.
"""
from __future__ import annotations
import argparse,collections,hashlib,json,os,pathlib,random,re,resource
import tempfile,time
import dmd1_bench as d1

PROTO="DRNAS-DMD4test-CAUSAL-CDCL-COUNTERS-24SEEN-4TOY-7ARMS-2REPS-8S-v1"
ARMS=("cadical_clean","cadical_observer_only","cadical_shadow_gate",
      "cadical_active_gate","cadical_shadow_all","cadical_active_all",
      "kissat_original")
REPS=2
SHARDS=4
CAP=8.0
ROOT=pathlib.Path("mre_dmd4test")
DMD1=ROOT/"bin/dmd1_anf"
GATE=ROOT/"bin/dmd2_gate"
LIVE=ROOT/"bin/dmd4test_live"
KISSAT=pathlib.Path("built/bin/kissat_4_0_4")
DMD1_MS=200
GATE_MS=90
d1.ROOT=ROOT
def need(ok,why):
    if not ok:raise RuntimeError("DMD4test_FAIL_CLOSED "+str(why))
def cpu(which):
    r=resource.getrusage(which)
    return r.ru_utime+r.ru_stime
def cases():
    items=d1.cases()
    need(len(items)==28 and len({x["sha256"] for x in items})==28 and
         sum(x["cohort"]=="reused_equiv7_original" for x in items)==24 and
         sum(x["cohort"]=="synthetic_toy" for x in items)==4,
         "unexpected DMD1 original cohort")
    return items
def stats(out):
    # Native CaDiCaL 2.1.0 statistics. Preserve raw matching text in row too.
    rows=[x for x in out.splitlines() if "conflicts:" in x or
          "decisions:" in x or "propagations:" in x or "learned:" in x]
    result={}
    for line in rows:
        for key in ("conflicts","decisions","propagations","learned"):
            m=re.search(r"\b"+key+r"\s*:\s*([0-9][0-9,]*)",line)
            if m:result[key]=int(m.group(1).replace(",",""))
    return result,rows[-12:]
def verify_sat(out,clauses):
    vals={}
    for line in out.splitlines():
        if not line.startswith("v "):continue
        for word in line.split()[1:]:
            v=int(word)
            if v==0:continue
            need(abs(v) not in vals or vals[abs(v)]==(v>0),
                 "conflicting SAT variable assignment")
            vals[abs(v)]=v>0
    need(vals,"empty SAT assignment")
    need(all(any(abs(lit) in vals and vals[abs(lit)]==(lit>0)
                 for lit in clause) for clause in clauses),
         "SAT certificate did not satisfy full original CNF")
    return True
def trial(case,arm,rep):
    need(arm in ARMS and rep in (0,1),"unregistered trial")
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    pinned=min(os.sched_getaffinity(0))
    source=pathlib.Path(case["path"])
    need(source.is_file() and d1.sha(source)==case["sha256"],
         "original SHA mismatch")
    start=time.monotonic()
    start_self=cpu(resource.RUSAGE_SELF)
    start_child=cpu(resource.RUSAGE_CHILDREN)
    n,orig=d1.read_cnf(source)
    prep_cpu=0.
    proof=dict(lemmas=[],groups=0,nonlinear_relations=0,timed_out=False)
    gate_data=dict(candidates=0,selected=0,novel_directions=0,
                   selected_indices=[],timed_out=False)
    outcome="TIMEOUT";witness=False
    live={}
    status_note="NO_PREP"
    cdcl_stats={}
    stat_lines=[]
    with tempfile.TemporaryDirectory(prefix="dmd4test-") as d:
        d=pathlib.Path(d)
        candidates=source
        if arm not in ("cadical_clean","kissat_original"):
            dmd_aug=d/"dmd1_augmented.cnf"
            cert=d/"local_proof.json"
            available=max(0.01,CAP-(time.monotonic()-start))
            rc,out,err,_,pcpu,timed=d1.run_process(
                [DMD1,source,dmd_aug,cert,DMD1_MS,48],available,pinned)
            prep_cpu+=pcpu
            need(not timed and rc==0 and cert.is_file(),
                 "DMD1 proof extraction failed "+err[-250:])
            proof=json.loads(cert.read_text())
            d1.proof_replay(source,dmd_aug,proof)
            candidates=dmd_aug if proof["lemmas"] else source
            status_note="LOCAL_PROOF_REPLAYED"
        if arm in ("cadical_observer_only","cadical_shadow_gate","cadical_active_gate") and proof["lemmas"]:
            gated=d/"gate.cnf"
            available=max(0.01,CAP-(time.monotonic()-start))
            rc,out,err,_,pcpu,timed=d1.run_process(
                [GATE,source,candidates,gated,GATE_MS],min(1.0,available),pinned)
            prep_cpu+=pcpu
            if timed or rc!=0:
                need(not gated.exists(),"partial gate result cannot be used")
                candidates=source
                status_note="GATE_ABSTAIN"
            else:
                v=[x[len("DMD2_GATE "):] for x in out.splitlines()
                   if x.startswith("DMD2_GATE ")]
                need(len(v)==1,"DMD2 gate metadata missing")
                gate_data=json.loads(v[0])
                idx=gate_data["selected_indices"]
                need(gate_data["candidates"]==len(proof["lemmas"]) and
                     len(idx)==gate_data["selected"] and
                     len(set(idx))==len(idx) and
                     all(type(i)==int and 0<=i<len(proof["lemmas"]) for i in idx),
                     "gate indices not subset of locally proved lemmas")
                if idx:
                    nn,cl=d1.read_cnf(gated)
                    need(nn==n and cl[:len(orig)]==orig and
                         cl[len(orig):]==[tuple(proof["lemmas"][i]["clause"]) for i in idx],
                         "gate source/payload drift")
                    candidates=gated
                else:
                    need(not gated.exists(),"empty gate unexpectedly emitted CNF")
                    candidates=source
                status_note="GATE_PROOF_REPLAYED"
        source_lemmas=[list(k["clause"]) for k in proof["lemmas"]]
        if arm in ("cadical_observer_only","cadical_shadow_gate","cadical_active_gate"):
            actual_lemmas=[source_lemmas[i] for i in gate_data["selected_indices"]]
        elif arm in ("cadical_shadow_all","cadical_active_all"):
            actual_lemmas=source_lemmas
        else:actual_lemmas=[]
        candidate_signature=fingerprint(actual_lemmas)
        source_lemma_signature=fingerprint(source_lemmas)
        elapsed=time.monotonic()-start
        remaining=CAP-elapsed
        if remaining>0.1:
            if arm=="kissat_original":
                rc,out,err,_,solver_cpu,timed=d1.run_process(
                    [KISSAT,source],remaining,pinned)
                if timed:outcome="TIMEOUT"
                else:outcome,witness=d1.outcome(rc,out,orig)
            else:
                mode={"cadical_clean":"clean","cadical_observer_only":"observer_control",
                      "cadical_shadow_all":"shadow",
                      "cadical_active_all":"all_active","cadical_shadow_gate":"shadow",
                      "cadical_active_gate":"gate_active"}[arm]
                # Reserve time for native UNKNOWN + solver.statistics output.
                native_cap=max(.20,remaining-.18)
                rc,out,err,_,solver_cpu,timed=d1.run_process(
                   [LIVE,source,candidates,mode,f"{native_cap:.5f}"],
                   remaining,pinned)
                if timed:
                    outcome="TIMEOUT";status_note="NATIVE_HARD_TIMEOUT"
                else:
                    need(rc in (0,10,20),"native observer exit failure "+err[-450:])
                    body=[x[len("DMD4test_RESULT "):] for x in out.splitlines()
                          if x.startswith("DMD4test_RESULT ")]
                    need(len(body)==1,"native live-CDCL report missing")
                    live=json.loads(body[0])
                    need(live["candidate_lemmas"]<=24 and
                         live["mode"]==mode and not live["callback_error"],
                         "live reported callback invariant failure")
                    outcome=live["status"]
                    if rc==10:
                        need(outcome=="SAT","SAT return/status mismatch")
                        witness=verify_sat(out,orig)
                        need(live["model_original_verified"],"native model not verified")
                    elif rc==20:need(outcome=="UNSAT","UNSAT return/status mismatch")
                    else:need(outcome=="TIMEOUT","UNKNOWN return/status mismatch")
                    cdcl_stats,stat_lines=stats(out)
        else:status_note="PREPROCESS_EXHAUSTED_CAP"
    e2e=time.monotonic()-start
    if outcome=="TIMEOUT" and e2e>=CAP:e2e=CAP
    need(outcome!="SAT" or witness,"invalid source SAT witness")
    return dict(protocol=PROTO,cohort=case["cohort"],arm=arm,
       original_file=case["filename"],original_sha256=case["sha256"],
       rep=rep,status=outcome,cap_s=CAP,
       e2e_s=round(e2e,6),
       PAR2_s=round(e2e if outcome!="TIMEOUT" else 2*CAP,6),
       SAT_original_witness_verified=witness,
       UNSAT_independent_LRAT=False,logical_cpu_budget=1,pinned_cpu=pinned,
       DMD1_proof_replayed=arm not in ("cadical_clean","kissat_original"),
       dmd1_lemmas=len(proof["lemmas"]),
       dmd1_groups=proof["groups"],
       dmd1_nonlinear=proof["nonlinear_relations"],
       gate_candidates=gate_data["candidates"],gate_selected=gate_data["selected"],
       gate_score=gate_data["novel_directions"],
       prep_child_cpu_s=round(prep_cpu,6),
       full_cpu_s=round(cpu(resource.RUSAGE_SELF)-start_self+
                       cpu(resource.RUSAGE_CHILDREN)-start_child,6),
       note=status_note,live=live,cdcl_stats=cdcl_stats,
       candidate_signature=candidate_signature,
       source_lemma_signature=source_lemma_signature,
       observed_lemmas=len(actual_lemmas),
       stat_lines=stat_lines)
def fingerprint(items):
    return hashlib.sha256(json.dumps(items,sort_keys=True,separators=(",",":")).encode()).hexdigest()

def selftest():
    need(LIVE.is_file() and DMD1.is_file() and GATE.is_file() and KISSAT.is_file(),
         "pinned executables missing")
    a=cases()
    need(len(a)==28 and len(ARMS)==7 and SHARDS==4,"benchmark matrix drift")
    toy=next(c for c in a if c["cohort"]=="synthetic_toy")
    sample=trial(toy,"cadical_active_gate",0)
    need(sample["status"]=="SAT" and sample["SAT_original_witness_verified"] and
         sample["DMD1_proof_replayed"],"live proof/reason smoke failed")
    placebo=trial(toy,"cadical_observer_only",0)
    need(placebo["status"]=="SAT" and placebo["candidate_signature"]==sample["candidate_signature"] and
         placebo["live"]["live_unit_opportunities"]==0 and
         placebo["live"]["observed_assignments"]>=0,
         "same-variables placebo did not match active toy")
    print("DMD4test_SELFTEST_PASS",json.dumps(dict(
        model_original_checked=True,live=sample["live"],
        proof_lemmas=sample["dmd1_lemmas"],gate_selected=sample["gate_selected"]),
        sort_keys=True),flush=True)
def bench(shard):
    need(0<=shard<SHARDS,"shard out of range")
    subset=[c for i,c in enumerate(cases()) if i%SHARDS==shard]
    need(len(subset)==7,"shard source count changed")
    ROOT.mkdir(exist_ok=True)
    rows=[]
    for c in subset:
        for rep in range(REPS):
            arms=list(ARMS)
            random.Random(c["sha256"]+str(rep)).shuffle(arms)
            for arm in arms:
                r=trial(c,arm,rep)
                rows.append(r)
                (ROOT/f"shard-{shard}.json").write_text(json.dumps(rows,sort_keys=True))
                print("DMD4test_TRIAL",json.dumps(r,sort_keys=True),flush=True)
    need(len(rows)==98,"shard incomplete")
    print("DMD4test_SHARD_PASS",shard,len(rows),flush=True)
def audit():
    selected=cases()
    rows=[]
    for shard in range(SHARDS):
        p=ROOT/f"shard-{shard}.json"
        need(p.is_file(),"missing shard "+str(shard))
        data=json.loads(p.read_text())
        need(len(data)==len(selected)//SHARDS*REPS*len(ARMS)==98,
             "wrong shard count")
        rows.extend(data)
    exp={(c["sha256"],rep,arm) for c in selected
         for rep in range(REPS) for arm in ARMS}
    found={(r["original_sha256"],r["rep"],r["arm"]) for r in rows}
    need(len(rows)==len(found)==len(exp)==392 and found==exp,
         "missing/duplicate one-core paired E2E records")
    rowmap={(r["original_sha256"],r["rep"],r["arm"]):r for r in rows}
    for r in rows:
        need(r["protocol"]==PROTO and r["logical_cpu_budget"]==1 and
             r["cap_s"]==CAP,"protocol/core drift")
        need(r["status"] in ("SAT","UNSAT","TIMEOUT"),"bad verdict")
        need(r["status"]!="SAT" or r["SAT_original_witness_verified"],
             "original SAT witness not verified")
        need(r["gate_selected"]<=r["dmd1_lemmas"],"unproved gate lemma")
        need(r["candidate_signature"]==fingerprint(
            [list(v) for v in []]) or r["observed_lemmas"]>0,
            "inconsistent empty candidate hash")
        if r["live"]:
            need(not r["live"]["callback_error"],"bad real-CDCL callback")
            if r["arm"]=="cadical_observer_only":
                need(r["live"]["live_unit_opportunities"]==0,
                     "observer-only unexpectedly evaluated lemmas")
    scores={}
    for arm in ARMS:
        group=[r for r in rows if r["arm"]==arm]
        co={}
        for name in ("reused_equiv7_original","synthetic_toy"):
            g=[r for r in group if r["cohort"]==name]
            co[name]=dict(trials=len(g),
                solved=sum(r["status"]!="TIMEOUT" for r in g),
                PAR2_s=round(sum(r["PAR2_s"] for r in g),6))
        scores[arm]=dict(trials=len(group),
            solved=sum(r["status"]!="TIMEOUT" for r in group),
            verified_SAT=sum(r["status"]=="SAT" for r in group),
            UNSAT_backend_no_LRAT=sum(r["status"]=="UNSAT" for r in group),
            PAR2_s=round(sum(r["PAR2_s"] for r in group),6),
            full_CPU_s=round(sum(r["full_cpu_s"] for r in group),6),
            proof_lemmas=sum(r["dmd1_lemmas"] for r in group),
            active_candidates=sum(r["observed_lemmas"] for r in group),
            detected_live_unit_opportunities=sum(
                r["live"].get("live_unit_opportunities",0) for r in group),
            observed_assignments=sum(
                r["live"].get("observed_assignments",0) for r in group),
            CDCL_decisions_reported=sum(
                r["cdcl_stats"].get("decisions",0) for r in group),
            CDCL_conflicts_reported=sum(
                r["cdcl_stats"].get("conflicts",0) for r in group),
            CDCL_propagations_reported=sum(
                r["cdcl_stats"].get("propagations",0) for r in group),
            decisions_count_present=sum("decisions" in r["cdcl_stats"]
                                      for r in group),
            conflicts_count_present=sum("conflicts" in r["cdcl_stats"]
                                      for r in group),
            propagations_count_present=sum("propagations" in r["cdcl_stats"]
                                      for r in group),
            cohorts=co)
    for arm in ARMS:
        scores[arm]["PAR2_delta_pct_vs_clean"]=round(
          100*(scores[arm]["PAR2_s"]/scores["cadical_clean"]["PAR2_s"]-1),5)
    # The A/B comparison that can actually speak to the lemma effect is
    # ACTIVE versus SHADOW with EXACTLY the SAME precommitted candidate
    # list and same observed vars. All mismatches are reported and excluded.
    comparisons=[
        ("gate_active_vs_shadow","cadical_active_gate","cadical_shadow_gate"),
        ("all_active_vs_shadow","cadical_active_all","cadical_shadow_all"),
        ("observer_only_vs_shadow_gate","cadical_shadow_gate","cadical_observer_only"),
        ("observer_only_vs_clean","cadical_observer_only","cadical_clean"),
        ("gate_active_vs_clean","cadical_active_gate","cadical_clean"),
        ("kissat_vs_clean","kissat_original","cadical_clean")]
    paired={}
    for label,active,base in comparisons:
        pairs=[]
        for case in selected:
            for rep in range(REPS):
                a=rowmap[(case["sha256"],rep,active)]
                b=rowmap[(case["sha256"],rep,base)]
                needs_matching=label in (
                    "gate_active_vs_shadow","all_active_vs_shadow",
                    "observer_only_vs_shadow_gate")
                match=a["candidate_signature"]==b["candidate_signature"] if needs_matching else True
                # Observed-variable set is entirely specified by candidate CNF
                # and the same original source SHA.
                bothsolved=a["status"]==b["status"] and a["status"] in ("SAT","UNSAT")
                decisions_measured=("decisions" in a["cdcl_stats"] and
                                    "decisions" in b["cdcl_stats"])
                conflicts_measured=("conflicts" in a["cdcl_stats"] and
                                    "conflicts" in b["cdcl_stats"])
                item=dict(sha256=case["sha256"],file=case["filename"],
                    cohort=case["cohort"],rep=rep,matched_candidates=match,
                    active_candidates=a["observed_lemmas"],
                    active_status=a["status"],base_status=b["status"],
                    active_PAR2_s=a["PAR2_s"],base_PAR2_s=b["PAR2_s"],
                    PAR2_delta_s=round(a["PAR2_s"]-b["PAR2_s"],6),
                    both_solved_same_verdict=bothsolved,
                    active_decisions=a["cdcl_stats"].get("decisions"),
                    base_decisions=b["cdcl_stats"].get("decisions"),
                    active_conflicts=a["cdcl_stats"].get("conflicts"),
                    base_conflicts=b["cdcl_stats"].get("conflicts"),
                    active_propagations=a["cdcl_stats"].get("propagations"),
                    base_propagations=b["cdcl_stats"].get("propagations"),
                    comparable_decisions=match and bothsolved and decisions_measured,
                    comparable_conflicts=match and bothsolved and conflicts_measured,
                    live_unit_opportunities=a["live"].get("live_unit_opportunities",0))
                pairs.append(item)
        matched=[p for p in pairs if p["matched_candidates"]]
        meaningful=[p for p in matched if p["active_candidates"]>0]
        d=[p for p in meaningful if p["comparable_decisions"]]
        c=[p for p in meaningful if p["comparable_conflicts"]]
        def changes(pairs,field):
            arr=[p["active_"+field]-p["base_"+field] for p in pairs]
            return dict(paired=len(arr),
                lower=sum(x<0 for x in arr),
                higher=sum(x>0 for x in arr),
                tied=sum(x==0 for x in arr),
                total_delta=sum(arr),
                total_active=sum(p["active_"+field] for p in pairs),
                total_control=sum(p["base_"+field] for p in pairs))
        paired[label]=dict(attempts=len(pairs),
            candidate_matched=len(matched),
            candidate_mismatched=len(pairs)-len(matched),
            matched_with_nonempty_lemmas=len(meaningful),
            pairs_solved_same_verdict=sum(p["both_solved_same_verdict"]
                                          for p in matched),
            active_only_solved=sum(
              p["active_status"]!="TIMEOUT" and p["base_status"]=="TIMEOUT"
              for p in matched),
            control_only_solved=sum(
              p["base_status"]!="TIMEOUT" and p["active_status"]=="TIMEOUT"
              for p in matched),
            PAR2_active_s=round(sum(p["active_PAR2_s"] for p in matched),6),
            PAR2_control_s=round(sum(p["base_PAR2_s"] for p in matched),6),
            PAR2_benefit_s=round(sum(
                p["base_PAR2_s"]-p["active_PAR2_s"] for p in matched),6),
            decisions_among_matched_nonempty_both_solved=changes(d,"decisions"),
            conflicts_among_matched_nonempty_both_solved=changes(c,"conflicts"),
            note="CDCL counter comparisons exclude nonmatching candidates, missing stats, and mismatched/timeout outcomes",
            most_improved=[p for p in sorted(meaningful,
                          key=lambda x:x["PAR2_delta_s"])[:5]],
            worst_regressions=[p for p in sorted(meaningful,
                          key=lambda x:x["PAR2_delta_s"],reverse=True)[:5]])
    report=dict(protocol=PROTO,source_n=28,
       seen_original_SHA_n=24,synthetic_controls_n=4,
       trials=392,cap_s=CAP,reps=REPS,
       one_logical_cpu_pinned=True,
       no_auto_promotion=True,
       UNSAT_independent_LRAT=False,
       not_blind=True,source_cohort="reused EQUIV7",
       estimator="matched candidates: active ANF clauses vs otherwise identical shadow observer of actual CaDiCaL IPASIR-UP assignments",
       limitations="different CDCL trajectories and missing/timeout stats do NOT establish individual lemma causation; observer-only arm includes its own 200ms proof/gate preprocessing",
       result_validity="original CNF SAT witness replay, local exhaustive source lemma proofs, original SHA and exact 392 paired schedule",
       scores=scores,paired=paired,rows=rows)
    ROOT.mkdir(exist_ok=True)
    (ROOT/"report.json").write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
    print("DMD4test_FINAL",json.dumps({k:v for k,v in report.items() if k!="rows"},
                                  sort_keys=True),flush=True)
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("selftest","bench","audit"))
    p.add_argument("--shard",type=int,default=0)
    x=p.parse_args()
    if x.action=="selftest":selftest()
    elif x.action=="bench":bench(x.shard)
    else:audit()
