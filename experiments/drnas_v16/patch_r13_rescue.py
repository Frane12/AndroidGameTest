#!/usr/bin/env python3
"""R13 pinned in-process Kissat gate. R12 and V15.3.1 remain byte-identical.
New experimental modes only schedule existing native restartint switch at 2048.
"""
from pathlib import Path
import argparse, hashlib
from patch_r12_hybrid import patch as patch_r12

UPSTREAM_PIN="8af8e56f174b778aef3aa45af9f739b2a5f492c2"

def once(s,a,b):
    n=s.count(a)
    if n!=1:
        raise RuntimeError("R13_ANCHOR_MISMATCH count="+str(n)+" expected="+a[:100])
    return s.replace(a,b,1)

def patch(source):
    s=patch_r12(source)
    s=once(s,
      '  const bool r12_inverse=!strcmp(drnas_mode,"r12_inverse");',
      '''  const bool r12_inverse=!strcmp(drnas_mode,"r12_inverse");
  const bool r13_rescue50=!strcmp(drnas_mode,"r13_rescue50");
  const bool r13_rescue25=!strcmp(drnas_mode,"r13_rescue25");
  const bool r13_struct50=!strcmp(drnas_mode,"r13_struct50");
  const bool r13_inverse50=!strcmp(drnas_mode,"r13_inverse50");
  const bool r13_active=r13_rescue50 || r13_rescue25 ||
                         r13_struct50 || r13_inverse50;
  unsigned r13_n=0;
  if (r13_active) {
    const char *n_text=getenv("DRNAS_R13_N");
    char *n_end=NULL;
    unsigned long n_value=n_text ? strtoul(n_text,&n_end,10) : 0;
    if (!n_text || !*n_text || !n_end || *n_end ||
        !(n_value==200 || n_value==220 || n_value==240)) {
      fprintf(stderr,"R13_INVALID_VARIABLE_COUNT\\n");exit(78);
    }
    r13_n=(unsigned)n_value;
  }''')
    s=once(s,'  double r12_degree_cv=0.0;\n  if (r12_active) {','  double r12_degree_cv=0.0;\n  if (r12_active || r13_active) {')
    s=once(s,
       '          fprintf(stdout,\n           "c DRNAS_V177_EARLY r=%.9f d=%.9f p=%.9f g=%.9f l=%.9f"',
       '''          if (r13_active) {
            const bool r13_base =
              r13_n>=220 && drnas_p>0.0 && drnas_p<46.5;
            const bool r13_high_glue=(drnas_g>=0.95);
            const bool r13_rescue=r13_base && r13_high_glue;
            const bool r13_choice =
              r13_rescue50 ? r13_rescue :
              r13_rescue25 ? r13_rescue :
              r13_struct50 ? (r13_rescue && r12_degree_cv>=0.27) :
                              (r13_base && !r13_high_glue);
            if (r13_choice) drnas_target=2048;
            fprintf(stdout,
              "c R13_CHOICE conflict=%" PRIu64
              " n=%u cv=%.9f p=%.9f g=%.9f"
              " selected=%d interval=%d target=%" PRIu64 "\\n",
              drnas_seen,r13_n,r12_degree_cv,drnas_p,drnas_g,
              (int)r13_choice,r13_rescue25 ? 25 : 50,drnas_target);
            fflush(stdout);
          }
          fprintf(stdout,
           "c DRNAS_V177_EARLY r=%.9f d=%.9f p=%.9f g=%.9f l=%.9f"''')
    s=once(s,
      'kissat_set_option(solver,"restartint",r11_mode ? r11_interval : 25);',
      'kissat_set_option(solver,"restartint",r11_mode ? r11_interval : (r13_active && !r13_rescue25 ? 50 : 25));')
    for marker in ("c R13_CHOICE","c R12_CHOICE","c R6_TRACE","DRNAS_V177_SWITCH"):
      if s.count(marker)!=1:raise RuntimeError("R13 required marker absent/duplicate: "+marker)
    return s

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--kissat-root",type=Path,required=True)
    a=p.parse_args()
    source=a.kissat_root/"src"/"search.c"
    patched=patch(source.read_text())
    source.write_text(patched)
    print("R13_FROZEN_PINNED_PATCH_OK",UPSTREAM_PIN,
          hashlib.sha256(patched.encode()).hexdigest(),flush=True)
