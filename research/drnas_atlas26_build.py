#!/usr/bin/env python3
"""ATLAS26: native C7 clause reason-reuse scoring, isolated proof-first GF(2) arms.

Generator overlays ATLAS25 B/C; NO edits to main, frozen controls or input CNFs.
C26 is CDCL single-process C7 with an optional source-derived GF(2) front-end.
Usage scores only reorder C7's deletion candidates; no new unproved inferences.
"""
from pathlib import Path

root=Path("mre_atlas26")
root.mkdir(exist_ok=True)
s=Path("mre_atlas25/drnas_native_core_c.hpp").read_text()

def one(a,b):
    global s
    n=s.count(a)
    assert n==1,("ATLAS26 patch drift",a[:120],n)
    s=s.replace(a,b,1)

one("    bool atlas25_b_=false,atlas25_c_=false,atlas25_initial_c7_=false;",
"""    bool atlas25_b_=false,atlas25_c_=false,atlas25_initial_c7_=false;
    int atlas26_reuse_mode_=0; // 1=3k conflicts, 2=6k conflicts
    struct Atlas26Use {
        uint16_t hits=0; // includes the initial asserting implication
        uint64_t last_conflict=0;
    };
    std::map<int,Atlas26Use> atlas26_use_;
    uint64_t atlas26_reason_uses_=0,atlas26_reused_=0;
    uint64_t atlas26_discounted_=0,atlas26_deleted_=0;
    uint64_t atlas26_tracked_=0,atlas26_lbd_low_=0;
    uint64_t atlas26_compaction_moves_=0;
    void atlas26_record_reason(int cid){
        if(!atlas26_reuse_mode_ || cid<0)return;
        auto it=atlas26_use_.find(cid);
        if(it==atlas26_use_.end())return;
        const uint16_t before=it->second.hits;
        if(before<65535)++it->second.hits;
        it->second.last_conflict=stats_.conflicts;
        ++atlas26_reason_uses_;
        if(before>=1)++atlas26_reused_;
    }""")

# Observe real reason use along the native CDCL trail, not post-hoc labels.
one("""        reasons_[v] = from_clause;
        trail_.push_back(lit);""",
"""        reasons_[v] = from_clause;
        atlas26_record_reason(from_clause);
        trail_.push_back(lit);""")

# Clause IDs are assigned at creation; metadata is stable until deletion/compaction.
one("""        atlas15_born_[cid]=stats_.conflicts;
        ++atlas15_live_learned_;""",
"""        atlas15_born_[cid]=stats_.conflicts;
        if(atlas26_reuse_mode_){
            atlas26_use_[cid]=Atlas26Use{};
            ++atlas26_tracked_;
            if(atlas15_last_lbd_<=3)++atlas26_lbd_low_;
        }
        ++atlas15_live_learned_;""")

# Compaction remaps watch lists, LBD, reasons and birth times upstream.
# This patch MUST migrate the same CID-keyed usage data.
one("""        atlas15_born_.swap(born_migrated);""",
"""        atlas15_born_.swap(born_migrated);
        if(atlas26_reuse_mode_){
            std::map<int,Atlas26Use> migrated_use;
            for(const auto&kv:atlas26_use_){
                if(kv.first<0 || size_t(kv.first)>=before)continue;
                const int next=remap[size_t(kv.first)];
                if(next>=0){
                    migrated_use.emplace(next,kv.second);
                    if(next!=kv.first)++atlas26_compaction_moves_;
                }
            }
            atlas26_use_.swap(migrated_use);
        }""")

# Soft protection prevents repeated dead-clause retention and is safe when
# all eligible clauses have recently been used. C7 deletion quota stays frozen.
one("""            candidates.push_back({kv.second*100+int(std::min<size_t>(cl.size(),99)),cid});""",
"""            int candidate_score=kv.second*100+
                int(std::min<size_t>(cl.size(),99));
            if(atlas26_reuse_mode_){
                auto hit=atlas26_use_.find(cid);
                const uint64_t window=atlas26_reuse_mode_==1?3000:6000;
                if(hit!=atlas26_use_.end() && hit->second.hits>=2 &&
                   stats_.conflicts>=hit->second.last_conflict &&
                   stats_.conflicts-hit->second.last_conflict<=window){
                    // Suppress priority for frequent, recently useful reasons.
                    // No hard veto: high BCP pressure still allows deletion.
                    const int bonus=350*std::min<int>(hit->second.hits-1,4);
                    candidate_score=std::max(0,candidate_score-bonus);
                    ++atlas26_discounted_;
                }
            }
            candidates.push_back({candidate_score,cid});""")

