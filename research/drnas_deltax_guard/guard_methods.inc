    // DELTAX-GUARD1. Speculative A/B uses TWO independent copies of the
    // exact same native-CDCL state. Neither probe is allowed to log proof,
    // rewrite the real trail or promote its SAT/UNSAT outcome.
    // Candidate correctness is a DIFFERENT gate: one-step original-source
    // resolution checked inside the algebra component before this callback.
    int64_t deltax_guard_calls_=0,deltax_guard_accept_=0;
    int64_t deltax_guard_reject_=0,deltax_guard_budget_reject_=0;
    int64_t deltax_guard_clone_inconsistency_=0,deltax_guard_events_=0;
    int64_t deltax_guard_total_base_dec_=0,deltax_guard_total_trial_dec_=0;
    int64_t deltax_guard_total_base_conf_=0,deltax_guard_total_trial_conf_=0;
    static constexpr int64_t deltax_guard_max_trials_=8;
    static constexpr int64_t deltax_guard_clone_max_decisions_=128;
    static constexpr int64_t deltax_guard_clone_max_conflicts_=96;
    static constexpr double deltax_guard_clone_wall_ms_=12.0;
    struct DeltaxGuardProbe {
        Result result=Result::UNKNOWN;
        int64_t decisions=0,conflicts=0,propagations=0;
    };
    DeltaxGuardProbe deltaxGuardProbe(const std::vector<int>& clause,bool trial) const {
        // Copy exactly this pre-insertion state. This is the same proven
        // clone mechanism already used by X46 shortProbeBranch.
        Solver cp(*this);
        cp.x46_clone_=true;
        cp.x46_enabled_=false;
        cp.proof_=nullptr;            // no speculative DRAT emissions
        cp.timeout_s_=0.0;            // bounded by strict clone budgets
        cp.x46_clone_origin_conflicts_=cp.stats_.conflicts;
        cp.x46_clone_origin_decisions_=cp.stats_.decisions;
        cp.x46_clone_conflict_cap_=deltax_guard_clone_max_conflicts_;
        cp.x46_clone_decision_cap_=deltax_guard_clone_max_decisions_;
        cp.x46_clone_wall_limit_ms_=deltax_guard_clone_wall_ms_;
        cp.x46_clone_started_=Clock::now();
        const int64_t before_dec=cp.stats_.decisions;
        const int64_t before_conf=cp.stats_.conflicts;
        const int64_t before_prop=cp.stats_.propagations;
        if(trial) {
            // The same component clause later enters main via the ordinary
            // checked CDCL bridge. Here it is only in a disposable copy.
            std::vector<int> candidate=clause;
            std::stable_sort(candidate.begin(),candidate.end(),[&](int a,int b){
                if((cp.value(a)==0)!=(cp.value(b)==0))return cp.value(a)==0;
                return cp.levels_[std::abs(a)-1]>cp.levels_[std::abs(b)-1];
            });
            bool sat=false;int free=0,unit=0;
            for(int lit:candidate) {
                const int v=cp.value(lit);
                if(v==1){sat=true;break;}
                if(v==0){++free;unit=lit;}
            }
            if(sat||free==0) return {};
            const int cid=cp.storeClause(std::move(candidate),true);
            ++cp.stats_.learnt;
            if(free==1 && !cp.enqueue(unit,cid))
                throw std::runtime_error("DELTAX_GUARD_CLONE_UNIT_FAILED");
        }
        const Result result=cp.solve();
        return {result,cp.stats_.decisions-before_dec,
                cp.stats_.conflicts-before_conf,
                cp.stats_.propagations-before_prop};
    }
    bool deltaxGuardApprove(const std::vector<int>& c) {
        ++deltax_guard_calls_;
        if(deltax_guard_calls_>deltax_guard_max_trials_ ||
           timedOut() || n_>4096 || x46_clone_ || probing_) {
            ++deltax_guard_budget_reject_;return false;
        }
        bool sat=false;int free=0;
        for(int lit:c){
            const int v=value(lit);
            if(v==1){sat=true;break;}
            if(v==0)++free;
        }
        if(sat || free==0) {
            ++deltax_guard_reject_;return false;
        }
        const int original_level=decisionLevel(),old_qhead=qhead_;
        const size_t old_trail=trail_.size(),old_clauses=clauses_.size();
        const auto old_decisions=stats_.decisions,old_conflicts=stats_.conflicts;
        const DeltaxGuardProbe baseline=deltaxGuardProbe(c,false);
        const DeltaxGuardProbe experiment=deltaxGuardProbe(c,true);
        if(decisionLevel()!=original_level || qhead_!=old_qhead ||
           trail_.size()!=old_trail || clauses_.size()!=old_clauses ||
           stats_.decisions!=old_decisions ||stats_.conflicts!=old_conflicts)
            throw std::runtime_error("DELTAX_GUARD_MAIN_SNAPSHOT_MUTATED");
        deltax_guard_total_base_dec_+=baseline.decisions;
        deltax_guard_total_trial_dec_+=experiment.decisions;
        deltax_guard_total_base_conf_+=baseline.conflicts;
        deltax_guard_total_trial_conf_+=experiment.conflicts;
        const bool contradiction=
            baseline.result!=Result::UNKNOWN &&
            experiment.result!=Result::UNKNOWN &&
            baseline.result!=experiment.result;
        if(contradiction)++deltax_guard_clone_inconsistency_;
        // Only use the clone results as heuristic information, NEVER a
        // source of SAT/UNSAT truth. Reject inconclusive or regressing
        // probes. A result verified by a bounded clone is NOT a proof.
        const int64_t bcost=baseline.decisions+5*baseline.conflicts;
        const int64_t ecost=experiment.decisions+5*experiment.conflicts;
        const bool nonregress=
            experiment.decisions<=baseline.decisions &&
            experiment.conflicts<=baseline.conflicts;
        const bool substantial=
            bcost>=4 && ecost*100<=bcost*95;
        const bool useful_termination=
            baseline.result==Result::UNKNOWN &&
            experiment.result!=Result::UNKNOWN && ecost<=bcost;
        const bool accept=
            !contradiction &&
            (nonregress && substantial || useful_termination);
        if(accept)++deltax_guard_accept_;
        else ++deltax_guard_reject_;
        if(deltax_guard_events_<12) {
            ++deltax_guard_events_;
            std::cerr<<"DELTAX_GUARD_PROBE {\"accepted\":"
                     <<(accept?"true":"false")
                     <<",\"baseline_decisions\":"<<baseline.decisions
                     <<",\"trial_decisions\":"<<experiment.decisions
                     <<",\"baseline_conflicts\":"<<baseline.conflicts
                     <<",\"trial_conflicts\":"<<experiment.conflicts
                     <<",\"baseline_result\":"<<static_cast<int>(baseline.result)
                     <<",\"trial_result\":"<<static_cast<int>(experiment.result)
                     <<",\"same_main_snapshot\":true}\n";
        }
        return accept;
    }
    void reportDeltaxGuard()const {
        std::cerr<<"DELTAX_GUARD_STATS {\"checks\":"<<deltax_guard_calls_
                 <<",\"accepted\":"<<deltax_guard_accept_
                 <<",\"rejected\":"<<deltax_guard_reject_
                 <<",\"budget_rejections\":"<<deltax_guard_budget_reject_
                 <<",\"inconsistent_clones\":"<<deltax_guard_clone_inconsistency_
                 <<",\"baseline_probe_decisions\":"<<deltax_guard_total_base_dec_
                 <<",\"trial_probe_decisions\":"<<deltax_guard_total_trial_dec_
                 <<",\"baseline_probe_conflicts\":"<<deltax_guard_total_base_conf_
                 <<",\"trial_probe_conflicts\":"<<deltax_guard_total_trial_conf_
                 <<",\"max_trials\":"<<deltax_guard_max_trials_
                 <<",\"clone_decision_limit\":"<<deltax_guard_clone_max_decisions_
                 <<",\"clone_conflict_limit\":"<<deltax_guard_clone_max_conflicts_
                 <<",\"clone_wall_ms\":"<<deltax_guard_clone_wall_ms_
                 <<"}\n";
    }
