#!/usr/bin/env python3
"""X5.8: SAT-witness-only decision audit vs DRAT-enabled same fixed policies.

Focused retrospective diagnosis: known REAL36-excluded SAT2024 originals
1 Break, 3 worker, 12 pcmax, 18 RBSAT, 19 circuit. Selection deliberately
uses earlier X57 scheduling results, NOT a blind holdout or promotion gate.

5 sources x 2 repetitions x 11 arms = 110 attempts. 25s solve wall cap.
Never accept UNSAT without an independent DRAT proof. SAT-only explicitly
downgrades internal UNSAT to UNKNOWN in the C++ executable.
"""
from __future__ import annotations
import argparse,collections,hashlib,json,pathlib,random,shutil,subprocess,tempfile,time
import drnas_x55_cpu_real36 as B

CAP=25.0
REPEATS=2
SELECTED_IDS=(1,3,12,18,19)
SHARDS=5
POLICIES=("VSIDS","CHB","LRB")
ARMS=tuple(f"{p}_{mode}" for p in POLICIES for mode in ("PROOF","SAT","TRACE"))+("KISSAT_SAT","CADICAL_SAT")
MANIFEST=pathlib.Path("x57_sched_unseen/manifest.json")
PREVIOUS_PROTOCOL=pathlib.Path("x57_sched_unseen/protocol.json")
ROOT=pathlib.Path("x58_frozen")
EXPECTED_SHA={
  1:"07bd5783f72508875b81075784d0e7e8b21ac5b375c7883ae4c9805f2458ff5a",
  3:"2a5259eab7f161306a39de59e2b058d41d49b881988a31002d3611d7dc320747",
  12:"a8db593056c6fe4445d6f81b232bc781c1917cd624fefff5b33bd818cd44a123",
  18:"4a3dde8588b06f42b73b96ba1e610a4b23d8cd239d44d17981c0638911c77aee",
  19:"d3338c04e29f5c8b7e75686fa30fd9927babb7b34b9f7c87785397662f59d8e2",
}
PURPOSE={
  1:"Break scheduling: previously fast SAT positive control",
  3:"worker scheduling: previous 512 MiB DRAT cap",
  12:"pcmax scheduling: harder SAT-labelled original (label never trusted)",
  18:"RBSAT: prior frozen VSIDS SAT but CHB and LRB failed",
  19:"circuit: prior Kissat and CaDiCaL SAT but DRNAS failed",
}

def sha(data):return hashlib.sha256(data).hexdigest()
def save(path,obj):
    p=pathlib.Path(path);p.parent.mkdir(exist_ok=True,parents=True)
    p.write_text(json.dumps(obj,sort_keys=True,indent=2)+"\n")
def emit(tag,obj):
    print(tag+" "+json.dumps(obj,sort_keys=True,separators=(",",":")),flush=True)

def sources():
    original=json.loads(MANIFEST.read_text())
    old=json.loads(PREVIOUS_PROTOCOL.read_text())
    assert original["schema"]=="x57-sched-original-v1" and len(original["sources"])==20
    assert old["schema"]=="x57-sched-freeze-v1"
    assert old["source_manifest_sha256"]==sha(MANIFEST.read_bytes())
    allsources={x["id"]:x for x in original["sources"]}
    chosen=[]
    for id in SELECTED_IDS:
        a=allsources[id]
        if a["sha256"]!=EXPECTED_SHA[id]:raise RuntimeError(f"X58 wrong frozen SHA id={id}")
        if sha(pathlib.Path(a["path"]).read_bytes())!=a["sha256"]:
            raise RuntimeError(f"X58 source bytes changed id={id}")
        chosen.append(a)
    return chosen,original

def bins():
    return {
      "X58":"build/drnas-x58","X57_FROZEN":"build/drnas-x57",
      "KISSAT":"build/kissat","CADICAL":"build/cadical",
      "DRAT_TRIM":"build/drat-trim"}

