// R153: Certified GF(2) unit bridge, extending frozen R28; no modifications to R28.
// Source original: experiments/drnas_v16/r28_exact_gf2.cpp (R115 frozen).
// Only source-implied unit clauses may join certified complete XOR equations.
// DRNAS SAT R153 (R28 + certified units): exact CNF parity recovery + GF(2) Gaussian elimination.
// Research prototype, not a new SAT algorithm. Never infer answer from a
// partial pattern. On mixed formulas, prove UNSAT only if XOR subset itself
// is contradictory; otherwise exec the pinned unmodified Kissat baseline.
// Native proof traces permit independent verification of XOR UNSAT claims.
#include <algorithm>
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
  if(size<0 || size>12*1024*1024)return false;
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
         n>3000 || declared<0 || declared>150000)return false;
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
static bool valid_model(const vector<vector<int>>& clauses,const vector<int>& truth) {
  for(const auto& cl:clauses){
    bool sat=false;
    for(int x:cl)
      if((x>0)==bool(truth[abs(x)])){sat=true;break;}
    if(!sat)return false;
  }
  return true;
}
static void print_equations(const vector<Equation>& equations) {
  for(size_t i=0;i<equations.size();i++){
    cout << "c R28_EQ id=" << i << " rhs=" << equations[i].rhs << " vars=";
    for(size_t j=0;j<equations[i].vars.size();j++){
      if(j)cout<<",";
      cout<<equations[i].vars[j];
    }
    cout<<"\n";
  }
}
static int fallback(const string& filename,const string& kissat,
                    const string& reason,int total,int covered,int neq,bool classify) {
  r153_trace_decision("fallback",total,covered,0);
  cout<<"c R28_ROUTE fallback reason="<<reason<<" clauses="<<total
      <<" covered="<<covered<<" equations="<<neq<<"\n"<<flush;
  if(classify)return 0;
  char* args[]={const_cast<char*>(kissat.c_str()),
                const_cast<char*>(filename.c_str()),nullptr};
  execv(args[0],args);
  cerr<<"R28_EXEC_FAILURE "<<strerror(errno)<<"\n";
  return 77;
}
int main(int argc,char** argv){
  if(argc!=3 && !(argc==4 && string(argv[3])=="--classify-only")){
    cerr<<"Usage: r28_gf2 INPUT KISSAT [--classify-only]\n";return 2;
  }
  const string filename=argv[1],kissat=argv[2];
  const bool classify=argc==4;
  int n=0;
  vector<vector<int>> clauses;
  if(!read_cnf(filename,n,clauses))
    return fallback(filename,kissat,"invalid_or_over_limit",0,0,0,classify);
  // R153 speed improvement: fixed-size 6-variable keys, hash lookup,
  // one-pass exact sign-mask multiplicity; no per-clause string keys,
  // no second lookup pass, no changes to the source implications.
  unordered_map<XORKey,Pattern,XORKeyHash> groups;
  groups.max_load_factor(0.8f);
  groups.reserve(min(size_t(32768),clauses.size()/4+1));
  vector<Equation> units;
  units.reserve(min(size_t(3000),clauses.size()/8+1));
  int eligible=0;
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
    eligible++;
  }
  vector<Equation> eqs;
  int blocks=0;
  int covered=0;
  for(auto& kv:groups){
    Pattern &p=kv.second;
    int k=int(p.vars.size());
    uint64_t even=parity_mask(k,0),odd=parity_mask(k,1);
    if((p.masks&even)==even){
      eqs.push_back({p.vars,1});blocks++;
      p.recognized|=even;
    }
    if((p.masks&odd)==odd){
      eqs.push_back({p.vars,0});blocks++;
      p.recognized|=odd;
    }
    uint64_t found=p.recognized;
    while(found){
      unsigned m=unsigned(__builtin_ctzll(found));
      covered+=int(p.frequency[size_t(m)]);
      found&=found-1;
    }
  }
  // R153 certified unit bridge: clauses of length one are *exact* GF(2)
  // equations x=1 (positive unit) or x=0 (negative unit).  No inference
  // from incomplete XOR patterns is allowed.  A contradictory subset gives
  // a fully replayable UNSAT proof; complete coverage permits SAT witness.
  // Fail closed to unchanged Kissat whenever any clause remains uncovered.
  if(blocks==0)
    return fallback(filename,kissat,"no_verified_complete_xor",int(clauses.size()),covered,0,classify);
  const int unit_count=int(units.size());
  // Strict equation budget. If too many source units, do not risk
  // expensive elimination or unbounded proof traces: use plain Kissat.
  if(eqs.size()+units.size()>3000)
    return fallback(filename,kissat,"equation_limit",int(clauses.size()),covered,int(eqs.size()+units.size()),classify);
  eqs.insert(eqs.end(),units.begin(),units.end());
  covered+=unit_count;
  if(eqs.size()>3000)
    return fallback(filename,kissat,"equation_limit",int(clauses.size()),covered,int(eqs.size()),classify);
  const size_t words=size_t(n/64+1), proof_words=(eqs.size()+63)/64;
  vector<Row> basis(size_t(n)+1);
  int rank=0;
  for(size_t idx=0;idx<eqs.size();idx++){
    Row row;
    row.bits.assign(words,0);
    row.proof.assign(proof_words,0);
    row.rhs=eqs[idx].rhs;
    for(int x:eqs[idx].vars)flip(row.bits,x);
    row.proof[idx>>6]|=uint64_t(1)<<(idx&63);
    for(;;){
      int p=lowest(row.bits);
      if(p==0){
        if(row.rhs){
          r153_trace_decision("gf2_unsat",int(clauses.size()),covered,unit_count);
          cout<<"c R28_ROUTE certified_xor_contradiction equations="<<eqs.size()
              <<" rank="<<rank<<" clauses="<<clauses.size()
              <<" covered="<<covered<<"\n";
          print_equations(eqs);
          cout<<"c R28_UNSAT_CERT ids=";
          bool first=true;
          for(size_t i=0;i<eqs.size();i++)if(bit(row.proof,int(i))){
            if(!first)cout<<",";
            cout<<i;first=false;
          }
          cout<<"\ns UNSATISFIABLE\n"<<flush;
          return classify?0:20;
        }
        break;
      }
      if(basis[p].valid)add(row,basis[p]);
      else {row.valid=true;basis[p]=move(row);rank++;break;}
    }
  }
  if(covered!=int(clauses.size()))
    return fallback(filename,kissat,"mixed_consistent_xor",int(clauses.size()),covered,int(eqs.size()),classify);
  // Every original clause is now backed by a mathematically equivalent,
  // complete parity block. Assign all free variables false.
  vector<int> truth(size_t(n)+1,0);
  for(int p=n;p>=1;p--)if(basis[p].valid){
    int value=basis[p].rhs;
    for(int w=p+1;w<=n;w++)if(bit(basis[p].bits,w))value^=truth[w];
    truth[p]=value;
  }
  if(!valid_model(clauses,truth))
    fail("GF2_SAT_WITNESS_MISMATCH");
  r153_trace_decision("gf2_sat",int(clauses.size()),covered,unit_count);
  cout<<"c R28_ROUTE certified_pure_xor_sat rank="<<rank
      <<" equations="<<eqs.size()<<" clauses="<<clauses.size()
      <<" covered="<<covered<<"\n";
  if(classify)return 0;
  cout<<"s SATISFIABLE\n";
  for(int v=1;v<=n;v++){
    if((v-1)%20==0)cout<<"v ";
    cout<<(truth[v]?v:-v)<<" ";
    if(v%20==0)cout<<"0\n";
  }
  if(n%20!=0)cout<<"0\n";
  cout<<flush;
  return 10;
}
