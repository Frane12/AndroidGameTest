#!/usr/bin/env python3
"""ID6 ORIGINAL 2025 Tseitin source, 2 repeats x 5 serial arms.

Retrospective after inspection: purpose is to independently certify standard
VeriPB UNSAT on unchanged original and measure SAME GitHub-runner E2E cap
versus exact previous frozen Kissat/CaDiCaL/CMS and old MATH5 emitter.
One logical CPU per solver, no parallel solver portfolio or main promotion.
"""
import collections
import hashlib
import json
import os
from pathlib import Path
import random
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/"results/tseitin_xor3carry_standard"
sys.path.insert(0,str(ROOT/"research"/"unified_evidence"))
import benchmark as frozen
sys.path.insert(0,str(ROOT/"research"/"graphclique"))
import real67 as graph
EMITTER=ROOT/"research"/"math5"/"emit_veripb_xor3_carry.py"
SOURCE_CHECKER=ROOT/"research"/"math5"/"check_math5.py"
CHECKER=ROOT/"veripb-tool/bin/veripb"
MANIFEST=ROOT/"research/graph_family_disjoint25/inputs/manifest.json"
ORIGINAL_SHA="9e4c57b9739f39a924d03267f05542831dc87fec9e9e2238f5e4ba11886378f4"
ARMS=("XOR3_CARRY_VERIPB","X59_MATH5_VERIPB",
      "Kissat","CaDiCaL","CryptoMiniSat")
CAP=8.0
REPS=2

def sha(path):return frozen.sha(path)

def one_cpu():
    if hasattr(os,"sched_setaffinity"):
        cpus=os.sched_getaffinity(0)
        assert cpus
        os.sched_setaffinity(0,{min(cpus)})
        assert len(os.sched_getaffinity(0))==1

def original():
    manifest=json.loads(MANIFEST.read_text())
    assert manifest["status"]=="FROZEN_SOURCE_ONLY_NO_SOLVER_RUN"
    assert manifest["selected_count"]==len(manifest["sources"])==10
    source=next(s for s in manifest["sources"] if s["id"]==6)
    assert source["family"]=="tseitin-formulas"
    assert source["gbd_hash"]=="42f1311ce504db8cc0cb590a568da20a"
    assert source["sha256"]==ORIGINAL_SHA
    assert sha(ROOT/source["path"])==ORIGINAL_SHA
    return source

def save(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,sort_keys=True,indent=2)+"\n")

def unknown(src,rep,started,status,reason=None,critical=False,kind=None,
            solver_s=0,project_checker_s=0,emitter_s=0,veripb_s=0,
            proof_bytes=0,proof_sha256=None):
    elapsed=time.perf_counter()-started
    if elapsed>CAP and not critical:status="E2E_OVER_CAP"
    return {"id":src["id"],"arm":"XOR3_CARRY_VERIPB","rep":rep,
      "source_sha256":src["sha256"],"family":src["family"],
      "status":status,"strict_accepted":False,"accepted":False,
      "certificate_kind":kind,"critical":critical,"reason":reason,
      "e2e_s":round(elapsed,6),"PAR2_strict_s":2*CAP,
      "PAR2_s":2*CAP,"proof_bytes":proof_bytes,
      "proof_sha256":proof_sha256,
      "solver_s":round(solver_s,6),
      "project_checker_s":round(project_checker_s,6),
      "emitter_s":round(emitter_s,6),"veripb_s":round(veripb_s,6)}

