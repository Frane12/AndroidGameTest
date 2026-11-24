// DRNAS SCALE9 -- experimental native source-CNF Singleton Arc Consistency.
// No CDCL, no expected labels, no source-specific patterns, no standard proof
// acceptance claimed. A DRAT/RUP trace is EMITTED_UNCHECKED until externally
// accepted against the unchanged original DIMACS CNF.
#include <algorithm>
#include <chrono>
#include <cstdint>
#include <deque>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <limits>
#include <map>
#include <numeric>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

using Clock = std::chrono::steady_clock;

struct Error:std::runtime_error{using std::runtime_error::runtime_error;};
struct Input {
    int vars=0;
    std::vector<std::vector<int>> clauses;
};
Input read_dimacs(const std::string& path) {
    std::ifstream f(path);
    if(!f)throw Error("unable_to_open_cnf");
    Input in;int expected=-1;std::string line;std::vector<int> clause;
    while(std::getline(f,line)) {
        std::istringstream s(line);std::string first;
        if(!(s>>first))continue;
        if(first=="c")continue;
        if(first=="p") {
            std::string kind;
            if(expected>=0||!(s>>kind>>in.vars>>expected)||kind!="cnf"||in.vars<1||expected<0)
                throw Error("invalid_dimacs_header");
            if(in.vars>400000 || expected>2000000)throw Error("size_gate");
            continue;
        }
        if(expected<0)throw Error("missing_dimacs_header");
        std::istringstream lits(line);
        int x;
        while(lits>>x) {
            if(x==0) {
                in.clauses.push_back(std::move(clause));clause.clear();
                if(in.clauses.size()>size_t(expected))throw Error("too_many_clauses");
            } else {
                if(x==std::numeric_limits<int>::min()||std::abs(x)>in.vars)
                    throw Error("invalid_literal");
                clause.push_back(x);
            }
        }
        if(lits.fail()&&!lits.eof())throw Error("invalid_dimacs_token");
    }
    if(expected<0||!clause.empty()||in.clauses.size()!=size_t(expected))
        throw Error("invalid_clause_count");
    return in;
}
inline uint64_t edge_key(int a,int b){
    return (uint64_t(uint32_t(a))<<32)|uint32_t(b);
}
struct Arc {
    int u,v;
    std::vector<std::vector<uint64_t>> supports;
    std::vector<int> cached_support;
};
struct Graph {
    std::vector<std::vector<int>> groups;
    std::vector<Arc> arcs;
    std::vector<std::vector<int>> incoming;
    size_t pairs=0,nested_pairs=0, total_literals=0;
};
inline bool subset(const std::vector<uint64_t>&a,const std::vector<uint64_t>&b){
    for(size_t k=0;k<a.size();++k)if(a[k]&~b[k])return false;
    return true;
}
bool nested(const Arc&a) {
    const auto& S=a.supports;
    for(size_t i=0;i<S.size();++i)
      for(size_t j=i+1;j<S.size();++j)
        if(!subset(S[i],S[j])&&!subset(S[j],S[i]))return false;
    return true;
}
Graph extract(const Input &in) {
    Graph g;
    std::vector<int> owner(in.vars+1,-1),index(in.vars+1,-1);
    for(const auto&c:in.clauses) {
        if(c.size()<2 || !std::all_of(c.begin(),c.end(),[](int x){return x>0;}))continue;
        if(g.groups.size()>=256||c.size()>512)throw Error("source_domain_size_gate");
        int id=int(g.groups.size());
        for(size_t i=0;i<c.size();++i) {
            int v=c[i];
            if(owner[v]>=0)throw Error("overlapping_positive_source_domains");
            owner[v]=id;index[v]=int(i);
        }
        g.total_literals+=c.size();
        if(g.total_literals>8000)throw Error("selector_limit");
        g.groups.push_back(c);
    }
    if(g.groups.empty())throw Error("no_positive_source_domains");
    using Pair=std::pair<int,int>;
    std::map<Pair,std::vector<Pair>> banned;
    for(const auto&c:in.clauses) {
        if(c.size()!=2||c[0]>=0||c[1]>=0)continue;
        int a=-c[0],b=-c[1];
        int u=owner[a],v=owner[b];
        if(u<0||v<0||u==v)continue;
        int i=index[a],j=index[b];
        if(u>v){std::swap(u,v);std::swap(i,j);}
        banned[{u,v}].push_back({i,j});
    }
    g.incoming.resize(g.groups.size());
    for(auto &[uv,pairs]:banned) {
        int u=uv.first,v=uv.second;
        Arc ab{u,v},ba{v,u};
        size_t Wu=(g.groups[u].size()+63)/64;
        size_t Wv=(g.groups[v].size()+63)/64;
        ab.supports.assign(g.groups[u].size(),std::vector<uint64_t>(Wv,~uint64_t(0)));
        ba.supports.assign(g.groups[v].size(),std::vector<uint64_t>(Wu,~uint64_t(0)));
        const int ru=int(g.groups[u].size()%64),rv=int(g.groups[v].size()%64);
        if(rv)for(auto&row:ab.supports)row.back()&=(uint64_t(1)<<rv)-1;
        if(ru)for(auto&row:ba.supports)row.back()&=(uint64_t(1)<<ru)-1;
        for(auto [i,j]:pairs) {
            ab.supports[i][j/64]&=~(uint64_t(1)<<(j%64));
            ba.supports[j][i/64]&=~(uint64_t(1)<<(i%64));
        }
        ab.cached_support.assign(g.groups[u].size(),-1);
        ba.cached_support.assign(g.groups[v].size(),-1);
        if(nested(ab)&&nested(ba))++g.nested_pairs;
        int a_id=int(g.arcs.size()),b_id=a_id+1;
        g.arcs.push_back(std::move(ab));
        g.arcs.push_back(std::move(ba));
        g.incoming[v].push_back(a_id);
        g.incoming[u].push_back(b_id);
        ++g.pairs;
    }
    return g;
}
using Domains=std::vector<std::vector<uint64_t>>;
Domains full(const Graph&g) {
    Domains d;d.reserve(g.groups.size());
    for(const auto&grp:g.groups) {
        size_t n=grp.size(),words=(n+63)/64;
        d.emplace_back(words,~uint64_t(0));
        if(n%64)d.back().back()=(uint64_t(1)<<(n%64))-1;
    }
    return d;
}
inline bool has(const Domains&d,int group,int i) {
    return d[group][i/64]&(uint64_t(1)<<(i%64));
}
inline void erase(Domains&d,int group,int i) {
    d[group][i/64]&=~(uint64_t(1)<<(i%64));
}
inline bool empty(const Domains&d,int group) {
    return std::all_of(d[group].begin(),d[group].end(),[](uint64_t x){return x==0;});
}
int count(const Domains&d,int group){
    int k=0;for(uint64_t w:d[group])k+=__builtin_popcountll(w);return k;
}
template<class Fn>void each(const Domains&d,int u,Fn f) {
    for(size_t word=0;word<d[u].size();++word) {
        uint64_t bits=d[u][word];
        while(bits){
            int i=int(word*64+__builtin_ctzll(bits));
            f(i);bits&=bits-1;
        }
    }
}
struct Stats{
    int checks=0, removed=0;uint64_t cache_hits=0,cache_misses=0,arc_visits=0,lemmas=0;
};
using Proof=std::vector<std::vector<int>>;
struct Solver {
    Graph g;bool use_cache=true;
    Stats stats;Clock::time_point deadline;int cap;
    explicit Solver(Graph graph,double seconds,int cap_,bool cache=true):
        g(std::move(graph)),use_cache(cache),
        deadline(Clock::now()+std::chrono::duration_cast<Clock::duration>(std::chrono::duration<double>(seconds))),cap(cap_){}
    void check_time(){
        if(Clock::now()>deadline)throw Error("time_budget_exhausted");
    }
    // A support cache is safe to reuse across different temporary domains:
    // a cached value is accepted ONLY if it is still active in that domain.
    bool supported(Arc&a,int i,const Domains&d){
        if(use_cache) {
            int cached=a.cached_support[i];
            if(cached>=0 && has(d,a.v,cached)){++stats.cache_hits;return true;}
        }
        ++stats.cache_misses;
        const auto& m=a.supports[i];
        for(size_t w=0;w<m.size();++w){
            uint64_t ok=m[w]&d[a.v][w];
            if(ok){
                if(use_cache)a.cached_support[i]=int(w*64+__builtin_ctzll(ok));
                return true;
            }
        }
        if(use_cache)a.cached_support[i]=-1;
        return false;
    }
    bool propagate(Domains&d,Proof&proof,int pivot=-1,const std::vector<int>* initial=nullptr){
        std::deque<int> todo;
        std::vector<uint8_t>queued(g.arcs.size(),0);
        auto put=[&](int id){if(!queued[id]){queued[id]=1;todo.push_back(id);}};
        if(initial){for(int k:*initial)put(k);}
        else for(size_t k=0;k<g.arcs.size();++k)put(int(k));
        while(!todo.empty()){
            int id=todo.front();todo.pop_front();queued[id]=0;
            Arc& a=g.arcs[id];
            ++stats.arc_visits;
            if((stats.arc_visits&511)==0)check_time();
            std::vector<int> lost;
            each(d,a.u,[&](int i){if(!supported(a,i,d))lost.push_back(i);});
            if(lost.empty())continue;
            for(int i:lost){
                int literal=-g.groups[a.u][i];
                if(pivot>=0 && literal!=-pivot)
                    proof.push_back({-pivot,literal});
                else proof.push_back({literal});
                erase(d,a.u,i);
            }
            if(empty(d,a.u))return false;
            for(int in:g.incoming[a.u])if(g.arcs[in].u!=a.v)put(in);
        }
        return true;
    }
    Proof proof;
    bool run() {
        Domains d=full(g);
        if(!propagate(d,proof))return true;
        while(true){
            check_time();bool progress=false;
            std::vector<int> order(g.groups.size());
            std::iota(order.begin(),order.end(),0);
            std::sort(order.begin(),order.end(),[&](int u,int v){
                int a=count(d,u),b=count(d,v);
                return a!=b?a<b:u<v;
            });
            for(int u:order){
                std::vector<int> candidates;
                each(d,u,[&](int i){candidates.push_back(i);});
                for(int i:candidates){
                    if(!has(d,u,i))continue;
                    if(stats.checks>=cap)throw Error("singleton_budget_exhausted");
                    check_time();
                    ++stats.checks;
                    int p=g.groups[u][i];
                    Domains trial=d;
                    Proof temporary;
                    each(d,u,[&](int j){
                        if(i!=j) {erase(trial,u,j);temporary.push_back({-p,-g.groups[u][j]});}
                    });
                    std::vector<int> init=g.incoming[u];
                    if(!propagate(trial,temporary,p, &init)){
                        // Preserve all RUP trial lemmas before the RUP unit -p.
                        proof.insert(proof.end(),temporary.begin(),temporary.end());
                        proof.push_back({-p});
                        erase(d,u,i);++stats.removed;progress=true;
                        if(empty(d,u))return true;
                        std::vector<int> again=g.incoming[u];
                        for(size_t k=0;k<g.arcs.size();++k)
                            if(g.arcs[k].u==u)again.push_back(int(k));
                        if(!propagate(d,proof,-1,&again))return true;
                    }
                }
            }
            if(!progress)break;
        }
        return false;
    }
};

