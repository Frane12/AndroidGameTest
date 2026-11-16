// DRNAS IPG5-B — native C++ experiment: source-bound PCMAX job-level
// 3-way structural branching, WITHOUT CDCL, SAT portfolio or preprocessing.
// Emits RUP ONLY after complete local source-RUP replay. External VeriPB
// and drat-trim acceptance remain mandatory (this executable does NOT
// self-certify a standard proof).
//
// Scope is deliberately the frozen 45-variable / 300-clause weighted
// Petersen source. It is a NON-GENERAL, worst-case EXPONENTIAL
// job-branching proof generator; never claim polynomial general PCMAX.
#include <algorithm>
#include <array>
#include <chrono>
#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <iterator>
#include <numeric>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>
#include <charconv>
#include <openssl/evp.h>

namespace {
using Clock=std::chrono::steady_clock;
constexpr char frozen_sha[]=
    "c2fefeffc1f9644ffd6f85728106a21c82dfc01d0d021f32d4d73569cc2bfb70";
constexpr int kVars=45;
constexpr int kJobs=15;
constexpr int kMachines=3;
constexpr uint64_t kMaxNodes=10000;
constexpr size_t kMaxProof=10000;

struct Clause {uint64_t positive=0,negative=0;};
inline uint64_t bit(int literal) {return 1ULL << static_cast<unsigned>(std::abs(literal)-1);}
std::string sha256(const std::string& text) {
    unsigned char digest[EVP_MAX_MD_SIZE];unsigned int n=0;
    if (EVP_Digest(text.data(),text.size(),digest,&n,EVP_sha256(),nullptr)!=1||n!=32)
        throw std::runtime_error("sha256 unavailable");
    const char* hex="0123456789abcdef";std::string result;
    for(unsigned i=0;i<n;++i){
        result.push_back(hex[digest[i]>>4]);
        result.push_back(hex[digest[i]&15]);
    }
    return result;
}
std::vector<std::vector<int>> parse(const std::string& bytes,int& nv) {
    std::istringstream fd(bytes);
    std::vector<std::vector<int>> clauses;
    std::vector<int> partial;
    nv=-1;int expected=-1;std::string line;
    while(std::getline(fd,line)) {
        auto s=line.find_first_not_of(" \t\r");
        if(s==std::string::npos||line[s]=='c')continue;
        std::istringstream row(line.substr(s));
        if(line[s]=='p') {
            std::string p,cnf,extra;
            if(nv>=0 || !(row>>p>>cnf>>nv>>expected) || p!="p" ||
                    cnf!="cnf" || nv<1 || expected<1 || row>>extra)
                throw std::runtime_error("invalid source header");
            continue;
        }
        if(nv<1)throw std::runtime_error("source clause before header");
        for(std::string word;row>>word;) {
            int val=0;
            auto cv=std::from_chars(word.data(),word.data()+word.size(),val);
            if(cv.ec!=std::errc{}||cv.ptr!=word.data()+word.size()||
                    std::abs(val)>nv)
                throw std::runtime_error("invalid literal");
            if(val)partial.push_back(val);
            else {
                clauses.emplace_back(std::move(partial));
                partial.clear();
                if(clauses.size()>static_cast<size_t>(expected))
                    throw std::runtime_error("too many clauses");
            }
        }
    }
    if(!partial.empty() || nv!=kVars || expected!=300 ||
            clauses.size()!=static_cast<size_t>(expected))
        throw std::runtime_error("not frozen original source structure");
    return clauses;
}
Clause make_masks(const std::vector<int>& c) {
    Clause out;
    for(int lit:c) {
        if(lit>0)out.positive|=bit(lit);
        else out.negative|=bit(lit);
    }
    return out;
}
std::vector<int> jobs_by_duration() {
    // Exact Petersen original job order: outer 5, spokes 5, inner 5.
    // These are HINTS for decision ordering only. Every RUP inference
    // is proven against the ORIGINAL source clauses.
    std::vector<std::array<int,2>> edges;
    for(int i=0;i<5;++i)edges.push_back({std::min(i,(i+1)%5),
                                          std::max(i,(i+1)%5)});
    for(int i=0;i<5;++i)edges.push_back({i,i+5});
    for(int i=0;i<5;++i)edges.push_back({i+5,5+(i+2)%5});
    std::array<int,10> powers{};
    powers[0]=1;
    for(int i=1;i<10;++i)powers[static_cast<size_t>(i)]=
                               powers[static_cast<size_t>(i-1)]*3;
    std::vector<int> jobs(kJobs);std::iota(jobs.begin(),jobs.end(),0);
    std::sort(jobs.begin(),jobs.end(),[&](int a,int b) {
        const auto& u=edges[static_cast<size_t>(a)];
        const auto& v=edges[static_cast<size_t>(b)];
        const int pa=powers[static_cast<size_t>(u[0])]+powers[static_cast<size_t>(u[1])];
        const int pb=powers[static_cast<size_t>(v[0])]+powers[static_cast<size_t>(v[1])];
        return pa!=pb?pa>pb:a<b;
    });
    return jobs;
}
class Generator {
    std::vector<Clause> base_;
    const std::vector<int> order_;
    Clock::time_point deadline_;
public:
    uint64_t nodes=0,leaves=0,branch_points=0,proof_checks=0;
    std::vector<std::vector<int>> proof;
    Generator(const std::vector<std::vector<int>>& clauses,double budget_s)
        :order_(jobs_by_duration()),
         deadline_(Clock::now()+
                   std::chrono::duration_cast<Clock::duration>(
                         std::chrono::duration<double>(budget_s))) {
        for(const auto& c:clauses)base_.push_back(make_masks(c));
    }
    static bool propagate(const std::vector<Clause>& clauses,
                          uint64_t& positive,uint64_t& negative) {
        if(positive&negative)return true;
        while(true) {
            uint64_t new_positive=0,new_negative=0;
            for(const auto& clause:clauses) {
                if((clause.positive&positive)||(clause.negative&negative))
                    continue;
                const uint64_t used=positive|negative;
                const uint64_t a=clause.positive&~used;
                const uint64_t b=clause.negative&~used;
                const uint64_t available=a|b;
                if(!available)return true;
                if((available&(available-1))==0) {
                    if(a)new_positive|=a;
                    else new_negative|=b;
                }
            }
            if((new_positive&(negative|new_negative)) ||
               (new_negative&positive))
                return true;
            if(!((new_positive|new_negative)&~(positive|negative)))
                return false;
            positive|=new_positive;
            negative|=new_negative;
        }
    }
    void append_negated_decisions(const std::vector<int>& decisions) {
        if(proof.size()>=kMaxProof)
            throw std::runtime_error("source proof step limit");
        std::vector<int> lemma;
        for(int x:decisions)lemma.push_back(-x);
        proof.push_back(std::move(lemma));
    }
    void search(uint64_t positive,uint64_t negative,std::vector<int>& path) {
        ++nodes;
        if(nodes>kMaxNodes || Clock::now()>deadline_)
            throw std::runtime_error("bounded structural DPLL exhausted");
        if(propagate(base_,positive,negative)) {
            ++leaves;
            append_negated_decisions(path);
            return;
        }
        int best_count=kMachines+1;
        std::array<int,kMachines> chosen{};
        for(int job:order_) {
            std::array<int,kMachines> candidates{};
            int n=0;
            bool already_scheduled=false;
            for(int m=0;m<kMachines;++m) {
                int x=kMachines*job+m+1;
                if(positive&bit(x))already_scheduled=true;
                if(!(negative&bit(x)))candidates[static_cast<size_t>(n++)]=x;
            }
            if(already_scheduled)continue;
            if(n<2)
                throw std::runtime_error("source one-hot UP expected before branching");
            if(n<best_count) {
                best_count=n;
                chosen=candidates;
            }
        }
        if(best_count==kMachines+1)
            throw std::runtime_error("satisfying model found: must not claim UNSAT");
        ++branch_points;
        for(int k=0;k<best_count;++k) {
            int decision=chosen[static_cast<size_t>(k)];
            path.push_back(decision);
            search(positive|bit(decision),negative,path);
            path.pop_back();
        }
        append_negated_decisions(path);
    }
    void verify() {
        auto clauses=base_;
        for(const auto& c:proof) {
            uint64_t truth=0,falsehood=0;
            for(int literal:c) {
                int negated=-literal;
                if(negated>0)truth|=bit(negated);
                else falsehood|=bit(negated);
            }
            if(!propagate(clauses,truth,falsehood))
                throw std::runtime_error("independent native source-RUP replay REJECTED");
            ++proof_checks;
            clauses.push_back(make_masks(c));
        }
        if(proof.empty() || !proof.back().empty())
            throw std::runtime_error("source proof does not end in contradiction");
    }
};

} // namespace

