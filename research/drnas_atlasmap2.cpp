// DRNAS ATLAS-MAP2: source-certified, live CDCL parity-relation shortcuts.
// Native R3C engine; optional MAP1 preprocessing; no external SAT solver.
#define DRNAS_ATLASMAP2
#define DRNAS_ATLASMAP1_AS_LIBRARY
#include "drnas_atlasmap1.cpp"
#undef DRNAS_ATLASMAP1_AS_LIBRARY
#undef DRNAS_ATLASMAP2

namespace atlasmap2 {
using drnas::CNF;
using drnas::Clock;

static double elapsed(Clock::time_point start) {
    return std::chrono::duration<double>(Clock::now()-start).count();
}
static bool is_true(const CNF& f, unsigned mask) {
    for(const auto& clause:f.clauses) {
        bool good=false;
        for(int lit:clause)
            if(bool(mask&(1u<<(std::abs(lit)-1)))==(lit>0)) {
                good=true;break;
            }
        if(!good)return false;
    }
    return true;
}
// All parity relations below have *complete* CNF encodings in ORIGINAL input.
// x XOR y = rhs is encoded as:
//  rhs 0: (-x OR y) AND (x OR -y)
//  rhs 1: (x OR y) AND (-x OR -y)
static void add_pair(CNF& f,int x,int y,int rhs) {
    if(rhs==0) {
        f.clauses.push_back({-x,y});
        f.clauses.push_back({x,-y});
    } else {
        f.clauses.push_back({x,y});
        f.clauses.push_back({-x,-y});
    }
}
static void test_one(const CNF& f,unsigned& solves,unsigned& verified) {
    const bool expected=drnas::brute_sat(f);
    for(int mode=0;mode<3;++mode) {
        drnas::NativeCDCL s(f.vars);
        s.add_cnf(f);
        if(mode!=0)s.enable_atlasmap2_from_original(f,mode==2);
        const int result=s.solve(3.0);
        drnas::require(result==(expected?10:20),
            "ATLASMAP2 brute force status mismatch");
        if(result==10) {
            drnas::require(s.verify_original(f),
                "ATLASMAP2 native SAT assignment invalid on ORIGINAL CNF");
            ++verified;
        }
        ++solves;
    }
}
static int selftest() {
    CNF positive;positive.vars=6;
    add_pair(positive,1,2,1);
    add_pair(positive,2,3,0);
    positive.clauses.push_back({1});
    drnas::NativeCDCL live(positive.vars),shadow(positive.vars);
    live.add_cnf(positive);
    shadow.add_cnf(positive);
    live.enable_atlasmap2_from_original(positive,false);
    shadow.enable_atlasmap2_from_original(positive,true);
    drnas::require(live.solve(3.0)==10 && shadow.solve(3.0)==10,
        "ATLASMAP2 synthetic SAT control failed");
    drnas::require(live.verify_original(positive) && shadow.verify_original(positive),
        "ATLASMAP2 original SAT witness failed");
    const auto& a=live.statistics();
    const auto& b=shadow.statistics();
    drnas::require(a.map2_source_pairs>=2 && a.map2_groups==1,
        "ATLASMAP2 group from transitive source parity missing");
    drnas::require(a.map2_implications>=2 && a.map2_reasons>=2,
        "ATLASMAP2 did not deliver actual causal CDCL reasons");
    drnas::require(b.map2_shadow_opportunities>=2 && b.map2_implications==0,
        "ATLASMAP2 shadow must observe without intervening");
    CNF incomplete;incomplete.vars=3;
    incomplete.clauses={{1,2},{-2,3},{1}};
    drnas::NativeCDCL rejected(3);
    rejected.add_cnf(incomplete);
    rejected.enable_atlasmap2_from_original(incomplete,false);
    drnas::require(rejected.statistics().map2_groups==0,
        "ATLASMAP2 accepted a single binary clause as parity equivalence");
    CNF inconsistent;inconsistent.vars=3;
    add_pair(inconsistent,1,2,0);
    add_pair(inconsistent,2,3,0);
    add_pair(inconsistent,1,3,1);
    drnas::NativeCDCL cycle(3);
    cycle.add_cnf(inconsistent);
    cycle.enable_atlasmap2_from_original(inconsistent,false);
    drnas::require(cycle.statistics().map2_groups==0 && cycle.solve(3.0)==20,
        "ATLASMAP2 contradictory source parity cycle must safely abstain");
    std::mt19937 rng(20261111u);
    unsigned trials=0, verified=0;
    for(int sample=0;sample<240;++sample) {
        CNF f;f.vars=6;
        // Certified two-edge relation graph, plus mixed unrelated clauses.
        const int first=int(rng()&1u),second=int(rng()&1u);
        add_pair(f,1,2,first);
        add_pair(f,2,3,second);
        if(sample%3==0)f.clauses.push_back({1});
        for(int i=0;i<12;++i) {
            std::vector<int> clause;
            const int width=1+int(rng()%3);
            for(int j=0;j<width;++j) {
                int v=1+int(rng()%6);
                clause.push_back((rng()&1u)?v:-v);
            }
            f.clauses.push_back(std::move(clause));
        }
        test_one(f,trials,verified);
    }
    std::cout<<"ATLASMAP2_SELFTEST_PASS randomized_cases=240"
             <<" independent_oracle_attempts="<<trials
             <<" verified_SAT="<<verified
             <<" live_source_pairs="<<a.map2_source_pairs
             <<" live_groups="<<a.map2_groups
             <<" live_implications="<<a.map2_implications
             <<" live_completed_reasons="<<a.map2_reasons
             <<" shadow_opportunities="<<b.map2_shadow_opportunities
             <<" incomplete_pair_rejected=1 contradictory_cycle_fallback=1"
             <<" original_UNSAT_LRAT=0\n";
    return 0;
}
} // namespace atlasmap2

