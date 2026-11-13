#!/usr/bin/env python3
"""SPECTRAL1B delayed rank-deficient Walsh-guided CDCL A/B on frozen SAT2024 REAL36.

Same binary OFF vs ON, plus SHA-frozen X5 and two external references.
This is retrospective diagnostic material, NEVER a fresh blind holdout.
"""
from __future__ import annotations
import argparse, collections, hashlib, json, os, pathlib, random, subprocess, tempfile, time
import drnas_x55_cpu_real36 as B

CAP=5.0
REPS=2
SHARDS=12
ARMS=("X5_FROZEN","SPECTRAL1B_OFF","SPECTRAL1B_ON","KISSAT","CADICAL")
BINS={"X5_FROZEN":"build/drnas-x5","SPECTRAL1B_OFF":"build/drnas-spectral1b","SPECTRAL1B_ON":"build/drnas-spectral1b",
      "KISSAT":"build/kissat","CADICAL":"build/cadical"}
CHECKS={"DRAT":"build/drat-trim"}
LABEL="SPECTRAL1B_WALSH_LOCAL"
def emit(tag, data):
    print(tag+" "+json.dumps(data,sort_keys=True,separators=(",",":")),flush=True)
def save(path, thing):
    path=pathlib.Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(thing,sort_keys=True,indent=2)+"\n")
def frozen_sources():
    original, protocol=B.official_manifest()
    if len(original)!=36 or len({r["sha256"] for r in original})!=36:
        raise RuntimeError("REAL36 source count/hash not frozen")
    return original,protocol
def freeze():
    sources, proto=frozen_sources()
    paths={**BINS,**CHECKS}
    frozen={
      "protocol":"DRNAS-SPECTRAL1B-DELAYED-GATE-v1",
      "dataset":"SAT Competition 2024 REAL36 originals (retrospective only)",
      "source_run":43387395060,
      "source_manifest_sha256":proto["manifest_sha256"],
      "source_sha256":[r["sha256"] for r in sources],
      "source_families":{f:sum(r["family"]==f for r in sources) for f in sorted({r["family"] for r in sources})},
      "binary_sha256":{key:B.sha(pathlib.Path(path).read_bytes()) for key,path in paths.items()},
      "source_code_sha256":B.sha(pathlib.Path("src/drnas_spectral1b.cpp").read_bytes()),
      "walsh_module_sha256":B.sha(pathlib.Path("src/drnas_spectral1.hpp").read_bytes()),
      "frozen_x5_source_sha256":B.sha(pathlib.Path("src/drnas_x5.cpp").read_bytes()),
      "arms":list(ARMS),"shards":SHARDS,"repeats":REPS,"cap_s":CAP,
      "expected_trials":36*REPS*len(ARMS),
      "policy":"SPECTRAL1B_OFF and SPECTRAL1B_ON are identical executables; only --spectral1-late differs. Same 5s cap and same original CNFs.",
      "optimization":"Exact local Walsh spectral analysis, only rank-reduced windows; defer VSIDS bonus to 256 native conflicts, preserve easy SAT fast path; no proof changes.",
      "safety":"SAT witness original CNF, UNSAT independent DRAT verifier, crashes fail workflow",
      "publication":"retrospective diagnostic, no automatic promotion or holdout claim",
    }
    save("spectral1b_freeze/protocol.json",frozen)
    emit("SPECTRAL1B_FREEZE", frozen)

