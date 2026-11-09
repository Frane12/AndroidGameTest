#!/usr/bin/env python3
"""DMD6: source-only implication graph value versus DMD1/DMD2/DMD5 controls.

Seven? EIGHT preregistered independent one-core CaDiCaL/Kissat arms, 24
DMD5 transfer (historically seen EQUIV7) original SHAs x 2 reps x 8 arms,
6s full E2E; no dual-core and no model-based selector training on transfer.
Candidate implication lemmas must originate from the DMD1 independent
exhaustive source-bag proof; the graph only RANKS those clauses.

Native graph selects at most 1 or 3. DMD5's shape-only pattern is retained
as placebo. All observed structural novelty is a heuristic, NEVER a proof.
SAT models replayed on ORIGINAL CNF; UNSAT backend-only (no independent LRAT).
"""
from __future__ import annotations
import argparse,collections,hashlib,json,os,pathlib,random,resource,tempfile,time
import dmd5_ablation_transfer as prev

PROTO="DRNAS-DMD6-GRAPH-SCC-NOVELTY-VALUE-24SHA-8ARM-2REP-6S-v1"
ROOT=pathlib.Path("mre_dmd6")
SCOUT=ROOT/"bin/dmd6_graph"
REPS=2
SHARDS=4
CAP=6.0
SCOUT_MS=250
ARMS=("cadical_clean","kissat_original","dmd1_all","dmd2_gate",
      "dmd5_shape","dmd6_top1","dmd6_top3","dmd6_up1")
MODES={"dmd6_top1":"top1","dmd6_top3":"top3","dmd6_up1":"up1"}
prior="DMD5-transfer already evaluated the same 24 original SHA sources"
def need(ok,msg):
    if not ok:raise RuntimeError("DMD6_FAIL_CLOSED "+str(msg))
def configure():
    # Reuse immutable DMD5 native CaDiCaL binary and proof replay; never
    # mutate the predecessor source. All outputs use a separate root.
    prev.ROOT=ROOT
    prev.DMD1=ROOT/"bin/dmd1_anf"
    prev.GATE=ROOT/"bin/dmd2_gate"
    prev.LIVE=ROOT/"bin/dmd5_live"
    prev.d1.ROOT=ROOT
def roster():
    configure()
    train,hold=prev.read_cases()
    need(len(hold)==24 and train["sha256"] not in {x["sha256"] for x in hold},
         "transfer cohort or train separation drift")
    return train,hold
def hashfile(p):
    return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def bench_settings():
    train,hold=roster()
    return dict(protocol=PROTO,source_announcement="historically reused DMD5 transfer CNF; not a blind holdout",
        cases=[{"sha256":c["sha256"],"filename":c["filename"]} for c in hold],
        candidate_local_proof="independently enumerated DMD1 source groups",
        selector="fixed C++ SCC, source UP novelty, 2-hop fanout ranking",
        decisions="top1 score; top3 diverse; up1 requires UP novelty",
        training_excluded_SHA=train["sha256"],
        arms=ARMS,cap_s=CAP,reps=REPS,shards=SHARDS,
        expected_trials=24*REPS*len(ARMS),
        single_pinned_logical_cpu=True,UNSAT_independent_LRAT=False,
        no_auto_promotion=True)
def freeze():
    ROOT.mkdir(exist_ok=True)
    m=bench_settings()
    m["source_codes"]={s:hashfile("research/"+s) for s in (
        "dmd6_graph_benchmark.py","dmd6_implication_graph_value.cpp")}
    m["native_bins"]={s:hashfile(ROOT/"bin"/s) for s in (
        "dmd6_graph","dmd1_anf","dmd2_gate","dmd5_live")}
    (ROOT/"manifest.json").write_text(json.dumps(m,sort_keys=True,indent=2)+"\n")
    print("DMD6_FREEZE_PASS",json.dumps({k:v for k,v in m.items() if k!="cases"},sort_keys=True),flush=True)
def check():
    m=json.loads((ROOT/"manifest.json").read_text())
    b=bench_settings()
    for k in ("protocol","cases","arms","cap_s","reps","shards","expected_trials","training_excluded_SHA"):
        need(m[k]==(list(b[k]) if k=="arms" else b[k]),"frozen manifest drift "+k)
    for s,h in m["native_bins"].items():
        need(hashfile(ROOT/"bin"/s)==h,"native binary SHA changed "+s)
    for s,h in m["source_codes"].items():
        need(hashfile("research/"+s)==h,"source code SHA changed "+s)
    return m

