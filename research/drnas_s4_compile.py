#!/usr/bin/env python3
"""Compile two isolated S4 binaries from frozen original-CNF LTM9 certificate engine."""
from pathlib import Path
import os,subprocess
p=Path("mre_atlas23/native_certificate.cpp")
if not p.exists():
    raise RuntimeError("build LTM9 certificate first")
src=p.read_text()
anchor="   solver.add_cnf(work);"
if src.count(anchor)!=1 or "drnas_s4_utility.hpp" in src:
    raise RuntimeError("native insertion point mismatch")
for cap in (16,32):
    replacement=f"   const auto s4_stats=drnas_s4::enrich(work,{cap});\n"+anchor
    code='#include "drnas_s4_utility.hpp"\n'+src.replace(anchor,replacement,1)
    dest=p.with_name(f"native_s4_utility_{cap}.cpp")
    dest.write_text(code)
    out=f"mre_atlas23/bin/drnas_s4_utility_{cap}"
    cmd=[os.environ.get("CXX","g++"),"-O3","-std=c++17",
         "-I","research","-I","mre_atlas23","-I","mre_atlas15",
         str(dest),"-o",out]
    subprocess.run(cmd,check=True)
    print(f"S4_NATIVE_BUILD_PASS cap={cap} path={out} original_baseline_untouched=true",flush=True)
