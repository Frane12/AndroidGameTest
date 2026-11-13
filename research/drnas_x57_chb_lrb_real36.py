#!/usr/bin/env python3
"""DRNAS X5.7 CHB and LRB online decision learning — SHA-frozen REAL36.

One SAT solver per logical CPU. Six arms:
 - X55B_FROZEN: frozen reference from original X5.5b C++ source;
 - X57_VSIDS: same C++ build as candidates but identical VSIDS algorithm;
 - X57_CHB: conflict-history recency EMA;
 - X57_LRB: learned-clause-participation rate EMA;
 - KISSAT and CADICAL: frozen external reference binaries.

36 original SAT2024 CNFs, two repeats, 10s cap, PAR2=20s on
unknown/unverified. This is retrospective, NOT a blind family holdout.
"""
from __future__ import annotations
import argparse,collections,json,pathlib,random,subprocess,tempfile,time
import drnas_x55_cpu_real36 as B

CAP=10.0
REPS=2
SHARDS=12
ARMS=("X55B_FROZEN","X57_VSIDS","X57_CHB","X57_LRB","KISSAT","CADICAL")
BINS={"X55B_FROZEN":"build/drnas-x55b",
      "X57_VSIDS":"build/drnas-x57",
      "X57_CHB":"build/drnas-x57",
      "X57_LRB":"build/drnas-x57",
      "KISSAT":"build/kissat","CADICAL":"build/cadical"}
POLICIES={"X57_VSIDS":"vsids","X57_CHB":"chb","X57_LRB":"lrb"}

def emit(name,obj):
    print(name+" "+json.dumps(obj,sort_keys=True,separators=(",",":")),flush=True)

def save(path,obj):
    f=pathlib.Path(path);f.parent.mkdir(exist_ok=True,parents=True)
    f.write_text(json.dumps(obj,sort_keys=True,indent=2)+"\n")

def originals():
    sources,protocol=B.official_manifest()
    assert len(sources)==36 and {s["id"] for s in sources}==set(range(36))
    return sources,protocol

def freeze():
    sources,manifest=originals()
    p={
      "dataset":"Original SAT Competition 2024 REAL36 (retrospective)",
      "original_source_run":43387395060,
      "original_manifest_sha256":manifest["manifest_sha256"],
      "source_sha256":[s["sha256"] for s in sources],
      "source_families":dict(collections.Counter(s["family"] for s in sources)),
      "selection":"All 36 original SHA-frozen source IDs, never screened by solver outcome",
      "binary_sha256":{arm:B.sha(pathlib.Path(b).read_bytes()) for arm,b in BINS.items()},
      "arms":list(ARMS),"cap_s":CAP,"reps":REPS,"shards":SHARDS,
      "total_trials":36*REPS*len(ARMS),
      "proof_file_limit_bytes":512*1024*1024,
      "policy":{
        "CHB":"recency-weighted conflict participation with EMA alpha 0.4 down to 0.06",
        "LRB":"per-assignment learned-clause membership rate with same EMA alpha",
        "VSIDS":"frozen baseline X5.5b activity and phase-saving"},
      "cpu":"Serial solver invocation pinned to one logical CPU per shard",
      "verification":"Original SAT witness check / independent DRAT for UNSAT",
      "promotion":"none; independent new original family-held-out validation required"
    }
    save("x57_freeze/protocol.json",p)
    emit("X57_FREEZE",p)

