#!/usr/bin/env python3
"""DRNAS X5.6 immutable-original binary implication CSR experiment.

Retrospective SAT Competition 2024 REAL36 originals, not a new blind holdout.
36 CNFs x2 repeats x5 solver arms = 360 trials at 10s solve cap.
All SAT witnesses checked against source; all UNSAT independently DRAT checked.
One logical CPU per solver set by CI. Source SHA and binary SHA frozen before
runs; source clustering respects dependence of repeated trials.
"""
from __future__ import annotations
import argparse, collections, hashlib, json, os, pathlib, random, subprocess
import tempfile, time
import drnas_x55_cpu_real36 as B

ROOT=pathlib.Path("real36_frozen")
CAP=10.0
SHARDS=12
REPS=2
ARMS=("X55B_FROZEN","X56_OFF","X56_CSR","KISSAT","CADICAL")
BINS={"X55B_FROZEN":"build/drnas-x55b","X56_OFF":"build/drnas-x56",
      "X56_CSR":"build/drnas-x56","KISSAT":"build/kissat","CADICAL":"build/cadical"}

def emit(k,d):print(k+" "+json.dumps(d,sort_keys=True,separators=(",",":")),flush=True)
def save(path,thing):
    path=pathlib.Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(thing,sort_keys=True,indent=2)+"\n")

def frozen_sources():
    arr,protocol=B.official_manifest()
    assert len(arr)==36 and {v["id"] for v in arr}==set(range(36))
    return arr,protocol

def freeze():
    arr,protocol=frozen_sources()
    frozen={
      "dataset":"36 original SAT Competition 2024 application CNFs (retrospective REAL36)",
      "source_archive_run":43387395060,
      "manifest_sha256":protocol["manifest_sha256"],
      "sources":[{"sha256":v["sha256"],"id":v["id"],"family":v["family"]} for v in arr],
      "binary_sha256":{arm:B.sha(pathlib.Path(path).read_bytes()) for arm,path in BINS.items()},
      "arms":list(ARMS),"cap_s":CAP,"repeat":REPS,"shards":SHARDS,
      "trials":len(arr)*REPS*len(ARMS),
      "selector":"all original 36, no outcome or speed screening",
      "proof_output_cap_bytes":512*1024*1024,
      "comparison":"X55B frozen, X56 OFF, X56 CSR, Kissat, CaDiCaL",
      "optimization":"static original binary clauses only: contiguous CSR with stable reason IDs; learned binaries remain dynamic",
      "correctness":"independent SAT witness check; original-CNF DRAT for UNSAT",
      "limits":"Retrospective, no promotion without independent family-held-out validation."
    }
    save("x56_freeze/protocol.json",frozen);emit("X56_FREEZE",frozen)

