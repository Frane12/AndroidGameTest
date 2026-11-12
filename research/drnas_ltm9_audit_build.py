#!/usr/bin/env python3
"""LTM9: audit CDCL learned-clause LBD, retention and progress, no policy change.
Apply after research/drnas_ltm8_php_build.py on generated C++ only.
"""
from pathlib import Path
hpath=Path("mre_atlas23/drnas_native_core_c.hpp")
cpath=Path("mre_atlas23/native.cpp")
s=hpath.read_text()
def one(a,b):
    global s
    n=s.count(a)
    assert n==1,("LTM9 header drift",a[:120],n)
    s=s.replace(a,b,1)

one("    uint64_t atlas15_peak_live_=0;",
"""    uint64_t atlas15_peak_live_=0;
    uint64_t ltm9_lbd_le2_=0,ltm9_lbd_3to6_=0,ltm9_lbd_ge7_=0;
    uint64_t ltm9_next_progress_=25000,ltm9_progress_events_=0;""")
one("        std::set<int> active(cl.begin(),cl.end());",
"""        if(stats_.conflicts>=ltm9_next_progress_ && ltm9_progress_events_<10){
            ltm9_next_progress_=stats_.conflicts+25000;
            ++ltm9_progress_events_;
            std::cout<<"LTM9_PROGRESS conflicts="<<stats_.conflicts
                <<" decisions="<<stats_.decisions
                <<" restarts="<<stats_.restarts
                <<" learned="<<stats_.learned_clauses
                <<" minimized="<<atlas15_minimized_
                <<" deleted="<<atlas15_deleted_
                <<" lbd_le2="<<ltm9_lbd_le2_
                <<" lbd_3to6="<<ltm9_lbd_3to6_
                <<" lbd_ge7="<<ltm9_lbd_ge7_
                <<" active_lbd="<<atlas15_lbd_.size()
                <<" quota_attempts="<<atlas36_attempts_
                <<" quota_effective="<<atlas36_effective_quota_
                <<std::endl;
        }
        std::set<int> active(cl.begin(),cl.end());""")
one("        atlas15_lbd_[cid]=atlas15_last_lbd_;",
"""        if(atlas15_last_lbd_<=2)++ltm9_lbd_le2_;
        else if(atlas15_last_lbd_<=6)++ltm9_lbd_3to6_;
        else ++ltm9_lbd_ge7_;
        atlas15_lbd_[cid]=atlas15_last_lbd_;""")
one("    uint64_t atlas15_deleted()const{return atlas15_deleted_;}",
"""    uint64_t atlas15_deleted()const{return atlas15_deleted_;}
    uint64_t ltm9_lbd_le2()const{return ltm9_lbd_le2_;}
    uint64_t ltm9_lbd_3to6()const{return ltm9_lbd_3to6_;}
    uint64_t ltm9_lbd_ge7()const{return ltm9_lbd_ge7_;}
    uint64_t ltm9_active_lbd()const{return atlas15_lbd_.size();}
    uint64_t ltm9_progress_events()const{return ltm9_progress_events_;}""")
hpath.write_text(s)

s=cpath.read_text()
anchor='           <<" SAT_original_verified="<<int(status==10)'
assert s.count(anchor)==1,("LTM9 output drift",s.count(anchor))
metrics='''           <<" ltm9_lbd_le2="<<solver.ltm9_lbd_le2()
           <<" ltm9_lbd_3to6="<<solver.ltm9_lbd_3to6()
           <<" ltm9_lbd_ge7="<<solver.ltm9_lbd_ge7()
           <<" ltm9_active_lbd="<<solver.ltm9_active_lbd()
           <<" ltm9_progress_events="<<solver.ltm9_progress_events()
           <<" ltm9_learned="<<st.learned_clauses
           <<" ltm9_restarts="<<st.restarts
           <<" ltm9_propagations="<<st.propagations
           <<" ltm9_watch_visits="<<st.watch_visits
           <<" ltm9_peak_learned_counter="<<solver.atlas15_peak_live()
'''
# stats fields and public peak accessor are provided by existing ATLAS15 CDCL.
s=s.replace(anchor,metrics+anchor,1)
cpath.write_text(s)
print("LTM9_AUDIT_PATCH_PASS nonsemantic=true LBD_histograms=true timeout_checkpoints=true",flush=True)
