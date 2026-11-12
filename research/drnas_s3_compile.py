#!/usr/bin/env python3
"""Build isolated S3 CDCL native engine; preserve baseline and original CNF."""
from pathlib import Path
import os
import subprocess
p = Path("mre_atlas23/native_certificate.cpp")
if not p.exists():
    raise RuntimeError("first run research/drnas_ltm9_cert_compile.py")
src = p.read_text()
anchor = "   solver.add_cnf(work);"
if src.count(anchor) != 1 or "drnas_s3_crr.hpp" in src:
    raise RuntimeError("native integration point drifted")
src = '#include "drnas_s3_crr.hpp"\n' + src.replace(
    anchor,
    "   const auto drnas_s3_stats = drnas_s3::enrich(work);\n" + anchor,
    1)
out = p.with_name("native_s3_crr.cpp")
out.write_text(src)
command = [os.environ.get("CXX", "g++"), "-O3", "-std=c++17",
           "-I", "research", "-I", "mre_atlas23", "-I", "mre_atlas15",
           str(out), "-o", "mre_atlas23/bin/drnas_s3_crr"]
subprocess.run(command, check=True)
print("S3_NATIVE_BUILD_PASS baseline_unchanged=true added_derived_cnf=true", flush=True)
