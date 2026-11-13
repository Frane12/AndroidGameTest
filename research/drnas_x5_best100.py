#!/usr/bin/env python3
"""Frozen original SAT2024 comparison; X5_NO_MIN is the primary reference."""
import argparse
import collections
import json
import math
import os
from pathlib import Path
import random
from types import SimpleNamespace
import tempfile

import drnas_x5_bench as B
from drnas_x5_report import comparison

ROOT = Path(__file__).resolve().parents[1]
CAP, REPS, COUNT, SHARDS = 5.0, 2, 100, 10
ARMS = ["X5_NO_MIN", "X5", "Kissat", "CaDiCaL", "CMS"]
REFERENCES = ["Kissat", "CaDiCaL", "CMS"]
BINARIES = ["drnas-x5", "kissat", "cadical", "cms", "drat-trim", "frat-rs", "timed"]
SOURCES = ["src/drnas_x5.cpp", "research/drnas_x5_bench.py",
           "research/drnas_x47_long_bench.py", "research/drnas_x5_report.py",
           "research/drnas_x5_best100.py"]
PROTOCOL = ROOT / "best100_protocol.json"


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def read(path):
    return json.loads(path.read_text())


def identities():
    runtime = ROOT / "build/best100_runtime.txt"
    return {"binary_sha256": {name: B.sha(ROOT / "build" / name) for name in BINARIES},
            "source_sha256": {name: B.sha(ROOT / name) for name in SOURCES},
            "runtime_sha256": B.sha(runtime) if runtime.exists() else None}


def original_sources(inputs):
    manifest = inputs / "source_manifest.json"
    sources = read(manifest)["sources"]
    require(len(sources) == COUNT, "Expected exactly 100 original sources")
    require({s["id"] for s in sources} == set(range(COUNT)), "Invalid original source IDs")
    require(len({s["sha256"] for s in sources}) == COUNT, "Duplicate original SHA")
    require(len({s["file"] for s in sources}) == COUNT, "Duplicate source filenames")
    sources = sorted(sources, key=lambda s: s["id"])
    for source in sources:
        path = (inputs / source["file"]).resolve()
        require(path.parent == inputs.resolve(), "Source path leaves input directory")
        require(path.stat().st_size == source["bytes"], "Original byte count changed")
        require(B.sha(path) == source["sha256"], "Original CNF SHA mismatch")
        require(isinstance(source["family"], str) and source["family"], "Missing family")
    return sources, B.sha(manifest)


def freeze(inputs):
    sources, manifest_sha = original_sources(inputs)
    require(not PROTOCOL.exists(), "Refusing to replace existing frozen protocol")
    protocol = {"protocol": "X5-best100-verified-e2e-v1", "primary": "X5_NO_MIN",
                "arms": ARMS, "count": COUNT, "repeats": REPS, "shards": SHARDS,
                "cap_s": CAP, "total_trials": COUNT * REPS * len(ARMS),
                "original_source_run": 43396550073, "frozen_binary_run": 43368689724,
                "original_source_artifact": "drnas-x52-original100-frozen-source-bytes",
                "frozen_binary_artifact": "drnas-x5-frozen-binaries",
                "source_manifest_sha256": manifest_sha, "sources": sources,
                "source_sha256_ordered": [s["sha256"] for s in sources],
                "source_families": dict(collections.Counter(s["family"] for s in sources)),
                "seed_rule": "20261113 + 1009 * original_source_id + 37 * repetition",
                "timing": "5 s shared solver, original SAT witness and independent proof verification budget",
                "selection": "Existing metadata-only family-round-robin selection with original-byte SHA deduplication",
                "cohort": "original_SAT2024_retrospective",
                "learning": False, "promotion": False,
                "limitations": ["Reused original competition CNFs; not a new blind holdout.",
                                "Two repetitions of one CNF are one bootstrap cluster.",
                                "This metadata-selected set does not represent all industrial SAT instances.",
                                "X5 is a secondary control; X5_NO_MIN remains the primary reference."],
                **identities()}
    save(PROTOCOL, protocol)
    B.emit("BEST100_FREEZE", {k: v for k, v in protocol.items() if k != "sources"})


