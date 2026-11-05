#!/usr/bin/env python3
"""R17: conservative dual-model agreement + bounded training-feature novelty.
This is an *abstention heuristic*, not calibrated uncertainty or a new solver.
Patch only pinned Kissat read-only native R16 inference, never V15.3.1.
"""
from pathlib import Path
import argparse, hashlib, sys
sys.path.insert(0,"experiments/drnas_v16")
import patch_r16_live_ridge as r16

UPSTREAM_PIN=r16.UPSTREAM_PIN
MODES={"r17_agree50":(.25,.05,2.50),"r17_guarded50":(.40,.10,2.00)}
def once(s,a,b):
    k=s.count(a)
    if k!=1:raise RuntimeError("R17_REFUSE_ANCHOR "+str(k)+" "+a[:75])
    return s.replace(a,b,1)

def patch(src):
    s=r16.patch(src)
    s=once(s,
'''  const bool r16_snapshot50=!strcmp(drnas_mode,"r16_snapshot50");
  const bool r16_active=r16_live50 || r16_live50_strict || r16_snapshot50;''',
'''  const bool r16_snapshot50=!strcmp(drnas_mode,"r16_snapshot50");
  const bool r17_agree50=!strcmp(drnas_mode,"r17_agree50");
  const bool r17_guarded50=!strcmp(drnas_mode,"r17_guarded50");
  const bool r17_active=r17_agree50 || r17_guarded50;
  const bool r16_active=r16_live50 || r16_live50_strict || r16_snapshot50 || r17_active;''')
    s=once(s,
'const double threshold=r16_live50_strict?0.40:0.25;',
'const double threshold=(r16_live50_strict || r17_guarded50)?0.40:0.25;')
    s=once(s,
'''                double score=0.0;
                bool selected=false;''',
'''                double score=0.0,r17_snapshot_score=0.0,r17_novelty=0.0;
                bool selected=false;''')
    s=once(s,
'''                  selected=r13_n>=220 && isfinite(score) && score>threshold;
                  if (selected) drnas_target=2048;''',
'''                  if (r17_active) {
                    r17_snapshot_score=r16_s_coef[0];
                    for (int j=0;j<10;j++) {
                      double z=(x[j]-r16_s_mean[j])/r16_s_sd[j];
                      if(z>3.0)z=3.0;
                      if(z< -3.0)z= -3.0;
                      r17_snapshot_score+=r16_s_coef[j+1]*z;
                    }
                    // Explicitly selected six pre-action measurements; never
                    // predict a calibrated error probability from this proxy.
                    static const int guard_indices[6]={4,5,10,12,15,17};
                    for(int j=0;j<6;j++){
                      const int k=guard_indices[j];
                      const double z=fabs((x[k]-r16_t_mean[k])/r16_t_sd[k]);
                      if(z>r17_novelty)r17_novelty=z;
                    }
                  }
                  const bool agreement=!r17_active ||
                      (isfinite(r17_snapshot_score) &&
                       r17_snapshot_score>(r17_guarded50?0.10:0.05) &&
                       isfinite(r17_novelty) &&
                       r17_novelty<=(r17_guarded50?2.00:2.50));
                  selected=r13_n>=220 && isfinite(score) &&
                      score>threshold && agreement;
                  if (selected) drnas_target=2048;''')
    s=once(s,
'''                  " score=%.12f threshold=%.12f selected=%d"
                  " model=%s target=%" PRIu64 "\\n",
                  drnas_seen,(int)ready,r13_n,r12_degree_cv,
                  r16_degree_gini,r16_polarity,score,threshold,(int)selected,
                  r16_snapshot50?"snapshot":"trajectory",drnas_target);''',
'''                  " score=%.12f threshold=%.12f selected=%d"
                  " model=%s target=%" PRIu64
                  " r17_snapshot=%.12f r17_novelty=%.12f r17_active=%d\\n",
                  drnas_seen,(int)ready,r13_n,r12_degree_cv,
                  r16_degree_gini,r16_polarity,score,threshold,(int)selected,
                  r16_snapshot50?"snapshot":"trajectory",drnas_target,
                  r17_snapshot_score,r17_novelty,(int)r17_active);''')
    for name in ('r17_agree50','r17_guarded50','r17_snapshot','r17_novelty','R16_DECISION'):
        if name not in s:raise RuntimeError("R17_NATIVE_MISSING "+name)
    return s

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--kissat-root",type=Path,required=True)
    a=p.parse_args()
    target=a.kissat_root/"src"/"search.c"
    source=patch(target.read_text())
    target.write_text(source)
    print("R17_PATCH_NATIVE_DONE",UPSTREAM_PIN,hashlib.sha256(source.encode()).hexdigest(),flush=True)
