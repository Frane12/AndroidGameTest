#!/usr/bin/env python3
"""R31: extend read-only R30 instrumentation with a final native conflict count.

The search algorithm, restart strategy, clause DB, decisions and propagation
are unchanged; this is telemetry only. Does not alter stable DRNAS V15.3.1.
"""
import argparse,hashlib
from pathlib import Path
from patch_r30_passive_cdcl import patch,UPSTREAM,change_once

def add_final(src):
    s=patch(src)
    before="  report_search_result (solver, res);\n  return res;"
    after="""  report_search_result (solver, res);
  printf ("c R31_FINAL status=%d conflict=%" PRIu64
          " decisions=%" PRIu64 " restarts=%" PRIu64
          " propagations=%" PRIu64 " learned=%" PRIu64 "\\n",
          res, solver->statistics.conflicts, solver->statistics.decisions,
          solver->statistics.restarts, solver->statistics.propagations,
          solver->statistics.clauses_learned);
  fflush(stdout);
  return res;"""
    s=change_once(s,before,after,"final_stats_anchor")
    if s.count("c R31_FINAL")!=1:raise RuntimeError("R31_FINAL_LOG_NOT_ATTACHED")
    return s

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--kissat-root",required=True,type=Path)
    a=p.parse_args()
    target=a.kissat_root/"src/search.c"
    content=add_final(target.read_text())
    target.write_text(content)
    print("R31_READONLY_CDCL_FINAL_PATCH_OK",UPSTREAM,
          "sha256="+hashlib.sha256(content.encode()).hexdigest(),flush=True)
if __name__=="__main__":main()