def strict_xor3(src,rep):
    started=time.perf_counter()
    cnf=ROOT/src["path"]
    assert sha(cnf)==src["sha256"]
    solver_s=project_s=emitter_s=veripb_s=0.0
    with tempfile.TemporaryDirectory(prefix="drnas-xor3-carry-original-") as d:
        dir=Path(d)
        native_proof=dir/"fallback.drat"
        math5_cert=dir/"math5.json"
        standard_proof=dir/"carry.pbp"
        standard_meta=dir/"carry-meta.json"
        cmd=frozen.command("X59_MATH5",cnf,native_proof,math5_cert,dir,CAP)
        run=frozen.execute(cmd,CAP)
        solver_s=run["wall_s"]
        if run["expired"]:
            return unknown(src,rep,started,"NATIVE_TIMEOUT",solver_s=solver_s)
        if run["returncode"]!=20 or "s UNSATISFIABLE" not in run["stdout"].splitlines():
            return unknown(src,rep,started,"NATIVE_UNSUPPORTED",
                reason=(run["stdout"]+run["stderr"])[-250:],
                solver_s=solver_s,
                critical=run["returncode"] not in (0,10,20,153))
        if not math5_cert.is_file() or (native_proof.exists() and native_proof.stat().st_size):
            return unknown(src,rep,started,"INVALID_MATH5_CERT_OR_MIXED_PROOF",
                critical=True,solver_s=solver_s)
        remaining=CAP-(time.perf_counter()-started)
        if remaining<=0:
            return unknown(src,rep,started,"NO_SOURCE_CHECK_BUDGET",solver_s=solver_s)
        source_check=frozen.execute([sys.executable,str(SOURCE_CHECKER),
            str(cnf),str(math5_cert)],remaining)
        project_s=source_check["wall_s"]
        if source_check["expired"]:
            return unknown(src,rep,started,"SOURCE_CHECK_TIMEOUT",
                solver_s=solver_s,project_checker_s=project_s)
        if source_check["returncode"]!=0 or (
            "UNSAT_MATH5_CERTIFICATE_VERIFIED" not in source_check["stdout"]):
            return unknown(src,rep,started,"INVALID_MATH5_ORIGINAL_SOURCE",
                critical=True,solver_s=solver_s,project_checker_s=project_s,
                reason=(source_check["stdout"]+source_check["stderr"])[-350:])
        remaining=CAP-(time.perf_counter()-started)
        if remaining<=0:
            return unknown(src,rep,started,"NO_EMITTER_BUDGET",
                solver_s=solver_s,project_checker_s=project_s)
        emitted=frozen.execute([sys.executable,str(EMITTER),
            "--cnf",str(cnf),"--certificate",str(math5_cert),
            "--output",str(standard_proof),"--meta",str(standard_meta)],
            remaining)
        emitter_s=emitted["wall_s"]
        if emitted["expired"]:
            return unknown(src,rep,started,"PBP_EMITTER_TIMEOUT",
                solver_s=solver_s,project_checker_s=project_s,emitter_s=emitter_s)
        if emitted["returncode"]==2 and not standard_proof.exists():
            return unknown(src,rep,started,"PBP_UNSUPPORTED_SOURCE",
                solver_s=solver_s,project_checker_s=project_s,emitter_s=emitter_s)
        if (emitted["returncode"]!=0 or not standard_proof.exists()
            or not standard_meta.exists()):
            return unknown(src,rep,started,"INVALID_PBP_EMITTER",
                critical=True,solver_s=solver_s,project_checker_s=project_s,
                emitter_s=emitter_s,
                reason=(emitted["stdout"]+emitted["stderr"])[-350:])
        meta=json.loads(standard_meta.read_text())
        if meta.get("source_sha256")!=src["sha256"]:
            return unknown(src,rep,started,"INVALID_PBP_SOURCE_SHA",
                critical=True,solver_s=solver_s,project_checker_s=project_s,
                emitter_s=emitter_s)
        remaining=CAP-(time.perf_counter()-started)
        if remaining<=0:
            return unknown(src,rep,started,"NO_EXTERNAL_CHECK_BUDGET",
                solver_s=solver_s,project_checker_s=project_s,emitter_s=emitter_s)
        result=frozen.execute([str(CHECKER),"--cnf",str(cnf),
                               str(standard_proof)],remaining)
        veripb_s=result["wall_s"]
        if result["expired"]:
            return unknown(src,rep,started,"VERIPB_CHECK_TIMEOUT",
                solver_s=solver_s,project_checker_s=project_s,
                emitter_s=emitter_s,veripb_s=veripb_s)
        if (result["returncode"]!=0 or
            "s VERIFIED UNSATISFIABLE" not in result["stdout"]+result["stderr"]):
            return unknown(src,rep,started,"INVALID_EXTERNAL_VERIPB",
                critical=True,solver_s=solver_s,project_checker_s=project_s,
                emitter_s=emitter_s,veripb_s=veripb_s,
                reason=(result["stdout"]+result["stderr"])[-350:])
        elapsed=time.perf_counter()-started
        if elapsed>CAP:
            return unknown(src,rep,started,"E2E_OVER_CAP",
                solver_s=solver_s,project_checker_s=project_s,
                emitter_s=emitter_s,veripb_s=veripb_s)
        verified_dir=OUT/"verified_original_proofs"
        verified_dir.mkdir(parents=True,exist_ok=True)
        (verified_dir/f"ID6_rep{rep}_veripb_accepted.pbp").write_bytes(standard_proof.read_bytes())
        (verified_dir/f"ID6_rep{rep}_math5_certificate.json").write_bytes(math5_cert.read_bytes())
        (verified_dir/f"ID6_rep{rep}_source_metadata.json").write_bytes(standard_meta.read_bytes())
        return {"id":src["id"],"arm":"XOR3_CARRY_VERIPB","rep":rep,
          "source_sha256":src["sha256"],"family":src["family"],
          "status":"UNSAT_VERIFIED","accepted":True,"strict_accepted":True,
          "certificate_kind":"VERIPB_XOR3_CARRY_RED_RUP_CP",
          "critical":False,"reason":None,
          "proof_bytes":standard_proof.stat().st_size,
          "proof_sha256":sha(standard_proof),
          "source_certificate_sha256":sha(math5_cert),
          "e2e_s":round(elapsed,6),"PAR2_s":round(elapsed,6),
          "PAR2_strict_s":round(elapsed,6),
          "solver_s":round(solver_s,6),
          "project_checker_s":round(project_s,6),
          "emitter_s":round(emitter_s,6),
          "veripb_s":round(veripb_s,6)}

