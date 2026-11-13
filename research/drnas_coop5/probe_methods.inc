    // COOP5: independent BCP probe gate. Invariants:
    // - never commits speculative trail, clauses, decisions or proof steps;
    // - independent CDCL proves SAT/UNSAT;
    // - hints only alter branch selection, never infer a truth value;
    // - fixed and dynamic probes have a total wall-time budget.
    std::string coop5_mode_="off";
    bool coop5_dynamic_=COOP5_DYNAMIC_DEFAULT!=0;
    double coop5_budget_ms_=25.0,coop5_spent_ms_=0.0;
    int coop5_inspections_=320,coop5_gap_=24,coop5_failures_=0;
    int64_t coop5_next_decision_=0;
    bool coop5_feedback_pending_=false;
    int64_t coop5_feedback_conflicts_=0,coop5_feedback_decisions_=0;
    int coop5_feedback_trail_=0,coop5_feedback_long_=0;
    int64_t coop5_hints_=0,coop5_candidates_=0,coop5_attempts_=0;
    int64_t coop5_pairs_complete_=0,coop5_pairs_partial_=0;
    int64_t coop5_recommend_=0,coop5_applied_=0,coop5_shadow_recommend_=0;
    int64_t coop5_rejected_=0,coop5_conflict_probes_=0;
    int64_t coop5_overbudget_=0,coop5_cooldowns_=0,coop5_feedback_good_=0;
    int64_t coop5_feedback_bad_=0,coop5_stale_hints_=0;
    int64_t coop5_depth96_=0,coop5_depth320_=0,coop5_depth900_=0;
    int64_t coop5_total_inspected_=0,coop5_total_implied_=0;
    double coop5_max_pair_ms_=0.0;
    void configureCoop5(const std::string& mode) {
        if(mode!="off" && mode!="shadow" && mode!="on")
            throw std::runtime_error("bad COOP5 gate mode");
        coop5_mode_=mode;
        coop5_inspections_=coop5_dynamic_?96:320;
        coop5_gap_=coop5_dynamic_?64:24;
        coop5_budget_ms_=coop5_dynamic_?
            std::min(25.0,std::max(1.0,timeout_s_*5.0)):25.0;
    }
    void coop5Adjust(bool proxy_good) {
        if(!coop5_dynamic_)return;
        if(proxy_good) {
            coop5_failures_=0;
            coop5_gap_=std::max(12,coop5_gap_/2);
            coop5_inspections_=std::min(900,
                coop5_inspections_<320?320:900);
        } else if(++coop5_failures_>=3) {
            coop5_failures_=0;
            ++coop5_cooldowns_;
            coop5_gap_=std::min(256,coop5_gap_*2);
            coop5_inspections_=std::max(96,
                coop5_inspections_>320?320:96);
        }
    }
    void coop5Settle(bool conflict) {
        if(!coop5_feedback_pending_)return;
        coop5_feedback_pending_=false;
        const int extra=std::max(0,
            static_cast<int>(trail_.size())-coop5_feedback_trail_-1);
        // This is an outcome proxy only, not proof of a better global
        // search tree than the unchosen VSIDS counterfactual.
        const int longgain=conflict?0:
            std::max(0,coop5_feedback_long_-structuralDistance());
        const bool positive=!conflict && (extra>=4 || longgain>=2);
        if(positive)++coop5_feedback_good_;
        else {
            ++coop5_feedback_bad_;
            if(coop5_dynamic_){
                coop5_gap_=std::min(256,coop5_gap_*2);
                coop5_inspections_=std::max(96,
                    coop5_inspections_>320?320:96);
            }
        }
    }
    int coop5Choose(int baseline) {
        if(coop5_mode_=="off" || coop_hint_<0 || baseline<0)
            return baseline;
        ++coop5_hints_;
        const int hint=coop_hint_;
        if(hint==baseline || values_[static_cast<size_t>(hint)]!=0)return baseline;
        ++coop5_candidates_;
        if(stats_.conflicts<64 || stats_.decisions<coop5_next_decision_ ||
           timedOut() || (timeout_s_>0 && elapsed()>timeout_s_*0.90) ||
           coop5_spent_ms_>=coop5_budget_ms_) {
            if(coop5_spent_ms_>=coop5_budget_ms_)++coop5_overbudget_;
            return baseline;
        }
        const int depth=coop5_inspections_;
        if(depth<=96)++coop5_depth96_;
        else if(depth<=320)++coop5_depth320_;
        else ++coop5_depth900_;
        coop5_next_decision_=stats_.decisions+coop5_gap_;
        // Verify both candidates under the identical stable residual trail.
        // Neither candidate's polarity is flipped; there are only two probes.
        const auto started=Clock::now();
        const Probe normal=probe(phase_[static_cast<size_t>(baseline)]*(baseline+1),depth);
        const Probe guided=probe(phase_[static_cast<size_t>(hint)]*(hint+1),depth);
        const double spent=std::chrono::duration<double,std::milli>(
            Clock::now()-started).count();
        coop5_spent_ms_+=spent;
        coop5_max_pair_ms_=std::max(coop5_max_pair_ms_,spent);
        ++coop5_attempts_;
        coop5_total_inspected_+=normal.inspected+guided.inspected;
        coop5_total_implied_+=normal.implied+guided.implied;
        if(normal.contradiction || guided.contradiction) {
            ++coop5_conflict_probes_;
            ++coop5_rejected_;
            coop5Adjust(false);
            return baseline; // never declare SAT/UNSAT from a probe
        }
        if(normal.completed && guided.completed)++coop5_pairs_complete_;
        else ++coop5_pairs_partial_;
        // Both BCP prefixes use the same inspection cap. Partial BCP can
        // produce a useful but risky proxy; require a clear gap.
        const int better_implied=guided.implied-normal.implied;
        const int better_long=normal.remaining_long-guided.remaining_long;
        const bool confident=(better_long>=2 && better_implied>=-2) ||
                              (better_implied>=6 && better_long>=0);
        const double score=2.0*better_long+0.12*better_implied;
        const bool recommend=confident && score>=2.4 &&
              (normal.completed && guided.completed ||
               (better_long>=3 && better_implied>=4));
        if(!recommend) {
            ++coop5_rejected_;
            coop5Adjust(false);
            return baseline;
        }
        ++coop5_recommend_;
        coop5Adjust(true);
        if(coop5_mode_=="shadow") {
            ++coop5_shadow_recommend_;
            return baseline;
        }
        ++coop5_applied_;
        ++coop_.applied_hints;
        coop5_feedback_pending_=true;
        coop5_feedback_conflicts_=stats_.conflicts;
        coop5_feedback_decisions_=stats_.decisions;
        coop5_feedback_trail_=static_cast<int>(trail_.size());
        coop5_feedback_long_=structuralDistance();
        // The unchosen VSIDS head remains in the heap. No implication or
        // learned clause is injected by this heuristic.
        return hint;
    }
    void coop5Report() const {
        std::cerr<<"COOP5_PROBE {\"default_policy\":\""
                 <<(coop5_dynamic_?"dynamic":"fixed")
                 <<"\",\"mode\":\""<<coop5_mode_
                 <<"\",\"budget_ms\":"<<coop5_budget_ms_
                 <<",\"probe_wall_ms\":"<<coop5_spent_ms_
                 <<",\"max_pair_ms\":"<<coop5_max_pair_ms_
                 <<",\"hint_proposals\":"<<coop5_hints_
                 <<",\"distinct_candidates\":"<<coop5_candidates_
                 <<",\"attempted_pairs\":"<<coop5_attempts_
                 <<",\"completed_pairs\":"<<coop5_pairs_complete_
                 <<",\"partial_pairs\":"<<coop5_pairs_partial_
                 <<",\"would_override\":"<<coop5_recommend_
                 <<",\"actually_overrode\":"<<coop5_applied_
                 <<",\"shadow_recommend\":"<<coop5_shadow_recommend_
                 <<",\"rejected\":"<<coop5_rejected_
                 <<",\"conflict_probes\":"<<coop5_conflict_probes_
                 <<",\"budget_skips\":"<<coop5_overbudget_
                 <<",\"adaptive_cooldowns\":"<<coop5_cooldowns_
                 <<",\"feedback_good\":"<<coop5_feedback_good_
                 <<",\"feedback_bad\":"<<coop5_feedback_bad_
                 <<",\"depth96\":"<<coop5_depth96_
                 <<",\"depth320\":"<<coop5_depth320_
                 <<",\"depth900\":"<<coop5_depth900_
                 <<",\"total_inspected\":"<<coop5_total_inspected_
                 <<",\"total_implied\":"<<coop5_total_implied_
                 <<"}\n";
    }
