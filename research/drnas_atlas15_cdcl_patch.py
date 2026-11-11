#!/usr/bin/env python3
"""ATLAS15 C5_CDCL only: guarded clause minimization, LBD reduction,
quality-controlled restart, adaptive branching and phase. Proof-first.
Runs after the warm patch; changes do not affect the A/C3/C4 controls.
"""
from pathlib import Path
p=Path("mre_atlas15/drnas_native_core_c.hpp")
s=p.read_text()
def one(a,b):
 global s
 assert s.count(a)==1,(a,s.count(a))
 s=s.replace(a,b)
one("    int pick_branch_variable() {", r'''
    bool atlas15_enabled_=false;
    uint64_t atlas15_deleted_=0,atlas15_minimized_=0,atlas15_reductions_=0;
    uint64_t atlas15_last_restart_=0;
    int atlas15_last_lbd_=4;
    double atlas15_short_lbd_=4.0,atlas15_long_lbd_=4.0;
    std::map<int,int> atlas15_lbd_;
    std::map<int,uint64_t> atlas15_born_;
    uint64_t atlas15_last_reduce_=0;
    uint64_t atlas15_live_learned_=0;
    uint64_t atlas15_peak_live_=0;
    int atlas15_compute_lbd(const std::vector<int>&cl) const {
        std::set<int> levels;
        for(int lit:cl)if(levels_[var(lit)]>0)levels.insert(levels_[var(lit)]);
        return std::max(1,int(levels.size()));
    }
    void atlas15_minimize(std::vector<int>&cl,int&target){
        if(!atlas15_enabled_)return;
        std::set<int> active(cl.begin(),cl.end());
        // Conservative 1-level implication graph elimination via resolution:
        // other literals of the reason must remain in learned or be root false.
        for(size_t i=1;i<cl.size();){
            const int lit=cl[i],cid=reasons_[var(lit)];
            bool redundant=cid>=0 && cid<int(clauses_.size()) &&
                !clauses_[size_t(cid)].lits.empty();
            if(redundant){
                for(int r:clauses_[size_t(cid)].lits){
                    if(r==-lit || levels_[var(r)]==0)continue;
                    if(!active.count(r)){redundant=false;break;}
                }
            }
            if(redundant){
                active.erase(lit);
                cl.erase(cl.begin()+i);
                ++atlas15_minimized_;
            }else ++i;
        }
        target=0;
        if(cl.size()>=2){
            size_t best=1;
            for(size_t i=2;i<cl.size();++i)
                if(levels_[var(cl[i])]>levels_[var(cl[best])])best=i;
            std::swap(cl[1],cl[best]);
            target=levels_[var(cl[1])];
        }
        atlas15_last_lbd_=atlas15_compute_lbd(cl);
        atlas15_short_lbd_=.94*atlas15_short_lbd_+.06*atlas15_last_lbd_;
        atlas15_long_lbd_=.995*atlas15_long_lbd_+.005*atlas15_last_lbd_;
    }
    void atlas15_onlearn(int cid){
        if(!atlas15_enabled_)return;
        atlas15_lbd_[cid]=atlas15_last_lbd_;
        atlas15_born_[cid]=stats_.conflicts;
        ++atlas15_live_learned_;
        atlas15_peak_live_=std::max(atlas15_peak_live_,atlas15_live_learned_);
        atlas13_prior_explore_=std::max(.25,std::min(2.0,
          atlas13_prior_explore_*(atlas15_short_lbd_>atlas15_long_lbd_?1.0008:.9996)));
    }
    void atlas15_reduce_db(){
        if(!atlas15_enabled_)return;
        if(stats_.conflicts<atlas15_last_reduce_+10000)return;
        atlas15_last_reduce_=stats_.conflicts;
        ++atlas15_reductions_;
        if(atlas15_live_learned_<20000)return;
        std::vector<uint8_t> locked(clauses_.size(),0);
        for(int v=1;v<=n_;++v)
            if(values_[v] && reasons_[v]>=0 && reasons_[v]<int(locked.size()))
                locked[size_t(reasons_[v])]=1;
        std::vector<std::pair<int,int>> candidates;
        for(const auto&kv:atlas15_lbd_){
            int cid=kv.first;
            const auto&c=clauses_[size_t(cid)].lits;
            auto born=atlas15_born_.find(cid);
            if(locked[size_t(cid)]||kv.second<=5||c.size()<=3||
               born==atlas15_born_.end()||
               stats_.conflicts-born->second<20000)continue;
            candidates.push_back({kv.second*100+int(std::min<size_t>(c.size(),99)),cid});
        }
        if(candidates.size()<1000)return;
        std::sort(candidates.begin(),candidates.end(),std::greater<std::pair<int,int>>());
        const size_t quota=std::min(candidates.size()/4,
            std::min<size_t>(atlas15_live_learned_/10,atlas15_live_learned_-20000));
        for(size_t i=0;i<quota;++i){
            int cid=candidates[i].second;
            auto&c=clauses_[size_t(cid)].lits;
            const int wa=watch_index(c[0]),wb=watch_index(c[1]);
#ifdef DRNAS_ONE2_BLOCKER
            for(int w:{wa,wb}){
                auto&watch=watches_[size_t(w)];
                watch.erase(std::remove_if(watch.begin(),watch.end(),[cid](const WatchEntry&e){
                    return e.cid==cid;}),watch.end());
            }
#else
            for(int w:{wa,wb}){
                auto&watch=watches_[size_t(w)];
                watch.erase(std::remove(watch.begin(),watch.end(),cid),watch.end());
            }
#endif
            std::vector<int>().swap(c);
            atlas15_lbd_.erase(cid);
            atlas15_born_.erase(cid);
            --atlas15_live_learned_;
            ++atlas15_deleted_;
        }
    }
    bool atlas15_restart_due()const{
        if(stats_.conflicts<atlas15_last_restart_+80)return false;
        return atlas15_short_lbd_>atlas15_long_lbd_*1.15 ||
               stats_.conflicts>=atlas15_last_restart_+1500;
    }
public:
    void atlas15_enable_cdcl(){atlas15_enabled_=true;}
    uint64_t atlas15_deleted()const{return atlas15_deleted_;}
    uint64_t atlas15_minimized()const{return atlas15_minimized_;}
    uint64_t atlas15_reductions()const{return atlas15_reductions_;}
    uint64_t atlas15_live_learned()const{return atlas15_live_learned_;}
    uint64_t atlas15_peak_live()const{return atlas15_peak_live_;}
private:
    int pick_branch_variable() {''')