def run(src,arm,rep,td):
    cnf=pathlib.Path(src["path"])
    if B.sha(cnf.read_bytes())!=src["sha256"]:raise RuntimeError("Source SHA changed")
    n,clauses=B.parse_cnf(cnf.read_bytes())
    out,err,usage,proof=(td/part for part in ("stdout","stderr","usage","proof.drat"))
    for f in (out,err,usage,proof):f.unlink(missing_ok=True)
    if arm in ("X55B_FROZEN","X56_OFF","X56_CSR"):
        cmd=[BINS[arm],str(cnf),"--mode","core","--time",str(CAP),
             "--stats","--proof",str(proof),"--x52-proof-deletions",
             "--x53-policy","baseline","--x53-progress"]
        if arm=="X56_CSR":cmd.append("--x56-binary-csr")
    elif arm=="KISSAT":
        cmd=[BINS[arm],str(cnf),str(proof)]
    else:
        cmd=[BINS[arm],"-q","--no-binary",str(cnf),str(proof)]
    rc,wall,killed,rss,cpu=B.run_process(cmd,out,err,usage,CAP+0.3)
    stdout=out.read_text(errors="replace");stderr=err.read_text(errors="replace")
    stats={};csr={};progress=[]
    for line in stderr.splitlines():
        if line.startswith("X41_STATS "):
            try:stats=json.loads(line.split(" ",1)[1])
            except json.JSONDecodeError:pass
        if line.startswith("X56_STATS "):
            try:csr=json.loads(line.split(" ",1)[1])
            except json.JSONDecodeError:pass
        if line.startswith("X53_PROGRESS "):
            try:progress.append(json.loads(line.split(" ",1)[1]))
            except json.JSONDecodeError:pass
    if arm.startswith("X56") and not killed and rc in (0,10,20) and not csr:
        raise RuntimeError("Missing X56 telemetry from correctly exited solver")
    status="timeout" if killed else "UNKNOWN"
    check_s=0.
    if not killed:
        if rc==10:
            if not B.check_sat(stdout,clauses,n):
                raise RuntimeError(f"WRONG_SAT arm={arm} id={src['id']} rep={rep}")
            status="SAT_VERIFIED"
        elif rc==20:
            status="UNSAT_UNVERIFIED"
            if proof.exists() and proof.stat().st_size:
                t=time.perf_counter()
                try:
                    checked=subprocess.run(["build/drat-trim",str(cnf),str(proof)],
                        capture_output=True,text=True,timeout=16)
                    check_s=time.perf_counter()-t
                    if checked.returncode==0 and "s VERIFIED" in checked.stdout:
                        status="UNSAT_CERTIFIED"
                    elif checked.returncode==0:
                        raise RuntimeError("UNSAT checker returned success without VERIFIED")
                    else:
                        raise RuntimeError(f"INVALID_UNSAT_PROOF arm={arm} id={src['id']} {checked.stdout[-450:]}")
                except subprocess.TimeoutExpired:
                    check_s=time.perf_counter()-t
                    status="UNSAT_CHECK_TIMEOUT"
        elif rc==153 and proof.exists() and proof.stat().st_size==512*1024*1024:
            status="PROOF_SIZE_LIMIT"
        elif rc not in (0,):
            raise RuntimeError(f"EXCEPTION arm={arm} src={src['id']} rc={rc}: {stderr[-500:]}")
    accepted=bool(status in ("SAT_VERIFIED","UNSAT_CERTIFIED") and wall<=CAP)
    return {
        "id":src["id"],"family":src["family"],"sha256":src["sha256"],"arm":arm,
        "rep":rep,"status":status,"accepted":accepted,
        "PAR2_s":round(wall if accepted else 2*CAP,6),
        "solve_e2e_s":round(wall,6),"cpu_s":cpu,"maxrss_kib":rss,
        "proof_audit_s":round(check_s,6),
        "proof_bytes":proof.stat().st_size if proof.exists() else 0,
        "x56":csr,"native":stats,"progress_samples":len(progress),
        "partial_counters":progress[-1] if progress and not stats else {},
        "proof_size_limited":status=="PROOF_SIZE_LIMIT",
    }

def shard(idx):
    arr,_=frozen_sources()
    freeze_data=json.loads(pathlib.Path("x56_freeze/protocol.json").read_text())
    assert [v["sha256"] for v in arr]==[v["sha256"] for v in freeze_data["sources"]]
    for arm,binpath in BINS.items():
        assert B.sha(pathlib.Path(binpath).read_bytes())==freeze_data["binary_sha256"][arm]
    picked=[v for v in arr if v["id"]%SHARDS==idx]
    assert len(picked)==3
    out=pathlib.Path("x56_shards")/str(idx)
    out.mkdir(parents=True,exist_ok=False)
    with tempfile.TemporaryDirectory() as d,(out/"trials.jsonl").open("w") as fd:
        td=pathlib.Path(d)
        for v in picked:
            for rep in range(REPS):
                order=list(ARMS);random.Random(561513+v["id"]*41+rep).shuffle(order)
                for arm in order:
                    row=run(v,arm,rep,td)
                    fd.write(json.dumps(row,sort_keys=True)+"\n");fd.flush()
                    emit("X56_TRIAL",{
                        k:row[k] for k in ("id","family","arm","rep","status","accepted","PAR2_s",
                                          "solve_e2e_s","cpu_s","maxrss_kib")})
                emit("X56_PROGRESS",{"shard":idx,"id":v["id"],"rep":rep})
    save(out/"manifest.json",{"shard":idx,"source_sha256":[v["sha256"] for v in picked],
         "sha256":freeze_data["manifest_sha256"],"binary_sha256":freeze_data["binary_sha256"],
         "trials":3*REPS*len(ARMS)})
    emit("X56_SHARD_FINAL",{"shard":idx,"trials":3*REPS*len(ARMS)})

def summarize(rows):
    out={}
    for arm in ARMS:
        subset=[r for r in rows if r["arm"]==arm]
        csrs=[r["x56"] for r in subset]
        out[arm]={
           "attempts":len(subset),"solved":sum(r["accepted"] for r in subset),
           "SAT":sum(r["accepted"] and r["status"]=="SAT_VERIFIED" for r in subset),
           "UNSAT":sum(r["accepted"] and r["status"]=="UNSAT_CERTIFIED" for r in subset),
           "PAR2_s":round(sum(r["PAR2_s"] for r in subset),5),
           "wall_s":round(sum(r["solve_e2e_s"] for r in subset),5),
           "cpu_s":round(sum((r["cpu_s"] or 0) for r in subset),5),
           "cpu_data_missing":sum(r["cpu_s"] is None for r in subset),
           "rss_max_kib":max((r["maxrss_kib"] or 0 for r in subset),default=0),
           "proof_audit_s":round(sum(r["proof_audit_s"] for r in subset),5),
           "proof_size_limited":sum(r["proof_size_limited"] for r in subset),
           "CSR_active_runs":sum(v.get("csr_enabled") is True for v in csrs),
           "CSR_static_edges_checked":sum(v.get("binary_csr_edge_checks",0) for v in csrs)
        }
    return out

