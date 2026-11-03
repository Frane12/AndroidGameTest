#!/usr/bin/env python3
"""R44 frozen early-checkpoint 0/16/32 dose selector. NO data fitting here.

Empirical *hypothesis* frozen before R44 official holdout, deliberately cautious:
  start with original v9.1 quality gate (L>=20, LBD2>=6%, P/C>=32)
  must have v7.6 early-resume (no extended continuation)
  if LBD2 share <= 12% AND P/C <= 384: 32 phase hints
  else if LBD2 share <=20% AND P/C <= 512: 16 hints
  else abstain (0 hints).
No formula ID / SAT labels / known timing in logic. The thresholds were motivated
by earlier R41-R43 data and are NOT independent mathematical discoveries.
"""
import argparse,hashlib
from pathlib import Path
p=argparse.ArgumentParser()
p.add_argument("--source",required=True);p.add_argument("--out",required=True)
a=p.parse_args()
s=Path(a.source).read_text()
def once(old,new):
 global s
 n=s.count(old)
 if n!=1:raise RuntimeError(f"R44 patch anchor {n}: {old[:100]}")
 s=s.replace(old,new,1)
 print("R44_PATCH_ANCHOR_PASS",old[:75],flush=True)
once('''                const bool choose=policy=="v91_force_fallback" ||
                                  a.v91_gate_quality;
                if(choose && !h.literals.empty()) {''',
'''                bool choose=policy=="v91_force_fallback" ||
                                  a.v91_gate_quality;
                // Dose selector is ONLY enabled by v91_adaptive mode.
                // Both other arms preserve the exact frozen R42 behavior.
                int effective_cap=r42_max_rescue_hints;
                if(r42_max_rescue_hints==-2) {
                    choose=false;
                    const int64_t L=a.v90_learned_256;
                    const int64_t C=a.v90_conflicts_256;
                    const int64_t P=a.v90_props_256;
                    const int64_t Q=a.v90_lbd2_256;
                    if(a.v91_gate_quality && L>0 && C>0) {
                        if(100*Q<=12*L && P<=384*C) {
                            choose=true;
                            effective_cap=32;
                        } else if(100*Q<=20*L && P<=512*C) {
                            choose=true;
                            effective_cap=16;
                        }
                    }
                }
                if(choose && !h.literals.empty()) {''')
once('''                        if(r42_max_rescue_hints>=0 &&
                           a.r42_actual_hints>=r42_max_rescue_hints)break;''',
'''                        if(effective_cap>=0 &&
                           a.r42_actual_hints>=effective_cap)break;''')
once('''                    a.gate_reason=choose?"r40_no_hint_candidates":
                        "r40_quality_reject_fallback";''',
'''                    a.gate_reason=(r42_max_rescue_hints==-2)?
                        "r44_adaptive_abstain":
                        (choose?"r40_no_hint_candidates":
                         "r40_quality_reject_fallback");''')
once('''        } else if(mode=="v91_cap32") {
            a=ablation(f,"v91_rescue",false,seed,true,32);''',
'''        } else if(mode=="v91_cap32") {
            a=ablation(f,"v91_rescue",false,seed,true,32);
        } else if(mode=="v91_adaptive") {
            a=ablation(f,"v91_rescue",false,seed,true,-2);''')
out=Path(a.out);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(s)
print("R44_NATIVE_PATCH_PASS",hashlib.sha256(s.encode()).hexdigest(),flush=True)
