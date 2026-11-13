#!/usr/bin/env python3
"""X5.7 Decision Trace on SAT-VERIFIED original SAT2024 REAL36 formulas.

Retrospective diagnostic, explicitly NOT independent validation or a causal
test of individual decisions. Original SAT selection is from previously
verified X5.7 evidence, locked by SHA before the trace run.
10 SAT originals x2 repeats x9 arms =180 solver executions.
All credited SAT models rechecked against original CNF, UNSAT proof checked.
"""
from __future__ import annotations
import argparse,collections,json,math,pathlib,random,shutil,subprocess,tempfile,time
import drnas_x57_chb_lrb_real36 as X57

B=X57.B
REPS=2
SHARDS=5
CAP=8.0
POLICIES=("VSIDS","CHB","LRB")
ARMS=tuple(f"{kind}_{p}" for p in POLICIES for kind in ("FROZEN","TRACEOFF","TRACEON"))
BINARIES={name:("build/drnas-x57" if name.startswith("FROZEN_") else
                "build/drnas-x57-decision") for name in ARMS}
DATA=pathlib.Path("x57_previous/x57_final/paired_trials.jsonl")
PROTO=pathlib.Path("x57_previous/x57_freeze/protocol.json")
TRACE_ENABLED={f"TRACEON_{p}" for p in POLICIES}
CONTROL_ARMS={f"FROZEN_{p}" for p in POLICIES}
METRICS=("decisions","conflicts","propagations","learnt","reduce_removed","binary_propagations")

def write(path,obj):
    p=pathlib.Path(path);p.parent.mkdir(exist_ok=True,parents=True)
    p.write_text(json.dumps(obj,indent=2,sort_keys=True)+"\n")

def emit(event,obj):
    print(event+" "+json.dumps(obj,sort_keys=True,separators=(",",":")),flush=True)

def select_originals():
    originals,manifest=X57.originals()
    old=json.loads(PROTO.read_text())
    assert manifest["manifest_sha256"]==old["original_manifest_sha256"]
    oldrows=[json.loads(x) for x in DATA.read_text().splitlines()]
    assert len(oldrows)==432
    grouped=collections.defaultdict(list)
    for row in oldrows:
        grouped[row["sha256"]].append(row)
    result=[]
    for src in originals:
        rows=grouped[src["sha256"]]
        assert len(rows)==12
        seen={(x["arm"],x["rep"]) for x in rows}
        assert len(seen)==12
        needed={"X55B_FROZEN","X57_VSIDS","X57_CHB","X57_LRB"}
        certified={x["arm"] for x in rows
                   if x["status"]=="SAT_VERIFIED" and x["accepted"]
                   and x["rep"] in (0,1)}
        selected=all(all(x["status"]=="SAT_VERIFIED" and x["accepted"]
                         for x in rows if x["arm"]==a) for a in needed)
        if selected:
            assert certified>=needed
            result.append(src)
    assert len(result)==10,[(s["id"],s["family"]) for s in result]
    return sorted(result,key=lambda x:x["id"]),manifest

def freeze():
    sources,manifest=select_originals()
    d={
       "version":"decision-trace-sat10-v1",
       "source":"SAT2024 REAL36 previously tested original CNFs",
       "previous_evidence_run":43418696306,
       "source_archive_run":43387395060,
       "previous_evidence_sha256":B.sha(DATA.read_bytes()),
       "original_manifest_sha256":manifest["manifest_sha256"],
       "source_ids":[s["id"] for s in sources],
       "sources":[{"id":s["id"],"sha256":s["sha256"],"family":s["family"]} for s in sources],
       "selection":"SAT VERIFIED by four previous X57 arms for both repetitions, retrospective and nonblind",
       "arms":list(ARMS),"cap_s":CAP,"repeats":REPS,"shards":SHARDS,
       "total_trials":len(sources)*REPS*len(ARMS),
       "binary_sha256":{a:B.sha(pathlib.Path(path).read_bytes()) for a,path in BINARIES.items()},
       "trace_sampling":{"first_decisions":4096,"stride_after":512,"max_rows":8192},
       "correctness":"all SAT witness values independently checked on original CNF; no unverified answers credited",
       "causal_claim":"none; trace is observational, same instance histories cannot isolate decision counterfactuals"
    }
    write("x57_trace_freeze/protocol.json",d)
    emit("X57_DT_FREEZE",d)