def trial(src,rep,arm,td):
    path=pathlib.Path(src["path"])
    raw=path.read_bytes()
    assert B.sha(raw)==src["sha256"],"Modified original CNF"
    n,clauses=B.parse_cnf(raw)
    stdout,stderr,usage,proof=(td/x for x in ("stdout","stderr","usage","proof.drat"))
    for f in (stdout,stderr,usage,proof):f.unlink(missing_ok=True)
    if arm in POLICIES or arm=="X55B_FROZEN":
        cmd=[BINS[arm],str(path),"--mode","core","--time",str(CAP),
             "--stats","--proof",str(proof),"--x52-proof-deletions",
             "--x53-policy","baseline","--x53-progress"]
        if arm in POLICIES:cmd+=["--x57-branch",POLICIES[arm]]
    elif arm=="KISSAT":
        cmd=[BINS[arm],str(path),str(proof)]
    else:
        cmd=[BINS[arm],"-q","--no-binary",str(path),str(proof)]
    returncode,wall,expired,rss,cpu=B.run_process(cmd,stdout,stderr,usage,CAP+0.3)
    out=stdout.read_text(errors="replace")
    err=stderr.read_text(errors="replace")
    native={};x57={};progress=[]
    for line in err.splitlines():
        if line.startswith("X41_STATS "):
            try:native=json.loads(line.split(" ",1)[1])
            except json.JSONDecodeError:pass
        if line.startswith("X57_STATS "):
            try:x57=json.loads(line.split(" ",1)[1])
            except json.JSONDecodeError:pass
        if line.startswith("X57_PROGRESS "):
            try:progress.append(json.loads(line.split(" ",1)[1]))
            except json.JSONDecodeError:pass
    if arm in POLICIES and not expired and returncode in (0,10,20):
        if not x57:raise RuntimeError(f"Missing X57 stats {arm} source {src['id']}")
        if x57["requested"]!=POLICIES[arm].upper():raise RuntimeError("Wrong policy compiled")
    status="timeout" if expired else "UNKNOWN"
    audit_s=0.0
    if not expired:
        if returncode==10:
            if not B.check_sat(out,clauses,n):
                raise RuntimeError(f"WRONG SAT arm={arm} source={src['id']}")
            status="SAT_VERIFIED"
        elif returncode==20:
            status="UNSAT_UNVERIFIED"
            if proof.exists() and proof.stat().st_size>0:
                start=time.perf_counter()
                try:
                    v=subprocess.run(["build/drat-trim",str(path),str(proof)],
                         capture_output=True,text=True,timeout=15)
                    audit_s=time.perf_counter()-start
                    if v.returncode==0 and "s VERIFIED" in v.stdout:
                        status="UNSAT_CERTIFIED"
                    elif v.returncode==0:
                        raise RuntimeError(f"UNSAT verifier success without 'VERIFIED': {arm}")
                    else:
                        raise RuntimeError(f"UNSAT proof rejected {arm} id={src['id']}: {v.stdout[-500:]}")
                except subprocess.TimeoutExpired:
                    audit_s=time.perf_counter()-start
                    status="UNSAT_CHECK_TIMEOUT"
        elif returncode==153 and proof.exists() and proof.stat().st_size==512*1024*1024:
            status="PROOF_SIZE_LIMIT"
        elif returncode!=0:
            raise RuntimeError(f"Unexpected process exit {returncode} {arm} {src['id']}: {err[-600:]}")
    accepted=status in ("SAT_VERIFIED","UNSAT_CERTIFIED") and wall<=CAP
    return {
        "source_id":src["id"],"sha256":src["sha256"],"family":src["family"],
        "rep":rep,"arm":arm,"status":status,"accepted":accepted,
        "PAR2_s":round(wall if accepted else 2*CAP,6),
        "solve_e2e_s":round(wall,6),"maxrss_kib":rss,"cpu_s":cpu,
        "proof_audit_s":round(audit_s,6),"proof_bytes":proof.stat().st_size if proof.exists() else 0,
        "native":native,"x57":x57,"last_progress":progress[-1] if progress else {},
        "progress_samples":len(progress),
        "proof_size_limited":status=="PROOF_SIZE_LIMIT"
    }

