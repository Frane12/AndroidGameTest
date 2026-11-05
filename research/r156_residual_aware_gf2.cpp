// R156: residual-aware certified GF(2) consequences (1..12 variables) to mixed CNF.
// Includes bounded two-row recombination and exact Tseitin XOR for width >=5.
// On source-related equations, only audit-verified GF2 implications are injected.
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
#include <cstdio>
#include <fcntl.h>
#include <sys/stat.h>
#include <iostream>
#include <limits>
#include <map>
#include <sstream>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <cmath>
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

// R155 research-only mixed-CNF bridge. Gaussian rows are XOR linear
// combinations of source-certified complete parity blocks and original units.
// Only equations with 1..4 variables are encoded as logically ENTAILED CNF.
// Original file never changes. /proc/self/fd points to an unlinked temporary
// file so OS cleans up even if solver is killed by benchmark wall timeout.
struct R155ShortEq { vector<int> vars; int rhs=0; };

static string r156_identity(const vector<int>&vs,int rhs){
  string s=to_string(rhs)+":";
  for(int v:vs){s+=to_string(v);s+=",";}
  return s;
}
struct R156Candidate {
  R155ShortEq eq;
  int clauses=0,aux=0;
  double score=0.0;
};
static vector<R155ShortEq> r156_residual_consequences(
    const vector<Row>&basis,int n,const vector<Equation>&source,
    const vector<vector<int>>&clauses,
    const unordered_map<XORKey,Pattern,XORKeyHash>&groups){
  // Measure relevance to CNF clauses not already represented by the
  // source-certified XOR equations. Original unit clauses are not residual.
  vector<int> freq(size_t(n)+1,0);
  for(const auto&cl:clauses){
    const int k=int(cl.size());
    if(k==1)continue;
    bool covered=false;
    if(k>=2 && k<=6){
      array<pair<int,bool>,6> items{};
      for(int i=0;i<k;i++)items[size_t(i)]={abs(cl[size_t(i)]),cl[size_t(i)]<0};
      sort(items.begin(),items.begin()+k);
      bool unique=true;
      for(int i=1;i<k;i++)if(items[size_t(i-1)].first==items[size_t(i)].first)unique=false;
      if(unique){
        XORKey key;key.k=uint8_t(k);
        int mask=0;
        for(int i=0;i<k;i++){
          key.vars[size_t(i)]=items[size_t(i)].first;
          if(items[size_t(i)].second)mask|=1<<i;
        }
        auto it=groups.find(key);
        if(it!=groups.end())covered=bool(it->second.recognized&(uint64_t(1)<<mask));
      }
    }
    if(!covered)for(int lit:cl){
      if(abs(lit)<=n && abs(lit)>0)freq[size_t(abs(lit))]++;
    }
  }
  unordered_set<string> source_ids,seen;
  source_ids.reserve(source.size()*2+1);
  for(const auto&e:source)source_ids.insert(r156_identity(e.vars,e.rhs));
  vector<Row> rref(size_t(n)+1);
  vector<Row> pair_seeds;
  vector<R156Candidate> candidates;
  candidates.reserve(512);
  auto consider=[&](const Row&row,bool pairwise){
    vector<int> vs;
    for(size_t w=0;w<row.bits.size();w++){
      uint64_t bits=row.bits[w];
      while(bits){
        int var=int(w*64+__builtin_ctzll(bits));
        if(var>=1 && var<=n)vs.push_back(var);
        if(vs.size()>12)return;
        bits&=bits-1;
      }
    }
    const int k=int(vs.size());
    if(k<1 || k>12)return;
    string key=r156_identity(vs,row.rhs);
    if(source_ids.count(key) || !seen.insert(key).second)return;
    double impact=0;
    for(int v:vs)impact+=min(freq[size_t(v)],200);
    if(impact<=0)return;
    const int clauses_add=k<=4?(1<<(k-1)):(4*(k-2)+2);
    const int aux=k<=4?0:k-2;
    double score=impact / double((k+1)*(k+1)) / double(1.0+0.05*clauses_add);
    if(pairwise)score*=1.03; // near-ties prefer source-different consequences
    candidates.push_back({{move(vs),row.rhs},clauses_add,aux,score});
  };
  for(int p=n;p>=1;p--){
    if(!basis[size_t(p)].valid)continue;
    Row r=basis[size_t(p)];
    for(int q=p+1;q<=n;q++)if(rref[size_t(q)].valid && bit(r.bits,q))
      add(r,rref[size_t(q)]);
    rref[size_t(p)]=move(r);
    const Row& z=rref[size_t(p)];
    consider(z,false);
    int width=0;
    for(uint64_t word:z.bits)width+=__builtin_popcountll(word);
    if(width<=20 && pair_seeds.size()<96)pair_seeds.push_back(z);
  }
  // Bounded pair combinations uncover low-weight XOR consequences that a
  // reduced basis alone cannot expose. Every such row stays in the same
  // source GF(2) span. Never enumerate more than 4560 combinations.
  for(size_t i=0;i<pair_seeds.size();i++)
    for(size_t j=i+1;j<pair_seeds.size();j++){
      Row a=pair_seeds[i];
      add(a,pair_seeds[j]);
      consider(a,true);
    }
  sort(candidates.begin(),candidates.end(),[](const R156Candidate&a,const R156Candidate&b){
    if(a.score!=b.score)return a.score>b.score;
    if(a.eq.vars.size()!=b.eq.vars.size())return a.eq.vars.size()<b.eq.vars.size();
    return a.eq.vars<b.eq.vars;
  });
  vector<R155ShortEq> selected;
  int added_clauses=0,aux_count=0;
  for(const auto&c:candidates){
    if(selected.size()>=48)break;
    if(added_clauses+c.clauses>384 || aux_count+c.aux>120)continue;
    selected.push_back(c.eq);
    added_clauses+=c.clauses;
    aux_count+=c.aux;
  }
  cout<<"c R156_SELECTION candidate_count="<<candidates.size()
      <<" selected="<<selected.size()
      <<" injected_clauses="<<added_clauses
      <<" auxiliary_vars="<<aux_count
      <<" detector_us="<<r153_elapsed_us()<<"\n"<<flush;
  return selected;
}
static int r156_exec_augmented(const string&kissat,int n,
      const vector<vector<int>>&clauses,const vector<R155ShortEq>&extra){
  if(extra.empty())return 79;
  size_t additions=0,auxiliary=0;
  for(const auto&e:extra){
    const int k=int(e.vars.size());
    additions+=k<=4?size_t(1)<<(k-1):size_t(4*(k-2)+2);
    auxiliary+=k<=4?0:size_t(k-2);
  }
  char path[]="/tmp/r156-gf2-XXXXXX";
  int fd=mkstemp(path);
  if(fd<0)return 79;
  unlink(path);
  FILE*file=fdopen(fd,"w+");
  if(!file){close(fd);return 79;}
  bool ok=fprintf(file,"p cnf %zu %zu\n",size_t(n)+auxiliary,clauses.size()+additions)>0;
  auto emit=[&](const vector<int>&vs,int rhs){
    const int k=int(vs.size());
    for(int mask=0;mask<(1<<k);mask++){
      if((__builtin_popcount(unsigned(mask))&1)!=(1-rhs))continue;
      for(int i=0;i<k;i++)
        if(fprintf(file,"%d ",(mask&(1<<i)) ? -vs[size_t(i)] : vs[size_t(i)])<0)
          ok=false;
      if(fprintf(file,"0\n")<0)ok=false;
    }
  };
  for(const auto&cl:clauses){
    for(int v:cl)if(fprintf(file,"%d ",v)<0)ok=false;
    if(fprintf(file,"0\n")<0)ok=false;
  }
  int next_var=n;
  for(const auto&e:extra){
    const int k=int(e.vars.size());
    if(k<=4){emit(e.vars,e.rhs);continue;}
    int left=e.vars[0];
    for(int j=1;j<k-1;j++){
      int new_var=++next_var;
      emit({left,e.vars[size_t(j)],new_var},0); // z=left XOR x_j
      left=new_var;
    }
    emit({left,e.vars.back()},e.rhs);
  }
  if(size_t(next_var)!=size_t(n)+auxiliary)ok=false;
  if(fflush(file)!=0 || ferror(file))ok=false;
  if(fseek(file,0,SEEK_SET)!=0)ok=false;
  int flags=fcntl(fd,F_GETFD);
  if(flags<0 || fcntl(fd,F_SETFD,flags&~FD_CLOEXEC)!=0)ok=false;
  if(!ok){fclose(file);return 79;}
  for(const auto&e:extra){
    cout<<"c R156_DERIVED_EQ rhs="<<e.rhs<<" vars=";
    for(size_t i=0;i<e.vars.size();i++)cout<<(i?",":"")<<e.vars[i];
    cout<<"\n";
  }
  cout<<"c R156_ROUTE augmented_gf2_residual selected="<<extra.size()
      <<" added_clauses="<<additions<<" auxiliary_vars="<<auxiliary
      <<" original_clauses="<<clauses.size()
      <<" detector_us="<<r153_elapsed_us()<<"\n"<<flush;
  string pathfd="/proc/self/fd/"+to_string(fd);
  char*args[]={const_cast<char*>(kissat.c_str()),const_cast<char*>(pathfd.c_str()),nullptr};
  execv(args[0],args);
  cerr<<"R156_AUGMENT_EXEC_FAILED "<<strerror(errno)<<"\n";
  fclose(file);
  return 77;
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
  if(covered!=int(clauses.size())) {
    // Bounded cost and safety: skip high-cost preprocessing and retain
    // unchanged Kissat for all unsupported/large mixed formulas.
    if(r153_elapsed_us() < 200000 && n<=3000 && eqs.size()<=2000) {
      auto consequences=r156_residual_consequences(basis,n,eqs,clauses,groups);
      if(!consequences.empty()){
        if(classify){
          cout<<"c R156_CLASSIFY residual_entailed_eq="<<consequences.size()
              <<" decision_us="<<r153_elapsed_us()<<"\n"<<flush;
          return 0;
        }
        int result=r156_exec_augmented(kissat,n,clauses,consequences);
        if(result!=79)return result;
      }
    }
    return fallback(filename,kissat,"mixed_no_safe_short_consequence",
                    int(clauses.size()),covered,int(eqs.size()),classify);
  }
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