def run(src,arm,rep,td):
    cnf=pathlib.Path(src["path"])
    if B.sha(cnf.read_bytes())!=src["sha256"]:
        raise RuntimeError("Original source SHA drift")
    n, clauses=B.parse_cnf(cnf.read_bytes())
    out,err,usage,proof=(td/x for x in ("stdout","stderr","usage","proof.log"))
    for p in (out,err,usage,proof):p.unlink(missing_ok=True)
    if arm in ("X5_FROZEN","SPECTRAL1B_OFF","SPECTRAL1B_ON"):
        cmd=[BINS[arm],str(cnf),"--mode","core","--time",str(CAP),
             "--stats","--proof",str(proof)]
        if arm=="SPECTRAL1B_ON":cmd.append("--spectral1-late")
    elif arm=="KISSAT":
        cmd=[BINS[arm],str(cnf),str(proof)]
    elif arm=="CADICAL":
        cmd=[BINS[arm],"-q","--no-binary",str(cnf),str(proof)]
    else:
        raise RuntimeError("Unsupported benchmark arm: "+arm)
    rc,wall,killed,rss,cpu=B.run_process(cmd,out,err,usage,CAP+0.3)
    stdout=out.read_text(errors="replace");stderr=err.read_text(errors="replace")
    stats={};hot={}
    for line in stderr.splitlines():
        if line.startswith("X41_STATS "):
            stats=json.loads(line.split(" ",1)[1])
        if line.startswith("SPECTRAL1_STATS "):
            hot=json.loads(line.split(" ",1)[1])
    if arm in ("SPECTRAL1B_OFF","SPECTRAL1B_ON") and not killed and rc in (0,10,20):
        if not hot or hot.get("enabled") != (arm=="SPECTRAL1B_ON"):
            raise RuntimeError("SPECTRAL1B telemetry/off-on mismatch")
    status="TIMEOUT" if killed else "UNKNOWN"
    verify_s=0.;cert="none"
    if not killed:
        if rc==10:
            if not B.check_sat(stdout,clauses,n):
                raise RuntimeError("WRONG_SAT_WITNESS arm="+arm+" sha="+src["sha256"])
            status="SAT_VERIFIED";cert="ORIGINAL_WITNESS"
        elif rc==20:
            status="UNSAT_UNVERIFIED"
            if proof.exists() and proof.stat().st_size>0:
                started=time.perf_counter()
                try:
                    command=[CHECKS["DRAT"],str(cnf),str(proof)]
                    checked=subprocess.run(command,capture_output=True,text=True,timeout=15)
                    verify_s=time.perf_counter()-started
                    verified=(checked.returncode==0 and "s VERIFIED" in checked.stdout)
                    if not verified:
                        raise RuntimeError("WRONG_UNSAT_PROOF arm="+arm+" sha="+src["sha256"]+
                                           " proof-log="+(checked.stdout+checked.stderr)[-350:])
                    status="UNSAT_CERTIFIED";cert="INDEPENDENT_PROOF"
                except subprocess.TimeoutExpired:
                    verify_s=time.perf_counter()-started
                    status="UNSAT_CHECK_TIMEOUT"
        elif rc in (0,153):
            status="UNKNOWN" if rc==0 else "PROOF_LIMIT"
        else:
            raise RuntimeError(f"PROCESS_CRASH arm={arm} sha={src['sha256']} rc={rc} stderr={stderr[-900:]}")
    accepted=bool(status in ("SAT_VERIFIED","UNSAT_CERTIFIED") and wall<=CAP)
    return {
      "sha256":src["sha256"],"id":src["id"],"family":src["family"],
      "arm":arm,"rep":rep,"status":status,"cert":cert,"accepted":accepted,
      "PAR2_s":round(wall if accepted else 2*CAP,6),
      "solve_e2e_s":round(wall,6),"cpu_s":cpu,"rss_kib":rss,
      "proof_audit_s":round(verify_s,6),"spectral1b":hot,"native":stats,
      "proof_bytes":proof.stat().st_size if proof.exists() else 0
    }

