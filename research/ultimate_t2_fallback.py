#!/usr/bin/env python3
"""DRNAS Ultimate T2 (causal isolation): source-certified trail-coupled XOR/CDCL.

R153 exact router runs first and only genuine fallback reaches this script.
All clauses of the original CNF remain byte-identical. Optional source XOR
facts are replayed independently BEFORE injection; a cost veto uses t_clean.
"""
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import ultimate_r2_fallback as r2
import ultimate_t2_probe as detector
import r157_source_certified_xor as cert
import r166x_certified_gauss as gauss

ROOT = pathlib.Path("ultimate_t2")
NATIVE = ROOT / "t-native"
EMPTY = ROOT / "empty.tsv"
ALLOWED = {"clean", "shadow", "source", "adaptive", "derived",
           "t2_derived_rows", "t2_derived_units",
           "t2_derived_incremental", "t2_derived_shadow", "td_lazy_source",
           "c1_lazy_cooldown", "c1_lazy_fastwake", "c1_lazy_shadow"}
NATIVE_MODES = {"clean": "t_clean", "shadow": "t_shadow",
                "source": "t_source", "adaptive": "t_adaptive",
                "derived": "gauss_cooldown", "t2_derived_rows": "t2_derived_rows",
                 "t2_derived_units": "t2_derived_units",
                 "t2_derived_incremental": "t2_derived_incremental",
                 "t2_derived_shadow": "t2_derived_shadow",
                 "td_lazy_source": "td_lazy_source",
                 "c1_lazy_cooldown": "c1_lazy_cooldown",
                 "c1_lazy_fastwake": "c1_lazy_fastwake",
                 "c1_lazy_shadow": "c1_lazy_shadow"}

def need(ok, detail):
    if not ok:
        raise RuntimeError("ULTIMATE_T_FAIL_CLOSED " + str(detail))

def sha256(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()

def source_replay(cnf, evidence, rows_tsv):
    """Reconstruct complete parity blocks from original clauses (no reliance on extracted rows alone)."""
    _, clauses = gauss.exact.parse_dimacs(cnf)
    _, groups, units = gauss.source_equations(clauses)
    verified = gauss.check_selected(evidence, groups, units)
    need(len(verified) == evidence["selected_rows"], "independent source replay row count")
    reconstructed = "".join(
        f"{m.bit_count()} {rhs} " +
        " ".join(str(v) for v in gauss.bits(m)) + "\n"
        for m, rhs in verified
    )
    need(pathlib.Path(rows_tsv).read_text() == reconstructed,
         "independent source replay TSV mismatch")
    return len(verified)

def run_native(cnf, original_sha, mode, reason, selected, derived,
               implied, eligible, prep_s, rows, units, deadline, probe=None):
    rem = (deadline - time.monotonic_ns()) / 1e9
    native_mode = NATIVE_MODES[mode] if eligible or mode == "clean" else "t_clean"
    gate = dict(mode=mode, native_expected=native_mode, reason=reason,
                source_sha256=original_sha, selected_rows=selected,
                derived_rows=derived, derived_units=implied,
                eligible=eligible, prep_s=round(prep_s, 6), probe=probe or {})
    print("ULTIMATE_T_GATE " + json.dumps(gate, sort_keys=True), flush=True)
    if rem < 1.0:
        print("ULTIMATE_T_TIMEOUT remaining_deadline", flush=True)
        return 0
    argv = [str(NATIVE.resolve()), native_mode, str(cnf),
            str(rows.resolve()), str(min(rem, 120.0))]
    if native_mode in ("gauss_cooldown", "t2_derived_units",
                       "t2_derived_incremental", "t2_derived_shadow"):
        need(units is not None, "certified units TSV required for Gaussian mode")
        argv.append(str(units.resolve()))
    try:
        # Keep stdout streaming: the wrapper may be externally killed at cap,
        # in which case terminal counters are unavailable but progress remains.
        sys.stdout.flush()
        child = subprocess.run(argv, timeout=rem + 0.5)
    except subprocess.TimeoutExpired:
        print("ULTIMATE_T_TIMEOUT native_watchdog", flush=True)
        return 0
    need(child.returncode in (0, 10, 20), "native solver error " + str(child.returncode))
    return child.returncode

def main():
    need(len(sys.argv) == 2, "usage: original.cnf")
    src = pathlib.Path(sys.argv[1]).resolve()
    need(src.is_file() and NATIVE.is_file(), "missing source/native")
    need(EMPTY.is_file() and EMPTY.stat().st_size == 0, "missing empty control")
    mode = os.environ.get("ULTIMATE_T_MODE", "clean")
    need(mode in ALLOWED, "unknown experiment arm")
    deadline = int(os.environ["ULTIMATE_R2_DEADLINE_NS"])
    digest = sha256(src)
    started = time.monotonic()
    if mode == "clean":
        return run_native(src, digest, mode, "clean", 0, 0, 0, False, 0., EMPTY, None, deadline)
    eligible = False
    selected = derived = implied = 0
    rows, units = EMPTY, None
    reason = "no_source_parity"
    # One total budget including the cheap probe and independent proof replay,
    # not separate unbounded budgets at different processing stages.
    budget = min(1.2, (deadline - time.monotonic_ns()) / 1e9 - 1.5)
    if budget <= 0:
        return run_native(src, digest, mode, "insufficient_time", 0, 0, 0,
                          False, time.monotonic()-started, EMPTY, None, deadline)
    with tempfile.TemporaryDirectory(prefix="ultimate-t-certified-") as tempdir:
        base = pathlib.Path(tempdir)
        try:
            with r2.preparation_budget(budget):
                yes, reason, probe = detector.cheap_probe(src)
                if yes:
                    evidence = cert.extract(src, base/"source.tsv", base/"proof.json", max_rows=64)
                    need(evidence["source_sha256"] == digest, "original CNF SHA changed")
                    selected = evidence["selected_rows"]
                    if selected >= 1 and evidence["usable_residual_linked_equations"] >= 1:
                        need(source_replay(src, evidence, base/"source.tsv") == selected,
                             "source parity proof replay failed")
                        rows = base/"source.tsv"
                        if mode in ("derived", "t2_derived_rows", "t2_derived_units",
                                        "t2_derived_incremental", "t2_derived_shadow"):
                            extra = gauss.prepare(src, evidence, base/"derived", max_derived=48)
                            need(extra["source_sha256"] == digest, "derived source SHA changed")
                            need(gauss.replay(src, evidence, extra["certificate"],
                                              extra["tsv"], extra["units_tsv"]),
                                 "Gaussian source proof replay failed")
                            rows = pathlib.Path(extra["tsv"])
                            units = pathlib.Path(extra["units_tsv"])
                            derived = extra["derived_short_rows"]
                            implied = extra["derived_units"]
                        if (deadline - time.monotonic_ns()) > 1_500_000_000:
                            eligible = True
                            reason = "source_replayed_trail_frontier"
                        else:
                            reason = "remaining_time_veto"
                    else:
                        reason = "insufficient_residual_linked_XOR"
        except r2.PreparationBudgetExceeded:
            eligible = False
            rows, units = EMPTY, None
            derived = implied = 0
            reason = "certification_budget_preempted"
        prep_s = time.monotonic()-started
        return run_native(src, digest, mode, reason, selected, derived, implied,
                          eligible, prep_s, rows, units, deadline, locals().get("probe", {}))

if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print("ULTIMATE_T_FATAL " + str(exc), file=sys.stderr, flush=True)
        sys.exit(78)
