#!/usr/bin/env python3
"""Build exactly one native X59+MATH5 CDCL process with a bounded CNF structure gate.

Freeze/preserve original X59 and MATH5 implementation; add ONLY an eligibility
gate in front of existing original-source MATH5 proof attempt. No portfolio.
The generated source and native executable are preserved for reproducibility.
"""
from pathlib import Path
import hashlib
import os
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/"build"/"structure_gate1"
OUT.mkdir(parents=True,exist_ok=True)

# Build the existing, experimentally validated X59+MATH5 baseline unmodified.
# Its legacy builder verifies pinned mathematical source hashes.
subprocess.run([sys.executable,str(ROOT/"research/xor_math5_unified1/build.py")],
               cwd=ROOT,check=True)
base=ROOT/"build/xor_math5_unified1/drnas_x59_math5.cpp"
source=base.read_text()

def patch(old,new):
    global source
    n=source.count(old)
    if n!=1:raise RuntimeError(f"Expected one anchor, got {n}: {old[:90]}")
    source=source.replace(old,new,1)

patch('#include "math5_unit_only.hpp"',
      '#include "math5_unit_only.hpp"\n#include "drnas_structure_gate.hpp"')
patch('    void configureMath5(double budget_ms, std::string raw_sha, std::string certificate) {',
r'''    void configureStructureGate(double budget_ms) {
        structure_gate_ms_=budget_ms;
    }
    const drnas_structure_gate::Decision& structureGateDecision() const {
        return structure_gate_result_;
    }
    void configureMath5(double budget_ms, std::string raw_sha, std::string certificate) {''')
patch('        if (math5_ms_>0 && !x46_clone_ && !timedOut() &&',
r'''        // STRUCTURE-GATE: original CNF source scan only. The result is an
        // optimization hint, never SAT/UNSAT proof. A NO or timeout falls
        // through to the unchanged CDCL branch; a YES permits existing MATH5.
        if (structure_gate_ms_>0 && math5_ms_>0 && !x46_clone_ && !timedOut()) {
            structure_gate_result_=drnas_structure_gate::inspect(
                clauses_,n_,original_count_,structure_gate_ms_);
            if(!structure_gate_result_.use_math5)math5_ms_=0.0;
        }
        if (math5_ms_>0 && !x46_clone_ && !timedOut() &&''')
patch('    double math5_ms_=0.0, math5_elapsed_s_=0.0;',
r'''    double math5_ms_=0.0, math5_elapsed_s_=0.0;
    double structure_gate_ms_=0.0;
    drnas_structure_gate::Decision structure_gate_result_{};''')
patch('    double sat_construct_ms=0.0, math5_ms=0.0;',
      '    double sat_construct_ms=0.0, math5_ms=0.0, structure_gate_ms=0.0;')
patch('        else if (opt=="--math5-ms" && i+1<argc) math5_ms=std::stod(argv[++i]);',
r'''        else if (opt=="--math5-ms" && i+1<argc) math5_ms=std::stod(argv[++i]);
        else if (opt=="--structure-gate-ms" && i+1<argc)
            structure_gate_ms=std::stod(argv[++i]);''')
patch('    if (!std::isfinite(math5_ms)||math5_ms<0||math5_ms>1000)',
r'''    if (!std::isfinite(structure_gate_ms) || structure_gate_ms<0 ||
        structure_gate_ms>100 || (structure_gate_ms>0 && math5_ms<=0))
        throw std::runtime_error("invalid --structure-gate-ms: needs --math5-ms");
    if (!std::isfinite(math5_ms)||math5_ms<0||math5_ms>1000)''')

# Allow an independent DRAT output for CDCL fallback while retaining the
# structurally generated JSON certificate in a completely separate file.
# The result checker must select EITHER proof path, never accept both.
patch('        math5_certificate==input || math5_certificate==proof_path ||\n        !proof_path.empty()))',
      '        math5_certificate==input || math5_certificate==proof_path))')
patch('MATH5 custom proof needs --math5-certificate and no --proof; not DRAT/LRAT',
      'MATH5 needs a separate custom certificate path (never treat it as DRAT)')
patch('        solver->configureMath5(math5_ms,raw_sha,math5_certificate);',
r'''        solver->configureMath5(math5_ms,raw_sha,math5_certificate);
        solver->configureStructureGate(structure_gate_ms);''')
patch('        std::cerr<<"MATH5_UNIFIED_STATS ',
r'''        const auto& g=solver->structureGateDecision();
        std::cerr<<"STRUCTURE_GATE_STATS {\"enabled\":"
                 <<(structure_gate_ms>0?"true":"false")
                 <<",\"selected_math5\":"<<(g.use_math5?"true":"false")
                 <<",\"reason\":\""<<g.reason
                 <<"\",\"scan_ms\":"<<g.wall_ms
                 <<",\"original_clauses\":"<<g.source_clauses
                 <<",\"negative_binary\":"<<g.negative_binary
                 <<",\"positive_alo\":"<<g.positive_alo
                 <<",\"complete_eo\":"<<g.candidate_eo
                 <<",\"complete_xor\":"<<g.complete_xor
                 <<",\"mixed\":"<<g.mixed_clauses<<"}\n";
        std::cerr<<"MATH5_UNIFIED_STATS ''')

output=OUT/"drnas_x59_structure_gate.cpp"
output.write_text(source)
candidate=ROOT/"build/drnas-x59-structure-gate1"
cmd=[os.environ.get("CXX","g++"),"-std=c++20","-O3","-DNDEBUG",
     "-I"+str(ROOT/"src"),
     "-I"+str(ROOT/"build/xor_math5_unified1"),
     str(output),"-lcrypto","-o",str(candidate)]
print("STRUCTURE_GATE_BUILD "+" ".join(cmd),flush=True)
subprocess.run(cmd,cwd=ROOT,check=True)
print("STRUCTURE_GATE_BUILD_OK",{
    "candidate_sha256":hashlib.sha256(candidate.read_bytes()).hexdigest(),
    "generated_source_sha256":hashlib.sha256(output.read_bytes()).hexdigest(),
    "baseline_sha256":hashlib.sha256((ROOT/"build/drnas-x59-xor-math5-unified1").read_bytes()).hexdigest(),
},flush=True)
