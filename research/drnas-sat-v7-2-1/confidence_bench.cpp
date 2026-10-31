// DRNAS Structural SAT v7.2: fast selective initial phase hints for ONE
// unmodified CaDiCaL 3.0.1 solver. No decomposition, changed clauses,
// assumptions, external propagators, or modification to CaDiCaL itself.
// Gate sees ONLY formula statistics; not the answer, timing or family label.
// Each benchmark method creates a fresh solver. Timed: allocation, loading
// the clauses into API, gate, hint construction, phase(), and solve().
#include "cadical.hpp"
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <numeric>
#include <random>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_set>
#include <vector>

using Clock=std::chrono::steady_clock;
using CNF=std::vector<std::vector<int>>;
struct Formula{CNF clauses;int vars=0;};
struct Item{std::string id,family,path;};
struct Hints{
    bool selected=false;
    int candidates=0;
    double density=0.0;
    double sample_3cnf_fraction=0.0;
    double pair_reuse=-1.0;
    double analysis_us=0.0;
    std::vector<int> literals;
};
struct Outcome{int status=0;Hints hint;};

static std::string trim(std::string s){
    while(!s.empty() && (s.back()=='\r' || s.back()=='\n' || s.back()==' '))s.pop_back();
    return s;
}
Formula read_cnf(const std::string &path){
    std::ifstream in(path);
    if(!in)throw std::runtime_error("Missing DIMACS "+path);
    Formula f;std::string line;std::vector<int> clause;
    int advertised_clauses=-1;
    while(std::getline(in,line)){
        if(line.empty() || line[0]=='c')continue;
        if(line[0]=='p'){
            std::istringstream s(line);std::string p,typ;
            s>>p>>typ>>f.vars>>advertised_clauses;
            if(typ!="cnf"||f.vars<0||advertised_clauses<0)
                throw std::runtime_error("Bad DIMACS header "+path);
        }else{
            std::istringstream s(line);int lit;
            while(s>>lit){
                if(lit==0){f.clauses.push_back(clause);clause.clear();}
                else {f.vars=std::max(f.vars,std::abs(lit));clause.push_back(lit);}
            }
        }
    }
    if(!clause.empty()||advertised_clauses!=(int)f.clauses.size())
        throw std::runtime_error("Incomplete DIMACS "+path);
    return f;
}
std::vector<Item> read_manifest(const std::string &path){
    std::ifstream in(path);
    if(!in)throw std::runtime_error("Missing manifest "+path);
    std::string line;std::getline(in,line);
    std::vector<Item> items;
    while(std::getline(in,line)){
        if(line.empty())continue;
        std::istringstream s(line);Item item;std::string unused;
        std::getline(s,item.id,',');
        std::getline(s,item.family,',');
        std::getline(s,item.path,',');
        item.path=trim(item.path);
        std::getline(s,unused,',');
        std::getline(s,unused,',');
        if(item.path.empty()||item.id.empty())throw std::runtime_error("Bad manifest line");
        items.push_back(item);
    }
    return items;
}
void fill_solver(CaDiCaL::Solver &solver,const Formula &f){
    for(const auto &clause:f.clauses){
        for(int l:clause)solver.add(l);
        solver.add(0);
    }
}
void check_sat_model(CaDiCaL::Solver &solver,const Formula &f){
    for(const auto &c:f.clauses){
        bool sat=false;
        for(int lit:c){
            if(solver.val(lit)==lit){sat=true;break;}
        }
        if(!sat)throw std::runtime_error("INVALID SAT MODEL: violated clause");
    }
}
// This cost gate was FIXED from V7.1 development data before the V7.2 pilot:
// O(1) for nvars + m/n, and O(<=64 clauses) to sample clause width.
// It does not use any expensive graph construction and is safe to skip.
Hints fast_gate(const Formula &f){
    const auto start=Clock::now();
    Hints h;
    if(f.vars==0){
        h.analysis_us=std::chrono::duration<double,std::micro>(Clock::now()-start).count();
        return h;
    }
    h.density=double(f.clauses.size())/f.vars;
    if(f.vars>=120 && h.density>=3.20 && h.density<=4.02){
        int checked=std::min<int>(64,f.clauses.size()),ternary=0;
        for(int i=0;i<checked;i++){
            // fixed-position evenly spaced sample, deterministic across hosts
            int idx=(int)((int64_t)i*f.clauses.size()/checked);
            if(f.clauses[idx].size()==3)ternary++;
        }
        h.sample_3cnf_fraction=checked?double(ternary)/checked:0.0;
        h.selected=(checked>0 && h.sample_3cnf_fraction>=0.90);
    }
    h.analysis_us=std::chrono::duration<double,std::micro>(Clock::now()-start).count();
    return h;
}