def parse_trace(path,policy,n,solved):
    lines=[json.loads(row) for row in path.read_text().splitlines()]
    assert lines and lines[0]["type"]=="meta"
    meta=lines[0]
    assert meta["schema"]=="x57-decision-trace-v1"
    assert meta["policy"]==policy and not meta["counterfactual_known"]
    assert meta["rows_retained"]==len(lines)-1
    assert meta["source_nvars"]==n
    if solved:assert meta["internal_result"]=="SAT"
    decisions=lines[1:];previous=0
    for d in decisions:
        assert d["type"]=="decision"
        assert previous<d["decision_id"]<=meta["total_decisions"]
        previous=d["decision_id"]
        assert 1<=d["chosen_variable"]<=n
        assert abs(d["chosen_literal"])==d["chosen_variable"]
        assert d["phase_sign"]==(1 if d["chosen_literal"]>0 else -1)
        assert d["decision_level"]>=1
        assert math.isfinite(d["score_at_selection"])
        assert not d["is_causal_effect_known"]
        if d["immediate_bcp_result"] in ("conflict","no_conflict","timeout"):
            assert d["immediate_bcp_propagations"]>=1
            assert d["immediate_bcp_implied"]>=0
        if d["immediate_conflict_learned_lbd"]>=0:
            assert d["immediate_bcp_result"]=="conflict"
            assert d["immediate_conflict_learned_size"]>=1
    return meta,decisions

