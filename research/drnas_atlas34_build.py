#!/usr/bin/env python3
"""ATLAS34: two isolated learned-clause retention policies on native C7."""
from pathlib import Path
p=Path("mre_atlas23/drnas_native_core_c.hpp")
s=p.read_text()
def one(a,b):
 global s
 assert s.count(a)==1,(a[:100],s.count(a))
 s=s.replace(a,b,1)
one("    bool atlas23_min_only_=false,atlas23_age_protect_=false,atlas23_stable_phase_=false;",
"""    bool atlas23_min_only_=false,atlas23_age_protect_=false,atlas23_stable_phase_=false;
    int atlas34_retention_=0;""")
one("        if(atlas15_live_learned_<20000)return;",
"""        if(atlas15_live_learned_<(atlas34_retention_?30000:20000))return;""")
one("            if(atlas23_age_protect_){",
"""            if(atlas34_retention_){
                const auto born=atlas15_born_.find(cid);
                const uint64_t age=(born!=atlas15_born_.end() &&
                    stats_.conflicts>=born->second)?
                    stats_.conflicts-born->second:0;
                // Keep young clauses and stronger LBDs. Adaptive mode
                // protects more aggressively during high LBD pressure.
                const int min_age=atlas34_retention_==1?40000:
                    (atlas15_short_lbd_>atlas15_long_lbd_*1.08?80000:30000);
                const int max_lbd=atlas34_retention_==1?8:
                    (atlas15_short_lbd_>atlas15_long_lbd_*1.08?10:7);
                if(age<uint64_t(min_age)||kv.second<=max_lbd)continue;
            }
            if(atlas23_age_protect_){""")
one("        const size_t quota=std::min(candidates.size()/4,",
"""        const size_t quota=std::min(candidates.size()/
            size_t(atlas34_retention_==1?8:atlas34_retention_==2?12:4),""")
one("    bool atlas23_stable_phase()const{return atlas23_stable_phase_;}",
"""    bool atlas23_stable_phase()const{return atlas23_stable_phase_;}
    void atlas34_enable_retention(int policy){
        require(atlas16_keep_ && atlas17_adaptive_,"retention requires C7");
        require(policy==1||policy==2,"invalid retention policy");
        atlas34_retention_=policy;
    }
    int atlas34_retention()const{return atlas34_retention_;}""")
p.write_text(s)
p=Path("mre_atlas23/native.cpp")
s=p.read_text()
assert s.count('mode=="V23_C7_STABLE"')>=2
s=s.replace('mode=="V23_C7_STABLE"','mode=="V23_C7_STABLE"||mode=="A34_KEEP"||mode=="A34_ADAPT"')
anchor='solver.atlas23_enable_stable_phase();'
assert s.count(anchor)==1
s=s.replace(anchor,anchor+'''
    if(mode=="A34_KEEP")solver.atlas34_enable_retention(1);
    if(mode=="A34_ADAPT")solver.atlas34_enable_retention(2);''')
anchor='           <<" SAT_original_verified="<<int(status==10)'
assert s.count(anchor)==1
s=s.replace(anchor,'           <<" atlas34_retention="<<solver.atlas34_retention()\n'+anchor)
p.write_text(s)
print("ATLAS34_BUILD_PASS conservative_and_adaptive_retention=true")
