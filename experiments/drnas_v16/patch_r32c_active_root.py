#!/usr/bin/env python3
"""R32c: additive patch to the audited R32b native instrumented pinned Kissat.

Run patch_r32b_native_shadow.py FIRST. R32c changes only parse-time behavior:
when explicitly selected by R32B_MODE=active, inject up to twelve mathematically
entailed GF(2) ROOT UNIT clauses before Kissat preprocesses/searches. Every
candidate must be a consequence of complete source-CNF parity clause blocks
or sound binary-parent resolvents and independently reproduced root BCP.
An UNSAT parity subsystem is NOT a unit source. All uncertain cases abstain.
No restart, phase, learned-clause, heuristic, or decision policy modification.
"""
import argparse
from pathlib import Path

def replace_once(s, old, new, label):
    count = s.count(old)
    if count != 1:
        raise RuntimeError(f"R32C_ANCHOR_ERROR {label} count={count}")
    return s.replace(old, new, 1)

INJECTION = r'''  // R32c: computed from the original DIMACS capture ONLY. No learned CNF.
  if (!res && !solver->inconsistent) {
    const char *mode = getenv("R32B_MODE");
    if (mode && !strcmp(mode, "active")) {
      r32b_discover();
      if (r32b_guard) {
        printf("c R32C_ACTIVE signal=INPUT_GUARD injected=0 certified=0\n");
      } else {
        r32b_gap gap = r32b_compute(NULL, 0);
        const int admissible = !gap.contradiction &&
          gap.extra > 0 && gap.extra <= 12 && gap.nsample == gap.extra;
        if (admissible) {
          // Each signed literal follows algebraically from sound source
          // equations + original BCP, and is added at the root only.
          for (unsigned i = 0; i < gap.nsample; i++) {
            kissat_add(solver, gap.sample[i]);
            kissat_add(solver, 0);
          }
          printf("c R32C_ACTIVE signal=APPLIED injected=%u certified=%u\n",
                 gap.nsample, gap.extra);
        } else {
          printf("c R32C_ACTIVE signal=%s injected=0 certified=%u\n",
                 gap.contradiction ? "CONTRADICTION_ABSTAIN" :
                 gap.extra ? "UNIT_CAP_ABSTAIN" : "NO_GAP",
                 gap.contradiction ? 0 : gap.extra);
        }
      }
      fflush(stdout);
    }
  }
'''

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--kissat-root", type=Path, required=True)
    args=ap.parse_args()
    src=args.kissat_root/"src"
    header=src/"r32b_shadow_core.h"
    parse=src/"parse.c"
    h=header.read_text()
    h=replace_once(h,
      'r32b_active=(mode && !strcmp(mode,"shadow")) ? 1 : 0;',
      'r32b_active=(mode && (!strcmp(mode,"shadow") || !strcmp(mode,"active"))) ? 1 : 0;',
      "enable_active_capture")
    s=parse.read_text()
    s=replace_once(s,
      '  res = parse_dimacs (solver, file, strict, lineno_ptr, max_var_ptr);\n  if (!solver->inconsistent)',
      '  res = parse_dimacs (solver, file, strict, lineno_ptr, max_var_ptr);\n'+INJECTION+
      '  if (!solver->inconsistent)',
      "parse_before_defrag")
    header.write_text(h)
    parse.write_text(s)
    print("R32C_CERTIFIED_ROOT_PATCH_OK",flush=True)

if __name__=="__main__":
    main()