def freeze():
    chosen,original=sources()
    p={
      "schema":"x58-sat-decision-audit-v1",
      "prior_run":43434020900,"original_manifest_sha256":sha(MANIFEST.read_bytes()),
      "source_ids":list(SELECTED_IDS),
      "source_sha256":[x["sha256"] for x in chosen],
      "purpose":PURPOSE,
      "selection":"purposefully selected based on previously revealed X57 outcomes: exploratory only",
      "globally_blind":False,"new_holdout":False,
      "cap_s":CAP,"repeats":REPEATS,"shards":SHARDS,"total_trials":len(chosen)*REPEATS*len(ARMS),
      "arms":list(ARMS),
      "binary_sha256":{name:sha(pathlib.Path(path).read_bytes()) for name,path in bins().items()},
      "SAT_ONLY":"no proof output, external witness verification required; UNSAT -> UNKNOWN",
      "PROOF":"normal DRAT writing with proof-size cap, independent DRAT check for UNSAT",
      "TRACE":"SAT-only plus bounded observational chosen-variable and BCP/LBD trace",
      "attribution":"same fixed branching policy; no online training, no automatic promotion",
      "cpu":"serial arm invocations pinned to one logical CPU, five independent jobs",
      "PAR2":"50 seconds on timeout or answer without an independent certificate",
    }
    save(ROOT/"protocol.json",p)
    emit("X58_FREEZE",p)

