// DRNAS SAT V7.8: Ultra-cheap static FAST PATH + instrumental Benefit Predictor.
//
// EXPERIMENTAL research, not a general purpose acceleration claim.
// The fast path rejects tiny/atypical CNFs in O(1) after DIMACS parsing.
// When eligible, both guided and matched no-guidance paths pay the same
// O(literals) feature extraction to measure offline prediction signals.
// Threshold was frozen from V7.7 DEVELOPMENT before V7.8 holdout:
// n>=180, clauses>=800, 3.9 <= clauses/n <=4.4 (250-random SATLIB family).
//
// No use of CNF filename, SAT label, solver result or runtime in the gate.
// Unmodified CaDiCaL 3.0.1. Existing V7.7 quality callback is reused.
// Feature telemetry is OBSERVATIONAL: not a trained predictor, and a
// single trial cannot reveal the counterfactual unguided runtime.

#define main drnas_v77_benchmark_main_unused
#include "../drnas-sat-v7-7/v77_single.cpp"
#undef main

struct V78Features {
    bool selected=false;
    int variables=0,clauses=0;
    int proposed=0;
    double mean_hint_margin=-1;
    double strongly_biased_fraction=-1;
    double ternary_fraction=-1;
    double analysis_us=0;
};

static bool v78_gate(const Formula &f) {
    if(f.vars<180 || f.clauses.size()<800) return false;
    // Use integer arithmetic for reproducible exact fixed thresholds.
    // 3.9 <= clauses / vars <= 4.4
    return static_cast<uint64_t>(f.clauses.size())*10 >=
               static_cast<uint64_t>(f.vars)*39 &&
           static_cast<uint64_t>(f.clauses.size())*10 <=
               static_cast<uint64_t>(f.vars)*44;
}

static V78Features v78_features(const Formula &f,bool eligible) {
    const auto t=Clock::now();
    V78Features out;
    out.variables=f.vars;out.clauses=static_cast<int>(f.clauses.size());
    out.selected=eligible;
    if(eligible) {
        std::vector<int> pos(static_cast<size_t>(f.vars)+1,0);
        std::vector<int> neg(static_cast<size_t>(f.vars)+1,0);
        int ternary=0;
        for(const auto &c:f.clauses) {
            if(c.size()==3)ternary++;
            for(int lit:c)
                (lit>0?pos[lit]:neg[-lit])++;
        }
        int strongly=0;
        double total_margin=0;
        for(int v=1;v<=f.vars;v++) {
            const int count=pos[v]+neg[v];
            if(count<6 || pos[v]==neg[v] ||
               100*std::abs(pos[v]-neg[v])<15*count) continue;
            out.proposed++;
            const double margin=double(std::abs(pos[v]-neg[v]))/count;
            total_margin+=margin;
            if(margin>=0.30)strongly++;
        }
        out.mean_hint_margin=out.proposed?total_margin/out.proposed:0;
        out.strongly_biased_fraction=f.vars?double(strongly)/f.vars:0;
        out.ternary_fraction=f.clauses.empty()?
                              0:double(ternary)/f.clauses.size();
    }
    out.analysis_us=std::chrono::duration<double,std::micro>(
                            Clock::now()-t).count();
    return out;
}

int main(int argc,char **argv) {
    try {
        if(argc!=4) {
            std::cerr<<"Usage: v78_single MODE original.cnf SEED\n";
            return 2;
        }
        const std::string method=argv[1];
        const Formula f=read_cnf(argv[2]);
        const uint32_t seed=static_cast<uint32_t>(std::stoul(argv[3]));
        const bool selected=v78_gate(f);
        const bool fast=method=="fastpath_guided" ||
                        method=="fastpath_plain" ||
                        method=="fastpath_random" ||
                        method=="fastpath_majority";
        const bool instrumented=method=="profile_only";
        if(!fast&&!instrumented &&
           method!="plain" && method!="majority" &&
           method!="quality_guided" && method!="quality_plain" &&
           method!="quality_random" && method!="split1024" &&
           method!="guided1024")
            throw std::runtime_error("Unknown V7.8 benchmark method");

        // For fastpath modes, same selected O(literals) profiling overhead
        // across guided / no-hint / random / majority controls.
        const auto started=Clock::now();
        const V78Features features=v78_features(f,selected &&
                                                   (fast||instrumented));

        std::string underlying=method;
        if(fast) {
            if(!selected)underlying="plain";
            else if(method=="fastpath_guided")underlying="quality_guided";
            else if(method=="fastpath_plain")underlying="quality_plain";
            else if(method=="fastpath_random")underlying="quality_random";
            else underlying="majority";
        } else if(instrumented) underlying="plain";

        const V77 o=solve77(f,underlying,seed);
        const double total_us=std::chrono::duration<double,std::micro>(
                                    Clock::now()-started).count();
        std::cout<<std::fixed<<std::setprecision(8)
            <<"DRNAS_RESULT\t"<<method
            <<'\t'<<(o.status==10?"SAT":"UNSAT")
            <<'\t'<<total_us
            <<'\t'<<o.phases
            <<'\t'<<o.first_budget
            <<'\t'<<o.stage1
            <<'\t'<<o.second_budget
            <<'\t'<<o.stage2
            <<'\t'<<(o.extended?1:0)
            <<'\t'<<(o.resumed?1:0)
            <<'\t'<<o.observed
            <<'\t'<<o.short3
            <<'\t'<<o.short5
            <<'\t'<<o.short8
            <<'\t'<<o.sum_len
            <<'\t'<<o.short_fraction
            <<'\t'<<o.probe_us
            <<'\t'<<o.extension_us
            <<'\t'<<o.resume_us
            <<'\t'<<f.vars
            <<'\t'<<f.clauses.size()
            <<'\t'<<(selected?1:0)
            <<'\t'<<features.analysis_us
            <<'\t'<<features.mean_hint_margin
            <<'\t'<<features.strongly_biased_fraction
            <<'\t'<<features.ternary_fraction
            <<'\t'<<features.proposed
            <<"\n";
        return 0;
    } catch(const std::exception&e) {
        std::cerr<<"DRNAS_V78_ERROR: "<<e.what()<<"\n";
        return 1;
    }
}
