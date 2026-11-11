// ATLAS9: native DRNAS CDCL with ATLAS8 persistent exact-block reductions,
// original-source-certified GF(2), bounded Gaussian RREF and short CNF reasons.
// No proprietary/third-party SAT backend. Main branch untouched.
#define main drnas_atlas9_embedded_core_main
#include "drnas_native_core_r3c.cpp"
#undef main
#include "atlas8_rules.hpp"
#include <sstream>
namespace atlas9 {
using drnas::CNF;
using drnas::Clock;
using Clauses=std::vector<std::vector<int>>;
struct TableStats {int matched=0,committed=0,literals_saved=0;double seconds=0;};
static std::vector<int> support(const std::vector<int>& c) {
 std::vector<int> v;for(int l:c)v.push_back(std::abs(l));
 std::sort(v.begin(),v.end());v.erase(std::unique(v.begin(),v.end()),v.end());return v;
}
static bool local_holds(const Clauses& cs,int k,int bits) {
 for(const auto&c:cs) {
  bool yes=false;
  for(int l:c) {
   drnas::require(std::abs(l)>=1&&std::abs(l)<=k,"invalid catalog variable");
   if(bool((bits>>(std::abs(l)-1))&1)==(l>0)){yes=true;break;}
  }
  if(!yes)return false;
 }
 return true;
}
static bool equivalent(const Clauses& a,const Clauses& b,int k){
 for(int bits=0;bits<(1<<k);++bits)
  if(local_holds(a,k,bits)!=local_holds(b,k,bits))return false;
 return true;
}
static int lits(const Clauses& cs){int n=0;for(auto&c:cs)n+=int(c.size());return n;}
static CNF table_reduce(const CNF& src,TableStats&stats,double budget=0.012){
 const auto t0=Clock::now();
 std::map<Clauses,Clauses> lookup;
 for(auto rule:atlas9_data::load()){
  std::sort(rule.original.begin(),rule.original.end());
  if(rule.original.empty())continue;
  int k=0;for(auto&c:rule.original)for(int l:c)k=std::max(k,std::abs(l));
  drnas::require(k>=2&&k<=4&&equivalent(rule.original,rule.reduced,k),
   "ATLAS8 catalog rule failed runtime equivalence");
  drnas::require(lits(rule.original)>lits(rule.reduced),"catalog rule not reductive");
  lookup[rule.original]=rule.reduced;
 }
 std::map<std::vector<int>,int> support_count;
 for(const auto&c:src.clauses)if(c.size()>=2&&c.size()<=4){
  auto sp=support(c);if(sp.size()>=2&&sp.size()<=4)++support_count[sp];
 }
 std::vector<std::pair<std::vector<int>,int>> candidates(support_count.begin(),support_count.end());
 std::sort(candidates.begin(),candidates.end(),[](const auto&a,const auto&b){
  return a.second!=b.second?a.second>b.second:a.first<b.first;
 });
 std::vector<char> used(src.clauses.size(),0);
 Clauses added;
 size_t examined=0;
 for(const auto& candidate:candidates){
  if(examined++>=512)break;
  if(std::chrono::duration<double>(Clock::now()-t0).count()>budget)break;
  const auto&sup=candidate.first;const int k=int(sup.size());
  std::map<int,int> remap;
  for(int j=0;j<k;++j)remap[sup[j]]=j+1;
  Clauses old;
  std::vector<int> ids;
  for(size_t id=0;id<src.clauses.size();++id){
   const auto&c=src.clauses[id];
   if(c.size()>4)continue;
   bool inside=true;
   for(int l:c)if(!remap.count(std::abs(l))){inside=false;break;}
   if(!inside)continue;
   ids.push_back(int(id));
   std::vector<int> norm;
   bool taut=false;
   for(int l:c)norm.push_back(l>0?remap.at(std::abs(l)):-remap.at(std::abs(l)));
   std::sort(norm.begin(),norm.end(),[](int a,int b){return std::abs(a)!=std::abs(b)?std::abs(a)<std::abs(b):a>b;});
   norm.erase(std::unique(norm.begin(),norm.end()),norm.end());
   for(int l:norm)if(std::find(norm.begin(),norm.end(),-l)!=norm.end()){taut=true;break;}
   if(taut){old.clear();break;}
   old.push_back(std::move(norm));
  }
  if(old.size()<2||old.size()>24)continue;
  std::sort(old.begin(),old.end());old.erase(std::unique(old.begin(),old.end()),old.end());
  const auto it=lookup.find(old);if(it==lookup.end())continue;
  ++stats.matched;
  bool conflicts=false;for(int id:ids)if(used[id]){conflicts=true;break;}
  if(conflicts)continue;
  const auto&replacement=it->second;
  drnas::require(equivalent(old,replacement,k),"rule mismatch in exact source context");
  int before=0;for(int id:ids)before+=int(src.clauses[size_t(id)].size());
  if(before<=lits(replacement))continue;
  for(int id:ids)used[id]=1;
  for(const auto&c:replacement){
   std::vector<int> real;
   for(int l:c)real.push_back(l>0?sup[size_t(l-1)]:-sup[size_t(-l-1)]);
   added.push_back(std::move(real));
  }
  ++stats.committed;stats.literals_saved+=before-lits(replacement);
 }
 CNF out;out.vars=src.vars;
 for(size_t i=0;i<src.clauses.size();++i)if(!used[i])out.clauses.push_back(src.clauses[i]);
 out.clauses.insert(out.clauses.end(),added.begin(),added.end());
 stats.seconds=std::chrono::duration<double>(Clock::now()-t0).count();
 return out;
}
struct GRow {
 std::vector<uint64_t> bits,proof;
 int rhs=0;
};
static bool bit(const std::vector<uint64_t>&a,int p){return bool((a[size_t(p)>>6]>>(p&63))&1ULL);}
static void setbit(std::vector<uint64_t>&a,int p){a[size_t(p)>>6]^=1ULL<<(p&63);}
static void addrow(GRow&a,const GRow&b){
 for(size_t i=0;i<a.bits.size();++i)a.bits[i]^=b.bits[i];
 for(size_t i=0;i<a.proof.size();++i)a.proof[i]^=b.proof[i];
 a.rhs^=b.rhs;
}
struct Gauss {
 int source=0,rank=0,units=0,binary_rows=0,clauses=0;
 bool conflict=false,enabled=false;
 double seconds=0;
 std::vector<int> core_indices;
 Clauses implied;
};
static Gauss eliminate(const CNF&original,const std::vector<drnas::XorRowR2>&sources){
 auto start=Clock::now();Gauss out;out.source=int(sources.size());
 if(original.vars>2000||sources.size()>512||sources.size()<2){
  out.seconds=std::chrono::duration<double>(Clock::now()-start).count();return out;
 }
 out.enabled=true;
 const int n=original.vars;const int m=int(sources.size());
 const size_t bw=size_t(n+64)/64,pw=size_t(m+63)/64;
 std::vector<GRow> basis(size_t(n)+1);
 std::vector<uint8_t> has(size_t(n)+1,0);
 for(int eq=0;eq<m;++eq){
  GRow r;r.bits.assign(bw,0);r.proof.assign(pw,0);r.rhs=sources[size_t(eq)].rhs;
  for(int v:sources[size_t(eq)].vars)setbit(r.bits,v);
  setbit(r.proof,eq);
  while(true){
   int pivot=0;
   for(int v=1;v<=n;++v)if(bit(r.bits,v)){pivot=v;break;}
   if(!pivot){
    if(r.rhs){
     out.conflict=true;
     for(int i=0;i<m;++i)if(bit(r.proof,i))out.core_indices.push_back(i);
    }
    break;
   }
   if(!has[size_t(pivot)]){
    has[size_t(pivot)]=1;basis[size_t(pivot)]=std::move(r);
    ++out.rank;break;
   }
   addrow(r,basis[size_t(pivot)]);
  }
  if(out.conflict)break;
 }
 if(!out.conflict){
  // RREF over GF(2): short rows become *original-source-implied* CNF units/binaries.
  for(int high=n;high>=1;--high)if(has[size_t(high)])
   for(int low=1;low<high;++low)
    if(has[size_t(low)]&&bit(basis[size_t(low)].bits,high))
     addrow(basis[size_t(low)],basis[size_t(high)]);
  std::set<std::vector<int>> clauses;
  for(int p=1;p<=n;++p)if(has[size_t(p)]){
   const auto&r=basis[size_t(p)];
   std::vector<int> vs;
   for(int v=1;v<=n;++v)if(bit(r.bits,v))vs.push_back(v);
   if(vs.size()==1){
    ++out.units;
    clauses.insert({r.rhs?vs[0]:-vs[0]});
   }else if(vs.size()==2){
    ++out.binary_rows;
    const int a=vs[0],b=vs[1];
    if(r.rhs){clauses.insert({-a,-b});clauses.insert({a,b});}
    else {clauses.insert({-a,b});clauses.insert({a,-b});}
   }
  }
  for(auto c:clauses)out.implied.push_back(std::move(c));
  out.clauses=int(out.implied.size());
 }
 out.seconds=std::chrono::duration<double>(Clock::now()-start).count();
 return out;
}
static CNF source_xor(int k,int parity){
 CNF f;f.vars=k;
 for(int bits=0;bits<(1<<k);++bits)if((__builtin_popcount(unsigned(bits))&1)!=parity){
  std::vector<int> c;
  for(int v=1;v<=k;++v)c.push_back((bits>>(v-1))&1?-v:v);
  f.clauses.push_back(std::move(c));
 }
 return f;
}
static void selftest(){
 auto rules=atlas9_data::load();
 drnas::require(int(rules.size())==atlas9_data::kRuleCount,"ATLAS9 table count");
 for(auto&rule:rules){
  int k=0;for(auto&c:rule.original)for(int l:c)k=std::max(k,std::abs(l));
  drnas::require(equivalent(rule.original,rule.reduced,k),"invalid stored rule");
 }
 // Genuine XOR contradiction: same certified support with opposed parity.
 CNF a=source_xor(3,0),b=source_xor(3,1);
 a.clauses.insert(a.clauses.end(),b.clauses.begin(),b.clauses.end());
 auto s=drnas::extract_source_xors(a);
 auto g=eliminate(a,s);
 drnas::require(s.size()==2&&g.conflict&&g.core_indices.size()==2,
                "Gaussian XOR contradiction proof smoke test");
 CNF c=source_xor(3,0);
 TableStats ts;auto tab=table_reduce(c,ts);
 (void)tab;
 std::cout<<"ATLAS9_SELFTEST_PASS rules="<<rules.size()<<" XOR_unsat_core="<<g.core_indices.size()<<"\n";
}
}
int main(int argc,char**argv){
 try{
  if(argc==2&&std::string(argv[1])=="--selftest"){atlas9::selftest();return 0;}
  if(argc!=6||std::string(argv[2])!="--mode"||std::string(argv[4])!="--time"){
   std::cerr<<"usage: atlas9 FORMULA.cnf --mode A|TABLE|GF2_CORE|GAUSS|TABLE_GAUSS --time SECONDS\n";return 2;
  }
  const std::string mode=argv[3];
  drnas::require(mode=="A"||mode=="TABLE"||mode=="GF2_CORE"||mode=="GAUSS"||mode=="TABLE_GAUSS","bad arm");
  double cap=std::stod(argv[5]);
  drnas::require(cap>0&&cap<=120&&std::isfinite(cap),"bad cap");
  auto t0=drnas::Clock::now();
  const drnas::CNF orig=drnas::read_dimacs(argv[1]);
  drnas::CNF work=orig;
  atlas9::TableStats tab;
  atlas9::Gauss gauss;
  const bool use_table=mode=="TABLE"||mode=="TABLE_GAUSS";
  const bool use_gauss=mode=="GAUSS"||mode=="TABLE_GAUSS";
  const bool use_gf2=mode=="GF2_CORE"||use_gauss;
  if(use_table)work=atlas9::table_reduce(work,tab);
  if(use_gauss){
   auto certified=drnas::extract_source_xors(orig);
   gauss=atlas9::eliminate(orig,certified);
   if(!gauss.conflict)
    work.clauses.insert(work.clauses.end(),gauss.implied.begin(),gauss.implied.end());
  }
  int status=0;
  drnas::NativeCDCL solver(work.vars);
  if(!gauss.conflict){
   solver.add_cnf(work);
   if(use_gf2&&(!use_gauss||gauss.source>=4))
    solver.enable_gf2_from_original(orig);
   const double elapsed=std::chrono::duration<double>(drnas::Clock::now()-t0).count();
   if(elapsed<cap)status=solver.solve(cap-elapsed);
  }else status=20;
  if(status==10)drnas::require(solver.verify_original(orig),"SAT model not valid on original CNF");
  const auto e2e=std::chrono::duration<double>(drnas::Clock::now()-t0).count();
  const auto &st=solver.statistics();
  std::cout<<std::fixed<<std::setprecision(8)
           <<"ATLAS9_TRIAL arm="<<mode<<" status="<<(status==10?"SAT":status==20?"UNSAT":"UNKNOWN")
           <<" e2e_s="<<e2e<<" table_s="<<tab.seconds<<" table_matched="<<tab.matched
           <<" table_modules="<<tab.committed<<" table_saved_literals="<<tab.literals_saved
           <<" gauss_s="<<gauss.seconds<<" gauss_rows="<<gauss.source
           <<" gauss_rank="<<gauss.rank<<" gauss_units="<<gauss.units
           <<" gauss_binaries="<<gauss.binary_rows<<" gauss_clauses="<<gauss.clauses
           <<" gauss_conflict="<<int(gauss.conflict)
           <<" xor_source_rows="<<st.xor_source_rows<<" xor_derived_rows="<<st.xor_derived_rows
           <<" xor_implications="<<st.xor_implications<<" xor_conflicts="<<st.xor_conflicts
           <<" conflicts="<<st.conflicts<<" decisions="<<st.decisions
           <<" SAT_original_verified="<<int(status==10)
           <<" UNSAT_independent_LRAT=0 oneCPU=1\n";
  if(gauss.conflict){
   std::cout<<"ATLAS9_GF2_CORE";
   for(int i:gauss.core_indices)std::cout<<" "<<i;
   std::cout<<"\n";
  }
  if(status==10){
   std::cout<<"s SATISFIABLE\nv ";
   for(int v=1;v<=orig.vars;++v)std::cout<<(solver.assignments()[v]<0?-v:v)<<" ";
   std::cout<<"0\n";
  }else std::cout<<(status==20?"s UNSATISFIABLE\n":"s UNKNOWN\n");
  return status==10?10:status==20?20:0;
 }catch(const std::exception&e){std::cerr<<"ATLAS9_FAIL_CLOSED "<<e.what()<<"\n";return 2;}
}
