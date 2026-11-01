#!/usr/bin/env python3
"""DRNAS World Cup R2: seven-policy paired replay on medium-difficulty official 2026 CNFs.

Diagnostic/re-used instances from frozen v18.0 list, NOT a new blind holdout.
The V18.4 Jacobian controller is NOT tested: fixed25/fixed50 are discrete
directional contrasts only. Historical official results are external references,
not measurements on this runner. Original Kissat binary is truly unmodified.
"""
import argparse, json, platform, subprocess, sys
from pathlib import Path
import official_parallel_v180 as core

MODES = ("baseline", "v1531", "cadical", "predict", "switch2048", "fixed25", "fixed50")
ROOT = Path("drnas-worldcup-r2-results")
ORIGINAL = Path("/tmp/kissat-r2-original/build/kissat")
PATCHED = Path("/tmp/kissat-v180/build/kissat")
core.MODES = MODES
core.ROOT = ROOT
core.TIME_LIMIT = 60.0
core.REPEATS = 2
original_run_one = core.run_one

def compare_one(case, mode, kissat, drnas, rule):
    # No patched code even compiled into the default Kissat reference.
    source = ORIGINAL if mode in ("baseline", "v1531") else PATCHED
    assert source.is_file(), source
    return original_run_one(case, mode, source, drnas, rule)

core.run_one = compare_one

def sha_binary(path):
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()

def runner_fingerprint():
    paths = {
      "kissat_original": ORIGINAL,
      "kissat_patched": PATCHED,
      "cadical_3_0_1": Path("/tmp/cadical-v180/build/cadical"),
      "drnas_v1531": Path("/tmp/v1531_nohang"),
    }
    assert all(p.is_file() for p in paths.values()), paths
    return {
      "platform": platform.platform(),
      "processor": subprocess.run(["lscpu"],text=True,capture_output=True,check=True).stdout,
      "binaries_sha256": {key:sha_binary(path) for key,path in paths.items()},
      "sources": {"kissat":"8af8e56f174b778aef3aa45af9f739b2a5f492c2",
                  "cadical":"c60730422e758ef1cebe7aeddf2dda31c996bf04",
                  "official_2026_track":"3e2dee7cf5aa643c77bf946280a3c1c520756ef9"},
      "reused_official_cases":True,
      "new_blind_holdout":False,
      "paired_same_runner_per_shard":True,
      "identical_physical_machine_across_shards":False,
      "v184_real_jacobian_controller_tested":False,
      "independent_unsat_certificates_checked":False,
      "fixed_restart_policies_are_discrete_control_contrasts":True
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--batch",type=int)
    p.add_argument("--aggregate",action="store_true")
    args=p.parse_args()
    if args.aggregate:
        core.main_aggregate()
        resultpath=ROOT/"aggregate.json"
        result=json.loads(resultpath.read_text())
        result.update(experiment="DRNAS World Cup R2 / directional-response diagnostic",
                      interpretation="re-run of frozen v18.0 moderate instances; not new official competition or unseen holdout",
                      actual_unmodified_kissat_reference=True,
                      additional_modes=["fixed25","fixed50"],
                      original_v184_jacobian_software_tested=False,
                      independent_unsat_proofs=False)
        resultpath.write_text(json.dumps(result,indent=2)+"\n")
        print("R2_AGGREGATE_FINAL",json.dumps(result),flush=True)
    elif args.batch in range(core.SHARDS):
        out=ROOT/f"batch_{args.batch}";out.mkdir(parents=True,exist_ok=True)
        (out/"r2_environment.json").write_text(json.dumps(runner_fingerprint(),indent=2)+"\n")
        (out/"r2_protocol.json").write_text(json.dumps({
            "experiment":"DRNAS R2 directional official 2026 diagnostics",
            "source":"v180 pre-registered 12 moderate official instances (already used in development)",
            "modes":MODES,"cap_seconds":core.TIME_LIMIT,"repeats":core.REPEATS,
            "sat_witness_check":True,"unsat_independent_proof":False,
            "selection":"external official published Kissat times, not DRNAS performance",
            "fairness":"paired per formula, serialized randomized order on same runner; 4 separate runners overall"},indent=2)+"\n")
        core.main_batch(args.batch)
    else:
        p.error("Provide --batch 0..3 or --aggregate")

if __name__=="__main__":
    main()
