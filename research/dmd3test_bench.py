#!/usr/bin/env python3
"""DMD3test: ACTUAL CaDiCaL 2.1 CDCL trail via IPASIR-UP observer.

Local ANF lemmas from unchanged DMD1 pass independent exhaustive source-bag
proof replay. DMD2 live UP novelty gate can select a subset. Live observer
counts lemma unit opportunities on REAL solver assignment/backtrack callbacks,
but this is only OBSERVATIONAL, not proof of a new propagation. Active arms
add source-consequent clauses to native CaDiCaL before solving.
Six arms, 24 REUSED official CNFs plus 4 synthetic controls x 2 repeats:
336 single-logical-CPU full E2E attempts, cap 6 s per arm. No independent LRAT.
"""
from __future__ import annotations
import argparse,collections,json,os,pathlib,random,re,resource
import tempfile,time
import dmd1_bench as d1

PROTO="DRNAS-DMD3test-REAL-CDCL-TRAIL-24SEEN-4TOY-6ARMS-2REPS-6S-v1"
ARMS=("cadical_clean","cadical_shadow_all","cadical_active_all",
      "cadical_shadow_gate","cadical_active_gate","kissat_original")
REPS=2
SHARDS=4
CAP=6.0
ROOT=pathlib.Path("mre_dmd3test")
DMD1=ROOT/"bin/dmd1_anf"
GATE=ROOT/"bin/dmd2_gate"
LIVE=ROOT/"bin/dmd3test_live"
KISSAT=pathlib.Path("built/bin/kissat_4_0_4")
DMD1_MS=15
GATE_MS=60
d1.ROOT=ROOT
def need(ok,why):
    if not ok:raise RuntimeError("DMD3test_FAIL_CLOSED "+str(why))
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
    with tempfile.TemporaryDirectory(prefix="dmd3test-") as d:
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
        if arm in ("cadical_shadow_gate","cadical_active_gate") and proof["lemmas"]:
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
        elapsed=time.monotonic()-start
        remaining=CAP-elapsed
        if remaining>0.1:
            if arm=="kissat_original":
                rc,out,err,_,solver_cpu,timed=d1.run_process(
                    [KISSAT,source],remaining,pinned)
                if timed:outcome="TIMEOUT"
                else:outcome,witness=d1.outcome(rc,out,orig)
            else:
                mode={"cadical_clean":"clean","cadical_shadow_all":"shadow",
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
                    body=[x[len("DMD3TEST_RESULT "):] for x in out.splitlines()
                          if x.startswith("DMD3TEST_RESULT ")]
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
       stat_lines=stat_lines)