def select_graph(case,work,source,aug,n,original,all_lemmas,mode,pinned):
    need(mode in MODES.values(),"unregistered graph policy")
    outpath=work/"dmd6_selected.cnf"
    cmd=[SCOUT,source,aug,outpath,mode,SCOUT_MS]
    rc,out,err,sec,pcpu,timed=prev.d1.run_process(cmd,1.5,pinned)
    if timed or rc!=0:
        need(not outpath.exists(),"abstaining graph selector emitted output")
        return [],{"abstained":True,"reason":"native_bounded_failure","error":err[-200:]},pcpu
    p="DMD6_GRAPH "
    found=[x[len(p):] for x in out.splitlines() if x.startswith(p)]
    need(len(found)==1,"graph telemetry missing")
    data=json.loads(found[0])
    need(data["source_only"] and data["policy"]==mode and
         data["source_vars"]==n and data["source_clauses"]==len(original) and
         data["candidate_count"]==len(all_lemmas) and
         data["scored_candidates"]<=data["candidate_count"],
         "graph selector input/protocol mismatch")
    ids=data["selected_indices"]
    need(data["selected"]==len(ids) and len(ids)==len(set(ids)) and
         len(ids)<=(3 if mode=="top3" else 1) and
         all(type(i)==int and 0<=i<len(all_lemmas) for i in ids),
         "graph selected an invalid candidate index")
    chosen=[all_lemmas[i] for i in ids]
    need(bool(chosen)==outpath.exists(),"selected CNF existence mismatch")
    if chosen:
        nn,cs=prev.d1.read_cnf(outpath)
        need(nn==n and cs==original+chosen,
             "graph selector changed source or appended unproved clause")
    if data["abstained"]:
        need(not chosen,"partial graph selection used after timeout")
    if mode=="up1" and ids:
        need(data["candidate_features"][ids[0]]["novel_up"]>0,
             "UP novelty precondition violated")
    return chosen,data,pcpu
def trial(case,arm,rep):
    need(arm in ARMS and rep in (0,1),"bad trial arm or rep")
    check()
    pinned=prev.core()
    os.sched_setaffinity(0,{pinned})
    source=pathlib.Path(case["path"])
    need(source.is_file() and prev.d1.sha(source)==case["sha256"],
         "original source SHA mismatch")
    start=time.monotonic()
    cpu_start=prev.used_cpu(resource.RUSAGE_CHILDREN)
    n,original=prev.d1.read_cnf(source)
    chosen=[]
    all_lemmas=[]
    gate_lemmas=[]
    stats={}
    telemetry={"policy":"none","selected_indices":[],"abstained":False}
    proof_replayed=False
    with tempfile.TemporaryDirectory(prefix="dmd6-") as d:
        work=pathlib.Path(d)
        if arm not in ("cadical_clean","kissat_original"):
            want_gate=arm=="dmd2_gate"
            nn,cc,proof,all_lemmas,gate_lemmas,gate_data,_=prev.discover(
                case,work,pinned,gate=want_gate)
            proof_replayed=True
            need(n==nn and original==cc,"preprocessing changed source CNF")
            if arm=="dmd1_all":chosen=all_lemmas
            elif arm=="dmd2_gate":chosen=gate_lemmas
            elif arm=="dmd5_shape":
                chosen=[c for c in all_lemmas if prev.shape(c)=="length2_pos1"]
            else:
                need(arm in MODES,"invalid graph arm")
                aug=work/"full.cnf"
                # DMD1 proof_replay already independently checked every
                # candidate and its exact original source prefix.
                if all_lemmas:
                    chosen,telemetry,_=select_graph(case,work,source,aug,n,
                        original,all_lemmas,MODES[arm],pinned)
                else:
                    telemetry={"policy":MODES[arm],"selected_indices":[],
                               "abstained":False,"reason":"no_source_proved_candidates"}
        status,verified,cdcl_stats,_=prev.solve(
            source,n,original,chosen,
            "kissat" if arm=="kissat_original" else "cadical",
            CAP,start,work,pinned)
    elapsed=time.monotonic()-start
    if status=="TIMEOUT" and elapsed>=CAP:elapsed=CAP
    need(status!="SAT" or verified,"original SAT model not replayed")
    return dict(protocol=PROTO,sha256=case["sha256"],filename=case["filename"],
       arm=arm,rep=rep,cohort="DMD5_transfer_reused_EQUIV7_original",
       cap_s=CAP,one_logical_cpu=True,pinned_cpu=pinned,
       status=status,original_SAT_verified=verified,UNSAT_independent_LRAT=False,
       e2e_s=round(elapsed,6),
       PAR2_s=round(elapsed if status!="TIMEOUT" else 2*CAP,6),
       cpu_s=round(prev.used_cpu(resource.RUSAGE_CHILDREN)-cpu_start,6),
       independent_local_proof_replayed=proof_replayed,
       derived_lemmmas=len(all_lemmas),gate_selected_lemmas=len(gate_lemmas),
       appended_lemmas=len(chosen),appended_shapes=dict(collections.Counter(
           prev.shape(c) for c in chosen)),
       original_lemma_clause_hash=prev.digest(chosen), # audit candidate identity
       graph=telemetry,cdcl_stats=cdcl_stats)
