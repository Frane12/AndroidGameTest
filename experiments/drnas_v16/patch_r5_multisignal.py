#!/usr/bin/env python3
"""R5.0 multi-signal guarded intervention atop reproducible R4 patch.

R5 provisional policy, fitted ONLY using R3/R4 development diagnostics:
  At first 512 conflicts, require:
  restarts <=20 AND fast/slow glue ratio < 0.965 AND
  propagations/conflict in [60,200] AND decisions/conflict <=2.15.
  If and only if all pass, in same Kissat search change restartint to 25
  at conflict 2048. No restart resets, state destruction or oracle.
  Compare original R4 and forced interventions within same compiled binary.
  R4 prior policy remains available for a strict paired comparator.
"""
from __future__ import annotations
import argparse,hashlib
from pathlib import Path
from patch_r4_restart_gate import patch as r4_patch

PIN="8af8e56f174b778aef3aa45af9f739b2a5f492c2"
THRESHOLD=20
GLUE_LT=0.965
PROP_MIN=60.0
PROP_MAX=200.0
DEC_MAX=2.15
SAMPLE=512
SWITCH=2048
INTERVAL=25

def substitute_once(s: str, old: str, new: str) -> str:
    n=s.count(old)
    if n!=1: raise RuntimeError(f"R4_EXPECT_EXACTLY_ONE_ANCHOR count={n} at={old[:100]}")
    return s.replace(old,new,1)

def patch(source: str) -> str:
    s=r4_patch(source)
    s=substitute_once(s,
        '  const bool r4_monitor=!strcmp(drnas_mode,"r4_monitor");',
        '  const bool r4_monitor=!strcmp(drnas_mode,"r4_monitor");\n'
        '  const bool r5_gate=!strcmp(drnas_mode,"r5_gate");\n'
        '  const bool r5_monitor=!strcmp(drnas_mode,"r5_monitor");')
    s=substitute_once(s,
        '          if (r4_gate || r4_inverse || r4_monitor) {',
        '          if (r4_gate || r4_inverse || r4_monitor || r5_gate || r5_monitor) {')
    s=substitute_once(s,
        '          drnas_sampled=true;\n'
        '        }\n'
        '        if (drnas_active && !res && !drnas_changed && drnas_target &&',
        '''          if (r5_gate || r5_monitor) {
            const uint64_t r5_restarts =
              (solver->statistics.restarts >= r4_initial_restarts) ?
              solver->statistics.restarts-r4_initial_restarts : 0;
            const bool r5_ok=(r5_restarts <=20) &&
                (drnas_g<0.965) &&
                (drnas_p>=60.0 && drnas_p<=200.0) &&
                (drnas_d<=2.15);
            if (r5_gate && r5_ok) drnas_target=2048;
            printf("c R5_EARLY conflict=%" PRIu64
              " restarts=%" PRIu64 " g=%.9f p=%.9f d=%.9f"
              " eligible=%d action=%" PRIu64 "\\n",
              drnas_seen,r5_restarts,drnas_g,drnas_p,drnas_d,
              (int)r5_ok,drnas_target);
            fflush(stdout);
          }
          drnas_sampled=true;
        }
        if (drnas_active && !res && !drnas_changed && drnas_target &&''') 
    if 'R5_EARLY' not in s:raise RuntimeError("R5 instrumentation did not apply")
    return s

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--kissat-root",type=Path,required=True)
    a=p.parse_args()
    f=a.kissat_root/"src"/"search.c"
    src=f.read_text()
    out=patch(src)
    f.write_text(out)
    print("R5_FROZEN_PATCH_APPLIED",PIN,
          "r512_leq20_g_lt0.965_p60_200_d_le2.15_at2048_restartint25",
          "modified_search_sha256="+hashlib.sha256(out.encode()).hexdigest(),flush=True)

if __name__=="__main__":
    main()
