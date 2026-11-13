#!/usr/bin/env python3
"""COOP2 proof-certified exact affine lemmas and branching on original REAL36 CNFs.

Same binary OFF vs ON, plus SHA-frozen X5 and two external references.
This is retrospective diagnostic material, NEVER a fresh blind holdout.
"""
from __future__ import annotations
import argparse, collections, hashlib, json, os, pathlib, random, subprocess, tempfile, time, sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import drnas_x55_cpu_real36 as B

CAP=5.0
REPS=2
SHARDS=12
ARMS=("X5_FROZEN","COOP2_OFF","COOP2_OBSERVE","COOP2_ALGEBRA","COOP2_ON","COOP2_EAGER","KISSAT","CADICAL")
BINS={"X5_FROZEN":"build/drnas-x5","COOP2_OFF":"build/drnas-coop2","COOP2_OBSERVE":"build/drnas-coop2","COOP2_ALGEBRA":"build/drnas-coop2","COOP2_ON":"build/drnas-coop2","COOP2_EAGER":"build/drnas-coop2",
      "KISSAT":"build/kissat","CADICAL":"build/cadical"}
CHECKS={"DRAT":"build/drat-trim"}
LABEL="COOP2_REAL36_PROOF_ALGEBRA"
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
      "protocol":"DRNAS-COOP2-REAL36-PROOF-ALGEBRA-v1",
      "dataset":"SAT Competition 2024 REAL36 originals (retrospective only)",
      "source_run":43387395060,
      "source_manifest_sha256":proto["manifest_sha256"],
      "source_sha256":[r["sha256"] for r in sources],
      "source_families":{f:sum(r["family"]==f for r in sources) for f in sorted({r["family"] for r in sources})},
      "binary_sha256":{key:B.sha(pathlib.Path(path).read_bytes()) for key,path in paths.items()},
      "source_code_sha256":B.sha(pathlib.Path("build/drnas_coop2.cpp").read_bytes()),
      "coop2_engine_sha256":B.sha(pathlib.Path("research/drnas_coop2/coop.hpp").read_bytes()),
      "coop2_builder_sha256":B.sha(pathlib.Path("research/drnas_coop2/build.py").read_bytes()),
      "frozen_x5_source_sha256":B.sha(pathlib.Path("src/drnas_x5.cpp").read_bytes()),
      "arms":list(ARMS),"shards":SHARDS,"repeats":REPS,"cap_s":CAP,
      "expected_trials":36*REPS*len(ARMS),
      "policy":"OFF, OBSERVE, ALGEBRA, ON and ON_EAGER use same exact binary. Delayed arm starts after >=64 native conflicts; eager is explicit control. Models/proofs independently certified.",
      "optimization":"Exact local Walsh parity constraints, source-resolved RUP-certified guarded unit/binary lemmas, optional affine-defect branching. Defer expensive analysis until CDCL has >=64 conflicts.",
      "safety":"SAT witness original CNF, UNSAT independent DRAT verifier, crashes fail workflow",
      "publication":"retrospective diagnostic, no automatic promotion or holdout claim",
    }
    save("coop2_freeze/protocol.json",frozen)
    emit("COOP2_FREEZE", frozen)

def run(src,arm,rep,td):
    cnf=pathlib.Path(src["path"])
    if B.sha(cnf.read_bytes())!=src["sha256"]:
        raise RuntimeError("Original source SHA drift")
    n, clauses=B.parse_cnf(cnf.read_bytes())
    out,err,usage,proof=(td/x for x in ("stdout","stderr","usage","proof.log"))
    for p in (out,err,usage,proof):p.unlink(missing_ok=True)
    if arm in ("X5_FROZEN","COOP2_OFF","COOP2_OBSERVE","COOP2_ALGEBRA","COOP2_ON","COOP2_EAGER"):
        cmd=[BINS[arm],str(cnf),"--mode","core","--time",str(CAP),
             "--stats","--proof",str(proof)]
        if arm!="X5_FROZEN":
            cmd+=["--coop2",{"COOP2_OFF":"off","COOP2_OBSERVE":"observe","COOP2_ALGEBRA":"algebra","COOP2_ON":"on","COOP2_EAGER":"on"}[arm]]
            if arm=="COOP2_EAGER":cmd.append("--coop2-eager")
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
        if line.startswith("COOP2_STATS "):
            hot=json.loads(line.split(" ",1)[1])
    if arm.startswith("COOP2_") and not killed and rc in (0,10,20):
        intended={"COOP2_OFF":"off","COOP2_OBSERVE":"observe","COOP2_ALGEBRA":"algebra","COOP2_ON":"on","COOP2_EAGER":"on"}[arm]
        if not hot or hot.get("mode")!=intended or hot.get("delayed")!=(arm!="COOP2_EAGER"):
            raise RuntimeError("COOP2 telemetry control mismatch")
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
      "proof_audit_s":round(verify_s,6),"coop2":hot,"native":stats,
      "nvars":n,"nclauses":len(clauses),
      "proof_bytes":proof.stat().st_size if proof.exists() else 0
    }

