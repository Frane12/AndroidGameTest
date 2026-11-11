// ARL1-B opportunity indexed first look, one bounded probe, immediate decision.
// Native original DRNAS CDCL; isolated experiment, no third-party backend.
// Only exact binary resolvents from two ORIGINAL ternary clauses are appended.
// Every candidate is an exact consequence; return SAT is checked on original.
#define main drnas_r3c_embedded_main
#include "drnas_native_core_r3c.cpp"
#undef main
#include <unordered_set>
#include <unordered_map>
#include <array>
#include "atlas1_table.hpp"
namespace arl1 {
using drnas::CNF;
using drnas::Clock;
struct Result{
 int vars=0,clauses=0,unit=0,binary=0,ternary=0,longer=0;
 int pairs=0,pivots=0,taut=0,derived=0,accepted=0;
 int gate_hits=0,gate_scanned=0,npn_class=-1,saved_literals=0;
 std::string decision="none",reason="none",method="none";
 double scan_s=0,probe_s=0;
};
static std::vector<int> normalized(const std::vector<int>& c) {
 std::vector<int> s=c;
 std::sort(s.begin(),s.end(),[](int a,int b){return std::abs(a)!=std::abs(b)?
                      std::abs(a)<std::abs(b):a<b;});
 s.erase(std::unique(s.begin(),s.end()),s.end());
 for(size_t k=1;k<s.size();++k)
  if(s[k]==-s[k-1])return {};
 return s;
}
static uint64_t key2(int a,int b,int n){
 auto encode=[&](int lit)->uint64_t{return uint64_t(lit+n);};
 return (encode(a)<<32)|encode(b);
}

struct CatalogRule {
 std::vector<std::vector<int>> clauses;
 int cls=-1;
};
static CatalogRule atlas_recipe(int k,uint32_t truth,const std::vector<int>& vars) {
 namespace db=drnas_atlas1_data;
 const uint32_t key=k==2?db::index2[truth]:k==3?db::index3[truth]:db::index4[truth];
 const unsigned cls=key&255u,witness=key>>8;
 const unsigned invert=witness&1u,flip=(witness>>1u)&((1u<<k)-1u);
 const unsigned perm_id=witness>>(k+1);
 const unsigned recipe_index=cls*2u+invert;
 const unsigned begin=k==2?db::offset2[recipe_index]:k==3?db::offset3[recipe_index]:db::offset4[recipe_index];
 const unsigned end=k==2?db::offset2[recipe_index+1]:k==3?db::offset3[recipe_index+1]:db::offset4[recipe_index+1];
 CatalogRule result;result.cls=int(cls);
 for(unsigned z=begin;z<end;++z) {
  unsigned code=k==2?db::recipes2[z]:k==3?db::recipes3[z]:db::recipes4[z];
  std::vector<int> c;
  for(int i=0;i<k;++i){
   const unsigned digit=code%3;code/=3;
   if(!digit)continue;
   const unsigned position=k==2?db::perm2[perm_id][i]:k==3?db::perm3[perm_id][i]:db::perm4[perm_id][i];
   const bool positive=(digit==1)^bool((flip>>i)&1u);
   c.push_back(positive?vars[position]:-vars[position]);
  }
  result.clauses.push_back(std::move(c));
 }
 return result;
}
static bool clause_holds(const std::vector<int>& c,const std::vector<int>& vars,int bits){
 for(int lit:c){
  auto it=std::lower_bound(vars.begin(),vars.end(),std::abs(lit));
  drnas::require(it!=vars.end()&&*it==std::abs(lit),"atlas literal outside module");
  const bool assigned=((bits>>int(it-vars.begin()))&1)!=0;
  if(assigned==(lit>0))return true;
 }
 return false;
}
static CNF first_look(const CNF& f,Result& r,double cap,Clock::time_point start){
 r.vars=f.vars;r.clauses=int(f.clauses.size());
 CNF out=f;
 const auto t0=Clock::now();
 // Source-only indexing; each module contains whole ORIGINAL clauses, never
 // clauses from a learned database. Allow up to 1,400 clauses and 4 variables.
 std::map<std::vector<int>,std::vector<int>> by_support;
 const size_t cap_clauses=std::min<size_t>(f.clauses.size(),1400);
 for(size_t id=0;id<cap_clauses;++id){
  const auto& clause=f.clauses[id];
  if(clause.empty()||clause.size()>4)continue;
  std::vector<int> support;
  for(int lit:clause)support.push_back(std::abs(lit));
  std::sort(support.begin(),support.end());
  support.erase(std::unique(support.begin(),support.end()),support.end());
  if(support.size()<=4)by_support[support].push_back(int(id));
  if(clause.size()==1)++r.unit;
  if(clause.size()==2)++r.binary;
  if(clause.size()==3)++r.ternary;
 }
 r.scan_s=std::chrono::duration<double>(Clock::now()-t0).count();
 r.method="exact_truth_table_NPN";
 if(f.vars<=8){r.decision="fallback";r.reason="tiny_input";return out;}
 if(r.scan_s>0.001){r.decision="fallback";r.reason="index_budget";return out;}
 const auto t1=Clock::now();
 const double budget=std::min(0.00075,cap*0.001);
 int best_score=0,best_class=-1,best_saved=0;
 std::vector<int> best_ids;std::vector<std::vector<int>> best_recipe;
 for(const auto& it:by_support){
  if(std::chrono::duration<double>(Clock::now()-t1).count()>budget)break;
  const auto& vars=it.first;
  const int k=int(vars.size());
  if(k<2||k>4)continue;
  ++r.gate_scanned;
  std::vector<int> module;
  for(unsigned sub=1;sub<(1u<<k);++sub){
   std::vector<int> key;
   for(int j=0;j<k;++j)if(sub&(1u<<j))key.push_back(vars[j]);
   auto jt=by_support.find(key);
   if(jt!=by_support.end())module.insert(module.end(),jt->second.begin(),jt->second.end());
  }
  if(module.size()<2||module.size()>16)continue;
  ++r.pairs;
  const unsigned nstates=1u<<k;
  uint32_t truth=0;
  for(unsigned bits=0;bits<nstates;++bits){
   bool all=true;
   for(int id:module)if(!clause_holds(f.clauses[id],vars,int(bits))){all=false;break;}
   if(all)truth|=1u<<bits;
  }
  const auto candidate=atlas_recipe(k,truth,vars);
  ++r.gate_hits;
  int old_lits=0,new_lits=0;
  for(int id:module)old_lits+=int(f.clauses[id].size());
  for(const auto& c:candidate.clauses)new_lits+=int(c.size());
  if(candidate.clauses.size()>module.size())continue;
  const int saved=old_lits-new_lits;
  if(saved<=0)continue;
  // Mandatory independent 2^k-truth-table equality verification before COMMIT.
  bool valid=true;
  for(unsigned bits=0;bits<nstates;++bits){
   bool reconstructed=true;
   for(const auto& c:candidate.clauses)
    if(!clause_holds(c,vars,int(bits))){reconstructed=false;break;}
   if(reconstructed!=bool((truth>>bits)&1u)){valid=false;break;}
  }
  drnas::require(valid,"ATLAS1 exact local equivalence proof failed");
  ++r.derived;
  const int score=8*(int(module.size())-int(candidate.clauses.size()))+saved;
  if(score>best_score){
   best_score=score;best_ids=std::move(module);
   best_recipe=candidate.clauses;best_class=candidate.cls;best_saved=saved;
  }
 }
 r.probe_s=std::chrono::duration<double>(Clock::now()-t1).count();
 if(best_ids.empty()){
  r.decision="sleep";r.reason="no_profitable_exact_rewrite";return out;
 }
 std::vector<unsigned char> drop(f.clauses.size(),0);
 for(int id:best_ids)drop[size_t(id)]=1;
 out.clauses.clear();out.clauses.reserve(f.clauses.size()-best_ids.size()+best_recipe.size());
 for(size_t i=0;i<f.clauses.size();++i)if(!drop[i])out.clauses.push_back(f.clauses[i]);
 for(const auto& c:best_recipe)out.clauses.push_back(c);
 r.accepted=int(best_recipe.size());r.pivots=int(best_ids.size());
 r.derived=1;r.npn_class=best_class;r.saved_literals=best_saved;
 r.decision="commit";r.reason="truth_table_proven_equivalence";
 return out;
}

}
#ifndef DRNAS_ATLAS1_AS_LIBRARY
int main(int argc,char**argv) {
 try{
  if(argc==2 && std::string(argv[1])=="--atlas-selftest"){
   for(int k=2;k<=4;++k){
    std::vector<int> support;for(int v=1;v<=k;++v)support.push_back(v);
    const unsigned functions=1u<<(1u<<k);
    for(unsigned truth=0;truth<functions;++truth){
     const auto rule=arl1::atlas_recipe(k,truth,support);
     for(unsigned bits=0;bits<(1u<<k);++bits){
      bool sat=true;
      for(const auto& clause:rule.clauses)
       if(!arl1::clause_holds(clause,support,int(bits))){sat=false;break;}
      drnas::require(sat==bool((truth>>bits)&1u),"atlas generated recipe mismatch");
     }
    }
    std::cout<<"ATLAS1_EXHAUSTIVE_PASS k="<<k<<" functions="<<functions<<"\n";
   }
   return 0;
  }
  if(argc!=6||std::string(argv[2])!="--mode"||std::string(argv[4])!="--time"){
   std::cerr<<"usage: atlas1 FILE --mode A|ATLAS1 --time SECONDS\n";return 2;
  }
  const std::string arm=argv[3];drnas::require(arm=="A"||arm=="ATLAS1","bad mode");
  const double cap=std::stod(argv[5]);drnas::require(cap>0&&cap<=3600,"bad cap");
  auto start=drnas::Clock::now();
  const drnas::CNF original=drnas::read_dimacs(argv[1]);
  arl1::Result p;drnas::CNF working=original;
  if(arm=="ATLAS1")working=arl1::first_look(original,p,cap,start);
  else {p.decision="baseline";p.reason="baseline_no_scan";}
  drnas::NativeCDCL solver(working.vars);
  solver.add_cnf(working);
  const double elapsed=std::chrono::duration<double>(drnas::Clock::now()-start).count();
  const int status=elapsed<cap?solver.solve(cap-elapsed):0;
  if(status==10)drnas::require(solver.verify_original(original),"SAT witness failed ORIGINAL CNF");
  const auto e2e=std::chrono::duration<double>(drnas::Clock::now()-start).count();
  const auto& st=solver.statistics();
  std::cout<<std::fixed<<std::setprecision(8)
           <<"ATLAS1_TRIAL arm="<<arm<<" status="<<(status==10?"SAT":status==20?"UNSAT":"UNKNOWN")
           <<" e2e_s="<<e2e<<" look_s="<<p.scan_s<<" probe_s="<<p.probe_s
           <<" vars="<<original.vars<<" original_clauses="<<original.clauses.size()
           <<" final_clauses="<<working.clauses.size()
           <<" unit="<<p.unit<<" binary="<<p.binary<<" ternary="<<p.ternary
           <<" gate_hits="<<p.gate_hits<<" gate_scanned="<<p.gate_scanned<<" pairs="<<p.pairs<<" pivots="<<p.pivots<<" derived="<<p.derived
           <<" method="<<p.method<<" npn_class="<<p.npn_class<<" saved_literals="<<p.saved_literals<<" removed="<<p.pivots<<" added="<<p.accepted<<" accepted="<<p.accepted<<" decision="<<p.decision<<" reason="<<p.reason
           <<" conflicts="<<st.conflicts<<" decisions="<<st.decisions
           <<" propagations="<<st.propagations<<" watch_visits="<<st.watch_visits
           <<" learned="<<st.learned_clauses
           <<" SAT_original_verified="<<int(status==10)
           <<" UNSAT_independent_LRAT=0"<<" oneCPU=1\n";
  if(status==10){
   std::cout<<"s SATISFIABLE\nv ";
   for(int v=1;v<=original.vars;++v)std::cout<<(solver.assignments()[v]<0?-v:v)<<" ";
   std::cout<<"0\n";
  }else std::cout<<(status==20?"s UNSATISFIABLE\n":"s UNKNOWN\n");
  return status==10?10:status==20?20:0;
 }catch(const std::exception& e){std::cerr<<"ATLAS1_ERROR "<<e.what()<<"\n";return 2;}
}

#endif // DRNAS_ATLAS1_AS_LIBRARY