def run_one(src,rep,arm,tmp,tracefolder):
    f=pathlib.Path(src["path"]);raw=f.read_bytes()
    assert sha(raw)==src["sha256"]
    n,clauses=B.parse_cnf(raw)
    out,err,usage,proof,trace=(tmp/x for x in ("stdout","stderr","usage","proof.drat","decisions.jsonl"))
    for p in (out,err,usage,proof,trace):p.unlink(missing_ok=True)
    is_ref=arm in ("KISSAT_SAT","CADICAL_SAT")
    is_trace=arm.endswith("_TRACE")
    is_proof=arm.endswith("_PROOF")
    mode=("TRACE" if is_trace else "PROOF" if is_proof else "SAT_ONLY")
    policy=arm.split("_",1)[0]
    if not is_ref:
        cmd=["build/drnas-x58",str(f),"--mode","core","--time",str(CAP),
             "--stats","--x52-proof-deletions","--x53-policy","baseline",
             "--x53-progress","--x57-branch",policy.lower()]
        if is_proof:cmd+=["--proof",str(proof)]
        else:
            cmd+=["--x58-sat-only"]
            if is_trace:cmd+=["--x57-decision-trace",str(trace)]
    elif arm=="KISSAT_SAT":
        cmd=["build/kissat",str(f)]
    else:cmd=["build/cadical","-q","--no-binary",str(f)]
    rc,wall,expired,rss,cpu=B.run_process(cmd,out,err,usage,CAP+0.3)
    stdout=out.read_text(errors="replace")
    stderr=err.read_text(errors="replace")
    native={};x58={};x57={};trace_write={}
    lastprogress={}
    for line in stderr.splitlines():
        if line.startswith("X41_STATS "):
            try:native=json.loads(line.split(" ",1)[1])
            except json.JSONDecodeError:pass
        if line.startswith("X58_SAT_ONLY "):
            try:x58=json.loads(line.split(" ",1)[1])
            except json.JSONDecodeError:pass
        if line.startswith("X57_STATS "):
            try:x57=json.loads(line.split(" ",1)[1])
            except json.JSONDecodeError:pass
        if line.startswith("X57_PROGRESS "):
            try:lastprogress=json.loads(line.split(" ",1)[1])
            except json.JSONDecodeError:pass
        if line.startswith("X57_TRACE_WRITE "):
            try:trace_write=json.loads(line.split(" ",1)[1])
            except json.JSONDecodeError:pass
    if not is_ref and not is_proof and not expired and rc in (0,10):
        if not x58 or not x58["enabled"] or not x58["proof_disabled"]:
            raise RuntimeError(f"SAT-only option not active for {arm} id={src['id']}")
        if x58["policy"]!=policy or x58["UNSAT_without_proof_credited"] is not False:
            raise RuntimeError(f"Incorrect SAT-only metadata {x58}")
        if x58["internal_status"]=="UNSAT" and (rc!=0 or x58["reported_status"]!="UNKNOWN"):
            raise RuntimeError("Unverified UNSAT was not downgraded to UNKNOWN")
        if proof.exists():raise RuntimeError("Unexpected proof output in SAT-only mode")
    status="timeout" if expired else "UNKNOWN"
    proof_checked_s=0.0
    if not expired:
        if rc==10:
            if not B.check_sat(stdout,clauses,n):
                raise RuntimeError(f"INVALID SAT witness source={src['id']} arm={arm}")
            status="SAT_VERIFIED"
        elif rc==20:
            if not is_proof:
                raise RuntimeError(f"UNSAFE UNSAT without DRAT id={src['id']} arm={arm}")
            if not proof.exists() or proof.stat().st_size==0:
                raise RuntimeError("UNSAT result without nonempty proof")
            tick=time.perf_counter()
            try:
                v=subprocess.run(["build/drat-trim",str(f),str(proof)],
                     capture_output=True,text=True,timeout=20)
                proof_checked_s=time.perf_counter()-tick
                if v.returncode==0 and "s VERIFIED" in v.stdout:
                    status="UNSAT_CERTIFIED"
                else:
                    raise RuntimeError(f"UNSAT proof failed id={src['id']} arm={arm}: {v.stdout[-300:]}")
            except subprocess.TimeoutExpired:
                proof_checked_s=time.perf_counter()-tick
                status="UNSAT_CHECK_TIMEOUT"
        elif rc==0:
            if x58.get("internal_status")=="UNSAT":
                status="UNSAT_UNVERIFIED_DOWNGRADED"
            else:status="UNKNOWN"
        elif is_proof and proof.exists() and proof.stat().st_size>=512*1024*1024-4096:
            status="PROOF_FILE_LIMIT"
        else:
            raise RuntimeError(f"unexpected exit code rc={rc} arm={arm} id={src['id']}: {stderr[-700:]}")
    accepted=wall<=CAP and status in ("SAT_VERIFIED","UNSAT_CERTIFIED")
    detail={}
    if is_trace and trace.exists():
        rows=[json.loads(line) for line in trace.read_text().splitlines()]
        if not rows or rows[0]["schema"]!="x57-decision-trace-v1" or rows[0]["policy"]!=policy:
            raise RuntimeError("Unexpected decision trace schema or policy")
        if rows[0]["rows_retained"]!=len(rows)-1 or not rows[0]["observational_only"]:
            raise RuntimeError("Trace integrity failure")
        for row in rows[1:]:
            if row["type"]!="decision" or row["is_causal_effect_known"]:
                raise RuntimeError("Causal label erroneously asserted")
        dest=tracefolder/f"{src['id']:02d}_{src['sha256'][:12]}_rep{rep}_{arm}.jsonl"
        shutil.copyfile(trace,dest)
        detail={
          "path":dest.name,"rows":len(rows)-1,
          "total_decisions":rows[0]["total_decisions"],
          "first_16_literals":[x["chosen_literal"] for x in rows[1:17]],
          "immediate_conflicts":sum(x["immediate_bcp_result"]=="conflict" for x in rows[1:]),
          "immediate_learned_lbd":[x["immediate_conflict_learned_lbd"] for x in rows[1:]
                                   if x["immediate_conflict_learned_lbd"]>=0],
          "trace_write_s":trace_write.get("trace_write_s"),
          "solve_pre_trace_s":trace_write.get("solve_end_e2e_s"),
        }
    if is_trace and accepted and not detail:
        raise RuntimeError(f"SAT completed with no trace id={src['id']} arm={arm}")
    return {
      "id":src["id"],"sha256":src["sha256"],"source_name":src["source_name"],
      "family":src["family"],"rep":rep,"arm":arm,"policy":policy,"mode":mode,
      "status":status,"accepted":accepted,
      "PAR2_s":round(wall if accepted else 2*CAP,6),"wall_s":round(wall,6),
      "cpu_s":cpu,"maxrss_kib":rss,"proof_size_bytes":proof.stat().st_size if proof.exists() else 0,
      "check_s":round(proof_checked_s,6),"native":native,"x57":x57,"x58":x58,
      "progress":lastprogress,"trace":detail,
    }

