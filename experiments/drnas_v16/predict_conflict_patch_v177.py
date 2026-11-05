#!/usr/bin/env python3
"""DRNAS V17.7: in-process conflict-512 feature capture and frozen selector.

Exact pinned upstream Kissat 4.0.4 patch. No prior CNF output, no SAT witness,
no restarts, and no learned clauses are reset by the intervention. The rule
file is trained only on 176000-176019 (V17.6 development).
"""
from pathlib import Path
import argparse,hashlib

PINNED="8af8e56f174b778aef3aa45af9f739b2a5f492c2"

def patch(src):
    if "DRNAS_V177" in src:raise ValueError("Already patched")
    def once(a,b):
        nonlocal src
        if src.count(a)!=1:
            raise ValueError(f"Pinned Kissat source changed near {a[:80]}: {src.count(a)}")
        src=src.replace(a,b,1)
    once("#include <inttypes.h>\n",
         "#include <inttypes.h>\n#include <stdio.h>\n#include <stdlib.h>\n#include <string.h>\n")
    once("int kissat_search (kissat *solver) {\n  REPORT (0, '*');",
"""int kissat_search (kissat *solver) {
  const char *drnas_mode=getenv("DRNAS_V177_MODE");
  if (!drnas_mode) drnas_mode="";
  const bool drnas_active=*drnas_mode!=0;
  const bool drnas_predict=!strcmp(drnas_mode,"predict");
  const bool drnas_forced=!strcmp(drnas_mode,"switch2048");
  uint64_t drnas_start=0, drnas_target=0;
  bool drnas_sampled=false, drnas_changed=false;
  char drnas_feature='g', drnas_op[8]="ge";
  double drnas_threshold=0;
  int drnas_action=0;
  if (drnas_predict) {
    const char *file=getenv("DRNAS_V177_RULE_FILE");
    FILE *f=file?fopen(file,"r"):NULL;
    if (!f) {fprintf(stderr,"DRNAS_V177_RULE_FILE_MISSING\\n");exit(77);}
    if (fscanf(f,"%c %7s %lf %d", &drnas_feature, drnas_op,
               &drnas_threshold, &drnas_action)!=4 ||
        !strchr("rdpgl",drnas_feature) ||
        (strcmp(drnas_op,"lt") && strcmp(drnas_op,"ge")) ||
        (drnas_action!=0 && drnas_action!=1024 && drnas_action!=2048)) {
      fprintf(stderr,"DRNAS_V177_RULE_BAD\\n");exit(77);
    }
    fclose(f);
  }
  REPORT (0, '*');""")
    once("    start_search (solver);\n    while (!res) {",
"""    start_search (solver);
    drnas_start=CONFLICTS;
    if (drnas_forced) drnas_target=2048;
    while (!res) {""")
    once("      if (conflict)\n        res = kissat_analyze (solver, conflict);\n      else if (solver->iterating)",
"""      if (conflict) {
        res=kissat_analyze(solver,conflict);
        const uint64_t drnas_seen=CONFLICTS-drnas_start;
        if (drnas_active && !res && !drnas_sampled && drnas_seen>=512) {
          const double drnas_r=(double)solver->statistics.restarts/512.0;
          const double drnas_d=(double)DECISIONS/512.0;
          const double drnas_p=(double)solver->statistics.propagations/512.0;
          const double drnas_g=AVERAGE(fast_glue)/
                                (AVERAGE(slow_glue)>1e-9 ?
                                  AVERAGE(slow_glue) : 1e-9);
          const double drnas_l=(double)solver->statistics.clauses_learned/512.0;
          fprintf(stdout,
           "c DRNAS_V177_EARLY r=%.9f d=%.9f p=%.9f g=%.9f l=%.9f"
           " conflict=%" PRIu64 " restarts=%" PRIu64 "\\n",
           drnas_r,drnas_d,drnas_p,drnas_g,drnas_l,CONFLICTS,
           solver->statistics.restarts);
          if (drnas_predict) {
            const double v=drnas_feature=='r'?drnas_r:
              drnas_feature=='d'?drnas_d:
              drnas_feature=='p'?drnas_p:
              drnas_feature=='l'?drnas_l:drnas_g;
            const bool pass=!strcmp(drnas_op,"lt") ?
               v<drnas_threshold : v>=drnas_threshold;
            drnas_target=pass?(uint64_t)drnas_action:0;
            fprintf(stdout,"c DRNAS_V177_CHOICE action=%" PRIu64
              " feature=%c value=%.9f op=%s threshold=%.9f\\n",
              drnas_target,drnas_feature,v,drnas_op,drnas_threshold);
          }
          fflush(stdout);
          drnas_sampled=true;
        }
        if (drnas_active && !res && !drnas_changed && drnas_target &&
            drnas_seen>=drnas_target) {
          const uint64_t before=solver->statistics.clauses_learned;
          const int was=GET_OPTION(restartint);
          kissat_set_option(solver,"restartint",25);
          if (!solver->stable)
            kissat_update_focused_restart_limit(solver);
          const uint64_t after=solver->statistics.clauses_learned;
          fprintf(stdout,
            "c DRNAS_V177_SWITCH at=%" PRIu64 " before=%" PRIu64
            " after=%" PRIu64 " restart_before=%d restart_after=%d\\n",
            drnas_seen,before,after,was,GET_OPTION(restartint));
          fflush(stdout);
          drnas_changed=true;
        }
      } else if (solver->iterating)""")
    once("    stop_search (solver);\n  }\n  report_search_result (solver, res);",
"""    stop_search (solver);
    if (drnas_active) {
      fprintf(stdout,
        "c DRNAS_V177_FINAL conflicts=%" PRIu64
        " restarts=%" PRIu64 " learned=%" PRIu64 "\\n",
        CONFLICTS,solver->statistics.restarts,
        solver->statistics.clauses_learned);
      fflush(stdout);
    }
  }
  report_search_result (solver, res);""")
    return src

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--kissat-root",type=Path,required=True)
    a=parser.parse_args()
    f=a.kissat_root/"src"/"search.c"
    before=f.read_text()
    patched=patch(before)
    f.write_text(patched)
    print("V177_PINNED_IN_PROCESS_PATCH",
        PINNED,hashlib.sha256(patched.encode()).hexdigest(),flush=True)
