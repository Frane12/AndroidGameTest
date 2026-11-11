#!/usr/bin/env python3
"""Matched native ATLAS23 test: ATLAS21M regressions and SATLIB source extension.

The first group REPLAYS ATLAS21M on its exact SHA. Second group uses SATLIB
indices 10..11, absent from ATLAS21M/22, but NOT promised globally blind.
No learned policy is trained on either test group. UNSAT is unverified.
"""
import argparse, collections, hashlib, json, os, pathlib, resource
import subprocess, sys, time
sys.path.insert(0, "research")
import drnas_atlas_wide500 as W
import drnas_atlas21_official as Verify

ARMS = ("V23_C7_STABLE", "A34_KEEP", "A34_ADAPT", "KISSAT")
ROOT = pathlib.Path("mre_atlas34")
BIN = pathlib.Path("mre_atlas23/bin")
REGRESSION_INDEX = (0, 1)
EXTENSION_INDEX = (10, 11)
EXTENSION_FAMILIES = ("uf250-1065", "uuf250-1065", "flat200-479")

def source_set(cohort):
    limit = 12 if cohort == "extension" else 2
    corpus = W.source_corpus(limit=limit)
    result = []
    for fam in (EXTENSION_FAMILIES if cohort == "extension" else W.SOURCES):
        indices = EXTENSION_INDEX if cohort == "extension" else REGRESSION_INDEX
        for index in indices:
            n, clauses, sha, archive_entry = corpus[fam][index]
            raw = W.canonical(n, clauses)
            assert hashlib.sha256(raw).hexdigest() == sha
            path = ROOT / cohort / (fam + "_" + str(index) + ".cnf")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
            result.append(dict(id=len(result), family=fam, index=index,
                sha256=sha, archive_entry=archive_entry,
                source_kind="SATLIB_normalized_original", path=str(path),
                bytes=len(raw), cohort=cohort))
    assert len({s["sha256"] for s in result}) == len(result)
    assert len(result) == (6 if cohort == "extension" else 10)
    return result

def run(source, mode, rep, cap):
    p = pathlib.Path(source["path"])
    assert hashlib.sha256(p.read_bytes()).hexdigest() == source["sha256"]
    if mode == "KISSAT":
        cmd = [str(BIN / "kissat"), str(p)]
    elif mode == "CMS":
        cmd = ["cryptominisat5", "--threads=1", "--verb=0", str(p)]
    else:
        cmd = [str(BIN / "drnas_atlas34"), str(p), "--mode", mode,
               "--time", str(cap), "--seed", str(rep+1)]
        if mode not in ("A", "V23_A_MIN"):
            cmd += ["--policy", "1.0,0.85"]
    def limits():
        cpu = int(cap) + 3
        resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu+1))
        resource.setrlimit(resource.RLIMIT_AS, (3*1024**3, 3*1024**3))
    t0 = time.monotonic()
    try:
        done = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=cap, preexec_fn=limits)
        rc, output, stderr = done.returncode, done.stdout, done.stderr
    except subprocess.TimeoutExpired:
        rc, output, stderr = 124, "", "timeout"
    elapsed = round(time.monotonic() - t0, 6)
    if rc not in (0, 10, 20, 124, -9, -24, -25, 15, -15):
        raise RuntimeError("Solver failed mode=" + mode + " rc=" +
                           str(rc) + " stderr=" + stderr[-400:])
    sat = rc == 10 and Verify.model_ok(p, output)
    if rc == 10 and not sat:
        raise RuntimeError("INVALID SAT original witness: " + mode + " " +
                           source["sha256"])
    status = "SAT_VERIFIED" if sat else "UNSAT_UNVERIFIED" if rc == 20 else "UNKNOWN"
    metrics = {}
    for line in output.splitlines():
        if line.startswith("ATLAS13_TRIAL "):
            metrics = dict(a.split("=", 1) for a in line.split()[1:] if "=" in a)
    keys = ("conflicts", "decisions", "propagations", "watch_visits",
            "atlas15_deleted", "atlas15_minimized", "atlas16_compactions",
            "atlas16_maxrss_kb", "atlas23_min_only",
            "atlas23_age_protect", "atlas23_stable_phase")
    telem = {key: int(float(metrics.get(key, 0))) for key in keys}
    # Fail closed: ensure dispatch actually activated the requested experiment.
    if rc in (10, 20) and mode.startswith("V23_"):
        flag = {"V23_A_MIN":"atlas23_min_only",
                "V23_C7_AGE":"atlas23_age_protect",
                "V23_C7_STABLE":"atlas23_stable_phase"}[mode]
        assert telem[flag] == 1, ("Mode was not activated", mode, flag)
    return dict(sha256=source["sha256"], family=source["family"],
        index=source["index"], cohort=source["cohort"], arm=mode, rep=rep,
        status=status, original_SAT_witness_verified=sat,
        independent_UNSAT_proof_verified=False, E2E_s=elapsed,
        PAR2_reported_s=elapsed if rc in (10, 20) else 2*cap,
        PAR2_verified_s=elapsed if sat else 2*cap,
        telemetry=telem)

