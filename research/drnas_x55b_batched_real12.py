#!/usr/bin/env python3
"""X5.5b: coarser CPU profiling, frozen subset of 12 original SAT2024 CNFs.

Select ONLY by frozen source ID modulo 3, not by solver outcome.
Requires the source archive / binaries from earlier verified REAL36 workflow.
CPU sample measurement is per complete nonempty propagate() call (stride 64),
not sub-microsecond per trail element (the X5.5 failure mode).
"""
from __future__ import annotations
import argparse,collections,json,pathlib,random,subprocess,tempfile,time
import drnas_x55_cpu_real36 as B

ROOT=pathlib.Path("real36_frozen")
CAP=8.0
REPS=2
SHARDS=4
ARMS=("X54_CONTROL","X54_ROTATE","X55B_CONTROL_OFF","X55B_CONTROL_ON","X55B_ROTATE_ON")
BIN={a:"build/drnas-x54" if a.startswith("X54_") else "build/drnas-x55b" for a in ARMS}
PROFILED={"X55B_CONTROL_ON","X55B_ROTATE_ON"}

def cases():
    allcases,proto=B.official_manifest()
    selected=[c for c in allcases if c["id"]%3==0]
    assert len(selected)==12 and len(set(c["sha256"] for c in selected))==12
    return selected,proto

def freeze():
    src,proto=cases()
    info={"source_count":12,"all_original_count":36,
          "original_manifest_sha256":proto["manifest_sha256"],
          "source_sha256":[c["sha256"] for c in src],
          "source_ids":[c["id"] for c in src],
          "families":dict(collections.Counter(c["family"] for c in src)),
          "selection":"frozen source IDs divisible by 3; NO outcome/speed screening",
          "binary_sha256":{a:B.sha(pathlib.Path(f).read_bytes()) for a,f in BIN.items()},
          "cap_s":CAP,"repeats":REPS,"shards":SHARDS,"arms":list(ARMS),
          "total_trials":12*REPS*len(ARMS),
          "proof_file_limit_bytes":512*1024*1024,
          "sampling":"every 64th nonempty propagate call; CLOCK_THREAD_CPUTIME_ID",
          "reuse":"retrospective original SAT2024; NOT blind holdout",
          "baseline":"frozen X5.4 compiled with same flags; NO X5.4 logic changes"}
    B.save("x55b_freeze/protocol.json",info)
    B.emit("X55B_FREEZE",info)

