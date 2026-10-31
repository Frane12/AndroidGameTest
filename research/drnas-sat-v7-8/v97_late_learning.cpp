// V9.7 PREREGISTERED: inject original phase hints ONLY AFTER unphased
// 64/128/256-conflict quality probe; randomized matched arms, untouched controls.
// LBD threshold derives from previous V9.1 exploratory values; NOT trained on V9.7 holdout.
// DRNAS V9.6 CAUSAL TELEMETRY EXPERIMENT - FIXED BEFORE PROSPECTIVE 2026 CNFS
// Six matched arms: phase vs no-phase, crossed with durable/force/stop at 256.
// Diagnostic only; control may alter CDCL trajectory. No independent proof for UNSAT.
// DRNAS v9.4 frozen 2026 out-of-sample structural phase vs CaDiCaL
// Precommit rule uses only CNF structure, NEVER known SAT/UNSAT answer or
// official time. No post-run threshold updates permitted on holdout.
// DRNAS SAT v9.2, PRE-SEARCH O(literals) structural phase routing.
// Decisions use only current CNF clause widths, degree and sign imbalance;
// no family, filename, solved label, learned clauses or post-conflict data.
// Precommitted before v9.2 fresh seeded 30-case benchmark.
// This is a hypothesis, not a validated speed improvement.
// DRNAS SAT v9.1, PRECOMMITTED prospective causal late-phase experiment.
// All v91 variants share IDENTICAL first 256-conflict unphased search;
// the v7.6 retained-clause continuation decision is unchanged.
// Selector chooses ONLY whether to apply phase hints AFTER checkpoint 256.
// From exploratory v9.0 ONLY: >=6% preminimization first-UIP LBD<=2,
// >=32 search propagations/conflict, >=20 learned clauses. No family labels.
// Do not tune this threshold based on v9.1 results.
// DRNAS v9.0: TRUE first-UIP LBD and actual propagation/backjump instrumentation.
// Separate instrumented CaDiCaL checkout, not the unmodified production solver.
// Experimental probe has no new control decisions; diagnostic replay of v7.6.
// DRNAS V8.8b: delayed-phase low-level optimization. No hot-loop callbacks.
// The unmodified CaDiCaL baseline does the first 256 conflicts without phase hints.
// Only durable learned-clause progress triggers late application of phase hints.
// The solver and learned database are never reset; test as hypothesis, not a release.
// v7.6 untouched: durable 256->768 path is preserved byte-for-byte in policy.
// When first-256 learning is near original durable threshold, strong phase
// coverage can justify ONE 128-conflict sample, using redundant()/active() only.
// No code is injected into CaDiCaL's propagation/learning hot loop.
// CAUTION: higher-level policy, not verified CPU cycle/cache improvement.
// Guard is an exploratory response to V8.6 cross-family regression; test on new seeds.
// V7.6 / V7.7 frozen originals remain unchanged. Prospective gate policy.
// This test is an experiment, not a validated speedup or production default.
// DRNAS V7.9 HINT CAUSAL DIAGNOSTIC ONLY. Does NOT alter V7.6 or V7.7 code.
// Include both original frozen implementations. All additional modes are
// strictly experimental controls; never publish as measured speedups.
// The build deterministically extracts frozen v7.7 source *before*
// its only int main(...) entrypoint. This avoids the internal main
// preprocessor undef in original v7.6 without editing either file.
#include "../drnas-sat-v7-7/v77_embedded_functions.inc"
#include <map>
// DRNAS v8.9: conflict+CPU-time learned-clause yield, checkpoint only, experimental.
// One CaDiCaL 3.0.1 solver; no changes to propagation or clause learning hot loop.
// Delay optional majority phases until AFTER 256 initial conflicts; measure process CPU.
// Retained redundant clauses = proxy for durable progress, not LBD or proof quality.
#include <ctime>
// V9.6 diagnosis: matched 2 x 3 intervention factorial, no solver hot-loop changes.
static bool v96_diag_policy(const std::string &p) { return p.rfind("v96_",0)==0; }
static bool v97_late_policy(const std::string &p) { return p.rfind("v97_late_",0)==0; }
#include <time.h>
static inline unsigned long long drnas_process_cpu_ns() {
    timespec t{};
    if(clock_gettime(CLOCK_PROCESS_CPUTIME_ID,&t)!=0)
        throw std::runtime_error("CLOCK_PROCESS_CPUTIME_ID unavailable");
    return static_cast<unsigned long long>(t.tv_sec)*1000000000ULL+
           static_cast<unsigned long long>(t.tv_nsec);
}


struct V92Static {
    int broad=0,strong=0,selected=0,clause2=0,clause3=0,clause4=0;
    int max_width=0;
    std::string choice="n/a";
    double analysis_us=0;
};

// This single O(total input literals) scan replaces two independent
// passes. Thresholds are frozen BEFORE v9.2 holdout:
 // broad: degree >=6 and >=15% polarity majority imbalance
 // strong: degree >=8 and >=30% imbalance
 // long-width >=65% or 2-CNF-heavy with wide pigeonhole-style clauses:
 // avoid initial phases. Otherwise apply broad if structural support, else
 // choose strong only with >=12.5% variable coverage.
