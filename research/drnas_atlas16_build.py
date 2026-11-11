#!/usr/bin/env python3
"""ATLAS16: isolated, conservative learned-clause retention patch over ATLAS15.

No modification of the frozen ATLAS15 source tree. Produces generated C++ only.
C5_CDCL remains the legacy control; C6_KEEP uses 1/8 high-LBD removal with
safe clause-slot compaction and ID remapping for watches and reasons.
"""
from pathlib import Path

root=Path("mre_atlas16")
root.mkdir(exist_ok=True)
s=Path("mre_atlas15/drnas_native_core_c.hpp").read_text()

def one(a,b):
    global s
    assert s.count(a)==1,(a,s.count(a))
    s=s.replace(a,b,1)

one("    bool atlas15_enabled_=false;",
"""    bool atlas15_enabled_=false;
    bool atlas16_keep_=false;
    uint64_t atlas16_compactions_=0,atlas16_reclaimed_slots_=0;
    uint64_t atlas16_reclaimed_capacity_bytes_=0;""")
one("    void atlas15_reduce_db(){",
"""    void atlas16_compact(){
        const size_t before=clauses_.size();
        std::vector<int> remap(before,-1);
        std::vector<drnas::Clause> kept;
        kept.reserve(before);
        for(size_t i=0;i<before;++i){
            if(clauses_[i].lits.empty())continue;
            remap[i]=int(kept.size());
            kept.push_back(std::move(clauses_[i]));
        }
        if(kept.size()==before)return;
        for(int v=1;v<=n_;++v)
            if(reasons_[v]>=0){
                require(size_t(reasons_[v])<before && remap[size_t(reasons_[v])]>=0,
                        "compaction attempted to drop a live implication reason");
                reasons_[v]=remap[size_t(reasons_[v])];
            }
        std::map<int,int> migrated;
        for(auto kv:atlas15_lbd_){
            require(kv.first>=0 && size_t(kv.first)<before &&
                    remap[size_t(kv.first)]>=0,"LBD index maps to deleted clause");
            migrated[remap[size_t(kv.first])]]=kv.second;
        }
        atlas15_lbd_.swap(migrated);
        const size_t old_capacity=clauses_.capacity();
        std::vector<drnas::Clause>(std::move(kept)).swap(clauses_);
        for(auto &w:watches_)std::vector<typename std::remove_reference<decltype(w)>::type::value_type>().swap(w);
        for(size_t cid=0;cid<clauses_.size();++cid)attach(int(cid));
        ++atlas16_compactions_;
        atlas16_reclaimed_slots_+=before-clauses_.size();
        if(old_capacity>clauses_.capacity())
            atlas16_reclaimed_capacity_bytes_+=(old_capacity-clauses_.capacity())*sizeof(drnas::Clause);
    }
    void atlas16_reduce_db(){
        ++atlas15_reductions_;
        std::vector<uint8_t> locked(clauses_.size(),0);
        for(int v=1;v<=n_;++v)
            if(values_[v] && reasons_[v]>=0 &&
               size_t(reasons_[v])<locked.size())locked[size_t(reasons_[v])]=1;
        std::vector<std::pair<int,int>> candidates;
        for(const auto&kv:atlas15_lbd_){
            const int cid=kv.first;
            require(cid>=0&&size_t(cid)<clauses_.size(),"invalid learned clause ID");
            const auto&cl=clauses_[size_t(cid)].lits;
            // Preserve glue clauses, binaries, recent low-LBD information and all reasons.
            if(locked[size_t(cid)] || kv.second<7 || cl.size()<4)continue;
            candidates.push_back({kv.second*100+int(std::min<size_t>(cl.size(),99)),cid});
        }
        if(candidates.size()<48)return;
        std::sort(candidates.begin(),candidates.end(),std::greater<std::pair<int,int>>());
        // Conservative 12.5% of eligible poor clauses, not 50% every 500 conflicts.
        const size_t count=std::max<size_t>(1,candidates.size()/8);
        for(size_t i=0;i<count;++i){
            const int cid=candidates[i].second;
            auto&cl=clauses_[size_t(cid)].lits;
            const int a=watch_index(cl[0]),b=watch_index(cl[1]);
#ifdef DRNAS_ONE2_BLOCKER
            for(int w:{a,b}){
                auto&entries=watches_[size_t(w)];
                entries.erase(std::remove_if(entries.begin(),entries.end(),
                    [cid](const WatchEntry&x){return x.cid==cid;}),entries.end());
            }
#else
            for(int w:{a,b}){
                auto&entries=watches_[size_t(w)];
                entries.erase(std::remove(entries.begin(),entries.end(),cid),entries.end());
            }
#endif
            std::vector<int>().swap(cl);
            atlas15_lbd_.erase(cid);
            ++atlas15_deleted_;
        }
        const size_t tombstones=clauses_.size()-
            std::count_if(clauses_.begin(),clauses_.end(),
                          [](const drnas::Clause& c){return !c.lits.empty();});
        if(tombstones>=64 && tombstones*10>=clauses_.size())
            atlas16_compact();
    }
    void atlas15_reduce_db(){
        if(atlas16_keep_){atlas16_reduce_db();return;}""")
