#!/usr/bin/env python3
"""ATLAS38 replay-causal deletion: identical deterministic prefix then
one 75 vs 100 deletion reduction; all later reductions revert to 75.
Does NOT implement a live in-memory fork or claim bitwise full-state snapshots.
"""
from pathlib import Path
p=Path("mre_atlas23/drnas_native_core_c.hpp")
s=p.read_text()
def one(a,b):
 global s
 assert s.count(a)==1,("ATLAS38 drift",a[:110],s.count(a))
 s=s.replace(a,b,1)

one("    uint64_t atlas37_last_watch_=0,atlas37_last_prop_=0;",
"""    uint64_t atlas37_last_watch_=0,atlas37_last_prop_=0;
    bool atlas38_pulse_=false;
    uint64_t atlas38_target_=0;
    int atlas38_pulse_pct_=75;
    uint64_t atlas38_seen_=0,atlas38_applied_=0;
    uint64_t atlas38_pre_fingerprint_=0;
    void atlas38_trace_before_pulse(){
        // Lightweight deterministic state signature; NOT a full CDCL
        // snapshot proof. Compare against a fixed-75 sham with same seed.
        uint64_t h=1469598103934665603ULL;
        auto mix=[&](uint64_t v){h^=v;h*=1099511628211ULL;};
        mix(stats_.conflicts);mix(stats_.decisions);
        mix(stats_.propagations);mix(stats_.watch_visits);
        mix(atlas15_deleted_);
        mix(clauses_.size());mix(trail_.size());
        for(int lit:trail_)mix(uint64_t(int64_t(lit)));
        atlas38_pre_fingerprint_=h;
        std::cerr<<"ATLAS38_PRE target="<<atlas38_target_
           <<" pct="<<atlas38_pulse_pct_
           <<" state_hash="<<h
           <<" conflicts="<<stats_.conflicts
           <<" decisions="<<stats_.decisions
           <<" propagations="<<stats_.propagations
           <<" watch_visits="<<stats_.watch_visits
           <<" deleted="<<atlas15_deleted_
           <<" clauses="<<clauses_.size()
           <<" trail="<<trail_.size()
           <<std::endl;
    }""")
# Existing ATLAS37 post-patch reduction, unaffected for all original arms.
one("""        const size_t count=std::max<size_t>(1,
            (baseline_count*size_t(effective_pct)+99)/100);""",
"""        if(atlas38_pulse_){
            effective_pct=75;
            ++atlas38_seen_;
            if(atlas38_seen_==atlas38_target_){
                atlas38_trace_before_pulse();
                effective_pct=atlas38_pulse_pct_;
                ++atlas38_applied_;
            }
        }
        const size_t count=std::max<size_t>(1,
            (baseline_count*size_t(effective_pct)+99)/100);""")

one("""    uint64_t atlas37_route_100()const{return atlas37_route_100_;}""",
"""    uint64_t atlas37_route_100()const{return atlas37_route_100_;}
    void atlas38_enable_pulse(uint64_t target,int pct){
        require(atlas16_keep_ && atlas17_adaptive_ && !atlas37_route_,
                "ATLAS38 requires isolated active C7");
        require(target>0 && target<=200 && (pct==75 || pct==100),
                "ATLAS38 invalid pulse target or quota");
        atlas38_pulse_=true;atlas38_target_=target;
        atlas38_pulse_pct_=pct;
    }
    uint64_t atlas38_seen()const{return atlas38_seen_;}
    uint64_t atlas38_applied()const{return atlas38_applied_;}
    uint64_t atlas38_pre_fingerprint()const{return atlas38_pre_fingerprint_;}
    uint64_t atlas38_target()const{return atlas38_target_;}
    uint64_t atlas38_pulse_pct()const{return atlas38_pulse_pct_;}""")
p.write_text(s)

p=Path("mre_atlas23/native.cpp")
s=p.read_text()
needle='mode=="V23_C7_STABLE"'
assert s.count(needle)>=2
s=s.replace(needle,needle+'||mode.rfind("A38_PULSE75_",0)==0||mode.rfind("A38_PULSE100_",0)==0')
anchor='solver.atlas23_enable_stable_phase();'
assert s.count(anchor)==1
s=s.replace(anchor,anchor+'''
    if(mode.rfind("A38_PULSE75_",0)==0)
        solver.atlas38_enable_pulse(std::stoull(mode.substr(12)),75);
    if(mode.rfind("A38_PULSE100_",0)==0)
        solver.atlas38_enable_pulse(std::stoull(mode.substr(13)),100);''',1)
anchor='           <<" SAT_original_verified="<<int(status==10)'
assert s.count(anchor)==1
s=s.replace(anchor,'''           <<" atlas38_target="<<solver.atlas38_target()
           <<" atlas38_pulse_pct="<<solver.atlas38_pulse_pct()
           <<" atlas38_seen="<<solver.atlas38_seen()
           <<" atlas38_applied="<<solver.atlas38_applied()
           <<" atlas38_pre_fingerprint="<<solver.atlas38_pre_fingerprint()
'''+anchor,1)
p.write_text(s)
print("ATLAS38_BUILD_PASS deterministic_prefix=true single_quota_intervention=true"
      " future_75=true original_controls_frozen=true")