static Hints v92_static_hints(const Formula &f,
                              const bool sparse_only,V92Static &out) {
    const auto start=Clock::now();
    Hints h;
    if(f.vars<=0) {out.choice="empty";return h;}
    std::vector<int> pos(f.vars+1,0),neg(f.vars+1,0);
    const int M=static_cast<int>(f.clauses.size());
    for(const auto &c:f.clauses) {
        const int w=static_cast<int>(c.size());
        out.clause2+=(w==2);out.clause3+=(w==3);out.clause4+=(w==4);
        out.max_width=std::max(out.max_width,w);
        for(const int lit:c) {
            if(lit>0)++pos[lit]; else ++neg[-lit];
        }
    }
    std::vector<int> broad,strong;
    broad.reserve(f.vars);strong.reserve(f.vars);
    for(int v=1;v<=f.vars;++v) {
        const int degree=pos[v]+neg[v],delta=std::abs(pos[v]-neg[v]);
        if(degree>=6 && 100LL*delta>=15LL*degree && delta>0)
            broad.push_back(pos[v]>neg[v]?v:-v);
        if(degree>=8 && 100LL*delta>=30LL*degree && delta>0)
            strong.push_back(pos[v]>neg[v]?v:-v);
    }
    out.broad=static_cast<int>(broad.size());
    out.strong=static_cast<int>(strong.size());
    if(sparse_only) {
        h.literals.swap(strong);out.choice="strong_only";
    } else if(M>0 && (100LL*out.clause4>=65LL*M ||
                    (100LL*out.clause2>=50LL*M &&
                     out.max_width>=6))) {
        out.choice="skip_long_or_mixed_binary";
    } else if(M>0 && out.broad*3>=f.vars &&
             (100LL*out.clause3>=75LL*M ||
              (100LL*out.clause2>=55LL*M && out.max_width<=3))) {
        h.literals.swap(broad);out.choice="broad";
    } else if(out.strong*8>=f.vars) {
        h.literals.swap(strong);out.choice="strong";
    } else {
        out.choice="skip_low_confidence";
    }
    out.selected=static_cast<int>(h.literals.size());
    out.analysis_us=std::chrono::duration<double,std::micro>(
                      Clock::now()-start).count();
    h.candidates=out.selected;
    h.analysis_us=out.analysis_us;
    return h;
}

struct Audit {
    int status=0, stage1=-1,stage2=-1,stage3=-1, first_budget=256,second_budget=0,third_budget=0;
    int hints=0,active_pre=0,active_256=0,threshold=0;
    std::string gate_reason="n/a";
    bool extended=false,resumed=false,observer_connected=false,adaptive_keep=false;
    bool v91_phase_applied=false,v91_gate_quality=false;
    int v92_broad_candidates=0,v92_strong_candidates=0;
    int v92_clause2=0,v92_clause3=0,v92_clause4=0,v92_maxwidth=0;
    double v92_static_us=0;
    std::string v92_choice="n/a";
    int64_t redundant_pre=0,redundant_256=0,learned_delta=0,checkpoint_learned=0;
    int64_t v90_learned_256=0,v90_lbd2_256=0,v90_lbd4_256=0;
    int64_t v90_lbd_sum_256=0,v90_props_256=0,v90_jumps_256=0;
    int64_t v90_jumpdepth_256=0,v90_conflicts_256=0,v90_backtracks_256=0;
    int64_t v90_learned_total=0,v90_lbd2_total=0,v90_props_total=0;
    uint64_t offered=0,short5=0,checkpoint_offered=0,checkpoint_short5=0;
    unsigned long long cpu_256_ns=0,cpu_128_ns=0,cpu_total_ns=0;
    int64_t active_384=0;
    double short_fraction=0, total_us=0,probe_us=0,extension_us=0,resume_us=0,checkpoint_us=0,final_extension_us=0;
    int v96_status64=-1,v96_status128=-1;
    int64_t v96_c64=0,v96_c128=0,v96_lbd2_64=0,v96_lbd2_128=0;
    int64_t v96_lbd4_64=0,v96_lbd4_128=0,v96_props64=0,v96_props128=0;
    int64_t v96_jump64=0,v96_jump128=0,v96_learn64=0,v96_learn128=0;
};

