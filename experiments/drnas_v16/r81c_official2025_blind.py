#!/usr/bin/env python3
"""R81C fresh SAT Competition 2025 source holdout versus frozen Kissat/R28/R65.
Source IDs excluded using R63-R78 attempted registries; selected BEFORE timings
with a fixed SHA salt. Not proof of global novelty or official placement.
"""
import argparse, collections, csv, hashlib, json, os, random, subprocess, tempfile, time
from pathlib import Path
import r78_xor_adaptive_prospective as r78
import r81c_exact_algebra as r81c

PROTO="DRNAS-R81C-SAT2025-SOURCE-HOLDOUT-20261104-v1"
SALT="DRNAS-R81C-OFFICIAL2025-EXCLUDE-ALL-R78-ATTEMPTS-20261104-v1"
N,SHARDS,REPS,CAP=16,8,2,30.0
MODES=("clean_kissat","r28_gf2","r65_full","r81c_exact")

def check(x,why):
    if not x:raise RuntimeError("R81C_BLIND_FAIL_CLOSED "+why)

def digest(p):
    h=hashlib.sha256()
    with open(p,"rb") as f:
        for b in iter(lambda:f.read(1<<20),b""):h.update(b)
    return h.hexdigest()

def configure():
    r78.PROTO=PROTO
    r78.SALT=SALT
    r78.N=N
    r78.SHARDS=SHARDS
    r78.REPS=REPS
    r78.CAP=CAP
    r78.MODES=MODES

def freeze(args):
    configure()
    previous=Path(args.r78)/"world"/"manifest.json"
    check(previous.is_file(),"R78 selected/attempted manifest absent")
    history=json.loads(previous.read_text())
    check(history["ready"]==24 and len(history["cases"])==24,
          "R78 manifest incomplete")
    blocked_ids={x["gbd"] for x in history["selection_attempts"]}
    blocked_ids.update(c["gbd"] for c in history["cases"])
    blocked_sha={c["sha256"] for c in history["cases"]}
    check(len(blocked_sha)==24,"R78 SHA registry duplicate")
    original_history=r78.old.history
    def with_r78_exclusions(a):
        seen,hashes,binary,registry=original_history(a)
        check(not (hashes & blocked_sha),"historical SHA overlap")
        seen|=blocked_ids
        hashes|=blocked_sha
        registry["r78_manifest_sha256"]=digest(previous)
        registry["r78_attempted_gbd_excluded"]=len(blocked_ids)
        registry["r78_accepted_sha_excluded"]=len(blocked_sha)
        return seen,hashes,binary,registry
    r78.old.history=with_r78_exclusions
    try:
        r78.freeze(args)
    finally:
        r78.old.history=original_history
    manifest_path=Path(args.out)/"manifest.json"
    m=json.loads(manifest_path.read_text())
    check(m["ready"]==N and m["protocol"]==PROTO,"not enough fresh original sources")
    check(not ({c["gbd"] for c in m["cases"]}&blocked_ids),
          "R78 already attempted source reused")
    check(not ({c["sha256"] for c in m["cases"]}&blocked_sha),
          "R78 accepted source SHA reused")
    m["gate_rule"]=dict(
        exact_algebra="R81C direct certified GF2 iff every original clause is a complete XOR block or original unit",
        otherwise="pinned unchanged Kissat",gf2_budget_s=3.0)
    m["limitations"]+= [
        "16 original SAT Competition 2025 catalog sources; R78 attempted IDs explicitly excluded",
        "Also inherits R63/R66/R67/R72/R73/R77 conservative exclusion registry",
        "Selection was frozen before any solver timing; no structure or runtime prescreen",
        "Other undocumented historical source attempts cannot be ruled out",
        "No independent official SAT2025 UNSAT status imported: uncertified Kissat UNSAT remains provisional",
        "Eight GitHub runners may have different CPU models; modes paired by formula within runner",
        "This is not official competition scoring nor an independent third-party replication"]
    manifest_path.write_text(json.dumps(m,sort_keys=True,indent=2)+"\n")
    print("R81C_BLIND_FREEZE_PASS",json.dumps(dict(source_count=N,
       r78_excluded_ids=len(blocked_ids),r78_excluded_sha=len(blocked_sha),
       categories=m["observed_strata"])),flush=True)

