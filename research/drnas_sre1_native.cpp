// DRNAS SRE1 Native — own R3C CDCL with certified cross-representation reduction.
// Reference native CDCL compiled from source directly; no foreign SAT solver.
#define main drnas_r3c_base_entry
#include "drnas_native_core_r3c.cpp"
#undef main
#include "drnas_sre1_reduction.hpp"

namespace drnas {
static CNF sre1_radio(bool impossible) {
    CNF f; f.vars=15;
    const std::vector<std::pair<int,int>> edges={
        {0,1},{0,2},{1,2},{0,3},{2,3},{0,4},{1,4},{3,4}};
    for(int v=0;v<5;++v){
        const int a=3*v+1,b=a+1,c=a+2;
        f.clauses.push_back({a,b,c});
        f.clauses.push_back({-a,-b});
        f.clauses.push_back({-a,-c});
        f.clauses.push_back({-b,-c});
    }
    auto add_edge=[&](int a,int b){
        for(int k=0;k<3;++k)f.clauses.push_back({-(3*a+k+1),-(3*b+k+1)});
    };
    for(auto [a,b]:edges)add_edge(a,b);
    if(impossible)add_edge(1,3); // A,B,C,D are now a 4-clique, 3 colors.
    return f;
}
static CNF sre1_circuit(bool impossible) {
    CNF f; f.vars=7;
    // A structural chain of aliases with explicit complement.
    // 1=2, 2=3, 4=NOT 3, 5=4, 6=NOT 5; 7 is output of AND(1,6).
    auto eq=[&](int a,int b){
        f.clauses.push_back({-a,b});f.clauses.push_back({a,-b});
    };
    auto inv=[&](int a,int b){
        f.clauses.push_back({a,b});f.clauses.push_back({-a,-b});
    };
    eq(1,2);eq(2,3);inv(3,4);eq(4,5);inv(5,6);
    // 7 iff (1 & 6), source-only exact Tseitin encoding.
    f.clauses.push_back({-7,1});
    f.clauses.push_back({-7,6});
    f.clauses.push_back({7,-1,-6});
    f.clauses.push_back({7});
    if(impossible)f.clauses.push_back({-1});
    return f;
}
static CNF sre1_parity(bool impossible) {
    CNF f;f.vars=7;
    auto add=[&](std::vector<int> vars,int rhs){
        for(unsigned bits=0;bits<(1u<<vars.size());++bits){
            if((__builtin_popcount(bits)&1)==rhs)continue;
            std::vector<int> c;
            for(size_t i=0;i<vars.size();++i)
                c.push_back((bits&(1u<<i))?-vars[i]:vars[i]);
            f.clauses.push_back(std::move(c));
        }
    };
    add({1,2,3},0);
    add({1,2,4},1); // XOR 3 XOR 4 == 1, a GF2-derived signed equality.
    add({4,5,6},0);
    add({4,5,7},1); // XOR 6 XOR 7 == 1.
    f.clauses.push_back({3});
    if(impossible)f.clauses.push_back({4});
    return f;
}
static void sre1_prove_case(const CNF& f, const char* family) {
    require(f.vars<=15,"SRE1 selftest brute-forcing too many variables");
    const bool truth=brute_sat(f);
    for(bool use_gf2:{false,true}){
        auto red=sre1_reduce(f,use_gf2);
        const bool reduced_truth=brute_sat(red.reduced);
        require(truth==reduced_truth,"SRE1 wrong SAT/UNSAT status in substitution");
        NativeCDCL solver(red.reduced.vars);
        solver.add_cnf(red.reduced);
        const int status=solver.solve(4.0);
        require(status==(truth?10:20),"SRE1 native reduced truth mismatch");
        if(truth){
            auto lifted=red.lift(solver.assignments());
            require((int)lifted.size()==f.vars+1,"SRE1 model lifting dimensions");
            for(const auto& c:f.clauses){
                bool sat=false;
                for(int lit:c)if((lit>0?lifted[std::abs(lit)]:
                    -lifted[std::abs(lit)])==1){sat=true;break;}
                require(sat,"SRE1 model reconstruction does not satisfy original CNF");
            }
        }
    }
    (void)family;
}
static void sre1_selftest() {
    // Compile-time one CPU external solver independence: all source is ours.
    const CNF radio=sre1_radio(false),no_radio=sre1_radio(true);
    require(radio.vars==15 && radio.clauses.size()==44,
            "SRE1 radio physical encoding changed");
    require(no_radio.clauses.size()==47,"SRE1 radio UNSAT encoding changed");
    sre1_prove_case(radio,"radio_sat");
    sre1_prove_case(no_radio,"radio_unsat");
    sre1_prove_case(sre1_circuit(false),"circuit_sat");
    sre1_prove_case(sre1_circuit(true),"circuit_unsat");
    sre1_prove_case(sre1_parity(false),"parity_sat");
    sre1_prove_case(sre1_parity(true),"parity_unsat");
    CNF aliases=sre1_circuit(false);
    auto a=sre1_reduce(aliases,false);
    require(a.equivalences>=3,"SRE1 failed to discover circuit equivalences");
    auto g=sre1_reduce(sre1_parity(false),true);
    require(g.gf2_pairs>=1,"SRE1 cross representation GF2 pair missing");
    CNF contradictory;contradictory.vars=2;
    contradictory.clauses={{-1,2},{-2,1},{1,2},{-1,-2}};
    require(sre1_reduce(contradictory,false).contradiction,
            "SRE1 implication SCC did not expose contradictory parity");
    std::mt19937 rng(0x511E2026u);
    int tested=0;
    for(int n=1;n<=9;++n)for(int i=0;i<55;++i){
        CNF f;f.vars=n;
        int clauses=(int)(rng()%(unsigned)(n*5+6));
        for(int j=0;j<clauses;++j){
            int width=(int)(rng()%(unsigned)(n+4));
            std::vector<int> c;
            for(int k=0;k<width;++k){
                const int v=1+(int)(rng()%(unsigned)n);
                c.push_back((rng()&1u)?v:-v);
            }
            f.clauses.push_back(std::move(c));
        }
        sre1_prove_case(f,"random");++tested;
    }
    std::cout<<"SRE1_SELFTEST_PASS random_originals="<<tested
             <<" three_real_world_families=3 paired_instances=6"
             <<" exhaustive_original_truth=true independent_model_lift=true"
             <<" cross_representation=true foreign_solver_calls=0\n";
}
static bool sre1_verify_original(const CNF& f,const std::vector<int8_t>& model) {
    require((int)model.size()==f.vars+1,"wrong model width");
    for(const auto&c:f.clauses){
        bool sat=false;
        for(int lit:c)if((lit>0?model[std::abs(lit)]:
                        -model[std::abs(lit)])==1){sat=true;break;}
        if(!sat)return false;
    }
    return true;
}
} // namespace drnas

