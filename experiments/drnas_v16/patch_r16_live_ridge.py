#!/usr/bin/env python3
"""R16: faithful R15 frozen ridge50 model in a SINGLE native Kissat solve.

At live conflict 1024, use already-collected checkpoints at 128/256/512/1024
and static CNF features provided before solving. No hindsight, no second solve.
Switch only native restartint=50 at conflict 2048 when a locked risk gate passes.
R15 model JSON and V15.3.1 sources are never modified.
"""
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
from patch_r14_dual import patch as patch_r14

UPSTREAM_PIN="8af8e56f174b778aef3aa45af9f739b2a5f492c2"
MODEL=Path("experiments/drnas_v16/r15-results/current/frozen_trained_models.json")
PROTOCOL=Path("experiments/drnas_v16/r16_frozen_live_protocol.json")
FEATURES=("n_scaled","degree_cv","degree_gini","polarity_imbalance",
          "p512","g512","restarts512","learned512","stable512","reached1024",
          "p128_256","p256_512","p512_1024","p_slope_256_1024","p_curvature",
          "g128","g256","g1024","g_slope_256_1024","g_curvature",
          "restart_rate_256_512","restart_rate_512_1024",
          "learned_rate_256_512","learned_rate_512_1024",
          "decision_rate_512_1024")
SNAPSHOT=FEATURES[:10]
MODES={"r16_live50":.25,"r16_live50_strict":.40,"r16_snapshot50":.25}

def once(s,a,b):
 n=s.count(a)
 if n!=1:raise RuntimeError("R16_PINNED_SOURCE_ANCHOR count="+str(n)+": "+a[:115])
 return s.replace(a,b,1)
def nums(v):
 return "{"+",".join(format(float(x),".17g") for x in v)+"}"
def load():
 c=json.loads(PROTOCOL.read_text())
 model=json.loads(MODEL.read_text())
 if (c["protocol"]!="R16-live-trajectory-ridge50-frozen-20261102-v1"
   or c["trained_model_git_blob_sha"]!="d005747f177008172b49cef5f0b8a6f29c3ffc46"
   or c["safety_design"]["allowed_thresholds"]!=MODES
   or model["training_fold"]!="random3_development"
   or model["n_eligible_training"]!=59
   or model["threshold"]!=0.12):
  raise RuntimeError("R16_FROZEN_MODEL_OR_PROTOCOL_MISMATCH")
 for mode,names in (("trajectory",FEATURES),("snapshot",SNAPSHOT)):
  m=model["models"][mode]["r11_2048_50"]
  if (m["feature_names"]!=list(names) or m["n_train"]!=59 or
      m["ridge_lambda"]!=30 or
      len(m["coefficients"])!=len(names)+1):
   raise RuntimeError("R16_MODEL_DIMENSION_OR_FEATURE_ORDER_MISMATCH")
 return c,model

