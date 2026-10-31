// DRNAS SAT V7.5: limited-conflict phase probe, then return control to same
// unmodified CaDiCaL v3.0.1 solver. A 0 result from solve() means UNKNOWN,
// NOT UNSAT; the original solver is resumed with learned clauses intact.
// All methods load identical clauses, same solver library and flags.
// Exposes both stage outcome and wall-clock duration for independent review.
#define main drnas_v721_unused_main
#include "../drnas-sat-v7-2-1/confidence_bench.cpp"
#undef main

struct Outcome75 {
    int status=0;
    int probe_status=-1; // -1: not probed, 0 inconclusive, 10 SAT, 20 UNSAT
    int proposed=0;
    int probe_limit=0;
    double hint_us=0.0;
    double probe_us=0.0;
    double resume_us=0.0;
    double full_us=0.0;
    bool resumed=false;
};
static Outcome75 solve75(const Formula& f, const std::string& mode, uint32_t seed) {
    const auto beginning=Clock::now();
    CaDiCaL::Solver solver;
    fill_solver(solver,f);
    Outcome75 o;
    const bool plain=(mode=="plain");
    const bool full=(mode=="majority");
    const bool segmented=(mode=="split_plain256" || mode=="split_plain1024");
    const bool guided=(mode=="guided256" || mode=="guided1024" || mode=="random256" || mode=="random1024");
    if(!plain&&!full&&!segmented&&!guided)
        throw std::runtime_error("Unknown mode "+mode);
    Hints hints;
    if(full||guided) {
        add_phase_hints(f,hints,mode=="random256" || mode=="random1024",seed);
        o.hint_us=hints.analysis_us;
        o.proposed=(int)hints.literals.size();
        for(int lit:hints.literals) solver.phase(lit);
    }
    if(plain||full) {
        o.status=solver.solve();
    }else {
        o.probe_limit=(mode=="guided1024" || mode=="split_plain1024" || mode=="random1024")?1024:256;
        // This limit is for the NEXT solve() only; it is reset afterward.
        if(!solver.limit("conflicts",o.probe_limit))
            throw std::runtime_error("Unsupported CaDiCaL conflicts limit");
        const auto probe_start=Clock::now();
        o.probe_status=solver.solve();
        o.probe_us=std::chrono::duration<double,std::micro>(
                            Clock::now()-probe_start).count();
        if(o.probe_status==0) {
            // Remove only DRNAS's forced default decision polarity.
            // Crucially: no solver re-creation, NO lost learned clauses.
            for(int lit:hints.literals)solver.unphase(lit);
            const auto resume_start=Clock::now();
            o.status=solver.solve();
            o.resume_us=std::chrono::duration<double,std::micro>(
                              Clock::now()-resume_start).count();
            o.resumed=true;
        }else o.status=o.probe_status;
    }
    if(o.status!=10 && o.status!=20)
        throw std::runtime_error("Final solve returned UNKNOWN");
    if(o.status==10)check_sat_model(solver,f);
    o.full_us=std::chrono::duration<double,std::micro>(
                  Clock::now()-beginning).count();
    return o;
}
int main(int argc,char**argv) {
    try {
        if(argc!=4) {
            std::cerr<<"Usage: v75_single METHOD CNF SEED\n";
            return 2;
        }
        const std::string method(argv[1]);
        const Formula f=read_cnf(argv[2]); // input reading excluded equally
        const auto o=solve75(f,method,(uint32_t)std::stoul(argv[3]));
        std::cout<<std::fixed<<std::setprecision(7)
          <<"DRNAS_RESULT\t"<<method
          <<'\t'<<(o.status==10?"SAT":"UNSAT")
          <<'\t'<<o.full_us
          <<'\t'<<o.proposed
          <<'\t'<<o.probe_limit
          <<'\t'<<o.probe_status
          <<'\t'<<(o.resumed?1:0)
          <<'\t'<<o.hint_us
          <<'\t'<<o.probe_us
          <<'\t'<<o.resume_us
          <<'\t'<<f.vars
          <<'\t'<<f.clauses.size()<<"\n";
        return 0;
    } catch(const std::exception& error) {
        std::cerr<<"DRNAS_V75_ERROR: "<<error.what()<<"\n";
        return 1;
    }
}
