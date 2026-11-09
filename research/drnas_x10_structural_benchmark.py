#!/usr/bin/env python3
"""DRNAS X10 controlled cheap-structural-selection benchmark.

24 already-used official SAT Competition 2026 original CNFs, two source-disjoint
historical cohorts (C13/C14NV), two repetitions and five arms. Reuses exactly
pinned native CMS 5.11, Kissat 4.0.4 and CaDiCaL 1.7.3.
Source-only predictor frozen BEFORE any X10 timed execution. Features cost
included in each X10 E2E wall cap. NO claim of global blindness, new originals,
official competition ranking, or independent UNSAT LRAT.
"""
from __future__ import annotations
import argparse,collections,json,os,pathlib,random,shutil,subprocess,time
import drnas_x8_worldcup_mid16 as w
import drnas_x10_structural_profile as s

w.PROTO="DRNAS-X10-SHA24-C13-C14NV-5ARM-2REP-25S-STRUCTURE-SAMPLE-v1"
w.SRC=pathlib.Path("x10_sources")
w.OUT=pathlib.Path("x10_out")
w.CAP=25.0
w.REPS=2
w.SHARDS=8
w.MIN_READY=w.TARGET=24
w.ARMS=("cms_orig","kissat_404","cadical_173","x10_structural","x10_no_graph")
w.X8_BINARY=pathlib.Path("x10_bin/mre_x8/bin/native")
w.KISSAT=pathlib.Path("built/bin/kissat_4_0_4")
w.CADICAL=pathlib.Path("c8c/bin/plain")
C13=pathlib.Path("x10_prior_c13/c13_sources")
C14=pathlib.Path("c14nv_sources")
C13_SHA="e1563f7acb67bbbca4a8ff7d982e9c7e25c59e3a8b1941e6d660ae6cf1be45f3"
C14_SHA="73bd88baae02e65de28aa541e8e46e73ecbe2be89f0698ac2d0afaa9a7cf6712"
C13_PROTO="DRNAS-C13-2026-NEW12-6ARMS-3REPS-30S-E2E-v1"
C14_PROTO="DRNAS-C14NV-H2-NEW12-5ARM-2REP-30S-v1"

def need(ok,msg):w.need(ok,msg)
def freeze():
    w.SRC.mkdir(parents=True,exist_ok=True)
    selected=[]
    for cohort,origin,sha,proto in (
       ("historical_c13",C13,C13_SHA,C13_PROTO),
       ("historical_c14nv",C14,C14_SHA,C14_PROTO)):
        man=origin/"manifest.json"
        need(man.is_file() and w.digest(man)==sha,"source manifest SHA drift "+cohort)
        raw=json.loads(man.read_text())
        need(raw["protocol"]==proto and len(raw["cases"])==12,
             "source manifest protocol/number drift "+cohort)
        for c in raw["cases"]:
            p=origin/c["filename"]
            need(p.exists() and p.stat().st_size==c["bytes"] and
                 w.digest(p)==c["sha256"],"original CNF SHA drift")
            dest=w.SRC/(cohort+"-"+c["gbd"]+".cnf")
            shutil.copyfile(p,dest)
            features,seconds=s.probe(dest,c["nvars"],c["nclauses"])
            chosen,why=s.route(features,True)
            ablation,_=s.route(features,False)
            row=dict(cohort=cohort,gbd=c["gbd"],
                 sha256=c["sha256"],filename=dest.name,bytes=c["bytes"],
                 nvars=c["nvars"],nclauses=c["nclauses"],
                 reference=c["status"],official_ca3_s=None,
                 features=features,predicted_route=chosen,
                 prediction_reason=why,no_graph_route=ablation,
                 source_previously_evaluated=True)
            selected.append(row)
            print("X10_FEATURE",json.dumps(dict(cohort=cohort,gbd=c["gbd"],
                 reference=c["status"],sample_ms=round(seconds*1000,3),
                 binary=features["sample_binary_ratio"],
                 ternary=features["sample_ternary_ratio"],
                 degree_cv=features["occurrence_degree_cv"],
                 cyclic=features["implication_cyclic_fraction"],
                 scc=features["implication_largest_scc_fraction"],
                 xor4=features["xor4_groups"],
                 route=chosen,why=why),sort_keys=True),flush=True)
    need(len(selected)==24 and
         len({r["sha256"] for r in selected})==24 and
         len({r["gbd"] for r in selected})==24,
         "original cohort overlap or missing source")
    need(collections.Counter(r["cohort"] for r in selected)=={
         "historical_c13":12,"historical_c14nv":12},
         "unequal source cohorts")
    manifest=dict(protocol=w.PROTO,source_count=24,target=24,
       seed_repeats=w.REPS,cap_s=w.CAP,arms=list(w.ARMS),
       source_frozen_before_local_solver=True,cases=selected,
       frozen_feature_version=s.POLICY_VERSION,
       feature_budget_bytes=s.MAX_BYTES,
       original_C13_manifest_sha256=C13_SHA,
       original_C14NV_manifest_sha256=C14_SHA,
       no_training_on_test_time_or_winners=True,
       route_chosen_only_from_original_source=True,
       no_solver_preprobe=True,
       both_historical_not_blind=True,not_official_competition=True,
       independent_UNSAT_LRAT=False,no_auto_promotion=True)
    w.save(w.SRC/"manifest.json",manifest)
    (w.SRC/"source.sha256").write_text("".join(
        c["sha256"]+"  "+c["filename"]+"\n" for c in selected))
    print("X10_FROZEN",json.dumps(dict(sources=24,SAT=sum(x["reference"]=="SAT" for x in selected),
       UNSAT=sum(x["reference"]=="UNSAT" for x in selected),
       routes=dict(collections.Counter(x["predicted_route"] for x in selected)),
       SHA=w.digest(w.SRC/"manifest.json"))),flush=True)

