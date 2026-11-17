#!/usr/bin/env python3
"""Audit-only replay of ORIGINAL 2026-11-17 XORLIN-CDCL1 run 44065020804.

NO SOLVER EXECUTION. Restore exact immutable original 12 CNFs, compiled
C++/embedded-Python solver binary, four original paired shard artifacts,
and verifier binaries from original GitHub Actions archive. Check all
120 unchanged trials, all source SHA-256s, and independently REVERIFY
the 10 retained original UNSAT proofs with external VeriPB/DRAT-trim.

This is an audit fix for a JSON serialization bug (mixed None/string
route keys), not a new training/test experiment or any solver modification.
"""
from collections import Counter
from pathlib import Path
import hashlib,json,os,shutil,subprocess,sys

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/"results/xorlin_cdcl1_paired12"
COLLECTED=ROOT/"collected"
MANIFEST=ROOT/"research/xorlin1_prospective_mixed12/inputs/manifest.json"
AUDIT=ROOT/"results/xorlin_cdcl1_audit_repair"
ORIGINAL_COMMIT="3ec2df9ee56e434aba9ee72b957fdbf3c69f2571"
ORIGINAL_RUN_ID="44065020804"
EXPECTED_MANIFEST="83c4607b66de977d3f1acfe62e348e1b652628efaf6e251e2e897d809addb296"
ARMS=("HYBRID_ON","HYBRID_OFF","Kissat","CaDiCaL","CryptoMiniSat")
PROOF_KINDS={"VERIPB_XORLIN1","DRAT","MODEL","FRAT"}

def sha(path):
    h=hashlib.sha256()
    with path.open("rb") as stream:
        for part in iter(lambda:stream.read(1<<20),b""):h.update(part)
    return h.hexdigest()

def require(cond,msg):
    if not cond:raise RuntimeError("XORLIN_CDCL1_AUDIT_FAILURE: "+str(msg))

