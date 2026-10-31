// DRNAS V8.6: experimental bounded two-checkpoint adaptive decision.
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

struct Audit {
    int status=0, stage1=-1,stage2=-1,stage3=-1, first_budget=256,second_budget=0,third_budget=0;
    int hints=0,active_pre=0,active_256=0,threshold=0;
    std::string gate_reason="n/a";
    bool extended=false,resumed=false,observer_connected=false,adaptive_keep=false;
    int64_t redundant_pre=0,redundant_256=0,learned_delta=0,checkpoint_learned=0;
    uint64_t offered=0,short5=0,checkpoint_offered=0,checkpoint_short5=0;
    double short_fraction=0, total_us=0,probe_us=0,extension_us=0,resume_us=0,checkpoint_us=0,final_extension_us=0;
};

// This is an A/B copy of the phase+checkpoint path, for measuring policy and
// the public Learner observer independently. Solver is always CaDiCaL 3.0.1.
// 'old_rule' = original V7.6 redundant-delta/active threshold.
// 'new_rule' = original V7.7 >=32,>=10 short5, >=20% clause shortness.
// 'force_extend' / 'force_stop' are matched boundary controls (NOT releases).
static Audit ablation(const Formula &f,const std::string &policy,
                      bool use_observer,uint32_t seed,bool enable_hints=true) {
    const auto start=Clock::now();
    // Observer must outlive solver (as in the frozen original V7.7).
    ClauseSizeObserver obs;
    CaDiCaL::Solver solver;
    fill_solver(solver,f);
    if(use_observer) solver.connect_learner(&obs);
    Audit a;
    a.observer_connected=use_observer;
    Hints h;
    if(enable_hints) add_phase_hints(f,h,false,seed); // matched no-hint ablation
    a.hints=static_cast<int>(h.literals.size());
    for(const int lit:h.literals) solver.phase(lit);

    a.redundant_pre=solver.redundant();
    a.active_pre=solver.active();
    a.threshold=std::max(48,(a.active_pre+3)/4);
    if(!solver.limit("conflicts",256))
        throw std::runtime_error("CaDiCaL rejected first 256 conflict limit");
    auto phase_start=Clock::now();
    a.stage1=solver.solve();
    a.probe_us=std::chrono::duration<double,std::micro>(
                    Clock::now()-phase_start).count();
    a.redundant_256=solver.redundant();
    a.active_256=solver.active();
    a.learned_delta=std::max<int64_t>(0,a.redundant_256-a.redundant_pre);
    a.offered=obs.observed;
    a.short5=obs.short5;
    a.short_fraction=a.offered?double(a.short5)/a.offered:0.;
    if(a.stage1==0) {
        if(policy=="old_rule") {
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
        } else if(policy=="adaptive_two_checkpoint") {
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
        } else if(policy=="force_extend") {
            a.extended=true;
        } else if(policy=="force_stop") {
            a.extended=false;
        } else throw std::runtime_error("Unknown policy");
        int after=a.stage1;
        if(a.extended) {
            const bool adaptive=policy=="adaptive_two_checkpoint";
            a.second_budget=adaptive?128:768;
            if(!solver.limit("conflicts",a.second_budget))
                throw std::runtime_error("CaDiCaL rejected extension");
            const auto next=Clock::now();
            a.stage2=solver.solve();
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
                 <<"\tvars="<<f.vars
                 <<"\tclauses="<<f.clauses.size()
                 <<"\n";
        return 0;
    } catch(const std::exception &e) {
        std::cerr<<"DRNAS_CAUSAL_ERROR: "<<e.what()<<"\n";
        return 1;
    }
}
