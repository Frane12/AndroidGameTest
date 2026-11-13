// R153: Certified GF(2) unit bridge, extending frozen R28; no modifications to R28.
// Source original: experiments/drnas_v16/r28_exact_gf2.cpp (R115 frozen).
// Only source-implied unit clauses may join certified complete XOR equations.
// DRNAS SAT R153 (R28 + certified units): exact CNF parity recovery + GF(2) Gaussian elimination.
// Research prototype, not a new SAT algorithm. Never infer answer from a
// partial pattern. On mixed formulas, prove UNSAT only if XOR subset itself
// is contradictory; otherwise exec the pinned unmodified Kissat baseline.
// Native proof traces permit independent verification of XOR UNSAT claims.
#include <algorithm>
#include <sys/resource.h>
#include <numeric>
#include <cmath>
#include <array>
#include <chrono>
#include <cerrno>
#include <cstdint>
#include <cstring>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <limits>
#include <map>
#include <sstream>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>
#include <unistd.h>
using namespace std;

struct Pattern {
  vector<int> vars;
  uint64_t masks=0, recognized=0;
  array<uint32_t,64> frequency{}; // exact coverage, including duplicate source clauses
};
struct XORKey {
  array<int,6> vars{};
  uint8_t k=0;
  bool operator==(const XORKey &o) const { return k==o.k && vars==o.vars; }
};
struct XORKeyHash {
  size_t operator()(const XORKey &x) const {
    uint64_t h=1469598103934665603ULL;
    for(int i=0;i<x.k;i++) {
      h^=uint64_t(x.vars[i])+0x9e3779b97f4a7c15ULL;
      h*=1099511628211ULL;
    }
    return size_t(h ^ uint64_t(x.k));
  }
};
struct Equation {
  vector<int> vars;
  int rhs=0;
};
struct Row {
  vector<uint64_t> bits, proof;
  int rhs=0;
  bool valid=false;
};
static void fail(const string& msg) {
  cerr << "R28_FATAL " << msg << "\n";
  exit(78);
}
static bool bit(const vector<uint64_t>& v,int x) {
  return !!(v[size_t(x)>>6] & (uint64_t(1) << (x&63)));
}
static void flip(vector<uint64_t>& v,int x) {
  v[size_t(x)>>6] ^= (uint64_t(1) << (x&63));
}
static int lowest(const vector<uint64_t>& v) {
  for(size_t w=0;w<v.size();w++)
    if(v[w]) return int(w*64 + __builtin_ctzll(v[w]));
  return 0;
}
static void add(Row &a,const Row &b) {
  for(size_t i=0;i<a.bits.size();i++)a.bits[i]^=b.bits[i];
  for(size_t i=0;i<a.proof.size();i++)a.proof[i]^=b.proof[i];
  a.rhs^=b.rhs;
}
static const auto r153_start=chrono::steady_clock::now();
static long long r153_elapsed_us() {
  return chrono::duration_cast<chrono::microseconds>(chrono::steady_clock::now()-r153_start).count();
}
static void r153_trace_decision(const char* outcome,int total,int covered,int units) {
  cout<<"c R153_DECISION_US "<<r153_elapsed_us()
      <<" outcome="<<outcome<<" clauses="<<total
      <<" covered="<<covered<<" units="<<units<<"\n";
}
static uint64_t parity_mask(int k,int bitparity) {
  uint64_t s=0;
  for(int mask=0;mask<(1<<k);mask++)
    if((__builtin_popcount(unsigned(mask))&1)==bitparity)
      s|=uint64_t(1)<<mask;
  return s;
}
static bool read_cnf(const string& filename,int &n,vector<vector<int>>& clauses) {
  ifstream in(filename,ios::binary);
  if(!in)return false;
  in.seekg(0,ios::end);
  auto size=in.tellg();
  if(size<0 || size>64*1024*1024)return false;
  in.seekg(0);
  string t;
  bool header=false;
  int declared=-1;
  vector<int> clause;
  while(in>>t) {
    if(t=="c" || t=="%"){string rest;getline(in,rest);continue;}
    if(t=="p") {
      string kind;
      if(header || !(in>>kind>>n>>declared) || kind!="cnf" || n<1 ||
         n>1000000 || declared<0 || declared>1000000)return false;
      header=true;
      continue;
    }
    if(!header)return false;
    char* end=nullptr;
    errno=0;
    long raw=strtol(t.c_str(),&end,10);
    if(errno || !end || *end || raw < -n || raw>n)return false;
    if(raw) {
      if(clause.size()>10000)return false;
      clause.push_back(int(raw));
    }else {
      clauses.push_back(clause);
      clause.clear();
      if(int(clauses.size())>declared)return false;
    }
  }
  return header && clause.empty() && int(clauses.size())==declared;
}

