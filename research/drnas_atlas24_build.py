#!/usr/bin/env python3
"""ATLAS24: isolated utility-aware clause deletion experiment.

Generated exclusively from ATLAS23; C7, C23 and original CNFs remain frozen.
Only deletion selection/schedule changes: all SAT implications and analysis
remain in the existing CDCL implementation.
"""
from pathlib import Path
root=Path("mre_atlas24")
root.mkdir(exist_ok=True)
s=Path("mre_atlas23/drnas_native_core_c.hpp").read_text()
def one(old,new):
    global s
    n=s.count(old)
    assert n==1,("ATLAS24 source drift",old,n)
    s=s.replace(old,new,1)

one("    int atlas23_recovery_mode_=0;",
"""    int atlas24_utility_mode_=0;  // 1=balanced, 2=longer reuse guard
    bool atlas24_high_pressure_=false;
    uint64_t atlas24_last_watch_=0,atlas24_last_prop_=0;
    uint64_t atlas24_high_cycles_=0,atlas24_low_cycles_=0;
    uint64_t atlas24_protected_=0,atlas24_deleted_=0,atlas24_reason_uses_=0;
    std::map<int,uint16_t> atlas24_reason_hits_;
    int atlas23_recovery_mode_=0;""")

# Record actual enqueue uses of learned clauses, not inferences from benchmark labels.
one("""        reasons_[v] = from_clause;
        trail_.push_back(lit);""",
"""        reasons_[v] = from_clause;
        if(atlas24_utility_mode_ && from_clause>=0){
            auto it=atlas24_reason_hits_.find(from_clause);
            if(it!=atlas24_reason_hits_.end()){
                if(it->second<65535)++it->second;
                ++atlas24_reason_uses_;
            }
        }
        trail_.push_back(lit);""")
one("""        atlas15_born_[cid]=stats_.conflicts;
        ++atlas15_live_learned_;""",
"""        atlas15_born_[cid]=stats_.conflicts;
        if(atlas24_utility_mode_)atlas24_reason_hits_[cid]=0;
        ++atlas15_live_learned_;""")
# Keep learned-clause quality indices synchronized with clause slot compaction.
one("""        atlas15_born_.swap(born_migrated);""",
"""        atlas15_born_.swap(born_migrated);
        if(atlas24_utility_mode_){
            std::map<int,uint16_t> hits_migrated;
            for(auto kv:atlas24_reason_hits_)
                if(kv.first>=0 && size_t(kv.first)<before &&
                   remap[size_t(kv.first)]>=0)
                    hits_migrated[remap[size_t(kv.first)]]=kv.second;
            atlas24_reason_hits_.swap(hits_migrated);
        }""")
one("""            atlas15_born_.erase(cid);
            ++atlas15_deleted_;""",
"""            atlas15_born_.erase(cid);
            if(atlas24_utility_mode_){
                atlas24_reason_hits_.erase(cid);
                ++atlas24_deleted_;
            }
            ++atlas15_deleted_;""")
one("""                    (atlas23_recovery_mode_ && stats_.conflicts%6000==0) ||""",
"""                    (atlas24_utility_mode_ && stats_.conflicts%3000==0) ||
                    (atlas23_recovery_mode_ && stats_.conflicts%6000==0) ||""")
one("""        if(atlas17_adaptive_){
            const uint64_t dw=stats_.watch_visits-atlas17_last_watch_;""",
"""        if(atlas24_utility_mode_){
            const uint64_t dw=stats_.watch_visits-atlas24_last_watch_;
            const uint64_t dp=stats_.propagations-atlas24_last_prop_;
            // Watch-visits/propagation is a BCP work proxy, not actual CPU time.
            atlas24_high_pressure_=(dp>0 && dw>8*dp);
            if(atlas16_allocated_clause_bytes()>96ULL*1024*1024)
                atlas24_high_pressure_=true;
            if(!atlas24_high_pressure_ && stats_.conflicts%6000!=0)return;
            atlas24_last_watch_=stats_.watch_visits;
            atlas24_last_prop_=stats_.propagations;
            if(atlas24_high_pressure_)++atlas24_high_cycles_;
            else ++atlas24_low_cycles_;
        }else if(atlas17_adaptive_){
            const uint64_t dw=stats_.watch_visits-atlas17_last_watch_;""")