def run():
    one_cpu()
    source=original()
    checksums=frozen.pinned()
    assert checksums["veripb-tool/bin/veripb"]==sha(CHECKER)
    OUT.mkdir(parents=True,exist_ok=True)
    records=[]
    for rep in range(REPS):
        arms=list(ARMS)
        random.Random(f"MATH5-XOR3-ORIGINAL-ID6-{rep}").shuffle(arms)
        for arm in arms:
            if arm=="XOR3_CARRY_VERIPB":
                row=strict_xor3(source,rep)
            elif arm=="X59_MATH5_VERIPB":
                row=graph.old.standard_trial(source,rep)
            else:
                row=frozen.trial(source,arm,rep)
            assert row["arm"]==arm and row["rep"]==rep
            assert row["source_sha256"]==source["sha256"]
            records.append(row)
            print("MATH5_XOR3_TSEITIN_TRIAL "+json.dumps({
                "arm":arm,"rep":rep,"status":row["status"],
                "kind":row.get("certificate_kind"),
                "strict":row["strict_accepted"],
                "critical":row["critical"],
                "strict_PAR2_s":row["PAR2_strict_s"],
                "e2e_s":row["e2e_s"],
                "proof_bytes":row.get("proof_bytes",0)},sort_keys=True),flush=True)
            save(OUT/"trials.json",records)
    assert len(records)==len(ARMS)*REPS==10
    assert len({(r["arm"],r["rep"]) for r in records})==10
    errors=[r for r in records if r["critical"]]
    for r in records:
        if r["strict_accepted"] and r["certificate_kind"] not in (
            "MODEL","DRAT","FRAT","VERIPB_XOR3_CARRY_RED_RUP_CP","VERIPB_MATH5"):
            errors.append({"reason":"NONSTANDARD_PROOF_WRONGLY_ACCEPTED",**r})
    totals={arm:{
       "attempts":REPS,
       "strict_verified":sum(r["strict_accepted"] for r in records if r["arm"]==arm),
       "strict_PAR2_s":round(sum(r["PAR2_strict_s"] for r in records if r["arm"]==arm),6),
       "statuses":dict(collections.Counter(r["status"] for r in records if r["arm"]==arm)),
       "proof_kinds":dict(collections.Counter(
            r.get("certificate_kind") for r in records
            if r["arm"]==arm and r["strict_accepted"]))} for arm in ARMS}
    result={"status":"COMPLETE" if not errors else "CRITICAL",
       "source_id":source["id"],"source_family":source["family"],
       "source_sha256":source["sha256"],"attempts":len(records),
       "cap_s":CAP,"repetitions":REPS,"critical_count":len(errors),
       "totals":totals,
       "errors":errors,
       "one_logical_cpu_per_solver":True,
       "same_E2E_8s_cap_on_all_solver_and_proof_validation":True,
       "frozen_reference_SHA256":checksums,
       "new_emitter_SHA256":sha(EMITTER),
       "source_frozen_manifest_SHA256":sha(MANIFEST),
       "retrospective_development_set_after_structure_discovery":True,
       "not_blind":True,"no_main_promotion":True}
    save(OUT/"final.json",result)
    print("MATH5_XOR3_TSEITIN_FINAL "+json.dumps(result,sort_keys=True),flush=True)
    if errors:raise SystemExit(1)

if __name__=="__main__":
    run()
