#!/usr/bin/env python3
"""R6 read-only seven-checkpoint dynamics instrumentation layered on frozen R5.
Instrumentation changes no solver state or decisions. Existing R4/R5 policies
remain unchanged; 512-conflict gate and 2048-conflict restart switch are frozen.
"""
from pathlib import Path
import argparse
import hashlib
from patch_r5_multisignal import patch as patch_r5

PIN = "8af8e56f174b778aef3aa45af9f739b2a5f492c2"

def replace_exact(src, old, new):
    n = src.count(old)
    if n != 1:
        raise RuntimeError(f"R6_PINNED_ANCHOR_CHANGED count={n}: {old[:110]}")
    return src.replace(old, new, 1)

def patch(src):
    src = patch_r5(src)
    src = replace_exact(src, "  uint64_t drnas_start=0, drnas_target=0;",
        """  uint64_t drnas_start=0, drnas_target=0;
  unsigned r6_checkpoint_index=0;
  uint64_t r6_base_decisions=0, r6_base_props=0, r6_base_restarts=0;
  uint64_t r6_base_learned=0;""")
    src = replace_exact(src, "    drnas_start=CONFLICTS;\n    r4_initial_restarts=",
        """    drnas_start=CONFLICTS;
    r6_base_decisions=DECISIONS;
    r6_base_props=solver->statistics.propagations;
    r6_base_restarts=solver->statistics.restarts;
    r6_base_learned=solver->statistics.clauses_learned;
    r4_initial_restarts=""")
    src = replace_exact(src,
        "        if (drnas_active && !res && !drnas_sampled && drnas_seen>=512) {",
        """        if (drnas_active && r6_checkpoint_index<7) {
          static const uint64_t r6_marks[7]={100,250,500,1000,2000,4096,8192};
          if (drnas_seen>=r6_marks[r6_checkpoint_index]) {
            printf("c R6_TRACE conflict=%" PRIu64
                " restarts=%" PRIu64 " decisions=%" PRIu64
                " propagations=%" PRIu64 " learned=%" PRIu64
                " glue=%.9f stable=%d\\n",
                drnas_seen, solver->statistics.restarts-r6_base_restarts,
                DECISIONS-r6_base_decisions,
                solver->statistics.propagations-r6_base_props,
                solver->statistics.clauses_learned-r6_base_learned,
                AVERAGE(fast_glue)/(AVERAGE(slow_glue)>1e-9 ?
                   AVERAGE(slow_glue):1e-9), (int)solver->stable);
            fflush(stdout);
            r6_checkpoint_index++;
          }
        }
        if (drnas_active && !res && !drnas_sampled && drnas_seen>=512) {""")
    if src.count("c R6_TRACE") != 1:
        raise RuntimeError("R6 marker insertion failed")
    return src

if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--kissat-root",type=Path,required=True)
    args=parser.parse_args()
    source=args.kissat_root/"src"/"search.c"
    new=patch(source.read_text())
    source.write_text(new)
    print("R6_PINNED_PATCH_OK",PIN,
          "sha256="+hashlib.sha256(new.encode()).hexdigest(),flush=True)
