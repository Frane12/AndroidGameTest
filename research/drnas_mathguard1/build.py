#!/usr/bin/env python3
"""Build a proof-first, single-thread mathematical guard into frozen native X59.

The canonical src/drnas_x59.cpp is never overwritten. Baseline and guard are
compiled from the same frozen source, and guard is disabled by default.
"""
from pathlib import Path
import hashlib
import json
import subprocess

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
BUILD = ROOT / "build"
FROZEN = ROOT / "src/drnas_x59.cpp"


def substitute_once(source, old, new):
    found = source.count(old)
    if found != 1:
        raise RuntimeError(f"MATHGUARD_SOURCE_DRIFT count={found} anchor={old[:90]!r}")
    return source.replace(old, new, 1)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    BUILD.mkdir(exist_ok=True)
    source = FROZEN.read_text()
    source = substitute_once(source, "#include <algorithm>\n",
                             "#include <algorithm>\n#include <array>\n#include <map>\n#include <set>\n")
    source = substitute_once(source,
        "    void configureX59(bool enabled) { x59_stamp_glue_=enabled; }",
        """    void configureX59(bool enabled) { x59_stamp_glue_=enabled; }
    void configureMathGuard(bool enabled, double budget_ms) {
        if (!(budget_ms > 0.0 && budget_ms <= 20.0 && std::isfinite(budget_ms)))
            throw std::runtime_error("invalid math guard budget");
        math_guard_enabled_ = enabled;
        math_guard_ms_ = budget_ms;
    }""")
    source = substitute_once(source,
        "    bool x59_stamp_glue_=false;",
        """    bool x59_stamp_glue_=false;
    bool math_guard_enabled_=false;
    double math_guard_ms_=4.0;""")
    source = substitute_once(source,
        "    int64_t x59_stamp_glue_calls=0, x59_stamp_seen_levels=0;",
        """    int64_t x59_stamp_glue_calls=0, x59_stamp_seen_levels=0;
    int64_t math_guard_scanned=0, math_guard_pairs=0, math_guard_lemmas=0;
    int64_t math_guard_units=0, math_guard_duplicate=0;
    bool math_guard_budget_hit=false;
    double math_guard_wall_ms=0.0;""")
    source = substitute_once(source, "    Result solve() {",
                             (HERE / "guard.inc").read_text() + "\n    Result solve() {")
    source = substitute_once(source,
        """        if (root_unsat_) return Result::UNSAT;
        Prop p;""",
        """        if (root_unsat_) return Result::UNSAT;
        if (math_guard_enabled_) runMathGuard();
        if (root_unsat_) return Result::UNSAT;
        Prop p;""")
    source = substitute_once(source,
        "    bool x59_stamp_glue=false;",
        "    bool x59_stamp_glue=false;\n    bool math_guard=false;\n    double math_guard_budget_ms=4.0;")
    source = substitute_once(source,
        '        else if (opt=="--x59-stamp-glue") x59_stamp_glue=true;',
        """        else if (opt=="--x59-stamp-glue") x59_stamp_glue=true;
        else if (opt=="--math-guard") math_guard=true;
        else if (opt=="--math-guard-budget-ms" && i+1<argc)
            math_guard_budget_ms=std::stod(argv[++i]);""")
    source = substitute_once(source,
        '            solver->configureX59(x59_stamp_glue);',
        '            solver->configureX59(x59_stamp_glue);\n'
        '            solver->configureMathGuard(math_guard,math_guard_budget_ms);')
    source = substitute_once(source,
        '        std::cerr<<"X58_STATS {',
        '''        std::cerr<<"MATH_GUARD_STATS {\\"enabled\\":"<<(math_guard?"true":"false")
                 <<",\\"budget_ms\\":"<<math_guard_budget_ms
                 <<",\\"scanned\\":"<<s.math_guard_scanned
                 <<",\\"pairs\\":"<<s.math_guard_pairs
                 <<",\\"lemmas\\":"<<s.math_guard_lemmas
                 <<",\\"units\\":"<<s.math_guard_units
                 <<",\\"duplicates\\":"<<s.math_guard_duplicate
                 <<",\\"budget_hit\\":"<<(s.math_guard_budget_hit?"true":"false")
                 <<",\\"wall_ms\\":"<<std::fixed<<std::setprecision(7)
                 <<s.math_guard_wall_ms<<"}\\n";
        std::cerr<<"X58_STATS {''')
    # Note: generated sources and compiled binaries live only under build/.
    output = BUILD / "drnas_mathguard1.cpp"
    output.write_text(source)
    cxx = ["g++", "-std=c++20", "-O3", "-Wall", "-Wextra", "-Wpedantic", "-o"]
    subprocess.run(cxx + [str(BUILD / "drnas-x59-frozen"), str(FROZEN)], check=True)
    subprocess.run(cxx + [str(BUILD / "drnas-mathguard1"), str(output)], check=True)
    report = {
        "frozen_source_sha256": digest(FROZEN),
        "derived_source_sha256": digest(output),
        "binary_frozen_sha256": digest(BUILD / "drnas-x59-frozen"),
        "binary_guard_sha256": digest(BUILD / "drnas-mathguard1"),
        "single_thread": True, "one_process": True,
        "default_guard_enabled": False,
        "proof_origin": "original CNF binary/ternary clause resolution",
    }
    path = BUILD / "MATH_GUARD1_BUILD.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print("MATH_GUARD1_BUILD " + json.dumps(report, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
