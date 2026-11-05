// DRNAS R130 precommitted adaptive structural selector, extending R129.
// Strict independent holdout; never modifies CNF. R118 handles checked GF(2) decisions.
// This component NEVER proves SAT/UNSAT and never modifies the formula.
// It only decides whether a complete XOR-heavy CNF merits running R118 GF(2).
// Otherwise it execs the identical pinned original Kissat, avoiding deep scans.
// A complete 2-4 variable XOR pattern has all 2^(k-1) clauses of one parity.
#include <algorithm>
#include <array>
#include <cerrno>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iostream>
#include <string>
#include <unordered_map>
#include <vector>
#include <unistd.h>
using namespace std;
using Key=array<int,5>;
struct H {size_t operator()(const Key&v)const noexcept{
  uint64_t h=1469598103934665603ULL;
  for(int x:v){h^=uint32_t(x);h*=1099511628211ULL;}return size_t(h);
}};
struct Result {
  bool parsed=false,trigger=false;
  int clauses=0,patterns=0,exact_xor=0,covered=0,recognized=0,connected_equations=0;
  string reason="unreadable";
  long bytes=0;
};
static bool parse_int(const string&s,int&v) {
  if(s.empty())return false;
  char*end=nullptr;errno=0;const long x=strtol(s.c_str(),&end,10);
  if(errno||!end||*end||x<-2000000000L||x>2000000000L)return false;
  v=int(x);return true;
}
static uint32_t parity(int k,int parity_bit){
  uint32_t out=0;
  for(int m=0;m<(1<<k);++m)
    if((__builtin_popcount(unsigned(m))&1)==parity_bit)out|=uint32_t(1)<<m;
  return out;
}
static Result probe(const string&input,int min_eq,int min_cover_pct) {
  Result out;
  ifstream f(input,ios::binary);
  if(!f)return out;
  f.seekg(0,ios::end);auto nbytes=f.tellg();
  if(nbytes<0){out.reason="size_unavailable";return out;}
  out.bytes=long(nbytes);
  constexpr long MAX_BYTES=8L*1024*1024; // Strict upper bound: 8 MiB, inherited input-size cap.
  if(nbytes>MAX_BYTES){out.reason="file_size_budget";return out;}
  f.seekg(0);
  unordered_map<Key,uint32_t,H> groups;
  groups.reserve(2048);
  int variables=0,expected=-1;
  bool header=false;string t;vector<int> clause;bool skip_long_clause=false;
  while(f>>t){
    if(t=="c"||t=="%"){string rest;getline(f,rest);continue;}
    if(t=="p"){
      string typ;if(header||!(f>>typ>>variables>>expected)||typ!="cnf"||
          variables<1||variables>3000000||expected<0||expected>1000000){
        out.reason="header_invalid";return out;
      }
      header=true;continue;
    }
    if(!header){out.reason="no_header";return out;}
    int x=0;
    if(!parse_int(t,x)||abs(x)>variables){out.reason="literal_invalid";return out;}
    if(x){if(clause.size()<5)clause.push_back(x);else skip_long_clause=true;}
    else{
      out.clauses++;
      if(out.clauses>expected){out.reason="clause_overflow";return out;}
      if(!skip_long_clause&&clause.size()>=2&&clause.size()<=4){
        sort(clause.begin(),clause.end(),[](int a,int b){
          return abs(a)==abs(b)?a<b:abs(a)<abs(b);
        });
        bool unique=true;
        for(size_t i=1;i<clause.size();++i)
          if(abs(clause[i-1])==abs(clause[i]))unique=false;
        if(unique){
          Key key{};int mask=0;key[0]=int(clause.size());
          for(size_t i=0;i<clause.size();++i){
            key[i+1]=abs(clause[i]);if(clause[i]<0)mask|=1<<i;
          }
          groups[key]|=uint32_t(1)<<mask;
          if(groups.size()>50000){out.reason="group_budget";return out;}
          out.recognized++;
        }
      }
      clause.clear();skip_long_clause=false;
    }
  }
  if(!header||!clause.empty()||skip_long_clause||out.clauses!=expected){
    out.reason="incomplete_dimacs";return out;
  }
  out.parsed=true;out.patterns=int(groups.size());
  vector<Key> eq_keys;
  eq_keys.reserve(groups.size());
  for(const auto&pair:groups){
    const int k=pair.first[0];const uint32_t mask=pair.second;
    const uint32_t p=parity(k,0),q=parity(k,1);
    if((mask&p)==p){out.exact_xor++;out.covered+=1<<(k-1);eq_keys.push_back(pair.first);}
    if((mask&q)==q){out.exact_xor++;out.covered+=1<<(k-1);eq_keys.push_back(pair.first);}
  }
  // Causal structural signal: size (number of XOR equations) of the largest
  // connected component of the verified XOR hypergraph. No solver timing enters.
  if(!eq_keys.empty()){
    vector<int> parent(size_t(variables)+1);
    for(int i=0;i<=variables;++i)parent[size_t(i)]=i;
    auto find_root=[&](int v){
      while(parent[size_t(v)]!=v){
        parent[size_t(v)]=parent[size_t(parent[size_t(v)])];
        v=parent[size_t(v)];
      }
      return v;
    };
    for(const auto&key:eq_keys){
      int r=find_root(key[1]);
      for(int j=2;j<=key[0];++j){
        int s=find_root(key[j]);
        if(r!=s)parent[size_t(s)]=r;
      }
    }
    unordered_map<int,int> totals;
    for(const auto&key:eq_keys){
      int n=++totals[find_root(key[1])];
      out.connected_equations=max(out.connected_equations,n);
    }
  }
  // Precommitted strict rule: only near-pure complete XOR CNFs.
  out.trigger=(out.exact_xor>=min_eq && out.clauses>=4 &&
               100LL*out.covered>=int64_t(min_cover_pct)*out.clauses);
  out.reason=out.trigger?"high_complete_xor_coverage":"insufficient_complete_xor";
  return out;
}
int main(int argc,char**argv){
  if(argc!=5 && !(argc==6&&string(argv[5])=="--probe-only")){
    cerr<<"Usage: r128_filter SOURCE.cnf R118_BIN KISSAT_BIN POLICY [--probe-only]\n";
    return 2;
  }
  string policy=argv[4];
  int eq=0,cover=0;
  if(policy=="q8_90"){eq=8;cover=90;}
  else if(policy=="q4_60"){eq=4;cover=60;}
  else if(policy=="q2_25"){eq=2;cover=25;}
  else if(policy=="q1_0"){eq=1;cover=0;}
  else if(policy=="adaptive"){eq=1;cover=0;}
  else {cerr<<"R130_INVALID_FROZEN_POLICY\\n";return 2;}
  Result s=probe(argv[1],eq,cover);
  if(policy=="adaptive" && s.parsed){
    // Strong pure-XOR signal OR a nontrivial connected XOR component.
    // Both are deterministic, bounded and frozen before the prospective run.
    const bool pure=(s.exact_xor>=8 && s.clauses>=4 &&
                     100LL*s.covered>=90LL*s.clauses);
    const bool connected=(s.exact_xor>=4 && s.connected_equations>=4 &&
                          s.clauses>=4 && 100LL*s.covered>=10LL*s.clauses);
    s.trigger=(pure||connected);
    s.reason=pure?"adaptive_pure_xor":connected?"adaptive_connected_xor":"adaptive_structural_fallback";
  }
  cout<<"c R130_SELECTOR policy="<<policy<<" route="<<(s.trigger?"GF2":"KISSAT")
      <<" reason="<<s.reason<<" bytes="<<s.bytes
      <<" clauses="<<s.clauses<<" xor_equations="<<s.exact_xor
      <<" covered_clauses="<<s.covered<<" connected_equations="<<s.connected_equations<<" patterns="<<s.patterns
      <<" parsed="<<(s.parsed?1:0)<<"\n"<<flush;
  if(argc==6)return 0;
  if(s.trigger){
    char*args[]={argv[2],argv[1],argv[3],nullptr};
    execv(args[0],args);
  } else{
    char*args[]={argv[3],argv[1],nullptr};
    execv(args[0],args);
  }
  cerr<<"R130_EXEC_FAILURE "<<strerror(errno)<<"\n";
  return 78;
}