def trial(source,arm,rep,temp):
    path=pathlib.Path(source["path"])
    assert B.sha(path.read_bytes())==source["sha256"]
    n,clauses=B.parse_cnf(path.read_bytes())
    out,err,usage,proof=[temp/f for f in ("run.out","run.err","run.usage","run.drat")]
    for f in (out,err,usage,proof):f.unlink(missing_ok=True)
    cmd=[BIN[arm],str(path),"--mode","core","--time",str(CAP),
         "--stats","--x52-proof-deletions","--x53-policy","baseline",
         "--x53-progress","--proof",str(proof)]
    if "ROTATE" in arm:cmd.append("--x54-rotate-watches")
    if arm in PROFILED:cmd.append("--x55b-profile")
    rc,wall,expired,rss,cpu=B.run_process(cmd,out,err,usage,CAP+0.30)
    stderr=err.read_text(errors="replace")
    stdout=out.read_text(errors="replace")
    stats={};profile={};progress=[]
    for line in stderr.splitlines():
        if line.startswith("X41_STATS "):
            try:stats=json.loads(line.split(" ",1)[1])
            except json.JSONDecodeError:pass
        if line.startswith("X55B_PROFILE "):
            try:profile=json.loads(line.split(" ",1)[1])
            except json.JSONDecodeError:pass
        if line.startswith("X55B_PROGRESS "):
            try:progress.append(json.loads(line.split(" ",1)[1]))
            except json.JSONDecodeError:pass
    status="TIMEOUT" if expired else "UNKNOWN"
    checked=0.0
    if not expired:
        if rc==10:
            status="SAT_VERIFIED" if B.check_sat(stdout,clauses,n) else "WRONG_SAT"
            if status=="WRONG_SAT":raise RuntimeError(f"Wrong SAT model {arm} {source['id']}")
        elif rc==20:
            status="UNSAT_UNVERIFIED"
            if proof.exists() and proof.stat().st_size:
                started=time.perf_counter()
                try:
                    v=subprocess.run(["build/drat-trim",str(path),str(proof)],
                         capture_output=True,text=True,timeout=16)
                    checked=time.perf_counter()-started
                    if v.returncode==0 and "s VERIFIED" in v.stdout:
                        status="UNSAT_CERTIFIED"
                    else:raise RuntimeError(f"Wrong UNSAT proof {arm} {source['id']}")
                except subprocess.TimeoutExpired:checked=time.perf_counter()-started
        elif rc==153 and proof.exists() and proof.stat().st_size==512*1024*1024:
            status="PROOF_SIZE_LIMIT"
        elif rc!=0:
            status="PROCESS_ERROR"
            raise RuntimeError(f"Unexplained process error rc={rc} arm={arm} id={source['id']} stderr={stderr[-300:]}")
    if arm in PROFILED and not expired and rc in (0,10,20) and not profile:
        raise RuntimeError("X55B profile unexpectedly missing")
    accepted=wall<=CAP and status in ("SAT_VERIFIED","UNSAT_CERTIFIED")
    return {"source_id":source["id"],"family":source["family"],"sha256":source["sha256"],
            "arm":arm,"rep":rep,"status":status if not expired else "timeout",
            "accepted":accepted,"PAR2_s":round(wall if accepted else CAP*2,6),
            "solve_e2e_s":round(wall,6),"proof_audit_s":round(checked,6),
            "cpu_s":cpu,"maxrss_kib":rss,
            "profile":profile,"partial":progress[-1] if progress else {},
            "progress_samples":len(progress),"native_stats":stats,
            "proof_bytes":proof.stat().st_size if proof.exists() else 0}