one("                atlas13_clause_feedback(learned);",
    "                atlas15_minimize(learned,target);\n                atlas13_clause_feedback(learned);")
one("                ++stats_.learned_clauses;\n                require(enqueue(assertion, cid),",
    "                ++stats_.learned_clauses;\n                atlas15_onlearn(cid);\n                require(enqueue(assertion, cid),")
one("                if (stats_.conflicts >= next_restart_ && level() > 0) {",
    "                if(atlas15_enabled_ && stats_.conflicts%10000==0)atlas15_reduce_db();\n                if(level()>0 && (atlas15_enabled_?atlas15_restart_due():stats_.conflicts>=next_restart_)) {")
one("                    ++stats_.restarts;\n                    restart_window_ =",
    "                    ++stats_.restarts;\n                    if(atlas15_enabled_)atlas15_last_restart_=stats_.conflicts;\n                    restart_window_ =")
one("                if(atlas13_c_enabled_ && (atlas13_next()%1000)<100)phases_[v]=-phases_[v];",
    "                if(atlas13_c_enabled_ && (atlas13_next()%1000)<(atlas15_enabled_?(atlas15_short_lbd_>atlas15_long_lbd_?140:40):100))phases_[v]=-phases_[v];")
one("            if (clauses_.size() > 1500000 || stats_.learned_clauses > 500000) {",
    "            if (clauses_.size()-atlas15_deleted_ > 1500000 || atlas15_live_learned_ > 500000) {")
p.write_text(s)
print("ATLAS15_CDCL_PATCH_PASS",len(s))