int main(int argc,char**argv){
    std::string cnf,drat,report;double seconds=20;
    int cap=6000;bool cache=true;
    for(int i=1;i<argc;++i){
        std::string a=argv[i];
        if(a=="--cnf"&&i+1<argc)cnf=argv[++i];
        else if(a=="--drat"&&i+1<argc)drat=argv[++i];
        else if(a=="--report"&&i+1<argc)report=argv[++i];
        else if(a=="--seconds"&&i+1<argc)seconds=std::stod(argv[++i]);
        else if(a=="--cap"&&i+1<argc)cap=std::stoi(argv[++i]);
        else if(a=="--no-cache")cache=false;
        else if(a=="--help"){
            std::cout<<"Usage: drnas-sac9 --cnf file.cnf [--drat new.drat] [--report new.json] [--seconds N] [--cap N] [--no-cache]\n";
            return 0;
        } else {std::cerr<<"Unknown option "<<a<<"\n";return 2;}
    }
    if(cnf.empty()||!std::isfinite(seconds)||seconds<=0||seconds>3600||cap<1||cap>1000000){
        std::cerr<<"Invalid arguments\n";return 2;
    }
    auto start=Clock::now();std::string status="UNKNOWN",reason="no_contradiction";
    Stats st;size_t groups=0,links=0,nested_pairs=0,vars=0,clauses=0,lemmas=0;
    try{
        Input in=read_dimacs(cnf);vars=in.vars;clauses=in.clauses.size();
        Graph graph=extract(in);groups=graph.groups.size();links=graph.pairs;nested_pairs=graph.nested_pairs;
        Solver solver(std::move(graph),seconds,cap,cache);
        bool conflict=solver.run();
        st=solver.stats;lemmas=solver.proof.size();
        if(conflict){
            status="EMITTED_UNCHECKED";reason="structural_conflict";
            if(drat.empty())throw Error("proof_path_required");
            if(std::filesystem::exists(drat))throw Error("proof_path_exists");
            std::ofstream out(drat,std::ios::out|std::ios::trunc);
            if(!out)throw Error("proof_open_failed");
            for(const auto &cl:solver.proof){
                for(int lit:cl)out<<lit<<" ";
                out<<"0\n";
            }
            out<<"0\n";out.flush();
            if(!out)throw Error("proof_write_failed");
        }
    }catch(const std::exception&e){status="UNKNOWN";reason=e.what();}
    double elapsed=std::chrono::duration<double>(Clock::now()-start).count();
    std::ostringstream result;
    result<<"{\"status\":\""<<status<<"\",\"reason\":\""<<reason
          <<"\",\"vars\":"<<vars<<",\"clauses\":"<<clauses
          <<",\"groups\":"<<groups<<",\"cross_links\":"<<links
          <<",\"nested_support_pairs\":"<<nested_pairs
          <<",\"checks\":"<<st.checks<<",\"singleton_eliminations\":"<<st.removed
          <<",\"cache_hits\":"<<st.cache_hits<<",\"cache_misses\":"<<st.cache_misses
          <<",\"arc_visits\":"<<st.arc_visits<<",\"lemmas\":"<<lemmas
          <<",\"elapsed_s\":"<<elapsed<<"}\n";
    std::cout<<"SAC9_RESULT "<<result.str();
    if(!report.empty() && !std::filesystem::exists(report)) {
        std::ofstream out(report);out<<result.str();
    }
    return 0;
}