struct Component {uint64_t vars=0, equations=0;};
int main(int argc,char** argv) {
  if(argc!=2){cerr<<"expected input CNF\n";return 2;}
  auto begin=chrono::steady_clock::now();
  int n=0; vector<vector<int>> clauses;
  if(!read_cnf(argv[1],n,clauses)){cerr<<"invalid CNF or diagnostic resource limits\n";return 3;}
  auto parsed=chrono::steady_clock::now();
  unordered_map<XORKey,Pattern,XORKeyHash> groups;
  groups.max_load_factor(0.8f);
  groups.reserve(min(size_t(32768),clauses.size()/4+1));
  vector<Equation> units;
  units.reserve(min(size_t(3000),clauses.size()/8+1));
  for(const auto& clause:clauses) {
    const int k=int(clause.size());
    if(k==1){
      const int lit=clause.front();
      units.push_back({{abs(lit)},lit>0?1:0});
      continue;
    }
    if(k<2 || k>6)continue;
    array<pair<int,bool>,6> lit{};
    for(int j=0;j<k;j++)lit[size_t(j)]={abs(clause[size_t(j)]),clause[size_t(j)]<0};
    sort(lit.begin(),lit.begin()+k);
    bool unique=true;
    for(int j=1;j<k;j++)if(lit[size_t(j-1)].first==lit[size_t(j)].first)unique=false;
    if(!unique)continue;
    XORKey key;key.k=uint8_t(k);
    int mask=0;
    for(int j=0;j<k;j++){
      key.vars[size_t(j)]=lit[size_t(j)].first;
      if(lit[size_t(j)].second)mask|=1<<j;
    }
    Pattern& p=groups[key];
    if(p.vars.empty())p.vars.assign(key.vars.begin(),key.vars.begin()+k);
    p.masks|=uint64_t(1)<<mask;
    p.frequency[size_t(mask)]++;
  }

  vector<Equation> eqs;
  uint64_t covered=0,blocks=0;
  uint64_t widths[7]={};
  for(auto& kv:groups){
    Pattern &p=kv.second;int k=int(p.vars.size());
    uint64_t even=parity_mask(k,0),odd=parity_mask(k,1);
    if((p.masks&even)==even){eqs.push_back({p.vars,1});blocks++;widths[k]++;p.recognized|=even;}
    if((p.masks&odd)==odd){eqs.push_back({p.vars,0});blocks++;widths[k]++;p.recognized|=odd;}
    uint64_t found=p.recognized;
    while(found){unsigned m=unsigned(__builtin_ctzll(found));covered+=p.frequency[size_t(m)];found&=found-1;}
  }
  covered+=units.size();
  eqs.insert(eqs.end(),units.begin(),units.end());
  vector<int> parent(size_t(n)+1),sz(size_t(n)+1,1); iota(parent.begin(),parent.end(),0);
  vector<uint8_t> active(size_t(n)+1,0);
  auto root=[&](int x){while(parent[size_t(x)]!=x){parent[size_t(x)]=parent[size_t(parent[size_t(x)])];x=parent[size_t(x)];}return x;};
  for(const auto& e:eqs){
    for(int v:e.vars)active[size_t(v)]=1;
    int first=e.vars[0];
    for(size_t i=1;i<e.vars.size();i++){
      int a=root(first),b=root(e.vars[i]);
      if(a!=b){if(sz[size_t(a)]<sz[size_t(b)])swap(a,b);parent[size_t(b)]=a;sz[size_t(a)]+=sz[size_t(b)];}
    }
  }
  unordered_map<int,Component> comps;
  uint64_t activevars=0;
  for(int v=1;v<=n;v++)if(active[size_t(v)]){comps[root(v)].vars++;activevars++;}
  for(const auto& e:eqs)comps[root(e.vars[0])].equations++;
  vector<Component> ordered;
  uint64_t coefficient_bytes=0,proof_bytes=0, largest_vars=0,largest_eqs=0;
  for(const auto& item:comps){
    auto c=item.second;ordered.push_back(c);largest_vars=max(largest_vars,c.vars);largest_eqs=max(largest_eqs,c.equations);
    uint64_t rankbound=min(c.vars,c.equations);
    coefficient_bytes+=rankbound*((c.vars+63)/64)*8;
    proof_bytes+=rankbound*((c.equations+63)/64)*8;
  }
  sort(ordered.begin(),ordered.end(),[](const Component&a,const Component&b){return a.vars>b.vars;});
  auto done=chrono::steady_clock::now();
  struct rusage usage{};getrusage(RUSAGE_SELF,&usage);
  double parse_s=chrono::duration<double>(parsed-begin).count();
  double total_s=chrono::duration<double>(done-begin).count();
  cout<<"{\"vars\":"<<n<<",\"clauses\":"<<clauses.size()
      <<",\"xor_blocks\":"<<blocks<<",\"units\":"<<units.size()
      <<",\"equations_with_units\":"<<eqs.size()<<",\"covered_clauses\":"<<covered
      <<",\"pattern_groups\":"<<groups.size()<<",\"active_variables\":"<<activevars
      <<",\"components\":"<<comps.size()<<",\"largest_component_variables\":"<<largest_vars
      <<",\"largest_component_equations\":"<<largest_eqs
      <<",\"estimate_coefficient_basis_bytes\":"<<coefficient_bytes
      <<",\"estimate_proof_basis_bytes\":"<<proof_bytes
      <<",\"parse_s\":"<<parse_s<<",\"total_s\":"<<total_s
      <<",\"cpu_s\":"<<(usage.ru_utime.tv_sec+usage.ru_utime.tv_usec/1000000.0+usage.ru_stime.tv_sec+usage.ru_stime.tv_usec/1000000.0)
      <<",\"peak_rss_kib\":"<<usage.ru_maxrss<<",\"widths\":{";
  for(int k=2;k<=6;k++){if(k>2)cout<<",";cout<<char(34)<<k<<char(34)<<":"<<widths[k];}
  cout<<"},\"largest_components\":[";
  for(size_t i=0;i<min(size_t(10),ordered.size());i++){
    if(i)cout<<",";
    cout<<"{\"vars\":"<<ordered[i].vars<<",\"equations\":"<<ordered[i].equations<<"}";
  }
  cout<<"]}\n";
  return 0;
}
