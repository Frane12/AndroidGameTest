// DRNAS SAT V7.3: conservative phase risk control over the EXACT unmodified
// V7.2.1 and official CaDiCaL 3.0.1 C++ API. Builds a single CaDiCaL solver.
// All gate, sign tally, solver setup and solving are timed. Source graph
// or family name is NEVER consulted for deciding when to emit phases.
#define main original_v721_unused_main
#include "../drnas-sat-v7-2-1/confidence_bench.cpp"
#undef main

struct Risk {
    Hints hints;
    double mean_margin=0.0;
    double strong_fraction=0.0;
    int supported=0;
};

Risk risk_hints(const Formula &f,bool strong_only) {
    const auto start=Clock::now();
    Risk result;
    Hints &h=result.hints;
    h=confidence_gate(f);
    if(!h.selected)return result;

    std::vector<int> pos(f.vars+1,0),neg(f.vars+1,0);
    for(const auto &clause:f.clauses)
      for(int lit:clause)(lit>0?pos[lit]:neg[-lit])++;

    int eligible=0, strong=0;
    double total_margin=0;
    std::vector<int> advice;
    for(int v=1;v<=f.vars;v++) {
        const int a=pos[v],b=neg[v],count=a+b;
        if(count<6 || a==b)continue;
        const double margin=double(std::abs(a-b))/count;
        if(margin<0.15)continue;
        eligible++;
        total_margin+=margin;
        if(margin>=0.30)strong++;
        if(!strong_only || margin>=0.30)advice.push_back(a>b?v:-v);
    }
    result.mean_margin=eligible?total_margin/eligible:0.0;
    result.strong_fraction=f.vars?double(strong)/f.vars:0.0;
    result.supported=eligible;

    // FROZEN conservative guard. Developed on previous public instances,
    // not on the prospective real-world validation instances.
    // Abstention is important: polarities are only hints, NOT constraints.
    const bool safe=(eligible>=12 && result.mean_margin>=0.28 &&
                     result.strong_fraction>=0.10);
    h.selected=safe;
    if(safe)h.literals=std::move(advice);
    h.candidates=h.literals.size();
    h.analysis_us=std::chrono::duration<double,std::micro>(Clock::now()-start).count();
    return result;
}
struct V73Outcome {
    int status=0;
    Risk risk;
};
V73Outcome solve_v73(const Formula &f,const std::string &method) {
    CaDiCaL::Solver solver;
    fill_solver(solver,f);
    Risk decision=risk_hints(f,method=="risk_strong");
    for(int lit:decision.hints.literals)solver.phase(lit);
    int status=solver.solve();
    if(status!=10 && status!=20)throw std::runtime_error("CaDiCaL returned UNKNOWN");
    if(status==10)check_sat_model(solver,f);
    return {status,std::move(decision)};
}
int main(int argc,char **argv) {
    try{
        if(argc!=4){
            std::cerr<<"Usage: risk_single method input.cnf seed\n";
            return 2;
        }
        const std::string method(argv[1]);
        const auto f=read_cnf(argv[2]);  // file I/O excluded EQUALLY
        const uint32_t seed=(uint32_t)std::stoul(argv[3]);

        if(method=="risk_features") {
            const auto r=risk_hints(f,false);
            std::cout<<std::setprecision(12)
              <<"DRNAS_FEATURES\t"<<(fast_gate(f).selected?1:0)
              <<'\t'<<(confidence_gate(f).selected?1:0)
              <<'\t'<<(r.hints.selected?1:0)<<'\t'<<r.hints.analysis_us
              <<'\t'<<r.mean_margin<<'\t'<<r.strong_fraction
              <<'\t'<<r.supported<<'\t'<<r.hints.pair_reuse
              <<'\t'<<f.vars<<'\t'<<f.clauses.size()<<"\n";
            return 0;
        }
        const auto start=Clock::now();
        int status;
        Hints h;
        double mean_margin=0, strong_fraction=0;
        int supported=0;
        if(method=="risk_guard" || method=="risk_strong") {
            auto result=solve_v73(f,method);
            status=result.status;
            h=std::move(result.risk.hints);
            mean_margin=result.risk.mean_margin;
            strong_fraction=result.risk.strong_fraction;
            supported=result.risk.supported;
        } else {
            if(method!="plain" && method!="majority" &&
               method!="confidence" && method!="selective")
              throw std::runtime_error("Unknown method");
            auto out=solve(f,method,seed);
            status=out.status;
            h=std::move(out.hint);
        }
        const double elapsed=std::chrono::duration<double,std::micro>(Clock::now()-start).count();
        std::cout<<std::setprecision(12)
          <<"DRNAS_RESULT\t"<<method
          <<'\t'<<(status==10?"SAT":"UNSAT")
          <<'\t'<<elapsed
          <<'\t'<<(h.selected?1:0)<<'\t'<<h.candidates
          <<'\t'<<h.analysis_us<<'\t'<<h.pair_reuse
          <<'\t'<<f.vars<<'\t'<<f.clauses.size()
          <<'\t'<<mean_margin<<'\t'<<strong_fraction
          <<'\t'<<supported<<"\n";
        return 0;
    }catch(const std::exception &e){
        std::cerr<<"ERROR: "<<e.what()<<"\n";
        return 1;
    }
}