def patch(src):
 cfg,model=load()
 s=patch_r14(src)
 t=model["models"]["trajectory"]["r11_2048_50"]
 a=model["models"]["snapshot"]["r11_2048_50"]
 decl='''  const bool r16_live50=!strcmp(drnas_mode,"r16_live50");
  const bool r16_live50_strict=!strcmp(drnas_mode,"r16_live50_strict");
  const bool r16_snapshot50=!strcmp(drnas_mode,"r16_snapshot50");
  const bool r16_active=r16_live50 || r16_live50_strict || r16_snapshot50;
  double r16_degree_gini=0.0, r16_polarity=0.0;
  if (r16_active) {
    const char *g=getenv("DRNAS_R16_GINI"), *p=getenv("DRNAS_R16_POLARITY");
    char *e1=NULL,*e2=NULL;
    if (!g || !p || !*g || !*p) {
      fprintf(stderr,"R16_STATIC_FEATURES_MISSING\\n");exit(78);
    }
    r16_degree_gini=strtod(g,&e1);
    r16_polarity=strtod(p,&e2);
    if (!e1 || *e1 || !e2 || *e2 ||
        !(r16_degree_gini>=0.0 && r16_degree_gini<=1.0) ||
        !(r16_polarity>=0.0 && r16_polarity<=1.0)) {
      fprintf(stderr,"R16_STATIC_FEATURES_INVALID\\n");exit(78);
    }
  }
'''
 s=once(s,
  '  const bool r14_active=r14_complement50 || r14_dual50 ||\n                        r14_dual25 || r14_guarded50;',
  '  const bool r14_active=r14_complement50 || r14_dual50 ||\n                        r14_dual25 || r14_guarded50;\n'+decl.rstrip())
 s=once(s,'  if (r13_active || r14_active) {\n    const char *n_text=getenv("DRNAS_R13_N");',
           '  if (r13_active || r14_active || r16_active) {\n    const char *n_text=getenv("DRNAS_R13_N");')
 s=once(s,'  if (r12_active || r13_active || r14_active) {',
           '  if (r12_active || r13_active || r14_active || r16_active) {')
 static_models=f'''
  static const double r16_t_mean[25]={nums(t["mu"])};
  static const double r16_t_sd[25]={nums(t["sd"])};
  static const double r16_t_coef[26]={nums(t["coefficients"])};
  static const double r16_s_mean[10]={nums(a["mu"])};
  static const double r16_s_sd[10]={nums(a["sd"])};
  static const double r16_s_coef[11]={nums(a["coefficients"])};
  const uint64_t r16_landmarks[4]={{128,256,512,1024}};
  uint64_t r16_cp_conflicts[4]={{0}},r16_cp_props[4]={{0}};
  uint64_t r16_cp_restarts[4]={{0}},r16_cp_learned[4]={{0}};
  uint64_t r16_cp_decisions[4]={{0}};
  double r16_cp_glue[4]={{0.0}};
  int r16_cp_stable[4]={{0}},r16_cp_ready[4]={{0}};
  double r16_p512=0.0,r16_g512=0.0;
  bool r16_sampled512=false,r16_decided1024=false;
'''
 s=once(s,'  uint64_t r6_base_learned=0;',
           '  uint64_t r6_base_learned=0;'+static_models)
 # At 512 store exactly the early values used by the R15 development model.
 s=once(s,
  '          if (r14_active) {\n            const bool high_glue =',
  '''          if (r16_active) {
            r16_p512=drnas_p;
            r16_g512=drnas_g;
            r16_sampled512=true;
          }
          if (r14_active) {
            const bool high_glue =''')
 inference='''
            if (r16_active) {
              const uint64_t r16_mark=r6_marks[r6_checkpoint_index];
              for (int i=0;i<4;i++) {
                if (r16_mark!=r16_landmarks[i]) continue;
                r16_cp_ready[i]=1;
                r16_cp_conflicts[i]=drnas_seen;
                r16_cp_props[i]=solver->statistics.propagations-r6_base_props;
                r16_cp_restarts[i]=solver->statistics.restarts-r6_base_restarts;
                r16_cp_decisions[i]=DECISIONS-r6_base_decisions;
                r16_cp_learned[i]=solver->statistics.clauses_learned-r6_base_learned;
                r16_cp_glue[i]=AVERAGE(fast_glue)/
                     (AVERAGE(slow_glue)>1e-9 ? AVERAGE(slow_glue):1e-9);
                r16_cp_stable[i]=(int)solver->stable;
              }
              if (!r16_decided1024 && r16_mark==1024) {
                r16_decided1024=true;
                const bool ready=r16_sampled512 &&
                    r16_cp_ready[0] && r16_cp_ready[1] &&
                    r16_cp_ready[2] && r16_cp_ready[3];
                const double threshold=r16_live50_strict?0.40:0.25;
                double score=0.0;
                bool selected=false;
                if (ready) {
                  double x[25]={0.0};
                  double prop12=(double)(r16_cp_props[1]-r16_cp_props[0])/
                      (double)(r16_cp_conflicts[1]-r16_cp_conflicts[0]);
                  double prop23=(double)(r16_cp_props[2]-r16_cp_props[1])/
                      (double)(r16_cp_conflicts[2]-r16_cp_conflicts[1]);
                  double prop34=(double)(r16_cp_props[3]-r16_cp_props[2])/
                      (double)(r16_cp_conflicts[3]-r16_cp_conflicts[2]);
                  double glue1=r16_cp_glue[0],glue2=r16_cp_glue[1],
                         glue3=r16_cp_glue[2],glue4=r16_cp_glue[3];
                  x[0]=(double)r13_n/240.0;
                  x[1]=r12_degree_cv;
                  x[2]=r16_degree_gini;
                  x[3]=r16_polarity;
                  x[4]=r16_p512;
                  x[5]=r16_g512;
                  x[6]=log1p((double)r16_cp_restarts[2]);
                  x[7]=(double)r16_cp_learned[2]/512.0;
                  x[8]=(double)r16_cp_stable[2];
                  x[9]=1.0;
                  x[10]=prop12;
                  x[11]=prop23;
                  x[12]=prop34;
                  x[13]=prop34-prop23;
                  x[14]=prop34-2.0*prop23+prop12;
                  x[15]=glue1;
                  x[16]=glue2;
                  x[17]=glue4;
                  x[18]=glue4-glue2;
                  x[19]=glue4-2.0*glue3+glue2;
                  x[20]=(double)(r16_cp_restarts[2]-r16_cp_restarts[1])/
                      (double)(r16_cp_conflicts[2]-r16_cp_conflicts[1]);
                  x[21]=(double)(r16_cp_restarts[3]-r16_cp_restarts[2])/
                      (double)(r16_cp_conflicts[3]-r16_cp_conflicts[2]);
                  x[22]=(double)(r16_cp_learned[2]-r16_cp_learned[1])/
                      (double)(r16_cp_conflicts[2]-r16_cp_conflicts[1]);
                  x[23]=(double)(r16_cp_learned[3]-r16_cp_learned[2])/
                      (double)(r16_cp_conflicts[3]-r16_cp_conflicts[2]);
                  x[24]=(double)(r16_cp_decisions[3]-r16_cp_decisions[2])/
                      (double)(r16_cp_conflicts[3]-r16_cp_conflicts[2]);
                  score=r16_snapshot50?r16_s_coef[0]:r16_t_coef[0];
                  const int nfeatures=r16_snapshot50?10:25;
                  for (int j=0;j<nfeatures;j++) {
                    const double mu=r16_snapshot50?r16_s_mean[j]:r16_t_mean[j];
                    const double sd=r16_snapshot50?r16_s_sd[j]:r16_t_sd[j];
                    const double coef=r16_snapshot50?r16_s_coef[j+1]:r16_t_coef[j+1];
                    double z=(x[j]-mu)/sd;
                    if (z>3.0) z=3.0;
                    if (z< -3.0) z= -3.0;
                    score+=coef*z;
                  }
                  selected=r13_n>=220 && isfinite(score) && score>threshold;
                  if (selected) drnas_target=2048;
                }
                fprintf(stdout,
                  "c R16_DECISION conflict=%" PRIu64
                  " complete=%d n=%u cv=%.12f gini=%.12f polarity=%.12f"
                  " score=%.12f threshold=%.12f selected=%d"
                  " model=%s target=%" PRIu64 "\\n",
                  drnas_seen,(int)ready,r13_n,r12_degree_cv,
                  r16_degree_gini,r16_polarity,score,threshold,(int)selected,
                  r16_snapshot50?"snapshot":"trajectory",drnas_target);
                fflush(stdout);
              }
            }
'''
 # Declaration for math is needed for log1p and isfinite.
 s=once(s,'#include <inttypes.h>\n', '#include <inttypes.h>\n#include <math.h>\n')
 s=once(s,'            printf("c R6_TRACE conflict=%" PRIu64', inference+'            printf("c R6_TRACE conflict=%" PRIu64')
 # Reuse only restartint 50. No learned database mutation, no process restart.
 s=once(s,
  'kissat_set_option(solver,"restartint",r11_mode ? r11_interval : ((r14_active && !r14_dual25) || (r13_active && !r13_rescue25) ? 50 : 25));',
  'kissat_set_option(solver,"restartint",r11_mode ? r11_interval : (r16_active || (r14_active && !r14_dual25) || (r13_active && !r13_rescue25) ? 50 : 25));')
 for marker in ("c R16_DECISION","c R14_CHOICE","c R13_CHOICE","c R6_TRACE","DRNAS_V177_SWITCH"):
  if s.count(marker)!=1:raise RuntimeError("R16 EXPECTED SINGLE PINNED MARKER: "+marker)
 return s

if __name__=="__main__":
 ap=argparse.ArgumentParser();ap.add_argument("--kissat-root",required=True,type=Path)
 args=ap.parse_args()
 target=args.kissat_root/"src"/"search.c"
 result=patch(target.read_text())
 target.write_text(result)
 print("R16_LIVE_NATIVE_RIDGE50_PATCHED",UPSTREAM_PIN,
       "r15_model_blob=d005747f177008172b49cef5f0b8a6f29c3ffc46",
       "patched_sha256="+hashlib.sha256(result.encode()).hexdigest(),flush=True)
