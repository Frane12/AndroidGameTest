#!/usr/bin/env python3
"""ATLAS23 isolated recovery: preserve recently learned clauses and reduce deletion.
Generated on top of ATLAS19. Frozen A/C6/C7/Kissat/CMS unchanged.
"""
from pathlib import Path
root=Path("mre_atlas23");root.mkdir(exist_ok=True)
s=Path("mre_atlas19/drnas_native_core_c.hpp").read_text()
def one(a,b):
 global s
 assert s.count(a)==1,("ATLAS23 source drift",a,s.count(a))
 s=s.replace(a,b,1)
one("    int atlas19_fixed_q4_mode_=0;",
"""    int atlas23_recovery_mode_=0; // 1: low quota, 2: low quota + recent-age guard
    uint64_t atlas23_age_protected_=0;
    int atlas19_fixed_q4_mode_=0;""")
one("""                    (atlas19_fixed_q4_mode_==1 && stats_.conflicts%1500==0) ||""",
"""                    (atlas23_recovery_mode_ && stats_.conflicts%6000==0) ||
                    (atlas19_fixed_q4_mode_==1 && stats_.conflicts%1500==0) ||""")
one("""            if(locked[size_t(cid)] || kv.second<7 || cl.size()<4)continue;""",
"""            if(locked[size_t(cid)] || kv.second<7 || cl.size()<4)continue;
            if(atlas23_recovery_mode_==2){
                const auto it=atlas15_born_.find(cid);
                if(it!=atlas15_born_.end() &&
                   stats_.conflicts>=it->second &&
                   stats_.conflicts-it->second<12000){
                    ++atlas23_age_protected_;
                    continue;
                }
            }""")
one("""        const size_t divisor=atlas19_fixed_q4_mode_?4:""",
"""        const size_t divisor=atlas23_recovery_mode_?32:
            atlas19_fixed_q4_mode_?4:""")
one("""            atlas15_lbd_.erase(cid);
            ++atlas15_deleted_;""",
"""            atlas15_lbd_.erase(cid);
            atlas15_born_.erase(cid);
            ++atlas15_deleted_;""")
one("""        atlas15_lbd_.swap(migrated);""",
"""        atlas15_lbd_.swap(migrated);
        std::map<int,uint64_t> born_migrated;
        for(auto kv:atlas15_born_)
            if(kv.first>=0 && size_t(kv.first)<before &&
               remap[size_t(kv.first)]>=0)
                born_migrated[remap[size_t(kv.first)]]=kv.second;
        atlas15_born_.swap(born_migrated);""")
one("""    uint64_t atlas17_low_cycles()const{return atlas17_low_cycles_;}""",
"""    uint64_t atlas17_low_cycles()const{return atlas17_low_cycles_;}
    void atlas23_enable_recovery(int mode){
        require(atlas16_keep_ && !atlas17_adaptive_ &&
                !atlas19_fixed_q4_mode_ && !atlas23_recovery_mode_,
                "ATLAS23 requires isolated C6 control");
        require(mode==1||mode==2,"invalid ATLAS23 mode");
        atlas23_recovery_mode_=mode;
    }
    uint64_t atlas23_age_protected()const{return atlas23_age_protected_;}""")
(root/"drnas_native_core_c.hpp").write_text(s)
src=Path("mre_atlas19/native.cpp").read_text()
for old,new in [
 ('mode=="C6_KEEP_GAUSS"','mode=="C6_KEEP_GAUSS"||mode=="C23_RECENT"||mode=="C23_QUOTA"'),
 ('mode=="C6_KEEP"','mode=="C6_KEEP"||mode=="C23_RECENT"||mode=="C23_QUOTA"')]:
 assert src.count(old)>=2
 src=src.replace(old,new)
anchor='if(mode=="C7_ADAPT"||mode=="C7_ADAPT_GAUSS")solver.atlas17_enable_adaptive();'
assert src.count(anchor)==1
src=src.replace(anchor,anchor+'''
    if(mode=="C23_QUOTA")solver.atlas23_enable_recovery(1);
    if(mode=="C23_RECENT")solver.atlas23_enable_recovery(2);''',1)
anchor='           <<" SAT_original_verified="<<int(status==10)'
assert src.count(anchor)==1
src=src.replace(anchor,'''           <<" atlas23_age_protected="<<solver.atlas23_age_protected()
''' +anchor,1)
(root/"native.cpp").write_text(src)
assert 'C23_RECENT' in src and 'C23_QUOTA' in src
print("ATLAS23_PATCH_PASS control_frozen=true quota=1/32 cadence=6000 recent_age=12000")