one("    void atlas15_enable_cdcl(){atlas15_enabled_=true;}",
"""    void atlas15_enable_cdcl(){atlas15_enabled_=true;}
    void atlas16_enable_keep(){require(atlas15_enabled_,"enable CDCL first");atlas16_keep_=true;}
    uint64_t atlas16_compactions()const{return atlas16_compactions_;}
    uint64_t atlas16_reclaimed_slots()const{return atlas16_reclaimed_slots_;}
    uint64_t atlas16_reclaimed_capacity_bytes()const{return atlas16_reclaimed_capacity_bytes_;}
    uint64_t atlas16_clause_slots()const{return clauses_.size();}
    uint64_t atlas16_clause_tombstones()const{
        return std::count_if(clauses_.begin(),clauses_.end(),
            [](const drnas::Clause&c){return c.lits.empty();});
    }
    uint64_t atlas16_allocated_clause_bytes()const{
        uint64_t bytes=clauses_.capacity()*sizeof(drnas::Clause);
        for(const auto&c:clauses_)bytes+=c.lits.capacity()*sizeof(int);
        for(const auto&w:watches_)bytes+=w.capacity()*sizeof(w.front());
        return bytes;
    }""")
one("if(atlas15_enabled_ && stats_.conflicts%500==0)atlas15_reduce_db();",
    "if(atlas15_enabled_ && stats_.conflicts%(atlas16_keep_?1500:500)==0)atlas15_reduce_db();")
one("clauses_.size()-atlas15_deleted_ > 1500000",
    "(atlas16_keep_?clauses_.size():clauses_.size()-atlas15_deleted_) > 1500000")
# Include type_traits for the container element type when rebuilding watch lists.
s=s.replace("#include <vector>","#include <vector>\n#include <type_traits>",1)
(root/"drnas_native_core_c.hpp").write_text(s)

src=Path("research/drnas_atlas15_native.cpp").read_text()
assert src.count('mode=="C5_CDCL"')>=2
assert src.count('mode=="C5_CDCL_GAUSS"')>=2
src=src.replace('mode=="C5_CDCL_GAUSS"', 'mode=="C5_CDCL_GAUSS"||mode=="C6_KEEP_GAUSS"')
src=src.replace('mode=="C5_CDCL"', 'mode=="C5_CDCL"||mode=="C6_KEEP"')
target='solver.atlas15_enable_cdcl();'
assert src.count(target)==1
src=src.replace(target,target+'\n    if(mode=="C6_KEEP"||mode=="C6_KEEP_GAUSS")solver.atlas16_enable_keep();',1)
src=src.replace('#include <sstream>','#include <sstream>\n#include <sys/resource.h>',1)
anchor='           <<" SAT_original_verified="<<int(status==10)'
assert src.count(anchor)==1
src=src.replace(anchor,
'''           <<" atlas16_compactions="<<solver.atlas16_compactions()
           <<" atlas16_reclaimed_slots="<<solver.atlas16_reclaimed_slots()
           <<" atlas16_reclaimed_capacity_bytes="<<solver.atlas16_reclaimed_capacity_bytes()
           <<" atlas16_clause_slots="<<solver.atlas16_clause_slots()
           <<" atlas16_tombstones="<<solver.atlas16_clause_tombstones()
           <<" atlas16_clause_alloc_bytes="<<solver.atlas16_allocated_clause_bytes()
           <<" atlas16_maxrss_kb="<<([](){struct rusage ru{};return getrusage(RUSAGE_SELF,&ru)==0?ru.ru_maxrss:0L;}())
''' +anchor,1)
(root/"native.cpp").write_text(src)
print("ATLAS16_BUILD_PATCH_PASS source_clauses_preserved=true C5_legacy_control=true conservative_C6_keep=true")
