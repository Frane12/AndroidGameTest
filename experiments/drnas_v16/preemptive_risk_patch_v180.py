#!/usr/bin/env python3
"""V18.0: pre-intervention risk gate on exact pinned Kissat 4.0.4.

Builds on V17.8 instrument *without modifying the original module*.
At conflict 512, choose SKIP, SWITCH1024 or SWITCH2048, entirely based on
a frozen rule trained before the fresh holdout. Learned clauses are retained.
"""
from pathlib import Path
import argparse,hashlib
from feedback_patch_v178 import patch as patch_v178

def substitute_once(source,old,new):
    n=source.count(old)
    if n!=1:raise ValueError(f"Expected one upstream-instrument anchor, got {n}: {old[:70]}")
    return source.replace(old,new,1)

def patch(source):
    code=patch_v178(source)
    code=substitute_once(code,
        '  const bool drnas_feedback=!strcmp(drnas_mode,"feedback") ||\n       !strcmp(drnas_mode,"switch2048-feedback");',
        '  const bool drnas_feedback=!strcmp(drnas_mode,"feedback") ||\n       !strcmp(drnas_mode,"switch2048-feedback");\n'
        '  const bool drnas_riskgate=!strcmp(drnas_mode,"riskgate");')
    code=substitute_once(code,
        '  unsigned drnas_checks=0;',
        '  unsigned drnas_checks=0;\n'
        '  char drnas_guard_feature=\'g\', drnas_guard_op[8]="lt";\n'
        '  double drnas_guard_threshold=0;\n'
        '  int drnas_guard_pass=0, drnas_guard_fail=0;')
    code=substitute_once(code,
        "  REPORT (0, '*');",
        """  if (drnas_riskgate) {
    const char *file=getenv("DRNAS_V180_RULE_FILE");
    FILE *f=file?fopen(file,"r"):NULL;
    if (!f) {fprintf(stderr,"DRNAS_V180_RULE_MISSING\\n");exit(77);}
    const int got=fscanf(f," %c %7s %lf %d %d",
        &drnas_guard_feature,drnas_guard_op,&drnas_guard_threshold,
        &drnas_guard_pass,&drnas_guard_fail);
    fclose(f);
    if (got!=5 || !strchr("rdpgl",drnas_guard_feature) ||
        (strcmp(drnas_guard_op,"lt") && strcmp(drnas_guard_op,"ge")) ||
        (drnas_guard_pass!=0 && drnas_guard_pass!=1024 &&
         drnas_guard_pass!=2048) ||
        (drnas_guard_fail!=0 && drnas_guard_fail!=1024 &&
         drnas_guard_fail!=2048)) {
      fprintf(stderr,"DRNAS_V180_BAD_RULE\\n");exit(77);
    }
  }
  REPORT (0, '*');""")
    code=substitute_once(code,
        '    if (drnas_forced) drnas_target=2048;',
        '    if (drnas_forced) drnas_target=2048;\n'
        '    if (!strcmp(drnas_mode,"switch1024")) drnas_target=1024;')
    code=substitute_once(code,
        '          fflush(stdout);\n          drnas_sampled=true;',
        """          if (drnas_riskgate) {
            const double score=drnas_guard_feature=='r'?drnas_r:
              drnas_guard_feature=='d'?drnas_d:
              drnas_guard_feature=='p'?drnas_p:
              drnas_guard_feature=='l'?drnas_l:drnas_g;
            const bool pass=!strcmp(drnas_guard_op,"lt") ?
                score<drnas_guard_threshold : score>=drnas_guard_threshold;
            drnas_target=(uint64_t)(pass?drnas_guard_pass:drnas_guard_fail);
            fprintf(stdout,"c DRNAS_V180_GUARD action=%" PRIu64
                " feature=%c value=%.9f op=%s threshold=%.9f"
                " decision=%s\\n",drnas_target,drnas_guard_feature,
                score,drnas_guard_op,drnas_guard_threshold,
                drnas_target?"SWITCH":"SKIP");
          }
          fflush(stdout);
          drnas_sampled=true;""")
    return code

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--kissat-root",required=True,type=Path)
    a=p.parse_args()
    path=a.kissat_root/"src"/"search.c"
    patched=patch(path.read_text())
    path.write_text(patched)
    print("V180_PINNED_PREEMPTIVE_PATCH_PASS",
          hashlib.sha256(patched.encode()).hexdigest(),flush=True)

if __name__=="__main__":main()