def selftest():
    need(all(pathlib.Path(p).is_file() for p in (
        SCOUT,prev.DMD1,prev.GATE,prev.LIVE,prev.KISSAT)),"missing executables")
    train,transfer=roster()
    with tempfile.TemporaryDirectory(prefix="dmd6-self-") as td:
        w=pathlib.Path(td)
        n,original,proof,all_l,gate_l,gate_data,_=prev.discover(
            train,w,prev.core(),gate=True)
        need(len(all_l)==13 and len(gate_l)==6,"training known source drift")
        graph={}
        for mode in MODES.values():
            selected,meta,_=select_graph(train,w,pathlib.Path(train["path"]),
               w/"full.cnf",n,original,all_l,mode,prev.core())
            need(meta["selected"]==len(selected),"selftest graph selection")
            graph[mode]={"selected":selected,
                         "score":meta.get("candidate_features",[]),
                         "graph_edges":meta.get("binary_implication_edges")}
            (w/"dmd6_selected.cnf").unlink(missing_ok=True)
    print("DMD6_GRAPH_TEST_PASS",json.dumps({
        "training_original":train["sha256"],"proof_lemmas":13,
        "gate_selected":6,"all_policy_graph":graph},sort_keys=True),flush=True)
    # Compile/module+source prior to frozen workflow; do not consume transfer.
def shard(i):
    need(0<=i<SHARDS,"invalid shard")
    m=check()
    train,hold=roster()
    items=hold[i::SHARDS]
    need(len(items)==6,"missing 6 source SHA per shard")
    rows=[]
    ROOT.mkdir(exist_ok=True)
    for c in items:
        for rep in range(REPS):
            arms=list(ARMS)
            random.Random(c["sha256"]+str(rep)+"dmd6").shuffle(arms)
            for arm in arms:
                x=trial(c,arm,rep)
                rows.append(x)
                (ROOT/f"shard-{i}.json").write_text(json.dumps(rows,sort_keys=True))
                print("DMD6_TRIAL",json.dumps(x,sort_keys=True),flush=True)
    need(len(rows)==96,"incomplete 6x2x8 shard")
    print("DMD6_SHARD_PASS",i,len(rows),flush=True)
