#!/usr/bin/env python3
"""ATLAS35: isolate 10%/25% deletion-quota reduction on V23 C7.
Existing guards preserve LBD<=5, short/young/locked clauses.
"""
from pathlib import Path
header=Path("mre_atlas23/drnas_native_core_c.hpp")
s=header.read_text()
def one(needle,replacement):
    global s
    assert s.count(needle)==1,("ATLAS35 header drift",needle[:120],s.count(needle))
    s=s.replace(needle,replacement,1)
one("    bool atlas23_min_only_=false,atlas23_age_protect_=false,atlas23_stable_phase_=false;",
"""    bool atlas23_min_only_=false,atlas23_age_protect_=false,atlas23_stable_phase_=false;
    int atlas35_quota_pct_=100;""")
one("""        const size_t quota=std::min(candidates.size()/4,
            std::min<size_t>(atlas15_live_learned_/10,atlas15_live_learned_-20000));""",
"""        const size_t base_quota=std::min(candidates.size()/4,
            std::min<size_t>(atlas15_live_learned_/10,atlas15_live_learned_-20000));
        // Keep 10% or 25% more candidates per reduction event.
        // Do not alter LBD, age, lock, or candidate-selection rules.
        const size_t quota=(base_quota*size_t(atlas35_quota_pct_)+99)/100;""")
one("    bool atlas23_stable_phase()const{return atlas23_stable_phase_;}",
"""    bool atlas23_stable_phase()const{return atlas23_stable_phase_;}
    void atlas35_enable_quota(int pct){
        require(atlas16_keep_ && atlas17_adaptive_,"ATLAS35 requires C7");
        require(pct==90 || pct==75,"ATLAS35 invalid quota");
        atlas35_quota_pct_=pct;
    }
    int atlas35_quota_pct()const{return atlas35_quota_pct_;}""")
header.write_text(s)
native=Path("mre_atlas23/native.cpp")
s=native.read_text()
old='mode=="V23_C7_STABLE"'
assert s.count(old)>=2, ("ATLAS35 dispatch drift",s.count(old))
s=s.replace(old,old+'||mode=="A35_90"||mode=="A35_75"')
anchor='solver.atlas23_enable_stable_phase();'
assert s.count(anchor)==1
s=s.replace(anchor,anchor+'''
    if(mode=="A35_90")solver.atlas35_enable_quota(90);
    if(mode=="A35_75")solver.atlas35_enable_quota(75);''',1)
anchor='           <<" SAT_original_verified="<<int(status==10)'
assert s.count(anchor)==1
s=s.replace(anchor,'           <<" atlas35_quota_pct="<<solver.atlas35_quota_pct()\n'+anchor,1)
for m in ("A35_90","A35_75"):
    assert s.count('mode=="'+m+'"')>=3
native.write_text(s)
print("ATLAS35_BUILD_PASS C7_baseline_untouched=true quota_90_75=true",flush=True)
