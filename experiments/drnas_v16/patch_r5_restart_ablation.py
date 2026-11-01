#!/usr/bin/env python3
"""R5 diagnostic ablation: matched in-process restartint=25/50/100 at C2048.

Development-only pilot on known R4 regression formula #361. Not a blind
holdout, a world-record claim, or a validated generalized improvement.
All arms retain the original Kissat source, apart from tracing and the
specified single in-process option intervention.
"""
from __future__ import annotations
from pathlib import Path
import argparse
import hashlib
from predict_conflict_patch_v177 import patch as v177_patch

PIN = "8af8e56f174b778aef3aa45af9f739b2a5f492c2"

def once(s: str, original: str, changed: str) -> str:
    count = s.count(original)
    if count != 1:
        raise RuntimeError(f"R5 patch anchor mismatch count={count}: {original[:100]}")
    return s.replace(original, changed, 1)

def patch(source: str) -> str:
    s = v177_patch(source)
    s = once(
        s,
        '  const bool drnas_forced=!strcmp(drnas_mode,"switch2048");',
        '  const bool drnas_forced=!strcmp(drnas_mode,"switch2048");\n'
        '  const bool r5_25=!strcmp(drnas_mode,"r5_25");\n'
        '  const bool r5_50=!strcmp(drnas_mode,"r5_50");\n'
        '  const bool r5_100=!strcmp(drnas_mode,"r5_100");',
    )
    s = once(
        s,
        '    if (drnas_forced) drnas_target=2048;',
        '    if (drnas_forced || r5_25 || r5_50 || r5_100) drnas_target=2048;',
    )
    s = once(
        s,
        '          kissat_set_option(solver,"restartint",25);',
        '          const int drnas_r5_interval=r5_100?100:(r5_50?50:25);\n'
        '          kissat_set_option(solver,"restartint",drnas_r5_interval);',
    )
    if 'drnas_r5_interval' not in s or 'r5_100' not in s:
        raise RuntimeError("R5 patch verification failed")
    return s

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kissat-root", type=Path, required=True)
    args = parser.parse_args()
    file = args.kissat_root / "src" / "search.c"
    original = file.read_text()
    transformed = patch(original)
    file.write_text(transformed)
    print(
        "R5_ABLATION_PATCH_APPLIED",
        PIN,
        "fixed_intervention_C2048",
        "restartint=[25,50,100]",
        "search_sha256=" + hashlib.sha256(transformed.encode()).hexdigest(),
        flush=True,
    )

if __name__ == "__main__":
    main()
