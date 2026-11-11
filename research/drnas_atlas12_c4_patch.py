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
src=src.replace(anchor,'''    // ATLAS12-C: deliberately explore non-maximal CDCL branching variables.
    // All assignments are still ordinary CDCL decisions, not forced implications.
    bool atlas12_c_enabled_ = false;
    bool atlas12_learning_ = true;
    uint64_t atlas12_rng_ = 0x9e3779b97f4a7c15ULL;
    uint64_t atlas12_explored_ = 0,atlas12_penalized_ = 0,atlas12_exploited_ = 0;
    uint64_t atlas12_last_conflicts_ = 0;
    uint64_t atlas12_last_decisions_ = 0;
    uint64_t atlas12_good_lbd_=0,atlas12_bad_lbd_=0;
    std::vector<double> atlas12_quality_;
    void atlas12_clause_feedback(const std::vector<int>& clause) {
        if(!atlas12_c_enabled_||!atlas12_learning_)return;
        std::vector<int> levels;
        for(int lit:clause){int lev=levels_[std::abs(lit)];if(std::find(levels.begin(),levels.end(),lev)==levels.end())levels.push_back(lev);}
        const int lbd=int(levels.size());
        if(atlas12_quality_.empty())atlas12_quality_.assign(size_t(n_)+1,0.0);
        const bool good=lbd<=3&&clause.size()<=8;
        if(good)++atlas12_good_lbd_;else ++atlas12_bad_lbd_;
        // Reward decisions that produced useful low-LBD 1-UIP clauses.
        const int v=atlas12_last_decision_var_;
        if(v>0&&v<=n_)atlas12_quality_[size_t(v)]=0.94*atlas12_quality_[size_t(v)]+(good?0.20:-0.10);
    }
    int atlas12_last_decision_var_ = 0;
    std::vector<double> atlas12_penalty_;
    uint64_t atlas12_next() {
        atlas12_rng_ ^= atlas12_rng_ >> 12;
        atlas12_rng_ ^= atlas12_rng_ << 25;
        atlas12_rng_ ^= atlas12_rng_ >> 27;
        return atlas12_rng_ * 2685821657736338717ULL;
    }
    void atlas12_feedback(int variable) {
        if(!atlas12_c_enabled_ || !atlas12_learning_ || variable<1 || variable>n_)return;
        if(atlas12_penalty_.empty())atlas12_penalty_.assign(size_t(n_)+1,0.0);
        // Feedback from actual CDCL conflicts since previous decision.
        const uint64_t delta=stats_.conflicts-atlas12_last_conflicts_;
        const uint64_t steps=stats_.decisions-atlas12_last_decisions_;
        double &p=atlas12_penalty_[size_t(variable)];
        p=0.90*p+(delta?1.0:-0.10);
        if(delta)++atlas12_penalized_;
        atlas12_last_conflicts_=stats_.conflicts;
        atlas12_last_decisions_=stats_.decisions;
    }
    int atlas12_pick_branch_variable() {
        if(heap_.empty())return 0;
        // Explore about 25% initially, annealing to 5% after 512 decisions.
        const uint64_t threshold=stats_.decisions<512?250:50;
        if(heap_.size()>1 && atlas12_next()%1000<threshold) {
            const size_t window=std::min<size_t>(heap_.size(),32);
            size_t best=0;
            double score=-1e100;
            // Sample up to 8 arbitrary heap slots; deliberately override VSIDS.
            for(int i=0;i<8;++i){
                const size_t pos=size_t(atlas12_next()%window);
                const int v=heap_[pos];
                if(values_[v])continue;
                const double normalized_activity=activity_[v]/std::max(1e-12,activity_[heap_[0]]);
                const double penalty=atlas12_learning_&&!atlas12_penalty_.empty()?atlas12_penalty_[size_t(v)]:0.0;
                const double quality=atlas12_learning_&&!atlas12_quality_.empty()?atlas12_quality_[size_t(v)]:0.0;
                const double candidate=normalized_activity-0.40*penalty+0.85*quality+0.1*double(atlas12_next()%1000)/1000.0;
                if(candidate>score){score=candidate;best=pos;}
            }
            if(best>0){
                ++atlas12_explored_;
                return heap_[best];
            }
        }
        ++atlas12_exploited_;
        return pick_branch_variable();
    }
public:
    void atlas12_enable_c(uint64_t seed,bool learning=true) {
        atlas12_learning_=learning;
        atlas12_c_enabled_=true;
        atlas12_rng_=seed?seed:0x9e3779b97f4a7c15ULL;
        atlas12_penalty_.assign(size_t(n_)+1,0.0);
        atlas12_quality_.assign(size_t(n_)+1,0.0);
    }
    uint64_t atlas12_explorations() const {return atlas12_explored_;}
    uint64_t atlas12_penalties() const {return atlas12_penalized_;}
    uint64_t atlas12_good_lbd() const {return atlas12_good_lbd_;}
    uint64_t atlas12_bad_lbd() const {return atlas12_bad_lbd_;}
private:
''' +anchor)
needle="                const int v = pick_branch_variable();"
assert src.count(needle)==1
src=src.replace(needle,"                if(atlas12_c_enabled_ && atlas12_last_decision_var_)atlas12_feedback(atlas12_last_decision_var_);\n                const int v = atlas12_c_enabled_ ? atlas12_pick_branch_variable() : pick_branch_variable();\n                if(atlas12_c_enabled_ && v)atlas12_last_decision_var_=v;")
# CDCL phases are optionally flipped as exploratory decisions, never as forced facts.
needle2="                require(enqueue(phases_[v] >= 0 ? v : -v, -1),"
assert src.count(needle2)==1
src=src.replace(needle2,"                if(atlas12_c_enabled_ && (atlas12_next()%1000)<100)phases_[v]=-phases_[v];\n"+needle2)
needle3="                auto [learned, target] = analyze(conflicting);"
assert src.count(needle3)==1
src=src.replace(needle3,needle3+"\n                atlas12_clause_feedback(learned);")
dest=pathlib.Path("mre_atlas12/drnas_native_core_c.hpp")
dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(src)
print("ATLAS12_C_PATCH_PASS generated",dest,"source_bytes",len(src))
