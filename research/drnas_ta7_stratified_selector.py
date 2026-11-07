#!/usr/bin/env python3
"""DRNAS TA7 — bounded three-region, source-only SAT strategy selection.

Preregistered research hypotheses, not performance claims:
  guarded: act only on corroborated cross-region structure or clear
           contradiction of a weak early XOR->CMS routing hint.
  explore: allow a broader family of exploratory decisions.
  shadow: pay the same scan cost but keep exactly TA3's host decision.

Original DIMACS files are never modified. A byte-bounded region scanner sees
at most 3 x 160 KiB and 3 x 320 complete clauses; fragments are discarded.
All feature cost is charged within the end-to-end SAT benchmark budget.
"""
from __future__ import annotations

import argparse
import collections
import json
import mmap
import pathlib
import tempfile
import time

import drnas_ta3_adaptive_selector as ta3

MODES = frozenset(("ta7_guarded", "ta7_explore", "ta7_shadow"))
BACKENDS = frozenset(("cms_plain", "cms_r28", "kissat_plain", "kissat_r28"))
WINDOW_BYTES = 160 * 1024
CLAUSE_CAP = 320
LITERAL_CAP = 12000
MIN_MULTI_BYTES = 550000


def region_stats(mm, start):
    """Collect complete CNF clauses from one bounded byte window.

    Starting in the middle of a file: discard a partial line, and then the
    first possibly incomplete clause. Never interpret fragments as XOR proofs.
    """
    size = len(mm)
    if start:
        boundary = mm.find(b"\n", start)
        if boundary < 0:
            return None
        start = boundary + 1
    end = min(size, start + WINDOW_BYTES)
    chunk = mm[start:end]
    if end < size:
        last_newline = chunk.rfind(b"\n")
        chunk = chunk[:last_newline+1] if last_newline >= 0 else b""
    if not chunk:
        return None
    aligned = (start == 0)
    clauses = literals = binary = horn = long = 0
    xor_masks = collections.defaultdict(set)
    current = []

    def accept(lits):
        nonlocal clauses, literals, binary, horn, long
        clauses += 1
        literals += len(lits)
        binary += len(lits) == 2
        horn += sum(1 for v in lits if v > 0) <= 1
        long += len(lits) >= 5
        if len(lits) == 3 and len({abs(v) for v in lits}) == 3:
            ordered = sorted(lits, key=abs)
            key = tuple(abs(v) for v in ordered)
            mask = sum(1 << j for j, v in enumerate(ordered) if v < 0)
            xor_masks[key].add(mask)

    for line in chunk.splitlines():
        stripped = line.strip()
        if not stripped or stripped[:1] in (b"c", b"p", b"%"):
            continue
        for raw in stripped.split():
            if raw[:1] == b"%":
                break
            try:
                lit = int(raw)
            except ValueError:
                raise ValueError("non-integer DIMACS token in region")
            if not aligned:
                if lit == 0:
                    aligned = True
                continue
            if lit == 0:
                if current:
                    accept(current)
                current = []
                if clauses >= CLAUSE_CAP or literals >= LITERAL_CAP:
                    break
            else:
                current.append(lit)
                if len(current) > 100000:
                    raise ValueError("oversized DIMACS clause")
        if clauses >= CLAUSE_CAP or literals >= LITERAL_CAP:
            break
    if clauses == 0:
        return None
    xor3 = sum(
        any(all(mask in masks for mask in range(8)
                if mask.bit_count() % 2 == parity)
            for parity in (0, 1))
        for masks in xor_masks.values()
    )
    return {
        "start_byte": start, "clauses": clauses, "literals": literals,
        "binary": binary, "horn": horn, "long": long,
        "xor3": xor3,
    }


def stratified_features(path):
    """Read 1 or 3 non-overlapping fixed byte windows, never outcomes."""
    began = time.perf_counter()
    path = pathlib.Path(path)
    with path.open("rb") as fd:
        if fd.seek(0, 2) <= 0:
            raise ValueError("empty DIMACS")
        fd.seek(0)
        with mmap.mmap(fd.fileno(), 0, access=mmap.ACCESS_READ) as mm:
            size = len(mm)
            offsets = [0, int(size * .48), int(size * .84)] \
                if size >= MIN_MULTI_BYTES else [0]
            regions = [region_stats(mm, offset) for offset in offsets]
    regions = [r for r in regions if r is not None]
    if not regions:
        raise ValueError("no complete clauses in sampled regions")
    clauses = sum(r["clauses"] for r in regions)
    out = {
        "size_bytes": size,
        "regions": len(regions),
        "sampled_clauses": clauses,
        "head_xor3": regions[0]["xor3"],
        "later_xor3": sum(r["xor3"] for r in regions[1:]),
        "xor3_total": sum(r["xor3"] for r in regions),
        "xor_regions": sum(r["xor3"] > 0 for r in regions),
        "binary_fraction": sum(r["binary"] for r in regions) / clauses,
        "horn_fraction": sum(r["horn"] for r in regions) / clauses,
        "long_fraction": sum(r["long"] for r in regions) / clauses,
        "scan_ms": round((time.perf_counter() - began) * 1000, 3),
        "region_summaries": [
            {"position": i, "clauses": r["clauses"], "xor3": r["xor3"]}
            for i, r in enumerate(regions)
        ],
    }
    return out


