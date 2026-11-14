#!/usr/bin/env python3
"""COOP54 proof-checked paired X5/COOP vs Kissat/CaDiCaL original SAT2024.

Retrospective REAL36, one logical CPU, SHA-pinned source/binaries, identical
8s end-to-end cap, two repeats. SAT original witness and independent original
UNSAT DRAT are required for credited PAR2. No blind or automatic promotion.
"""
import argparse, collections, hashlib, json, os, pathlib, random, signal
import subprocess, sys, tempfile, time
sys.path.insert(0,"research")
import drnas_x55_cpu_real36 as B

CAP=8.0
REPS=2
SHARDS=6
ARMS=("COOP53_BASE","COOP54_GATE","COOP54_MIN","COOP54_RETAIN",
      "COOP54_RESTART","COOP54_MIN_RETAIN","COOP54_FULL",
      "KISSAT","CADICAL")
BIN={
    "COOP53_BASE":"build/drnas-coop53-repair",
    "COOP54_GATE":"build/drnas-coop54-gate",
    "COOP54_MIN":"build/drnas-coop54-gate",
    "COOP54_RETAIN":"build/drnas-coop54-gate",
    "COOP54_RESTART":"build/drnas-coop54-gate",
    "COOP54_MIN_RETAIN":"build/drnas-coop54-gate",
    "COOP54_FULL":"build/drnas-coop54-gate",
    "KISSAT":"cross/x59/build/kissat",
    "CADICAL":"cross/x59/build/cadical"
}
EXTRA={
    "COOP53_BASE":["--x5-no-minimize"],
    "COOP54_GATE":["--x5-no-minimize"],
    "COOP54_MIN":[],
    "COOP54_RETAIN":["--x5-no-minimize","--x5-retain"],
    "COOP54_RESTART":["--x5-no-minimize","--x5-restarts"],
    "COOP54_MIN_RETAIN":["--x5-retain"],
    "COOP54_FULL":["--x5-retain","--x5-restarts"]
}
CHECKER="build/drat-trim"
PINS={"frozen_coop53_run":43534791673,"real36_source_run":43387395060,
      "frozen_kissat_cadical_run":43449841902}

def emit(label,value):
    print(label+" "+json.dumps(value,sort_keys=True,separators=(",",":")),flush=True)

