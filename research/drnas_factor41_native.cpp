// FACTOR2: Native C++ exact component projection with automatic separator.
// This is a bounded prototype; no independent LRAT proof is emitted.
#define DRNAS_FACTOR2_EMBED
#include "drnas_sre2c_native.cpp"
#undef DRNAS_FACTOR2_EMBED
#include <numeric>
namespace factor2 {
using drnas::CNF;
struct Plan {
 std::vector<int> sep;
 std::vector<std::vector<int>> vars;
 std::vector<std::vector<std::vector<int>>> clauses;
 std::vector<std::vector<int>> sep_only;
 bool ok=false;
};
static Plan decompose(const CNF& f,const std::vector<int>& sep) {
 Plan p;p.sep=sep;
 std::vector<int> parent(f.vars+1);
 std::iota(parent.begin(),parent.end(),0);
 auto root=[&](int x){while(parent[x]!=x){parent[x]=parent[parent[x]];x=parent[x];}return x;};
 auto join=[&](int a,int b){a=root(a);b=root(b);if(a!=b)parent[b]=a;};
 std::vector<bool> cut(f.vars+1,false);
 for(int s:sep)cut[s]=true;
 for(const auto& c:f.clauses){
  int first=0;
  for(int lit:c)if(!cut[abs(lit)]){if(first)join(first,abs(lit));else first=abs(lit);}
 }
 std::map<int,int> ids;
 std::vector<int> where(f.vars+1,-1);
 for(int v=1;v<=f.vars;++v)if(!cut[v]){
  int r=root(v);
  if(!ids.count(r)){ids[r]=int(p.vars.size());p.vars.push_back({});}
  int i=ids[r];p.vars[i].push_back(v);where[v]=i;
 }
 p.clauses.resize(p.vars.size());
 for(const auto& c:f.clauses){
  int id=-1;
  for(int lit:c)if(!cut[abs(lit)]){
   int x=where[abs(lit)];
   if(id!=-1&&id!=x)throw std::runtime_error("bad component partition");
   id=x;
  }
  if(id<0)p.sep_only.push_back(c);else p.clauses[id].push_back(c);
 }
 p.ok=p.vars.size()>=2;
 return p;
}
static Plan choose(const CNF& f){
 // Find small separator automatically, using only original CNF structure.
 // One-variable cuts first, then pairs; bounded candidate scan.
 for(int k=1;k<=2;++k){
  for(int a=1;a<=f.vars;++a){
   if(k==1){
    Plan p=decompose(f,{a});
    if(p.ok)return p;
   }else{
    for(int b=a+1;b<=f.vars;++b){
     Plan p=decompose(f,{a,b});
     if(p.ok)return p;
    }
   }
  }
 }
 return {};
}
static bool holds(const std::vector<std::vector<int>>& clauses,const std::vector<int8_t>& values){
 for(const auto& c:clauses){
  bool sat=false;
  for(int lit:c)if(values[abs(lit)]==(lit>0?1:-1)){sat=true;break;}
  if(!sat)return false;
 }
 return true;
}
struct Result {
 int status=0;
 std::vector<int8_t> model;
 int separator_size=0,components=0,checks=0,rejected=0,gate_skip=0,separator_probes=0;
 double separator_search_s=0;
 double density=0;
 bool abstained=false;
};
static Plan choose_budgeted(const CNF& f,Result& r,double budget_s){
 // Bounded source-only probe: never enumerate O(n^2) separator pairs.
 // Large graphs go straight to CDCL. At most eight single-variable cuts.
 if(f.vars>256||f.clauses.size()>4000){r.gate_skip=2;return {};}
 std::vector<int> occurrence(f.vars+1,0);
 for(const auto& c:f.clauses)for(int lit:c)++occurrence[abs(lit)];
 std::vector<int> candidates(f.vars);
 std::iota(candidates.begin(),candidates.end(),1);
 std::stable_sort(candidates.begin(),candidates.end(),
  [&](int a,int b){return occurrence[a]>occurrence[b];});
 auto begin=drnas::Clock::now();
 for(int i=0;i<std::min<int>(8,candidates.size());++i){
  if(std::chrono::duration<double>(drnas::Clock::now()-begin).count()>=budget_s)break;
  ++r.separator_probes;
  Plan p=decompose(f,{candidates[i]});
  if(p.ok){
   r.separator_search_s=std::chrono::duration<double>(drnas::Clock::now()-begin).count();
   return p;
  }
 }
 r.separator_search_s=std::chrono::duration<double>(drnas::Clock::now()-begin).count();
 return {};
}
static Result solve(const CNF& f,double budget,bool gated=false,bool budgeted=false){
 auto start=drnas::Clock::now();
 Result r;
 // Source-only cheap gate: clause density, measured before any separator search.
 // Prespecified threshold; no SAT labels, timings or solution data.
 r.density=f.vars?double(f.clauses.size())/double(f.vars):0;
 if(gated && r.density>5.0){r.gate_skip=1;r.abstained=true;return r;}
 Plan p=budgeted?choose_budgeted(f,r,std::min(0.003,budget*0.01)):choose(f);
 if(!p.ok){r.abstained=true;return r;}
 r.separator_size=p.sep.size();r.components=p.vars.size();
 // No exponential blow-up in local components.
 for(const auto& vars:p.vars)if(vars.size()>12){r.abstained=true;return r;}
 std::vector<int8_t> assignment(f.vars+1,0);
 const int total=1<<int(p.sep.size());
 for(int mask=0;mask<total;++mask){
  if(std::chrono::duration<double>(drnas::Clock::now()-start).count()>budget){
   r.abstained=true;return r;
  }
  for(size_t j=0;j<p.sep.size();++j)assignment[p.sep[j]]=(mask&(1<<j))?1:-1;
  if(!holds(p.sep_only,assignment)){++r.rejected;continue;}
  bool all=true;
  for(size_t i=0;i<p.vars.size();++i){
   const auto& vars=p.vars[i];
   bool found=false;
   for(int bits=0;bits<(1<<int(vars.size()));++bits){
    ++r.checks;
    for(size_t j=0;j<vars.size();++j)assignment[vars[j]]=(bits&(1<<j))?1:-1;
    if(holds(p.clauses[i],assignment)){found=true;break;}
   }
   if(!found){all=false;break;}
  }
  if(all){
   r.status=10;r.model=assignment;
   drnas::require(drnas::sre1_verify_original(f,r.model),"factor SAT model invalid");
   return r;
  }
  ++r.rejected;
 }
 r.status=20;return r;
}
}
int main(int argc,char**argv){
 try{
  if(argc!=6||std::string(argv[2])!="--mode"||std::string(argv[4])!="--time"){
   std::cerr<<"usage: factor41 FILE --mode A|B|C|D --time SECONDS\n";return 2;
  }
  std::string mode=argv[3];
  drnas::require(mode=="A"||mode=="B"||mode=="C"||mode=="D","invalid arm");
  double cap=std::stod(argv[5]);
  auto started=drnas::Clock::now();
  auto f=drnas::read_dimacs(argv[1]);
  factor2::Result result;
  drnas::NativeCDCL solver(f.vars);
  if(mode=="A"){
   solver.add_cnf(f);
   double prep=std::chrono::duration<double>(drnas::Clock::now()-started).count();
   if(prep<cap)result.status=solver.solve(cap-prep);
   if(result.status==10)result.model=solver.assignments();
  }else{
   double prep=std::chrono::duration<double>(drnas::Clock::now()-started).count();
   if(prep<cap)result=factor2::solve(f,cap-prep,mode=="C"||mode=="D",mode=="D");
   if(result.abstained){
    // Safe fallback: solve original CNF, never report guessed UNSAT.
    solver.add_cnf(f);
    double elapsed=std::chrono::duration<double>(drnas::Clock::now()-started).count();
    if(elapsed<cap)result.status=solver.solve(cap-elapsed);
    if(result.status==10)result.model=solver.assignments();
   }
  }
  if(result.status==10)
   drnas::require(drnas::sre1_verify_original(f,result.model),"original SAT model invalid");
  double e2e=std::chrono::duration<double>(drnas::Clock::now()-started).count();
  const auto& st=solver.statistics();
  std::cout<<std::fixed<<std::setprecision(7)<<"FACTOR2_TRIAL"
   <<" arm="<<mode<<" status="<<(result.status==10?"SAT":result.status==20?"UNSAT":"UNKNOWN")
   <<" e2e_s="<<e2e<<" sep="<<result.separator_size
   <<" components="<<result.components<<" local_checks="<<result.checks
   <<" rejected="<<result.rejected<<" fallback="<<int(result.abstained)
   <<" gate_skip="<<result.gate_skip<<" density="<<result.density
   <<" separator_probes="<<result.separator_probes<<" separator_search_s="<<result.separator_search_s
   <<" decisions="<<st.decisions<<" conflicts="<<st.conflicts
   <<" SAT_original_verified="<<int(result.status==10)
   <<" UNSAT_independent_LRAT=0\n";
  if(result.status==10){
   std::cout<<"s SATISFIABLE\nv ";
   for(int v=1;v<=f.vars;++v)std::cout<<(result.model[v]<0?-v:v)<<" ";
   std::cout<<"0\n";
  }else std::cout<<(result.status==20?"s UNSATISFIABLE\n":"s UNKNOWN\n");
  return result.status==10?10:result.status==20?20:0;
 }catch(const std::exception& e){std::cerr<<"FACTOR2_FAIL "<<e.what()<<"\n";return 2;}
}
