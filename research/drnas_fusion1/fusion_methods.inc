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
    int64_t fusion_original_binary_=0,fusion_original_ternary_=0;
    int64_t fusion_max_original_clause_size_=0,fusion_xor_groups_=0;
    int64_t fusion_opportunities_graph_=0,fusion_opportunities_xor_=0;
    std::map<std::array<int,3>,uint8_t> fusion_xor_masks_;
    static constexpr int64_t fusion_max_wakeups_=6;
    static constexpr int64_t fusion_max_variables_=4096;
    static constexpr int64_t fusion_max_original_clauses_=12000;

    void fusionObserveOriginal(const std::vector<int>& c) {
        // Called during source parsing ONLY if guarded mode was requested.
        // O(1) for almost all clauses, and a strictly bounded map for
        // exact XOR-three variable signatures. No learned clauses sampled.
        if(fusion_mode_!=3)return;
        fusion_max_original_clause_size_=std::max<int64_t>(
            fusion_max_original_clause_size_,static_cast<int64_t>(c.size()));
        if(c.size()==2)++fusion_original_binary_;
        if(c.size()!=3)return;
        ++fusion_original_ternary_;
        if(fusion_xor_masks_.size()>=1024 || n_>fusion_max_variables_)return;
        std::array<int,3> lits{{c[0],c[1],c[2]}};
        std::sort(lits.begin(),lits.end(),[](int a,int b){
            return std::abs(a)<std::abs(b);
        });
        std::array<int,3> key{{std::abs(lits[0]),std::abs(lits[1]),
                               std::abs(lits[2])}};
        if(key[0]==key[1]||key[1]==key[2])return;
        const int mask=(lits[0]<0?1:0)|(lits[1]<0?2:0)|
                       (lits[2]<0?4:0);
        const uint8_t bit=static_cast<uint8_t>(1u<<mask);
        uint8_t& observed=fusion_xor_masks_[key];
        const uint8_t before=observed;
        observed=static_cast<uint8_t>(before|bit);
        if(before!=observed && (observed==0x69 || observed==0x96))
            ++fusion_xor_groups_;
    }
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
        // Two independently motivated SOURCE-BLIND structural hints:
        // (1) graph-like: many original binary constraints plus short
        //     original clauses (blocks of at-most-one indicators);
        // (2) exact 3-variable XOR: all four parity clauses on the same
        //     three original variables, known prior-art mathematical pattern.
        // Neither is a new SAT deduction. They merely estimate whether
        // costly proof modules deserve a short trial.
        const bool graph_like=(
            n_<=768 && fusion_max_original_clause_size_<=3 &&
            fusion_original_binary_>=n_/2 &&
            fusion_original_ternary_>=n_/10);
        const bool xor_like=fusion_xor_groups_>0;
        if(!graph_like && !xor_like){++fusion_cheap_veto_;return false;}
        const bool early=(graph_like||xor_like) &&
            stats_.decisions<=24 && stats_.conflicts<=48;
        const bool pressure=(stats_.conflicts>=16 &&
            3*stats_.conflicts>=stats_.decisions &&
            (graph_like||xor_like));
        if(!early && !pressure){
            ++fusion_cheap_veto_;return false;
        }
        if(fusion_wakeups_>0 &&
           stats_.conflicts<fusion_next_conflict_ &&
           stats_.decisions<fusion_next_decision_){
            ++fusion_cheap_veto_;return false;
        }
        ++fusion_cheap_pass_;
        if(graph_like)++fusion_opportunities_graph_;
        if(xor_like)++fusion_opportunities_xor_;
        // Stamp the next eligible window immediately. This bounds even
        // readiness checks where no heavy module work actually launches.
        fusion_next_conflict_=stats_.conflicts+64;
        fusion_next_decision_=stats_.decisions+96;
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
                 <<",\"original_binary\":"<<fusion_original_binary_
                 <<",\"original_ternary\":"<<fusion_original_ternary_
                 <<",\"original_max_width\":"<<fusion_max_original_clause_size_
                 <<",\"exact_xor_triples\":"<<fusion_xor_groups_
                 <<",\"graph_pre_gate_passes\":"<<fusion_opportunities_graph_
                 <<",\"xor_pre_gate_passes\":"<<fusion_opportunities_xor_
                 <<",\"max_wakeups\":"<<fusion_max_wakeups_
                 <<",\"one_process\":true,\"core_cdcl_decisions_unchanged_by_guard\":true}\n";
    }
