// R155a: verified bidirectional CNF BCP <-> GF(2) closure on mixed originals; frozen R155/R153/R28 unchanged.
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
#include <set>
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

// R155 research-only mixed-CNF bridge. Gaussian rows are XOR linear
// combinations of source-certified complete parity blocks and original units.
// Only equations with 1..4 variables are encoded as logically ENTAILED CNF.
// Original file never changes. /proc/self/fd points to an unlinked temporary
// file so OS cleans up even if solver is killed by benchmark wall timeout.
struct R155ShortEq { vector<int> vars; int rhs=0; };
static vector<R155ShortEq> r155_short_consequences(const vector<Row>&basis,int n){
  vector<Row> rref(size_t(n)+1);
  vector<R155ShortEq> out;
  size_t added_clauses=0;
  // Original basis rows pivot on LOWEST nonzero variable. Reduced later
  // pivots have no other pivot variables; eliminate them in ascending order.
  for(int p=n;p>=1;p--){
    if(!basis[size_t(p)].valid)continue;
    Row r=basis[size_t(p)];
    for(int q=p+1;q<=n;q++)if(rref[size_t(q)].valid && bit(r.bits,q))
      add(r,rref[size_t(q)]);
    rref[size_t(p)]=move(r);
    const Row &z=rref[size_t(p)];
    vector<int> vars;
    for(size_t w=0;w<z.bits.size();w++){
      uint64_t mask=z.bits[w];
      while(mask){
        int v=int(w*64+__builtin_ctzll(mask));
        if(v>=1 && v<=n)vars.push_back(v);
        mask&=mask-1;
        if(vars.size()>4)break;
      }
      if(vars.size()>4)break;
    }
    if(vars.empty()||vars.size()>4)continue;
    size_t nc=size_t(1)<<(vars.size()-1);
    if(out.size()>=128 || added_clauses+nc>384)continue;
    out.push_back({move(vars),z.rhs});
    added_clauses+=nc;
  }
  return out;
}
static int r155_exec_augmented(const string&kissat,int n,
     const vector<vector<int>>&clauses,const vector<R155ShortEq>&extra){
  if(extra.empty())return 79;
  size_t additions=0;
  for(auto &e:extra)additions+=size_t(1)<<(e.vars.size()-1);
  char path[]="/tmp/r155-proven-XXXXXX";
  int fd=mkstemp(path);
  if(fd<0)return 79;
  unlink(path); // never leave a reusable or stale augmented CNF on disk
  FILE* file=fdopen(fd,"w+");
  if(!file){close(fd);return 79;}
  bool ok=fprintf(file,"p cnf %d %zu\n",n,clauses.size()+additions)>0;
  for(const auto&cl:clauses){
    for(int v:cl)if(fprintf(file,"%d ",v)<0)ok=false;
    if(fprintf(file,"0\n")<0)ok=false;
  }
  for(const auto &e:extra){
    const int k=int(e.vars.size());
    for(int mask=0;mask<(1<<k);mask++){
      if((__builtin_popcount(unsigned(mask))&1)!=(1-e.rhs))continue;
      for(int j=0;j<k;j++){
        int v=(mask&(1<<j)) ? -e.vars[size_t(j)] : e.vars[size_t(j)];
        if(fprintf(file,"%d ",v)<0)ok=false;
      }
      if(fprintf(file,"0\n")<0)ok=false;
    }
  }
  if(fflush(file)!=0 || ferror(file))ok=false;
  if(fseek(file,0,SEEK_SET)!=0)ok=false;
  int flags=fcntl(fd,F_GETFD);
  if(flags<0 || fcntl(fd,F_SETFD, flags&~FD_CLOEXEC)!=0)ok=false;
  if(!ok){fclose(file);return 79;}
  // Every announced row is independently checkable for membership in the
  // original XOR+unit GF(2) span, before any augmented UNSAT is trusted.
  for(const auto &e:extra){
    cout<<"c R155_DERIVED_EQ rhs="<<e.rhs<<" vars=";
    for(size_t j=0;j<e.vars.size();j++)cout<<(j?",":"")<<e.vars[j];
    cout<<"\n";
  }
  cout<<"c R155_ROUTE augmented_gf2_short consequence_eq="<<extra.size()
      <<" added_clauses="<<additions<<" original_clauses="<<clauses.size()
      <<" detector_us="<<r153_elapsed_us()<<"\n"<<flush;
  string procfd="/proc/self/fd/"+to_string(fd);
  char* args[]={const_cast<char*>(kissat.c_str()),
                const_cast<char*>(procfd.c_str()),nullptr};
  execv(args[0],args);
  cerr<<"R155_AUGMENT_EXEC_FAILED "<<strerror(errno)<<"\n";
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

// R155a: Source-CNF BCP and fully certified Gaussian consequences exchange
// ENTAILED units. All exported proof steps are checked independently against
// the ORIGINAL input by the separate benchmark verifier, including on timeout.
// No incomplete XOR pattern may imply any GF(2) equation.
struct R155AUnit { int lit=0, clause=-1; bool from_gf2=false; };
struct R155AClosure {
  vector<R155AUnit> steps;
  vector<R155ShortEq> rows;
  vector<vector<int>> novel;
  int bcp_units=0, gf2_units=0, bcp_scans=0, closure_rounds=0;
  bool contradiction=false, timed_out=false;
};
static bool r155a_bcp(const vector<vector<int>>&clauses,vector<int>&val,
                       R155AClosure &c) {
  bool changed=false;
  for(size_t i=0;i<clauses.size();i++){
    if((i&1023)==0 && r153_elapsed_us()>170000){c.timed_out=true;return changed;}
    const auto &cl=clauses[i];
    bool sat=false;int count=0,missing=0;
    for(int lit:cl){
      int a=val[size_t(abs(lit))];
      if(a<0){count++;missing=lit;if(count>1)break;}
      else if((a==1)==(lit>0)){sat=true;break;}
    }
    if(sat || count>1)continue;
    if(count==0){c.contradiction=true;return changed;}
    const int v=abs(missing),wanted=missing>0?1:0;
    if(val[size_t(v)]<0){
      val[size_t(v)]=wanted;
      c.steps.push_back({missing,int(i),false});
      ++c.bcp_units;changed=true;
      if(c.steps.size()>=300)return changed;
    }else if(val[size_t(v)]!=wanted){c.contradiction=true;return changed;}
  }
  c.bcp_scans++;
  return changed;
}
static bool r155a_gauss(const vector<Equation>&source,int n,
                        const vector<R155AUnit>&trace,
                        vector<Row>&basis, bool &contradiction) {
  vector<Equation> dyn=source;
  for(const auto &e:trace)dyn.push_back({{abs(e.lit)},e.lit>0?1:0});
  if(dyn.size()>3000)return false;
  const size_t words=size_t(n/64+1),proof_words=(dyn.size()+63)/64;
  basis.assign(size_t(n)+1,Row{});
  for(size_t i=0;i<dyn.size();i++){
    Row row;
    row.bits.assign(words,0);
    row.proof.assign(proof_words,0);
    row.rhs=dyn[i].rhs;
    for(int v:dyn[i].vars)flip(row.bits,v);
    row.proof[i>>6]|=uint64_t(1)<<(i&63);
    for(;;){
      int pivot=lowest(row.bits);
      if(!pivot){
        if(row.rhs){contradiction=true;return false;}
        break;
      }
      if(basis[size_t(pivot)].valid)add(row,basis[size_t(pivot)]);
      else {row.valid=true;basis[size_t(pivot)]=move(row);break;}
    }
  }
  return true;
}
static vector<vector<int>> r155a_rref_units(
       const vector<Row>&basis,int n,vector<int>&val,R155AClosure&c){
  vector<Row> rref(size_t(n)+1);
  vector<vector<int>> shortrows;
  for(int p=n;p>=1;p--){
    if(!basis[size_t(p)].valid)continue;
    Row z=basis[size_t(p)];
    for(int q=p+1;q<=n;q++)if(rref[size_t(q)].valid && bit(z.bits,q))
      add(z,rref[size_t(q)]);
    rref[size_t(p)]=move(z);
    const Row& r=rref[size_t(p)];
    int found=0,v=0;
    for(size_t w=0;w<r.bits.size();w++){
      uint64_t mask=r.bits[w];
      while(mask){
        v=int(64*w+__builtin_ctzll(mask));found++;
        mask&=mask-1;
        if(found>=2)break;
      }
      if(found>=2)break;
    }
    if(found==1 && v>=1 && v<=n){
      int wanted=r.rhs;
      if(val[size_t(v)]<0 && c.steps.size()<300){
        val[size_t(v)]=wanted;
        c.steps.push_back({wanted?v:-v,-1,true});
        c.gf2_units++;
      }else if(val[size_t(v)]>=0 && val[size_t(v)]!=wanted){
        c.contradiction=true;
      }
    }
  }
  return shortrows;
}
static R155AClosure r155a_closure(const vector<vector<int>>&clauses,
        const vector<Equation>&certified,int n){
  R155AClosure c;
  vector<int> val(size_t(n)+1,-1);
  for(const auto&cl:clauses)if(cl.size()==1){
    int lit=cl[0],v=abs(lit),wanted=lit>0?1:0;
    if(val[size_t(v)]>=0 && val[size_t(v)]!=wanted)c.contradiction=true;
    val[size_t(v)]=wanted;
  }
  if(c.contradiction)return c;
  vector<Row> basis;
  for(int round=0;round<8;round++){
    if(r153_elapsed_us()>170000){c.timed_out=true;break;}
    const auto old=c.steps.size();
    r155a_bcp(clauses,val,c);
    if(c.contradiction||c.timed_out)break;
    bool contradiction=false;
    if(!r155a_gauss(certified,n,c.steps,basis,contradiction)){
      c.contradiction=contradiction;break;
    }
    r155a_rref_units(basis,n,val,c);
    if(c.contradiction)break;
    c.closure_rounds++;
    if(c.steps.size()==old || c.steps.size()>=300)break;
  }
  if(c.contradiction||c.timed_out)return c;
  bool contradiction=false;
  if(!r155a_gauss(certified,n,c.steps,basis,contradiction)){
    c.contradiction=contradiction;return c;
  }
  const auto candidates=r155_short_consequences(basis,n);
  set<vector<int>> already;
  for(const auto&orig:clauses){
    vector<int> key=orig;
    sort(key.begin(),key.end());
    already.insert(move(key));
  }
  // Prioritize newly propagated units, so the mixed residual can use
  // GF2 consequences already at the first CNF propagation step.
  auto enqueue=[&](vector<int> cl)->bool{
    sort(cl.begin(),cl.end());
    if(already.count(cl))return false;
    if(c.novel.size()>=384)return false;
    already.insert(cl);
    c.novel.push_back(move(cl));
    return true;
  };
  for(const auto &u:c.steps)enqueue({u.lit});
  // Only short ORIGINAL-GF2-span consequences; select rows if and only if
  // at least one CNF clause is genuinely absent from the ORIGINAL+derived CNF.
  for(const auto&e:candidates){
    if(c.rows.size()>=128 || c.novel.size()>=384)break;
    vector<vector<int>> possible;
    for(int mask=0;mask<(1<<e.vars.size());mask++){
      if((__builtin_popcount(unsigned(mask))&1)!=(1-e.rhs))continue;
      vector<int>cl;
      for(size_t k=0;k<e.vars.size();k++){
        int v=e.vars[k];
        cl.push_back(mask&(1<<k)?-v:v);
      }
      sort(cl.begin(),cl.end());
      if(!already.count(cl))possible.push_back(move(cl));
    }
    if(possible.empty())continue;
    if(possible.size()+c.novel.size()>384)continue;
    for(auto &cl:possible)enqueue(move(cl));
    c.rows.push_back(e);
  }
  return c;
}
static int r155a_write_and_exec(const string&kissat,int n,
          const vector<vector<int>>&original,const R155AClosure&c){
  if(c.novel.empty())return 79;
  char path[]="/tmp/r155a-proven-XXXXXX";
  int fd=mkstemp(path);
  if(fd<0)return 79;
  unlink(path);
  FILE* f=fdopen(fd,"w+");
  if(!f){close(fd);return 79;}
  bool ok=fprintf(f,"p cnf %d %zu\n",n,original.size()+c.novel.size())>0;
  for(const auto&cl:original){
    for(int lit:cl)if(fprintf(f,"%d ",lit)<0)ok=false;
    if(fprintf(f,"0\n")<0)ok=false;
  }
  for(const auto&cl:c.novel){
    for(int lit:cl)if(fprintf(f,"%d ",lit)<0)ok=false;
    if(fprintf(f,"0\n")<0)ok=false;
  }
  if(fflush(f)!=0||ferror(f)||fseek(f,0,SEEK_SET)!=0)ok=false;
  int flags=fcntl(fd,F_GETFD);
  if(flags<0||fcntl(fd,F_SETFD,flags&~FD_CLOEXEC)!=0)ok=false;
  if(!ok){fclose(f);return 79;}
  for(const auto &u:c.steps){
    if(u.from_gf2)cout<<"c R155A_GF2_UNIT lit="<<u.lit<<"\n";
    else cout<<"c R155A_BCP_UNIT lit="<<u.lit<<" clause="<<u.clause<<"\n";
  }
  for(const auto &e:c.rows){
    cout<<"c R155A_EQ rhs="<<e.rhs<<" vars=";
    for(size_t j=0;j<e.vars.size();j++)cout<<(j?",":"")<<e.vars[j];
    cout<<"\n";
  }
  for(const auto&cl:c.novel){
    cout<<"c R155A_NEW_CLAUSE";
    for(int lit:cl)cout<<" "<<lit;
    cout<<" 0\n";
  }
  cout<<"c R155A_ROUTE augmented_verified original_clauses="<<original.size()
      <<" new_clauses="<<c.novel.size()
      <<" bcp_units="<<c.bcp_units<<" gf2_units="<<c.gf2_units
      <<" derived_eq="<<c.rows.size()<<" rounds="<<c.closure_rounds
      <<" decision_us="<<r153_elapsed_us()<<"\n"<<flush;
  string fdpath="/proc/self/fd/"+to_string(fd);
  char* args[]={const_cast<char*>(kissat.c_str()),const_cast<char*>(fdpath.c_str()),nullptr};
  execv(args[0],args);
  cerr<<"R155A_EXEC_FAILED "<<strerror(errno)<<"\n";
  fclose(f);return 77;
}
static int r155a_process_mixed(const string&filename,const string&kissat,
        const vector<vector<int>>&clauses,const vector<Equation>&eqs,
        int n,int covered,bool classify){
  auto c=r155a_closure(clauses,eqs,n);
  cout<<"c R155A_DIAG original_eq="<<eqs.size()<<" clauses="<<clauses.size()
      <<" covered="<<covered<<" bcp_scans="<<c.bcp_scans
      <<" bcp_units="<<c.bcp_units<<" gf2_units="<<c.gf2_units
      <<" rounds="<<c.closure_rounds<<" novel="<<c.novel.size()
      <<" derived_short_eq="<<c.rows.size()
      <<" contradiction="<<(c.contradiction?1:0)
      <<" overhead_us="<<r153_elapsed_us()<<"\n"<<flush;
  if(classify)return 0;
  if(!c.contradiction && !c.timed_out && !c.novel.empty()){
    const int result=r155a_write_and_exec(kissat,n,clauses,c);
    if(result!=79)return result;
  }
  return fallback(filename,kissat,"r155a_no_safe_novel_consequence",
                  int(clauses.size()),covered,int(eqs.size()),false);
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
    return r155a_process_mixed(filename,kissat,clauses,eqs,n,covered,classify);
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