def trial(src,arm,rep,tmp,archive):
    raw=pathlib.Path(src["path"]).read_bytes()
    assert B.sha(raw)==src["sha256"]
    n,clauses=B.parse_cnf(raw)
    out,err,usage,proof,trace=[tmp/f for f in
        ("stdout","stderr","time.usage","proof.drat","decision.jsonl")]
    for p in (out,err,usage,proof,trace):p.unlink(missing_ok=True)
    policy=arm.rsplit("_",1)[-1]
    cmd=[BINARIES[arm],str(src["path"]),"--mode","core","--time",str(CAP),
         "--stats","--x52-proof-deletions","--x53-policy","baseline",
         "--x57-branch",policy.lower(),"--proof",str(proof)]
    if arm in TRACE_ENABLED:cmd+=["--x57-decision-trace",str(trace)]
    rc,wall,expired,rss,cpu=B.run_process(cmd,out,err,usage,CAP+0.3)
    stdout=out.read_text(errors="replace");stderr=err.read_text(errors="replace")
    native={};x57={};write_stats={}
    for l in stderr.splitlines():
        if l.startswith("X41_STATS "):
            try:native=json.loads(l.split(" ",1)[1])
            except json.JSONDecodeError:pass
        if l.startswith("X57_STATS "):
            try:x57=json.loads(l.split(" ",1)[1])
            except json.JSONDecodeError:pass
        if l.startswith("X57_TRACE_WRITE "):
            try:write_stats=json.loads(l.split(" ",1)[1])
            except json.JSONDecodeError:pass
    state="timeout" if expired else "UNKNOWN"
    verify_time=0.
    if not expired:
        if rc==10:
            assert B.check_sat(stdout,clauses,n),("invalid SAT witness",src["id"],arm)
            state="SAT_VERIFIED"
        elif rc==20:
            # Dataset contains independently certified SAT models from prior run.
            # An actual UNSAT proof here would indicate a correctness contradiction.
            if not proof.exists():raise RuntimeError("UNSAT without proof file")
            t=time.perf_counter()
            ck=subprocess.run(["build/drat-trim",str(src["path"]),str(proof)],
                               capture_output=True,text=True,timeout=10)
            verify_time=time.perf_counter()-t
            raise RuntimeError(f"UNEXPECTED_UNSAT_ANSWER {src['id']} {arm} return={ck.returncode}")
        elif rc!=0:raise RuntimeError(f"unexpected process rc={rc} {arm} {src['id']}: {stderr[-500:]}")
    accepted=state=="SAT_VERIFIED" and wall<=CAP
    detail={}
    if arm in TRACE_ENABLED:
        assert not expired and trace.exists() and write_stats,("trace unavailable",src["id"],arm)
        meta,rows=parse_trace(trace,policy,n,accepted)
        assert native and meta["total_decisions"]==native["decisions"]
        assert meta["rows_retained"]<=8192
        dest=archive/f"{src['id']:03d}_{src['sha256'][:12]}_rep{rep}_{arm}.jsonl"
        shutil.copyfile(trace,dest)
        sizes=[d["immediate_conflict_learned_size"] for d in rows if d["immediate_conflict_learned_size"]>=0]
        lbd=[d["immediate_conflict_learned_lbd"] for d in rows if d["immediate_conflict_learned_lbd"]>=0]
        detail={
          "path":dest.name,"records":len(rows),"total_decisions":meta["total_decisions"],
          "dropped":meta["rows_dropped_due_to_cap"],
          "sampled_immediate_conflicts":sum(d["immediate_bcp_result"]=="conflict" for d in rows),
          "sampled_implied":sum(max(0,d["immediate_bcp_implied"]) for d in rows),
          "sampled_bcp_propagations":sum(max(0,d["immediate_bcp_propagations"]) for d in rows),
          "first_15_literals":[d["chosen_literal"] for d in rows[:15]],
          "immediate_learned_lbd":lbd,"immediate_learned_sizes":sizes,
          "trace_write_s":write_stats["trace_write_s"],
          "internal_solve_e2e_s":write_stats["solve_end_e2e_s"],
          "causal_effect_known":False,
        }
    elif trace.exists():
        raise RuntimeError("Trace was produced while not enabled")
    return {
      "source_id":src["id"],"source_sha256":src["sha256"],"family":src["family"],
      "rep":rep,"arm":arm,"status":state,"accepted":accepted,
      "PAR2_s":round(wall if accepted else 2*CAP,6),"wall_s":round(wall,6),
      "cpu_s":cpu,"maxrss_kib":rss,"proof_audit_s":round(verify_time,6),
      "native":native,"x57":x57,"trace":detail
    }