def measure(args):
    configure()
    root=Path(args.sources)
    m=json.loads((root/"manifest.json").read_text())
    check(m["protocol"]==PROTO and m["ready"]==N,"wrong frozen source manifest")
    check(0<=args.shard<SHARDS,"bad shard")
    binaries=Path(args.binaries).resolve()
    checksum=subprocess.run(["sha256sum","-c","binary.sha256"],cwd=binaries,
                           capture_output=True,text=True)
    check(checksum.returncode==0,"binary SHA mismatch "+checksum.stderr)
    kissat=(binaries/"kissat").resolve()
    r28=(binaries/"r28_gf2").resolve()
    check(digest(kissat)==m["registry"]["binary_sha"],"historical Kissat pin drift")
    if hasattr(os,"sched_setaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    r78.r65.MAX_PREP_S=2.0
    results=[]
    for case in m["cases"][args.shard::SHARDS]:
        source=root/case["filename"]
        check(digest(source)==case["sha256"],"source SHA drift")
        for rep in range(REPS):
            modes=list(MODES)
            random.Random(int(hashlib.sha256((PROTO+case["sha256"]+str(rep)).encode()).hexdigest(),16)).shuffle(modes)
            for mode in modes:
                start=time.monotonic()
                argv=[kissat,source]
                action="kissat"
                direct=None
                clauses_added=0
                with tempfile.TemporaryDirectory(prefix="r81c-holdout-") as tmp:
                    if mode=="r28_gf2":
                        argv=[r28,source,kissat];action="r28"
                    elif mode=="r65_full":
                        action="r65"
                        _,_,clauses,_,_=r78.r71.prepare(root,case)
                        clauses_added=len(clauses)
                        if clauses:
                            target=Path(tmp)/"augmented.cnf"
                            r78.r64.augment(source,target,case["variables"],case["clauses"],clauses)
                            argv=[kissat,target]
                    elif mode=="r81c_exact":
                        action="r81c"
                        direct=r81c.solve(source,case,max_budget_s=3.0)
                    overhead=time.monotonic()-start
                    remaining=CAP-overhead
                    if direct and direct.get("solved"):
                        answer=direct["answer"];solver_wall=0.0;timeout=False
                        route=direct["route"]
                    else:
                        answer,solver_wall,timeout,route=r78.run_solver(argv,source,remaining)
                        if direct:route="fallback_"+direct["route"]
                    elapsed=time.monotonic()-start
                    solved=answer!="UNKNOWN" and not timeout and elapsed<=CAP
                    result=dict(source_id=case["gbd"],source_sha256=case["sha256"],
                        group=case["group"],rep=rep,mode=mode,answer=answer,
                        solved=solved,timeout=not solved,
                        end_to_end_s=round(elapsed,6),
                        preprocess_s=round(overhead,6),
                        par2_s=round(elapsed if solved else 2*CAP,6),
                        native_route=route,clauses_added=clauses_added,
                        r81c_route=direct.get("route") if direct else None,
                        r81c_rank=direct.get("rank") if direct else None,
                        r81c_model_hex=hex(direct["model"]) if direct and direct.get("solved") and answer=="SAT" else None,
                        r81c_certificate=direct.get("proof") if direct and direct.get("solved") and answer=="UNSAT" else None,
                        seed=rep,runner=os.environ.get("RUNNER_NAME",""),
                        commit=os.environ.get("GITHUB_SHA",""),
                        binary_sha256=digest(r28 if action=="r28" else kissat))
                    results.append(result)
                    print("R81C_BLIND_TRIAL",json.dumps({k:result[k] for k in
                        ("source_id","rep","mode","answer","par2_s","r81c_route")}),flush=True)
    check(len(results)==len(m["cases"][args.shard::SHARDS])*REPS*len(MODES),"incomplete shard")
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    report=dict(protocol=PROTO,shard=args.shard,
        manifest_sha256=digest(root/"manifest.json"),
        binaries={"kissat":digest(kissat),"r28_gf2":digest(r28)},
        cpu=Path("/proc/cpuinfo").read_text(errors="replace")[:2000],rows=results)
    (out/"r81c-blind-shard.json").write_text(json.dumps(report,indent=2)+"\n")
    print("R81C_BLIND_SHARD_PASS",args.shard,len(results),flush=True)

def audit(args):
    configure()
    root=Path(args.sources);m=json.loads((root/"manifest.json").read_text())
    check(m["protocol"]==PROTO and m["ready"]==N,"frozen source manifest wrong")
    source_by_sha={c["sha256"]:c for c in m["cases"]}
    check(len(source_by_sha)==N,"duplicate source SHA")
    for c in m["cases"]:
        check(digest(root/c["filename"])==c["sha256"],"original SHA failure")
    rows=[];binary_sets=[];cpu=[]
    for shard in range(SHARDS):
        f=Path(args.combined)/f"r81c-blind-shard-{shard}"/"results"/"r81c-blind-shard.json"
        check(f.is_file(),"missing benchmark shard "+str(shard))
        d=json.loads(f.read_text())
        check(d["protocol"]==PROTO and d["shard"]==shard
              and d["manifest_sha256"]==digest(root/"manifest.json"),"shard manifest mismatch")
        binary_sets.append(tuple(sorted(d["binaries"].items())))
        cpu.append(dict(shard=shard,cpu=d["cpu"].splitlines()[:12]))
        subset=m["cases"][shard::SHARDS]
        check(len(d["rows"])==len(subset)*REPS*len(MODES),"wrong shard row count")
        rows+=d["rows"]
    check(len(set(binary_sets))==1 and len(rows)==N*REPS*len(MODES),
          "binary drift or incomplete trials")
    grouped=collections.defaultdict(list)
    for r in rows:
        check(r["source_sha256"] in source_by_sha and
              r["commit"] and r["runner"] and r["seed"] in range(REPS),
              "trial provenance invalid")
        grouped[(r["source_sha256"],r["seed"])].append(r)
    check(len(grouped)==N*REPS,"missing formula/seed pairs")
    for (sha,rep),paired in grouped.items():
        check(len(paired)==len(MODES) and {r["mode"] for r in paired}==set(MODES),
              "unpaired formula/control")
        verdicts={r["answer"] for r in paired if r["answer"]!="UNKNOWN"}
        check(len(verdicts)<=1,"SAT/UNSAT contradiction")
        for r in paired:
            if r["mode"]!="r81c_exact":continue
            original=root/source_by_sha[sha]["filename"]
            if r["r81c_route"]=="gf2_sat_model_verified":
                check(r["answer"]=="SAT" and r81c.verify_sat_model(
                    original,int(r["r81c_model_hex"],16),source_by_sha[sha]["variables"]),
                    "SAT witness fails independent original CNF check")
            if r["r81c_route"]=="gf2_unsat_certified":
                check(r["answer"]=="UNSAT" and r81c.verify_unsat_certificate(
                    original,r["r81c_certificate"]),"GF2 proof fails independent check")
    summary={}
    for mode in MODES:
        arr=[r for r in rows if r["mode"]==mode]
        summary[mode]=dict(solved=sum(r["solved"] for r in arr),
             attempts=len(arr),par2_s=round(sum(r["par2_s"] for r in arr),6))
    pairs=[]
    for sha,c in sorted(source_by_sha.items()):
        for rep in range(REPS):
            matched=grouped[(sha,rep)]
            t=dict(source_id=c["gbd"],source_sha256=sha,rep=rep,group=c["group"])
            t.update({r["mode"]:r["par2_s"] for r in matched})
            pairs.append(t)
    # Cluster bootstrap resamples formulas, not repeated attempts.
    by_source=collections.defaultdict(lambda:collections.defaultdict(float))
    for row in rows:by_source[row["source_sha256"]][row["mode"]]+=row["par2_s"]
    items=list(by_source.values())
    rng=random.Random(8105)
    gains=[]
    for _ in range(6000):
        draw=[items[rng.randrange(len(items))] for _ in items]
        kiss=sum(x["clean_kissat"] for x in draw)
        new=sum(x["r81c_exact"] for x in draw)
        gains.append(100*(kiss-new)/kiss)
    gains.sort()
    ci=[round(gains[int(.025*len(gains))],5),
        round(gains[int(.975*len(gains))],5)]
    actions=dict(collections.Counter(r["r81c_route"] for r in rows
                                      if r["mode"]=="r81c_exact"))
    report=dict(protocol=PROTO,status="PASS_UNOFFICIAL",
        official_competition_score=False,
        sources=N,trials=len(rows),shards=SHARDS,repeats=REPS,cap_s=CAP,
        source_manifest_sha256=digest(root/"manifest.json"),
        binary_sha256=dict(binary_sets[0]),summary=summary,
        r81c_routes=actions,bootstrap_formula_95_ci_gain_pct=ci,
        pairs=pairs,hosts=cpu,rows=rows,limitations=m["limitations"])
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    (out/"results.json").write_text(json.dumps(report,indent=2)+"\n")
    with (out/"paired.csv").open("w",newline="") as f:
        fields=["source_id","source_sha256","rep","group"]+list(MODES)
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(pairs)
    print("R81C_BLIND_FINAL_AUDIT_PASS",json.dumps(dict(summary=summary,
        routes=actions,bootstrap_ci=ci,source_count=N,attempts=len(rows))),flush=True)

def main():
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest="cmd",required=True)
    f=sub.add_parser("freeze")
    for key in ("r63","r66","r67","r67final","r73","r77","r78","kissat","out"):
        f.add_argument("--"+key,required=True)
    measure_parser=sub.add_parser("measure")
    for key in ("sources","binaries","out"):measure_parser.add_argument("--"+key,required=True)
    measure_parser.add_argument("--shard",type=int,required=True)
    auditp=sub.add_parser("audit")
    for key in ("sources","combined","out"):auditp.add_argument("--"+key,required=True)
    a=p.parse_args()
    if a.cmd=="freeze":freeze(a)
    elif a.cmd=="measure":measure(a)
    else:audit(a)
if __name__=="__main__":main()