// This is an A/B copy of the phase+checkpoint path, for measuring policy and
// the public Learner observer independently. Solver is always CaDiCaL 3.0.1.
// 'old_rule' = original V7.6 redundant-delta/active threshold.
// 'new_rule' = original V7.7 >=32,>=10 short5, >=20% clause shortness.
// 'force_extend' / 'force_stop' are matched boundary controls (NOT releases).
static Audit ablation(const Formula &f,const std::string &policy,
                      bool use_observer,uint32_t seed,bool enable_hints=true) {
    const auto start=Clock::now();
    const auto cpu_start_ns=drnas_process_cpu_ns();
    // Observer must outlive solver (as in the frozen original V7.7).
    ClauseSizeObserver obs;
    CaDiCaL::Solver solver;
    fill_solver(solver,f);
    if(use_observer) solver.connect_learner(&obs);
    Audit a;
    a.observer_connected=use_observer;
    Hints h;
    if(policy=="v92_structural" || policy=="v92_sparse") {
        V92Static d;
        h=v92_static_hints(f,policy=="v92_sparse",d);
        a.v92_broad_candidates=d.broad;
        a.v92_strong_candidates=d.strong;
        a.v92_clause2=d.clause2;a.v92_clause3=d.clause3;
        a.v92_clause4=d.clause4;a.v92_maxwidth=d.max_width;
        a.v92_static_us=d.analysis_us;
        a.v92_choice=d.choice;
    } else if(enable_hints) {
        add_phase_hints(f,h,false,seed); // frozen v7.6 compatible
    }
    a.hints=static_cast<int>(h.literals.size());
    // All V9.7 arms start with identical, completely unphased CaDiCaL search.
    if(policy!="delayed_v88b" && policy!="v89_rate" &&
       policy!="v91_gate" && policy!="v91_always" && policy!="v91_never" &&
       !v97_late_policy(policy))
        for(const int lit:h.literals) solver.phase(lit);

    a.redundant_pre=solver.redundant();
    a.active_pre=solver.active();
    a.threshold=std::max(48,(a.active_pre+3)/4);
    const bool v96=v96_diag_policy(policy);
    const bool v97=v97_late_policy(policy);
    if(!solver.limit("conflicts",(v96||v97)?64:256))
        throw std::runtime_error("CaDiCaL rejected first conflict limit");
    auto phase_start=Clock::now();
    const auto cpu_first_start=drnas_process_cpu_ns();
    const auto d0=solver.drnas_telemetry();
    // All six V9.6 arms see identical 64/128/256 checkpoint scheduling.
    // The only interventions are initial phases and the policy AFTER 256.
    if(v96||v97) {
        a.v96_status64=solver.solve();
        const auto d64=solver.drnas_telemetry();
        a.v96_c64=d64.conflicts-d0.conflicts;
        a.v96_lbd2_64=d64.lbd_le2-d0.lbd_le2;
        a.v96_lbd4_64=d64.lbd_le4-d0.lbd_le4;
        a.v96_props64=d64.search_propagations-d0.search_propagations;
        a.v96_jump64=d64.jump_depth_sum-d0.jump_depth_sum;
        a.v96_learn64=d64.learned_clauses-d0.learned_clauses;
        if(a.v96_status64==0) {
            if(!solver.limit("conflicts",64))
                throw std::runtime_error("V96 128-limit rejected");
            a.v96_status128=solver.solve();
        } else a.v96_status128=a.v96_status64;
        const auto d128=solver.drnas_telemetry();
        a.v96_c128=d128.conflicts-d0.conflicts;
        a.v96_lbd2_128=d128.lbd_le2-d0.lbd_le2;
        a.v96_lbd4_128=d128.lbd_le4-d0.lbd_le4; 
        a.v96_props128=d128.search_propagations-d0.search_propagations;
        a.v96_jump128=d128.jump_depth_sum-d0.jump_depth_sum;
        a.v96_learn128=d128.learned_clauses-d0.learned_clauses;
        if(a.v96_status128==0) {
            if(!solver.limit("conflicts",128))
                throw std::runtime_error("V96 256-limit rejected");
            a.stage1=solver.solve();
        } else a.stage1=a.v96_status128;
    } else a.stage1=solver.solve();
    const auto d256=solver.drnas_telemetry();
    if(v96 || v97 || policy=="v90_quality" || policy=="v91_gate" ||
       policy=="v91_always" || policy=="v91_never") {
        a.v90_learned_256=d256.learned_clauses-d0.learned_clauses;
        a.v90_lbd2_256=d256.lbd_le2-d0.lbd_le2;
        a.v90_lbd4_256=d256.lbd_le4-d0.lbd_le4;
        a.v90_lbd_sum_256=d256.lbd_sum-d0.lbd_sum;
        a.v90_props_256=d256.search_propagations-d0.search_propagations;
        a.v90_conflicts_256=d256.conflicts-d0.conflicts;
        a.v90_jumpdepth_256=d256.jump_depth_sum-d0.jump_depth_sum;
        a.v90_jumps_256=d256.jumps-d0.jumps;
        a.v90_backtracks_256=d256.backtracks-d0.backtracks;
    }
    a.cpu_256_ns=drnas_process_cpu_ns()-cpu_first_start;
    a.probe_us=std::chrono::duration<double,std::micro>(
                    Clock::now()-phase_start).count();
    a.redundant_256=solver.redundant();
    a.active_256=solver.active();
    a.learned_delta=std::max<int64_t>(0,a.redundant_256-a.redundant_pre);
    a.offered=obs.observed;
    a.short5=obs.short5;
    a.short_fraction=a.offered?double(a.short5)/a.offered:0.;
    // Flush BEFORE any unrestricted continuation: timeouts must retain
    // the first 64/128/256-conflict trace. Same output for every V96 arm.
    if(v96||v97) {
        const bool durable=(a.active_256>0 && a.learned_delta>=a.threshold);
        std::cout<<"DRNAS_EARLY\tmode="<<policy
                 <<"\tstage1="<<a.stage1
                 <<"\tv96_status64="<<a.v96_status64
                 <<"\tv96_status128="<<a.v96_status128
                 <<"\tv96_c64="<<a.v96_c64
                 <<"\tv96_c128="<<a.v96_c128
                 <<"\tv96_lbd2_64="<<a.v96_lbd2_64
                 <<"\tv96_lbd2_128="<<a.v96_lbd2_128
                 <<"\tv96_lbd4_64="<<a.v96_lbd4_64
                 <<"\tv96_lbd4_128="<<a.v96_lbd4_128
                 <<"\tv96_props64="<<a.v96_props64
                 <<"\tv96_props128="<<a.v96_props128
                 <<"\tv96_jump64="<<a.v96_jump64
                 <<"\tv96_jump128="<<a.v96_jump128
                 <<"\tv96_learn64="<<a.v96_learn64
                 <<"\tv96_learn128="<<a.v96_learn128
                 <<"\tv90_learned_256="<<a.v90_learned_256
                 <<"\tv90_lbd2_256="<<a.v90_lbd2_256
                 <<"\tv90_lbd4_256="<<a.v90_lbd4_256
                 <<"\tv90_lbd_sum_256="<<a.v90_lbd_sum_256
                 <<"\tv90_props_256="<<a.v90_props_256
                 <<"\tv90_conflicts_256="<<a.v90_conflicts_256
                 <<"\tv90_jumpdepth_256="<<a.v90_jumpdepth_256
                 <<"\tv90_jumps_256="<<a.v90_jumps_256
                 <<"\tlearned_delta="<<a.learned_delta
                 <<"\tthreshold="<<a.threshold
                 <<"\tactive_pre="<<a.active_pre
                 <<"\tactive_256="<<a.active_256
                 <<"\thints="<<a.hints
                 <<"\tvars="<<f.vars
                 <<"\tclauses="<<f.clauses.size()
                 <<"\tv96_durable_predicted="<<int(durable)
                 <<std::endl;
    }
    if(a.stage1==0) {
        if(v97) {
            // Precommitted hypothesis: infer early learning QUALITY from the
            // identical unphased 64/128/256-conflict trajectory.
            const int64_t L=a.v90_learned_256;
            const int64_t C=a.v90_conflicts_256;
            const int64_t P=a.v90_props_256;
            const bool quality=(L>=20 && C>0 &&
                100*a.v90_lbd2_256>=6*L && P>=32*C);
            // Yield is a distinct incremental 128->256 signal.
            const int64_t dL=std::max<int64_t>(0,L-a.v96_learn128);
            const int64_t dC=std::max<int64_t>(1,C-a.v96_c128);
            const int64_t dP=std::max<int64_t>(0,P-a.v96_props128);
            const int64_t dQ=std::max<int64_t>(0,a.v90_lbd2_256-a.v96_lbd2_128);
            const bool yield=quality && dL>=8 &&
                100*dQ>=6*dL && dP>=24*dC && a.active_256>0;
            bool apply=false;
            if(policy=="v97_late_always")apply=true;
            else if(policy=="v97_late_never")apply=false;
            else if(policy=="v97_late_quality")apply=quality && a.active_256>0;
            else if(policy=="v97_late_yield")apply=yield;
            else throw std::runtime_error("Unknown V97 policy "+policy);
            a.v91_phase_applied=apply;
            if(apply)
                for(const int lit:h.literals)solver.phase(lit);
            const bool durable=a.active_256>0 && a.learned_delta>=a.threshold;
            a.extended=durable; // identical v7.6 256->768 guard in all V97 arms
            a.gate_reason=apply?"v97_late_phase_on":"v97_late_phase_off";
            // Capture decision before unlimited search, even if wall timed out.
            std::cout<<"DRNAS_DECISION\tmode="<<policy
                     <<"\tapply="<<int(apply)
                     <<"\tquality="<<int(quality)
                     <<"\tyield="<<int(yield)
                     <<"\tdurable="<<int(durable)
                     <<"\thints="<<h.literals.size()
                     <<std::endl;
        } else if(v96) {
            const bool durable=a.active_256>0 && a.learned_delta>=a.threshold;
            if(policy.find("_durable")!=std::string::npos) {
                a.extended=durable;a.gate_reason=durable?"v96_durable_extend":"v96_durable_resume";
            } else if(policy.find("_force")!=std::string::npos) {
                a.extended=true;a.gate_reason="v96_force_extend";
            } else if(policy.find("_stop")!=std::string::npos) {
                a.extended=false;a.gate_reason="v96_force_resume";
            } else throw std::runtime_error("Unexpected V96 arm");
        } else if(policy=="v92_structural" || policy=="v92_sparse" ||
           policy=="v92_full") {
            // Exactly the original v7.6 256 -> 768 continuation policy.
            a.extended=a.learned_delta>=a.threshold && a.active_256>0;
            a.gate_reason=a.extended?"v92_durable_v76":"v92_low_yield_resume";
        } else if(policy=="v91_gate" || policy=="v91_always" || policy=="v91_never") {
            // Same v7.6 continuation budget for EVERY v9.1 arm.
            a.extended=a.learned_delta>=a.threshold && a.active_256>0;
            // This comparison is observational; do not act until >256.
            const int64_t L=a.v90_learned_256;
            const int64_t C=a.v90_conflicts_256;
            const int64_t P=a.v90_props_256;
            a.v91_gate_quality=(L>=20 && C>0 &&
                                 100*a.v90_lbd2_256>=6*L &&
                                 P>=32*C);
            a.gate_reason=a.extended?"v91_v76_durable":"v91_v76_early_resume";
        } else if(policy=="v90_quality") {
            // EXACT durable v7.6 gate. Quality counters are observed only,
            // never used to decide continuation in v9.0. No lookahead label.
            a.extended=a.learned_delta>=a.threshold && a.active_256>0;
            a.gate_reason=a.extended?"v90_frozen_v76_extend":"v90_frozen_v76_resume";
        } else if(policy=="old_rule") {
            a.extended=a.learned_delta>=a.threshold && a.active_256>0;
        } else if(policy=="new_rule") {
            if(!use_observer) throw std::runtime_error(
                "New rule cannot run without clause observer");
            a.extended=a.offered>=32 && a.short5>=10 &&
                       5*a.short5>=a.offered;
        } else if(policy=="hybrid_gate") {
            if(!use_observer) throw std::runtime_error(
                "Hybrid quality evidence requires observer");
            // Baseline v7.6 keeps priority: never veto durable learned progress.
            const bool durable = a.active_256>0 && a.learned_delta>=a.threshold;
            // Only admit a quality override near the original durable threshold.
            // Clause lengths refer to CaDiCaL *export offers*, not LBD.
            const bool quality_override =
                a.active_256>0 &&
                a.learned_delta*4>=static_cast<int64_t>(a.threshold)*3 &&
                a.offered>=64 && a.short5>=16 &&
                4*a.short5>=a.offered;
            a.extended=durable || quality_override;
            a.gate_reason=durable?"durable":(quality_override?"quality":"none");
        } else if(policy=="adaptive_two_checkpoint" || policy=="adaptive_guarded_v87") {
            if(!use_observer) throw std::runtime_error(
                "Adaptive policy requires clause observer");
            // PREDECLARED before unseen V8.6 cases:
            // V7.6 durable survival OR V7.7 quality evidence permits a
            // short (128-conflict) exploratory continuation. No case labels.
            const bool durable=a.active_256>0 && a.learned_delta>=a.threshold;
            const bool quality=a.offered>=32 && a.short5>=10 &&
                               5*a.short5>=a.offered;
            a.extended=durable || quality;
            a.gate_reason=durable?"checkpoint_durable":
                          (quality?"checkpoint_quality":"checkpoint_no_signal");
        } else if(policy=="v89_rate") {
            // First 256 conflicts are always unphased for both matched modes.
            // Preserve the v7.6 durable extension, and sample 128 only when
            // retained clauses are near but below the v7.6 learned threshold.
            const bool durable=a.active_256>0 &&
                a.learned_delta>=a.threshold;
            const bool near=!durable && a.active_256>0 &&
                5*a.learned_delta>=3*static_cast<int64_t>(a.threshold) &&
                2*static_cast<int64_t>(a.active_256)>=a.active_pre;
            a.extended=durable || near;
            a.gate_reason=durable?"v89_durable_768":
                         (near?"v89_near_128":"v89_early_resume");
        } else if(policy=="delayed_v88b") {
            const bool durable=a.active_256>0 &&
                a.learned_delta>=a.threshold;
            a.extended=durable;
            a.gate_reason=durable?"v88b_apply_after_256":
                                  "v88b_no_phase_on_low_progress";
        } else if(policy=="lowlevel_v88") {
            // Integer-only and O(1) policy: CaDiCaL's public cumulative
            // redundant()/active() counters are read at 256. No per-clause
            // Learner callbacks, LBD inference or floating point divisions.
            const bool durable=a.active_256>0 &&
                a.learned_delta>=a.threshold;
            const bool near=!durable && a.active_256>0 &&
                static_cast<int64_t>(a.learned_delta)*4 >=
                    static_cast<int64_t>(a.threshold)*3 &&
                static_cast<int64_t>(h.literals.size())*4 >=
                    static_cast<int64_t>(f.vars)*3 &&
                static_cast<int64_t>(a.active_256)*2 >=
                    static_cast<int64_t>(a.active_pre);
            a.extended=durable || near;
            a.gate_reason=durable?"v88_preserve_v76_durable":
                          (near?"v88_near_128_probe":"v88_early_fallback");
        } else if(policy=="force_extend") {
            a.extended=true;
        } else if(policy=="force_stop") {
            a.extended=false;
        } else throw std::runtime_error("Unknown policy");
        int after=a.stage1;
        if(a.extended) {
            // Do not perturb the first 256-conflict phase trajectory.
            // Add hints ONLY after durable progress has been observed.
            if(policy=="delayed_v88b" || policy=="v89_rate")
                for(const int lit:h.literals) solver.phase(lit);
            if(policy=="v91_gate" || policy=="v91_always" || policy=="v91_never") {
                const bool apply=policy=="v91_always" ||
                    (policy=="v91_gate" && a.v91_gate_quality);
                a.v91_phase_applied=apply;
                a.gate_reason=(policy=="v91_always")?"v91_always_late":
                              (policy=="v91_never")?"v91_never":
                              (apply?"v91_quality_late":"v91_quality_skip");
                if(apply)
                    for(const int lit:h.literals) solver.phase(lit);
            }
            // Conservative structural guard: very broad phase guidance AND
            // substantial short-clause evidence keep the proven V7.6 full
            // 768-conflict continuation rather than introduce a new 128
            // conflict boundary. No family IDs or SAT/UNSAT labels.
            const bool guarded=policy=="adaptive_guarded_v87" &&
                4*h.literals.size()>=3*static_cast<size_t>(f.vars) &&
                a.offered>=64 && a.short5>=16 &&
                a.learned_delta>=a.threshold;
            const bool ll_near=policy=="lowlevel_v88" &&
                               a.gate_reason=="v88_near_128_probe";
            const bool v89_near=policy=="v89_rate" &&
                                a.gate_reason=="v89_near_128";
            const bool adaptive=((policy=="adaptive_two_checkpoint" ||
                                 policy=="adaptive_guarded_v87") && !guarded) ||
                                 ll_near || v89_near;
            if(guarded) a.gate_reason="guard_dense_hints_full_v76";
            a.second_budget=adaptive?128:768;
            if(!solver.limit("conflicts",a.second_budget))
                throw std::runtime_error("CaDiCaL rejected extension");
            const auto next=Clock::now();
            const auto cpu_second_start=drnas_process_cpu_ns();
            a.stage2=solver.solve();
            if(v89_near) a.cpu_128_ns=drnas_process_cpu_ns()-cpu_second_start;
            a.extension_us=std::chrono::duration<double,std::micro>(
                              Clock::now()-next).count();
            after=a.stage2;
            if(adaptive && after==0) {
                // Same CaDiCaL solver, same learnt database. Measure ONLY
                // new work during the 128-conflict checkpoint.
                const auto redundant_after=solver.redundant();
                a.checkpoint_learned=std::max<int64_t>(
                    0,redundant_after-a.redundant_256);
                a.checkpoint_offered=obs.observed-a.offered;
                a.checkpoint_short5=obs.short5-a.short5;
                if(v89_near) {
                    a.active_384=solver.active();
                    // Two simultaneous measurements: yield per *conflict
                    // budget* and yield per *process CPU nanosecond*.
                    // Fixed integer cross-products avoid divisions and NaN.
                    // Some signals are CPU-scheduling sensitive: diagnostics
                    // preserve outcomes and no threshold tuning on holdout.
                    const auto L1=std::max<int64_t>(1,a.learned_delta);
                    const auto L2=a.checkpoint_learned;
                    const auto T1=std::max<unsigned long long>(1,a.cpu_256_ns);
                    const auto T2=std::max<unsigned long long>(1,a.cpu_128_ns);
                    const bool conflict_yield=4*L2>=L1;
                    const bool cpu_yield=
                       (__int128)5*L2*T1 >= (__int128)3*L1*T2;
                    const bool retained=a.active_384>0 &&
                        2*a.active_384>=a.active_256;
                    a.adaptive_keep=L2>=12 && conflict_yield &&
                                    cpu_yield && retained;
                    a.gate_reason=a.adaptive_keep?
                        "v89_keep_640_yield":"v89_stop_128_low_yield";
                } else if(ll_near) {
                    // Low-level gate: use only public integer counters.
                    // No learner observer, clause allocation or callback path.
                    const int active_after=solver.active();
                    const int64_t needed=std::max<int64_t>(32,a.threshold/3);
                    a.adaptive_keep=active_after>0 &&
                        a.checkpoint_learned>=needed &&
                        static_cast<int64_t>(active_after)*2 >= a.active_256;
                    a.gate_reason=a.adaptive_keep?
                        "v88_keep_640":"v88_fallback_after_128";
                } else {
                    const bool quality_progress=
                        a.checkpoint_offered>=16 &&
                        5*a.checkpoint_short5>=a.checkpoint_offered;
                    const bool durable_progress=a.checkpoint_learned>=120;
                    const bool useful_progress=a.checkpoint_learned>=96 &&
                        (quality_progress || durable_progress);
                    a.adaptive_keep=solver.active()>0 && useful_progress;
                    a.gate_reason=a.adaptive_keep?
                        (quality_progress?"keep_quality":"keep_durable"):
                        "stop_low_yield_or_quality";
                }
                if(a.adaptive_keep) {
                    // 256 + 128 + 640 = 1024 conflicts maximum while hints
                    // remain. Mirrors frozen V7.6 256 + 768 budget.
                    a.third_budget=640;
                    if(!solver.limit("conflicts",a.third_budget))
                        throw std::runtime_error("CaDiCaL rejected third limit");
                    const auto final_start=Clock::now();
                    a.stage3=solver.solve();
                    a.final_extension_us=std::chrono::duration<double,std::micro>(
                        Clock::now()-final_start).count();
                    a.extension_us+=a.final_extension_us;
                    after=a.stage3;
                }
            }
        }
        if(after==0) {
            // In never/skip arms, unphase() would itself alter later
            // phase state, violating the matched no-hint continuation.
            const bool is_v91=(policy=="v91_gate" ||
                               policy=="v91_always" || policy=="v91_never");
            // V97 late applied phases intentionally persist through the
            // unrestricted continuation, unlike early-V7.6 hints.
            if(!v97 && (!is_v91 || a.v91_phase_applied))
                for(const int lit:h.literals)solver.unphase(lit);
            auto next=Clock::now();
            a.status=solver.solve();
            a.resume_us=std::chrono::duration<double,std::micro>(
                            Clock::now()-next).count();
            a.resumed=true;
        } else a.status=after;
    } else a.status=a.stage1;
    if(a.status!=10 && a.status!=20)
        throw std::runtime_error("Unexpected final UNKNOWN status");
    if(a.status==10) check_sat_model(solver,f);
    if(use_observer)solver.disconnect_learner();
    a.total_us=std::chrono::duration<double,std::micro>(
                         Clock::now()-start).count();
    a.cpu_total_ns=drnas_process_cpu_ns()-cpu_start_ns;
    if(v96 || v97 || policy=="v90_quality" || policy=="v91_gate" ||
       policy=="v91_always" || policy=="v91_never") {
        const auto dt=solver.drnas_telemetry();
        a.v90_learned_total=dt.learned_clauses;
        a.v90_lbd2_total=dt.lbd_le2;
        a.v90_props_total=dt.search_propagations;
    }
    return a;
}

