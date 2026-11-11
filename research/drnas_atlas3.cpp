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
 int gate_hits=0,gate_scanned=0,npn_class=-1,saved_literals=0,committed_modules=0;
 int signal_repeats=0,signal_nested=0,gate_score=0,gate_sampled=0;
 double gate_s=0;
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

struct ModuleProposal {
 std::vector<int> ids;
 std::vector<std::vector<int>> replacement;
 int score=0, saved=0, class_id=-1;
};
static CNF first_look(const CNF& f,Result& r,double cap,Clock::time_point start){
 r.vars=f.vars;r.clauses=int(f.clauses.size());
 r.method="bounded_batch_exact_NPN";
 const auto scan_start=Clock::now();
 // Do not assume adjacent gate clauses: group ORIGINAL clauses by unsigned
 // variable support; any accepted substitution is truth-table equivalent.
 std::map<std::vector<int>,std::vector<int>> by_support;
 const size_t source_cap=std::min<size_t>(f.clauses.size(),4000);
 for(size_t id=0;id<source_cap;++id){
  const auto& c=f.clauses[id];
  if(c.size()>4||c.empty())continue;
  std::vector<int> support;
  for(int lit:c)support.push_back(std::abs(lit));
  std::sort(support.begin(),support.end());
  support.erase(std::unique(support.begin(),support.end()),support.end());
  if(support.size()<=4)by_support[support].push_back(int(id));
  if(c.size()==1)++r.unit;
  else if(c.size()==2)++r.binary;
  else if(c.size()==3)++r.ternary;
  else ++r.longer;
 }
 r.scan_s=std::chrono::duration<double>(Clock::now()-scan_start).count();
 if(f.vars<=8){r.decision="fallback";r.reason="tiny_input";return f;}
 if(r.scan_s>0.003){r.decision="fallback";r.reason="scan_budget";return f;}
 const auto begin=Clock::now();
 const double probe_cap=std::min(0.003,cap*0.001);
 std::vector<ModuleProposal> opportunities;
 opportunities.reserve(64);
 for(const auto& it:by_support){
  if(std::chrono::duration<double>(Clock::now()-begin).count()>probe_cap)break;
  const auto& vars=it.first;
  const int k=int(vars.size());
  if(k<2||k>4)continue;
  ++r.gate_scanned;
  std::vector<int> ids;
  for(unsigned mask=1;mask<(1u<<k);++mask){
   std::vector<int> subset;
   for(int j=0;j<k;++j)if(mask&(1u<<j))subset.push_back(vars[j]);
   auto candidate=by_support.find(subset);
   if(candidate!=by_support.end())
    ids.insert(ids.end(),candidate->second.begin(),candidate->second.end());
  }
  if(ids.size()<2||ids.size()>24)continue;
  ++r.pairs;
  const unsigned states=1u<<k;
  uint32_t truth=0;
  for(unsigned bits=0;bits<states;++bits){
   bool sat=true;
   for(int cid:ids){
    if(!clause_holds(f.clauses[size_t(cid)],vars,int(bits))){
     sat=false;break;
    }
   }
   if(sat)truth|=1u<<bits;
  }
  auto recipe=atlas_recipe(k,truth,vars);
  ++r.gate_hits;
  if(recipe.clauses.size()>ids.size())continue;
  int old_lits=0,new_lits=0;
  for(int cid:ids)old_lits+=int(f.clauses[size_t(cid)].size());
  for(const auto& c:recipe.clauses)new_lits+=int(c.size());
  const int saved=old_lits-new_lits;
  if(saved<=0)continue;
  // Never select an approximate Boolean match: independently enumerate
  // the local truth table AFTER reorienting the NPN recipe.
  for(unsigned bits=0;bits<states;++bits){
   bool sat=true;
   for(const auto& c:recipe.clauses)
    if(!clause_holds(c,vars,int(bits))){sat=false;break;}
   drnas::require(sat==bool((truth>>bits)&1u),"ATLAS3 equivalence check FAILED");
  }
  ++r.derived;
  ModuleProposal p;
  p.score=16*(int(ids.size())-int(recipe.clauses.size()))+saved;
  p.saved=saved;p.class_id=recipe.cls;
  p.ids=std::move(ids);
  p.replacement=std::move(recipe.clauses);
  opportunities.push_back(std::move(p));
 }
 r.probe_s=std::chrono::duration<double>(Clock::now()-begin).count();
 if(opportunities.empty()){
  r.decision="sleep";r.reason="no_profitable_structured_blocks";return f;
 }
 std::sort(opportunities.begin(),opportunities.end(),[](const ModuleProposal& a,const ModuleProposal& b){
  if(a.score!=b.score)return a.score>b.score;
  if(a.saved!=b.saved)return a.saved>b.saved;
  return a.ids<b.ids;
 });
 // Greedy disjoint BATCH: every module uses a set of ORIGINAL clauses.
 // Modules may share variables, but their removed clause IDs may NOT overlap.
 // Consequently replacing their conjunction preserves the full formula.
 std::vector<unsigned char> selected(f.clauses.size(),0);
 std::vector<std::vector<int>> new_clauses;
 int modules=0,deleted=0,saved=0,last_class=-1;
 for(const auto& p:opportunities){
  if(modules>=32)break;
  bool overlaps=false;
  for(int cid:p.ids)if(selected[size_t(cid)]){overlaps=true;break;}
  if(overlaps)continue;
  for(int cid:p.ids)selected[size_t(cid)]=1;
  deleted+=int(p.ids.size());
  saved+=p.saved;
  last_class=p.class_id;
  ++modules;
  for(const auto& c:p.replacement)new_clauses.push_back(c);
 }
 if(modules==0){r.decision="sleep";r.reason="no_disjoint_blocks";return f;}
 CNF result;result.vars=f.vars;
 result.clauses.reserve(f.clauses.size()-size_t(deleted)+new_clauses.size());
 for(size_t i=0;i<f.clauses.size();++i)
  if(!selected[i])result.clauses.push_back(f.clauses[i]);
 for(auto& c:new_clauses)result.clauses.push_back(std::move(c));
 r.accepted=int(new_clauses.size());
 r.pivots=deleted;
 r.committed_modules=modules;
 r.saved_literals=saved;
 r.npn_class=last_class;
 r.decision="commit";r.reason="multi_block_exact_truth_table";
 return result;
}

