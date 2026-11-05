#!/usr/bin/env python3
"""Frozen R14 in-process Kissat intervention add-on.
Uses the same original Kissat pin and existing in-process 2048-conflict
restart option mutation. R13 and V15.3.1 are untouched.
"""
from pathlib import Path
import argparse,hashlib
from patch_r13_rescue import patch as patch_r13

UPSTREAM_PIN="8af8e56f174b778aef3aa45af9f739b2a5f492c2"

def once(s,a,b):
 n=s.count(a)
 if n!=1:raise RuntimeError(f"R14_PATCH_ANCHOR mismatch {n} for: {a[:100]}")
 return s.replace(a,b,1)

def patch(source):
 s=patch_r13(source)
 s=once(s,
  '  const bool r13_inverse50=!strcmp(drnas_mode,"r13_inverse50");',
  '''  const bool r13_inverse50=!strcmp(drnas_mode,"r13_inverse50");
  const bool r14_complement50=!strcmp(drnas_mode,"r14_complement50");
  const bool r14_dual50=!strcmp(drnas_mode,"r14_dual50");
  const bool r14_dual25=!strcmp(drnas_mode,"r14_dual25");
  const bool r14_guarded50=!strcmp(drnas_mode,"r14_guarded50");
  const bool r14_active=r14_complement50 || r14_dual50 ||
                        r14_dual25 || r14_guarded50;''')
 s=once(s,
  '  if (r13_active) {\n    const char *n_text=getenv("DRNAS_R13_N");',
  '  if (r13_active || r14_active) {\n    const char *n_text=getenv("DRNAS_R13_N");')
 s=once(s,
  '  if (r12_active || r13_active) {',
  '  if (r12_active || r13_active || r14_active) {')
 s=once(s,
  '''          fprintf(stdout,
           "c DRNAS_V177_EARLY r=%.9f d=%.9f p=%.9f g=%.9f l=%.9f"''',
  '''          if (r14_active) {
            const bool high_glue =
              r13_n>=220 && drnas_p>0.0 &&
              drnas_p<46.5 && drnas_g>=0.95;
            const bool complement =
              r13_n==240 && r12_degree_cv>=0.285 &&
              drnas_p>=43.0 && drnas_g<0.95;
            const bool guarded_complement =
              complement && drnas_p>=45.0;
            const bool r14_choice =
              r14_complement50 ? complement :
              r14_dual50 ? (high_glue || complement) :
              r14_dual25 ? (high_glue || complement) :
                             (high_glue || guarded_complement);
            if (r14_choice) drnas_target=2048;
            fprintf(stdout,
              "c R14_CHOICE conflict=%" PRIu64
              " n=%u cv=%.9f p=%.9f g=%.9f"
              " rescue=%d complement=%d guarded=%d"
              " selected=%d interval=%d target=%" PRIu64 "\\n",
              drnas_seen,r13_n,r12_degree_cv,drnas_p,drnas_g,
              (int)high_glue,(int)complement,(int)guarded_complement,
              (int)r14_choice,r14_dual25?25:50,drnas_target);
            fflush(stdout);
          }
          fprintf(stdout,
           "c DRNAS_V177_EARLY r=%.9f d=%.9f p=%.9f g=%.9f l=%.9f"''')
 s=once(s,
  'kissat_set_option(solver,"restartint",r11_mode ? r11_interval : (r13_active && !r13_rescue25 ? 50 : 25));',
  'kissat_set_option(solver,"restartint",r11_mode ? r11_interval : ((r14_active && !r14_dual25) || (r13_active && !r13_rescue25) ? 50 : 25));')
 for marker in ("c R14_CHOICE","c R13_CHOICE","c R12_CHOICE","c R6_TRACE","DRNAS_V177_SWITCH"):
  if s.count(marker)!=1:raise RuntimeError("R14 expected single telemetry marker: "+marker)
 return s

if __name__=="__main__":
 p=argparse.ArgumentParser()
 p.add_argument("--kissat-root",required=True,type=Path)
 args=p.parse_args()
 f=args.kissat_root/"src"/"search.c"
 result=patch(f.read_text())
 f.write_text(result)
 print("R14_COMPILED_SOURCE_PATCH",UPSTREAM_PIN,
       hashlib.sha256(result.encode()).hexdigest(),flush=True)
