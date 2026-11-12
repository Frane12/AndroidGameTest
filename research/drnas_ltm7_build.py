#!/usr/bin/env python3
"""LTM7: optional, fail-safe live GF(2) yield gate. Never changes core CDCL."""
from pathlib import Path
h=Path("mre_atlas23/drnas_native_core_c.hpp")
s=h.read_text()
def one(a,b):
 global s
 assert s.count(a)==1,("LTM7 header drift",a[:90],s.count(a))
 s=s.replace(a,b,1)
one("    bool gf2_enabled_=false, gf2_budget_exhausted_=false;",
"""    bool gf2_enabled_=false, gf2_budget_exhausted_=false;
    bool ltm7_selective_=false;
    uint64_t ltm7_last_useful_check_=0,ltm7_gate_off_=0;""")
one("        while(xor_head_<xor_pending_.size()){\n            if((stats_.xor_checks&1023u)==0 && timed_out())return -2;",
"""        while(xor_head_<xor_pending_.size()){
            if((stats_.xor_checks&1023u)==0 && timed_out())return -2;
            // Conservative extra propagator abstention. All existing source
            // clauses and permanent XOR reason clauses remain in CDCL.
            if(ltm7_selective_ &&
               stats_.xor_checks-ltm7_last_useful_check_>=1024){
                gf2_budget_exhausted_=true;
                xor_pending_.clear();xor_head_=0;
                ++ltm7_gate_off_;
                return -1;
            }""")
one("                ++stats_.xor_conflicts;++stats_.xor_reasons;\n                return cid;",
"""                ++stats_.xor_conflicts;++stats_.xor_reasons;
                if(ltm7_selective_)ltm7_last_useful_check_=stats_.xor_checks;
                return cid;""")
one("            ++stats_.xor_reasons;\n            return -3;",
"""            ++stats_.xor_reasons;
            if(ltm7_selective_)ltm7_last_useful_check_=stats_.xor_checks;
            return -3;""")
one("    void enable_gf2_from_original(const CNF& cnf) {",
"""    void ltm7_enable_selective(){
        require(gf2_enabled_,"LTM7 must be enabled after certified GF2");
        ltm7_selective_=true;
        ltm7_last_useful_check_=stats_.xor_checks;
    }
    uint64_t ltm7_gate_off() const{return ltm7_gate_off_;}
    bool ltm7_selective() const{return ltm7_selective_;}
    void enable_gf2_from_original(const CNF& cnf) {""")
h.write_text(s)
p=Path("mre_atlas23/native.cpp");t=p.read_text()
anchor='mode=="LTM6_LIVE"'
assert t.count(anchor)>=5,("LTM6 dispatch drift",t.count(anchor))
t=t.replace(anchor,'(mode=="LTM6_LIVE"||mode=="LTM7_SELECT")')
needle='     solver.enable_gf2_from_original(orig);'
assert t.count(needle)==1
t=t.replace(needle,needle+'\n   if(mode=="LTM7_SELECT" && ltm6_screen.enabled)solver.ltm7_enable_selective();',1)
needle='           <<" SAT_original_verified="<<int(status==10)'
assert t.count(needle)==1
t=t.replace(needle,'''           <<" ltm7_selective="<<int(solver.ltm7_selective())
           <<" ltm7_gate_off="<<solver.ltm7_gate_off()
'''+needle,1)
assert t.count('mode=="LTM7_SELECT"')>=6
p.write_text(t)
print("LTM7_PATCH_PASS certified_GF2_only=true fail_safe_abstain=true controls_unchanged=true",flush=True)
