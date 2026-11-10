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
namespace arl1 {
using drnas::CNF;
using drnas::Clock;
struct Result{
 int vars=0,clauses=0,unit=0,binary=0,ternary=0,longer=0;
 int pairs=0,pivots=0,taut=0,derived=0,accepted=0;
 int gate_hits=0,gate_scanned=0;
 std::string decision="none",reason="none";
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
static CNF first_look(const CNF& f,Result& r,double overall_cap,Clock::time_point start) {
 CNF extended=f;
 r.vars=f.vars;r.clauses=int(f.clauses.size());
 const auto s0=Clock::now();
 std::vector<int> ternary_ids;
 ternary_ids.reserve(std::min<size_t>(f.clauses.size(),1024));
 std::unordered_set<uint64_t> original_binary;
 // The fingerprint is a single scan of ORIGINAL clauses, no structural mutation.
 for(size_t i=0;i<f.clauses.size();++i){
  const auto& c=f.clauses[i];
  if(c.size()==1)++r.unit;
  else if(c.size()==2){++r.binary;
    auto v=normalized(c);
    if(v.size()==2)original_binary.insert(key2(v[0],v[1],f.vars));}
  else if(c.size()==3){++r.ternary;if(ternary_ids.size()<1024)ternary_ids.push_back(int(i));}
  else if(c.size()>3)++r.longer;
 }
 r.scan_s=std::chrono::duration<double>(Clock::now()-s0).count();
 // The decision to launch a probe follows FIRST LOOK only.
 if(f.vars<=24){r.decision="fallback";r.reason="tiny_input_skip_probe";return extended;}
 if(ternary_ids.size()<2){r.decision="fallback";r.reason="no_ternary_pairs";return extended;}
 if(r.scan_s>=std::min(0.001,overall_cap*0.01)){
  r.decision="fallback";r.reason="scan_budget_exceeded";return extended;
 }
 // ARL1-E: exact signed-pair opportunity gate and direct proof construction.
 // Each triple contributes 3 keys: (signed pair, abs(third)).
 // Opposite third signs on the same key give an exact binary resolvent.
 // The gate is NOT a Bloom filter: no false-positive collisions are accepted.
 // Only a single budgeted scan is performed, with no repeated probe.
 const auto p0=Clock::now();
 const double probe_budget=std::min(0.00025,overall_cap*0.002);
 struct PairKey {
  int a,b,x;
  bool operator==(const PairKey& o) const {return a==o.a&&b==o.b&&x==o.x;}
 };
 struct PairHash {
  size_t operator()(const PairKey& k) const {
   uint64_t h=uint32_t(k.a+f.vars+1);
   h=h*0x9e3779b185ebca87ULL+uint32_t(k.b+f.vars+1);
   h=h*0xc2b2ae3d27d4eb4fULL+uint32_t(k.x);
   h^=h>>33;h*=0xff51afd7ed558ccdULL;h^=h>>33;
   return size_t(h);
  }
 };
 std::unordered_map<PairKey,uint8_t,PairHash> polarity;
 std::unordered_set<uint64_t> added;
 bool over=false;
 for(int cid:ternary_ids){
  if(std::chrono::duration<double>(Clock::now()-p0).count()>probe_budget){over=true;break;}
  const auto& c=f.clauses[size_t(cid)];
  if(c.size()!=3)continue;
  for(int k=0;k<3;++k){
   int a=c[(k+1)%3],b=c[(k+2)%3],x=c[k];
   if(a>b)std::swap(a,b);
   if(a==-b)continue;
   ++r.gate_scanned;
   const PairKey key{a,b,std::abs(x)};
   const uint8_t sign=x>0?1:2;
   auto& flags=polarity[key];
   if((flags & (sign==1?2:1))!=0){
    ++r.gate_hits;++r.pivots;
    const uint64_t binary_key=key2(a,b,f.vars);
    if(!original_binary.count(binary_key)&&!added.count(binary_key)){
     ++r.derived;
     // Original ternary parents (a|b|x),(a|b|!x) imply (a|b).
     added.insert(binary_key);
     extended.clauses.push_back({a,b});
     ++r.accepted;
     if(r.accepted>=4){over=true;break;}
    }
   }
   flags|=sign;
  }
  if(over)break;
 }
 r.pairs=r.gate_scanned;
 r.probe_s=std::chrono::duration<double>(Clock::now()-p0).count();
 // Mandatory decision immediately after first and ONLY probe.
 if(r.accepted>0){r.decision="commit";r.reason="exact_direct_resolvent";}
 else {r.decision="sleep";r.reason="no_new_exact_binary";}
 return extended;
}
}
int main(int argc,char**argv) {
 try{
  if(argc!=6||std::string(argv[2])!="--mode"||std::string(argv[4])!="--time"){
   std::cerr<<"usage: arl1e FILE --mode A|ARL1E --time SECONDS\n";return 2;
  }
  const std::string arm=argv[3];drnas::require(arm=="A"||arm=="ARL1E","bad mode");
  const double cap=std::stod(argv[5]);drnas::require(cap>0&&cap<=3600,"bad cap");
  auto start=drnas::Clock::now();
  const drnas::CNF original=drnas::read_dimacs(argv[1]);
  arl1::Result p;drnas::CNF working=original;
  if(arm=="ARL1E")working=arl1::first_look(original,p,cap,start);
  else {p.decision="baseline";p.reason="baseline_no_scan";}
  drnas::NativeCDCL solver(working.vars);
  solver.add_cnf(working);
  const double elapsed=std::chrono::duration<double>(drnas::Clock::now()-start).count();
  const int status=elapsed<cap?solver.solve(cap-elapsed):0;
  if(status==10)drnas::require(solver.verify_original(original),"SAT witness failed ORIGINAL CNF");
  const auto e2e=std::chrono::duration<double>(drnas::Clock::now()-start).count();
  const auto& st=solver.statistics();
  std::cout<<std::fixed<<std::setprecision(8)
           <<"ARL1E_TRIAL arm="<<arm<<" status="<<(status==10?"SAT":status==20?"UNSAT":"UNKNOWN")
           <<" e2e_s="<<e2e<<" look_s="<<p.scan_s<<" probe_s="<<p.probe_s
           <<" vars="<<original.vars<<" original_clauses="<<original.clauses.size()
           <<" final_clauses="<<working.clauses.size()
           <<" unit="<<p.unit<<" binary="<<p.binary<<" ternary="<<p.ternary
           <<" gate_hits="<<p.gate_hits<<" gate_scanned="<<p.gate_scanned<<" pairs="<<p.pairs<<" pivots="<<p.pivots<<" derived="<<p.derived
           <<" accepted="<<p.accepted<<" decision="<<p.decision<<" reason="<<p.reason
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
 }catch(const std::exception& e){std::cerr<<"ARL1E_ERROR "<<e.what()<<"\n";return 2;}
}
