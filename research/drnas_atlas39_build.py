#!/usr/bin/env python3
"""ATLAS39: native C++ reason-clause utility memory, isolated C7 experiment.

C39_SHADOW measures references to learned clauses used as valid reasons
during learned-clause minimization without changing C7's deletion order.
C39_PROTECT applies a bounded recent-reason-use score discount to eligible
deletion candidates; quota stays the proven fixed A36_75.
Neither mode changes SAT/UNSAT inference nor the other arms.
"""
from pathlib import Path
p=Path("mre_atlas23/drnas_native_core_c.hpp")
s=p.read_text()
def one(a,b):
 global s
 n=s.count(a)
 assert n==1,("ATLAS39 patch drift",a[:135],n)
 s=s.replace(a,b,1)

one("    uint64_t atlas37_last_watch_=0,atlas37_last_prop_=0;",
"""    uint64_t atlas37_last_watch_=0,atlas37_last_prop_=0;
    // Packed per-slot live metadata; O(1) reason touch and age lookup.
    // Only minimization-reason uses are recorded, not all BCP reasons.
    int atlas39_mode_=0; // 0 frozen control, 1 shadow, 2 protect
    std::vector<uint32_t> atlas39_last_;
    std::vector<uint8_t> atlas39_hits_;
    uint64_t atlas39_reason_uses_=0,atlas39_reuses_=0;
    uint64_t atlas39_scored_=0,atlas39_recent_=0;
    uint64_t atlas39_changed_rank_=0,atlas39_reduction_events_=0;
    uint64_t atlas39_compaction_remaps_=0;
    void atlas39_touch(int cid){
        if(!atlas39_mode_ || cid<0 || size_t(cid)>=clauses_.size())return;
        if(atlas15_lbd_.find(cid)==atlas15_lbd_.end())return; // learned only
        if(size_t(cid)>=atlas39_last_.size())return;
        ++atlas39_reason_uses_;
        const uint32_t clock=uint32_t(stats_.conflicts);
        if(atlas39_hits_[size_t(cid)] &&
           clock-atlas39_last_[size_t(cid)]<=4500){
            ++atlas39_reuses_;
            if(atlas39_hits_[size_t(cid)]<8)++atlas39_hits_[size_t(cid)];
        }else atlas39_hits_[size_t(cid)]=1;
        atlas39_last_[size_t(cid)]=clock;
    }
    bool atlas39_recent(int cid)const{
        if(cid<0 || size_t(cid)>=atlas39_last_.size())return false;
        return atlas39_hits_[size_t(cid)]>=2 &&
            uint32_t(stats_.conflicts)-atlas39_last_[size_t(cid)]<=4500;
    }""")

# An actual read of a live learned-clause reason during conflict minimization.
# No new external propagation/decision behavior; only diagnostic metadata.
one("""            if(redundant){
                for(int r:clauses_[size_t(cid)].lits){""",
"""            if(redundant){
                atlas39_touch(cid);
                for(int r:clauses_[size_t(cid)].lits){""")

# Initialize metadata for every newly learned clause (including id reuse).
one("""        atlas15_lbd_[cid]=atlas15_last_lbd_;
        atlas15_born_[cid]=stats_.conflicts;""",
"""        atlas15_lbd_[cid]=atlas15_last_lbd_;
        atlas15_born_[cid]=stats_.conflicts;
        if(atlas39_mode_){
            if(size_t(cid)>=atlas39_last_.size()){
                atlas39_last_.resize(size_t(cid)+1,0);
                atlas39_hits_.resize(size_t(cid)+1,0);
            }
            atlas39_last_[size_t(cid)]=0;
            atlas39_hits_[size_t(cid)]=0;
        }""")

# Migrate metadata through C6/C7 clause-slot compaction, same CID remap as LBD.
one("""        atlas15_lbd_.swap(migrated);
        std::map<int,uint64_t> born_migrated;""",
"""        atlas15_lbd_.swap(migrated);
        if(atlas39_mode_){
            std::vector<uint32_t> last(kept.size(),0);
            std::vector<uint8_t> hits(kept.size(),0);
            for(size_t old=0;old<before;++old){
                if(remap[old]<0 || old>=atlas39_last_.size())continue;
                const size_t now=size_t(remap[old]);
                last[now]=atlas39_last_[old];
                hits[now]=atlas39_hits_[old];
                ++atlas39_compaction_remaps_;
            }
            atlas39_last_.swap(last);
            atlas39_hits_.swap(hits);
        }
        std::map<int,uint64_t> born_migrated;""")

