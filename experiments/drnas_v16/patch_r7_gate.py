#!/usr/bin/env python3
"""Experimental R7 rule layered onto the pinned R6 instrumentation.

R7 is a hypothesis derived from R6, not an independently validated predictor.
At 512 conflicts, allow the existing 2048-conflict switch to restartint=25
only when 0 < propagations/conflict < 35.  Missing checkpoints abstain.
The R5 mode name is retained internally solely for the existing R6 parser;
the benchmark labels this altered mode r7_gate. Other modes are unchanged.
"""
from pathlib import Path
import argparse
import hashlib
from patch_r6_trace import patch as patch_r6

OLD = '''const bool r5_ok=(r5_restarts <=20) &&
                (drnas_g<0.965) &&
                (drnas_p>=60.0 && drnas_p<=200.0) &&
                (drnas_d<=2.15);'''
NEW = '''const bool r5_ok=(drnas_p>0.0 && drnas_p<35.0);'''

def patch(source):
    result = patch_r6(source)
    if result.count(OLD) != 1:
        raise RuntimeError("R7 gate anchor mismatch; refusing to patch")
    return result.replace(OLD, NEW, 1)

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--kissat-root", type=Path, required=True)
    args = p.parse_args()
    f = args.kissat_root / "src" / "search.c"
    result = patch(f.read_text())
    f.write_text(result)
    print("R7_GATE_PATCH_OK", hashlib.sha256(result.encode()).hexdigest(), flush=True)