def shard(index):
    sources, proto=frozen_sources()
    frozen=json.loads(pathlib.Path("coop2_freeze/protocol.json").read_text())
    assert frozen["source_manifest_sha256"]==proto["manifest_sha256"]
    paths={**BINS,**CHECKS}
    for arm,path in paths.items():
        if B.sha(pathlib.Path(path).read_bytes())!=frozen["binary_sha256"][arm]:
            raise RuntimeError("binary drift "+arm)
    selected=[v for v in sources if v["id"]%SHARDS==index]
    assert len(selected)==3
    dest=pathlib.Path("coop2_shards")/str(index)
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
                    emit("COOP2_TRIAL",{k:row[k] for k in
                        ("id","family","arm","rep","status","accepted","PAR2_s","solve_e2e_s","cpu_s")})
                emit("COOP2_PROGRESS",{"shard":index,"id":src["id"],"rep":rep})
    save(dest/"manifest.json",{
        "shard":index,"source_sha":[v["sha256"] for v in selected],
        "freeze_sha256":B.sha(pathlib.Path("coop2_freeze/protocol.json").read_bytes()),
        "binary_sha256":frozen["binary_sha256"],"trials":len(selected)*REPS*len(ARMS)})
    emit("COOP2_SHARD_COMPLETE",{"shard":index,"sources":len(selected),"trials":len(selected)*REPS*len(ARMS)})

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
          "mode_reports":sum(r["coop2"].get("mode")=={
                                "COOP2_OFF":"off","COOP2_OBSERVE":"observe",
                                "COOP2_ALGEBRA":"algebra","COOP2_ON":"on","COOP2_EAGER":"on"
                              }.get(arm) and r["coop2"].get("delayed")==(arm!="COOP2_EAGER")
                              for r in rs) if arm.startswith("COOP2_") else 0,
          "eligible_trial_sources":len({r["sha256"] for r in rs
               if r["nvars"]<=4096 and r["nclauses"]<=12000}),
          "prepared_runs":sum(r["coop2"].get("prepared",False) for r in rs),
          "passes":sum(r["coop2"].get("passes",0) for r in rs),
          "lemmas":sum(r["coop2"].get("lemmas",0) for r in rs),
          "proof_steps":sum(r["coop2"].get("proof_steps",0) for r in rs),
          "forced_parities":sum(r["coop2"].get("forced_parities",0) for r in rs),
          "conditioned":sum(r["coop2"].get("conditioned",0) for r in rs),
          "hints_applied":sum(r["coop2"].get("applied_hints",0) for r in rs),
          "analysis_ms":sum(r["coop2"].get("analysis_ms",0) for r in rs)
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
    frozen=json.loads(pathlib.Path("coop2_freeze/protocol.json").read_text())
    assert frozen["source_manifest_sha256"]==proto["manifest_sha256"]
    trials=[]
    for i in range(SHARDS):
        p=pathlib.Path("coop2_downloads")/f"coop2-shard-{i}"
        meta=json.loads((p/"manifest.json").read_text())
        assert meta["shard"]==i
        assert meta["freeze_sha256"]==B.sha(pathlib.Path("coop2_freeze/protocol.json").read_bytes())
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
    if any(overall[k]["mode_reports"]!=len([r for r in trials if r["arm"]==k]) for k in ("COOP2_OFF","COOP2_OBSERVE","COOP2_ALGEBRA","COOP2_ON","COOP2_EAGER")):
        raise RuntimeError("COOP2 missing or inconsistent mode telemetry")
    if overall["COOP2_OBSERVE"]["lemmas"]!=0 or overall["COOP2_OBSERVE"]["hints_applied"]!=0:
        raise RuntimeError("OBSERVE illegally modified search")
    if overall["COOP2_OFF"]["passes"]!=0 or overall["COOP2_OFF"]["lemmas"]!=0:
        raise RuntimeError("OFF incorrectly activated algebra engine")
    diffs={k:family_bootstrap(trials,*pair) for k,pair in {
       "off_vs_observe":("COOP2_OFF","COOP2_OBSERVE"),
       "observe_vs_algebra":("COOP2_OBSERVE","COOP2_ALGEBRA"),
       "algebra_vs_on":("COOP2_ALGEBRA","COOP2_ON"),
       "off_vs_on":("COOP2_OFF","COOP2_ON"),
       "off_vs_eager":("COOP2_OFF","COOP2_EAGER"),
       "frozen_vs_off":("X5_FROZEN","COOP2_OFF"),
       "frozen_vs_on":("X5_FROZEN","COOP2_ON"),
       "kissat_vs_on":("KISSAT","COOP2_ON"),
       "cadical_vs_on":("CADICAL","COOP2_ON"),
    }.items()}
    result={
      "status":"COMPLETE","promotion":False,"blind_holdout":False,
      "protocol":frozen,"overall":overall,"family_CI":diffs,
      "same_binary_off_on_verified":True,"safety":"all earned SAT/UNSAT original CNF independently checked",
      "decision":"diagnostic only; require fresh family-blind holdout before promotion"
    }
    dest=pathlib.Path("coop2_final");dest.mkdir(parents=True,exist_ok=True)
    save(dest/"report.json",result)
    (dest/"trials.jsonl").write_text("".join(json.dumps(r,sort_keys=True)+"\n" for r in trials))
    emit("COOP2_FINAL",{"overall":overall,"comparisons":diffs,"promotion":False,"status":"COMPLETE"})

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