int main(int argc,char **argv) {
    try {
        if(argc!=4) {
            std::cerr<<"Usage: v80_hybrid_probe MODE ORIGINAL_CNF SEED\n";
            return 2;
        }
        const std::string mode=argv[1];
        const auto f=read_cnf(argv[2]);
        const auto seed=static_cast<uint32_t>(std::stoul(argv[3]));
        Audit a;
        if(mode=="orig_v76" || mode=="orig_v76_plain" || mode=="ca_plain") {
            const auto v=run76(f,mode=="orig_v76"?"adaptive_guided":(mode=="orig_v76_plain"?"adaptive_plain":"plain"),seed); // FROZEN SOURCE
            a.status=v.status;
            a.stage1=v.stage1;a.stage2=v.stage2;
            a.first_budget=v.first_budget;a.second_budget=v.second_budget;
            a.hints=v.hinted;
            a.active_pre=v.active_pre;a.active_256=v.active_256;
            a.redundant_pre=v.redundant_pre;a.redundant_256=v.redundant_256;
            a.learned_delta=v.learned;a.threshold=v.learned_threshold;
            a.extended=v.extended;a.resumed=v.resumed;
            a.total_us=v.total_us;a.probe_us=v.probe_us;
            a.extension_us=v.extension_us;a.resume_us=v.resume_us;
        } else if(v97_late_policy(mode)) {
            a=ablation(f,mode,false,seed,true);
        } else if(v96_diag_policy(mode)) {
            const bool with_phases=mode.rfind("v96_phase_",0)==0;
            if(!with_phases && mode.rfind("v96_plain_",0)!=0)
                throw std::runtime_error("Unexpected V96 mode prefix");
            a=ablation(f,mode,false,seed,with_phases);
        } else if(mode=="orig_v77") {
            const auto v=solve77(f,"quality_guided",seed); // FROZEN SOURCE
            a.status=v.status;
            a.stage1=v.stage1;a.stage2=v.stage2;
            a.first_budget=v.first_budget;a.second_budget=v.second_budget;
            a.hints=v.phases;
            a.extended=v.extended;a.resumed=v.resumed;
            a.offered=v.observed;a.short5=v.short5;
            a.short_fraction=v.short_fraction;
            a.total_us=v.elapsed_us;a.probe_us=v.probe_us;
            a.extension_us=v.extension_us;a.resume_us=v.resume_us;
            a.observer_connected=true;
        } else if(mode=="adaptive_two_checkpoint") {
            a=ablation(f,"adaptive_two_checkpoint",true,seed);
        } else if(mode=="adaptive_guarded_v87") {
            a=ablation(f,"adaptive_guarded_v87",true,seed);
        } else if(mode=="v94_cautious") {
            // v9.4 -- frozen BEFORE fetching any new holdout source CNF.
            // One O(input literal occurrences) pre-search structure probe.
            // Choose between original unhinted CaDiCaL and frozen sparse hints;
            // no SAT/UNSAT label, instance ID, or reference timing is used.
            V92Static d;
            const auto probe=v92_static_hints(f,true,d);
            const int64_t N=std::max(1,f.vars);
            const int64_t M=std::max<int64_t>(1,f.clauses.size());
            const bool use_sparse=(d.strong>=32 &&
                     int64_t(d.strong)*5>=N &&
                     int64_t(d.clause3+d.clause4)*2>=M &&
                     d.max_width<=10);
            if(use_sparse) {
                a=ablation(f,"v92_sparse",false,seed,true);
                a.gate_reason="v94_selected_sparse";
            } else {
                const auto v=run76(f,"plain",seed);  // untouched CaDiCaL
                a.status=v.status;
                a.stage1=v.stage1;a.stage2=v.stage2;
                a.first_budget=v.first_budget;
                a.second_budget=v.second_budget;
                a.hints=v.hinted;
                a.active_pre=v.active_pre;a.active_256=v.active_256;
                a.redundant_pre=v.redundant_pre;
                a.redundant_256=v.redundant_256;
                a.learned_delta=v.learned;a.threshold=v.learned_threshold;
                a.extended=v.extended;a.resumed=v.resumed;
                a.total_us=v.total_us;a.probe_us=v.probe_us;
                a.extension_us=v.extension_us;a.resume_us=v.resume_us;
                a.gate_reason="v94_selected_cadical";
            }
            a.v92_static_us+=d.analysis_us;
            a.v92_strong_candidates=d.strong;
            a.v92_broad_candidates=d.broad;
        } else if(mode=="v92_structural") {
            a=ablation(f,"v92_structural",false,seed,true);
        } else if(mode=="v92_sparse") {
            a=ablation(f,"v92_sparse",false,seed,true);
        } else if(mode=="v92_full_compat") {
            a=ablation(f,"v92_full",false,seed,true);
        } else if(mode=="v91_quality_gate") {
            a=ablation(f,"v91_gate",false,seed,true);
        } else if(mode=="v91_always_late") {
            a=ablation(f,"v91_always",false,seed,true);
        } else if(mode=="v91_never_late") {
            a=ablation(f,"v91_never",false,seed,true);
        } else if(mode=="v90_quality_guided") {
            a=ablation(f,"v90_quality",false,seed,true);
        } else if(mode=="v90_quality_no_hints") {
            a=ablation(f,"v90_quality",false,seed,false);
        } else if(mode=="v89_rate_no_hints") {
            a=ablation(f,"v89_rate",false,seed,false);
        } else if(mode=="v89_rate_late_hints") {
            a=ablation(f,"v89_rate",false,seed,true);
        } else if(mode=="delayed_v88b") {
            a=ablation(f,"delayed_v88b",false,seed,true);
        } else if(mode=="delayed_v88b_no_hints") {
            a=ablation(f,"delayed_v88b",false,seed,false);
        } else if(mode=="lowlevel_v88") {
            a=ablation(f,"lowlevel_v88",false,seed,true);
        } else if(mode=="lowlevel_v88_no_hints") {
            a=ablation(f,"lowlevel_v88",false,seed,false);
        } else if(mode=="adaptive_guarded_v87_no_hints") {
            a=ablation(f,"adaptive_guarded_v87",true,seed,false);
        } else if(mode=="adaptive_two_checkpoint_no_hints") {
            a=ablation(f,"adaptive_two_checkpoint",true,seed,false);
        } else if(mode=="hybrid_gate_with_observer") {
            a=ablation(f,"hybrid_gate",true,seed);
        } else if(mode=="old_gate_with_observer") {
            a=ablation(f,"old_rule",true,seed);
        } else if(mode=="new_gate_with_observer") {
            a=ablation(f,"new_rule",true,seed);
        } else if(mode=="new_gate_no_hints") {
            a=ablation(f,"new_rule",true,seed,false);
        } else if(mode=="old_gate_no_hints") {
            a=ablation(f,"old_rule",false,seed,false);
        } else if(mode=="force_extend_with_observer") {
            a=ablation(f,"force_extend",true,seed);
        } else if(mode=="force_stop_with_observer") {
            a=ablation(f,"force_stop",true,seed);
        } else if(mode=="force_extend_no_observer") {
            a=ablation(f,"force_extend",false,seed);
        } else if(mode=="force_stop_no_observer") {
            a=ablation(f,"force_stop",false,seed);
        } else if(mode=="force_extend_no_hints") {
            a=ablation(f,"force_extend",false,seed,false);
        } else if(mode=="force_stop_no_hints") {
            a=ablation(f,"force_stop",false,seed,false);
        } else {
            throw std::runtime_error("Unknown diagnostic mode "+mode);
        }
        std::cout<<std::fixed<<std::setprecision(6);
        // Exact parseable key=value pair output; no manual timing anecdotes.
        std::cout<<"DRNAS_CAUSAL"<<"\tmode="<<mode
                 <<"\tanswer="<<(a.status==10?"SAT":"UNSAT")
                 <<"\ttotal_us="<<a.total_us
                 <<"\tprobe_us="<<a.probe_us
                 <<"\textension_us="<<a.extension_us
                 <<"\tresume_us="<<a.resume_us
                 <<"\tstage1="<<a.stage1
                 <<"\tstage2="<<a.stage2
                 <<"\tfirst_budget="<<a.first_budget
                 <<"\tsecond_budget="<<a.second_budget
                 <<"\thints="<<a.hints
                 <<"\textended="<<int(a.extended)
                 <<"\tresumed="<<int(a.resumed)
                 <<"\tactive_pre="<<a.active_pre
                 <<"\tactive_256="<<a.active_256
                 <<"\tredundant_pre="<<a.redundant_pre
                 <<"\tredundant_256="<<a.redundant_256
                 <<"\tlearned_delta="<<a.learned_delta
                 <<"\tthreshold="<<a.threshold
                 <<"\tgate_reason="<<a.gate_reason
                 <<"\tobserver="<<int(a.observer_connected)
                 <<"\toffered="<<a.offered
                 <<"\tshort5="<<a.short5
                 <<"\tshort_fraction="<<a.short_fraction
                 <<"\tstage3="<<a.stage3
                 <<"\tthird_budget="<<a.third_budget
                 <<"\tadaptive_keep="<<int(a.adaptive_keep)
                 <<"\tcheckpoint_learned="<<a.checkpoint_learned
                 <<"\tcheckpoint_offered="<<a.checkpoint_offered
                 <<"\tcheckpoint_short5="<<a.checkpoint_short5
                 <<"\tfinal_extension_us="<<a.final_extension_us
                 <<"\tv92_choice="<<a.v92_choice
                 <<"\tv92_broad="<<a.v92_broad_candidates
                 <<"\tv92_strong="<<a.v92_strong_candidates
                 <<"\tv92_clause2="<<a.v92_clause2
                 <<"\tv92_clause3="<<a.v92_clause3
                 <<"\tv92_clause4="<<a.v92_clause4
                 <<"\tv92_maxwidth="<<a.v92_maxwidth
                 <<"\tv92_static_us="<<a.v92_static_us
                 <<"\tv91_phase_applied="<<int(a.v91_phase_applied)
                 <<"\tv91_quality_signal="<<int(a.v91_gate_quality)
                 <<"\tv90_learned_256="<<a.v90_learned_256
                 <<"\tv90_lbd2_256="<<a.v90_lbd2_256
                 <<"\tv90_lbd4_256="<<a.v90_lbd4_256
                 <<"\tv90_lbd_sum_256="<<a.v90_lbd_sum_256
                 <<"\tv90_props_256="<<a.v90_props_256
                 <<"\tv90_jumps_256="<<a.v90_jumps_256
                 <<"\tv90_jumpdepth_256="<<a.v90_jumpdepth_256
                 <<"\tv90_conflicts_256="<<a.v90_conflicts_256
                 <<"\tv90_backtracks_256="<<a.v90_backtracks_256
                 <<"\tv96_status64="<<a.v96_status64
                 <<"\tv96_status128="<<a.v96_status128
                 <<"\tv96_c64="<<a.v96_c64
                 <<"\tv96_c128="<<a.v96_c128
                 <<"\tv96_lbd2_64="<<a.v96_lbd2_64
                 <<"\tv96_lbd2_128="<<a.v96_lbd2_128
                 <<"\tv96_lbd4_64="<<a.v96_lbd4_64
                 <<"\tv96_lbd4_128="<<a.v96_lbd4_128
                 <<"\tv96_props64="<<a.v96_props64
                 <<"\tv96_props128="<<a.v96_props128
                 <<"\tv96_jump64="<<a.v96_jump64
                 <<"\tv96_jump128="<<a.v96_jump128
                 <<"\tv96_learn64="<<a.v96_learn64
                 <<"\tv96_learn128="<<a.v96_learn128
                 <<"\tv90_learned_total="<<a.v90_learned_total
                 <<"\tv90_lbd2_total="<<a.v90_lbd2_total
                 <<"\tv90_props_total="<<a.v90_props_total
                 <<"\tcpu_256_ns="<<a.cpu_256_ns
                 <<"\tcpu_128_ns="<<a.cpu_128_ns
                 <<"\tcpu_total_ns="<<a.cpu_total_ns
                 <<"\tactive_384="<<a.active_384
                 <<"\tvars="<<f.vars
                 <<"\tclauses="<<f.clauses.size()
                 <<"\n";
        return 0;
    } catch(const std::exception &e) {
        std::cerr<<"DRNAS_CAUSAL_ERROR: "<<e.what()<<"\n";
        return 1;
    }
}