one("""            atlas15_lbd_.erase(cid);
            ++atlas15_deleted_;""",
"""            atlas15_lbd_.erase(cid);
            if(atlas26_reuse_mode_){
                atlas26_use_.erase(cid);
                ++atlas26_deleted_;
            }
            ++atlas15_deleted_;""")

one("""    uint64_t atlas25_early_windows()const{return atlas25_early_windows_;}""",
"""    uint64_t atlas25_early_windows()const{return atlas25_early_windows_;}
    void atlas26_enable(int mode){
        require(atlas16_keep_ && atlas17_adaptive_ &&
                !atlas26_reuse_mode_ && !atlas24_live_ && !atlas25_b_,
                "ATLAS26 requires isolated C7 CDCL baseline");
        require(mode==1||mode==2,"ATLAS26 invalid reuse window");
        atlas26_reuse_mode_=mode;
    }
    int atlas26_mode()const{return atlas26_reuse_mode_;}
    uint64_t atlas26_reason_uses()const{return atlas26_reason_uses_;}
    uint64_t atlas26_reused()const{return atlas26_reused_;}
    uint64_t atlas26_discounted()const{return atlas26_discounted_;}
    uint64_t atlas26_deleted()const{return atlas26_deleted_;}
    uint64_t atlas26_tracked()const{return atlas26_tracked_;}
    uint64_t atlas26_lbd_low()const{return atlas26_lbd_low_;}
    uint64_t atlas26_live_metadata()const{return atlas26_use_.size();}
    uint64_t atlas26_compaction_moves()const{return atlas26_compaction_moves_;}""")

(root/"drnas_native_core_c.hpp").write_text(s)

src=Path("mre_atlas25/native.cpp").read_text()
needle='mode=="C7_ADAPT"'
assert src.count(needle)>=2,("C7 dispatch changed",src.count(needle))
src=src.replace(needle,needle+'||mode=="C26_REUSE3K"||mode=="C26_REUSE6K"||mode=="C26_REUSE6K_GF2"')
anchor="solver.atlas17_enable_adaptive();"
assert src.count(anchor)==1
src=src.replace(anchor,anchor+'''
    if(mode=="C26_REUSE3K")solver.atlas26_enable(1);
    if(mode=="C26_REUSE6K"||mode=="C26_REUSE6K_GF2")solver.atlas26_enable(2);''',1)
# Existing source-derived XOR/GF(2) procedure is reused without modification.
# The corresponding independent certificate is checked by the benchmark runner.
lines=src.splitlines(keepends=True)
items=[i for i,l in enumerate(lines) if "const bool use_gauss=" in l]
assert len(items)==1,"cannot locate source GF2 mode dispatch"
i=items[0]
assert lines[i].rstrip().endswith(";"),"unexpected multiline GF2 dispatch"
lines[i]=lines[i].rstrip()[:-1]+'||mode=="C26_REUSE6K_GF2";\n'
src="".join(lines)
anchor='           <<" SAT_original_verified="<<int(status==10)'
assert src.count(anchor)==1
src=src.replace(anchor,'''           <<" atlas26_mode="<<solver.atlas26_mode()
           <<" atlas26_reason_uses="<<solver.atlas26_reason_uses()
           <<" atlas26_reused="<<solver.atlas26_reused()
           <<" atlas26_discounted="<<solver.atlas26_discounted()
           <<" atlas26_deleted="<<solver.atlas26_deleted()
           <<" atlas26_tracked="<<solver.atlas26_tracked()
           <<" atlas26_lbd_low="<<solver.atlas26_lbd_low()
           <<" atlas26_live_metadata="<<solver.atlas26_live_metadata()
           <<" atlas26_compaction_moves="<<solver.atlas26_compaction_moves()
'''+anchor,1)
assert src.count("solver.atlas26_enable(")==2
(root/"native.cpp").write_text(src)
print("ATLAS26_BUILD_PATCH_PASS C7_frozen=true reason_at_enqueue=true"
      " soft_recent_usage_eviction=true compaction_remap=true source_GF2_unchanged=true")