def compare(rows,left,right,metric):
    bysource=collections.defaultdict(list)
    for r in rows:bysource[r["sha256"]].append(r)
    differences=[]
    for sha,pair in sorted(bysource.items()):
        l=[r for r in pair if r["arm"]==left]
        rr=[r for r in pair if r["arm"]==right]
        assert len(l)==len(rr)==REPS
        if any(r[metric] is None for r in l+rr):
            return {"available":False,"reason":"Missing measurement; not imputed as zero"}
        differences.append(sum(x[metric] for x in rr)-sum(x[metric] for x in l))
    rng=random.Random(561513)
    draws=sorted(sum(rng.choices(differences,k=len(differences))) for _ in range(5000))
    return {"available":True,"delta_right_minus_left":round(sum(differences),6),
            "cluster_bootstrap95":[round(draws[125],6),round(draws[4874],6)],
            "sources":len(differences),"repeats_per_source":REPS}

def finish():
    arr,proto=frozen_sources()
    frozen=json.loads(pathlib.Path("x56_freeze/protocol.json").read_text())
    assert frozen["manifest_sha256"]==proto["manifest_sha256"]
    trials=[]
    for idx in range(SHARDS):
        folder=pathlib.Path("x56_downloads")/f"x56-shard-{idx}"
        meta=json.loads((folder/"manifest.json").read_text())
        assert meta["shard"]==idx and meta["sha256"]==frozen["manifest_sha256"]
        assert meta["binary_sha256"]==frozen["binary_sha256"]
        lines=[json.loads(line) for line in (folder/"trials.jsonl").read_text().splitlines()]
        assert len(lines)==meta["trials"]
        assert {r["sha256"] for r in lines}==set(meta["source_sha256"])
        trials.extend(lines)
    expected={(v["sha256"],rep,a) for v in arr for rep in range(REPS) for a in ARMS}
    assert len(trials)==len(expected)==360
    assert {(x["sha256"],x["rep"],x["arm"]) for x in trials}==expected
    assert not any(x["status"] in ("WRONG_SAT","PROCESS_ERROR") for x in trials)
    by_sha=collections.defaultdict(set)
    for x in trials:
        if x["accepted"]:by_sha[x["sha256"]].add(x["status"][:3])
    assert all(len(x)<=1 for x in by_sha.values()),"inconsistent accepted SAT/UNSAT"
    report={
      "status":"COMPLETE","protocol":frozen,
      "overall":summarize(trials),
      "by_family":{fam:summarize([x for x in trials if x["family"]==fam])
                  for fam in sorted(set(x["family"] for x in trials))},
      "comparisons":{
         "candidate_vs_recompiled":{
              "PAR2":compare(trials,"X56_OFF","X56_CSR","PAR2_s"),
              "CPU":compare(trials,"X56_OFF","X56_CSR","cpu_s")},
         "recompile_vs_frozen":{
              "PAR2":compare(trials,"X55B_FROZEN","X56_OFF","PAR2_s")},
         "vs_kissat":{"PAR2":compare(trials,"KISSAT","X56_CSR","PAR2_s")},
         "vs_cadical":{"PAR2":compare(trials,"CADICAL","X56_CSR","PAR2_s")},
      },
      "limitations":[
          "REAL36 is a repeated retrospective original SAT2024 set, not blind holdout.",
          "CSR activates only for n<=250000 and >=512 static binary edges.",
          "Learned binary clauses retain dynamic vectors and unmodified reduction policy.",
          "Proof check time is separate; certification required for accepted UNSAT.",
          "Bootstrap clusters by original source SHA across both repeats.",
          "Do not promote without separate new original family-held-out validation."
      ]
    }
    out=pathlib.Path("x56_final");out.mkdir(exist_ok=True)
    save(out/"report.json",report)
    (out/"paired_trials.jsonl").write_text("".join(json.dumps(r,sort_keys=True)+"\n" for r in trials))
    emit("X56_FINAL",{
        "status":report["status"],"overall":report["overall"],
        "comparisons":report["comparisons"],"CSR_active_runs":report["overall"]["X56_CSR"]["CSR_active_runs"]})

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("stage",choices=("freeze","shard","finish"))
    ap.add_argument("--shard",type=int,default=0)
    a=ap.parse_args()
    if a.stage=="freeze":freeze()
    elif a.stage=="shard":shard(a.shard)
    else:finish()

if __name__=="__main__":main()
