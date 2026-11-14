    // DRNAS FUSION-GUARD1: ordinary CDCL is the ONLY decision authority.
    // Modules are OFF unless the cheap pre-gate explicitly grants a bounded
    // analysis window. The gate never alters assignments, watches, proofs
    // or decisions. Proof-first COOP4-GF(2) and DELTAX-SIGNAL1 share
    // the already-existing, serialized CDCL bridge AFTER activation.
    //
    // Mode 0: historical behavior (compatible frozen control).
    // Mode 1: CORE, forced modules OFF.
    // Mode 2: SHADOW: cheap pre-gate runs, no module startup.
    // Mode 3: GUARDED: cold originals and algebra construction only after
    //         a cheap, state-derived opportunity passes the gate.
    int fusion_mode_=0;
    bool fusion_originals_loaded_=false;
    int64_t fusion_ticks_=0,fusion_cheap_pass_=0,fusion_cheap_veto_=0;
    int64_t fusion_wakeups_=0,fusion_empty_windows_=0,fusion_useful_windows_=0;
    int64_t fusion_originals_copied_=0,fusion_skipped_large_=0;
    int64_t fusion_next_conflict_=0,fusion_next_decision_=0;
    int64_t fusion_last_lemmas_=0;
    static constexpr int64_t fusion_max_wakeups_=6;
    static constexpr int64_t fusion_max_variables_=4096;
    static constexpr int64_t fusion_max_original_clauses_=12000;

    void configureFusion(bool guarded,bool shadow,bool core) {
        const int choices=static_cast<int>(guarded)+
                          static_cast<int>(shadow)+static_cast<int>(core);
        if(choices>1)throw std::runtime_error("FUSION_CONFLICTING_MODES");
        fusion_mode_=guarded?3:shadow?2:core?1:0;
        if(fusion_mode_==1||fusion_mode_==2) {
            if(coop_.mode!="off")
                throw std::runtime_error("FUSION_CORE_REQUIRES_COOP_OFF");
        } else if(fusion_mode_==3) {
            if(coop_.mode!="gate"||coop_.join_mode!="deltax-signal-8"||
               !coop_.delayed)
                throw std::runtime_error("FUSION_GUARD_REQUIRES_COLD_PROOF_MODULES");
        }
    }
    bool fusionCheapPermit() {
        if(fusion_mode_==0)return true;
        if(fusion_mode_==1)return false;
        ++fusion_ticks_;
        // No analysis run, clone allocation, original-CNF cache, or
        // assumption-changing action occurs on a rejected gate.
        if(n_<=0 || n_>fusion_max_variables_ ||
           static_cast<int64_t>(clauses_.size())>fusion_max_original_clauses_ ||
           fusion_wakeups_>=fusion_max_wakeups_ ||
           timedOut() || x46_clone_ || probing_) {
            ++fusion_cheap_veto_;
            if(n_>fusion_max_variables_)++fusion_skipped_large_;
            return false;
        }
        // All features are ALREADY in the CDCL counters. A structural
        // signal comes from the binary implication footprint; pressure
        // signal comes from actual CDCL decisions/conflicts. We do not
        // run MATH, XOR, join tables, clone solvers or graph recognition
        // to determine whether to awaken the modules.
        const int64_t binary_edges=stats_.binary_edges;
        const bool dense_binary=(binary_edges>=n_ && n_<=768);
        const bool early=dense_binary && stats_.decisions<=24 &&
                         stats_.conflicts<=48;
        const bool pressure=(stats_.conflicts>=16 &&
                             3*stats_.conflicts>=stats_.decisions &&
                             binary_edges>=n_/5);
        if(!early && !pressure){
            ++fusion_cheap_veto_;return false;
        }
        if(fusion_wakeups_>0 &&
           stats_.conflicts<fusion_next_conflict_ &&
           stats_.decisions<fusion_next_decision_){
            ++fusion_cheap_veto_;return false;
        }
        ++fusion_cheap_pass_;
        if(fusion_mode_==2)return false; // SHADOW changes no CDCL state.
        ++fusion_wakeups_;
        // Cold-start source copy is deliberately deferred until the
        // pre-gate authorizes the FIRST expensive analysis. The preexisting
        // parser never pushes CNF into coop_ while FUSION is armed.
        if(!fusion_originals_loaded_){
            if(!coop_.originals.empty())
                throw std::runtime_error("FUSION_COLD_SOURCE_NOT_EMPTY");
            for(const Clause& c:clauses_)if(!c.learnt && !c.deleted) {
                coop_.add(c.lits);
                ++fusion_originals_copied_;
            }
            fusion_originals_loaded_=true;
            coop_.delayed=false;
        }
        fusion_last_lemmas_=coop_.lemmas;
        return true;
    }
    void fusionRecordWindow() {
        if(fusion_mode_!=3)return;
        if(coop_.lemmas<fusion_last_lemmas_)
            throw std::runtime_error("FUSION_LEMMA_COUNTER_ROLLED_BACK");
        if(coop_.lemmas>fusion_last_lemmas_) {
            ++fusion_useful_windows_;
            fusion_next_conflict_=stats_.conflicts+16;
            fusion_next_decision_=stats_.decisions+16;
        } else {
            ++fusion_empty_windows_;
            // Failed work is expensive; cool down for a longer interval.
            fusion_next_conflict_=stats_.conflicts+64;
            fusion_next_decision_=stats_.decisions+96;
        }
    }
    void reportFusion()const {
        std::cerr<<"DRNAS_FUSION_STATS {\"mode\":\""
                 <<(fusion_mode_==3?"GUARDED":
                     fusion_mode_==2?"SHADOW":
                     fusion_mode_==1?"CORE":"LEGACY")
                 <<"\",\"cheap_ticks\":"<<fusion_ticks_
                 <<",\"cheap_approved\":"<<fusion_cheap_pass_
                 <<",\"cheap_rejected\":"<<fusion_cheap_veto_
                 <<",\"module_wakeups\":"<<fusion_wakeups_
                 <<",\"cold_originals_loaded\":"<<(fusion_originals_loaded_?"true":"false")
                 <<",\"source_clauses_copied\":"<<fusion_originals_copied_
                 <<",\"productive_windows\":"<<fusion_useful_windows_
                 <<",\"empty_windows\":"<<fusion_empty_windows_
                 <<",\"skipped_large\":"<<fusion_skipped_large_
                 <<",\"max_wakeups\":"<<fusion_max_wakeups_
                 <<",\"one_process\":true,\"core_cdcl_decisions_unchanged_by_guard\":true}\n";
    }