def selftest():
    need(LIVE.is_file() and DMD1.is_file() and GATE.is_file() and KISSAT.is_file(),
         "pinned executables missing")
    a=cases()
    need(len(a)==28 and len(ARMS)==6 and SHARDS==4,"benchmark matrix drift")
    toy=next(c for c in a if c["cohort"]=="synthetic_toy")
    sample=trial(toy,"cadical_active_gate",0)
    need(sample["status"]=="SAT" and sample["SAT_original_witness_verified"] and
         sample["DMD1_proof_replayed"],"live proof/reason smoke failed")
    print("DMD3test_SELFTEST_PASS",json.dumps(dict(
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
                print("DMD3test_TRIAL",json.dumps(r,sort_keys=True),flush=True)
    need(len(rows)==84,"shard incomplete")
    print("DMD3test_SHARD_PASS",shard,len(rows),flush=True)
def audit():
    selected=cases()
    rows=[]
    for shard in range(SHARDS):
        path=ROOT/f"shard-{shard}.json"
        need(path.is_file(),"missing shard "+str(shard))
        x=json.loads(path.read_text())
        need(len(x)==84,"shard trial count")
        rows+=x
    exp={(c["sha256"],rep,arm) for c in selected for rep in range(REPS) for arm in ARMS}
    keys={(r["original_sha256"],r["rep"],r["arm"]) for r in rows}
    need(len(rows)==len(keys)==len(exp)==336 and keys==exp,"missing/duplicate trial")
    for r in rows:
        need(r["protocol"]==PROTO and r["logical_cpu_budget"]==1 and
             r["cap_s"]==CAP,"protocol or core mismatch")
        need(r["status"] in ("SAT","UNSAT","TIMEOUT"),"invalid verdict")
        need(r["status"]!="SAT" or r["SAT_original_witness_verified"],
             "unverified original SAT")
        need(r["gate_selected"]<=r["dmd1_lemmas"],"gate admitted extra")
        if r["live"]:
            need(not r["live"]["callback_error"],"invalid trail callback")
    scores={}
    for arm in ARMS:
        a=[r for r in rows if r["arm"]==arm]
        metric=lambda k:sum(r["live"].get(k,0) for r in a)
        types={}
        for cohort in ("reused_equiv7_original","synthetic_toy"):
            subset=[r for r in a if r["cohort"]==cohort]
            types[cohort]=dict(n=len(subset),
                 solved=sum(r["status"]!="TIMEOUT" for r in subset),
                 PAR2_s=round(sum(r["PAR2_s"] for r in subset),6))
        scores[arm]=dict(trials=len(a),
          solved=sum(r["status"]!="TIMEOUT" for r in a),
          SAT_verified=sum(r["status"]=="SAT" for r in a),
          UNSAT_backend_no_LRAT=sum(r["status"]=="UNSAT" for r in a),
          PAR2_s=round(sum(r["PAR2_s"] for r in a),6),
          full_CPU_s=round(sum(r["full_cpu_s"] for r in a),6),
          proved_lemmas=sum(r["dmd1_lemmas"] for r in a),
          gate_lemmas=sum(r["gate_selected"] for r in a),
          live_observed_assignments=metric("observed_assignments"),
          live_unit_opportunities=metric("live_unit_opportunities"),
          live_unique_lemmas_activated=metric("unique_lemmas_activated"),
          live_events_in_first_100=metric("first_unit_in_first_100"),
          live_events_in_first_1000=metric("first_unit_in_first_1000"),
          live_backtracks=metric("backtracks"),
          sources_with_live_unit=sum(r["live"].get("live_unit_opportunities",0)>0 for r in a),
          cdcl_conflicts_sum=sum(r["cdcl_stats"].get("conflicts",0) for r in a),
          cdcl_decisions_sum=sum(r["cdcl_stats"].get("decisions",0) for r in a),
          cohorts=types)
    ref=scores["cadical_clean"]["PAR2_s"]
    for s in scores.values():
        s["PAR2_pct_vs_clean"]=round(100*(s["PAR2_s"]/ref-1),5)
    paired={}
    for arm in ARMS:
        if arm=="cadical_clean":continue
        wins=losses=ties=0
        for source in selected:
            sub=[r for r in rows if r["original_sha256"]==source["sha256"]]
            orig=sum(r["PAR2_s"] for r in sub if r["arm"]=="cadical_clean")
            test=sum(r["PAR2_s"] for r in sub if r["arm"]==arm)
            if test<orig-.05:wins+=1
            elif test>orig+.05:losses+=1
            else:ties+=1
        paired[arm]=dict(wins=wins,losses=losses,ties=ties)
    report=dict(protocol=PROTO,total_trials=len(rows),sources=28,
       official_sources_reused=24,synthetic_controls=4,source_blind=False,
       no_auto_promotion=True,one_logical_cpu_per_arm=True,
       original_SAT_witness_verified=True,UNSAT_independent_LRAT=False,
       live_definition="CaDiCaL IPASIR-UP assignment/backtrack callbacks, observed subset of variables in proved ANF clauses; a live unit opportunity is a clause with exactly one unassigned literal and all others false, NOT proved extra propagation",
       cdcl_stats_scope="native CaDiCaL solver global counters parsed when present, zero default is NOT a verified zero",
       scores=scores,paired=paired,rows=rows)
    (ROOT/"report.json").write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
    print("DMD3test_FINAL",json.dumps({k:v for k,v in report.items() if k!="rows"},sort_keys=True),flush=True)
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("selftest","bench","audit"))
    p.add_argument("--shard",type=int,default=0)
    x=p.parse_args()
    if x.action=="selftest":selftest()
    elif x.action=="bench":bench(x.shard)
    else:audit()
