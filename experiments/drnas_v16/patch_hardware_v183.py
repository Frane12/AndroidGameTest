#!/usr/bin/env python3
"""DRNAS V18.3: read-only CPU/logic phase diagnostics for preprocessing.

Apply AFTER patch_neuroflow_v182.py, to the same pinned Kissat source.
The per-window V18.2 conflict telemetry remains unchanged. This patch fills
its blind spot for formulas solved in preprocessing: one sample per preprocessing
round, never an invented set of 256 conflicts. No solver-policy modifications.
A process-level getrusage audit lives in official_hardware_v183.py.
"""
from __future__ import annotations
import argparse
from pathlib import Path

BASE_SHA="8af8e56f174b778aef3aa45af9f739b2a5f492c2"

def patch_preprocess(text: str) -> str:
    if "V183_PREPROCESS" in text:
        raise RuntimeError("V18.3 patch already applied")
    def once(before: str, after: str):
        nonlocal text
        n=text.count(before)
        if n != 1:
            raise RuntimeError(f"V183_EXPECTED_ONE_ANCHOR got={n} snippet={before[:100]}")
        text=text.replace(before,after,1)
    once("#include <inttypes.h>\n",
r'''#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

static uint64_t drnas_v183_process_cpu_ns (void) {
  struct timespec time;
  if (clock_gettime (CLOCK_PROCESS_CPUTIME_ID, &time))
    return 0;
  return (uint64_t) time.tv_sec * 1000000000ull + (uint64_t) time.tv_nsec;
}
''')
    once("  START (preprocess);\n  assert (!solver->preprocessing);",
r'''  START (preprocess);
  const char *v183_flag = getenv ("DRNAS_V183_HW");
  const bool v183_enabled = v183_flag && !strcmp (v183_flag, "1");
  const uint64_t v183_cpu_start =
      v183_enabled ? drnas_v183_process_cpu_ns () : 0;
  if (v183_enabled) {
    printf ("c V183_PREPROCESS_BEGIN cpu_ns=%" PRIu64
            " variables=%u clauses=%" PRIu64
            " conflicts=%" PRIu64 " propagations=%" PRIu64 "\n",
            v183_cpu_start, solver->active, BINIRR_CLAUSES,
            solver->statistics.conflicts, solver->statistics.propagations);
  }
  assert (!solver->preprocessing);''')
    once("    const uint64_t clauses_after = BINIRR_CLAUSES;\n#ifndef QUIET",
r'''    const uint64_t clauses_after = BINIRR_CLAUSES;
    if (v183_enabled) {
      const uint64_t cpu = drnas_v183_process_cpu_ns ();
      printf ("c V183_PREPROCESS_ROUND round=%u cpu_ns=%" PRIu64
              " elapsed_ns=%" PRIu64 " variables_before=%u"
              " variables_after=%u clauses_before=%" PRIu64
              " clauses_after=%" PRIu64
              " conflicts=%" PRIu64 " propagations=%" PRIu64 "\n",
              round, cpu, cpu >= v183_cpu_start ? cpu - v183_cpu_start : 0,
              variables_before, variables_after,
              clauses_before, clauses_after, solver->statistics.conflicts,
              solver->statistics.propagations);
    }
#ifndef QUIET''')
    once("  STOP (preprocess);\n  return solver->inconsistent ? 20 : 0;",
r'''  if (v183_enabled) {
    const uint64_t cpu = drnas_v183_process_cpu_ns ();
    printf ("c V183_PREPROCESS_END cpu_ns=%" PRIu64
            " elapsed_ns=%" PRIu64 " variables=%u clauses=%" PRIu64
            " conflicts=%" PRIu64 " propagations=%" PRIu64 "\n",
            cpu, cpu >= v183_cpu_start ? cpu - v183_cpu_start : 0,
            solver->active, BINIRR_CLAUSES, solver->statistics.conflicts,
            solver->statistics.propagations);
    fflush (stdout);
  }
  STOP (preprocess);
  return solver->inconsistent ? 20 : 0;''')
    return text

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--kissat-root",type=Path,required=True)
    args=p.parse_args()
    path=args.kissat_root/"src"/"preprocess.c"
    path.write_text(patch_preprocess(path.read_text()))
    print("V183_PREPROCESS_PATCH_PASS",BASE_SHA)

if __name__ == "__main__":
    main()
