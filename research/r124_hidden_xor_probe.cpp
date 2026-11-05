// DRNAS R124: conservative external CNF XOR discovery with bounded one-hop resolution.
// Research instrumentation ONLY: all SAT/UNSAT decisions are delegated unchanged to
// the already verified R118 solver and its pinned Kissat fallback. V15.3.1 untouched.
// A resolvent of (x|A) and (!x|B) is entailed by the original CNF. Only FULL
// parity clause patterns, original or resolution-entailed, are called verified.
// Incomplete signatures are logged as candidates, never accepted as XOR facts.
#include <algorithm>
#include <cerrno>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iostream>
#include <map>
#include <string>
#include <vector>
#include <unistd.h>
using namespace std;
using Clause=vector<int>;
struct Group {uint32_t masks=0,original=0; int width=0;};
struct Stats {int original=0,resolution=0,partial=0,derived_clauses=0,scan_pairs=0; bool skipped=false;};
static bool normalize(Clause& a) {
  sort(a.begin(),a.end(),[](int x,int y){return abs(x)==abs(y)?x<y:abs(x)<abs(y);});
  for(size_t i=1;i<a.size();++i)if(abs(a[i])==abs(a[i-1]))return false;
  return true;
}
static void add_group(const Clause& a,bool original,map<Clause,Group>&groups){
  if(a.size()<2||a.size()>4)return;
  Clause vs;int mask=0;
  for(size_t i=0;i<a.size();++i){vs.push_back(abs(a[i]));if(a[i]<0)mask|=1<<i;}
  Group &g=groups[vs];g.width=int(a.size());g.masks|=uint32_t(1)<<mask;
  if(original)g.original|=uint32_t(1)<<mask;
}
static bool parse(const string&name,int&n,vector<Clause>& clauses,
                  vector<vector<int>>&pos,vector<vector<int>>&neg) {
  ifstream f(name,ios::binary);if(!f)return false;
  f.seekg(0,ios::end);auto sz=f.tellg();
  if(sz<0||sz>16*1024*1024)return false;
  f.seekg(0);string tok;bool header=false;int expected=-1;Clause current;
  while(f>>tok){
    if(tok=="c"||tok=="%"){string unused;getline(f,unused);continue;}
    if(tok=="p"){
      string fmt;
      if(header||!(f>>fmt>>n>>expected)||fmt!="cnf"||n<1||n>60000||
         expected<0||expected>250000)return false;
      header=true;pos.resize(size_t(n)+1);neg.resize(size_t(n)+1);continue;
    }
    if(!header)return false;
    char*end=nullptr;errno=0;long x=strtol(tok.c_str(),&end,10);
    if(errno||!end||*end||x<-n||x>n)return false;
    if(x){current.push_back(int(x));if(current.size()>12)return false;}
    else {
      if(current.empty())return false;
      // Only small clauses participate in the bounded prepass.
      if(current.size()>=2&&current.size()<=4&&normalize(current)){
        int id=int(clauses.size());clauses.push_back(current);
        for(int v:current)(v>0?pos[v]:neg[-v]).push_back(id);
      }
      current.clear();
    }
  }
  // There can be fewer collected small clauses than declared CNF clauses.
  return header&&current.empty();
}
static Stats detect(const vector<Clause>&clauses,const vector<vector<int>>&pos,
                    const vector<vector<int>>&neg,int n){
  map<Clause,Group>groups;
  for(const Clause&c:clauses)add_group(c,true,groups);
  Stats out;
  constexpr int PAIR_CAP=30000, RESOLVENT_CAP=12000, DEG_CAP=12;
  for(int x=1;x<=n&&out.scan_pairs<PAIR_CAP&&out.derived_clauses<RESOLVENT_CAP;++x){
    const auto&p=pos[x],&q=neg[x];
    if(p.empty()||q.empty()||p.size()>DEG_CAP||q.size()>DEG_CAP||
       p.size()*q.size()>64)continue;
    for(int a:p)for(int b:q){
      if(++out.scan_pairs>PAIR_CAP)break;
      Clause res;
      for(int v:clauses[a])if(v!=x)res.push_back(v);
      for(int v:clauses[b])if(v!=-x)res.push_back(v);
      if(res.size()<2||res.size()>4||!normalize(res))continue;
      add_group(res,false,groups);++out.derived_clauses;
      if(out.derived_clauses>=RESOLVENT_CAP)break;
    }
  }
  for(const auto&entry:groups){
    const Group &g=entry.second;
    int k=g.width,required=1<<(k-1);
    uint32_t even=0,odd=0;
    for(int mask=0;mask<(1<<k);++mask){
      ( __builtin_popcount(unsigned(mask))&1 ? odd : even ) |= uint32_t(1)<<mask;
    }
    for(uint32_t expected:{even,odd}){
      if((g.masks&expected)==expected){
        if((g.original&expected)==expected)++out.original;
        else ++out.resolution; // All missing patterns are one-step resolvents.
      }else if(k>=3&&__builtin_popcount(g.original&expected)>=required-1){
        ++out.partial; // Hypothesis only. NOT a proven parity equation.
      }
    }
  }
  return out;
}
int main(int argc,char**argv) {
  if(argc!=4 && !(argc==5&&string(argv[4])=="--probe-only")){
    cerr<<"Usage: r124_probe CNF R118 KISSAT [--probe-only]\n";return 2;
  }
  int n=0;vector<Clause>clauses;vector<vector<int>>pos,neg;Stats s;
  if(parse(argv[1],n,clauses,pos,neg))s=detect(clauses,pos,neg,n);
  else s.skipped=true;
  cout<<"c R124_PROBE exact_xor="<<s.original<<" resolved_xor="<<s.resolution
      <<" partial_hypotheses="<<s.partial<<" resolution_clauses="<<s.derived_clauses
      <<" resolution_pairs="<<s.scan_pairs<<" source_small_clauses="<<clauses.size()
      <<" probe_skipped="<<(s.skipped?1:0)<<"\n"<<flush;
  if(argc==5)return 0;
  // Never decide SAT/UNSAT from partial or bounded-resolution candidates.
  // R118 has its own exact parity proof and original-CNF witness checks.
  char*args[]={argv[2],argv[1],argv[3],nullptr};
  execv(args[0],args);
  cerr<<"R124_FALLBACK_EXEC_ERROR "<<strerror(errno)<<"\n";
  return 78;
}