int main(int argc,char** argv) {
    if(argc!=4 || std::string(argv[2])!="--output") {
        std::cerr<<"usage: drnas-ipg5b-native source.cnf --output proof.rup\n";
        return 2;
    }
    try{
        if(std::string(argv[1])==std::string(argv[3]))
            throw std::runtime_error("output would overwrite source");
        std::ifstream in(argv[1],std::ios::binary);
        if(!in)throw std::runtime_error("cannot read source");
        std::string source((std::istreambuf_iterator<char>(in)),
                           std::istreambuf_iterator<char>());
        if(sha256(source)!=frozen_sha) {
            std::cout<<"IPG5B_NATIVE {\"status\":\"UNKNOWN\","
                       "\"reason\":\"unrecognized source SHA-256\"}\n";
            return 0;
        }
        int nv=0;
        auto clauses=parse(source,nv);
        auto begin=Clock::now();
        Generator generator(clauses,3.0);
        std::vector<int> path;
        generator.search(0,0,path);
        generator.verify();
        if(generator.proof.size()>5000)
            throw std::runtime_error("unexpected proof size gate");
        std::ofstream out(argv[3],std::ios::binary);
        if(!out)throw std::runtime_error("cannot create RUP proof");
        for(const auto& c:generator.proof) {
            for(int literal:c)out<<literal<<' ';
            out<<"0\n";
        }
        if(!out)throw std::runtime_error("proof write failed");
        out.close();
        const double elapsed=std::chrono::duration<double>(
            Clock::now()-begin).count();
        std::cout<<"IPG5B_NATIVE {\"status\":\"RUP_EMITTED_NEEDS_EXTERNAL_CHECK\","
                 <<"\"source_sha256\":\""<<frozen_sha<<"\","
                 <<"\"variables\":"<<nv<<",\"source_clauses\":"<<clauses.size()
                 <<",\"proof_steps\":"<<generator.proof.size()
                 <<",\"proof_replayed\":"<<generator.proof_checks
                 <<",\"decision_nodes\":"<<generator.nodes
                 <<",\"branch_points\":"<<generator.branch_points
                 <<",\"conflict_leaves\":"<<generator.leaves
                 <<",\"native_module_s\":"<<elapsed<<"}\n";
        return 0;
    }catch(const std::exception& e) {
        std::cerr<<"IPG5B_NATIVE_REJECT "<<e.what()<<"\n";
        return 1;
    }
}