def shard(index):
    sources, proto=frozen_sources()
    frozen=json.loads(pathlib.Path("spectral1b_freeze/protocol.json").read_text())
    assert frozen["source_manifest_sha256"]==proto["manifest_sha256"]
    paths={**BINS,**CHECKS}
    for arm,path in paths.items():
        if B.sha(pathlib.Path(path).read_bytes())!=frozen["binary_sha256"][arm]:
            raise RuntimeError("binary drift "+arm)
    selected=[v for v in sources if v["id"]%SHARDS==index]
    assert len(selected)==3
    dest=pathlib.Path("spectral1b_shards")/str(index)
    dest.mkdir(parents=True,exist_ok=False)
    with tempfile.TemporaryDirectory() as tmp,(dest/"trials.jsonl").open("w") as log:
        td=pathlib.Path(tmp)
        for src in selected:
            for rep in range(REPS):
                order=list(ARMS);random.Random(5801013+src["id"]*31+rep).shuffle(order)
                answers=set()
                for arm in order:
                    row=run(src,arm,rep,td)
                    if row["accepted"]:
                        ans="SAT" if row["status"]=="SAT_VERIFIED" else "UNSAT"
                        answers.add(ans)
                        if len(answers)>1:raise RuntimeError("contradictory certified answers")
                    log.write(json.dumps(row,sort_keys=True)+"\n");log.flush()
                    emit("SPECTRAL1B_TRIAL",{k:row[k] for k in
                        ("id","family","arm","rep","status","accepted","PAR2_s","solve_e2e_s","cpu_s")})
                emit("SPECTRAL1B_PROGRESS",{"shard":index,"id":src["id"],"rep":rep})
    save(dest/"manifest.json",{
        "shard":index,"source_sha":[v["sha256"] for v in selected],
        "freeze_sha256":B.sha(pathlib.Path("spectral1b_freeze/protocol.json").read_bytes()),
        "binary_sha256":frozen["binary_sha256"],"trials":len(selected)*REPS*len(ARMS)})
    emit("SPECTRAL1B_SHARD_COMPLETE",{"shard":index,"sources":len(selected),"trials":len(selected)*REPS*len(ARMS)})

def summarize(rows):
    ans={}
    for arm in ARMS:
        rs=[r for r in rows if r["arm"]==arm]
        ans[arm]={
          "attempts":len(rs),"verified":sum(r["accepted"] for r in rs),
          "distinct_solved":len({r["sha256"] for r in rs if r["accepted"]}),
          "SAT":sum(r["accepted"] and r["status"]=="SAT_VERIFIED" for r in rs),
          "UNSAT":sum(r["accepted"] and r["status"]=="UNSAT_CERTIFIED" for r in rs),
          "PAR2_s":round(sum(r["PAR2_s"] for r in rs),6),
          "cpu_s_available":sum(r["cpu_s"] for r in rs if r["cpu_s"] is not None),
          "cpu_missing":sum(r["cpu_s"] is None for r in rs),
          "rss_peak_kib":max([r["rss_kib"] for r in rs if r["rss_kib"] is not None] or [0]),
          "check_s":round(sum(r["proof_audit_s"] for r in rs),6),
          "enabled_runs":sum(r["spectral1b"].get("enabled",False) for r in rs),
          "windows_analyzed":sum(r["spectral1b"].get("windows_analyzed",0) for r in rs),
          "windows_active":sum(r["spectral1b"].get("windows_active",0) for r in rs),
          "rank_reduced_windows":sum(r["spectral1b"].get("rank_reduced_windows",0) for r in rs),
          "high_order_coefficients":sum(r["spectral1b"].get("high_order_coefficients",0) for r in rs),
          "variables_biased":sum(r["spectral1b"].get("variables_biased",0) for r in rs),
          "preprocess_ms":sum(r["spectral1b"].get("preprocess_ms",0) for r in rs),
          "activated_runs":sum(r["spectral1b"].get("activated",False) for r in rs),
          "activated_vars":sum(r["spectral1b"].get("activated_vars",0) for r in rs)
        }
    return ans