def check_protocol(inputs, check_binaries=True):
    protocol = read(PROTOCOL)
    if inputs is None:
        # Report consumes the sealed metadata; original bytes were checked before every shard.
        sources, manifest_sha = protocol["sources"], protocol["source_manifest_sha256"]
        require(len(sources) == COUNT and [s["id"] for s in sources] == list(range(COUNT)), "Invalid sealed source IDs")
        require(len({s["sha256"] for s in sources}) == COUNT, "Duplicate sealed original SHA")
    else:
        sources, manifest_sha = original_sources(inputs)
    expected = {"protocol": "X5-best100-verified-e2e-v1", "primary": "X5_NO_MIN",
                "count": COUNT, "repeats": REPS, "shards": SHARDS, "cap_s": CAP,
                "arms": ARMS, "total_trials": COUNT * REPS * len(ARMS),
                "sources": sources, "source_manifest_sha256": manifest_sha,
                "source_sha256_ordered": [s["sha256"] for s in sources],
                "original_source_run": 43396550073, "frozen_binary_run": 43368689724,
                "learning": False, "promotion": False}
    for key, value in expected.items():
        require(protocol[key] == value, "Protocol mismatch: " + key)
    require(protocol["source_sha256"] == {p: B.sha(ROOT / p) for p in SOURCES}, "Harness/source drift")
    if check_binaries:
        actual = identities()
        for key in ("binary_sha256", "runtime_sha256"):
            require(protocol[key] == actual[key], "Frozen execution identity drift: " + key)
    return protocol, sources


