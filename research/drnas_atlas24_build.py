#!/usr/bin/env python3
"""ATLAS24: in-process adaptive A <-> C7 with measured BCP-cost gate.

One native CDCL instance, never parallel backends. It begins with native A,
observes conflict-window watch visits and propagations, and can enable C7
heuristics once if repeated high search pressure appears. Under severe BCP
pressure it can disable them once. Learned clauses/reasons/trail remain intact.
"""
from pathlib import Path

root=Path("mre_atlas24")
root.mkdir(parents=True,exist_ok=True)
s=Path("mre_atlas23/drnas_native_core_c.hpp").read_text()

def one(a,b):
    global s
    count=s.count(a)
    assert count==1,("ATLAS24 header drift",a[:90],count)
    s=s.replace(a,b,1)

one("    bool atlas23_min_only_=false,atlas23_age_protect_=false,atlas23_stable_phase_=false;",
"""    bool atlas23_min_only_=false,atlas23_age_protect_=false,atlas23_stable_phase_=false;
    bool atlas24_live_=false,atlas24_active_=false;
    uint64_t atlas24_seed_=1,atlas24_last_conflicts_=0,atlas24_last_watch_=0;
    uint64_t atlas24_last_prop_=0,atlas24_switch_at_=0;
    uint64_t atlas24_on_=0,atlas24_off_=0,atlas24_windows_=0;
    int atlas24_pressure_streak_=0,atlas24_recovery_streak_=0;
    // Frozen, training-free gate. These are hypotheses, not fitted thresholds.
    static constexpr uint64_t atlas24_window_=1500;
    void atlas24_on_conflict(){
        if(!atlas24_live_ || stats_.conflicts<atlas24_last_conflicts_+atlas24_window_)return;
        const auto dc=stats_.conflicts-atlas24_last_conflicts_;
        const auto dw=stats_.watch_visits-atlas24_last_watch_;
        const auto dp=stats_.propagations-atlas24_last_prop_;
        atlas24_last_conflicts_=stats_.conflicts;
        atlas24_last_watch_=stats_.watch_visits;
        atlas24_last_prop_=stats_.propagations;
        ++atlas24_windows_;
        if(!atlas24_active_){
            // Require TWO full high-pressure windows to avoid early noise.
            if(dp>0 && dw>=32*dp && dc>=atlas24_window_)
                ++atlas24_pressure_streak_;
            else atlas24_pressure_streak_=0;
            if(!atlas24_on_ && atlas24_pressure_streak_>=2 &&
               stats_.conflicts>=3000){
                atlas13_enable_c(atlas24_seed_,true,true);
                atlas13_warmstart(1.0,0.85);
                atlas15_enable_cdcl();
                atlas16_enable_keep();
                atlas17_enable_adaptive();
                atlas23_stable_phase_=true; // use 23's tested stable phase ablation
                atlas17_last_watch_=stats_.watch_visits;
                atlas17_last_prop_=stats_.propagations;
                atlas15_last_restart_=stats_.conflicts;
                atlas24_active_=true;
                atlas24_switch_at_=stats_.conflicts;
                ++atlas24_on_;
            }
        }else if(stats_.conflicts>=atlas24_switch_at_+3000){
            // Emergency cost fallback. Do NOT undo derived learned clauses.
            if(dp>0 && dw>=96*dp) ++atlas24_recovery_streak_;
            else atlas24_recovery_streak_=0;
            if(atlas24_recovery_streak_>=2 && !atlas24_off_){
                atlas13_c_enabled_=false;
                atlas15_enabled_=false;
                atlas16_keep_=false;
                atlas17_adaptive_=false;
                atlas23_stable_phase_=false;
                atlas24_active_=false;
                ++atlas24_off_;
            }
        }
    }""")
one("                ++stats_.conflicts;", "                ++stats_.conflicts;\n                atlas24_on_conflict();")
one("    bool atlas23_stable_phase()const{return atlas23_stable_phase_;}",
"""    bool atlas23_stable_phase()const{return atlas23_stable_phase_;}
    void atlas24_enable_live(uint64_t seed){
        require(!atlas15_enabled_ && !atlas13_c_enabled_ && !atlas24_live_,
                "ATLAS24 must start on original A search");
        atlas24_seed_=seed?seed:1;
        atlas24_live_=true;
    }
    bool atlas24_live()const{return atlas24_live_;}
    bool atlas24_active()const{return atlas24_active_;}
    uint64_t atlas24_on()const{return atlas24_on_;}
    uint64_t atlas24_off()const{return atlas24_off_;}
    uint64_t atlas24_windows()const{return atlas24_windows_;}""")
(root/"drnas_native_core_c.hpp").write_text(s)

src=Path("mre_atlas23/native.cpp").read_text()
needle='mode=="A"||mode=="V23_A_MIN"'
assert src.count(needle)==1,("dispatch A drift",src.count(needle))
src=src.replace(needle,needle+'||mode=="V24_LIVE"||mode=="V24_LIVE_GAUSS"',1)
lines=src.splitlines(keepends=True)
matches=[i for i,l in enumerate(lines) if 'const bool use_gauss=' in l]
assert len(matches)==1,"cannot locate Gaussian arm list"
i=matches[0]
assert lines[i].rstrip().endswith(';')
lines[i]=lines[i].rstrip()[:-1]+'||mode=="V24_LIVE_GAUSS";\n'
src=''.join(lines)
needle='if(mode=="V23_A_MIN")solver.atlas23_enable_min_only();'
assert src.count(needle)==1
src=src.replace(needle,needle+
'\n  if(mode=="V24_LIVE"||mode=="V24_LIVE_GAUSS")solver.atlas24_enable_live(trial_seed);',1)
anchor='           <<" SAT_original_verified="<<int(status==10)'
assert src.count(anchor)==1
src=src.replace(anchor,
'''           <<" atlas24_live="<<int(solver.atlas24_live())
           <<" atlas24_active="<<int(solver.atlas24_active())
           <<" atlas24_on="<<solver.atlas24_on()
           <<" atlas24_off="<<solver.atlas24_off()
           <<" atlas24_windows="<<solver.atlas24_windows()
'''+anchor,1)
assert src.count('mode=="V24_LIVE_GAUSS"')>=3
assert src.count('mode=="V24_LIVE"')>=2
(root/"native.cpp").write_text(src)
print("ATLAS24_BUILD_PASS single_process=true A_first=true "
      "live_BCP_pressure=true bounded_switches=true stable_phase=true")
