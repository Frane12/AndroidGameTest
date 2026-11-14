#!/usr/bin/env python3
"""MATH-GUARD3: derive same-process adaptive proof gate from frozen GUARD2.
No edits to src/, main, or frozen reference binaries.
"""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
BUILD=ROOT/"build"

def one(s,old,new):
    count=s.count(old)
    if count!=1:
        raise RuntimeError(f"GUARD3_SOURCE_DRIFT count={count} anchor={old!r}")
    return s.replace(old,new,1)

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def main():
    subprocess.run([sys.executable,str(ROOT/"research/drnas_mathguard2/build.py")],check=True)
    src=BUILD/"drnas_mathguard2.cpp"
    s=src.read_text()
    s=one(s,
        "        std::set<std::pair<int,int>> done;",
        (HERE/"adaptive.inc").read_text()+
        "        std::set<std::pair<int,int>> done;")
    s=one(s,
        "                    if (!done.insert({c,d}).second) continue;",
        """                    if (math_guard3_enabled_ &&
                        !selected_pairs.count({c,d})) continue;
                    if (!done.insert({c,d}).second) continue;""")
    s=one(s,
        "        if (math_guard2_enabled_) runMathGuard2();",
        "        if (math_guard2_enabled_ || math_guard3_enabled_) runMathGuard2();")
    s=one(s,
        "    bool math_guard2_enabled_=false;",
        "    bool math_guard2_enabled_=false;\n    bool math_guard3_enabled_=false;")
    s=one(s,
        "    int64_t math_guard2_stored=0,math_guard2_proof_only=0;",
        """    int64_t math_guard2_stored=0,math_guard2_proof_only=0;
    int64_t math_guard3_equalities=0,math_guard3_candidate_edges=0;
    int64_t math_guard3_path_len=0;
    bool math_guard3_triggered=false;""")
    s=one(s,
        "    void configureMathGuard2(bool enabled, double budget_ms, bool lean) {",
        """    void configureMathGuard3(bool enabled) { math_guard3_enabled_=enabled; }
    void configureMathGuard2(bool enabled, double budget_ms, bool lean) {""")
    s=one(s,
        "    bool math_guard2=false;",
        "    bool math_guard2=false;\n    bool math_guard3=false;")
    s=one(s,
        '        else if (opt=="--math-guard2") math_guard2=true;',
        '        else if (opt=="--math-guard2") math_guard2=true;\n'
        '        else if (opt=="--math-guard3") math_guard3=true;')
    s=one(s,
        "            solver->configureMathGuard2(math_guard2,math_guard2_budget_ms,math_guard2_lean);",
        "            solver->configureMathGuard2(math_guard2,math_guard2_budget_ms,math_guard2_lean);\n"
        "            solver->configureMathGuard3(math_guard3);")
    s=one(s,
        '        std::cerr<<"MATH_GUARD2_STATS {',
        '''        std::cerr<<"MATH_GUARD3_STATS {\\"enabled\\":"<<(math_guard3?"true":"false")
                 <<",\\"triggered\\":"<<(s.math_guard3_triggered?"true":"false")
                 <<",\\"equalities\\":"<<s.math_guard3_equalities
                 <<",\\"candidate_edges\\":"<<s.math_guard3_candidate_edges
                 <<",\\"selected_path\\":"<<s.math_guard3_path_len
                 <<",\\"lemmas\\":"<<s.math_guard2_lemmas
                 <<",\\"wall_ms\\":"<<std::fixed<<std::setprecision(7)
                 <<s.math_guard2_wall_ms<<"}\\n";
        std::cerr<<"MATH_GUARD2_STATS {''')
    output=BUILD/"drnas_mathguard3.cpp"
    output.write_text(s)
    binary=BUILD/"drnas-mathguard3"
    subprocess.run(["g++","-std=c++20","-O3","-Wall","-Wextra","-Wpedantic",
        "-o",str(binary),str(output)],check=True)
    audit=dict(
        frozen_source_sha256=digest(ROOT/"src/drnas_x59.cpp"),
        guard2_reference_sha256=digest(src),
        guard3_derived_sha256=digest(output),
        guard3_binary_sha256=digest(binary),
        proof_certificate_sha256=digest(ROOT/"research/drnas_mathguard2/diamond_proof.json"),
        one_solver_process=True,one_logical_cpu=True,
        adaptive_activation="only when >=3 chained proven diamond equalities contradict a graph edge",
        skip_without_proof=True, default_guard_enabled=False, original_main_untouched=True)
    (BUILD/"MATH_GUARD3_BUILD.json").write_text(json.dumps(audit,sort_keys=True,indent=2)+"\n")
    print("MATH_GUARD3_BUILD "+json.dumps(audit,sort_keys=True),flush=True)

if __name__=="__main__":
    main()
