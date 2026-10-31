// DRNAS SAT NeuroFlow V7.9 -- selective checkpoint / phase policy.
//
// IMPORTANT: This version does not change upstream CaDiCaL rel-3.0.1.
// Its rule is a FROZEN research hypothesis, not a trained, validated AI model.
// Three paths:
// 0 = unmodified, unsplit CaDiCaL for small/huge formulas
// 1 = 1024-conflict checkpoint then unbounded resume, NO phase hints
// 2 = same 1024-conflict checkpoint, then up to 512 conflicts with hints,
//     then unphase and unbounded resume of THE SAME solver.
// Selection sees only *this solver's own* clause-size callback after 1024
// unhinted conflicts, plus original CNF sign imbalance. NO SAT answers,
// family names, filenames, results from other methods, or instance runtimes.
// All matched variants measure identical features, observe same checkpoint,
// take identical path and budgets, differing ONLY in applied phase signs.
// "No intervention" truly applies ONLY to the initial static bypass. Once a
// checkpoint has occurred, cannot retroactively undo splitting.
//
// This is not an LBD metric; clause callback offers are not guaranteed to
// include every internal learned clause.

#define DRNAS_V77_EMBEDDED
#include "../drnas-sat-v7-7/v77_single.cpp"
#undef DRNAS_V77_EMBEDDED

struct V79Result {
    int status=0, path=0, checkpoint=0, stage1=-1, stage2=-1;
    int candidate_count=0, budget2=0;
    int variables=0, clauses=0;
    bool extended=false,resumed=false,eligible=false;
    uint64_t observed=0,short5=0;
    double short_ratio=0,preflight_us=0,probe_us=0,extend_us=0,resume_us=0,total_us=0;
};

static bool v79_eligible(const Formula &f) {
    // A priori resource-protection guard; 100% metadata, O(1).
    return f.vars>=180 && f.vars<=120000 &&
           f.clauses.size()>=800 && f.clauses.size()<=500000;
}

