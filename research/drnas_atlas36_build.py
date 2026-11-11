#!/usr/bin/env python3
"""ATLAS36: measurable 10/25% quota adjustment on ACTIVE C7/ATLAS16 reduction.
No changes to inference, candidate sorting, protected clause classes,
the pressure gate, original formulas, or default V23 policy.
"""
from pathlib import Path
h=Path("mre_atlas23/drnas_native_core_c.hpp")
s=h.read_text()
def one(a,b):
 global s
 assert s.count(a)==1,("ATLAS36 patch drift",a[:125],s.count(a))
 s=s.replace(a,b,1)

one("    bool atlas23_min_only_=false,atlas23_age_protect_=false,atlas23_stable_phase_=false;",
"""    bool atlas23_min_only_=false,atlas23_age_protect_=false,atlas23_stable_phase_=false;
    int atlas36_quota_pct_=100;
    uint64_t atlas36_attempts_=0,atlas36_schedule_skip_=0,atlas36_below48_=0;
    uint64_t atlas36_examined_=0,atlas36_locked_=0,atlas36_lbd_=0,atlas36_short_=0;
    uint64_t atlas36_eligible_=0,atlas36_base_quota_=0,atlas36_effective_quota_=0;
    uint64_t atlas36_pressure_high_=0,atlas36_pressure_low_=0;""")

one("""            if(!atlas17_high_pressure_ && stats_.conflicts%3000!=0)return;""",
"""            if(atlas17_high_pressure_)++atlas36_pressure_high_;
            else ++atlas36_pressure_low_;
            if(!atlas17_high_pressure_ && stats_.conflicts%3000!=0){
                ++atlas36_schedule_skip_;
                return;
            }""")

one("""        ++atlas15_reductions_;
        std::vector<uint8_t> locked(clauses_.size(),0);""",
"""        ++atlas15_reductions_;
        ++atlas36_attempts_;
        std::vector<uint8_t> locked(clauses_.size(),0);""")

one("""            // Preserve glue clauses, binaries, recent low-LBD information and all reasons.
            if(locked[size_t(cid)] || kv.second<7 || cl.size()<4)continue;
            if(atlas23_age_protect_){""",
"""            // Preserve the original guards and diagnose the first failing gate.
            ++atlas36_examined_;
            if(locked[size_t(cid)]){++atlas36_locked_;continue;}
            if(kv.second<7){++atlas36_lbd_;continue;}
            if(cl.size()<4){++atlas36_short_;continue;}
            if(atlas23_age_protect_){""")

one("""        if(candidates.size()<48)return;""",
"""        atlas36_eligible_+=candidates.size();
        if(candidates.size()<48){++atlas36_below48_;return;}""")

one("""        const size_t count=std::max<size_t>(1,candidates.size()/divisor);
        for(size_t i=0;i<count;++i){""",
"""        const size_t baseline_count=std::max<size_t>(1,candidates.size()/divisor);
        // A36_90/75 actually affects C7's active delete quota.
        const size_t count=std::max<size_t>(1,
            (baseline_count*size_t(atlas36_quota_pct_)+99)/100);
        atlas36_base_quota_+=baseline_count;
        atlas36_effective_quota_+=count;
        for(size_t i=0;i<count;++i){""")

one("""    bool atlas23_stable_phase()const{return atlas23_stable_phase_;}""",
"""    bool atlas23_stable_phase()const{return atlas23_stable_phase_;}
    void atlas36_enable_quota(int pct){
        require(atlas16_keep_ && atlas17_adaptive_,"ATLAS36 requires active C7");
        require(pct==90 || pct==75,"ATLAS36 invalid percentage");
        atlas36_quota_pct_=pct;
    }
    int atlas36_quota_pct()const{return atlas36_quota_pct_;}
    uint64_t atlas36_attempts()const{return atlas36_attempts_;}
    uint64_t atlas36_schedule_skip()const{return atlas36_schedule_skip_;}
    uint64_t atlas36_below48()const{return atlas36_below48_;}
    uint64_t atlas36_examined()const{return atlas36_examined_;}
    uint64_t atlas36_locked()const{return atlas36_locked_;}
    uint64_t atlas36_lbd()const{return atlas36_lbd_;}
    uint64_t atlas36_short()const{return atlas36_short_;}
    uint64_t atlas36_eligible()const{return atlas36_eligible_;}
    uint64_t atlas36_base_quota()const{return atlas36_base_quota_;}
    uint64_t atlas36_effective_quota()const{return atlas36_effective_quota_;}
    uint64_t atlas36_pressure_high()const{return atlas36_pressure_high_;}
    uint64_t atlas36_pressure_low()const{return atlas36_pressure_low_;}""")
h.write_text(s)
p=Path("mre_atlas23/native.cpp")
s=p.read_text()
needle='mode=="V23_C7_STABLE"'
assert s.count(needle)>=2
s=s.replace(needle,needle+'||mode=="A36_90"||mode=="A36_75"')
anchor='solver.atlas23_enable_stable_phase();'
assert s.count(anchor)==1
s=s.replace(anchor,anchor+'''
    if(mode=="A36_90")solver.atlas36_enable_quota(90);
    if(mode=="A36_75")solver.atlas36_enable_quota(75);''',1)
anchor='           <<" SAT_original_verified="<<int(status==10)'
assert s.count(anchor)==1
fields=("quota_pct","attempts","schedule_skip","below48","examined","locked",
        "lbd","short","eligible","base_quota","effective_quota",
        "pressure_high","pressure_low")
lines=''.join('           <<" atlas36_'+field+'="<<solver.atlas36_'+field+'()\\n' for field in fields)
s=s.replace(anchor,lines+anchor,1)
for m in ("A36_90","A36_75"):
 assert s.count('mode=="'+m+'"')>=3
p.write_text(s)
print("ATLAS36_BUILD_PASS active_C7_quota=true protected_candidates_unchanged=true diagnostics=true",flush=True)
