#!/usr/bin/env python3
"""R42: cap ONLY the R40 early-resume phase intervention to 32/128/512.
Applies after frozen R40 and read-only R41 tracing. Solver/CDCL untouched.
All cap modes use policy=v91_rescue, same 256-conflict prefix and frozen gate.
"""
from pathlib import Path
import argparse,hashlib
p=argparse.ArgumentParser()
p.add_argument("--source",required=True);p.add_argument("--out",required=True)
a=p.parse_args();s=Path(a.source).read_text()
def patch(old,new):
 global s
 n=s.count(old)
 if n!=1:raise RuntimeError(f"R42 anchor {n} !=1: {old[:100]}")
 s=s.replace(old,new,1)
 print("R42_PATCH_ANCHOR_PASS",old[:68],flush=True)
patch('''static Audit ablation(const Formula &f,const std::string &policy,
                      bool use_observer,uint32_t seed,bool enable_hints=true) {''',
'''static Audit ablation(const Formula &f,const std::string &policy,
                      bool use_observer,uint32_t seed,bool enable_hints=true,
                      int r42_max_rescue_hints=-1) {''')
patch('''    int hints=0,active_pre=0,active_256=0,threshold=0;''',
'''    int hints=0,active_pre=0,active_256=0,threshold=0;
    int r42_actual_hints=0;''')
patch('''                if(choose && !h.literals.empty()) {
                    for(const int lit:h.literals)solver.phase(lit);
                    a.v91_phase_applied=true;''',
'''                if(choose && !h.literals.empty()) {
                    // R42 dose response: first N frozen hint candidates only.
                    // The R40 gate and original first 256 conflicts are unchanged.
                    for(const int lit:h.literals) {
                        if(r42_max_rescue_hints>=0 &&
                           a.r42_actual_hints>=r42_max_rescue_hints)break;
                        solver.phase(lit);
                        ++a.r42_actual_hints;
                    }
                    a.v91_phase_applied=a.r42_actual_hints>0;''')
patch('''        } else if(mode=="v91_rescue") {
            a=ablation(f,"v91_rescue",false,seed,true);
        } else if(mode=="v91_force_fallback") {''',
'''        } else if(mode=="v91_rescue") {
            a=ablation(f,"v91_rescue",false,seed,true);
        } else if(mode=="v91_cap32") {
            a=ablation(f,"v91_rescue",false,seed,true,32);
        } else if(mode=="v91_cap128") {
            a=ablation(f,"v91_rescue",false,seed,true,128);
        } else if(mode=="v91_cap512") {
            a=ablation(f,"v91_rescue",false,seed,true,512);
        } else if(mode=="v91_force_fallback") {''')
patch('''                      << "\\thints=" << a.hints
                      << std::endl;''',
'''                      << "\\thints=" << a.hints
                      << "\\tactual_hints=" << a.r42_actual_hints
                      << std::endl;''')
out=Path(a.out);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(s)
print("R42_PATCH_PASS",hashlib.sha256(s.encode()).hexdigest(),flush=True)
