// DRNAS SAT R28: exact AND-output ↔ full 3-XOR-block phase intervention.
//
// CAUSAL ABLATION, not a proof of better general SAT complexity:
//  - same unmodified CaDiCaL 3.0.1, identical CNF and 256-conflict checkpoint
//  - gate_shadow computes the identical full topology and applies no hints
//  - gate_zero applies phase(-g) for up to 512 confirmed AND-output XOR variables
//  - gate_one applies phase(+g); gate_random randomizes those same outputs
//  - all methods CONTINUE the same solver instance and learned clauses
//  - no original CNF clauses are added, dropped or modified
//  - original SAT assignments checked against EVERY original clause
//
// R27c verified all four-clause AND gates by independent 16-case truth tables.
// R28 independently re-detects exact gates via 3 binary and 1 four-literal
// clauses, then requires participation in a COMPLETE 3-XOR CNF parity block.
// This reads no filename, expected status, prior benchmark times or answers.
#define main drnas_r28_base_unused_main
#include "../..//research/drnas-sat-v7-2-1/confidence_bench.cpp"
#undef main
#include <array>
#include <unordered_map>
#include <unordered_set>
#include <tuple>

using std::array;
using std::uint64_t;
using std::unordered_map;
using std::unordered_set;

struct R28TripleHash {
    size_t operator()(const array<int,3> &s) const noexcept {
        uint64_t v = 1469598103934665603ull;
        for(int x:s) { v ^= uint64_t(uint32_t(x)); v*=1099511628211ull; }
        return size_t(v);
    }
};
static uint64_t r28_pair(int a,int b) {
    if(a>b)std::swap(a,b);
    return (uint64_t(uint32_t(a))<<32)|uint32_t(b);
}
struct R28Graph {
    int exact_xor3_blocks=0;
    int exact_and3_gates=0;
    int joined_outputs=0;
    int chosen=0;
    int max_xor_degree=0;
    int candidate_quaternary=0;
    std::vector<int> targets;
    double extraction_us=0;
};
static R28Graph r28_extract(const Formula &f) {
    const auto t0=Clock::now();
    R28Graph out;
    unordered_map<array<int,3>,uint8_t,R28TripleHash> masks;
    masks.reserve(std::min<size_t>(f.clauses.size()/4,100000));
    unordered_set<uint64_t> binary;
    binary.reserve(std::min<size_t>(f.clauses.size(),200000));
    for(const auto &cl:f.clauses) {
        if(cl.size()==2 && abs(cl[0])!=abs(cl[1]))
            binary.insert(r28_pair(cl[0],cl[1]));
        if(cl.size()!=3)continue;
        array<int,3> sort_lits={cl[0],cl[1],cl[2]};
        std::sort(sort_lits.begin(),sort_lits.end(),[](int a,int b){
            return abs(a)<abs(b);
        });
        array<int,3> support;
        int mask=0;
        bool valid=true;
        for(int j=0;j<3;j++) {
            support[j]=abs(sort_lits[j]);
            if(sort_lits[j]<0)mask|=1<<j;
            if(j>0 && support[j]==support[j-1])valid=false;
        }
        if(valid)masks[support]|=uint8_t(1u<<mask);
    }
    std::vector<int> xor_degree(size_t(f.vars)+1,0);
    for(const auto &m:masks) {
        // Parity classes: even-negation masks 0,3,5,6 (0x69);
        // odd-negation masks 1,2,4,7 (0x96).
        if(m.second==0x69 || m.second==0x96) {
            out.exact_xor3_blocks++;
            for(int v:m.first)xor_degree[v]++;
        }
    }
    unordered_set<int> gates;
    gates.reserve(std::min<size_t>(f.clauses.size()/8,100000));
    for(const auto &cl:f.clauses) {
        if(cl.size()!=4)continue;
        out.candidate_quaternary++;
        for(int candidate:cl) {
            if(candidate<=0)continue;
            const int gate=candidate;
            bool valid=true;
            unordered_set<int> others;
            for(int other:cl) {
                if(other==candidate)continue;
                if(abs(other)==gate || !others.insert(abs(other)).second ||
                   binary.count(r28_pair(-gate,-other))==0) {
                    valid=false;break;
                }
            }
            if(valid && others.size()==3)gates.insert(gate);
        }
    }
    out.exact_and3_gates=int(gates.size());
    std::vector<std::pair<int,int>> candidates;
    candidates.reserve(gates.size());
    for(int g:gates) if(xor_degree[g]>0) {
        out.joined_outputs++;
        candidates.emplace_back(xor_degree[g],g);
        out.max_xor_degree=std::max(out.max_xor_degree,xor_degree[g]);
    }
    // Prioritize AND outputs occurring in more confirmed XOR equations.
    // Stable numeric tie break. At most 512 hints to bound phase overhead.
    std::sort(candidates.begin(),candidates.end(),[](auto a,auto b){
        if(a.first!=b.first)return a.first>b.first;
        return a.second<b.second;
    });
    for(size_t i=0;i<candidates.size() && i<512;i++)
        out.targets.push_back(candidates[i].second);
    out.chosen=int(out.targets.size());
    out.extraction_us=std::chrono::duration<double,std::micro>(
        Clock::now()-t0).count();
    return out;
}
int main(int argc,char **argv) {
    try {
        if(argc!=4 && !(argc==5 && std::string(argv[4])=="--classify-only")) {
            std::cerr<<"Usage: r28 MODE ORIGINAL_CNF SEED [--classify-only]\n";
            return 2;
        }
        const std::string mode=argv[1];
        if(mode!="gate_shadow" && mode!="gate_zero" &&
           mode!="gate_one" && mode!="gate_random")
            throw std::runtime_error("Invalid R28 mode");
        const auto whole=Clock::now();
        const Formula f=read_cnf(argv[2]);
        const uint32_t seed=static_cast<uint32_t>(std::stoul(argv[3]));
        const R28Graph graph=r28_extract(f);
        if(argc==5) {
            std::cout<<"DRNAS_R28_CLASSIFY\t"<<graph.exact_xor3_blocks
                     <<"\t"<<graph.exact_and3_gates
                     <<"\t"<<graph.joined_outputs
                     <<"\t"<<graph.chosen
                     <<"\t"<<graph.extraction_us<<"\n";
            return 0;
        }
        CaDiCaL::Solver solver;
        fill_solver(solver,f);
        std::mt19937 rng(seed);
        int hint_count=0;
        if(mode!="gate_shadow") {
            for(int gate:graph.targets) {
                int sign=(mode=="gate_zero")?-1:(mode=="gate_one")?1:
                         ((rng()&1)?1:-1);
                solver.phase(sign*gate);
                ++hint_count;
            }
        }
        const int64_t redundant_before=solver.redundant();
        const int active_before=solver.active();
        if(!solver.limit("conflicts",256))
            throw std::runtime_error("CaDiCaL refused 256 conflict limit");
        const auto first_time=Clock::now();
        const int first=solver.solve();
        const double first_us=std::chrono::duration<double,std::micro>(
            Clock::now()-first_time).count();
        const int64_t learnt=std::max<int64_t>(0,solver.redundant()-redundant_before);
        const int active_after=solver.active();
        const auto second_time=Clock::now();
        int status=first;
        if(status==0)status=solver.solve(); // SAME solver, no restart.
        const double resume_us=std::chrono::duration<double,std::micro>(
            Clock::now()-second_time).count();
        if(status!=10 && status!=20)throw std::runtime_error("UNKNOWN final status");
        if(status==10)check_sat_model(solver,f);
        const double wall_us=std::chrono::duration<double,std::micro>(
            Clock::now()-whole).count();
        std::cout<<std::fixed<<std::setprecision(6)
             <<"DRNAS_R28_RESULT\t"<<mode<<"\t"<<(status==10?"SAT":"UNSAT")
             <<"\t"<<graph.exact_xor3_blocks
             <<"\t"<<graph.exact_and3_gates
             <<"\t"<<graph.joined_outputs
             <<"\t"<<graph.chosen
             <<"\t"<<hint_count
             <<"\t"<<graph.max_xor_degree
             <<"\t"<<first
             <<"\t"<<learnt
             <<"\t"<<active_before
             <<"\t"<<active_after
             <<"\t"<<graph.extraction_us
             <<"\t"<<first_us
             <<"\t"<<resume_us
             <<"\t"<<wall_us
             <<"\n";
        return 0;
    }catch(const std::exception &ex){
        std::cerr<<"DRNAS_R28_ERROR: "<<ex.what()<<"\n";
        return 3;
    }
}
