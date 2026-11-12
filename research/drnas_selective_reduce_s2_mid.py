#!/usr/bin/env python3
"""DRNAS S2: bounded mixed-CNF 2SAT/GF(2) witness gate and medium-size paired screen.

Reuses LTM12 DYNAMIC and LTM13 HARD600 prepared generators. Separates groups
by actual DIMACS variable counts. Proof-first means FULL SAT witness is checked
on original CNF, never a partial reduction asserted as SAT. Otherwise serial
CaDiCaL fallback. Not a certified UNSAT reducer or globally blind holdout.
"""
import collections
import hashlib
import itertools
import json
import os
from pathlib import Path
import random
import statistics
import sys
import tempfile
import time

import drnas_ltm12_dynamic as D
import drnas_selective_reduce_s1 as S1
import drnas_ltm13_hard600 as H

B, L = D.B, D.L
ROOT = Path("drnas_selective_reduce_s2_mid")
ARMS = ("S2", "S1", "CaDiCaL", "Kissat", "CryptoMiniSat")
REFERENCES = ("CaDiCaL", "Kissat", "CryptoMiniSat")
CAP_SYNTH = 1.5
CAP_OFFICIAL = 5.0
MAX_SCAN_BYTES = 768 * 1024
MAX_VARS = 3000
MAX_CLAUSES = 45000
SNAPSHOT_CLAUSES = 192
MAX_GATE_SECONDS = 0.15
SEEDS = (17,)

def emit(label, value):
    print(label + " " + json.dumps(value, sort_keys=True, separators=(",", ":")), flush=True)

