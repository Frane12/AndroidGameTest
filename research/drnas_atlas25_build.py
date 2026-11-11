#!/usr/bin/env python3
"""ATLAS25: C7 adaptive BCP deletion with bounded, recent actual-reuse protection.

Frozen C7, C23, C24, Kissat, CMS unchanged. Only C25 uses this policy.
Two arms: C25_REUSE3K and C25_REUSE6K. Protect at most 25% of learned
clauses per reduction cycle (by eligible count proxy), only when used >=2
times as a learned propagation reason within the last 3k/6k conflicts.
Never alters SAT inference, CNF, learned-clause generation or proof logic.
"""
from pathlib import Path
root=Path("mre_atlas25");root.mkdir(exist_ok=True)
s=Path("mre_atlas24/drnas_native_core_c.hpp").read_text()
def one(a,b):
 global s
 assert s.count(a)>=1,("ATLAS25 drift",a,s.count(a))
 s=s.replace(a,b,1)
one("    int atlas24_utility_mode_=0;",
"""    int atlas25_reuse_mode_=0;
    uint64_t atlas25_protected_=0,atlas25_reuse_hits_=0;
    std::map<int,uint64_t> atlas25_last_used_;
    int atlas24_utility_mode_=0;""")
one("        if(atlas24_utility_mode_ && from_clause>=0){",
"""        if((atlas24_utility_mode_ || atlas25_reuse_mode_) && from_clause>=0){""")
one("""                ++atlas24_reason_uses_;
            }
        }
        trail_.push_back(lit);""",
"""                ++atlas24_reason_uses_;
                if(atlas25_reuse_mode_){
                    atlas25_last_used_[from_clause]=stats_.conflicts;
                    ++atlas25_reuse_hits_;
                }
            }
        }
        trail_.push_back(lit);""")
one("        if(atlas24_utility_mode_)atlas24_reason_hits_[cid]=0;",
"""        if(atlas24_utility_mode_ || atlas25_reuse_mode_)
            atlas24_reason_hits_[cid]=0;""")
one("        if(atlas24_utility_mode_){\n            std::map<int,uint16_t> hits_migrated;",
"""        if(atlas24_utility_mode_ || atlas25_reuse_mode_){
            std::map<int,uint16_t> hits_migrated;""")
one("""            atlas24_reason_hits_.swap(hits_migrated);
        }""",
"""            atlas24_reason_hits_.swap(hits_migrated);
            if(atlas25_reuse_mode_){
                std::map<int,uint64_t> used_migrated;
                for(auto kv:atlas25_last_used_)
                    if(kv.first>=0 && size_t(kv.first)<before &&
                       remap[size_t(kv.first)]>=0)
                        used_migrated[remap[size_t(kv.first)]]=kv.second;
                atlas25_last_used_.swap(used_migrated);
            }
        }""")
one("""            if(atlas24_utility_mode_){
                atlas24_reason_hits_.erase(cid);""",
"""            if(atlas24_utility_mode_ || atlas25_reuse_mode_){
                atlas24_reason_hits_.erase(cid);
                if(atlas25_reuse_mode_)atlas25_last_used_.erase(cid);""")
one("""        std::vector<std::pair<int,int>> candidates;
        for(const auto&kv:atlas15_lbd_){""",
"""        std::vector<std::pair<int,int>> candidates;
        size_t atlas25_protected_cycle=0;
        const size_t atlas25_protection_cap=atlas15_lbd_.size()/4;
        for(const auto&kv:atlas15_lbd_){""")
one("""            if(locked[size_t(cid)] || kv.second<7 || cl.size()<4)continue;
            if(atlas24_utility_mode_){""",
"""            if(locked[size_t(cid)] || kv.second<7 || cl.size()<4)continue;
            if(atlas25_reuse_mode_){
                const auto hit=atlas24_reason_hits_.find(cid);
                const auto used=atlas25_last_used_.find(cid);
                const uint64_t window=atlas25_reuse_mode_==1?3000:6000;
                if(hit!=atlas24_reason_hits_.end() && hit->second>=2 &&
                   used!=atlas25_last_used_.end() &&
                   stats_.conflicts>=used->second &&
                   stats_.conflicts-used->second<=window &&
                   atlas25_protected_cycle<atlas25_protection_cap){
                    ++atlas25_protected_cycle;
                    ++atlas25_protected_;
                    continue;
                }
            }
            if(atlas24_utility_mode_){""")
one("""    uint64_t atlas24_low_cycles()const{return atlas24_low_cycles_;}""",
"""    uint64_t atlas24_low_cycles()const{return atlas24_low_cycles_;}
    void atlas25_enable_reuse(int mode){
        require(atlas16_keep_ && atlas17_adaptive_ &&
                !atlas19_fixed_q4_mode_ && !atlas23_recovery_mode_ &&
                !atlas24_utility_mode_ && !atlas25_reuse_mode_,
                "ATLAS25 requires isolated C7 adaptive retention");
        require(mode==1||mode==2,"invalid ATLAS25 reuse mode");
        atlas25_reuse_mode_=mode;
    }
    int atlas25_reuse_mode()const{return atlas25_reuse_mode_;}
    uint64_t atlas25_protected()const{return atlas25_protected_;}
    uint64_t atlas25_reuse_hits()const{return atlas25_reuse_hits_;}""")
(root/"drnas_native_core_c.hpp").write_text(s)
src=Path("mre_atlas24/native.cpp").read_text()
# Include C25 in the exact C7 mode switches; C7's adaptive scheduler/quota retained.
assert src.count('mode=="C7_ADAPT"')>=2
src=src.replace('mode=="C7_ADAPT"', 'mode=="C7_ADAPT"||mode=="C25_REUSE3K"||mode=="C25_REUSE6K"')
anchor='    if(mode=="C24_GUARD")solver.atlas24_enable_utility(2);'
assert src.count(anchor)==1
src=src.replace(anchor,anchor+'''
    if(mode=="C25_REUSE3K")solver.atlas25_enable_reuse(1);
    if(mode=="C25_REUSE6K")solver.atlas25_enable_reuse(2);''')
anchor='           <<" SAT_original_verified="<<int(status==10)'
assert src.count(anchor)==1
src=src.replace(anchor,'''           <<" atlas25_mode="<<solver.atlas25_reuse_mode()
           <<" atlas25_protected="<<solver.atlas25_protected()
           <<" atlas25_reuse_hits="<<solver.atlas25_reuse_hits()
'''+anchor)
(root/"native.cpp").write_text(src)
assert src.count("solver.atlas25_enable_reuse(")==2
print("ATLAS25_PATCH_PASS C7_scheduler=true bounded_reuse_guard=true remap=true")
