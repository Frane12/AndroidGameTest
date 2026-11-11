#!/usr/bin/env python3
"""ATLAS27: conditional reuse of native CDCL reason clauses, pressure-gated.

C7, C26, source GF(2), SAT/UNSAT inference and frozen benchmarks stay unchanged.
Only ATLAS27 arms use live BCP and reason-reuse window gating for C26's score.
"""
from pathlib import Path
root=Path("mre_atlas27");root.mkdir(exist_ok=True)
s=Path("mre_atlas26/drnas_native_core_c.hpp").read_text()
def one(a,b):
 global s
 n=s.count(a)
 assert n==1,("ATLAS27 header drift",a[:110],n)
 s=s.replace(a,b,1)

one("    uint64_t atlas26_compaction_moves_=0;",
"""    uint64_t atlas26_compaction_moves_=0;
    uint64_t atlas27_last_watch_=0,atlas27_last_prop_=0;
    uint64_t atlas27_last_reason_=0,atlas27_last_reused_=0;
    uint64_t atlas27_windows_=0,atlas27_pressure_windows_=0;
    uint64_t atlas27_gate_on_=0,atlas27_gate_off_=0;
    uint64_t atlas27_score_eligible_=0,atlas27_bypassed_=0;
    int atlas27_high_streak_=0,atlas27_low_streak_=0;
    bool atlas27_active_=false;
    void atlas27_sample_pressure(){
        if(atlas26_reuse_mode_<3)return;
        const uint64_t dw=stats_.watch_visits-atlas27_last_watch_;
        const uint64_t dp=stats_.propagations-atlas27_last_prop_;
        const uint64_t du=atlas26_reason_uses_-atlas27_last_reason_;
        const uint64_t dr=atlas26_reused_-atlas27_last_reused_;
        atlas27_last_watch_=stats_.watch_visits;
        atlas27_last_prop_=stats_.propagations;
        atlas27_last_reason_=atlas26_reason_uses_;
        atlas27_last_reused_=atlas26_reused_;
        ++atlas27_windows_;
        // Require meaningful observed BCP cost and repeated actual learned
        // reasons, rather than source category/instance label. Fixed
        // thresholds are hypotheses frozen BEFORE matched evaluation.
        const bool pressure=(dp>=32 && dw>=12*dp && du>=32 &&
                            dr>=16 && dr*4>=du);
        if(pressure){
            ++atlas27_pressure_windows_;
            ++atlas27_high_streak_;
            atlas27_low_streak_=0;
        }else{
            ++atlas27_low_streak_;
            atlas27_high_streak_=0;
        }
        // Hysteresis limits policy oscillation. Never resets CDCL state,
        // reason pointers, learned clauses or branching/restart schedules.
        if(!atlas27_active_ && atlas27_high_streak_>=2){
            atlas27_active_=true;
            ++atlas27_gate_on_;
        }else if(atlas27_active_ && atlas27_low_streak_>=2){
            atlas27_active_=false;
            ++atlas27_gate_off_;
        }
    }""")

one("""    void atlas16_reduce_db(){
        if(stats_.conflicts%1500!=0)return;
        ++atlas15_reductions_;""",
"""    void atlas16_reduce_db(){
        if(stats_.conflicts%1500!=0)return;
        atlas27_sample_pressure();
        ++atlas15_reductions_;""")

one("""            if(atlas26_reuse_mode_){
                auto hit=atlas26_use_.find(cid);""",
"""            if(atlas26_reuse_mode_ && (
                 atlas26_reuse_mode_<=2 || atlas27_active_)){
                ++atlas27_score_eligible_;
                auto hit=atlas26_use_.find(cid);""")

# Keep original C26 3k/6k windows while adding gated codes 3,4.
one("""                const uint64_t window=atlas26_reuse_mode_==1?3000:6000;""",
"""                const uint64_t window=(atlas26_reuse_mode_==1 ||
                                       atlas26_reuse_mode_==3)?3000:6000;""")
one("""            candidates.push_back({candidate_score,cid});""",
"""            if(atlas26_reuse_mode_>=3 && !atlas27_active_)
                ++atlas27_bypassed_;
            candidates.push_back({candidate_score,cid});""")

one("""        require(mode==1||mode==2,"ATLAS26 invalid reuse window");""",
"""        require(mode>=1&&mode<=4,"ATLAS26/27 invalid reuse window");""")

one("""    uint64_t atlas26_compaction_moves()const{return atlas26_compaction_moves_;}""",
"""    uint64_t atlas26_compaction_moves()const{return atlas26_compaction_moves_;}
    uint64_t atlas27_windows()const{return atlas27_windows_;}
    uint64_t atlas27_pressure_windows()const{return atlas27_pressure_windows_;}
    uint64_t atlas27_gate_on()const{return atlas27_gate_on_;}
    uint64_t atlas27_gate_off()const{return atlas27_gate_off_;}
    uint64_t atlas27_active()const{return atlas27_active_?1:0;}
    uint64_t atlas27_score_eligible()const{return atlas27_score_eligible_;}
    uint64_t atlas27_bypassed()const{return atlas27_bypassed_;}""")
(root/"drnas_native_core_c.hpp").write_text(s)

src=Path("mre_atlas26/native.cpp").read_text()
needle='mode=="C26_REUSE6K_GF2"'
assert src.count(needle)>=2,("mode dispatch drift",src.count(needle))
# At each matching native CDCL selection, add the two experimental arms.
src=src.replace('mode=="C26_REUSE3K"',
                'mode=="C26_REUSE3K"||mode=="C27_GATE3K"||mode=="C27_GATE6K"')
anchor='    if(mode=="C26_REUSE3K")solver.atlas26_enable(1);'
assert src.count(anchor)==1
src=src.replace(anchor,anchor+'''
    if(mode=="C27_GATE3K")solver.atlas26_enable(3);
    if(mode=="C27_GATE6K")solver.atlas26_enable(4);''',1)
# Standalone GF2 is evaluated as the distinct unchanged C26_GF2 control,
# so neither conditional arm may gain a free UNSAT proof advantage.
anchor='           <<" SAT_original_verified="<<int(status==10)'
assert src.count(anchor)==1
src=src.replace(anchor,'''           <<" atlas27_windows="<<solver.atlas27_windows()
           <<" atlas27_pressure_windows="<<solver.atlas27_pressure_windows()
           <<" atlas27_gate_on="<<solver.atlas27_gate_on()
           <<" atlas27_gate_off="<<solver.atlas27_gate_off()
           <<" atlas27_active="<<solver.atlas27_active()
           <<" atlas27_score_eligible="<<solver.atlas27_score_eligible()
           <<" atlas27_bypassed="<<solver.atlas27_bypassed()
'''+anchor,1)
assert src.count("solver.atlas26_enable(")==4
(root/"native.cpp").write_text(src)
print("ATLAS27_BUILD_PATCH_PASS conditional_BCP=true use_propagations=true"
      " reason_reuse=true hysteresis=true original_C7_C26_frozen=true")