def read_hint(path):
    """Early structural hint, strictly bounded and independent of source label."""
    if path.stat().st_size > MAX_SCAN_BYTES:
        return None
    n = clauses_expected = None
    completed = 0
    width = 0
    histogram = collections.Counter()
    with path.open(encoding="ascii", errors="replace") as fd:
        for raw in fd:
            line = raw.strip()
            if not line or line.startswith(("c", "%")):
                continue
            if line.startswith("p "):
                parts = line.split()
                if len(parts) != 4 or parts[1] != "cnf" or n is not None:
                    return None
                n, clauses_expected = int(parts[2]), int(parts[3])
                if not (1 <= n <= MAX_VARS and 1 <= clauses_expected <= MAX_CLAUSES):
                    return None
                continue
            if n is None:
                return None
            for token in line.split():
                lit = int(token)
                if lit == 0:
                    completed += 1
                    histogram[min(width, 4)] += 1
                    width = 0
                else:
                    if abs(lit) > n:
                        return None
                    width += 1
                if completed >= SNAPSHOT_CLAUSES:
                    break
            if completed >= SNAPSHOT_CLAUSES:
                break
    if completed < 8:
        return None
    # Mixed CNFs can contain useful binary or exact parity substructures.
    if histogram[1] + histogram[2] >= max(8, completed // 6):
        return "binary_subsystem"
    if histogram[3] >= max(8, completed // 5):
        return "xor3_subsystem"
    return None

def full_witness(path, values):
    model = "v " + " ".join(
        str(i if bool(val) else -i) for i, val in enumerate(values, 1)) + " 0\n"
    return B.sat_witness_valid(path, len(values), model)

def mathematical_probe(path, hint, deadline):
    """Produce full witness or abstain; all statements checked against ORIGINAL."""
    if hint is None or time.monotonic() > deadline:
        return None, dict(binary_clauses=0, xor_rows=0, tested=0)
    parsed = D.parse_dimacs(path)
    n, clauses = parsed["n"], parsed["clauses"]
    if n <= 0 or n > MAX_VARS or len(clauses) > MAX_CLAUSES:
        return None, dict(binary_clauses=0, xor_rows=0, tested=0)

    info = dict(binary_clauses=0, xor_rows=0, tested=0)
    binaries = [c for c in clauses if 1 <= len(c) <= 2]
    info["binary_clauses"] = len(binaries)
    if len(binaries) >= 8 and time.monotonic() <= deadline:
        model = D.implication_model(n, binaries)
        if model is not None:
            info["tested"] += 1
            if full_witness(path, model):
                return "mixed_2sat_witness", info

    if time.monotonic() > deadline:
        return None, info
    masks = {}
    for clause in clauses:
        if len(clause) != 3:
            continue
        ordered = tuple(sorted(clause, key=abs))
        key = tuple(abs(v) for v in ordered)
        if len(set(key)) != 3:
            continue
        mask = sum((1 << i) for i, lit in enumerate(ordered) if lit < 0)
        masks[key] = masks.get(key, 0) | (1 << mask)
    # A GF(2) row is used ONLY if its four forbidden assignments are present.
    equations = [(key, mask) for key, mask in masks.items() if mask in (0x69, 0x96)]
    info["xor_rows"] = len(equations)
    if len(equations) >= 4 and time.monotonic() <= deadline:
        filtered = []
        for key, mask in equations[:300]:
            for pattern in range(8):
                if mask & (1 << pattern):
                    filtered.append(tuple(-v if (pattern >> i) & 1 else v
                                          for i, v in enumerate(key)))
        model = D.parity_model(n, filtered)
        if model is not None:
            info["tested"] += 1
            if full_witness(path, model):
                return "mixed_gf2_witness", info
    return None, info

def final(row, arm, source, seed, cap, start, **fields):
    e2e = time.monotonic() - start
    if row.get("status") in ("ERROR", "INVALID_SAT"):
        raise RuntimeError(f"{arm} invalid SAT status id={source['id']}")
    if e2e > cap:
        row.update(status="UNKNOWN", verified=False, php_math_certified=False)
    row.update(id=source["id"], split=source["split"], arm=arm, seed=seed,
               original_cnf_sha256=source["sha256"], cap_s=cap,
               e2e_s=round(e2e, 6), **fields)
    row = B.with_metrics(row, cap)
    if source.get("known_sat") and row["status"].startswith("UNSAT"):
        raise RuntimeError(f"UNSAT contradicts known SAT source {source['id']}")
    return row

def run_s2(source, seed, cap):
    start = time.monotonic()
    path = Path(source["path"])
    if hashlib.sha256(path.read_bytes()).hexdigest() != source["sha256"]:
        raise RuntimeError("original CNF hash mismatch")
    hint = read_hint(path)
    attempted = False
    gate_start = time.monotonic()
    operator, info = (None, dict(binary_clauses=0, xor_rows=0, tested=0))
    if hint and time.monotonic() - start < min(cap / 8, 0.14):
        attempted = True
        operator, info = mathematical_probe(path, hint, min(start + cap * .20,
                                                           gate_start + MAX_GATE_SECONDS))
    gate_s = time.monotonic() - gate_start
    if operator:
        row = dict(status="SAT_VERIFIED", verified=True, php_math_certified=False,
                   decisions=0, conflicts=0)
    else:
        remaining = cap - (time.monotonic() - start) - .12
        if remaining <= .25:
            row = dict(status="UNKNOWN", verified=False, php_math_certified=False,
                       decisions=None, conflicts=None)
        else:
            row = B.run_solver("CaDiCaL", source, seed, remaining)
    return final(row, "S2", source, seed, cap, start,
                 hint=hint, attempted=attempted, operator=operator,
                 fallback=operator is None, gate_s=round(gate_s, 7), **info)

def trial(arm, source, seed, cap):
    if arm == "S2":
        return run_s2(source, seed, cap)
    if arm == "S1":
        row = S1.selective(source, seed, cap)
        row["arm"] = "S1"
        return row
    start = time.monotonic()
    row = B.run_solver(arm, source, seed, max(.3, cap - .12))
    return final(row, arm, source, seed, cap, start)

def build_synthetic(root, seed):
    root.mkdir(parents=True, exist_ok=False)
    cases = root / "cases"
    cases.mkdir()
    sources = []
    families = ("implications", "parity", "exactly_one", "planted_sat")
    for tier in (1, 2):
        for group in families:
            variant = D.VARIANTS[group][2]  # prepared withheld generator variant
            for rep in range(2):
                k = seed + tier * 200000 + families.index(group) * 1000 + rep
                raw, witness = D.formula(group, variant, tier, k)
                sources.append((raw, witness, group, f"tier{tier}"))
    hard_pairs = (("binary", "hard_binary"), ("xor3", "hard_xor3"),
                  ("mixed", "hard_mixed"), ("three_dense", "hard_dense"))
    for idx, (gen_family, label) in enumerate(hard_pairs):
        raw, witness = H.generate_hard(gen_family, seed + 600000 + idx)
        sources.append((raw, witness, label, "tier3"))
    results = []
    for i, (raw, witness, group, tier) in enumerate(sources):
        raw_bytes = raw.encode("ascii")
        sha = hashlib.sha256(raw_bytes).hexdigest()
        path = cases / f"{i:03d}_{sha[:16]}.cnf"
        path.write_bytes(raw_bytes)
        n = B.nvars(path)
        assert B.sat_witness_valid(path, n, witness), (i, group, tier)
        results.append(dict(id=i, path=str(path), sha256=sha,
                            split="holdout", known_sat=True,
                            family=group, tier=tier, nvars=n))
    assert len(results) == 20 and len(set(x["sha256"] for x in results)) == 20
    (root / "manifest.json").write_text(json.dumps(dict(
        original_generator_modules=["drnas_ltm12_dynamic", "drnas_ltm13_hard600"],
        synthetic=True, blind=False, seed=seed, samples=results,
        sampling="two reused DYNAMIC tier1/tier2 per group; four reused HARD600 tier3",
        policies_frozen_before_generation=True), indent=2) + "\n")
    return results

def report(rows, cap, arms):
    metrics = B.metrics(rows, cap, arms)
    ref = min(REFERENCES, key=lambda arm: metrics[arm]["PAR2_verified_s"])
    old = metrics["S1"]["PAR2_verified_s"]
    new = metrics["S2"]["PAR2_verified_s"]
    base = metrics[ref]["PAR2_verified_s"]
    s2 = [r for r in rows if r["arm"] == "S2"]
    pair = {(r["id"], r["seed"], r["arm"]): r for r in rows}
    regressions = sum(
        r["PAR2_verified_s"] > 1.1 * pair[(r["id"], r["seed"], ref)]["PAR2_verified_s"] + .002
        for r in s2)
    return dict(best_reference=ref, totals=metrics,
                speedup_vs_reference_x=round(base/max(new, 1e-9), 5),
                PAR2_reduction_vs_reference_pct=round(100*(1-new/max(base,1e-9)), 3),
                speedup_vs_S1_x=round(old/max(new, 1e-9), 5),
                regressions_over_10pct=regressions,
                shortcut_count=sum(bool(r["operator"]) for r in s2),
                fallback_count=sum(r["fallback"] for r in s2),
                mean_gate_ms=round(1000*statistics.mean(r["gate_s"] for r in s2),3),
                max_gate_ms=round(1000*max(r["gate_s"] for r in s2),3),
                grouping="original CNF variables (not file size)",
                exploratory_only=True)

def run_synthetic(root, seed):
    sources = build_synthetic(root, seed)
    rows = []
    with (root/"trials.jsonl").open("w") as log:
        for i, source in enumerate(sources):
            order = list(ARMS)
            order = order[i % len(order):]+order[:i % len(order)]
            for arm in order:
                r = trial(arm, source, SEEDS[0], CAP_SYNTH)
                r.update(tier=source["tier"], group=source["family"],
                         nvars=source["nvars"])
                rows.append(r)
                log.write(json.dumps(r, sort_keys=True)+"\n")
                log.flush()
            emit("S2_MID_PROGRESS", dict(completed=i+1, total=len(sources),
                                        group=source["family"], nvars=source["nvars"]))
    B.check_contradictions(rows)
    result = report(rows, CAP_SYNTH, ARMS)
    result.update(dataset="reused synthetic SAT generators", source_count=len(sources),
                  one_logical_cpu=True, seeds=list(SEEDS),
                  bands={tier:report([r for r in rows if r["tier"]==tier],CAP_SYNTH,ARMS)
                         for tier in ("tier1","tier2","tier3")},
                  groups={group:report([r for r in rows if r["group"]==group],CAP_SYNTH,ARMS)
                          for group in sorted({r["group"] for r in rows})})
    (root/"report.json").write_text(json.dumps(result, indent=2, sort_keys=True)+"\n")
    emit("S2_MID_SYNTH_FINAL",result)
    return result

def run_official(root):
    root.mkdir(parents=True, exist_ok=False)
    B.ROOT = root
    sources = B.collect()  # existing official SAT2024 range-reader / manifest
    eligible = []
    for source in sources:
        n = B.nvars(source["path"])
        if 80 <= n <= MAX_VARS and source["bytes"] <= 700000:
            eligible.append(dict(source, nvars=n))
    bands = ((80, 300), (301, 1000), (1001, MAX_VARS))
    chosen = []
    for a,b in bands:
        options = sorted((s for s in eligible if a<=s["nvars"]<=b),
                         key=lambda s:(s["bytes"],s["sha256"]))
        chosen += options[:2]
    if len(chosen)<6:
        chosen += [s for s in sorted(eligible,key=lambda s:(s["bytes"],s["sha256"]))
                   if s["sha256"] not in {x["sha256"] for x in chosen}][:6-len(chosen)]
    chosen = chosen[:6]
    if len(chosen)<4:
        raise RuntimeError("insufficient medium official CNFs for S2 screen")
    (root/"selection.json").write_text(json.dumps(dict(
        sources=[dict(id=s["id"],sha256=s["sha256"],nvars=s["nvars"],
                      bytes=s["bytes"]) for s in chosen],
        source_selection="original 100 SAT2024 pool: up to two CNFs per variable bucket, no outcome filtering",
        official=True, previously_seen_archive=True, NOT_BLIND=True), indent=2)+"\n")
    rows=[]
    with (root/"trials.jsonl").open("w") as log:
        for source in chosen:
            for arm in ARMS:
                r=trial(arm,source,17,CAP_OFFICIAL)
                r.update(nvars=source["nvars"],tier="official",group="official")
                rows.append(r);log.write(json.dumps(r,sort_keys=True)+"\n");log.flush()
                emit("S2_MID_OFFICIAL_TRIAL",
                     dict(id=source["id"],nvars=source["nvars"],arm=arm,
                          status=r["status"],PAR2_verified_s=r["PAR2_verified_s"],
                          operator=r.get("operator")))
    B.check_contradictions(rows)
    result=report(rows,CAP_OFFICIAL,ARMS)
    result.update(dataset="official original SAT Competition 2024 CNF",
                  source_count=len(chosen),one_logical_cpu=True,repetitions=1,
                  NOT_BLIND=True,selection=[s["sha256"] for s in chosen])
    (root/"report.json").write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    emit("S2_MID_OFFICIAL_FINAL",result)
    return result

def selftest():
    with tempfile.TemporaryDirectory() as td:
        root=Path(td)
        p=root/"test.cnf"
        p.write_text("p cnf 3 9\n1 0\n2 0\n3 0\n1 2 0\n1 3 0\n2 3 0\n1 -2 0\n2 -3 0\n1 0\n")
        assert read_hint(p) == "binary_subsystem"
        operator, detail = mathematical_probe(p, "binary_subsystem",time.monotonic()+1)
        assert operator == "mixed_2sat_witness",(operator,detail)
        p.write_text("p cnf 3 8\n1 0\n-1 0\n2 0\n-2 0\n1 2 0\n-1 2 0\n1 -2 0\n-1 -2 0\n")
        operator, detail = mathematical_probe(p, "binary_subsystem",time.monotonic()+1)
        assert operator is None  # contradictory binary subsystem
        p.write_text("p cnf 3 4\n1 2 3 0\n1 -2 -3 0\n-1 2 -3 0\n-1 -2 3 0\n")
        assert D.shortcut(p) == "gf2_elimination"
        # A partial subsystem does not prove a mixed-CNF model: independent
        # verification on ALL original clauses is mandatory.
        p.write_text("p cnf 3 9\n1 0\n2 0\n3 0\n1 2 0\n1 3 0\n2 3 0\n1 -2 0\n2 -3 0\n1 0\n")
        assert not full_witness(p,[True,False,True])
        source=dict(id=1,split="holdout",path=str(p),
                    sha256=hashlib.sha256(p.read_bytes()).hexdigest(),known_sat=True)
        assert run_s2(source,17,.9)["status"] == "SAT_VERIFIED"
    emit("S2_SELFTEST_PASS", dict(mixed_binary=True, contradiction_rejected=True,
                                xor_parity=True, original_witness_checked=True))

def main():
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument("--selftest",action="store_true")
    parser.add_argument("--seed",type=int,default=220261112)
    parser.add_argument("--skip-official",action="store_true")
    args=parser.parse_args()
    if args.selftest:
        selftest();return
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    L.setup_source()
    ROOT.mkdir(exist_ok=False)
    results={"synthetic":run_synthetic(ROOT/"synthetic",args.seed)}
    if not args.skip_official:
        results["official"]=run_official(ROOT/"official")
    emit("S2_MID_DONE", dict(
        completed=list(results),
        reductions_pct={k:v["PAR2_reduction_vs_reference_pct"] for k,v in results.items()},
        shortcuts={k:v["shortcut_count"] for k,v in results.items()},
        official_blind=False,
        note="Short exploratory screen, no broad superiority claim"))
    (ROOT/"combined.json").write_text(json.dumps(
        {k:dict(reference=v["best_reference"],solvers=v["totals"],
                improvement_pct=v["PAR2_reduction_vs_reference_pct"],
                shortcuts=v["shortcut_count"]) for k,v in results.items()},
        indent=2,sort_keys=True)+"\n")

if __name__=="__main__":
    main()