def cases():
    a=w.cases()
    need(len(a)==24,"X10 wrong source count")
    for c in a:
        route,_=s.route(c["features"],True)
        route2,_=s.route(c["features"],False)
        need(route==c["predicted_route"] and route2==c["no_graph_route"],
             "precommitted policy drift")
    return a

def trial(c,rep,arm):
    original=w.SRC/c["filename"]
    need(w.digest(original)==c["sha256"],"original source drift")
    start=time.perf_counter()
    actual=arm;decision="fixed_control";profile_ms=0
    if arm in ("x10_structural","x10_no_graph"):
        f,profile_s=s.probe(original,c["nvars"],c["nclauses"])
        profile_ms=round(1000*profile_s,3)
        need(f==c["features"],"measured profile disagrees with frozen source")
        actual,decision=s.route(f,arm=="x10_structural")
        expected=(c["predicted_route"] if arm=="x10_structural"
                  else c["no_graph_route"])
        need(actual==expected,"route different from frozen preregistration")
    need(actual in ("cms_orig","kissat_404","cadical_173"),
         "unknown backend")
    if actual=="cms_orig":
        cmd=[str(w.X8_BINARY.resolve()),str(original.resolve()),"x_native",
             str(w.seed(c,rep))]
    else:
        cmd=[str((w.KISSAT if actual=="kissat_404" else w.CADICAL).resolve()),
             str(original.resolve())]
    env=os.environ.copy()
    for k in ("DRNAS_MAX_CONFLICTS","DRNAS_X7_TRACE","DRNAS_X8_TRACE",
              "DRNAS_C8I_EARLY_GATE16","DRNAS_C8I_GATE_TRACE"):
        env.pop(k,None)
    prep=time.perf_counter()-start
    remaining=w.CAP-(time.perf_counter()-start)
    proc=None
    if remaining>0:
        try:
            proc=subprocess.run(cmd,env=env,capture_output=True,text=True,
                      errors="replace",timeout=remaining,check=False)
        except subprocess.TimeoutExpired:
            pass
    wall=time.perf_counter()-start
    status="TIMEOUT";verified=False;stats=None
    if proc is not None:
        if actual=="cms_orig":
            need(proc.returncode==0,"CMS exited unexpectedly "+(proc.stderr or "")[-400:])
            status,model,stats=w.base.cms.parsed_native(proc.stdout)
            gate=w.base.parse_gate(proc.stdout,"x_native")
            need(not gate["applied"] and gate["clauses_removed"]==0,
                 "CMS unexpectedly transformed source")
        else:
            need(proc.returncode in (10,20),"reference backend failure")
            status,model=w.ref.external_parse(proc)
        need(status in ("SAT","UNSAT","TIMEOUT","UNKNOWN","BUDGET"),
             "invalid solver status")
        if status=="SAT":
            w.cms.verify_model(original,model)
            verified=True
        if status in ("SAT","UNSAT"):
            need(status==c["reference"],"published original SAT/UNSAT mismatch")
    if wall>w.CAP or status not in ("SAT","UNSAT"):
        status="TIMEOUT";verified=False
    return dict(protocol=w.PROTO,source_sha256=c["sha256"],gbd=c["gbd"],
       cohort=c["cohort"],reference=c["reference"],rep=rep,seed=w.seed(c,rep),
       arm=arm,route=actual,reason=decision,cap_s=w.CAP,
       status=status,PAR2_s=round(wall if status!="TIMEOUT" else 2*w.CAP,6),
       wall_s=round(wall,6),prep_s=round(prep,6),profile_ms=profile_ms,
       original_sha256_verified=True,SAT_original_witness_verified=verified,
       UNSAT_independent_LRAT=False,native_stats=stats,
       features_precommitted=True,no_runtime_solver_probe=True)

