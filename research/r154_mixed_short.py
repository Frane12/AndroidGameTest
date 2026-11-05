#!/usr/bin/env python3
"""R154 MIX short prospective external holdout: unchanged R153 against controls.

Source and content SHA exclusions are frozen BEFORE solver timing.
Only complete original CNFs with both a detectable XOR block and residual
non-XOR CNF clauses qualify.  No performance-based sample selection.
"""
from __future__ import annotations
import argparse
import importlib.util
import json
import pathlib

ROOT = pathlib.Path("r154mix")
PROTO = "DRNAS-R154-MIX-SHORT-NEW-SHA-20261105-v1"
CAP = 6.0
SHARDS = 4
MIN_CASES = 4  # Short prospective pilot: no claims beyond actual frozen sample

def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def source_module():
    m = load("research/r154_unseen_freeze.py", "r154_short_mix_freeze")
    m.ROOT = ROOT
    m.PROTO = PROTO
    # All categories have source overlap with mixed XOR/Boolean CNFs.
    # Keep the original 2025/26 GBD catalog and provenance checks.
    m.FAMILIES = (
        "or_randxor", "random-graph-xorsat", "xor-shifting",
        "minimum-disagreement-parity", "random-circuits", "bitvector",
        "cryptography", "miter", "xor-chain", "linear-equations", "lights-out",
    )
    # Expand actual competition source years, never reuse any prior ID/SHA.
    m.TRACKS = (
        "main_2023", "main_2024", "main_2025", "main_2026",
        "submissions_2024", "submissions_2025", "submissions_2026",
    )
    m.MIN_FREEZE_CASES = MIN_CASES
    m.RAW_CAP = 48 * 1024 * 1024
    m.CNF_CAP = 24 * 1024 * 1024
    m.MAX_VARIABLES = 25000
    m.MAX_CLAUSES = 500000
    m.QUOTA = {
        "xor_plus_units": 0,
        "complete_xor": 0,
        "mixed_residual": 12,
        "nonxor_control": 0,
    }
    m.MAX_SOURCE_FETCH = 350
    return m

def benchmark_module():
    m = load("research/r154_unseen_benchmark.py", "r154_short_mix_benchmark")
    m.ROOT = ROOT
    m.PROTO = PROTO
    m.CAP = CAP
    m.SHARDS = SHARDS
    m.BINARIES = {
        "r28": ROOT / "r28",
        "r153": ROOT / "r153",
        "kissat": pathlib.Path("built/bin/kissat_4_0_4"),
        "cadical": pathlib.Path("built/bin/cadical_3_0_1"),
    }
    return m

def verify_manifest():
    p = ROOT / "frozen" / "manifest.json"
    data = json.loads(p.read_text())
    assert data["protocol"] == PROTO
    assert len(data["cases"]) >= MIN_CASES
    assert data["cohort_counts"] == {"mixed_residual": len(data["cases"])}
    assert all(
        c["cohort"] == "mixed_residual"
        and c["structural"]["original_xor_covered_clauses"] > 0
        and c["structural"]["uncovered_nonunit_clauses"] > 0
        for c in data["cases"]
    ), "not genuine mixed original XOR + non-XOR CNF"
    assert data["historical_exclusions"]["prior_source_sha"] >= 1326
    assert any("prior/r154/" in f for f in data["historical_exclusions"]["files"])
    return data

def main():
    arg = argparse.ArgumentParser()
    arg.add_argument("action", choices=["freeze", "shard", "audit"])
    arg.add_argument("--shard", type=int, default=0)
    args = arg.parse_args()
    ROOT.mkdir(parents=True, exist_ok=True)
    if args.action == "freeze":
        source_module().freeze()
        data = verify_manifest()
        print("R154_MIX_FROZEN", len(data["cases"]), data["cohort_counts"], flush=True)
    elif args.action == "shard":
        verify_manifest()
        benchmark_module().shard(args.shard)
        print("R154_MIX_SHARD_PASS", args.shard, flush=True)
    else:
        data = verify_manifest()
        m = benchmark_module()
        m.audit()
        report = json.loads((ROOT / "report.json").read_text())
        assert report["attempts"] == len(data["cases"]) * 2 * 4
        assert report["cap_s"] == CAP
        assert report["formulas"] == len(data["cases"])
        assert report["status"] == "AUDIT_PASS"
        print("R154_MIX_FINAL", json.dumps({
            "formulas": report["formulas"],
            "attempts": report["attempts"],
            "cap_s": report["cap_s"],
            "cohorts": report["cohorts"],
        }, sort_keys=True), flush=True)

if __name__ == "__main__":
    main()
