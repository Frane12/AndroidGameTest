#!/usr/bin/env python3
"""R12 experimental *live in-process* structural+early-dynamics selector.
The V15.3.1 solver and the pinned upstream Kissat source are not modified in repo.
Layers on exact R11 Kissat source patch; all comparison arms share the same binary.
"""
from pathlib import Path
import argparse, hashlib
from patch_r11_restart_sweep import patch as patch_r11

PIN="8af8e56f174b778aef3aa45af9f739b2a5f492c2"
MODES=("r12_hybrid","r12_early","r12_structure","r12_inverse")
CV_CUTOFF=0.265
EARLY_P_CUTOFF=43.0
EARLY_G_CUTOFF=0.95
ACTION_CONFLICT=2048
ACTION_RESTARTINT=25

def once(s,old,new):
    n=s.count(old)
    if n!=1:raise RuntimeError(f"R12_ANCHOR_MISMATCH count={n} text={old[:95]}")
    return s.replace(old,new,1)

def patch(s):
    s=patch_r11(s)
    s=once(s,
      '  const bool drnas_predict=!strcmp(drnas_mode,"predict");',
      '''  const bool drnas_predict=!strcmp(drnas_mode,"predict");
  const bool r12_hybrid=!strcmp(drnas_mode,"r12_hybrid");
  const bool r12_early=!strcmp(drnas_mode,"r12_early");
  const bool r12_structure=!strcmp(drnas_mode,"r12_structure");
  const bool r12_inverse=!strcmp(drnas_mode,"r12_inverse");
  const bool r12_active=r12_hybrid || r12_early || r12_structure || r12_inverse;
  double r12_degree_cv=0.0;
  if (r12_active) {
    const char *cv_text=getenv("DRNAS_R12_DEGREE_CV");
    char *cv_end=NULL;
    if (!cv_text || !*cv_text) {
      fprintf(stderr,"R12_DEGREE_CV_MISSING\\n");exit(78);
    }
    r12_degree_cv=strtod(cv_text,&cv_end);
    if (!cv_end || *cv_end || !(r12_degree_cv>=0.0 && r12_degree_cv<=2.0)) {
      fprintf(stderr,"R12_DEGREE_CV_INVALID\\n");exit(78);
    }
  }''')
    s=once(s,
      '          const double drnas_l=(double)solver->statistics.clauses_learned/512.0;\n          fprintf(stdout,',
      '''          const double drnas_l=(double)solver->statistics.clauses_learned/512.0;
          if (r12_active) {
            const bool r12_early_pass =
              drnas_p>0.0 && drnas_p<43.0 && drnas_g<0.95;
            const bool r12_structure_pass = r12_degree_cv>=0.265;
            const bool r12_selected =
              r12_hybrid ? (r12_early_pass && r12_structure_pass) :
              r12_early ? r12_early_pass :
              r12_structure ? r12_structure_pass :
              (r12_early_pass && !r12_structure_pass);
            if (r12_selected) drnas_target=2048;
            fprintf(stdout,
              "c R12_CHOICE conflict=%" PRIu64
              " early=%d structural=%d selected=%d"
              " cv=%.9f p=%.9f g=%.9f target=%" PRIu64 "\\n",
              drnas_seen,(int)r12_early_pass,(int)r12_structure_pass,
              (int)r12_selected,r12_degree_cv,drnas_p,drnas_g,drnas_target);
            fflush(stdout);
          }
          fprintf(stdout,''')
    if s.count("c R12_CHOICE")!=1:raise RuntimeError("Missing R12 trace")
    if s.count("c R6_TRACE")!=1:raise RuntimeError("Lost R11/R6 trace")
    return s

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--kissat-root",required=True,type=Path)
    args=ap.parse_args()
    target=args.kissat_root/"src"/"search.c"
    result=patch(target.read_text())
    target.write_text(result)
    print("R12_INPROCESS_PATCH_OK",PIN,hashlib.sha256(result.encode()).hexdigest(),flush=True)
