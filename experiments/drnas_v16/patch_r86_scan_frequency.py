#!/usr/bin/env python3
"""R86 diagnostic ablation: only change CDCL XOR scan interval 4/16/64/256.

Apply after pinned R32b/R32n/R32s/R32u/R84/R85 patches. No solver rule,
reason format, CNF, source selection, or frozen V15.3.1 code is modified.
"""
from pathlib import Path
import argparse

BEFORE='r84_interval=freq && !strcmp(freq,"4") ? 4 : 16;'
AFTER=('r84_interval=freq && !strcmp(freq,"4") ? 4 :\n'
       '               freq && !strcmp(freq,"64") ? 64 :\n'
       '               freq && !strcmp(freq,"256") ? 256 : 16;')

def patch(path):
    text=path.read_text()
    if text.count(BEFORE)!=1:
        raise RuntimeError("R86_PATCH_FAIL_CLOSED expected exactly one R84 interval anchor")
    path.write_text(text.replace(BEFORE,AFTER,1))
    print("R86_ONLY_SCAN_CADENCE_4_16_64_256_PATCH_PASS",flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--kissat-root",type=Path)
    p.add_argument("--selftest",action="store_true")
    a=p.parse_args()
    if a.selftest:
        assert "64" in AFTER and "256" in AFTER and BEFORE not in AFTER
        print("R86_SCAN_INTERVAL_PATCH_SELFTEST_PASS",flush=True)
    elif a.kissat_root:patch(a.kissat_root/"src"/"search.c")
    else:p.error("provide --kissat-root or --selftest")