def run_shard(index):
    sources,_=select_originals()
    conf=json.loads(pathlib.Path("x57_trace_freeze/protocol.json").read_text())
    assert conf["source_ids"]==[s["id"] for s in sources]
    assert conf["previous_evidence_sha256"]==B.sha(DATA.read_bytes())
    for arm,path in BINARIES.items():
        assert B.sha(pathlib.Path(path).read_bytes())==conf["binary_sha256"][arm]
    chosen=[x for i,x in enumerate(sources) if i%SHARDS==index]
    assert len(chosen)==2
    folder=pathlib.Path("x57_trace_shards")/str(index)
    folder.mkdir(exist_ok=True,parents=True)
    traces=folder/"traces";traces.mkdir()
    with tempfile.TemporaryDirectory() as d,(folder/"trials.jsonl").open("w") as fd:
        tmp=pathlib.Path(d)
        for source in chosen:
            for rep in range(REPS):
                order=list(ARMS)
                random.Random(571713+source["id"]*51+rep).shuffle(order)
                bypolicy=collections.defaultdict(dict)
                for arm in order:
                    row=trial(source,arm,rep,tmp,traces)
                    fd.write(json.dumps(row,sort_keys=True,separators=(",",":"))+"\n");fd.flush()
                    emit("X57_DT_TRIAL",{k:row[k] for k in
                        ("source_id","family","rep","arm","accepted","status","PAR2_s","wall_s")})
                    bypolicy[arm.rsplit("_",1)[-1]][arm]=row
                # Explicit gate: for every source and seed, tracing itself
                # must preserve complete successful CDCL search counters.
                for p in POLICIES:
                    c=bypolicy[p]
                    assert len(c)==3
                    for metric in METRICS:
                        values=[c[f"{arm}_{p}"]["native"][metric]
                                for arm in ("FROZEN","TRACEOFF","TRACEON")]
                        assert len(set(values))==1,(source["id"],rep,p,metric,values)
                emit("X57_DT_PROGRESS",{"shard":index,"source_id":source["id"],"rep":rep})
    write(folder/"manifest.json",{
       "shard":index,"source_sha256":[x["sha256"] for x in chosen],
       "trial_count":len(chosen)*REPS*len(ARMS),
       "binary_sha256":conf["binary_sha256"],
       "original_manifest_sha256":conf["original_manifest_sha256"],
       "prior_evidence_sha256":conf["previous_evidence_sha256"],
    })
    emit("X57_DT_SHARD_FINAL",{"shard":index,"trials":len(chosen)*REPS*len(ARMS)})

def compare(rows,a,b):
    by=collections.defaultdict(list)
    for row in rows:by[row["source_sha256"]].append(row)
    differences=[]
    for sha,arr in sorted(by.items()):
        aa=[x for x in arr if x["arm"]==a]
        bb=[x for x in arr if x["arm"]==b]
        assert len(aa)==len(bb)==REPS
        differences.append(sum(x["PAR2_s"] for x in bb)-sum(x["PAR2_s"] for x in aa))
    gen=random.Random(571713)
    boot=sorted(sum(gen.choices(differences,k=len(differences))) for _ in range(5000))
    return {"delta_s":round(sum(differences),6),
            "source_cluster_bootstrap95":[round(boot[125],6),round(boot[4874],6)],
            "source_clusters":len(differences),"repeats_per_source":REPS}