#ifndef DRNAS_SRE2A_EMBED

int main(int argc,char** argv) {
    try{
        if(argc==2 && std::string(argv[1])=="--selftest"){
            drnas::sre1_selftest();
            return 0;
        }
        if(argc!=6 || std::string(argv[2])!="--mode" ||
                       std::string(argv[4])!="--time"){
            std::cerr<<"Usage: drnas-sre1 FORMULA.cnf --mode "
                        "plain|gf2|sre_graph|sre_all|sre_all_gf2|sre_placebo "
                        "--time SECONDS\n";
            return 2;
        }
        const std::string mode(argv[3]);
        drnas::require(mode=="plain"||mode=="gf2"||mode=="sre_graph"||
            mode=="sre_all"||mode=="sre_all_gf2"||mode=="sre_placebo",
            "unknown SRE1 mode");
        const double cap=std::stod(argv[5]);
        drnas::require(cap>0 && cap<=3600 && std::isfinite(cap),
                       "invalid E2E cap");
        const auto started=drnas::Clock::now();
        const auto input=drnas::read_dimacs(argv[1]);
        const bool do_sre=mode!="plain" && mode!="gf2";
        drnas::SRE1 mapping;
        mapping.original_vars=input.vars;
        if(do_sre)mapping=drnas::sre1_reduce(input,mode!="sre_graph");
        const bool apply=do_sre && mode!="sre_placebo";
        const drnas::CNF& work=apply?mapping.reduced:input;
        drnas::NativeCDCL solver(work.vars);
        solver.add_cnf(work);
        if(mode=="gf2"||mode=="sre_all_gf2")solver.enable_gf2_from_original(work);
        const double prep_s=std::chrono::duration<double>(
            drnas::Clock::now()-started).count();
        const double left=cap-prep_s;
        const int status=left>0?solver.solve(left):0;
        std::vector<int8_t> original_model;
        if(status==10){
            original_model=apply?mapping.lift(solver.assignments()):
                                 solver.assignments();
            drnas::require(drnas::sre1_verify_original(input,original_model),
                 "original CNF model lifting verification failed");
        }
        const double wall=std::chrono::duration<double>(
            drnas::Clock::now()-started).count();
        const auto& st=solver.statistics();
        std::cout<<std::fixed<<std::setprecision(6);
        std::cout<<"c DRNAS_SRE1_RESULT mode="<<mode
            <<" status="<<(status==10?"SAT":status==20?"UNSAT":"UNKNOWN")
            <<" e2e_s="<<wall<<" prep_s="<<prep_s
            <<" sre_reduce_s="<<mapping.preprocessing_s
            <<" solver_s="<<(left>0?solver.solve_elapsed_s():0)
            <<" original_vars="<<input.vars
            <<" original_clauses="<<input.clauses.size()
            <<" reduced_vars="<<work.vars
            <<" reduced_clauses="<<work.clauses.size()
            <<" sre_equivalences="<<mapping.equivalences
            <<" sre_opposites="<<mapping.opposite_equivalences
            <<" sre_units="<<mapping.root_units
            <<" sre_tautologies="<<mapping.tautologies
            <<" sre_gf2_pairs="<<mapping.gf2_pairs
            <<" sre_gf2_units="<<mapping.gf2_units
            <<" sre_graph_arcs="<<mapping.graph_arcs
            <<" sre_graph_scc="<<mapping.graph_scc
            <<" sre_budget_skipped="<<int(mapping.budget_skipped)
            <<" conflicts="<<st.conflicts<<" decisions="<<st.decisions
            <<" xor_implications="<<st.xor_implications
            <<" proof_original_SAT="<<int(status==10)
            <<" UNSAT_independent_LRAT=0"
            <<" third_party_solver_calls=0\n";
        if(status==10){
            std::cout<<"s SATISFIABLE\nv ";
            for(int v=1;v<=input.vars;++v){
                std::cout<<(original_model[v]<0?-v:v)<<" ";
                if(v%30==0)std::cout<<"0\nv ";
            }
            std::cout<<"0\n";
        } else if(status==20)std::cout<<"s UNSATISFIABLE\n";
        else std::cout<<"s UNKNOWN\n";
        return status==10?10:status==20?20:0;
    } catch(const std::exception& e){
        std::cerr<<"DRNAS_SRE1_FAIL_CLOSED "<<e.what()<<"\n";
        return 2;
    }
}

#endif // DRNAS_SRE2A_EMBED