def shard(index):
    selected,_=sources()
    frozen=json.loads((ROOT/"protocol.json").read_text())
    assert frozen["source_ids"]==list(SELECTED_IDS)
    assert frozen["original_manifest_sha256"]==sha(MANIFEST.read_bytes())
    for k,v in bins().items():
        if sha(pathlib.Path(v).read_bytes())!=frozen["binary_sha256"][k]:
            raise RuntimeError(f"Binary SHA mismatch {k}")
    src=selected[index]
    path=pathlib.Path("x58_shards")/str(index)
    path.mkdir(parents=True,exist_ok=False)
    traces=path/"traces";traces.mkdir()
    with tempfile.TemporaryDirectory() as d,(path/"trials.jsonl").open("w") as fd:
        tmp=pathlib.Path(d)
        for rep in range(REPEATS):
            shuffled=list(ARMS)
            random.Random(581113+src["id"]*109+rep).shuffle(shuffled)
            rows={}
            for arm in shuffled:
                row=run_one(src,rep,arm,tmp,traces)
                rows[arm]=row
                fd.write(json.dumps(row,sort_keys=True,separators=(",",":"))+"\n")
                fd.flush()
                emit("X58_TRIAL",{k:row[k] for k in ("id","rep","arm","status","accepted",
                                                    "PAR2_s","wall_s","cpu_s","maxrss_kib")})
            for p in POLICIES:
                # Exact branch mechanics must agree when all matched variants
                # fully solve SAT. If any cap is hit we cannot claim equality.
                a,b,c=(rows[f"{p}_{mode}"] for mode in ("PROOF","SAT","TRACE"))
                if all(x["accepted"] and x["status"]=="SAT_VERIFIED" for x in (a,b,c)):
                    for key in ("decisions","conflicts","propagations","learnt",
                                "reduce_removed","binary_propagations"):
                        assert len({x["native"][key] for x in (a,b,c)})==1,(
                            "unexpected search difference",src["id"],rep,p,key)
            emit("X58_PROGRESS",{"id":src["id"],"rep":rep,"shard":index})
    save(path/"manifest.json",{
       "source_id":src["id"],"source_sha256":src["sha256"],"shard":index,
       "attempts":len(ARMS)*REPEATS,
       "source_manifest_sha256":frozen["original_manifest_sha256"],
       "binary_sha256":frozen["binary_sha256"]
    })
    emit("X58_SHARD_FINAL",{"shard":index,"id":src["id"],"trials":len(ARMS)*REPEATS})

