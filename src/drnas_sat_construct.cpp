// DRNAS native SAT witness constructor, original CNF only.
// Exit 10: SAT with a fully verified v-model. Exit 0: UNKNOWN.
// Never declares UNSAT. One CPU/process, no portfolio.
#include "drnas_sat_construct.hpp"
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

int main(int argc,char**argv) {
  try {
    const auto begin=satconstruct::Clock::now();
    std::string path;bool stats=false;double budget_ms=25.0;
    for(int i=1;i<argc;++i){
      std::string opt=argv[i];
      if(opt=="--stats")stats=true;
      else if(opt=="--max-ms"&&i+1<argc)budget_ms=std::stod(argv[++i]);
      else if(opt=="--help") {
        std::cerr<<"usage: drnas-sat-construct FILE.cnf [--max-ms N] [--stats]\n";
        return 0;
      }else if(opt.rfind("-",0)==0)throw std::runtime_error("unknown option");
      else if(path.empty())path=opt;
      else throw std::runtime_error("multiple files");
    }
    if(path.empty()||!std::isfinite(budget_ms)||budget_ms<=0||budget_ms>1000)
      throw std::runtime_error("invalid input or budget");
    std::ifstream input(path);
    if(!input)throw std::runtime_error("cannot open CNF");
    std::string line;int n=-1,m=-1;int clauses_seen=0;
    satconstruct::CNF clauses;std::vector<int> clause;
    while(std::getline(input,line)){
      std::istringstream row(line);std::string first;
      if(!(row>>first)||first=="c"||first=="%")continue;
      if(first=="p"){
        std::string type;
        if(n>=0||!(row>>type>>n>>m)||type!="cnf"||n<0||m<0)
          throw std::runtime_error("invalid DIMACS header");
        if(n>20000000||m>10000000)throw std::runtime_error("input too large");
        clauses.reserve(std::min(150000,m));continue;
      }
      if(n<0)throw std::runtime_error("missing header");
      auto consume=[&](const std::string& token){
        size_t pos=0;long long literal=std::stoll(token,&pos);
        if(pos!=token.size()||literal>n||literal<-n)
          throw std::runtime_error("invalid literal");
        if(!literal){
          clauses.push_back(std::move(clause));clause.clear();++clauses_seen;
          if(clauses_seen>m)throw std::runtime_error("too many clauses");
        }else clause.push_back((int)literal);
      };
      consume(first);std::string token;while(row>>token)consume(token);
    }
    if(!input.eof()||n<0||clauses_seen!=m||!clause.empty())
      throw std::runtime_error("incomplete DIMACS");
    satconstruct::Limits limits;
    limits.max_ms=budget_ms;
    const auto ans=satconstruct::analyze(n,clauses,limits);
    if(ans.sat()){
      if(!satconstruct::verify(n,clauses,ans.model))
        throw std::runtime_error("invalid original-CNF SAT model");
      std::cout<<"s SATISFIABLE\n";
      for(int v=0;v<n;++v){
        if(v%20==0)std::cout<<"v ";
        std::cout<<(ans.model[v]>0?v+1:-(v+1))<<" ";
        if(v%20==19)std::cout<<"0\n";
      }
      if(n%20)std::cout<<"0\n";
      if(!n)std::cout<<"v 0\n";
    }else std::cout<<"s UNKNOWN\n";
    if(stats){
      double ms=std::chrono::duration<double,std::milli>(
           satconstruct::Clock::now()-begin).count();
      std::cerr<<"SAT_NATIVE_STATS {\"method\":\""<<ans.method
           <<"\",\"total_ms\":"<<ms
           <<",\"alo_groups\":"<<ans.alo_groups
           <<",\"resource_components\":"<<ans.resource_components
           <<",\"equations\":"<<ans.equations<<"}\n";
    }
    return ans.sat()?10:0;
  }catch(const std::exception& e){
    std::cerr<<"SAT_NATIVE_ERROR "<<e.what()<<"\n";
    return 2;
  }
}
