#!/usr/bin/env python3
"""Add an opt-in, frozen Jerk-triggered restart to the pinned R6 Kissat build.

The default solver path is unchanged. DRNAS_JERK_GATE=1 enables a one-time
decision at the 2048-conflict checkpoint. The normalized absolute timed-jerk
threshold is frozen from the 13 formula-level complete R7 calibration traces.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

PIN_KISSAT = "8af8e56f174b778aef3aa45af9f739b2a5f492c2"
THRESHOLD = 0.0105088239760238
PREFIX_MARKS = [32, 64, 96, 128, 160, 192, 224, 256, 320, 384,
                448, 512, 640, 768, 896, 1024, 1280, 1536, 1792, 2048]


def replace_once(source: str, old: str, new: str) -> str:
    n = source.count(old)
    if n != 1:
        raise RuntimeError(f"R9 frozen source anchor mismatch ({n}): {old[:100]}")
    return source.replace(old, new, 1)


def patch(source: str) -> str:
    source = replace_once(
        source,
        '#include "search.h"',
        '#include "search.h"\n#include <stdlib.h>\n#include <string.h>')
    source = replace_once(
        source,
        "  unsigned r6_checkpoint_index=0;",
        """  unsigned r6_checkpoint_index=0;
  uint64_t r9_jerk_wall_ns[20]={0};
  uint64_t r9_jerk_conflicts[20]={0};
  bool r9_jerk_gate_evaluated=false;""")
    source = replace_once(
        source,
        '            printf("c R6_TRACE conflict=%" PRIu64 " wall_ns=%" PRIu64',
        """            if (r6_checkpoint_index<20) {
              r9_jerk_wall_ns[r6_checkpoint_index]=drnas_jerk_wall_ns;
              r9_jerk_conflicts[r6_checkpoint_index]=drnas_seen;
            }
            printf("c R6_TRACE conflict=%" PRIu64 " wall_ns=%" PRIu64""")
    gate = f"""            r6_checkpoint_index++;
            const char *r9_jerk_env=getenv("DRNAS_JERK_GATE");
            if (r6_checkpoint_index==20 && !r9_jerk_gate_evaluated &&
                r9_jerk_env && !strcmp(r9_jerk_env,"1")) {{
              r9_jerk_gate_evaluated=true;
              bool r9_valid=true;
              for (unsigned r9_i=1;r9_i<20;r9_i++)
                if (r9_jerk_wall_ns[r9_i]<=r9_jerk_wall_ns[r9_i-1] ||
                    r9_jerk_conflicts[r9_i]<=r9_jerk_conflicts[r9_i-1])
                  r9_valid=false;
              double r9_samples[11]={{0}};
              if (r9_valid) {{
                for (unsigned r9_q=0;r9_q<=10;r9_q++) {{
                  const double r9_target=(double)r9_jerk_wall_ns[0] +
                    (double)(r9_jerk_wall_ns[19]-r9_jerk_wall_ns[0]) *
                    (double)r9_q / 10.0;
                  unsigned r9_hi=1;
                  while (r9_hi<20 &&
                         (double)r9_jerk_wall_ns[r9_hi]<r9_target)
                    r9_hi++;
                  if (r9_hi>=20) r9_hi=19;
                  const double r9_span=(double)(
                    r9_jerk_wall_ns[r9_hi]-r9_jerk_wall_ns[r9_hi-1]);
                  if (r9_span<=0.0) {{
                    r9_valid=false;
                    break;
                  }}
                  const double r9_fraction=(r9_target-
                    (double)r9_jerk_wall_ns[r9_hi-1])/r9_span;
                  r9_samples[r9_q]=(double)r9_jerk_conflicts[r9_hi-1] +
                    ((double)r9_jerk_conflicts[r9_hi]-
                     (double)r9_jerk_conflicts[r9_hi-1])*r9_fraction;
                }}
              }}
              double r9_jerk=0.0;
              if (r9_valid) {{
                double r9_sum=0.0;
                for (unsigned r9_i=3;r9_i<=10;r9_i++) {{
                  double r9_d=r9_samples[r9_i]-3.0*r9_samples[r9_i-1] +
                    3.0*r9_samples[r9_i-2]-r9_samples[r9_i-3];
                  if (r9_d<0.0) r9_d=-r9_d;
                  r9_sum+=r9_d;
                }}
                double r9_denominator=r9_samples[10]-r9_samples[0];
                if (r9_denominator<1.0) r9_denominator=1.0;
                r9_jerk=r9_sum/8.0/r9_denominator;
              }}
              const bool r9_eligible=r9_valid &&
                r9_jerk>={THRESHOLD:.16f};
              if (r9_eligible && !drnas_changed && !res) drnas_target=2048;
              printf("c DRNAS_JERK_GATE conflict=%" PRIu64
                  " jerk_abs=%.12f threshold=%.16f valid=%d"
                  " eligible=%d action=%" PRIu64 "\\n",
                  drnas_seen,r9_jerk,{THRESHOLD:.16f},(int)r9_valid,
                  (int)r9_eligible,r9_eligible && !drnas_changed && !res ?
                    (uint64_t)2048 : (uint64_t)0);
              fflush(stdout);
            }}"""
    source = replace_once(source, "            r6_checkpoint_index++;", gate)
    if source.count("DRNAS_JERK_GATE") != 2:
        raise RuntimeError("R9 gate patch did not apply completely")
    return source


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kissat-root", type=Path, required=True)
    args = parser.parse_args()
    path = args.kissat_root / "src" / "search.c"
    updated = patch(path.read_text())
    path.write_text(updated)
    print("R9_JERK_GATE_PATCHED", PIN_KISSAT,
          "threshold="+format(THRESHOLD, ".16f"),
          "marks="+str(len(PREFIX_MARKS)),
          "sha256="+hashlib.sha256(updated.encode()).hexdigest(), flush=True)


if __name__ == "__main__":
    main()