def digest(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()

def save(path,payload):
    path=pathlib.Path(path)
    path.parent.mkdir(exist_ok=True,parents=True)
    path.write_text(json.dumps(payload,sort_keys=True,indent=2)+"\n")

def proc(cmd,budget):
    started=time.perf_counter()
    p=subprocess.Popen([str(x) for x in cmd],stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE,text=True,start_new_session=True)
    killed=False
    try:
        stdout,stderr=p.communicate(timeout=max(.1,budget))
    except subprocess.TimeoutExpired:
        os.killpg(p.pid,signal.SIGKILL)
        stdout,stderr=p.communicate()
        killed=True
    return p.returncode,stdout,stderr,time.perf_counter()-started,killed

def sample(original,arm,rep,cap):
    raw=pathlib.Path(original["path"]).read_bytes()
    if B.sha(raw)!=original["sha256"]:
        raise RuntimeError("ORIGINAL_CNF_SHA_MISMATCH")
    src=pathlib.Path(original["path"]).resolve()
    with tempfile.TemporaryDirectory() as temp:
        proof=pathlib.Path(temp)/"trial.drat"
        if arm.startswith("COOP"):
            cmd=[str(pathlib.Path(BIN[arm]).resolve()),str(src),"--mode","core",
                 "--time",str(cap-.07),"--stats","--proof",str(proof),
                 "--coop4","on","--coop5","on",*EXTRA[arm]]
        elif arm=="KISSAT":
            cmd=[str(pathlib.Path(BIN[arm]).resolve()),str(src),str(proof)]
        elif arm=="CADICAL":
            cmd=[str(pathlib.Path(BIN[arm]).resolve()),"-q","--no-binary",
                 str(src),str(proof)]
        else:raise RuntimeError("UNKNOWN_ARM")
        rc,out,err,wall,killed=proc(cmd,cap+.15)
        status="TIMEOUT" if killed else "UNKNOWN"
        cert="none"
        check_s=0.0
        # Check every returned SAT/UNSAT, even if it arrived after the cap.
        # Only on-time verified results receive PAR2 credit.
        if not killed:
            if rc==10:
                n,clauses=B.parse_cnf(raw)
                if not B.check_sat(out,clauses,n):
                    raise RuntimeError("INVALID_ORIGINAL_SAT_MODEL "+arm+" "+original["sha256"])
                status="SAT_VERIFIED"
                cert="ORIGINAL_MODEL"
            elif rc==20:
                if proof.exists() and proof.stat().st_size>0:
                    t=time.perf_counter()
                    try:
                        checked=subprocess.run([str(pathlib.Path(CHECKER).resolve()),
                                               str(src),str(proof)],
                                              capture_output=True,text=True,timeout=20)
                        check_s=time.perf_counter()-t
                        if "s VERIFIED" not in checked.stdout:
                            raise RuntimeError("UNSAT_PROOF_NOT_VERIFIED "+arm+
                                               " "+original["sha256"]+" "+checked.stdout[-500:])
                        status="UNSAT_CERTIFIED"
                        cert="INDEPENDENT_DRAT"
                    except subprocess.TimeoutExpired:
                        check_s=time.perf_counter()-t
                        status="UNSAT_CHECK_TIMEOUT"
                else:
                    status="UNSAT_UNVERIFIED"
            elif rc in (0,153):status="UNKNOWN"
            else:raise RuntimeError(f"PROCESS_ERROR {arm} rc={rc} {err[-600:]}")
        metrics={}
        for label in ("X41_STATS","X5_STATS","COOP4_STATS",
                      "COOP5_PROBE","COOP53_CONTRACT","COOP54_DISPATCH"):
            found=[x.partition(" ")[2] for x in err.splitlines()
                   if x.startswith(label+" ")]
            if len(found)>1:raise RuntimeError("DUPLICATE_TELEMETRY_"+label)
            if found:
                try: metrics[label]=json.loads(found[0])
                except json.JSONDecodeError as e: raise RuntimeError(label+" invalid JSON") from e
        if arm.startswith("COOP") and status in ("SAT_VERIFIED","UNSAT_CERTIFIED"):
            if "COOP53_CONTRACT" not in metrics:
                raise RuntimeError("COOP53_PROVENANCE_MISSING")
            if arm.startswith("COOP54") and "COOP54_DISPATCH" not in metrics:
                raise RuntimeError("COOP54_DISPATCH_MISSING")
        accepted=status in ("SAT_VERIFIED","UNSAT_CERTIFIED") and wall<=cap
        return {"id":original["id"],"family":original["family"],
                "sha256":original["sha256"],"rep":rep,"arm":arm,
                "status":status,"verified":accepted,"cert":cert,
                "wall_e2e_s":round(wall,6),"proof_check_s":round(check_s,6),
                "PAR2_verified_s":round(wall if accepted else 2*cap,6),
                "stats":metrics}

def material():
    src,meta=B.official_manifest()
    assert len(src)==36 and len({z["sha256"] for z in src})==36
    hashes={a:digest(path) for a,path in BIN.items()}
    hashes["DRAT_TRIM"]=digest(CHECKER)
    return src,meta,hashes

def shard_run(index,cap,reps):
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    if not (0<=index<SHARDS and cap==CAP and reps==REPS):raise RuntimeError("BAD_PROTOCOL")
    src,meta,hashes=material()
    selected=[z for i,z in enumerate(src) if i%SHARDS==index]
    assert len(selected)==6
    folder=pathlib.Path(f"coop54_shards/{index}")
    folder.mkdir(parents=True,exist_ok=False)
    save(folder/"manifest.json",{
        "cap":cap,"reps":reps,"shard":index,"source_manifest_sha256":meta["manifest_sha256"],
        "selected_sha256":[z["sha256"] for z in selected],
        "binary_sha256":hashes,"arms":ARMS,"pins":PINS,
        "one_cpu":sorted(os.sched_getaffinity(0)),
        "blind_holdout":False,"promotion":False,
    })
    answers=collections.defaultdict(set)
    with (folder/"trials.jsonl").open("w") as out:
        for srcrow in selected:
            for rep in range(reps):
                order=list(ARMS)
                random.Random(int(srcrow["sha256"][:16],16)+11*rep).shuffle(order)
                for arm in order:
                    r=sample(srcrow,arm,rep,cap)
                    if r["verified"]:
                        answers[(srcrow["sha256"],rep)].add("SAT" if r["status"]=="SAT_VERIFIED" else "UNSAT")
                        if len(answers[(srcrow["sha256"],rep)])!=1:
                            raise RuntimeError("CONTRADICTORY_VERIFIED_SAT_UNSAT")
                    out.write(json.dumps(r,sort_keys=True)+"\n")
                    out.flush()
                emit("COOP54_PROGRESS",{"shard":index,"id":srcrow["id"],"rep":rep})
    emit("COOP54_SHARD_PASS",{"shard":index,"sources":len(selected),"trials":len(selected)*reps*len(ARMS)})

def aggregate():
    src,meta,_=material()
    allrows=[]; allmeta=[]
    for shard in range(SHARDS):
        base=pathlib.Path(f"coop54_downloads/coop54-shard-{shard}/coop54_shards/{shard}")
        m=json.loads((base/"manifest.json").read_text())
        allmeta.append(m)
        allrows.extend(json.loads(line) for line in (base/"trials.jsonl").read_text().splitlines())
    assert len(allrows)==len(src)*REPS*len(ARMS)
    expected={(z["sha256"],rep,arm) for z in src for rep in range(REPS) for arm in ARMS}
    actual=[(r["sha256"],r["rep"],r["arm"]) for r in allrows]
    assert len(set(actual))==len(actual) and set(actual)==expected
    for m in allmeta:
        assert m["cap"]==CAP and m["reps"]==REPS
        assert m["pins"]==PINS and m["source_manifest_sha256"]==meta["manifest_sha256"]
        assert m["binary_sha256"]==allmeta[0]["binary_sha256"]
        assert len(m["one_cpu"])==1 and not m["blind_holdout"] and not m["promotion"]
    answers=collections.defaultdict(set)
    for r in allrows:
        if r["verified"]:
            answers[r["sha256"]].add("SAT" if r["status"]=="SAT_VERIFIED" else "UNSAT")
    assert all(len(ans)<=1 for ans in answers.values())
    fields={}
    for arm in ARMS:
        rows=[z for z in allrows if z["arm"]==arm]
        fields[arm]={
            "attempts":len(rows),
            "verified":sum(r["verified"] for r in rows),
            "sat":sum(r["status"]=="SAT_VERIFIED" for r in rows),
            "unsat_proof":sum(r["status"]=="UNSAT_CERTIFIED" for r in rows),
            "par2_verified_s":round(sum(r["PAR2_verified_s"] for r in rows),6),
            "conflicts":sum(r["stats"].get("X41_STATS",{}).get("conflicts",0) for r in rows),
            "decisions":sum(r["stats"].get("X41_STATS",{}).get("decisions",0) for r in rows),
            "restarts":sum(r["stats"].get("X41_STATS",{}).get("restarts",0) for r in rows),
            "minimized":sum(r["stats"].get("X5_STATS",{}).get("minimized_literals",0) for r in rows),
            "clauses_reduced":sum(r["stats"].get("X41_STATS",{}).get("reduce_removed",0) for r in rows),
            "dead_dispatch_skipped":sum(r["stats"].get("COOP54_DISPATCH",{}).get("skipped_dead_dispatch",0) for r in rows),
            "contract_invalidated":sum(r["stats"].get("COOP53_CONTRACT",{}).get("bridge_hints_invalidated",0) for r in rows),
        }
    families=sorted(set(z["family"] for z in src))
    groups={arm:{f:sum(r["PAR2_verified_s"] for r in allrows if r["arm"]==arm and r["family"]==f)
                 for f in families} for arm in ARMS}
    rng=random.Random(541406)
    draws=[[rng.choice(families) for _ in families] for _ in range(1200)]
    compares={}
    for base in ("COOP53_BASE","KISSAT","CADICAL"):
        for arm in ARMS:
            if arm==base:continue
            b=fields[base]["par2_verified_s"];t=fields[arm]["par2_verified_s"]
            boot=[]
            for draw in draws:
                bb=sum(groups[base][f] for f in draw)
                tt=sum(groups[arm][f] for f in draw)
                boot.append((bb-tt)/bb if bb else 0)
            boot.sort()
            compares[f"{arm}_vs_{base}"]={
                "gain_pct":round(100*(b-t)/b,4),
                "family_CI95_pct":[round(100*boot[30],4),round(100*boot[1169],4)],
                "families":len(families),
            }
    planning=[{"id":r["id"],"arm":r["arm"],"rep":r["rep"],"status":r["status"],
               "wall_e2e_s":r["wall_e2e_s"],"conflicts":r["stats"].get("X41_STATS",{}).get("conflicts")}
              for r in allrows if r["id"]==5]
    report={
        "status":"COMPLETE","trials":len(allrows),"originals":len(src),
        "repetitions":REPS,"cap_s":CAP,"arms":ARMS,
        "overall":fields,"comparisons":compares,"planning_id5":planning,
        "original_manifest_sha256":meta["manifest_sha256"],
        "binary_sha256":allmeta[0]["binary_sha256"],
        "blind_holdout":False,"promotion":False,
        "verified_only":True,
        "note":"Retrospective paired diagnostic, not a blind claim of competitive dominance.",
    }
    save("coop54_final/report.json",report)
    lines=["## DRNAS COOP54 controlled CDCL policy ablations vs Kissat / CaDiCaL","",
           f"{len(src)} original SAT2024 REAL36 sources × {REPS} repeats × {len(ARMS)} arms = {len(allrows)} trials.",
           "**No blind holdout, no promotion.** SAT original witnesses and UNSAT DRAT independently verified.","",
           "| Solver | Verified /72 | SAT | UNSAT proof | Verified PAR2 (s) | Restarts | Minimized lits | Dead bridge skips |",
           "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for arm,z in fields.items():
        lines.append(f"| {arm} | {z['verified']}/72 | {z['sat']} | {z['unsat_proof']} | "
                     f"{z['par2_verified_s']:.3f} | {z['restarts']} | {z['minimized']} | {z['dead_dispatch_skipped']} |")
    lines.extend(["","### Family bootstrap (95% clustered CIs)"])
    for arm in ARMS:
        if arm in ("KISSAT","CADICAL"):continue
        for base in ("COOP53_BASE","KISSAT","CADICAL"):
            if arm==base:continue
            v=compares[f"{arm}_vs_{base}"]
            lines.append(f"- {arm} vs {base}: PAR2 gain {v['gain_pct']:+.3f}%; "
                         f"95% CI {v['family_CI95_pct']}%, independent families {v['families']}")
    lines.append("**No automatic solver promotion.**")
    pathlib.Path("coop54_final/summary.md").write_text("\n".join(lines)+"\n")
    emit("COOP54_FINAL",report)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"],"a") as f:f.write("\n".join(lines)+"\n")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("command",choices=("shard","aggregate"))
    p.add_argument("--shard",type=int,default=0)
    p.add_argument("--cap",type=float,default=CAP)
    p.add_argument("--reps",type=int,default=REPS)
    args=p.parse_args()
    if args.command=="shard":shard_run(args.shard,args.cap,args.reps)
    else:aggregate()
if __name__=="__main__":main()