def shard(idx):
    src,_=cases()
    conf=json.loads(pathlib.Path("x55b_freeze/protocol.json").read_text())
    assert conf["source_sha256"]==[c["sha256"] for c in src]
    for arm in ARMS:assert B.sha(pathlib.Path(BIN[arm]).read_bytes())==conf["binary_sha256"][arm]
    group=[s for s in src if (s["id"]//3)%SHARDS==idx]
    assert len(group)==3,(idx,len(group))
    folder=pathlib.Path("x55b_shards")/str(idx)
    folder.mkdir(parents=True,exist_ok=False)
    with tempfile.TemporaryDirectory() as tmp,(folder/"trials.jsonl").open("w") as fd:
        for source in group:
            for rep in range(REPS):
                arms=list(ARMS);random.Random(55115+source["id"]*13+rep).shuffle(arms)
                for arm in arms:
                    row=trial(source,arm,rep,pathlib.Path(tmp))
                    fd.write(json.dumps(row,sort_keys=True)+"\n");fd.flush()
                    B.emit("X55B_TRIAL",{k:row[k] for k in
                        ("source_id","family","rep","arm","status","accepted","PAR2_s","cpu_s")})
    B.save(folder/"manifest.json",{"shard":idx,"count":3,"trials":30,
        "original_manifest_sha256":conf["original_manifest_sha256"],
        "binary_sha256":conf["binary_sha256"],"sources":[x["sha256"] for x in group]})
    B.emit("X55B_SHARD_FINAL",{"shard":idx,"trials":30})

def finish():
    selected,_=cases();conf=json.loads(pathlib.Path("x55b_freeze/protocol.json").read_text())
    rows=[]
    for i in range(SHARDS):
        folder=pathlib.Path("x55b_downloads")/f"x55b-shard-{i}"
        manifest=json.loads((folder/"manifest.json").read_text())
        assert manifest["original_manifest_sha256"]==conf["original_manifest_sha256"]
        assert manifest["binary_sha256"]==conf["binary_sha256"]
        batch=[json.loads(v) for v in (folder/"trials.jsonl").read_text().splitlines()]
        assert len(batch)==30
        rows.extend(batch)
    expected={(v["sha256"],rep,a) for v in selected for rep in range(REPS) for a in ARMS}
    assert len(rows)==120 and {(r["sha256"],r["rep"],r["arm"]) for r in rows}==expected
    assert not any(r["status"] in ("WRONG_SAT","PROCESS_ERROR") for r in rows)
    by={}
    for arm in ARMS:
        arr=[r for r in rows if r["arm"]==arm]
        profiles=[(r["profile"] or r["partial"]) for r in arr]
        samples=sum(v.get("propagate_samples",0) for v in profiles)
        cpu_ns=sum(v.get("propagate_sample_cpu_ns",0) for v in profiles)
        total_cpu=sum(r["cpu_s"] or 0 for r in arr)
        estimate=(cpu_ns*64/1e9) if samples else None
        phases={}
        for phase in ("analysis","select","reduce","proof","garbage_collect"):
            ns=sum(v.get(phase+"_sample_cpu_ns",0) for v in profiles)
            count=sum(v.get(phase+"_samples",0) for v in profiles)
            phases[phase]={"samples":count,"sample_cpu_ns":ns,
                           "extrapolated_cpu_s":round(ns*128/1e9,6) if count else None}
        by[arm]={
            "attempts":len(arr),"solved":sum(r["accepted"] for r in arr),
            "PAR2_s":round(sum(r["PAR2_s"] for r in arr),6),
            "process_cpu_s":round(total_cpu,6),
            "maxrss_kib":max((r["maxrss_kib"] or 0) for r in arr),
            "bcp_propagate_samples":samples,
            "bcp_sample_cpu_ns":cpu_ns,
            "bcp_extrapolated_cpu_s":round(estimate,6) if estimate is not None else None,
            "sample_plausible":estimate is not None and estimate<=1.25*total_cpu,
            "phase":phases,
        }
    grouped=collections.defaultdict(list)
    for row in rows:grouped[row["sha256"]].append(row)
    def paired(a,b,metric):
        vals=[]
        for group in grouped.values():
            a0=sum(x[metric] for x in group if x["arm"]==a)
            b0=sum(x[metric] for x in group if x["arm"]==b)
            vals.append(b0-a0)
        rng=random.Random(55115)
        boot=sorted(sum(rng.choices(vals,k=len(vals))) for _ in range(4000))
        return {"delta":round(sum(vals),6),
                "bootstrap95":[round(boot[100],6),round(boot[3899],6)]}
    report={"status":"COMPLETE","protocol":conf,"overall":by,"comparisons":{
        "unprofiled_rotate_vs_control":paired("X54_CONTROL","X54_ROTATE","PAR2_s"),
        "same_source_build_effect":paired("X54_CONTROL","X55B_CONTROL_OFF","PAR2_s"),
        "profiler_overhead":paired("X55B_CONTROL_OFF","X55B_CONTROL_PROFILE","PAR2_s"),
        "profiled_rotate_vs_control":paired("X55B_CONTROL_PROFILE","X55B_ROTATE_PROFILE","PAR2_s"),
    },"limitations":[
        "12 original SAT2024 CNFs selected via source id modulo 3; retrospective and not blind.",
        "CPU samples cover every 64th nonempty propagate call; estimates may be biased by heterogeneity.",
        "A measured BCP CPU estimate larger than total process CPU is automatically flagged implausible.",
        "Proof verification is independent; proof check CPU is excluded from solver E2E.",
        "The sampler overhead is measured separately; this is not an optimizer promotion benchmark.",
    ]}
    target=pathlib.Path("x55b_final");target.mkdir(exist_ok=True)
    B.save(target/"report.json",report)
    (target/"trials.jsonl").write_text("".join(json.dumps(r,sort_keys=True)+"\n" for r in rows))
    B.emit("X55B_FINAL",report)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("stage",choices=("freeze","shard","finish"))
    parser.add_argument("--shard",type=int,default=0)
    arg=parser.parse_args()
    if arg.stage=="freeze":freeze()
    elif arg.stage=="shard":shard(arg.shard)
    else:finish()
if __name__=="__main__":main()