def run_shard(index):
    original,_=originals()
    frozen=json.loads(pathlib.Path("x57_freeze/protocol.json").read_text())
    assert [s["sha256"] for s in original]==frozen["source_sha256"]
    for arm in ARMS:
        if B.sha(pathlib.Path(BINS[arm]).read_bytes())!=frozen["binary_sha256"][arm]:
            raise RuntimeError("Binary SHA mismatch")
    selected=[s for s in original if s["id"]%SHARDS==index]
    assert len(selected)==3
    folder=pathlib.Path(f"x57_shards/{index}");folder.mkdir(parents=True,exist_ok=False)
    with tempfile.TemporaryDirectory() as d,(folder/"trials.jsonl").open("w") as fd:
        td=pathlib.Path(d)
        for src in selected:
            for rep in range(REPS):
                arms=list(ARMS)
                random.Random(571113+src["id"]*43+rep).shuffle(arms)
                for arm in arms:
                    row=trial(src,rep,arm,td)
                    fd.write(json.dumps(row,sort_keys=True,separators=(",",":"))+"\n");fd.flush()
                    emit("X57_TRIAL",{k:row[k] for k in ("source_id","family","rep","arm","status",
                         "accepted","PAR2_s","solve_e2e_s","maxrss_kib")})
                emit("X57_PROGRESS",{"shard":index,"source_id":src["id"],"rep":rep})
    save(folder/"manifest.json",{"shard":index,"trials":3*REPS*len(ARMS),
         "sha256":frozen["original_manifest_sha256"],"binary_sha256":frozen["binary_sha256"],
         "sources":[s["sha256"] for s in selected]})
    emit("X57_SHARD_FINAL",{"shard":index,"trials":3*REPS*len(ARMS)})

def totals(rows):
    result={}
    for arm in ARMS:
        rr=[x for x in rows if x["arm"]==arm]
        result[arm]={
            "attempts":len(rr),
            "solved":sum(x["accepted"] for x in rr),
            "SAT":sum(x["accepted"] and x["status"]=="SAT_VERIFIED" for x in rr),
            "UNSAT":sum(x["accepted"] and x["status"]=="UNSAT_CERTIFIED" for x in rr),
            "PAR2_s":round(sum(x["PAR2_s"] for x in rr),6),
            "solve_wall_s":round(sum(x["solve_e2e_s"] for x in rr),6),
            "CPU_s":round(sum(x["cpu_s"] or 0 for x in rr),6),
            "CPU_missing":sum(x["cpu_s"] is None for x in rr),
            "maxRSS_kib":max((x["maxrss_kib"] or 0 for x in rr),default=0),
            "proof_audit_s":round(sum(x["proof_audit_s"] for x in rr),6),
            "proof_size_limit":sum(x["proof_size_limited"] for x in rr),
            "fallbacks":sum(x["x57"].get("fallback",False) for x in rr),
            "score_updates":sum((x["x57"] or x["last_progress"]).get("score_updates",0) for x in rr),
            "learned_clause_hits":sum((x["x57"] or x["last_progress"]).get("learned_clause_hits",
                 (x["x57"] or x["last_progress"]).get("learned_hits",0)) for x in rr),
            "decisions_recorded":sum((x["native"] or x["last_progress"]).get("decisions",0) for x in rr),
            "conflicts_recorded":sum((x["native"] or x["last_progress"]).get("conflicts",0) for x in rr),
        }
    return result

def compare(rows,base,candidate,metric):
    bysha=collections.defaultdict(list)
    for x in rows:bysha[x["sha256"]].append(x)
    diffs=[]
    for sha,s in sorted(bysha.items()):
        a=[x for x in s if x["arm"]==base]
        b=[x for x in s if x["arm"]==candidate]
        assert len(a)==len(b)==REPS
        if any(x[metric] is None for x in a+b):
            return {"available":False,"reason":"Missing process CPU; no zero imputation"}
        diffs.append(sum(x[metric] for x in b)-sum(x[metric] for x in a))
    randomgen=random.Random(571113)
    draws=sorted(sum(randomgen.choices(diffs,k=len(diffs))) for _ in range(5000))
    return {"available":True,"delta_candidate_minus_reference":round(sum(diffs),6),
            "source_cluster_bootstrap95":[round(draws[125],6),round(draws[4874],6)],
            "independent_source_clusters":len(diffs),"repeats_per_source":REPS}

