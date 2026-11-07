// DRNAS SAT V7.7: Learned-Clause Shortness NeuroFlow, official CaDiCaL 3.0.1.
// The public Learner::learning(size) callback measures offered clause sizes;
// returns false, never copies literals. This is NOT an LBD measurement and
// may not include all internally learned clauses.
// At checkpoint 256: extend guidance by <=768 conflicts only if >=32 offered
// clauses, >=10 short clauses (size<=5), and >=20% short fraction.
// Otherwise unphase and continue. No solver re-creation, learnt clauses stay.
// Predeclared rule, prospective holdout, identical callback no-hint control.
#define DRNAS_V76_EMBEDDED
#include "../drnas-sat-v7-6/v76_single.cpp"
#undef DRNAS_V76_EMBEDDED

struct ClauseSizeObserver : CaDiCaL::Learner {
    uint64_t observed=0,short3=0,short5=0,short8=0,sum_len=0;
    bool learning(int size) override {
        if(size>=0) {
            ++observed;
            if(size<=3)++short3;
            if(size<=5)++short5;
            if(size<=8)++short8;
            sum_len+=static_cast<uint64_t>(size);
        }
        return false;
    }
    void learn(int) override {}
};

struct V77 {
    int status=0,stage1=-1,stage2=-1,phases=0;
    int first_budget=0,second_budget=0;
    bool extended=false,resumed=false;
    uint64_t observed=0,short3=0,short5=0,short8=0,sum_len=0;
    double short_fraction=0,elapsed_us=0,probe_us=0,extension_us=0,resume_us=0;
};

static V77 solve77(const Formula& f,const std::string &method,uint32_t seed) {
    const auto start=Clock::now();
    if(method=="plain" || method=="majority" || method=="split1024" ||
       method=="guided1024" || method=="v76_guided") {
        auto r=run76(f,method=="v76_guided"?"adaptive_guided":method,seed);
        V77 o;
        o.status=r.status;
        o.stage1=r.stage1;o.stage2=r.stage2;
        o.phases=r.hinted;
        o.first_budget=r.first_budget;o.second_budget=r.second_budget;
        o.extended=r.extended;o.resumed=r.resumed;
        o.elapsed_us=r.total_us;o.probe_us=r.probe_us;
        o.extension_us=r.extension_us;o.resume_us=r.resume_us;
        return o;
    }
    const bool quality=(method=="quality_plain"||
                        method=="quality_guided"||method=="quality_random");
    const bool monitor=(method=="observe_plain1024");
    if(!quality&&!monitor)throw std::runtime_error("Unknown V7.7 method");
    // Observer lives longer than solver even if solver destructor calls it.
    ClauseSizeObserver observer;
    CaDiCaL::Solver solver;
    fill_solver(solver,f);
    solver.connect_learner(&observer);
    Hints hints;
    if(method=="quality_guided" || method=="quality_random") {
        add_phase_hints(f,hints,method=="quality_random",seed);
        for(int lit:hints.literals)solver.phase(lit);
    }
    V77 o;o.phases=static_cast<int>(hints.literals.size());
    o.first_budget=monitor?1024:256;
    if(!solver.limit("conflicts",o.first_budget))
        throw std::runtime_error("CaDiCaL rejected conflict limit");
    const auto stage_start=Clock::now();
    o.stage1=solver.solve();
    o.probe_us=std::chrono::duration<double,std::micro>(
                           Clock::now()-stage_start).count();
    o.observed=observer.observed;
    o.short3=observer.short3;o.short5=observer.short5;
    o.short8=observer.short8;o.sum_len=observer.sum_len;
    o.short_fraction=o.observed?double(o.short5)/o.observed:0.0;
    if(o.stage1==0) {
        if(quality) {
            o.extended=(o.observed>=32 && o.short5>=10 &&
                        5*o.short5>=o.observed);
            if(o.extended) {
                o.second_budget=768;
                if(!solver.limit("conflicts",o.second_budget))
                    throw std::runtime_error("CaDiCaL rejected 768 extension");
                const auto mid=Clock::now();
                o.stage2=solver.solve();
                o.extension_us=std::chrono::duration<double,std::micro>(
                              Clock::now()-mid).count();
            }
        }
        const int interim=o.extended?o.stage2:o.stage1;
        if(interim==0) {
            for(int lit:hints.literals)solver.unphase(lit);
            const auto again=Clock::now();
            o.status=solver.solve();
            o.resume_us=std::chrono::duration<double,std::micro>(
                              Clock::now()-again).count();
            o.resumed=true;
        }else o.status=interim;
    } else o.status=o.stage1;
    if(o.status!=10&&o.status!=20)
        throw std::runtime_error("V7.7 final solver status UNKNOWN");
    if(o.status==10)check_sat_model(solver,f);
    solver.disconnect_learner();
    o.elapsed_us=std::chrono::duration<double,std::micro>(
                          Clock::now()-start).count();
    return o;
}

int main(int argc,char**argv) {
    try {
        if(argc!=4) {
            std::cerr<<"Usage: v77_single METHOD original.cnf SEED\n";
            return 2;
        }
        const std::string method=argv[1];
        const Formula f=read_cnf(argv[2]);
        const V77 r=solve77(f,method,static_cast<uint32_t>(std::stoul(argv[3])));
        std::cout<<std::fixed<<std::setprecision(8)
            <<"DRNAS_RESULT\t"<<method
            <<'\t'<<(r.status==10?"SAT":"UNSAT")
            <<'\t'<<r.elapsed_us
            <<'\t'<<r.phases
            <<'\t'<<r.first_budget
            <<'\t'<<r.stage1
            <<'\t'<<r.second_budget
            <<'\t'<<r.stage2
            <<'\t'<<(r.extended?1:0)
            <<'\t'<<(r.resumed?1:0)
            <<'\t'<<r.observed
            <<'\t'<<r.short3
            <<'\t'<<r.short5
            <<'\t'<<r.short8
            <<'\t'<<r.sum_len
            <<'\t'<<r.short_fraction
            <<'\t'<<r.probe_us
            <<'\t'<<r.extension_us
            <<'\t'<<r.resume_us
            <<'\t'<<f.vars
            <<'\t'<<f.clauses.size()
            <<"\n";
        return 0;
    } catch(const std::exception &e) {
        std::cerr<<"DRNAS_V77_ERROR: "<<e.what()<<"\n";
        return 1;
    }
}