def main():
    if hasattr(os,"sched_setaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
        require(len(os.sched_getaffinity(0))==1,"not on a single logical CPU")
    require(os.environ.get("DRNAS_SOURCE_RUN_ID")==ORIGINAL_RUN_ID,"wrong original run ID")
    require(os.environ.get("DRNAS_ORIGINAL_ARTIFACT_REPLAY")=="1","not audit-only mode")
    require(sha(MANIFEST)==EXPECTED_MANIFEST,"original source manifest changed")
    manifest=json.loads(MANIFEST.read_text())
    require(len(manifest["sources"])==12,"expected 12 frozen original sources")
    sources={s["id"]:s for s in manifest["sources"]}
    require(set(sources)==set(range(12)),"missing original source")
    for source in sources.values():
        require(sha(ROOT/source["path"])==source["sha256"],
                ("original CNF SHA changed",source["id"]))
    protocol=json.loads((OUT/"protocol.json").read_text())
    require(protocol["workflow_commit_sha256"]==ORIGINAL_COMMIT,
            "protocol not from original completed run")
    require(protocol["source_manifest_sha256"]==EXPECTED_MANIFEST,
            "original run source manifest mismatch")
    for label,path in [
      ("one-process native executable",ROOT/"build/drnas-xorlin-cdcl1"),
      ("VeriPB checker",ROOT/"veripb-tool/bin/veripb"),
      ("DRAT checker",ROOT/"build/drat-trim")]:
        require(path.is_file() and path.stat().st_size>0,
                ("required frozen executable missing",label))
    require(sha(ROOT/"build/drnas-xorlin-cdcl1")==
            protocol["new_binary_sha256"],"original native binary changed")
    require(sha(ROOT/"research/xorlin_cdcl1/solver.cpp")==
            protocol["new_native_cpp_sha256"],"original compiled C++ source changed")
    require(sha(ROOT/"src/drnas_x59.cpp")==
            protocol["old_cdcl_cpp_sha256"],"original CDCL core changed")
    for relative,digest in protocol["locked_math_source_sha256"].items():
        require(sha(ROOT/relative)==digest,("frozen mathematical method changed",relative))
    for relative,digest in protocol["frozen_reference_binaries_sha256"].items():
        require(sha(ROOT/relative)==digest,("frozen reference binary changed",relative))

    shard_hashes={}
    trial_rows=[]
    for shard in range(4):
        folder=COLLECTED/f"xorlin-cdcl1-shard-{shard}"
        matches=list(folder.glob("**/trials.jsonl"))
        require(len(matches)==1,("missing or duplicated original shard",shard,matches))
        raw=matches[0].read_bytes()
        shard_hashes[str(shard)]=hashlib.sha256(raw).hexdigest()
        target=OUT/f"shard-{shard}"
        require(not target.exists(),("refuse existing aggregate destination",shard))
        target.mkdir(parents=True)
        (target/"trials.jsonl").write_bytes(raw)
        records=[json.loads(line) for line in raw.decode("utf-8").splitlines()]
        require(len(records)==30,("expected 30 trials per source shard",shard,len(records)))
        trial_rows.extend(records)

    expected={(i,rep,arm) for i in range(12) for rep in range(2) for arm in ARMS}
    actual={(r["id"],r["rep"],r["arm"]) for r in trial_rows}
    require(len(trial_rows)==len(expected)==len(actual)==120 and actual==expected,
            ("original 120-paired-trial matrix incomplete",len(trial_rows),len(actual)))
    require(all(not r["critical"] for r in trial_rows),"original critical error flagged")
    require(all(r["source_sha256"]==sources[r["id"]]["sha256"] for r in trial_rows),
            "original source mismatch in trial")
    require(all(r["PAR2_strict_s"]==16 for r in trial_rows if not r["strict_accepted"]),
            "unverified original result has wrong PAR2")
    require(all(r["accepted"] and r.get("certificate_kind") in PROOF_KINDS
                for r in trial_rows if r["strict_accepted"]),
            "nonstandard original result scored strictly verified")

    external=[]
    for row in trial_rows:
        if row["arm"] not in ("HYBRID_ON","HYBRID_OFF") or not row["strict_accepted"]:
            continue
        require(row["status"]=="UNSAT_VERIFIED",
                ("cannot replay SAT model from absent original artifact",row["id"],row["arm"]))
        route=row.get("proof_route")
        require(route in ("GATE_VERIPB","CDCL_DRAT"),("invalid proof route",row))
        kind="VERIPB" if route=="GATE_VERIPB" else "DRAT"
        require(row["certificate_kind"]==
                ("VERIPB_XORLIN1" if kind=="VERIPB" else "DRAT"),
                ("proof kind inconsistent",row["id"],row["arm"]))
        filename=f"rep{row['rep']}_{row['arm']}_{kind}.proof"
        source=COLLECTED/f"xorlin-cdcl1-shard-{row['id']%4}"
        candidates=list(source.glob(f"**/source_{row['id']:02d}/{filename}"))
        require(len(candidates)==1,
                ("original standard proof missing or duplicated",row["id"],row["rep"],kind))
        proof=candidates[0]
        require(proof.stat().st_size==row["proof_bytes"] and
                sha(proof)==row["proof_sha256"],
                ("proof bytes or SHA changed",row["id"],row["rep"]))
        cnf=ROOT/sources[row["id"]]["path"]
        cmd=([str(ROOT/"veripb-tool/bin/veripb"),"--cnf",str(cnf),str(proof)]
             if kind=="VERIPB" else
             [str(ROOT/"build/drat-trim"),str(cnf),str(proof)])
        check=subprocess.run(cmd,capture_output=True,text=True,timeout=20)
        success=(check.returncode==0 and
                 ("s VERIFIED UNSATISFIABLE" if kind=="VERIPB" else "VERIFIED")
                 in check.stdout+check.stderr)
        require(success,("external standard checker rejected archived proof",
                         row["id"],row["rep"],kind,check.returncode,
                         (check.stdout+check.stderr)[-600:]))
        external.append({"id":row["id"],"rep":row["rep"],"arm":row["arm"],
                         "kind":kind,"sha256":sha(proof),"verified":True})
        print("XORLIN_CDCL1_AUDIT_PROOF_VERIFIED "+json.dumps(external[-1],
              sort_keys=True),flush=True)
    kinds=Counter(r["kind"] for r in external)
    require(len(external)==10 and kinds==Counter({"VERIPB":8,"DRAT":2}),
            ("proof coverage drift",len(external),dict(kinds)))
    require(all(not(any(r["status"]=="SAT_VERIFIED" and r["strict_accepted"] for r in trial_rows
                     if r["id"]==i) and
                      any(r["status"]=="UNSAT_VERIFIED" and r["strict_accepted"] for r in trial_rows
                          if r["id"]==i)) for i in range(12)),
            "contradictory independently verified SAT/UNSAT on original CNF")
    # Pre-JSON serialization regression check: no mixed None/string keys.
    route_totals={a:dict(Counter(str(r.get("proof_route") or "NO_ROUTE")
                    for r in trial_rows if r["arm"]==a))
                 for a in ("HYBRID_ON","HYBRID_OFF")}
    require(any("NO_ROUTE" in c for c in route_totals.values()),
            "original null-route JSON regression case not reproduced")
    json.dumps(route_totals,sort_keys=True)
    summary={"status":"PASS",
        "original_run_id":ORIGINAL_RUN_ID,
        "original_experiment_commit":ORIGINAL_COMMIT,
        "original_source_manifest_sha256":EXPECTED_MANIFEST,
        "original_shard_trial_log_sha256":shard_hashes,
        "original_attempts":len(trial_rows),
        "original_sources":len(sources),
        "original_solver_runs_reexecuted":0,
        "reverified_standard_proofs":len(external),
        "reverified_standard_proof_kinds":dict(kinds),
        "proof_records":external,
        "critical_count":0,
        "route_counter_none_key_fixed_for_JSON":True,
        "audit_patch_commit":os.environ.get("GITHUB_SHA"),
        "retrospective_not_blind":True,
        "original_solver_code_unchanged":True,
        "one_logical_CPU":True,"no_main_promotion":True}
    AUDIT.mkdir(parents=True,exist_ok=True)
    (AUDIT/"proof_recheck.json").write_text(
        json.dumps(summary,indent=2,sort_keys=True)+"\n")
    print("XORLIN_CDCL1_ORIGINAL_PROOF_REPLAY_AUDIT "+
          json.dumps({k:summary[k] for k in
          ("status","original_run_id","original_attempts","original_sources",
           "original_solver_runs_reexecuted","reverified_standard_proofs",
           "reverified_standard_proof_kinds","critical_count")},sort_keys=True),flush=True)

if __name__=="__main__":
    main()
