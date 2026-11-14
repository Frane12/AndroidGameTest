#!/usr/bin/env python3
"""Build native single-process DRNAS + bounded proof-logged congruence stage.
Derived from SHA-frozen CF6 first-reduction source. Never touches src or main.
"""
from pathlib import Path
import hashlib,json,subprocess,sys
R=Path(__file__).resolve().parents[1]
CF6=R/"build/drnas_clause_cf6.cpp"
SOURCE=R/"build/drnas_pg14_congruence.cpp"
OUT=R/"build/drnas-pg14"
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def replace_once(s,a,b):
    n=s.count(a)
    if n!=1:raise RuntimeError(("PG14_SOURCE_ANCHOR_DRIFT",n,a[:150]))
    return s.replace(a,b)
def build():
    subprocess.run([sys.executable,str(R/"research/drnas_clause_cf6_build.py")],cwd=R,check=True)
    s=CF6.read_text()
    s=replace_once(s,"#include <vector>",
        "#include <vector>\n#include <numeric>\n#include <unordered_map>\n#include <unordered_set>")
    s=replace_once(s,"    enum class Backdoor {",
        '    #include "../research/drnas_pg14_congruence.inc"\n\n    enum class Backdoor {')
    s=replace_once(s,"    bool root_unsat_ = false, probing_ = false;",
        "    bool root_unsat_ = false, probing_ = false;\n    bool pg14_enabled_ = false;")
    s=replace_once(s,
        '''            if (p.result == PropResult::TIMEOUT) return Result::UNKNOWN;
        }
        while (true) {''',
        '''            if (p.result == PropResult::TIMEOUT) return Result::UNKNOWN;
            if(pg14_enabled_) {
                preprocessPG14();
                if(root_unsat_) return Result::UNSAT;
                p=propagate(-1);
                if(p.result==PropResult::CONFLICT)return Result::UNSAT;
                if(p.result==PropResult::TIMEOUT)return Result::UNKNOWN;
            }
        }
        while (true) {''')
    s=replace_once(s,
        "    bool x5_minimize=true, x5_retain=false, x5_gc=true, x5_restarts=false;",
        "    bool x5_minimize=true, x5_retain=false, x5_gc=true, x5_restarts=false;\n    bool pg14=false;")
    s=replace_once(s,
        '        else if (opt=="--x5-no-minimize") x5_minimize=false;',
        '        else if (opt=="--pg-congruence") pg14=true;\n        else if (opt=="--x5-no-minimize") x5_minimize=false;')
    s=replace_once(s,
        "    solver->finishParsing();",
        "    solver->finishParsing();\n    solver->configurePG14(pg14);")
    SOURCE.write_text(s)
    subprocess.run(["g++","-std=c++20","-O3","-DNDEBUG","-Wall","-Wextra",
                    "-Wpedantic","-Werror",str(SOURCE),"-o",str(OUT)],cwd=R,check=True)
    print("PG14_BUILD "+json.dumps({
        "status":"COMPILED","base_source_sha":digest(CF6),
        "pg14_binary_sha":digest(OUT),"single_native_solver":True,
        "model_reconstruction_needed":False,
        "original_CNF_clauses_never_deleted":True,
        "derived_congruence_clauses_proof_logged":True,
        "main_modified":False
    },sort_keys=True),flush=True)
if __name__=="__main__":build()