def summarize(rows, cap):
    results = {}
    for arm in ARMS:
        subset = [r for r in rows if r["arm"] == arm]
        results[arm] = dict(trials=len(subset),
            SAT_verified=sum(r["status"] == "SAT_VERIFIED" for r in subset),
            UNSAT_unverified=sum(r["status"] == "UNSAT_UNVERIFIED" for r in subset),
            timeouts=sum(r["status"] == "UNKNOWN" for r in subset),
            PAR2_reported_s=round(sum(r["PAR2_reported_s"] for r in subset), 5),
            PAR2_verified_s=round(sum(r["PAR2_verified_s"] for r in subset), 5),
            E2E_s=round(sum(r["E2E_s"] for r in subset), 5),
            conflicts=sum(r["telemetry"]["conflicts"] for r in subset),
            watch_visits=sum(r["telemetry"]["watch_visits"] for r in subset),
            learned_deleted=sum(r["telemetry"]["atlas15_deleted"] for r in subset))
    return results

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cohort", choices=("smoke", "regression", "extension"),
                    required=True)
    ap.add_argument("--shard",type=int,choices=(0,1),required=True)
    args = ap.parse_args()
    cohort = "regression" if args.cohort == "smoke" else args.cohort
    cap = 3.0 if args.cohort == "smoke" else 10.0 if cohort == "regression" else 12.0
    sources = source_set(cohort)
    sources = [x for x in sources if x["id"]%2==args.shard]
    if args.cohort == "smoke":
        sources = sources[:1]
    rows = []
    print("ATLAS34_MANIFEST " + json.dumps(dict(cohort=args.cohort,
        source_count=len(sources), arms=list(ARMS), cap_s=cap,
        one_logical_CPU=True, repetitions=1 if args.cohort=="smoke" else 2,
        globally_blind=False, frozen_no_policy_learning=True), sort_keys=True), flush=True)
    for source in sources:
        for rep in range(1 if args.cohort == "smoke" else 2):
            statuses = set()
            for arm in ARMS:
                result = run(source, arm, rep, cap)
                rows.append(result)
                print("ATLAS34_TRIAL " + json.dumps(result, sort_keys=True), flush=True)
                if result["status"] != "UNKNOWN":
                    statuses.add(result["status"])
            if "SAT_VERIFIED" in statuses and "UNSAT_UNVERIFIED" in statuses:
                raise AssertionError("SAT/UNSAT disagreement " + source["sha256"])
    data = dict(cohort=args.cohort, cap_s=cap, sources=sources, rows=rows,
                summary=summarize(rows, cap), one_logical_CPU=True,
                independent_UNSAT_LRAT=False)
    target = ROOT / args.cohort / f"result_{args.shard}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, sort_keys=True, indent=2) + "\n")
    print("ATLAS34_FINAL " + json.dumps(dict(cohort=args.cohort, trials=len(rows),
          summary=data["summary"]), sort_keys=True), flush=True)

if __name__ == "__main__":
    main()