def summary(rows):
    result={}
    for arm in ARMS:
        v=[r for r in rows if r["arm"]==arm]
        result[arm]={
          "attempts":len(v),"SAT_verified":sum(r["status"]=="SAT_VERIFIED" and r["accepted"] for r in v),
          "UNSAT_certified":sum(r["status"]=="UNSAT_CERTIFIED" and r["accepted"] for r in v),
          "proof_file_limit":sum(r["status"]=="PROOF_FILE_LIMIT" for r in v),
          "unverified_unsat_downgraded":sum(r["status"]=="UNSAT_UNVERIFIED_DOWNGRADED" for r in v),
          "PAR2_s":round(sum(r["PAR2_s"] for r in v),6),
          "wall_s":round(sum(r["wall_s"] for r in v),6),
          "cpu_s":round(sum(r["cpu_s"] or 0 for r in v),6),
          "cpu_missing":sum(r["cpu_s"] is None for r in v),
          "maxrss_kib":max((r["maxrss_kib"] or 0 for r in v),default=0),
          "decisions_observed":sum((r["native"] or r["progress"]).get("decisions",0) for r in v),
          "conflicts_observed":sum((r["native"] or r["progress"]).get("conflicts",0) for r in v),
          "traced_decision_rows":sum(r["trace"].get("rows",0) for r in v),
          "trace_write_s":round(sum(r["trace"].get("trace_write_s") or 0 for r in v),6),
        }
    return result

def bootstrap(rows,base,other):
    groups=collections.defaultdict(list)
    for r in rows:groups[r["sha256"]].append(r)
    paired=[]
    for key,rr in sorted(groups.items()):
        a=[x for x in rr if x["arm"]==base]
        b=[x for x in rr if x["arm"]==other]
        assert len(a)==len(b)==REPEATS
        paired.append(sum(x["PAR2_s"] for x in b)-sum(x["PAR2_s"] for x in a))
    rng=random.Random(581113)
    samples=sorted(sum(rng.choices(paired,k=len(paired))) for _ in range(5000))
    return {"delta_candidate_minus_reference_s":round(sum(paired),6),
            "cluster_bootstrap95":[round(samples[125],6),round(samples[4874],6)],
            "distinct_original_sources":len(paired),
            "warning":"Only five source clusters; exploratory, low confidence"}

def divergence(decisionA,decisionB):
    a={r["decision_id"]:r for r in decisionA[1:] if r["type"]=="decision"}
    b={r["decision_id"]:r for r in decisionB[1:] if r["type"]=="decision"}
    ids=sorted(set(a)&set(b))
    for d in ids:
        if a[d]["chosen_literal"]!=b[d]["chosen_literal"]:
            return {
              "first_observed_decision":d,
              "exact_first_divergence":d<=4096 and all(x in a and x in b for x in range(1,d+1)),
              "VSIDS":{"lit":a[d]["chosen_literal"],"score":a[d]["score_at_selection"],
                       "bcp":a[d]["immediate_bcp_result"],
                       "learned_lbd":a[d]["immediate_conflict_learned_lbd"]},
              "other":{"lit":b[d]["chosen_literal"],"score":b[d]["score_at_selection"],
                       "bcp":b[d]["immediate_bcp_result"],
                       "learned_lbd":b[d]["immediate_conflict_learned_lbd"]},
              "counterfactual_effect_known":False
            }
    return {"first_observed_decision":None,"no_observed_difference_in_shared_samples":True,
            "note":"Sampling beyond 4096 makes late divergence non-exhaustive"}

