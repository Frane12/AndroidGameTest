#!/usr/bin/env python3
"""Build proof-checked 3-colour diamond GUARD inside the frozen X59 CDCL.

Only derived sources under build/ change; src/ and main remain untouched.
"""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
BASE=ROOT/"research/drnas_mathguard1/build.py"
SRC=ROOT/"build/drnas_mathguard1.cpp"
BUILD=ROOT/"build"
CERT=HERE/"diamond_proof.json"

def one(s,old,new):
    count=s.count(old)
    if count!=1:raise RuntimeError(f"MATH_GUARD2_SOURCE_DRIFT count={count} anchor={old!r}")
    return s.replace(old,new,1)

def canon(row):
    return tuple(sorted(set(row)))

def oracle_rup(clauses,clause):
    values={}
    for lit in clause:
        k=abs(lit);val=lit>0
        if k in values and values[k]!=val:return True
        values[k]=val
    for _ in range(200):
        changed=False
        for c in clauses:
            if any(abs(l) in values and values[abs(l)]==(l>0) for l in c):continue
            free=[l for l in c if abs(l) not in values]
            if not free:return True
            if len(free)==1:
                lit=free[0];k=abs(lit);val=lit>0
                if k in values and values[k]!=val:return True
                if k not in values:values[k]=val;changed=True
        if not changed:return False
    raise RuntimeError("RUP propagation unexpectedly exceeded bound")

def check_cert(obj):
    orig=[]
    for v in range(4):
        bits=[3*v+c+1 for c in range(3)]
        orig.append(canon(bits))
        for i in range(3):
            for j in range(i+1,3):orig.append(canon((-bits[i],-bits[j])))
    for a,b in obj["edges"]:
        for color in range(3):orig.append(canon((-(3*a+color+1),-(3*b+color+1))))
    known=set(orig)
    for i,step in enumerate(obj["steps"]):
        clause,a,b=map(canon,(step["r"],step["a"],step["b"]))
        if a not in known or b not in known:raise RuntimeError(("MISSING_PROOF_PARENT",i))
        pivots=[lit for lit in a if -lit in b]
        if len(pivots)!=1:raise RuntimeError(("INVALID_PIVOT",i,a,b))
        lit=pivots[0]
        resolvent=canon((set(a)|set(b))-{lit,-lit})
        if resolvent!=clause or any(-x in clause for x in clause):
            raise RuntimeError(("BAD_RESOLUTION",i,clause,resolvent))
        if not oracle_rup(known,[-lit for lit in clause]):
            raise RuntimeError(("NON_RUP",i,clause))
        known.add(clause)
    targets={canon((-(7+k),-(10+j))) for k in range(3) for j in range(3) if k!=j}
    if not targets.issubset(known):raise RuntimeError("MISSING_CROSS_COLOUR_TARGET")
    return len(obj["steps"]),len(targets)

