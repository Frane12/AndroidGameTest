#!/usr/bin/env python3
"""ATLAS25 B/C: source-structure first; C adds early progress-aware gate.

Single native solver, no portfolio, no changed inference. All thresholds frozen
before benchmarking; these are hypotheses, NOT trained/validated policies.
"""
from pathlib import Path
root=Path("mre_atlas25");root.mkdir(exist_ok=True)
s=Path("mre_atlas24/drnas_native_core_c.hpp").read_text()
def one(a,b):
 global s
 assert s.count(a)==1,("ATLAS25 header drift",a[:100],s.count(a))
 s=s.replace(a,b,1)
one("    bool atlas24_live_=false,atlas24_active_=false;",
"""    bool atlas24_live_=false,atlas24_active_=false;
    bool atlas25_b_=false,atlas25_c_=false,atlas25_initial_c7_=false;
    uint64_t atlas25_early_last_conflicts_=0,atlas25_early_last_watch_=0;
    uint64_t atlas25_early_last_prop_=0,atlas25_early_last_decisions_=0;
    uint64_t atlas25_early_windows_=0,atlas25_early_switches_=0;
    int atlas25_early_streak_=0;
    // Structure gate is deterministic and cheap; no source label or benchmark ID.
    void atlas25_enable_structure(bool c7,uint64_t seed,bool progress){
        require(!atlas24_live_&&!atlas13_c_enabled_&&!atlas15_enabled_,
                "ATLAS25 structure gate requires fresh A solver");
        atlas25_b_=true;atlas25_c_=progress;
        atlas25_initial_c7_=c7;
        if(c7){
            atlas13_enable_c(seed?seed:1,true,true);
            atlas13_warmstart(1.0,0.85);
            atlas15_enable_cdcl();
            atlas16_enable_keep();
            atlas17_enable_adaptive();
            atlas23_stable_phase_=true;
        }else if(progress){
            atlas24_seed_=seed?seed:1;
        }
    }
    void atlas25_progress_on_conflict(){
        if(!atlas25_c_||atlas25_initial_c7_||atlas25_early_switches_)return;
        if(stats_.conflicts<atlas25_early_last_conflicts_+500)return;
        const auto dw=stats_.watch_visits-atlas25_early_last_watch_;
        const auto dp=stats_.propagations-atlas25_early_last_prop_;
        const auto dd=stats_.decisions-atlas25_early_last_decisions_;
        atlas25_early_last_conflicts_=stats_.conflicts;
        atlas25_early_last_watch_=stats_.watch_visits;
        atlas25_early_last_prop_=stats_.propagations;
        atlas25_early_last_decisions_=stats_.decisions;
        ++atlas25_early_windows_;
        // Progress proxy: expensive BCP with high conflict/decision rate.
        // Require two consecutive windows. Avoid zero-division.
        if(dp>0&&dd>0&&dw>=16*dp&&dd<=850)
            ++atlas25_early_streak_;
        else atlas25_early_streak_=0;
        if(atlas25_early_streak_<2)return;
        atlas13_enable_c(atlas24_seed_,true,true);
        atlas13_warmstart(1.0,0.85);
        atlas15_enable_cdcl();
        atlas16_enable_keep();
        atlas17_enable_adaptive();
        atlas23_stable_phase_=true;
        atlas17_last_watch_=stats_.watch_visits;
        atlas17_last_prop_=stats_.propagations;
        atlas15_last_restart_=stats_.conflicts;
        ++atlas25_early_switches_;
    }""")
one("                atlas24_on_conflict();",
"""                atlas24_on_conflict();
                atlas25_progress_on_conflict();""")
one("    bool atlas24_live()const{return atlas24_live_;}",
"""    bool atlas25_b()const{return atlas25_b_;}
    bool atlas25_c()const{return atlas25_c_;}
    bool atlas25_initial_c7()const{return atlas25_initial_c7_;}
    uint64_t atlas25_early_switches()const{return atlas25_early_switches_;}
    uint64_t atlas25_early_windows()const{return atlas25_early_windows_;}
    bool atlas24_live()const{return atlas24_live_;}""")
(root/"drnas_native_core_c.hpp").write_text(s)
src=Path("mre_atlas24/native.cpp").read_text()
needle='mode=="V24_LIVE"||mode=="V24_LIVE_GAUSS"'
assert src.count(needle)>=2
src=src.replace(needle,needle+'||mode=="V25_B"||mode=="V25_C"')
# Structural selection uses only the ORIGINAL formula, not labels or outcome.
anchor='  if(mode=="V24_LIVE"||mode=="V24_LIVE_GAUSS"||mode=="V25_B"||mode=="V25_C")solver.atlas24_enable_live(trial_seed);'
assert src.count(anchor)==1
src=src.replace(anchor,anchor.replace('||mode=="V25_B"||mode=="V25_C"','')+'''
  if(mode=="V25_B"||mode=="V25_C"){
    uint64_t bin=0,ternary=0,longer=0;
    for(const auto&cl:orig.clauses){
      if(cl.size()==2)++bin;
      else if(cl.size()==3)++ternary;
      else if(cl.size()>=4)++longer;
    }
    const uint64_t count=orig.clauses.size();
    // Frozen coarse structural rule, not family names or instance hashes.
    // Binary-rich and larger constraint graphs favor early C7 hypothesis.
    const bool choose_c7=orig.vars>=150 && count>=500 &&
       (bin*100>=35*count || (orig.vars>=250 && ternary*100>=75*count));
    solver.atlas25_enable_structure(choose_c7,trial_seed,mode=="V25_C");
  }''',1)
anchor='           <<" SAT_original_verified="<<int(status==10)'
assert src.count(anchor)==1
src=src.replace(anchor,
'''           <<" atlas25_b="<<int(solver.atlas25_b())
           <<" atlas25_c="<<int(solver.atlas25_c())
           <<" atlas25_initial_c7="<<int(solver.atlas25_initial_c7())
           <<" atlas25_early_switches="<<solver.atlas25_early_switches()
           <<" atlas25_early_windows="<<solver.atlas25_early_windows()
''' +anchor,1)
assert src.count('mode=="V25_B"')>=2 and src.count('mode=="V25_C"')>=2
(root/"native.cpp").write_text(src)
print("ATLAS25_BUILD_PASS B_structural=true C_early_progress=true one_solver=true")