def shard(index):
    need(index in range(w.SHARDS),"invalid concurrent shard index")
    targets=[c for i,c in enumerate(cases()) if i%w.SHARDS==index]
    need(len(targets)==3,"unbalanced frozen source partitions")
    rows=[]
    w.OUT.mkdir(exist_ok=True)
    for c in targets:
        for rep in range(w.REPS):
            order=list(w.ARMS)
            random.Random(w.seed(c,rep)).shuffle(order)
            for arm in order:
                row=trial(c,rep,arm)
                rows.append(row)
                w.save(w.OUT/f"shard-{index}.json",rows)
                print("X10_TRIAL",json.dumps(row,sort_keys=True),flush=True)
    need(len(rows)==30,"incomplete X10 shard")
    print("X10_SHARD_PASS",index,len(rows),flush=True)

def scores(rows):
    return {arm:dict(n=len(group),
      solved=sum(x["status"]!="TIMEOUT" for x in group),
      SAT=sum(x["status"]=="SAT" for x in group),
      UNSAT_reference_only=sum(x["status"]=="UNSAT" for x in group),
      timeouts=sum(x["status"]=="TIMEOUT" for x in group),
      PAR2_s=round(sum(x["PAR2_s"] for x in group),6),
      profile_ms_sum=round(sum(x["profile_ms"] for x in group),3))
      for arm in w.ARMS
      for group in [[r for r in rows if r["arm"]==arm]]}

