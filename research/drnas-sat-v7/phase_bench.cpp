// DRNAS-SAT v7.1: structural decision phase hints to one unmodified CaDiCaL.
// Official CaDiCaL v3.0.1 C++ API. No changes to CNF, no assumptions or
// external propagator. Each solver instance is fresh. Timings include
// per-method phase computation, graph analysis, CaDiCaL construction and solve.
#include "cadical.hpp"
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <numeric>
#include <queue>
#include <random>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_set>
#include <utility>
#include <vector>
using CNF=std::vector<std::vector<int>>;
using Clock=std::chrono::steady_clock;
struct CNFData{ CNF clauses; int vars=0; };
struct Item{std::string id,family,path,group;};
struct Hints{
 std::vector<int> lit;
 int hubs=0,components=0,candidates=0;
 double analysis_us=0;
 bool structurally_separable=false;
};
struct Result{
 int status=0, hints=0,hubs=0,components=0;
 double analysis_us=0;
 bool modular=false;
};
CNFData load_cnf(const std::string &path){
 std::ifstream in(path);
 if(!in)throw std::runtime_error("Cannot read DIMACS: "+path);
 CNFData f; std::vector<int> c; std::string line;
 while(std::getline(in,line)){
  if(line.empty()||line[0]=='c')continue;
  if(line[0]=='p'){
   std::istringstream ss(line);std::string p,typ;int nc;
   ss>>p>>typ>>f.vars>>nc;
   if(typ!="cnf"||f.vars<0)throw std::runtime_error("Invalid DIMACS header");
   continue;
  }
  std::istringstream ss(line);int lit;
  while(ss>>lit){
   if(!lit){f.clauses.push_back(c);c.clear();}
   else {f.vars=std::max(f.vars,std::abs(lit));c.push_back(lit);}
  }
 }
 if(!c.empty())throw std::runtime_error("Unterminated clause");
 return f;
}
std::vector<Item> read_manifest(const std::string &path){
 std::ifstream in(path);
 if(!in)throw std::runtime_error("Cannot read manifest");
 std::string line; std::getline(in,line);std::vector<Item> items;
 while(std::getline(in,line)){
  if(line.empty())continue;
  std::istringstream ss(line);Item it;std::string trash;
  std::getline(ss,it.id,',');std::getline(ss,it.family,',');
  std::getline(ss,it.path,',');
  std::getline(ss,trash,',');std::getline(ss,trash,',');
  std::getline(ss,it.group,',');
  if(it.id.empty()||it.path.empty())throw std::runtime_error("Bad manifest row");
  items.push_back(std::move(it));
 }
 return items;
}
void fill(CaDiCaL::Solver &solver,const CNFData &f){
 for(const auto &c:f.clauses){
  for(int lit:c)solver.add(lit);
  solver.add(0);
 }
}
void assert_sat_model(CaDiCaL::Solver &solver,const CNFData &f){
 for(const auto &c:f.clauses){
  bool satisfied=false;
  for(int lit:c){
   if(solver.val(lit)==lit){satisfied=true;break;}
  }
  if(!satisfied)throw std::runtime_error("CaDiCaL returned invalid SAT model");
 }
}
bool eligible(double pos,double neg,int min_occ,double margin){
 const double total=pos+neg;
 return total>=min_occ && std::abs(pos-neg)>=margin*total && std::abs(pos-neg)>1e-12;
}
Hints majority(const CNFData &f){
 auto t0=Clock::now();
 std::vector<double> pos(f.vars+1,0),neg(f.vars+1,0);
 for(const auto &c:f.clauses)
  for(int lit:c){(lit>0?pos[lit]:neg[-lit])+=1.0;}
 Hints h;
 for(int v=1;v<=f.vars;v++){
  if(eligible(pos[v],neg[v],6,0.15)){
   h.lit.push_back(pos[v]>neg[v]?v:-v);
  }
 }
 h.candidates=h.lit.size();
 h.analysis_us=std::chrono::duration<double,std::micro>(Clock::now()-t0).count();
 return h;
}
Hints structure(const CNFData &f){
 const auto t0=Clock::now();
 Hints hints;
 const int n=f.vars;
 std::vector<std::unordered_set<int>> g(n+1);
 std::vector<int> occ(n+1,0);
 for(const auto &clause:f.clauses){
  for(int lit:clause)occ[std::abs(lit)]++;
  for(size_t i=0;i<clause.size();i++)
   for(size_t j=i+1;j<clause.size();j++){
    int a=std::abs(clause[i]),b=std::abs(clause[j]);
    if(a!=b){g[a].insert(b);g[b].insert(a);}
   }
 }
 std::vector<int> active;
 double degree_total=0;
 for(int v=1;v<=n;v++){
  if(occ[v]){active.push_back(v);degree_total+=g[v].size();}
 }
 double avg=degree_total/std::max(size_t(1),active.size());
 std::sort(active.begin(),active.end(),[&](int a,int b){
  if(g[a].size()!=g[b].size())return g[a].size()>g[b].size();
  return a<b;
 });
 std::vector<char> is_hub(n+1,0);
 std::vector<int> hubs;
 for(int v:active){
  if(hubs.size()==2)break;
  if(g[v].size()>=12 && g[v].size()>2.2*avg){
   hubs.push_back(v);is_hub[v]=1;
  }
 }
 std::vector<int> owner(n+1,-1),part_sizes;
 for(int v:active){
  if(owner[v]>=0 || is_hub[v])continue;
  int cid=part_sizes.size(),size=0;
  std::queue<int> q;q.push(v);owner[v]=cid;
  while(!q.empty()){
   int u=q.front();q.pop();size++;
   for(int w:g[u])if(!is_hub[w]&&owner[w]<0){owner[w]=cid;q.push(w);}
  }
  part_sizes.push_back(size);
 }
 int large=0;
 for(int sz:part_sizes)if(sz>=8)large++;
 hints.hubs=hubs.size();
 hints.components=part_sizes.size();
 hints.structurally_separable=(large>=2);
 if(!hints.structurally_separable){
  hints.analysis_us=std::chrono::duration<double,std::micro>(Clock::now()-t0).count();
  return hints;
 }
 // Internal module clauses receive higher weight, hub-adjacent clauses lower.
 // This deliberately tests *local* phase guidance, not simply global vote.
 std::vector<double> pos(n+1,0),neg(n+1,0);
 std::vector<std::vector<double>> hub_pos(n+1),hub_neg(n+1);
 for(int h:hubs){
  hub_pos[h].assign(part_sizes.size(),0);
  hub_neg[h].assign(part_sizes.size(),0);
 }
 for(const auto &clause:f.clauses){
  bool includes_hub=false;
  int owner_id=-1;bool mixed=false;
  for(int lit:clause){
   int v=std::abs(lit);
   if(is_hub[v]){includes_hub=true;continue;}
   if(owner_id==-1)owner_id=owner[v];
   else if(owner_id!=owner[v])mixed=true;
  }
  if(mixed)throw std::runtime_error("Invalid component structure");
  for(int lit:clause){
   int v=std::abs(lit);
   if(is_hub[v]){
    if(owner_id>=0){
     (lit>0?hub_pos[v][owner_id]:hub_neg[v][owner_id])+=1.0;
    }
   }else{
    double weight=includes_hub?0.35:1.35;
    (lit>0?pos[v]:neg[v])+=weight;
   }
  }
 }
 // Equal-weight module votes for hub variables: one module cannot drown out
 // all other modules merely by having more clauses.
 for(int h:hubs){
  double module_pos=0,module_neg=0,observed=0;
  for(size_t i=0;i<part_sizes.size();i++){
   double a=hub_pos[h][i],b=hub_neg[h][i];
   if(a+b<=0)continue;
   module_pos+=a/(a+b);
   module_neg+=b/(a+b);
   observed++;
  }
  if(observed>=2 && eligible(module_pos,module_neg,2,0.15))
   hints.lit.push_back(module_pos>module_neg?h:-h);
 }
 for(int v=1;v<=n;v++){
  if(is_hub[v])continue;
  if(occ[v]>=6 && eligible(pos[v],neg[v],1,0.15))
   hints.lit.push_back(pos[v]>neg[v]?v:-v);
 }
 hints.candidates=hints.lit.size();
 hints.analysis_us=std::chrono::duration<double,std::micro>(Clock::now()-t0).count();
 return hints;
}
Hints random_hint(const CNFData &f,unsigned seed){
 auto t0=Clock::now();
 std::vector<int> occ(f.vars+1,0);
 for(const auto &c:f.clauses)for(int lit:c)occ[std::abs(lit)]++;
 std::mt19937 rng(seed);
 Hints h;
 for(int v=1;v<=f.vars;v++){
  if(occ[v]>=6 && (rng()%100)<60)h.lit.push_back((rng()&1)?v:-v);
 }
 h.candidates=h.lit.size();
 h.analysis_us=std::chrono::duration<double,std::micro>(Clock::now()-t0).count();
 return h;
}
Result run(const CNFData &f,const std::string &method,unsigned seed){
 Result out;
 CaDiCaL::Solver solver;
 fill(solver,f);
 Hints hints;
 if(method=="majority")hints=majority(f);
 else if(method=="structural")hints=structure(f);
 else if(method=="random_phase")hints=random_hint(f,seed);
 else if(method!="plain")throw std::runtime_error("unknown method");
 for(int lit:hints.lit)solver.phase(lit);
 int status=solver.solve();
 if(status!=10&&status!=20)throw std::runtime_error("CaDiCaL UNKNOWN");
 if(status==10)assert_sat_model(solver,f);
 out.status=status;out.hints=hints.lit.size();out.hubs=hints.hubs;
 out.components=hints.components;out.modular=hints.structurally_separable;
 out.analysis_us=hints.analysis_us;
 return out;
}
int main(int argc,char **argv){
 try{
  if(argc<4){std::cerr<<"Usage: phase_bench manifest.csv result.csv REPS [seed]\n";return 2;}
  auto items=read_manifest(argv[1]);std::ofstream fp(argv[2]);
  int reps=std::stoi(argv[3]);
  if(reps<1||reps>20)throw std::runtime_error("Invalid reps");
  unsigned seed=(argc>4)?std::stoul(argv[4]):20261119u;
  const std::vector<std::string> methods={"plain","majority","structural","random_phase"};
  fp<<"case,family,group,method,rep,elapsed_us,answer,advised,hubs,components,modular,analysis_us,variables,clauses\n";
  fp<<std::fixed<<std::setprecision(5);
  int done=0;
  for(const auto &item:items){
   const auto f=load_cnf(item.path);
   int expected=-1;
   for(int rep=0;rep<reps;rep++){
    std::vector<std::string> order=methods;
    std::mt19937 rng(seed+done*1237u+rep);
    std::shuffle(order.begin(),order.end(),rng);
    for(const auto &method:order){
     auto t0=Clock::now();
     const Result result=run(f,method,seed+done*131u);
     double elapsed=std::chrono::duration<double,std::micro>(Clock::now()-t0).count();
     if(expected<0)expected=result.status;
     else if(expected!=result.status)
      throw std::runtime_error("SAT/UNSAT mismatch: "+item.id+" method "+method);
     fp<<item.id<<','<<item.family<<','<<item.group<<','<<method<<','
       <<rep<<','<<elapsed<<','<<(result.status==10?"SAT":"UNSAT")<<','
       <<result.hints<<','<<result.hubs<<','<<result.components<<','
       <<result.modular<<','<<result.analysis_us<<','
       <<f.vars<<','<<f.clauses.size()<<"\n";
    }
   }
   fp.flush();
   std::cerr<<"Verified "<<++done<<"/"<<items.size()<<" "<<item.id
            <<" "<<(expected==10?"SAT":"UNSAT")<<"\n";
  }
  return 0;
 }catch(const std::exception &ex){
  std::cerr<<"FATAL: "<<ex.what()<<"\n";
  return 1;
 }
}