static V79Result solve79(const Formula &f,
                         const std::string &method,uint32_t seed) {
    const auto started=Clock::now();
    V79Result out;
    out.variables=f.vars;
    out.clauses=static_cast<int>(f.clauses.size());
    out.eligible=v79_eligible(f);

    const bool normal = method=="plain" || method=="split1024" ||
                        method=="guided1024" || method=="quality_guided" ||
                        method=="quality_plain";
    const bool proposed = method=="v79_selective";
    const bool control = method=="v79_matched_plain";
    const bool random = method=="v79_matched_random";
    const bool forced = method=="v79_forced_guided";
    if(!normal&&!proposed&&!control&&!random&&!forced)
        throw std::runtime_error("Unknown V7.9 method "+method);

    if(normal) {
        auto r=solve77(f,method,seed);
        out.status=r.status;
        out.checkpoint=r.first_budget;
        out.stage1=r.stage1;
        out.stage2=r.stage2;
        out.budget2=r.second_budget;
        out.candidate_count=r.phases;
        out.extended=r.extended;out.resumed=r.resumed;
        out.path=method=="plain"?0:method=="guided1024"?2:1;
        out.observed=r.observed;out.short5=r.short5;
        out.short_ratio=r.short_fraction;
        out.probe_us=r.probe_us;out.extend_us=r.extension_us;
        out.resume_us=r.resume_us;
    } else if(!out.eligible) {
        // No restart or learner callback. Existing solver path exactly plain.
        CaDiCaL::Solver solver;
        fill_solver(solver,f);
        out.status=solver.solve();
        if(out.status==10)check_sat_model(solver,f);
    } else {
        // Always derive the exact same formula-polarity feature set and
        // monitor short clauses for the three SELECTED/MATCHED paths.
        ClauseSizeObserver observer;
        CaDiCaL::Solver solver;
        fill_solver(solver,f);
        solver.connect_learner(&observer);
        Hints h;
        const auto hint_started=Clock::now();
        add_phase_hints(f,h,false,seed);
        out.candidate_count=static_cast<int>(h.literals.size());
        out.preflight_us=std::chrono::duration<double,std::micro>(
                                 Clock::now()-hint_started).count();
        out.checkpoint=1024;
        if(!solver.limit("conflicts",1024))
            throw std::runtime_error("CaDiCaL rejected 1024 checkpoint");
        const auto probe_started=Clock::now();
        out.stage1=solver.solve();
        out.probe_us=std::chrono::duration<double,std::micro>(
                                 Clock::now()-probe_started).count();
        out.observed=observer.observed;
        out.short5=observer.short5;
        out.short_ratio=out.observed?double(out.short5)/out.observed:0;

        // Deterministic frozen eligibility: considerable clause offer yield,
        // short offers and nontrivial but not almost-global polarity signal.
        // The previous 15 benchmark cases informed the research *design*,
        // hence none of those can validate this rule prospectively.
        const bool informative=
            out.observed>=64 &&
            out.short5>=20 &&
            100*out.short5>=37*out.observed &&
            out.candidate_count>=64 &&
            4LL*out.candidate_count>=f.vars &&
            4LL*out.candidate_count<=3LL*f.vars;
        const bool apply=(forced || informative) && out.stage1==0;
        out.path=apply?2:1;

        // Flush telemetry BEFORE the potentially long continuation, even
        // when the external 15-second process cutoff later fires.
        std::cout<<"DRNAS_PROBE\t"<<method
                 <<'\t'<<(out.path==2?"guide":"split")
                 <<'\t'<<out.observed
                 <<'\t'<<out.short5
                 <<'\t'<<std::fixed<<std::setprecision(6)<<out.short_ratio
                 <<'\t'<<out.candidate_count
                 <<'\t'<<f.vars
                 <<'\t'<<f.clauses.size()
                 <<'\t'<<out.probe_us
                 <<'\n'<<std::flush;

        if(out.stage1!=0) {
            out.status=out.stage1;
        } else {
            if(apply) {
                out.budget2=512;
                out.extended=true;
                if(!control) {
                    // random uses EXACT SAME selected variables as proposed;
                    // only their signs differ.
                    std::mt19937 rng(seed);
                    for(int lit:h.literals) {
                        const int chosen=random ?
                            (std::abs(lit)*((rng()&1)?1:-1)) : lit;
                        solver.phase(chosen);
                    }
                }
                if(!solver.limit("conflicts",out.budget2))
                    throw std::runtime_error("CaDiCaL rejected 512 extension");
                const auto ext_started=Clock::now();
                out.stage2=solver.solve();
                out.extend_us=std::chrono::duration<double,std::micro>(
                                       Clock::now()-ext_started).count();
                if(out.stage2!=0) {
                    out.status=out.stage2;
                }
            }
            if(out.status==0) {
                // Clear only the phase guidance we applied, never reset
                // the solver or discard its learned clauses.
                if(apply && !control) {
                    for(int lit:h.literals)solver.unphase(lit);
                }
                const auto resume_started=Clock::now();
                out.status=solver.solve();
                out.resume_us=std::chrono::duration<double,std::micro>(
                                         Clock::now()-resume_started).count();
                out.resumed=true;
            }
        }
        if(out.status==10)check_sat_model(solver,f);
        solver.disconnect_learner();
    }
    if(out.status!=10 && out.status!=20)
        throw std::runtime_error("V7.9 final solver returned UNKNOWN");
    out.total_us=std::chrono::duration<double,std::micro>(
                            Clock::now()-started).count();
    return out;
}

int main(int argc,char **argv) {
    try {
        if(argc!=4) {
            std::cerr<<"Usage: v79_single METHOD original.cnf SEED\n";
            return 2;
        }
        const std::string method=argv[1];
        const Formula f=read_cnf(argv[2]);
        const uint32_t seed=static_cast<uint32_t>(std::stoul(argv[3]));
        const V79Result r=solve79(f,method,seed);
        std::cout<<std::fixed<<std::setprecision(8)
            <<"DRNAS_RESULT\t"<<method
            <<'\t'<<(r.status==10?"SAT":"UNSAT")
            <<'\t'<<r.total_us
            <<'\t'<<r.path
            <<'\t'<<(r.eligible?1:0)
            <<'\t'<<r.checkpoint
            <<'\t'<<r.stage1
            <<'\t'<<r.budget2
            <<'\t'<<r.stage2
            <<'\t'<<r.candidate_count
            <<'\t'<<r.observed
            <<'\t'<<r.short5
            <<'\t'<<r.short_ratio
            <<'\t'<<r.preflight_us
            <<'\t'<<r.probe_us
            <<'\t'<<r.extend_us
            <<'\t'<<r.resume_us
            <<'\t'<<(r.resumed?1:0)
            <<'\t'<<r.variables
            <<'\t'<<r.clauses
            <<'\n';
        return 0;
    } catch (const std::exception &e) {
        std::cerr<<"DRNAS_V79_ERROR: "<<e.what()<<"\n";
        return 1;
    }
}