def audit():
    cc=cases();bysha={c["sha256"]:c for c in cc}
    rows=[]
    for i in range(w.SHARDS):
        path=w.OUT/f"shard-{i}.json"
        need(path.is_file(),"missing X10 shard")
        rr=json.loads(path.read_text())
        need(len(rr)==30,"incomplete shard JSON")
        rows.extend(rr)
    expected={(c["sha256"],rep,arm) for c in cc for rep in range(w.REPS) for arm in w.ARMS}
    got={(r["source_sha256"],r["rep"],r["arm"]) for r in rows}
    need(len(rows)==len(got)==len(expected) and got==expected,
         "incomplete original SHA pairing")
    for r in rows:
        c=bysha[r["source_sha256"]]
        need(r["protocol"]==w.PROTO and r["gbd"]==c["gbd"]
              and r["cohort"]==c["cohort"] and r["seed"]==w.seed(c,r["rep"]),
             "source/seed mismatch")
        backend=c["predicted_route"] if r["arm"]=="x10_structural" else (
            c["no_graph_route"] if r["arm"]=="x10_no_graph" else r["arm"])
        need(r["route"]==backend,"routing differs from freeze")
        if r["status"]=="TIMEOUT":
            need(r["PAR2_s"]==2*w.CAP,"timeout PAR2 invalid")
        else:
            need(r["status"]==c["reference"] and
                 abs(r["PAR2_s"]-r["wall_s"])<=0.000002,
                 "wrong solved status / clock")
            if r["status"]=="SAT":
                need(r["SAT_original_witness_verified"],"SAT model missing")
    score=scores(rows)
    cohorts={cohort:scores([r for r in rows if r["cohort"]==cohort])
             for cohort in ("historical_c13","historical_c14nv")}
    bykey={(r["source_sha256"],r["rep"],r["arm"]):r for r in rows}
    decisive=correct=cms_true=cms_selected=cms_tp=0
    correct_ng=0
    oracle_par2=0.0
    individual=[]
    for c in cc:
        sample=[]
        for rep in range(w.REPS):
            get=lambda arm:bykey[(c["sha256"],rep,arm)]
            candidates={a:get(a)["PAR2_s"] for a in
                        ("cms_orig","kissat_404","cadical_173")}
            best=min(candidates.values())
            oracle_par2+=best
            # 0.5 s tolerance avoids calling same-speed noise decisive.
            winners=[a for a,v in candidates.items() if v<=best+0.5]
            if best<2*w.CAP and len(winners)==1:
                decisive+=1
                correct+=int(get("x10_structural")["route"]==winners[0])
                correct_ng+=int(get("x10_no_graph")["route"]==winners[0])
            cms_win=bool(best<2*w.CAP and len(winners)==1 and winners[0]=="cms_orig")
            pred_cms=get("x10_structural")["route"]=="cms_orig"
            cms_true+=int(cms_win);cms_selected+=int(pred_cms)
            cms_tp+=int(cms_win and pred_cms)
            sample.append(dict(rep=rep,reference_PAR2=candidates,
                oracle_PAR2=best,unique_winner=winners[0] if len(winners)==1 and best<2*w.CAP else None,
                predicted=c["predicted_route"],no_graph=c["no_graph_route"],
                selector_PAR2=get("x10_structural")["PAR2_s"],
                ablated_PAR2=get("x10_no_graph")["PAR2_s"]))
        individual.append(dict(gbd=c["gbd"],cohort=c["cohort"],
            reference=c["reference"],features=c["features"],
            frozen_prediction=c["predicted_route"],
            no_graph_prediction=c["no_graph_route"],repeats=sample))
    classification=dict(
        decisive_pairs=decisive,correct_with_graph=correct,
        correct_without_graph=correct_ng,
        accuracy_with_graph=round(correct/decisive,6) if decisive else None,
        accuracy_without_graph=round(correct_ng/decisive,6) if decisive else None,
        cms_true_winner_pairs=cms_true,cms_selected_pairs=cms_selected,
        cms_true_positive_pairs=cms_tp,
        cms_precision=round(cms_tp/cms_selected,6) if cms_selected else None,
        cms_recall=round(cms_tp/cms_true,6) if cms_true else None,
        oracle_three_solver_PAR2_s=round(oracle_par2,6),
        selector_oracle_gap_s=round(score["x10_structural"]["PAR2_s"]-oracle_par2,6))
    report=dict(protocol=w.PROTO,source_count=24,seed_repeats=2,
       trials=len(rows),cap_s=w.CAP,score=score,by_cohort=cohorts,
       classification=classification,
       selected_routes=dict(collections.Counter(c["predicted_route"] for c in cc)),
       individual=individual,
       original_CNF_SHA_verified=True,SAT_models_original_checked=True,
       UNSAT_independent_LRAT=False,profiling_inside_E2E=True,
       existing_historical_C13_C14NV_not_new_not_blind=True,
       source_disjoint_cohorts=True,no_auto_promotion=True,
       policy_frozen_before_timing=True,not_official_ranking=True)
    w.save(w.OUT/"report.json",report)
    print("X10_FINAL",json.dumps({k:v for k,v in report.items() if k!="individual"},sort_keys=True),flush=True)

def selftest():
    s.selftest()
    a=s.route(dict(xor4_groups=2,xor4_clause_fraction=0.02,
                   sample_binary_ratio=0,sample_ternary_ratio=0,
                   occurrence_degree_cv=0),True)
    need(a[0]=="cms_orig","predictor XOR4 gate failed")
    print("X10_PIPELINE_SELFTEST_PASS",flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("selftest","freeze","verify","shard","audit"))
    p.add_argument("--shard",type=int,default=0)
    a=p.parse_args()
    if a.action=="selftest":selftest()
    elif a.action=="freeze":freeze()
    elif a.action=="verify":
        cs=cases();print("X10_VERIFY_PASS",len(cs),flush=True)
    elif a.action=="shard":shard(a.shard)
    else:audit()
