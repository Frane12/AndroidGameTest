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
src=src.replace(anchor,'''    // ATLAS13-C: deliberately explore non-maximal CDCL branching variables.
    // All assignments are still ordinary CDCL decisions, not forced implications.
    bool atlas13_c_enabled_ = false;
    bool atlas13_learning_ = true;
    bool atlas13_lbd_enabled_ = false;
    double atlas13_prior_explore_ = 1.0;
    double atlas13_prior_quality_ = 0.85;
    uint64_t atlas13_rng_ = 0x9e3779b97f4a7c15ULL;
    uint64_t atlas13_explored_ = 0,atlas13_penalized_ = 0,atlas13_exploited_ = 0;
    uint64_t atlas13_last_conflicts_ = 0;
    uint64_t atlas13_last_decisions_ = 0;
    uint64_t atlas13_good_lbd_=0,atlas13_bad_lbd_=0;
    std::vector<double> atlas13_quality_;
    void atlas13_clause_feedback(const std::vector<int>& clause) {
        if(!atlas13_c_enabled_||!atlas13_learning_||!atlas13_lbd_enabled_)return;
        std::vector<int> levels;
        for(int lit:clause){int lev=levels_[std::abs(lit)];if(std::find(levels.begin(),levels.end(),lev)==levels.end())levels.push_back(lev);}
        const int lbd=int(levels.size());
        if(atlas13_quality_.empty())atlas13_quality_.assign(size_t(n_)+1,0.0);
        const bool good=lbd<=3&&clause.size()<=8;
        if(good)++atlas13_good_lbd_;else ++atlas13_bad_lbd_;
        // Reward decisions that produced useful low-LBD 1-UIP clauses.
        const int v=atlas13_last_decision_var_;
        if(v>0&&v<=n_)atlas13_quality_[size_t(v)]=0.94*atlas13_quality_[size_t(v)]+(good?0.20:-0.10);
    }
    int atlas13_last_decision_var_ = 0;
    std::vector<double> atlas13_penalty_;
    uint64_t atlas13_next() {
        atlas13_rng_ ^= atlas13_rng_ >> 12;
        atlas13_rng_ ^= atlas13_rng_ << 25;
        atlas13_rng_ ^= atlas13_rng_ >> 27;
        return atlas13_rng_ * 2685821657736338717ULL;
    }
    void atlas13_feedback(int variable) {
        if(!atlas13_c_enabled_ || !atlas13_learning_ || variable<1 || variable>n_)return;
        if(atlas13_penalty_.empty())atlas13_penalty_.assign(size_t(n_)+1,0.0);
        // Feedback from actual CDCL conflicts since previous decision.
        const uint64_t delta=stats_.conflicts-atlas13_last_conflicts_;
        const uint64_t steps=stats_.decisions-atlas13_last_decisions_;
        double &p=atlas13_penalty_[size_t(variable)];
        p=0.90*p+(delta?1.0:-0.10);
        if(delta)++atlas13_penalized_;
        atlas13_last_conflicts_=stats_.conflicts;
        atlas13_last_decisions_=stats_.decisions;
    }
    int atlas13_pick_branch_variable() {
        if(heap_.empty())return 0;
        // Explore about 25% initially, annealing to 5% after 512 decisions.
        const uint64_t threshold=uint64_t(std::min(900.0,(stats_.decisions<512?250.0:50.0)*atlas13_prior_explore_));
        if(heap_.size()>1 && atlas13_next()%1000<threshold) {
            const size_t window=std::min<size_t>(heap_.size(),32);
            size_t best=0;
            double score=-1e100;
            // Sample up to 8 arbitrary heap slots; deliberately override VSIDS.
            for(int i=0;i<8;++i){
                const size_t pos=size_t(atlas13_next()%window);
                const int v=heap_[pos];
                if(values_[v])continue;
                const double normalized_activity=activity_[v]/std::max(1e-12,activity_[heap_[0]]);
                const double penalty=atlas13_learning_&&!atlas13_penalty_.empty()?atlas13_penalty_[size_t(v)]:0.0;
                const double quality=atlas13_lbd_enabled_&&!atlas13_quality_.empty()?atlas13_quality_[size_t(v)]:0.0;
                const double candidate=normalized_activity-0.40*penalty+atlas13_prior_quality_*quality+0.1*double(atlas13_next()%1000)/1000.0;
                if(candidate>score){score=candidate;best=pos;}
            }
            if(best>0){
                ++atlas13_explored_;
                return heap_[best];
            }
        }
        ++atlas13_exploited_;
        return pick_branch_variable();
    }
public:
    void atlas13_enable_c(uint64_t seed,bool learning=true,bool lbd=false) {
        atlas13_lbd_enabled_=lbd;
        atlas13_learning_=learning;
        atlas13_c_enabled_=true;
        atlas13_rng_=seed?seed:0x9e3779b97f4a7c15ULL;
        atlas13_penalty_.assign(size_t(n_)+1,0.0);
        atlas13_quality_.assign(size_t(n_)+1,0.0);
    }
    void atlas13_warmstart(double explore,double quality) {
        // Bounded policy parameters from a disjoint training cohort; never import assignments.
        atlas13_prior_explore_=std::max(0.25,std::min(2.0,explore));
        atlas13_prior_quality_=std::max(0.0,std::min(2.0,quality));
    }
    uint64_t atlas13_explorations() const {return atlas13_explored_;}
    uint64_t atlas13_penalties() const {return atlas13_penalized_;}
    uint64_t atlas13_good_lbd() const {return atlas13_good_lbd_;}
    uint64_t atlas13_bad_lbd() const {return atlas13_bad_lbd_;}
private:
''' +anchor)
needle="                const int v = pick_branch_variable();"
assert src.count(needle)==1
src=src.replace(needle,"                if(atlas13_c_enabled_ && atlas13_last_decision_var_)atlas13_feedback(atlas13_last_decision_var_);\n                const int v = atlas13_c_enabled_ ? atlas13_pick_branch_variable() : pick_branch_variable();\n                if(atlas13_c_enabled_ && v)atlas13_last_decision_var_=v;")
# CDCL phases are optionally flipped as exploratory decisions, never as forced facts.
needle2="                require(enqueue(phases_[v] >= 0 ? v : -v, -1),"
assert src.count(needle2)==1
src=src.replace(needle2,"                if(atlas13_c_enabled_ && (atlas13_next()%1000)<100)phases_[v]=-phases_[v];\n"+needle2)
needle3="                auto [learned, target] = analyze(conflicting);"
assert src.count(needle3)==1
src=src.replace(needle3,needle3+"\n                atlas13_clause_feedback(learned);")
dest=pathlib.Path("mre_atlas15/drnas_native_core_c.hpp")
dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(src)
print("ATLAS13_C_PATCH_PASS generated",dest,"source_bytes",len(src))