def finish():
    sources,original=select_originals()
    conf=json.loads(pathlib.Path("x57_trace_freeze/protocol.json").read_text())
    assert conf["original_manifest_sha256"]==original["manifest_sha256"]
    allrows=[]
    for idx in range(SHARDS):
        folder=pathlib.Path("x57_trace_downloads")/f"x57dt-shard-{idx}"
        info=json.loads((folder/"manifest.json").read_text())
        assert info["shard"]==idx and info["binary_sha256"]==conf["binary_sha256"]
        assert info["prior_evidence_sha256"]==conf["previous_evidence_sha256"]
        batch=[json.loads(x) for x in (folder/"trials.jsonl").read_text().splitlines()]
        assert len(batch)==info["trial_count"]
        assert {r["source_sha256"] for r in batch}==set(info["source_sha256"])
        for row in batch:
            if row["arm"] in TRACE_ENABLED:
                trace=folder/"traces"/row["trace"]["path"]
                assert trace.exists() and trace.stat().st_size>0
                lines=[json.loads(l) for l in trace.read_text().splitlines()]
                assert len(lines)-1==row["trace"]["records"]
        allrows.extend(batch)
    needed={(s["sha256"],rep,a) for s in sources for rep in range(REPS) for a in ARMS}
    assert len(allrows)==len(needed)==180
    assert {(r["source_sha256"],r["rep"],r["arm"]) for r in allrows}==needed
    assert all(x["accepted"] and x["status"]=="SAT_VERIFIED" for x in allrows)
    # Gate frozen vs trace-enabled decisions on same instance, NOT only solved count.
    bycase=collections.defaultdict(dict)
    for row in allrows:bycase[(row["source_sha256"],row["rep"])][row["arm"]]=row
    for c in bycase.values():
        for policy in POLICIES:
            for m in METRICS:
                assert len({c[f"{kind}_{policy}"]["native"][m] for kind in
                            ("FROZEN","TRACEOFF","TRACEON")})==1,(policy,m)
    overall={}
    for a in ARMS:
        rr=[x for x in allrows if x["arm"]==a]
        overall[a]={
          "runs":len(rr),"SAT_verified":sum(x["accepted"] for x in rr),
          "PAR2_s":round(sum(x["PAR2_s"] for x in rr),6),
          "total_decisions":sum(x["native"]["decisions"] for x in rr),
          "total_conflicts":sum(x["native"]["conflicts"] for x in rr),
          "total_propagations":sum(x["native"]["propagations"] for x in rr),
          "maxrss_kib":max(x["maxrss_kib"] or 0 for x in rr),
          "trace_records":sum(x["trace"].get("records",0) for x in rr),
          "sampled_conflicts":sum(x["trace"].get("sampled_immediate_conflicts",0) for x in rr),
          "sampled_implied":sum(x["trace"].get("sampled_implied",0) for x in rr),
          "trace_write_s":round(sum(x["trace"].get("trace_write_s",0) for x in rr),6),
        }
    paired={a:{
       "trace_overhead_vs_same_binary":compare(allrows,f"TRACEOFF_{a}",f"TRACEON_{a}"),
       "recompile_vs_frozen":compare(allrows,f"FROZEN_{a}",f"TRACEOFF_{a}")
    } for a in POLICIES}
    report={
      "status":"COMPLETE","protocol":conf,"overall":overall,
      "paired":paired,
      "by_original":[{
         "id":s["id"],"sha256":s["sha256"],"family":s["family"],
         "arms":{a:{
             "SAT_verified":sum(r["accepted"] for r in allrows if r["source_sha256"]==s["sha256"] and r["arm"]==a),
             "total_decisions":sum(r["native"]["decisions"] for r in allrows if r["source_sha256"]==s["sha256"] and r["arm"]==a),
             "total_conflicts":sum(r["native"]["conflicts"] for r in allrows if r["source_sha256"]==s["sha256"] and r["arm"]==a),
             "total_PAR2_s":round(sum(r["PAR2_s"] for r in allrows if r["source_sha256"]==s["sha256"] and r["arm"]==a),6),
             "sampled_implied":sum(r["trace"].get("sampled_implied",0) for r in allrows if r["source_sha256"]==s["sha256"] and r["arm"]==a),
         } for a in ARMS}
      } for s in sources],
      "limitations":[
        "Sources selected from prior known SAT answers; this is diagnostic retrospective, not a blind holdout.",
        "9/10 source families are SIMON; do not generalize winner to broad SAT.",
        "Immediate BCP outcome and learned LBD describe what happened next, not causal benefit of the decision.",
        "Tracing changes measured end-to-end wall time via serialization; use paired on/off overhead and frozen off for primary timing.",
        "Rows sampled all first 4096 decisions, then 1/512 with max 8192, not an exhaustive trace for hard formulas.",
        "No global memory, learning, action on solver decisions or promotion."
      ]
    }
    out=pathlib.Path("x57_trace_final");out.mkdir(exist_ok=True)
    write(out/"report.json",report)
    (out/"paired_trials.jsonl").write_text("".join(json.dumps(r,sort_keys=True)+"\n" for r in allrows))
    emit("X57_DT_FINAL",{"status":"COMPLETE","overall":overall,
                          "paired":paired,"sources":len(sources)})

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("stage",choices=("freeze","shard","finish"))
    ap.add_argument("--shard",type=int,default=0)
    opts=ap.parse_args()
    if opts.stage=="freeze":freeze()
    elif opts.stage=="shard":run_shard(opts.shard)
    else:finish()
if __name__=="__main__":main()