// V7.2.1 HIGH-CONFIDENCE GATE — fixed after retrospective V7.2 analysis.
// First stage is O(1) plus at most 64 clause lengths. Second stage scans
// up to 128 evenly spaced clauses, hashes unordered variable pairs.
// Pair-collision statistic is invariant to renaming of variables, but
// approximate sampling can be sensitive to clause ordering.
Hints confidence_gate(const Formula &f) {
    const auto start=Clock::now();
    Hints h;
    if(f.vars==0) return h;
    h.density=double(f.clauses.size())/f.vars;
    if(f.vars<120 || h.density<3.65 || h.density>4.10) {
        h.analysis_us=std::chrono::duration<double,std::micro>(Clock::now()-start).count();
        return h;
    }
    int checked=std::min<int>(64,f.clauses.size()),ternary=0;
    for(int i=0;i<checked;i++) {
        size_t idx=size_t(i)*f.clauses.size()/checked;
        if(f.clauses[idx].size()==3)ternary++;
    }
    h.sample_3cnf_fraction=checked?double(ternary)/checked:0.0;
    if(checked==0 || h.sample_3cnf_fraction<0.90) {
        h.analysis_us=std::chrono::duration<double,std::micro>(Clock::now()-start).count();
        return h;
    }
    const int samples=std::min<int>(128,f.clauses.size());
    std::unordered_set<uint64_t> edges;
    edges.reserve(512);
    int total=0;
    for(int i=0;i<samples;i++) {
        const auto &cl=f.clauses[size_t(i)*f.clauses.size()/samples];
        for(size_t a=0;a<cl.size();a++) {
            for(size_t b=a+1;b<cl.size();b++) {
                uint32_t x=std::abs(cl[a]),y=std::abs(cl[b]);
                if(x==y) continue;
                if(x>y) std::swap(x,y);
                uint64_t edge=(uint64_t(x)<<32)|y;
                edges.insert(edge);
                total++;
            }
        }
    }
    h.pair_reuse=total ? double(total-edges.size())/total : 1.0;
    h.selected=(h.pair_reuse<=0.030);
    h.analysis_us=std::chrono::duration<double,std::micro>(Clock::now()-start).count();
    return h;
}

void add_phase_hints(const Formula &f,Hints &h,bool random_sign,uint32_t seed){
    const auto start=Clock::now();
    std::vector<int> pos(f.vars+1,0),neg(f.vars+1,0);
    for(const auto &c:f.clauses)
        for(int lit:c)(lit>0?pos[lit]:neg[-lit])++;
    std::mt19937 rng(seed);
    for(int v=1;v<=f.vars;v++){
        int a=pos[v],b=neg[v];
        if(a+b>=6 && std::abs(a-b)>=0.15*(a+b) && a!=b){
            int sign=(random_sign ? ((rng() & 1)?1:-1) : (a>b?1:-1));
            h.literals.push_back(v*sign);
        }
    }
    h.candidates=h.literals.size();
    h.analysis_us+=std::chrono::duration<double,std::micro>(Clock::now()-start).count();
}
Outcome solve(const Formula &f,const std::string &method,uint32_t seed){
    CaDiCaL::Solver solver;
    fill_solver(solver,f);
    Hints h;
    if(method=="majority"){
        h.selected=true;
        h.density=f.vars?double(f.clauses.size())/f.vars:0;
        add_phase_hints(f,h,false,seed);
    }else if(method=="selective"||method=="gated_random"){
        h=fast_gate(f);
        if(h.selected)add_phase_hints(f,h,method=="gated_random",seed);
    }else if(method=="confidence"||method=="confidence_random"){
        h=confidence_gate(f);
        if(h.selected)add_phase_hints(f,h,method=="confidence_random",seed);
    }else if(method!="plain"){
        throw std::runtime_error("Unknown method "+method);
    }
    for(int lit:h.literals)solver.phase(lit);
    int code=solver.solve();
    if(code!=10 && code!=20)throw std::runtime_error("CaDiCaL returned UNKNOWN");
    if(code==10)check_sat_model(solver,f);
    return {code,std::move(h)};
}
int main(int argc,char **argv){
    try{
        if(argc<4){
            std::cerr<<"Usage: selective_bench manifest.csv output.csv reps [seed]\n";
            return 2;
        }
        auto items=read_manifest(argv[1]);
        std::ofstream output(argv[2]);
        if(!output)throw std::runtime_error("Cannot write CSV");
        int reps=std::stoi(argv[3]);
        if(reps<1 || reps>15)throw std::runtime_error("Repetition bounds 1..15");
        uint32_t seed=(argc>4)?(uint32_t)std::stoul(argv[4]):20261122u;
        const std::vector<std::string> methods={"plain","majority","selective","confidence","confidence_random"};
        output<<"case,family,method,rep,elapsed_us,answer,selected,hint_count,density,three_sample,pair_reuse,analysis_us,vars,clauses\n";
        output<<std::fixed<<std::setprecision(6);
        for(size_t idx=0;idx<items.size();idx++){
            const auto &item=items[idx];
            const auto f=read_cnf(item.path);
            int expected=0;
            for(int rep=0;rep<reps;rep++){
                auto order=methods;
                std::mt19937 rng(seed+idx*65537u+rep*997u);
                std::shuffle(order.begin(),order.end(),rng);
                for(const auto &method:order){
                    auto t0=Clock::now();
                    Outcome result=solve(f,method,seed+(uint32_t)idx*131u);
                    double us=std::chrono::duration<double,std::micro>(Clock::now()-t0).count();
                    if(expected==0)expected=result.status;
                    if(expected!=result.status)
                        throw std::runtime_error("SAT/UNSAT mismatch "+item.id+" "+method);
                    output<<item.id<<','<<item.family<<','<<method<<','<<rep<<','
                          <<us<<','<<(result.status==10?"SAT":"UNSAT")<<','
                          <<(result.hint.selected?1:0)<<','<<result.hint.candidates<<','
                          <<result.hint.density<<','<<result.hint.sample_3cnf_fraction<<','
                          <<result.hint.pair_reuse<<','<<result.hint.analysis_us<<','<<f.vars<<','<<f.clauses.size()<<"\n";
                }
            }
            output.flush();
            std::cerr<<"Verified "<<idx+1<<'/'<<items.size()<<' '<<item.id
                     <<' '<<(expected==10?"SAT":"UNSAT")<<"\n";
        }
        return 0;
    }catch(const std::exception &ex){
        std::cerr<<"FATAL: "<<ex.what()<<"\n";
        return 1;
    }
}