def decide(leading, distribution, mode):
    if mode not in MODES:
        raise ValueError("bad TA7 mode")
    legacy, legacy_reason = ta3.decision(leading, "ta2_portfolio")
    if legacy not in BACKENDS:
        raise AssertionError("unknown frozen host")
    if mode == "ta7_shadow":
        return legacy, "TA7_shadow_TA3:" + legacy_reason

    size = int(leading["declared_clauses"])
    n = distribution["regions"]
    xor_total = distribution["xor3_total"]
    middle_late = distribution["later_xor3"]
    xregions = distribution["xor_regions"]
    b = distribution["binary_fraction"]
    h = distribution["horn_fraction"]
    long = distribution["long_fraction"]

    # A small complete XOR3 source is the one previously justified R28 use.
    if legacy == "cms_r28" and size <= 2500:
        return "kissat_r28", "TA7_small_source_XOR_Kissat"

    # In a larger real source, corroboration in distant windows is stronger
    # than relying only on the first 512 clauses. Still bound R28 attempt
    # to an explicitly testable CNF-size region.
    if (n >= 2 and xregions >= 2 and xor_total >= 10
            and size <= 20000 and b < .35 and long < .30):
        return "kissat_r28", "TA7_correlated_stratified_XOR_R28"

    # A suspiciously weak leading parity pattern should not automatically
    # force CMS if the other parts are dominated by Kissat-like structure.
    if (legacy == "cms_plain" and legacy_reason == "source_parity_plus_cnf"
            and n >= 2 and 2 <= int(leading["complete_xor3_templates_sample"]) <= 7
            and middle_late == 0
            and (b >= .60 or h >= .92 or long >= .45)):
        return "kissat_plain", "TA7_uncorroborated_early_parity"

    if mode == "ta7_explore":
        if (n >= 2 and xor_total >= 4 and size <= 60000
                and b < .65 and long < .55):
            return "kissat_r28", "TA7_explore_stratified_XOR"
        if (legacy == "cms_plain" and n >= 2 and
                (b >= .45 or h >= .85 or long >= .32)):
            return "kissat_plain", "TA7_explore_mixed_to_Kissat"

    return legacy, "TA7_fallback_TA3:" + legacy_reason


def select(path, leading, mode):
    features = stratified_features(path)
    selected, reason = decide(leading, features, mode)
    return selected, reason, features


def selftest():
    lead = dict(declared_clauses=30000,
                sample_fraction_clauses=.017,
                complete_xor3_templates_sample=3,
                binary_fraction=.1, horn_clause_fraction=.55,
                long_clause_fraction=.0,
                variable_occurrence_p90_over_median=2)
    dist = dict(regions=3, xor3_total=3, later_xor3=0,
                xor_regions=1, binary_fraction=.80,
                horn_fraction=.60, long_fraction=0.05)
    assert decide(lead, dist, "ta7_guarded")[0] == "kissat_plain"
    assert decide(lead, dist, "ta7_shadow")[0] == "cms_plain"
    assert decide(lead, dist, "ta7_explore")[0] == "kissat_plain"

    dist2 = dict(dist, xor3_total=16, later_xor3=13, xor_regions=3,
                 binary_fraction=.08, long_fraction=.04)
    lead2 = dict(lead, declared_clauses=8000)
    assert decide(lead2, dist2, "ta7_guarded")[0] == "kissat_r28"

    with tempfile.TemporaryDirectory() as tmp:
        p = pathlib.Path(tmp) / "toy.cnf"
        p.write_text("p cnf 6 6\n1 -2 3 0\n-1 2 3 0\n-3 4 0\n5 0\n-5 6 0\n-6 4 0\n")
        f = stratified_features(p)
        assert f["regions"] == 1 and f["sampled_clauses"] == 6
        assert 0 <= f["binary_fraction"] <= 1
        # Exercise three window offsets with byte/line and clause boundaries.
        large = pathlib.Path(tmp) / "zones.cnf"
        with large.open("w") as out:
            out.write("p cnf 8 60000\n")
            out.write("1 -2 3 0\n" * 60000)
        f = stratified_features(large)
        assert f["regions"] == 3, f
        assert 0 < f["sampled_clauses"] <= 3*CLAUSE_CAP
    try:
        decide(lead, dist, "bad")
    except ValueError:
        pass
    else:
        raise AssertionError("invalid TA7 mode accepted")
    print("TA7_SELFTEST_PASS", json.dumps({
        "fixed_regions": [0.0, .48, .84],
        "window_bytes": WINDOW_BYTES, "clause_cap_per_region": CLAUSE_CAP,
        "modes": sorted(MODES), "source_only": True,
        "benchmarks_not_used_as_features": True,
    }, sort_keys=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("selftest",))
    args = parser.parse_args()
    selftest()