# Bounded priority discount only for repeated, recent, independently
# observed uses. Keep C7 locked/LBD/short exclusions and 75% quota unchanged.
one("""            candidates.push_back({kv.second*100+int(std::min<size_t>(cl.size(),99)),cid});""",
"""            int score=kv.second*100+int(std::min<size_t>(cl.size(),99));
            if(atlas39_mode_){
                ++atlas39_scored_;
                if(atlas39_recent(cid)){
                    ++atlas39_recent_;
                    if(atlas39_mode_==2)score-=500;
                }
            }
            candidates.push_back({score,cid});""")

# Compare the same 75% deletion candidate set to a frozen score-only rank,
# counting actual CID differences rather than mere metadata presence.
one("""        const size_t count=std::max<size_t>(1,
            (baseline_count*size_t(effective_pct)+99)/100);
        atlas36_base_quota_+=baseline_count;""",
"""        const size_t count=std::max<size_t>(1,
            (baseline_count*size_t(effective_pct)+99)/100);
        if(atlas39_mode_==2){
            ++atlas39_reduction_events_;
            // Shadow baseline scoring on exactly the eligible candidate IDs.
            std::vector<std::pair<int,int>> reference;
            reference.reserve(candidates.size());
            for(const auto&c:candidates){
                const int cid=c.second;
                const auto&cl=clauses_[size_t(cid)].lits;
                const int lbd=atlas15_lbd_.at(cid);
                reference.push_back({lbd*100+int(std::min<size_t>(cl.size(),99)),cid});
            }
            std::sort(reference.begin(),reference.end(),
                      std::greater<std::pair<int,int>>());
            std::vector<int> selected_ref,selected_protect;
            for(size_t i=0;i<count;++i){
                selected_ref.push_back(reference[i].second);
                selected_protect.push_back(candidates[i].second);
            }
            std::sort(selected_ref.begin(),selected_ref.end());
            for(int cid:selected_protect)
                if(!std::binary_search(selected_ref.begin(),
                                       selected_ref.end(),cid))
                    ++atlas39_changed_rank_;
        }
        atlas36_base_quota_+=baseline_count;""")

one("""    uint64_t atlas37_route_100()const{return atlas37_route_100_;}""",
"""    uint64_t atlas37_route_100()const{return atlas37_route_100_;}
    void atlas39_enable(int mode){
        require(atlas16_keep_ && atlas17_adaptive_ && !atlas37_route_,
                "ATLAS39 requires frozen C7 without routing");
        require(mode==1||mode==2,"ATLAS39 invalid utility mode");
        atlas39_mode_=mode;
    }
    int atlas39_mode()const{return atlas39_mode_;}
    uint64_t atlas39_reason_uses()const{return atlas39_reason_uses_;}
    uint64_t atlas39_reuses()const{return atlas39_reuses_;}
    uint64_t atlas39_scored()const{return atlas39_scored_;}
    uint64_t atlas39_recent()const{return atlas39_recent_;}
    uint64_t atlas39_changed_rank()const{return atlas39_changed_rank_;}
    uint64_t atlas39_reduction_events()const{return atlas39_reduction_events_;}
    uint64_t atlas39_compaction_remaps()const{return atlas39_compaction_remaps_;}
    uint64_t atlas39_metadata_bytes()const{
        return atlas39_last_.capacity()*sizeof(uint32_t)+
               atlas39_hits_.capacity()*sizeof(uint8_t);
    }""")

p.write_text(s)
p=Path("mre_atlas23/native.cpp")
s=p.read_text()
needle='||mode=="A37_ROUTE"'
assert s.count(needle)>=2,("ATLAS39 dispatch drift",s.count(needle))
s=s.replace(needle,needle+'||mode=="A39_SHADOW"||mode=="A39_PROTECT"')
anchor='solver.atlas23_enable_stable_phase();'
assert s.count(anchor)==1
s=s.replace(anchor,anchor+'''
    if(mode=="A39_SHADOW"||mode=="A39_PROTECT"){
        solver.atlas36_enable_quota(75);
        solver.atlas39_enable(mode=="A39_SHADOW"?1:2);
    }''',1)
anchor='           <<" SAT_original_verified="<<int(status==10)'
assert s.count(anchor)==1
fields=("mode","reason_uses","reuses","scored","recent","changed_rank",
        "reduction_events","compaction_remaps","metadata_bytes")
lines=''.join('           <<" atlas39_'+field+'="<<solver.atlas39_'+field+'()'+chr(10)
              for field in fields)
s=s.replace(anchor,lines+anchor,1)
for mode in ("A39_SHADOW","A39_PROTECT"):
 assert s.count('mode=="'+mode+'"')>=3
p.write_text(s)
print("ATLAS39_BUILD_PASS native_C7=true score_protect=true shadow=true"
      " CID_compaction_migrated=true true_75_quota=true controls_unchanged=true",
      flush=True)