def finish():
    selected,_=sources()
    protocol=json.loads((ROOT/"protocol.json").read_text())
    rows=[]
    trace_files={}
    for index,src in enumerate(selected):
        folder=pathlib.Path("x58_downloads")/f"x58-shard-{index}"
        conf=json.loads((folder/"manifest.json").read_text())
        assert conf["shard"]==index and conf["source_id"]==src["id"]
        assert conf["source_sha256"]==src["sha256"]
        assert conf["source_manifest_sha256"]==protocol["original_manifest_sha256"]
        assert conf["binary_sha256"]==protocol["binary_sha256"]
        rr=[json.loads(x) for x in (folder/"trials.jsonl").read_text().splitlines()]
        assert len(rr)==len(ARMS)*REPEATS
        for r in rr:
            if r["trace"].get("path"):
                tr=(folder/"traces"/r["trace"]["path"])
                if not tr.exists():raise RuntimeError("missing decision trace file: "+str(tr))
                raw=[json.loads(l) for l in tr.read_text().splitlines()]
                assert len(raw)-1==r["trace"]["rows"]
                trace_files[(r["id"],r["rep"],r["policy"])]=raw
        rows.extend(rr)
    expected={(s["sha256"],rep,arm) for s in selected for rep in range(REPEATS) for arm in ARMS}
    assert len(rows)==len(expected)==110
    assert {(r["sha256"],r["rep"],r["arm"]) for r in rows}==expected
    for src in selected:
        proved={r["status"][:3] for r in rows if r["sha256"]==src["sha256"] and r["accepted"]}
        assert len(proved)<=1,("contradictory certified results",src["id"],proved)
    divergent=[]
    for s in selected:
        for rep in range(REPEATS):
            b=trace_files.get((s["id"],rep,"VSIDS"))
            if b:
                for p in ("CHB","LRB"):
                    a=trace_files.get((s["id"],rep,p))
                    if a:divergent.append({
                       "id":s["id"],"source_name":s["source_name"],"rep":rep,
                       "vs":p,"divergence":divergence(b,a)})
    out=pathlib.Path("x58_final")
    out.mkdir(exist_ok=True)
    report={
        "status":"COMPLETE","protocol":protocol,
        "overall":summary(rows),
        "by_source":[{
          "id":s["id"],"name":s["source_name"],"family":s["family"],
          "sha256":s["sha256"],
          "arms":summary([r for r in rows if r["id"]==s["id"]])
        } for s in selected],
        "paired":{
           "CHB_sat_vs_VSIDS_sat":bootstrap(rows,"VSIDS_SAT","CHB_SAT"),
           "LRB_sat_vs_VSIDS_sat":bootstrap(rows,"VSIDS_SAT","LRB_SAT"),
           "VSIDS_proof_overhead":bootstrap(rows,"VSIDS_SAT","VSIDS_PROOF"),
           "CHB_proof_overhead":bootstrap(rows,"CHB_SAT","CHB_PROOF"),
           "LRB_proof_overhead":bootstrap(rows,"LRB_SAT","LRB_PROOF"),
           "VSIDS_trace_overhead":bootstrap(rows,"VSIDS_SAT","VSIDS_TRACE"),
           "CHB_trace_overhead":bootstrap(rows,"CHB_SAT","CHB_TRACE"),
           "LRB_trace_overhead":bootstrap(rows,"LRB_SAT","LRB_TRACE"),
        },
        "first_observed_divergences":divergent,
        "limitations":[
           "Five purposively selected previously evaluated originals; NOT a blind SAT benchmark.",
           "SAT only credits externally checked original-CNF witness; UNSAT without DRAT is explicitly UNKNOWN.",
           "No-proof execution eliminates proof I/O; it does not imply faster search decisions.",
           "First observed path divergence is not a causal counterfactual due to differing prior solver states.",
           "Decision trace first 4096 decisions, then every 512 up to 8192 rows; late divergence may be missed.",
           "Trace-enabled wall time includes tracing and JSONL serialization; compare SAT mode without trace.",
           "Five original source clusters insufficient for general-purpose improvement claims.",
           "Frozen VSIDS remains default; no policy promotion or modification to main."
        ]
    }
    save(out/"report.json",report)
    (out/"trials.jsonl").write_text("".join(json.dumps(r,sort_keys=True)+"\n" for r in rows))
    emit("X58_FINAL",{
        "status":"COMPLETE","overall":report["overall"],"paired":report["paired"],
        "divergences":divergent})

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("stage",choices=("freeze","shard","finish"))
    parser.add_argument("--shard",type=int,default=0)
    args=parser.parse_args()
    {"freeze":freeze,"shard":lambda:shard(args.shard),"finish":finish}[args.stage]()

if __name__=="__main__":main()
