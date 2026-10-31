// DRNAS SAT V7.6 — NeuroFlow learned-clause-yield adaptive conflict budgeting.
//
// Unmodified CaDiCaL 3.0.1, ONE solver instance throughout.
// The decision at the 256-conflict checkpoint sees ONLY the current solver's
// redundant()/active() statistics; no SAT/UNSAT label or file/family name.
// If sufficiently many learned clauses survive (>= max(48, ceil(active/4))),
// keep initial phase hints for at most 768 more conflicts (two segments).
// Otherwise unphase immediately and continue unbounded. In either case
// learned clauses persist because the solver object is NEVER replaced.
//
// Critical matched control adaptive_plain executes the SAME two-step decision
// and same restart boundaries but does not set any phase hints.
//
// CaDiCaL::Solver::get(...) is an *option* API, NOT a statistics API;
// redundant()/active() are the actual supported observations.
//
// Freeze this rule BEFORE prospective benchmark. This is exploratory
// research; no general speedups claimed from the design itself.

#define main drnas_v721_main_unused
#include "../drnas-sat-v7-2-1/confidence_bench.cpp"
#undef main

struct V76 {
    int status=0,stage1=-1,stage2=-1;
    int hinted=0;
    bool extended=false,resumed=false;
    int64_t learned=0, redundant_pre=0, redundant_256=0;
    int active_pre=0,active_256=0;
    int learned_threshold=0;
    int first_budget=0,second_budget=0;
    double hint_us=0,probe_us=0,extension_us=0,resume_us=0,total_us=0;
};

V76 run76(const Formula &f, const std::string &method,uint32_t seed) {
    const auto start=Clock::now();
    CaDiCaL::Solver solver;
    fill_solver(solver,f);

    const bool plain=(method=="plain");
    const bool majority=(method=="majority");
    const bool split256=(method=="split256");
    const bool split1024=(method=="split1024");
    const bool guided1024=(method=="guided1024");
    const bool adapt=(method=="adaptive_plain" || method=="adaptive_guided" ||
                      method=="adaptive_random");
    if(!plain&&!majority&&!split256&&!split1024&&!guided1024&&!adapt)
        throw std::runtime_error("Unknown V7.6 method: "+method);

    V76 v;
    Hints h;
    if(majority||guided1024||method=="adaptive_guided"||method=="adaptive_random") {
        add_phase_hints(f,h,method=="adaptive_random",seed);
        v.hinted=(int)h.literals.size();
        v.hint_us=h.analysis_us;
        for(int lit:h.literals)solver.phase(lit);
    }

    if(plain||majority) {
        v.status=solver.solve();
    } else if(adapt) {
        v.first_budget=256;
        v.redundant_pre=solver.redundant();
        v.active_pre=solver.active();
        if(!solver.limit("conflicts",v.first_budget))
            throw std::runtime_error("CaDiCaL did not accept conflict limit");
        const auto before=Clock::now();
        v.stage1=solver.solve();
        v.probe_us=std::chrono::duration<double,std::micro>(Clock::now()-before).count();

        if(v.stage1==0) {
            v.redundant_256=solver.redundant();
            v.active_256=solver.active();
            v.learned=std::max<int64_t>(0,v.redundant_256-v.redundant_pre);
            v.learned_threshold=std::max(48,(v.active_pre+3)/4);
            // Deterministic causal hypothesis: the first 256 conflicts
            // made substantial durable learned-clause progress. Extending
            // is NOT proof that hints helped; matched controls test that.
            v.extended=(v.learned>=v.learned_threshold &&
                        v.active_256>0);
            int after=v.stage1;
            if(v.extended) {
                // Conflict limits apply to the NEXT solve() only, which
                // is a continuation of the SAME solver / learned database.
                v.second_budget=768;
                if(!solver.limit("conflicts",v.second_budget))
                    throw std::runtime_error("CaDiCaL failed second limit");
                const auto ext_start=Clock::now();
                v.stage2=solver.solve();
                v.extension_us=std::chrono::duration<double,std::micro>(
                    Clock::now()-ext_start).count();
                after=v.stage2;
            }
            if(after==0) {
                for(int lit:h.literals)solver.unphase(lit);
                const auto resume_start=Clock::now();
                v.status=solver.solve();
                v.resume_us=std::chrono::duration<double,std::micro>(
                    Clock::now()-resume_start).count();
                v.resumed=true;
            } else v.status=after;
        }else v.status=v.stage1;
    }else {
        v.first_budget=(split256?256:1024);
        if(!solver.limit("conflicts",v.first_budget))
            throw std::runtime_error("CaDiCaL failed single conflict limit");
        const auto before=Clock::now();
        v.stage1=solver.solve();
        v.probe_us=std::chrono::duration<double,std::micro>(Clock::now()-before).count();
        if(v.stage1==0) {
            for(int lit:h.literals)solver.unphase(lit);
            const auto resume_start=Clock::now();
            v.status=solver.solve();
            v.resume_us=std::chrono::duration<double,std::micro>(
                   Clock::now()-resume_start).count();
            v.resumed=true;
        }else v.status=v.stage1;
    }
    if(v.status!=10 && v.status!=20)
        throw std::runtime_error("Final solver status was UNKNOWN");
    if(v.status==10)check_sat_model(solver,f);
    v.total_us=std::chrono::duration<double,std::micro>(Clock::now()-start).count();
    return v;
}
int main(int argc,char **argv) {
    try {
        if(argc!=4) {
            std::cerr<<"Usage: v76_single MODE ORIGINAL_CNFDIMACS SEED\n";
            return 2;
        }
        const std::string mode=argv[1];
        const Formula f=read_cnf(argv[2]); // identical file-read exclusion
        const V76 r=run76(f,mode,(uint32_t)std::stoul(argv[3]));
        std::cout<<std::fixed<<std::setprecision(8)
         <<"DRNAS_RESULT\t"<<mode
         <<'\t'<<(r.status==10?"SAT":"UNSAT")
         <<'\t'<<r.total_us
         <<'\t'<<r.hinted
         <<'\t'<<r.first_budget
         <<'\t'<<r.stage1
         <<'\t'<<(r.extended?1:0)
         <<'\t'<<r.learned
         <<'\t'<<r.learned_threshold
         <<'\t'<<r.active_pre
         <<'\t'<<r.active_256
         <<'\t'<<r.second_budget
         <<'\t'<<r.stage2
         <<'\t'<<(r.resumed?1:0)
         <<'\t'<<r.hint_us
         <<'\t'<<r.probe_us
         <<'\t'<<r.extension_us
         <<'\t'<<r.resume_us
         <<'\t'<<f.vars
         <<'\t'<<f.clauses.size()
         <<"\n";
        return 0;
    } catch(const std::exception &e) {
        std::cerr<<"DRNAS_V76_ERROR: "<<e.what()<<"\n";
        return 1;
    }
}