static uint64_t support_signature(const int* lits,int width){
 uint64_t h=0x9e3779b97f4a7c15ULL ^ uint64_t(width);
 for(int i=0;i<width;++i){
  h^=uint64_t(uint32_t(lits[i]))*0xc2b2ae3d27d4eb4fULL;
  h=(h<<21)|(h>>43);
  h*=0x165667b19e3779f9ULL;
 }
 h^=h>>33;h*=0xff51afd7ed558ccdULL;h^=h>>33;
 return h;
}
static CNF atlas3_selective(const CNF& f,Result& r,double cap,Clock::time_point start,int threshold){
 r.method="cheap_structure_before_deep_atlas";
 r.vars=f.vars;r.clauses=int(f.clauses.size());
 const auto t0=Clock::now();
 constexpr unsigned BITS=65536;
 std::array<uint64_t,BITS/64> supports{},pair_seen{},pair_contained{};
 auto has=[](const std::array<uint64_t,BITS/64>& arr,uint64_t h){
  const unsigned bit=unsigned(h)&(BITS-1);
  return (arr[bit>>6]&(1ULL<<(bit&63)))!=0;
 };
 auto add=[](std::array<uint64_t,BITS/64>& arr,uint64_t h){
  const unsigned bit=unsigned(h)&(BITS-1);
  arr[bit>>6]|=1ULL<<(bit&63);
 };
 // Fast one-time fingerprint on only the first 384 original clauses.
 // Repeated 2-4-variable supports hint at parity/gates. A binary
 // clause nested in a ternary/quaternary support hints at Tseitin/AMO.
 // This is a COST ESTIMATE, not a Boolean proof. Only deep ATLAS2
 // is allowed to transform and re-verifies all truth-table assignments.
 const size_t limit=std::min<size_t>(384,f.clauses.size());
 for(size_t cid=0;cid<limit;++cid){
  if((cid&63u)==0 && std::chrono::duration<double>(Clock::now()-t0).count()>0.00018){
   r.gate_s=std::chrono::duration<double>(Clock::now()-t0).count();
   r.decision="sleep";r.reason="gate_budget_exceeded";
   return f;
  }
  const auto& c=f.clauses[cid];
  if(c.size()<2||c.size()>4)continue;
  int a[4];int n=0;
  for(int lit:c){const int v=std::abs(lit);if(v>0)a[n++]=v;}
  std::sort(a,a+n);n=int(std::unique(a,a+n)-a);
  if(n<2||n>4)continue;
  ++r.gate_sampled;
  const uint64_t whole=support_signature(a,n);
  if(has(supports,whole))++r.signal_repeats;
  add(supports,whole);
  if(n==2){
   if(has(pair_contained,whole))++r.signal_nested;
   add(pair_seen,whole);
  }else{
   for(int i=0;i<n;++i)for(int j=i+1;j<n;++j){
    const int pair[2]={a[i],a[j]};
    const uint64_t p=support_signature(pair,2);
    if(has(pair_seen,p))++r.signal_nested;
    add(pair_contained,p);
   }
  }
 }
 r.gate_s=std::chrono::duration<double>(Clock::now()-t0).count();
 r.gate_score=3*r.signal_repeats+2*r.signal_nested;
 if(r.gate_score<threshold){
  r.decision="sleep";r.reason="low_structural_opportunity";
  return f;
 }
 if(r.gate_s>0.00018){
  r.decision="sleep";r.reason="gate_budget_exceeded";
  return f;
 }
 const int repeats=r.signal_repeats,nested=r.signal_nested,score=r.gate_score,sampled=r.gate_sampled;
 const double gate_time=r.gate_s;
 CNF out=first_look(f,r,cap,start);
 r.signal_repeats=repeats;r.signal_nested=nested;r.gate_score=score;
 r.gate_sampled=sampled;r.gate_s=gate_time;
 r.method="cheap_structure_then_exact_NPN_batch";
 return out;
}

}
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
    std::cout<<"ATLAS3_EXHAUSTIVE_PASS k="<<k<<" functions="<<functions<<"\n";
   }
   return 0;
  }
  if(argc!=6||std::string(argv[2])!="--mode"||std::string(argv[4])!="--time"){
   std::cerr<<"usage: atlas3 FILE --mode A|ATLAS2|ATLAS3|ATLAS3_STRICT --time SECONDS\n";return 2;
  }
  const std::string arm=argv[3];drnas::require(arm=="A"||arm=="ATLAS2"||arm=="ATLAS3"||arm=="ATLAS3_STRICT","bad mode");
  const double cap=std::stod(argv[5]);drnas::require(cap>0&&cap<=3600,"bad cap");
  auto start=drnas::Clock::now();
  const drnas::CNF original=drnas::read_dimacs(argv[1]);
  arl1::Result p;
  drnas::CNF working=original;
  if(arm=="ATLAS2")working=arl1::first_look(original,p,cap,start);
  else if(arm=="ATLAS3")working=arl1::atlas3_selective(original,p,cap,start,12);
  else if(arm=="ATLAS3_STRICT")working=arl1::atlas3_selective(original,p,cap,start,32);
  if(arm=="A"){p.decision="baseline";p.reason="baseline_no_scan";}
  drnas::NativeCDCL solver(working.vars);
  solver.add_cnf(working);
  const double elapsed=std::chrono::duration<double>(drnas::Clock::now()-start).count();
  const int status=elapsed<cap?solver.solve(cap-elapsed):0;
  if(status==10)drnas::require(solver.verify_original(original),"SAT witness failed ORIGINAL CNF");
  const auto e2e=std::chrono::duration<double>(drnas::Clock::now()-start).count();
  const auto& st=solver.statistics();
  std::cout<<std::fixed<<std::setprecision(8)
           <<"ATLAS3_TRIAL arm="<<arm<<" status="<<(status==10?"SAT":status==20?"UNSAT":"UNKNOWN")
           <<" e2e_s="<<e2e<<" look_s="<<p.scan_s<<" probe_s="<<p.probe_s
           <<" gate_s="<<p.gate_s<<" gate_score="<<p.gate_score<<" gate_sampled="<<p.gate_sampled
           <<" signal_repeats="<<p.signal_repeats<<" signal_nested="<<p.signal_nested
           <<" vars="<<original.vars<<" original_clauses="<<original.clauses.size()
           <<" final_clauses="<<working.clauses.size()
           <<" unit="<<p.unit<<" binary="<<p.binary<<" ternary="<<p.ternary
           <<" gate_hits="<<p.gate_hits<<" gate_scanned="<<p.gate_scanned<<" pairs="<<p.pairs<<" pivots="<<p.pivots<<" derived="<<p.derived
           <<" method="<<p.method<<" modules="<<p.committed_modules<<" npn_class="<<p.npn_class<<" saved_literals="<<p.saved_literals<<" removed="<<p.pivots<<" added="<<p.accepted<<" accepted="<<p.accepted<<" decision="<<p.decision<<" reason="<<p.reason
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
 }catch(const std::exception& e){std::cerr<<"ATLAS3_ERROR "<<e.what()<<"\n";return 2;}
}
