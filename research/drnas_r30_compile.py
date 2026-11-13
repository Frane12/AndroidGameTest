#!/usr/bin/env python3
"""R30: isolated CDCL timer variants derived from frozen R29 native controls.

Only additional telemetry and DRNAS_PROFILE macro, without changing CDCL
inference, branching or clause learning. Original R29 executables are retained.
"""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path("mre_atlas23")
CXX = os.environ.get("CXX", "g++")
subprocess.run(["python3", "research/drnas_ltm9_cert_compile.py"], check=True)

for original, generated_name, executable in (
    ("native.cpp", "native_r30_profile.cpp", "drnas_r30_ltm8_profile"),
    ("native_certificate.cpp", "native_certificate_r30_profile.cpp", "drnas_r30_ltm9_profile"),
):
    source = (ROOT / original).read_text()
    anchor = "const auto &st=solver.statistics();"
    assert source.count(anchor) == 1, ("profile site changed", original)
    source = source.replace(anchor, anchor + "\n  solver.print_profile();", 1)
    anchor = '<<" conflicts="<<st.conflicts<<" decisions="<<st.decisions'
    assert source.count(anchor) == 1, ("counter site changed", original)
    source = source.replace(anchor, anchor
        + '<<" propagations="<<st.propagations'
        + '<<" watch_visits="<<st.watch_visits'
        + '<<" learned_clauses="<<st.learned_clauses'
        + '<<" restarts="<<st.restarts', 1)
    generated = ROOT / generated_name
    generated.write_text(source)
    subprocess.run([
        CXX, "-O3", "-std=c++17", "-DDRNAS_PROFILE",
        "-I", "research", "-I", "mre_atlas23", "-I", "mre_atlas15",
        str(generated), "-o", str(ROOT / "bin" / executable),
    ], check=True)

# The added measurements must not cause an invalid model or omit counters.
import drnas_ltm11_real2 as B
with tempfile.TemporaryDirectory() as temp:
    cnf = Path(temp) / "r30_smoke.cnf"
    cnf.write_text("p cnf 3 3\n1 2 0\n-1 3 0\n-2 3 0\n")
    for arm in ("LTM8_FAST", "LTM8_CHAOS", "LTM9_FAST"):
        args = B.command(arm, cnf, 17, 3.0)
        args[0] = str(ROOT / "bin" / (
            "drnas_r30_ltm9_profile" if arm == "LTM9_FAST"
            else "drnas_r30_ltm8_profile"
        ))
        test = subprocess.run(args, capture_output=True, text=True, timeout=8)
        assert test.returncode == 10, (arm, test.returncode, test.stderr[-300:])
        assert B.sat_witness_valid(cnf, 3, test.stdout), arm
        assert "DRNAS_PROFILE bcp_s=" in test.stdout, (arm, test.stdout[-400:])
        assert "ATLAS13_TRIAL " in test.stdout, arm
        assert " learned_clauses=" in test.stdout, arm
print("R30_COMPILE_SMOKE_PASS native_profile_binaries=2 native_modes=3")
