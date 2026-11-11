#!/usr/bin/env python3
"""Generate native C++ CDCL C arm with bounded epsilon-greedy branching.
Decision selection remains sound: never overrides propagation or learned clauses.
Local feedback: short conflict-distance reward/penalty updates a persistent
per-variable score only within a solve. No unverified cross-run learning claim.
"""
import pathlib
src=pathlib.Path("research/drnas_native_core_r3c.cpp").read_text()
anchor="    int pick_branch_variable() {\n"
assert src.count(anchor)==1
src=src.replace(anchor,'''    // ATLAS10-C: deliberately explore non-maximal CDCL branching variables.
    // All assignments are still ordinary CDCL decisions, not forced implications.
    bool atlas10_c_enabled_ = false;
    uint64_t atlas10_rng_ = 0x9e3779b97f4a7c15ULL;
    uint64_t atlas10_explored_ = 0,atlas10_penalized_ = 0,atlas10_exploited_ = 0;
    uint64_t atlas10_last_conflicts_ = 0;
    int atlas10_last_decision_var_ = 0;
    std::vector<double> atlas10_penalty_;
    uint64_t atlas10_next() {
        atlas10_rng_ ^= atlas10_rng_ >> 12;
        atlas10_rng_ ^= atlas10_rng_ << 25;
        atlas10_rng_ ^= atlas10_rng_ >> 27;
        return atlas10_rng_ * 2685821657736338717ULL;
    }
    void atlas10_feedback(int variable) {
        if(!atlas10_c_enabled_ || variable<1 || variable>n_)return;
        if(atlas10_penalty_.empty())atlas10_penalty_.assign(size_t(n_)+1,0.0);
        // Feedback from actual CDCL conflicts since previous decision.
        const uint64_t delta=stats_.conflicts-atlas10_last_conflicts_;
        double &p=atlas10_penalty_[size_t(variable)];
        p=0.90*p+(delta?1.0:-0.05);
        if(delta)++atlas10_penalized_;
        atlas10_last_conflicts_=stats_.conflicts;
    }
    int atlas10_pick_branch_variable() {
        if(heap_.empty())return 0;
        // Explore about 25% initially, annealing to 5% after 512 decisions.
        const uint64_t threshold=stats_.decisions<512?250:50;
        if(heap_.size()>1 && atlas10_next()%1000<threshold) {
            const size_t window=std::min<size_t>(heap_.size(),32);
            size_t best=0;
            double score=-1e100;
            // Sample up to 8 arbitrary heap slots; deliberately override VSIDS.
            for(int i=0;i<8;++i){
                const size_t pos=size_t(atlas10_next()%window);
                const int v=heap_[pos];
                if(values_[v])continue;
                const double candidate=activity_[v]-(atlas10_penalty_.empty()?0:atlas10_penalty_[size_t(v)])+
                    double(atlas10_next()%1000)/1000.0;
                if(candidate>score){score=candidate;best=pos;}
            }
            if(best>0){
                ++atlas10_explored_;
                return heap_[best];
            }
        }
        ++atlas10_exploited_;
        return pick_branch_variable();
    }
public:
    void atlas10_enable_c(uint64_t seed) {
        atlas10_c_enabled_=true;
        atlas10_rng_=seed?seed:0x9e3779b97f4a7c15ULL;
        atlas10_penalty_.assign(size_t(n_)+1,0.0);
    }
    uint64_t atlas10_explorations() const {return atlas10_explored_;}
    uint64_t atlas10_penalties() const {return atlas10_penalized_;}
private:
''' +anchor)
needle="                const int v = pick_branch_variable();"
assert src.count(needle)==1
src=src.replace(needle,"                const int v = atlas10_c_enabled_ ? atlas10_pick_branch_variable() : pick_branch_variable();\n                if(atlas10_c_enabled_ && v)atlas10_feedback(v);")
# CDCL phases are optionally flipped as exploratory decisions, never as forced facts.
needle2="                require(enqueue(phases_[v] >= 0 ? v : -v, -1),"
assert src.count(needle2)==1
src=src.replace(needle2,"                if(atlas10_c_enabled_ && (atlas10_next()%1000)<100)phases_[v]=-phases_[v];\n"+needle2)
dest=pathlib.Path("mre_atlas10/drnas_native_core_c.hpp")
dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(src)
print("ATLAS10_C_PATCH_PASS generated",dest,"source_bytes",len(src))