def audit():
    m=check()
    train,hold=roster()
    rows=[]
    for i in range(SHARDS):
        path=ROOT/f"shard-{i}.json"
        need(path.is_file(),"missing shard "+str(i))
        group=json.loads(path.read_text())
        need(len(group)==96,"malformed shard size")
        rows+=group
    expected={(c["sha256"],r,arm) for c in hold for r in range(REPS)
              for arm in ARMS}
    found={(x["sha256"],x["rep"],x["arm"]) for x in rows}
    need(len(rows)==len(found)==len(expected)==384 and found==expected,
         "duplicate or missing original-SHA paired trial")
    summaries={}
    paired={}
    for r in rows:
        need(r["protocol"]==PROTO and r["one_logical_cpu"] and
             r["cap_s"]==CAP,"protocol/cpu cap mismatch")
        need(r["sha256"]!=train["sha256"],"training formula leaked")
        need(r["status"]!="SAT" or r["original_SAT_verified"],
             "unverified source SAT")
        need(r["appended_lemmas"]<=r["derived_lemmmas"],
             "more added clauses than locally justified")
    rowmap={(r["sha256"],r["rep"],r["arm"]):r for r in rows}
    for arm in ARMS:
        x=[r for r in rows if r["arm"]==arm]
        summaries[arm]=dict(trials=len(x),
          solved=sum(r["status"]!="TIMEOUT" for r in x),
          SAT_original_verified=sum(r["status"]=="SAT" for r in x),
          UNSAT_backend_only=sum(r["status"]=="UNSAT" for r in x),
          PAR2_s=round(sum(r["PAR2_s"] for r in x),6),
          total_cpu_s=round(sum(r["cpu_s"] for r in x),6),
          appended_lemmas=sum(r["appended_lemmas"] for r in x),
          cases_with_nonempty_lemmas=sum(r["appended_lemmas"]>0 for r in x),
          candidate_formula_count=sum(r["derived_lemmmas"]>0 for r in x),
          graph_abstentions=sum(r["graph"].get("abstained",False) for r in x),
          conflicts_reported=sum(r["cdcl_stats"].get("conflicts",0) for r in x),
          decisions_reported=sum(r["cdcl_stats"].get("decisions",0) for r in x),
          reportable_conflicts=sum("conflicts" in r["cdcl_stats"] for r in x),
          reportable_decisions=sum("decisions" in r["cdcl_stats"] for r in x))
        if arm in ("cadical_clean","kissat_original"):continue
        pairs=[]
        for c in hold:
            for rep in range(REPS):
                v=rowmap[(c["sha256"],rep,arm)]
                b=rowmap[(c["sha256"],rep,"cadical_clean")]
                pairs.append((v,b))
        eligible=[(a,b) for a,b in pairs if a["appended_lemmas"]>0]
        same=[(a,b) for a,b in eligible if a["status"]==b["status"] and
              a["status"]!="TIMEOUT" and "conflicts" in a["cdcl_stats"] and
              "conflicts" in b["cdcl_stats"]]
        paired[arm]=dict(
          full_paired=len(pairs),nonempty_clause_pairs=len(eligible),
          win_any_par2=sum(a["PAR2_s"]<b["PAR2_s"]-.02 for a,b in pairs),
          loss_any_par2=sum(a["PAR2_s"]>b["PAR2_s"]+.02 for a,b in pairs),
          same_verdict_solved_with_lemmas=len(same),
          nonempty_decisions_lower=sum(a["cdcl_stats"].get("decisions",0)<
             b["cdcl_stats"].get("decisions",0) for a,b in same),
          nonempty_conflicts_lower=sum(a["cdcl_stats"]["conflicts"]<
             b["cdcl_stats"]["conflicts"] for a,b in same),
          net_PAR2_benefit_s=round(sum(b["PAR2_s"]-a["PAR2_s"]
              for a,b in pairs),6),
          nonempty_source_examples=[dict(source=a["filename"],
             rep=a["rep"],lemmas=a["appended_lemmas"],status=a["status"],
             PAR2_diff_s=round(a["PAR2_s"]-b["PAR2_s"],6))
             for a,b in eligible][:15])
    ref=summaries["cadical_clean"]["PAR2_s"]
    for s in summaries.values():
        s["PAR2_speedup_x_vs_cadical"]=round(ref/s["PAR2_s"],6)
    report=dict(protocol=PROTO,total_trials=384,original_sha24=24,
      no_global_holdout=True,not_blind_reused_DMD5_transfer=True,
      training_excluded=True,freeze=m,
      one_logical_cpu_per_arm=True,CAP_s=CAP,REPS=REPS,
      independent_local_proof_replay=True,
      original_SAT_models_verified=True,UNSAT_independent_LRAT=False,
      graph_rank_is_heuristic_not_proof=True,no_auto_promotion=True,
      scores=summaries,paired=paired,rows=rows)
    (ROOT/"report.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print("DMD6_FINAL",json.dumps({k:v for k,v in report.items()
          if k not in ("rows","freeze")},sort_keys=True),flush=True)
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("selftest","freeze","shard","audit"))
    p.add_argument("--shard",type=int,default=0)
    a=p.parse_args()
    configure()
    if a.action=="selftest":selftest()
    elif a.action=="freeze":freeze()
    elif a.action=="shard":shard(a.shard)
    else:audit()