def family_bootstrap(rows,base,candidate,draws=5000):
    fam=collections.defaultdict(lambda:collections.defaultdict(list))
    for r in rows:fam[r["family"]][r["arm"]].append(r["PAR2_s"])
    keys=sorted(fam)
    if not keys:raise RuntimeError("empty family samples")
    for f in keys:
        if any(len(fam[f][a])!=len(fam[f][base]) for a in (base,candidate)):
            raise RuntimeError("unequal arms in family "+f)
    def score(ids):
        a=sum(sum(fam[f][base]) for f in ids)
        b=sum(sum(fam[f][candidate]) for f in ids)
        return (a-b)/a if a>0 else 0
    randomgen=random.Random(580518)
    draw=sorted(score([randomgen.choice(keys) for _ in keys]) for _ in range(draws))
    return {"relative_PAR2_reduction":score(keys),
       "family_bootstrap95":[draw[int(.025*(draws-1))],draw[int(.975*(draws-1))]],
       "independent_families":len(keys), "source_count":len({r["sha256"] for r in rows})}

def finish():
    originals, proto=frozen_sources()
    frozen=json.loads(pathlib.Path("spectral1b_freeze/protocol.json").read_text())
    assert frozen["source_manifest_sha256"]==proto["manifest_sha256"]
    trials=[]
    for i in range(SHARDS):
        p=pathlib.Path("spectral1b_downloads")/f"spectral1b-shard-{i}"
        meta=json.loads((p/"manifest.json").read_text())
        assert meta["shard"]==i
        assert meta["freeze_sha256"]==B.sha(pathlib.Path("spectral1b_freeze/protocol.json").read_bytes())
        assert meta["binary_sha256"]==frozen["binary_sha256"]
        rr=[json.loads(x) for x in (p/"trials.jsonl").read_text().splitlines() if x]
        assert len(rr)==meta["trials"]
        assert {r["sha256"] for r in rr}==set(meta["source_sha"])
        trials+=rr
    expected={(s["sha256"],rep,arm) for s in originals for rep in range(REPS) for arm in ARMS}
    actual=[(r["sha256"],r["rep"],r["arm"]) for r in trials]
    if set(actual)!=expected or len(actual)!=len(expected):
        raise RuntimeError("missing/duplicate paired trials")
    answers=collections.defaultdict(set)
    for r in trials:
        if r["accepted"]:answers[r["sha256"]].add("SAT" if r["status"]=="SAT_VERIFIED" else "UNSAT")
    if any(len(x)>1 for x in answers.values()):
        raise RuntimeError("certified answer contradiction")
    overall=summarize(trials)
    if overall["SPECTRAL1B_ON"]["enabled_runs"]==0:
        raise RuntimeError("SPECTRAL1B ON control was not executed")
    diffs={k:family_bootstrap(trials,*pair) for k,pair in {
       "off_vs_on":("SPECTRAL1B_OFF","SPECTRAL1B_ON"),
       "frozen_vs_off":("X5_FROZEN","SPECTRAL1B_OFF"),
       "frozen_vs_on":("X5_FROZEN","SPECTRAL1B_ON"),
       "kissat_vs_on":("KISSAT","SPECTRAL1B_ON"),
       "cadical_vs_on":("CADICAL","SPECTRAL1B_ON"),
    }.items()}
    result={
      "status":"COMPLETE","promotion":False,"blind_holdout":False,
      "protocol":frozen,"overall":overall,"family_CI":diffs,
      "same_binary_off_on_verified":True,"safety":"all earned SAT/UNSAT original CNF independently checked",
      "decision":"diagnostic only; require fresh family-blind holdout before promotion"
    }
    dest=pathlib.Path("spectral1b_final");dest.mkdir(parents=True,exist_ok=True)
    save(dest/"report.json",result)
    (dest/"trials.jsonl").write_text("".join(json.dumps(r,sort_keys=True)+"\n" for r in trials))
    emit("SPECTRAL1B_FINAL",{"overall":overall,"comparisons":diffs,"promotion":False,"status":"COMPLETE"})

def main():
    p=argparse.ArgumentParser()
    p.add_argument("command",choices=("freeze","shard","finish"))
    p.add_argument("--shard",type=int,default=0)
    args=p.parse_args()
    if args.command=="freeze":freeze()
    elif args.command=="shard":
        if not 0<=args.shard<SHARDS:p.error("shard out of range")
        shard(args.shard)
    else:finish()
if __name__=="__main__":main()
