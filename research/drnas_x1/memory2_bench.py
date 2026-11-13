#!/usr/bin/env python3
"""DRNAS X1 MEMORY2: certified, paired future-horizon learning benchmark.

This pilot is synthetic and SHA-disjoint but NOT globally blind or family-disjoint.
It never promotes solver-written model files unless a separate original-CNF checker
accepts the SAT witness or UNSAT DRUP proof. A held-out policy is frozen on disk.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import random
import subprocess
import tempfile
import time
import check
from memory1_bench import make_case

HERE=Path(__file__).resolve().parent
ARMS=("X1_CORE","X1_M1_FROZEN","X1_M2_SHADOW","X1_M2_FROZEN","X1_M2_ONLINE")

def emit(tag,payload):
    print(tag+" "+json.dumps(payload,sort_keys=True,separators=(",",":")),flush=True)

def parse_stats(output):
    for line in output.splitlines():
        if line.startswith("c X1_STATS "):
            return json.loads(line[len("c X1_STATS "):])
    raise AssertionError("missing native X1_STATS line")

def audit_trace(path,stats):
    if not path.exists():
        raise AssertionError("MEMORY2 enabled but did not write trace")
    seq=[json.loads(x) for x in path.read_text().splitlines() if x.strip()]
    if not seq or seq[-1].get("event")!="outcome":
        raise AssertionError("MEMORY2 outcome row missing")
    opened,closed,seen=set(),set(),set()
    observed={16:0,64:0,256:0}
    censored={16:0,64:0,256:0}
    for e in seq[:-1]:
        t=e["event"]
        if t=="before_action":
            assert e["id"] not in opened and e["context"] in range(64)
            assert len(e["feature"]["recent_actions"])==4
            assert len(e["expected_utility"])==2
            opened.add(e["id"])
        elif t=="after_action":
            assert e["id"] in opened and e["id"] not in closed
            assert e["immediate_proxy"]>=0
            closed.add(e["id"])
        elif t=="horizon":
            assert e["id"] in closed and e["horizon"] in (16,64,256)
            key=(e["id"],e["horizon"])
            assert key not in seen;seen.add(key)
            h=e["horizon"]
            if e["observed"]:
                assert not e["censored"] and e["decisions"]>=h
                observed[h]+=1
            else:
                assert e["censored"] and e["decisions"]<h
                censored[h]+=1
        else:
            raise AssertionError("unknown MEMORY2 trace event "+str(t))
    # Valid for untruncated traces; a detailed trace is capped by design.
    if len(seq)-1<4096:
        assert opened==closed,(len(opened),len(closed))
        assert sum(observed.values())==stats["memory2_horizon_observations"]
    assert seq[-1]["episodes"]==stats["memory2_episodes"]
    return {"rows":len(seq),"horizons_observed":observed,"horizons_censored":censored}

def trial(binary,cnf,cap,seed,flags,root,tag,keep_trace=False):
    proof=root/(tag+".proof")
    log=root/(tag+".jsonl")
    cmd=[str(binary),"--mode","core","--seconds",str(cap),
         "--seed",str(seed),"--proof",str(proof)]
    is_memory2=any(x.startswith("--memory2") for x in flags)
    if is_memory2: cmd+=["--memory2-log",str(log)]
    cmd+=flags+[str(cnf)]
    start=time.monotonic()
    try:
        p=subprocess.run(cmd,capture_output=True,text=True,timeout=cap+1.0)
        wall=time.monotonic()-start
    except subprocess.TimeoutExpired:
        return {"status":"TIMEOUT","verified":False,"solve_s":cap,"check_s":0,
                "e2e_s":cap,"PAR2":2*cap,"stats":{},"trace":None}
    if p.returncode not in (0,10,20):
        raise AssertionError("solver crashed: "+str(p.returncode)+" "+p.stderr[-1200:])
    stats=parse_stats(p.stdout)
    if stats.get("external_solver_calls")!=0:
        raise AssertionError("X1 provenance violation")
    status={0:"UNKNOWN",10:"SAT",20:"UNSAT"}[p.returncode]
    verification="NOT_SOLVED";verified=False;check_s=0.0
    if status!="UNKNOWN":
        check_start=time.monotonic()
        try:
            valid=check.verify(cnf,p.stdout,proof,2.0)
            verified=bool(valid["verified"]);verification=valid["kind"]
        except (TimeoutError,ValueError) as exc:
            verification=type(exc).__name__
        check_s=time.monotonic()-check_start
        if status=="SAT" and not verified:
            raise AssertionError("unverified SAT model")
    audit=None
    if is_memory2:audit=audit_trace(log,stats)
    if not keep_trace and log.exists(): log.unlink()
    e2e=wall+check_s
    return {"status":status,"verified":verified,"verification":verification,
            "solve_s":round(wall,6),"check_s":round(check_s,6),
            "e2e_s":round(e2e,6),
            "PAR2":round(e2e if verified and e2e<=cap else 2*cap,6),
            "stats":stats,"trace":audit}

def summarize(rows):
    ret={}
    for arm in ARMS:
        part=[r for r in rows if r["arm"]==arm]
        ret[arm]={"trials":len(part),"verified":sum(r["verified"] for r in part),
            "SAT_verified":sum(r["verified"] and r["status"]=="SAT" for r in part),
            "UNSAT_verified":sum(r["verified"] and r["status"]=="UNSAT" for r in part),
            "PAR2_verified_e2e_s":round(sum(r["PAR2"] for r in part),6),
            "solve_s":round(sum(r["solve_s"] for r in part),6),
            "check_s":round(sum(r["check_s"] for r in part),6),
            "decisions":sum(r.get("decisions") or 0 for r in part),
            "conflicts":sum(r.get("conflicts") or 0 for r in part),
            "memory2_episodes":sum(r.get("episodes") or 0 for r in part),
            "horizon_observations":sum(r.get("horizon_observations") or 0 for r in part),
            "memory2_flip_blocks":sum(r.get("flips") or 0 for r in part)}
    return ret

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--binary",type=Path,default=Path("build/drnas-x1"))
    ap.add_argument("--out",type=Path,default=Path("x1_memory2_results"))
    ap.add_argument("--train",type=int,default=42)
    ap.add_argument("--holdout",type=int,default=30)
    ap.add_argument("--repeats",type=int,default=3)
    ap.add_argument("--cap",type=float,default=2.0)
    args=ap.parse_args()
    assert args.train>=8 and args.holdout>=6 and args.repeats>=2 and args.cap>=.5
    args.out.mkdir(parents=True,exist_ok=False)
    binary=args.binary.resolve()
    sources=[make_case(i) for i in range(args.train+args.holdout)]
    assert len({c["sha256"] for c in sources})==len(sources)
    training,holdout=sources[:args.train],sources[args.train:]
    manifest={"train":[{"id":c["id"],"sha256":c["sha256"],"kind":c["kind"]} for c in training],
              "holdout":[{"id":c["id"],"sha256":c["sha256"],"kind":c["kind"]} for c in holdout],
              "globally_blind":False,"family_disjoint":False,"seed_policy":"17+13*rep",
              "proofs":"on; independently checked","primary":"end-to-end verified PAR2"}
    (args.out/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
    m1=args.out/"trained-memory1.txt";m2=args.out/"trained-memory2.txt"
    accepted={"MEMORY1":0,"MEMORY2":0}
    records=[]
    with tempfile.TemporaryDirectory(prefix="x1-memory2-") as temp:
        root=Path(temp)
        for i,case in enumerate(training):
            cnf=root/"train.cnf";cnf.write_text(case["source"])
            # The two models are trained from identical original inputs.
            for tag,path,flags in [
                ("MEMORY1",m1,["--memory","--memory-interval","8"]),
                ("MEMORY2",m2,["--memory2","--memory2-interval","8"])]:
                staged=root/(tag+"-candidate.txt")
                if staged.exists(): staged.unlink()
                control=flags+["--"+("memory" if tag=="MEMORY1" else "memory2")+"-save",str(staged)]
                if path.exists():
                    control+=["--"+("memory" if tag=="MEMORY1" else "memory2")+"-load",str(path)]
                row=trial(binary,cnf,args.cap,17,control,root,"train-"+tag)
                if row["verified"] and staged.exists():
                    os.replace(staged,path);accepted[tag]+=1
                elif staged.exists():staged.unlink()
                emit("X1_M2_TRAIN",{"id":case["id"],"kind":case["kind"],"arm":tag,
                    "status":row["status"],"verified":row["verified"],
                    "horizon_observations":row["stats"].get("memory2_horizon_observations",0),
                    "flips":row["stats"].get("memory2_flip_blocks",0)})
        if not (m1.exists() and m2.exists()):
            raise AssertionError("training did not produce verified models")
        digest_before=(hashlib.sha256(m1.read_bytes()).hexdigest(),
                       hashlib.sha256(m2.read_bytes()).hexdigest())
        for i,case in enumerate(holdout):
            cnf=root/"holdout.cnf";cnf.write_text(case["source"])
            for rep in range(args.repeats):
                seed=17+13*rep
                arms=[
                    ("X1_CORE",[]),
                    ("X1_M1_FROZEN",["--memory-load",str(m1),"--memory-frozen",
                                     "--memory-interval","8"]),
                    ("X1_M2_SHADOW",["--memory2-load",str(m2),"--memory2-frozen",
                                     "--memory2-shadow","--memory2-interval","8"]),
                    ("X1_M2_FROZEN",["--memory2-load",str(m2),"--memory2-frozen",
                                     "--memory2-interval","8"]),
                    ("X1_M2_ONLINE",["--memory2-load",str(m2),"--memory2-interval","8"])
                ]
                rotated=arms[(i+rep)%len(arms):]+arms[:(i+rep)%len(arms)]
                subset=[]
                for arm,flags in rotated:
                    keep=(arm=="X1_M2_ONLINE" and (i in (0,1,len(holdout)-1)) and rep==0)
                    tag=f"holdout-{case['id']}-{rep}-{arm}"
                    working_root=args.out if keep else root
                    row=trial(binary,cnf,args.cap,seed,flags,working_root,tag,keep)
                    stats=row.pop("stats");row.pop("trace")
                    row.update(id=case["id"],kind=case["kind"],sha256=case["sha256"],
                        nvars=case["nvars"],rep=rep,seed=seed,arm=arm,
                        decisions=stats.get("decisions"),conflicts=stats.get("conflicts"),
                        episodes=stats.get("memory2_episodes",0),
                        horizon_observations=stats.get("memory2_horizon_observations",0),
                        flips=stats.get("memory2_flip_blocks",0))
                    subset.append(row);records.append(row);emit("X1_M2_TRIAL",row)
                certain={r["status"] for r in subset if r["verified"]}
                assert len(certain)<=1,"verified SAT vs UNSAT disagreement"
                b=next(x for x in subset if x["arm"]=="X1_CORE")
                s=next(x for x in subset if x["arm"]=="X1_M2_SHADOW")
                if b["verified"] and s["verified"]:
                    assert (b["status"],b["decisions"],b["conflicts"])==(
                        s["status"],s["decisions"],s["conflicts"]),(
                        "shadow changed logical search path",case["id"],rep)
            emit("X1_M2_PROGRESS",{"completed":i+1,"holdout":len(holdout)})
        digest_after=(hashlib.sha256(m1.read_bytes()).hexdigest(),
                      hashlib.sha256(m2.read_bytes()).hexdigest())
        assert digest_before==digest_after,"test/holdout data leaked into model"
    totals=summarize(records)
    grouped={kind:summarize([r for r in records if r["kind"]==kind])
             for kind in sorted({c["kind"] for c in holdout})}
    baseline=totals["X1_CORE"]["PAR2_verified_e2e_s"]
    comparisons={}
    for arm in ARMS[1:]:
        solved=totals[arm]["PAR2_verified_e2e_s"]
        pairs={(r["id"],r["rep"]):r for r in records if r["arm"]==arm}
        regressions=0
        for row in records:
            if row["arm"]!="X1_CORE":continue
            other=pairs[(row["id"],row["rep"])]
            if other["PAR2"]>row["PAR2"]*1.1+.0002:regressions+=1
        comparisons[arm]={"PAR2_speedup_vs_X1_CORE_x":round(baseline/max(1e-12,solved),5),
                          "paired_regressions_10pct":regressions}
    report={"protocol":"synthetic_SHA_disjoint_paired",
       "train_sources":len(training),"holdout_sources":len(holdout),
       "repeats":args.repeats,"cap_s":args.cap,
       "trained_verified":accepted,"totals":totals,"groups":grouped,
       "comparisons":comparisons,"holdout_model_files_unchanged":True,
       "proof_credit":"independent SAT model / UNSAT DRUP",
       "genuine_unseen_competition":False,
       "family_disjoint":False,"same_state_counterfactual":False,
       "M2_future_proxy_is_not_calibrated_SAT_probability":True}
    (args.out/"report.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    with (args.out/"trials.jsonl").open("w") as o:
        for row in records:o.write(json.dumps(row,sort_keys=True)+"\n")
    emit("X1_M2_FINAL",report)

if __name__=="__main__":main()