int main(int argc,char** argv) {
    try {
        if(argc==2 && std::string(argv[1])=="--atlasmap2-selftest")
            return atlasmap2::selftest();
        if(argc!=6 || std::string(argv[2])!="--mode" ||
           std::string(argv[4])!="--time") {
            std::cerr<<"usage: atlasmap2 FILE --mode "
                     <<"A|ATLASX|MAP1|MAP2_LIVE|MAP2_SHADOW|MAP2_COMBO|GF2_SELECTIVE "
                     <<"--time SECONDS\n";
            return 2;
        }
        const std::string mode=argv[3];
        const bool live=mode=="MAP2_LIVE" || mode=="MAP2_COMBO";
        const bool shadow=mode=="MAP2_SHADOW";
        const bool gf2_selective=mode=="GF2_SELECTIVE";
        drnas::require(mode=="A"||mode=="ATLASX"||mode=="MAP1"||
                       live||shadow||gf2_selective,"ATLASMAP2 invalid mode");
        const double cap=std::stod(argv[5]);
        drnas::require(std::isfinite(cap)&&cap>0&&cap<=3600,
                       "ATLASMAP2 invalid cap");
        const auto start=drnas::Clock::now();
        const auto original=drnas::read_dimacs(argv[1]);
        atlasmap::Metrics prep;
        auto working=original;
        if(mode=="ATLASX"||mode=="MAP1"||mode=="MAP2_COMBO")
            working=atlasmap::prepare(original,prep,
                       mode=="ATLASX"?"ATLASX":"MAP1",cap,{});
        else {
            prep.kind="baseline_original_cnf";
            prep.reason="no_preprocessing";
        }
        drnas::NativeCDCL solver(working.vars);
        solver.add_cnf(working);
        const auto map_start=drnas::Clock::now();
        if(live||shadow)solver.enable_atlasmap2_from_original(original,shadow);
        size_t gf2_source_rows=0;
        bool gf2_gate=false;
        if(gf2_selective && original.clauses.size()<=25000 && original.vars<=20000) {
            const auto exact=drnas::extract_source_xors(original);
            gf2_source_rows=exact.size();
            gf2_gate=gf2_source_rows>=2 &&
                double(gf2_source_rows)/double(std::max<size_t>(1,original.clauses.size()))>=0.002;
            if(gf2_gate)solver.enable_gf2_from_original(original);
        }
        const double map_init_s=atlasmap2::elapsed(map_start);
        const double before=atlasmap2::elapsed(start);
        const int status=(before<cap)?solver.solve(cap-before):0;
        std::vector<int8_t> model;
        if(status==10) {
            model=atlasmap::reconstruct(solver,prep,original);
            drnas::require(atlasmap::verify_original(original,model),
                           "ATLASMAP2 original SAT witness invalid");
        }
        const auto& s=solver.statistics();
        const double e2e=atlasmap2::elapsed(start);
        std::cout<<std::fixed<<std::setprecision(8)
            <<"ATLASMAP2_TRIAL arm="<<mode
            <<" status="<<(status==10?"SAT":status==20?"UNSAT":"UNKNOWN")
            <<" E2E_s="<<e2e
            <<" preprocess_s="<<prep.preprocess_s
            <<" map_init_s="<<map_init_s
            <<" original_clauses="<<original.clauses.size()
            <<" working_clauses="<<working.clauses.size()
            <<" prep_kind="<<prep.kind
            <<" prep_saved_literals="<<prep.saved_literals
            <<" gf2_gate="<<int(gf2_gate)
            <<" gf2_screen_rows="<<gf2_source_rows
            <<" gf2_active_rows="<<s.xor_source_rows
            <<" gf2_derived_rows="<<s.xor_derived_rows
            <<" gf2_implications="<<s.xor_implications
            <<" gf2_reasons="<<s.xor_reasons
            <<" gf2_conflicts="<<s.xor_conflicts
            <<" gf2_checks="<<s.xor_checks
            <<" map2_source_pairs="<<s.map2_source_pairs
            <<" map2_groups="<<s.map2_groups
            <<" map2_group_variables="<<s.map2_group_variables
            <<" map2_events="<<s.map2_events
            <<" map2_checks="<<s.map2_checks
            <<" map2_proposals="<<s.map2_proposals
            <<" map2_implications="<<s.map2_implications
            <<" map2_reasons="<<s.map2_reasons
            <<" map2_conflicts="<<s.map2_conflicts
            <<" map2_shadow_opportunities="<<s.map2_shadow_opportunities
            <<" map2_budget_off="<<s.map2_budget_off
            <<" map2_restarts="<<s.map2_restarts
            <<" conflicts="<<s.conflicts
            <<" decisions="<<s.decisions
            <<" propagations="<<s.propagations
            <<" watch_visits="<<s.watch_visits
            <<" learned="<<s.learned_clauses
            <<" SAT_original_verified="<<int(status==10)
            <<" UNSAT_independent_LRAT=0 oneCPU=1\n";
        if(status==10) {
            std::cout<<"s SATISFIABLE\nv ";
            for(int v=1;v<=original.vars;++v)
                std::cout<<(model[size_t(v)]<0?-v:v)<<" ";
            std::cout<<"0\n";
        } else std::cout<<(status==20?"s UNSATISFIABLE\n":"s UNKNOWN\n");
        return status==10?10:status==20?20:0;
    } catch(const std::exception& e) {
        std::cerr<<"ATLASMAP2_ERROR "<<e.what()<<"\n";return 2;
    }
}