one("""            if(locked[size_t(cid)] || kv.second<7 || cl.size()<4)continue;""",
"""            if(locked[size_t(cid)] || kv.second<7 || cl.size()<4)continue;
            if(atlas24_utility_mode_){
                const auto born=atlas15_born_.find(cid);
                if(born==atlas15_born_.end() || stats_.conflicts<born->second)
                    continue;
                const uint64_t age=stats_.conflicts-born->second;
                const auto hit=atlas24_reason_hits_.find(cid);
                const uint16_t uses=hit==atlas24_reason_hits_.end()?0:hit->second;
                const uint64_t min_age=atlas24_utility_mode_==1?3000:6000;
                const uint64_t reuse_age=atlas24_utility_mode_==1?12000:24000;
                if(age<min_age || (uses>0 && age<reuse_age) ||
                   (uses>=3 && age<60000)){
                    ++atlas24_protected_;
                    continue;
                }
            }""")
one("""            candidates.push_back({kv.second*100+int(std::min<size_t>(cl.size(),99)),cid});""",
"""            int eviction_score=kv.second*100+int(std::min<size_t>(cl.size(),99));
            if(atlas24_utility_mode_){
                const uint64_t age=stats_.conflicts-atlas15_born_.at(cid);
                const auto hit=atlas24_reason_hits_.find(cid);
                const int uses=hit==atlas24_reason_hits_.end()?0:int(hit->second);
                eviction_score+=int(std::min<uint64_t>(120,age/500));
                eviction_score-=150*std::min(uses,8);
            }
            candidates.push_back({eviction_score,cid});""")
one("""        const size_t divisor=atlas23_recovery_mode_?32:""",
"""        const size_t divisor=atlas24_utility_mode_?(atlas24_high_pressure_?8:32):
            atlas23_recovery_mode_?32:""")
one("""    uint64_t atlas23_age_protected()const{return atlas23_age_protected_;}""",
"""    uint64_t atlas23_age_protected()const{return atlas23_age_protected_;}
    void atlas24_enable_utility(int mode){
        require(atlas16_keep_ && !atlas17_adaptive_ &&
                !atlas19_fixed_q4_mode_ && !atlas23_recovery_mode_ &&
                !atlas24_utility_mode_,"ATLAS24 requires isolated C6 retention");
        require(mode==1||mode==2,"invalid ATLAS24 utility mode");
        atlas24_utility_mode_=mode;
    }
    int atlas24_utility_mode()const{return atlas24_utility_mode_;}
    uint64_t atlas24_reason_uses()const{return atlas24_reason_uses_;}
    uint64_t atlas24_protected()const{return atlas24_protected_;}
    uint64_t atlas24_deleted()const{return atlas24_deleted_;}
    uint64_t atlas24_high_cycles()const{return atlas24_high_cycles_;}
    uint64_t atlas24_low_cycles()const{return atlas24_low_cycles_;}""")
(root/"drnas_native_core_c.hpp").write_text(s)

src=Path("mre_atlas23/native.cpp").read_text()
old='mode=="C6_KEEP"||mode=="C23_RECENT"||mode=="C23_QUOTA"'
assert src.count(old)>=2,("ATLAS24 mode-switch drift",src.count(old))
src=src.replace(old,old+'||mode=="C24_BALANCED"||mode=="C24_GUARD"')
anchor='    if(mode=="C23_RECENT")solver.atlas23_enable_recovery(2);'
assert src.count(anchor)==1
src=src.replace(anchor,anchor+'''
    if(mode=="C24_BALANCED")solver.atlas24_enable_utility(1);
    if(mode=="C24_GUARD")solver.atlas24_enable_utility(2);''',1)
anchor='           <<" SAT_original_verified="<<int(status==10)'
assert src.count(anchor)==1
src=src.replace(anchor,'''           <<" atlas24_mode="<<solver.atlas24_utility_mode()
           <<" atlas24_reason_uses="<<solver.atlas24_reason_uses()
           <<" atlas24_protected="<<solver.atlas24_protected()
           <<" atlas24_deleted="<<solver.atlas24_deleted()
           <<" atlas24_high_cycles="<<solver.atlas24_high_cycles()
           <<" atlas24_low_cycles="<<solver.atlas24_low_cycles()
'''+anchor,1)
(root/"native.cpp").write_text(src)
assert src.count('solver.atlas24_enable_utility(')==2
print("ATLAS24_PATCH_PASS frozen_controls=true utility_reason_hits=true"
      " BCP_sampling=3000_low=6000 high_quota=1/8 low_quota=1/32")