def final():
    sources,protocol=originals()
    frozen=json.loads(pathlib.Path("x57_freeze/protocol.json").read_text())
    assert protocol["manifest_sha256"]==frozen["original_manifest_sha256"]
    rows=[]
    for index in range(SHARDS):
        directory=pathlib.Path("x57_downloads")/f"x57-shard-{index}"
        meta=json.loads((directory/"manifest.json").read_text())
        assert meta["shard"]==index and meta["sha256"]==frozen["original_manifest_sha256"]
        assert meta["binary_sha256"]==frozen["binary_sha256"]
        entries=[json.loads(x) for x in (directory/"trials.jsonl").read_text().splitlines()]
        assert len(entries)==meta["trials"]
        assert {e["sha256"] for e in entries}==set(meta["sources"])
        rows.extend(entries)
    expected={(s["sha256"],rep,arm) for s in sources for rep in range(REPS) for arm in ARMS}
    assert len(rows)==len(expected)==432
    assert {(x["sha256"],x["rep"],x["arm"]) for x in rows}==expected
    assert not any(x["status"] in ("WRONG_SAT","PROCESS_ERROR") for x in rows)
    for sha in frozen["source_sha256"]:
        outcomes={x["status"][:3] for x in rows if x["sha256"]==sha and x["accepted"]}
        assert len(outcomes)<=1,"Conflicting verified solver results"
    summary=totals(rows)
    comp={}
    for key,a,b in (
        ("chb_vs_frozen","X55B_FROZEN","X57_CHB"),
        ("lrb_vs_frozen","X55B_FROZEN","X57_LRB"),
        ("chb_vs_same_binary_vsids","X57_VSIDS","X57_CHB"),
        ("lrb_vs_same_binary_vsids","X57_VSIDS","X57_LRB"),
        ("same_binary_vsids_vs_frozen","X55B_FROZEN","X57_VSIDS"),
        ("chb_vs_kissat","KISSAT","X57_CHB"),
        ("lrb_vs_cadical","CADICAL","X57_LRB")):
        comp[key]={"PAR2":compare(rows,a,b,"PAR2_s"),
                   "CPU":compare(rows,a,b,"cpu_s")}
    report={
       "status":"COMPLETE","protocol":frozen,"overall":summary,
       "by_family":{f:totals([r for r in rows if r["family"]==f])
                    for f in sorted(set(r["family"] for r in rows))},
       "comparisons":comp,
       "limitations":[
          "Retrospective original SAT2024 REAL36; no blind holdout or model promotion.",
          "CHB and LRB are simplified paper-inspired online mechanisms; not exact MapleSAT reproductions.",
          "All nonbranching CDCL mechanics including BCP, proof, restart, reduction and polarity saving are identical.",
          "CHB uses conflict recency at unassignment; LRB uses final learned-clause membership per conflict since assignment.",
          "SAT witness and UNSAT proof checks independent; proof check time excludes solver PAR2.",
          "Two repetitions of each original are a cluster, not independent evidence.",
          "Only count CPU when tool reported it; absent CPU never substituted with 0."
       ]
    }
    out=pathlib.Path("x57_final");out.mkdir(exist_ok=True)
    save(out/"report.json",report)
    (out/"paired_trials.jsonl").write_text("".join(json.dumps(r,sort_keys=True)+"\n" for r in rows))
    emit("X57_FINAL",{"status":report["status"],"overall":summary,
                      "PAR2_comparisons":{k:v["PAR2"] for k,v in comp.items()}})

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("stage",choices=("freeze","shard","finish"))
    ap.add_argument("--shard",type=int,default=0)
    args=ap.parse_args()
    if args.stage=="freeze":freeze()
    elif args.stage=="shard":run_shard(args.shard)
    else:final()

if __name__=="__main__":main()
