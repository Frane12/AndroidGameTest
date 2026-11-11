#!/usr/bin/env python3
"""ATLAS37: causal online quota routing between 75% and 100%.
C7 native reduction, no training on benchmark labels or results.
"""
from pathlib import Path
p=Path("mre_atlas23/drnas_native_core_c.hpp")
s=p.read_text()
def one(a,b):
 global s
 assert s.count(a)==1,("ATLAS37 header drift",a[:120],s.count(a))
 s=s.replace(a,b,1)
one("    int atlas36_quota_pct_=100;",
"""    int atlas36_quota_pct_=100;
    bool atlas37_route_=false;
    uint64_t atlas37_route_75_=0,atlas37_route_100_=0;
    uint64_t atlas37_last_watch_=0,atlas37_last_prop_=0;""")
one("""        const size_t count=std::max<size_t>(1,
            (baseline_count*size_t(atlas36_quota_pct_)+99)/100);""",
"""        int effective_pct=atlas36_quota_pct_;
        if(atlas37_route_){
            // Use only measurements already observed at the current reduction.
            // Heavy watch-list pressure => baseline aggressive deletion;
            // otherwise retain 25% more candidate clauses.
            const uint64_t dw=stats_.watch_visits-atlas37_last_watch_;
            const uint64_t dp=stats_.propagations-atlas37_last_prop_;
            atlas37_last_watch_=stats_.watch_visits;
            atlas37_last_prop_=stats_.propagations;
            effective_pct=(dp>0 && dw>32*dp)?100:75;
            if(effective_pct==75)++atlas37_route_75_;
            else ++atlas37_route_100_;
        }
        const size_t count=std::max<size_t>(1,
            (baseline_count*size_t(effective_pct)+99)/100);""")
one("""    int atlas36_quota_pct()const{return atlas36_quota_pct_;}""",
"""    int atlas36_quota_pct()const{return atlas36_quota_pct_;}
    void atlas37_enable_route(){
        require(atlas16_keep_ && atlas17_adaptive_,"ATLAS37 requires C7");
        atlas37_route_=true;
    }
    int atlas37_route()const{return int(atlas37_route_);}
    uint64_t atlas37_route_75()const{return atlas37_route_75_;}
    uint64_t atlas37_route_100()const{return atlas37_route_100_;}""")
p.write_text(s)
p=Path("mre_atlas23/native.cpp")
s=p.read_text()
needle='mode=="V23_C7_STABLE"'
assert s.count(needle)>=2
s=s.replace(needle,needle+'||mode=="A37_ROUTE"')
anchor='solver.atlas23_enable_stable_phase();'
assert s.count(anchor)==1
s=s.replace(anchor,anchor+'\n    if(mode=="A37_ROUTE")solver.atlas37_enable_route();',1)
anchor='           <<" SAT_original_verified="<<int(status==10)'
assert s.count(anchor)==1
s=s.replace(anchor,'''           <<" atlas37_route="<<solver.atlas37_route()
           <<" atlas37_route_75="<<solver.atlas37_route_75()
           <<" atlas37_route_100="<<solver.atlas37_route_100()
'''+anchor,1)
assert s.count('mode=="A37_ROUTE"')>=3
p.write_text(s)
print("ATLAS37_BUILD_PASS online_causal_quota_route=true 75_or_100=true",flush=True)