def shard(inputs, index):
    require(index in range(SHARDS), "Shard index out of range")
    protocol, sources = check_protocol(inputs)
    os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    cpus = sorted(os.sched_getaffinity(0))
    require(len(cpus) == 1, "Expected one logical CPU")
    selected = [s for s in sources if s["id"] % SHARDS == index]
    require(len(selected) == COUNT // SHARDS, "Wrong shard source count")
    out = ROOT / "best100_shards" / str(index)
    out.mkdir(parents=True, exist_ok=False)
    manifest = {"protocol_sha256": B.sha(PROTOCOL), "shard": index,
                "count": len(selected), "logical_cpus": cpus, "sources": selected,
                **{k: protocol[k] for k in ("arms", "cap_s", "repeats", "shards", "primary",
                                            "binary_sha256", "source_sha256", "source_manifest_sha256", "runtime_sha256")}}
    save(out / "manifest.json", manifest)
    args = SimpleNamespace(cap=CAP, checker=ROOT / "build/drat-trim", frat=ROOT / "build/frat-rs",
                           kissat=str(ROOT / "build/kissat"), cadical=str(ROOT / "build/cadical"),
                           cms=str(ROOT / "build/cms"))
    rows = []
    with tempfile.TemporaryDirectory() as temporary, (out / "trials.jsonl").open("w") as log:
        for number, source in enumerate(selected):
            path = (inputs / source["file"]).resolve()
            raw = path.read_bytes()
            require(B.sha(path) == source["sha256"], "Original changed before trial")
            original = {**source, "content": raw.decode("ascii"), "cert": "ORIGINAL_PROOF_REQUIRED"}
            for rep in range(REPS):
                order = ARMS.copy()
                random.Random(20261113 + 1009 * source["id"] + 37 * rep).shuffle(order)
                for arm in order:
                    row = B.run(arm, original, path, Path(temporary), args)
                    row.update(source_id=source["id"], sha256=source["sha256"], family=source["family"],
                               rep=rep, shard=index, measurement_run_id=os.getenv("GITHUB_RUN_ID", "local"))
                    rows.append(row)
                    log.write(json.dumps(row, sort_keys=True) + "\n")
                    log.flush()
                    B.emit("BEST100_TRIAL", row)
            B.emit("BEST100_PROGRESS", {"shard": index, "completed": number + 1,
                                         "sources": len(selected), "totals": B.summarize(rows, ARMS)})
    for key, value in identities().items():
        require(value == protocol[key], "Execution identity changed during benchmark: " + key)
    summary = {"shard": index, "protocol_sha256": B.sha(PROTOCOL),
               "trials": len(rows), "totals": B.summarize(rows, ARMS)}
    save(out / "report.json", summary)
    B.emit("BEST100_SHARD_FINAL", summary)


def stats(rows, arms=ARMS):
    result = B.summarize(rows, arms)
    for arm, value in result.items():
        rr = [r for r in rows if r["arm"] == arm]
        value.update(mean_PAR2_s=value["PAR2_s"] / len(rr),
                     timeouts=sum(r["status"] == "TIMEOUT" for r in rr),
                     unknown=sum(r["status"] == "UNKNOWN" for r in rr),
                     unverified_answers=sum(r["status"] in ("SAT", "UNSAT") and not r["verified"] for r in rr),
                     not_accepted=sum(not r["accepted"] for r in rr))
    return result


def report(inputs, results):
    protocol, sources = check_protocol(None, check_binaries=False)
    manifests = sorted(results.rglob("manifest.json"))
    require(len(manifests) == SHARDS, "Expected exactly ten shard manifests")
    rows, seen_shards = [], set()
    for path in manifests:
        manifest = read(path)
        index = manifest["shard"]
        require(index in range(SHARDS) and index not in seen_shards, "Duplicate or invalid shard")
        seen_shards.add(index)
        require(manifest["protocol_sha256"] == B.sha(PROTOCOL), "Shard protocol mismatch")
        for key in ("arms", "cap_s", "repeats", "shards", "primary", "binary_sha256",
                    "source_sha256", "source_manifest_sha256", "runtime_sha256"):
            require(manifest[key] == protocol[key], "Shard metadata mismatch: " + key)
        selected = [s for s in sources if s["id"] % SHARDS == index]
        require(manifest["sources"] == selected and manifest["count"] == len(selected), "Shard source mismatch")
        require(len(manifest["logical_cpus"]) == 1, "Shard used more than one logical CPU")
        batch = [json.loads(line) for line in path.with_name("trials.jsonl").read_text().splitlines()]
        expected = {(s["sha256"], rep, arm) for s in selected for rep in range(REPS) for arm in ARMS}
        require(len(batch) == len(expected) and {(r["sha256"], r["rep"], r["arm"]) for r in batch} == expected,
                "Incomplete, duplicate or unpaired shard trials")
        for row in batch:
            source = sources[row["source_id"]]
            require(row["shard"] == index and source in selected and row["sha256"] == source["sha256"]
                    and row["family"] == source["family"], "Trial source metadata mismatch")
            require(row["status"] in ("SAT", "UNSAT", "TIMEOUT", "UNKNOWN"), "Invalid trial status")
            require(all(math.isfinite(row[k]) and row[k] >= 0 for k in ("PAR2", "e2e_s", "solve_s", "check_s")),
                    "Invalid trial timing")
            require(not row["verified"] or row["status"] in ("SAT", "UNSAT"), "Invalid certification")
            require(row["accepted"] == (row["verified"] and row["e2e_s"] <= CAP), "Acceptance mismatch")
            require(abs(row["PAR2"] - (row["e2e_s"] if row["accepted"] else 2 * CAP)) < 1e-9,
                    "PAR2 scoring mismatch")
        completed = read(path.with_name("report.json"))
        require(completed == {"shard": index, "protocol_sha256": B.sha(PROTOCOL),
                              "trials": len(batch), "totals": B.summarize(batch, ARMS)}, "Shard completion mismatch")
        rows.extend(batch)
    require(len(rows) == protocol["total_trials"] and len({r["sha256"] for r in rows}) == COUNT,
            "Incomplete final source/trial count")
    require(len({r["measurement_run_id"] for r in rows}) == 1, "Mixed measurement runs")
    verified_statuses = collections.defaultdict(set)
    for row in rows:
        if row["verified"]:
            verified_statuses[row["sha256"]].add(row["status"])
    require(all(len(statuses) == 1 for statuses in verified_statuses.values()),
            "Contradictory verified SAT and UNSAT answers on the same original CNF")
    rows.sort(key=lambda r: (r["source_id"], r["rep"], r["arm"]))
    overall = stats(rows)
    comparisons = {native: {reference: comparison(rows, native, reference) for reference in REFERENCES}
                   for native in ("X5_NO_MIN", "X5")}
    families = {family: stats([r for r in rows if r["family"] == family])
                for family in sorted({s["family"] for s in sources})}
    ranking = sorted(ARMS, key=lambda arm: (overall[arm]["PAR2_s"], -overall[arm]["solved"], arm))
    final = {"status": "COMPLETE", "protocol": protocol, "protocol_sha256": B.sha(PROTOCOL),
             "sources": COUNT, "trials": len(rows), "overall": overall, "ranking": ranking,
             "comparisons": comparisons, "by_family": families, "promotion": False,
             "conclusion_scope": "Retrospective paired comparison only; no baseline or model promotion."}
    out = ROOT / "best100_final"
    save(out / "report.json", final)
    (out / "paired_trials.jsonl").write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows))
    lines = ["# X5 BEST100 — verified original SAT2024 comparison", "",
             "100 original CNFs × 2 repetitions × 5 arms = 1,000 trials. One logical CPU per solver.",
             "5 s includes solver execution and independent answer verification. Unaccepted trials score 10 s.",
             "Primary: X5_NO_MIN. X5 is a secondary control. Retrospective set; no promotion.", "",
             "| Solver | Verified / 200 | SAT | UNSAT | Timeouts | Total PAR2 s | Mean PAR2 s |",
             "|---|---:|---:|---:|---:|---:|---:|"]
    for arm in ranking:
        v = overall[arm]
        lines.append(f"| {arm} | {v['solved']} | {v['SAT']} | {v['UNSAT']} | {v['timeouts']} | {v['PAR2_s']:.4f} | {v['mean_PAR2_s']:.6f} |")
    lines += ["", "## Paired comparisons", "", "Positive PAR2 reduction means the native solver is faster. Intervals resample whole CNFs.", "",
              "| Native | Reference | PAR2 reduction | 95% source interval |", "|---|---|---:|---:|"]
    for native, values in comparisons.items():
        for reference, v in values.items():
            lo, hi = v["source_cluster_95"]
            lines.append(f"| {native} | {reference} | {100*v['reduction']:+.3f}% | [{100*lo:+.3f}%, {100*hi:+.3f}%] |")
    lines += ["", "## Family PAR2 totals (seconds)", "", "| Family | CNFs | " + " | ".join(ARMS) + " |",
              "|---|---:|" + "---:|" * len(ARMS)]
    for family, values in families.items():
        lines.append("| " + family.replace("|", "\\|") + " | " + str(values[ARMS[0]]["trials"] // REPS) + " | "
                     + " | ".join(f"{values[a]['PAR2_s']:.3f}" for a in ARMS) + " |")
    (out / "summary.md").write_text("\n".join(lines) + "\n")
    B.emit("BEST100_FINAL", {k: final[k] for k in ("status", "sources", "trials", "overall", "ranking", "comparisons", "promotion")})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("freeze", "shard", "report"))
    parser.add_argument("--shard", type=int, default=0)
    parser.add_argument("--inputs", type=Path, default=ROOT / "input/x52_original100")
    parser.add_argument("--results", type=Path, default=ROOT / "best100_downloads")
    args = parser.parse_args()
    if args.mode == "freeze": freeze(args.inputs)
    elif args.mode == "shard": shard(args.inputs, args.shard)
    else: report(args.inputs, args.results)


if __name__ == "__main__":
    main()