def main():
    cert=json.loads(CERT.read_text())
    steps,targets=check_cert(cert)
    print("MATH_GUARD2_CERTIFICATE_PASS",steps,targets,flush=True)
    subprocess.run([sys.executable,str(BASE)],check=True)
    s=SRC.read_text()
    proof_code=",\n            ".join("{"+",".join(map(str,row["r"]))+"}" for row in cert["steps"])
    guard=(HERE/"guard2.inc").read_text().replace(
        "            // MATH_GUARD2_CERTIFICATE_STEPS",
        "            "+proof_code)
    s=one(s,"    Result solve() {",guard+"\n    Result solve() {")
    s=one(s,"    bool math_guard_enabled_=false;",
          "    bool math_guard_enabled_=false;\n"
          "    bool math_guard2_enabled_=false;\n"
          "    bool math_guard2_lean_=false;\n"
          "    double math_guard2_budget_ms_=8.0;")
    s=one(s,"    bool math_guard_budget_hit=false;",
          "    bool math_guard_budget_hit=false;\n"
          "    int64_t math_guard2_scanned=0,math_guard2_diamonds=0;\n"
          "    int64_t math_guard2_lemmas=0,math_guard2_binary=0;\n"
          "    int64_t math_guard2_stored=0,math_guard2_proof_only=0;\n"
          "    bool math_guard2_budget_hit=false;\n"
          "    double math_guard2_wall_ms=0.0;")
    s=one(s,"    void configureMathGuard(bool enabled, double budget_ms) {",
          """    void configureMathGuard2(bool enabled, double budget_ms, bool lean) {\n        math_guard2_lean_=lean;
        if (!(budget_ms>0.0 && budget_ms<=50.0 && std::isfinite(budget_ms)))
            throw std::runtime_error("invalid guard2 budget");
        math_guard2_enabled_=enabled;
        math_guard2_budget_ms_=budget_ms;
    }
    void configureMathGuard(bool enabled, double budget_ms) {""")
    s=one(s,"        if (math_guard_enabled_) runMathGuard();",
          "        if (math_guard_enabled_) runMathGuard();\n"
          "        if (math_guard2_enabled_) runMathGuard2();")
    s=one(s,"    bool math_guard=false;",
          "    bool math_guard=false;\n"
          "    bool math_guard2=false;\n"
          "    bool math_guard2_lean=false;\n"
          "    double math_guard2_budget_ms=8.0;")
    s=one(s,'        else if (opt=="--math-guard") math_guard=true;',
          '        else if (opt=="--math-guard") math_guard=true;\n'
          '        else if (opt=="--math-guard2") math_guard2=true;\n'
          '        else if (opt=="--math-guard2-lean") { math_guard2=true; math_guard2_lean=true; }\n'
          '        else if (opt=="--math-guard2-budget-ms" && i+1<argc)\n'
          '            math_guard2_budget_ms=std::stod(argv[++i]);')
    s=one(s,
          "            solver->configureMathGuard(math_guard,math_guard_budget_ms);",
          "            solver->configureMathGuard(math_guard,math_guard_budget_ms);\n"
          "            solver->configureMathGuard2(math_guard2,math_guard2_budget_ms,math_guard2_lean);")
    s=one(s,'        std::cerr<<"MATH_GUARD_STATS {',
          '''        std::cerr<<"MATH_GUARD2_STATS {\\"enabled\\":"<<(math_guard2?"true":"false")
                 <<",\\"diamonds\\":"<<s.math_guard2_diamonds
                 <<",\\"lemmas\\":"<<s.math_guard2_lemmas
                 <<",\\"binary\\":"<<s.math_guard2_binary
                 <<",\\"scanned\\":"<<s.math_guard2_scanned
                 <<",\\"budget_hit\\":"<<(s.math_guard2_budget_hit?"true":"false")
                 <<",\\"wall_ms\\":"<<std::fixed<<std::setprecision(7)
                 <<s.math_guard2_wall_ms<<"}\\n";
        std::cerr<<"MATH_GUARD_STATS {''')
    output=BUILD/"drnas_mathguard2.cpp"
    output.write_text(s)
    binary=BUILD/"drnas-mathguard2"
    subprocess.run(["g++","-std=c++20","-O3","-Wall","-Wextra","-Wpedantic",
                    "-o",str(binary),str(output)],check=True)
    def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
    obj=dict(frozen=digest(ROOT/"src/drnas_x59.cpp"),source=digest(output),
             binary=digest(binary),certificate=digest(CERT),
             one_process=True,one_logical_cpu=True,guard2_default_off=True,
             certificate_steps=steps,target_binary_clauses=targets)
    (BUILD/"MATH_GUARD2_BUILD.json").write_text(json.dumps(obj,sort_keys=True,indent=2)+"\n")
    print("MATH_GUARD2_BUILD "+json.dumps(obj,sort_keys=True),flush=True)

if __name__=="__main__":main()
