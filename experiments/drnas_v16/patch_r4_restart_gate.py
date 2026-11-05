#!/usr/bin/env python3
"""R4.0 frozen low-restart gate: in-process Kissat intervention at 2048 conflicts.

Policy (frozen before official R4 test):
  Capture the absolute increment of restarts across FIRST 512 conflicts.
  If restarts <=20, at conflict 2048 switch restartint to 25.
  Otherwise NEVER switch. No oracle and no rerunning from scratch.

Alternative 'r4_inverse' is a pre-registered negative control.
By importing the verified V17.7 patch we retain the same intervention
mechanism, changing only the threshold control source.
"""
from __future__ import annotations
import argparse,hashlib
from pathlib import Path
from predict_conflict_patch_v177 import patch as v177_patch

PIN="8af8e56f174b778aef3aa45af9f739b2a5f492c2"
THRESHOLD=20
SAMPLE=512
SWITCH=2048
INTERVAL=25

def substitute_once(s: str, old: str, new: str) -> str:
    n=s.count(old)
    if n!=1: raise RuntimeError(f"R4_EXPECT_EXACTLY_ONE_ANCHOR count={n} at={old[:100]}")
    return s.replace(old,new,1)

def patch(source: str) -> str:
    s=v177_patch(source)
    s=substitute_once(s,
        '  const bool drnas_forced=!strcmp(drnas_mode,"switch2048");',
        '  const bool drnas_forced=!strcmp(drnas_mode,"switch2048");\n'
        '  const bool r4_gate=!strcmp(drnas_mode,"r4_gate");\n'
        '  const bool r4_inverse=!strcmp(drnas_mode,"r4_inverse");\n'
        '  const bool r4_monitor=!strcmp(drnas_mode,"r4_monitor");')
    s=substitute_once(s,
        '  uint64_t drnas_start=0, drnas_target=0;',
        '  uint64_t drnas_start=0, drnas_target=0;\n'
        '  uint64_t r4_initial_restarts=0;')
    s=substitute_once(s,
        '    drnas_start=CONFLICTS;\n'
        '    if (drnas_forced) drnas_target=2048;',
        '    drnas_start=CONFLICTS;\n'
        '    r4_initial_restarts=solver->statistics.restarts;\n'
        '    if (drnas_forced) drnas_target=2048;')
    s=substitute_once(s,
        '          drnas_sampled=true;\n'
        '        }\n'
        '        if (drnas_active && !res && !drnas_changed && drnas_target &&',
        '''          if (r4_gate || r4_inverse || r4_monitor) {
            const uint64_t early_restarts =
              (solver->statistics.restarts>=r4_initial_restarts) ?
              solver->statistics.restarts-r4_initial_restarts : 0;
            const bool accept=(early_restarts<=20);
            const bool permitted=r4_gate ? accept :
                                 r4_inverse ? !accept : false;
            if (permitted) drnas_target=2048;
            printf("c R4_EARLY conflict=%" PRIu64
                   " restarts=%" PRIu64
                   " threshold=20 eligible=%d"
                   " inverse=%d action=%" PRIu64 "\\n",
                   drnas_seen,early_restarts,(int)accept,
                   (int)r4_inverse,drnas_target);
          }
          drnas_sampled=true;
        }
        if (drnas_active && !res && !drnas_changed && drnas_target &&''')
    if 'R4_EARLY' not in s: raise RuntimeError("R4 instrumentation did not apply")
    return s

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--kissat-root",type=Path,required=True)
    a=p.parse_args()
    f=a.kissat_root/"src"/"search.c"
    src=f.read_text()
    out=patch(src)
    f.write_text(out)
    print("R4_FROZEN_PATCH_APPLIED",PIN,
          "r512_leq20_switch2048_restartint25",
          "modified_search_sha256="+hashlib.sha256(out.encode()).hexdigest(),flush=True)

if __name__=="__main__":
    main()
