// DRNAS GF2-PROOF-FIRST-S1: source-only, exact CNF parity recognition.
// Complete 2..4-literal XOR encodings only. Produces algebraic combination IDs.
// This is NOT an LRAT/DRAT certificate. Independent original-CNF checker REQUIRED.
// On no proof, the caller must fall back to untouched original CNF.
#include <algorithm>
#include <chrono>
#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <vector>
using namespace std;
struct VHash {size_t operator()(vector<int> const& v)const noexcept{size_t h=1469598103934665603ull;for(int x:v){h^=(size_t)x;h*=1099511628211ull;}return h;}};
struct Group {uint16_t seen=0;};
struct Eq {vector<int> vars;int rhs;};
struct Basis {vector<uint64_t> lhs,comb;int rhs;};
static void need(bool v,const string& s){if(!v)throw runtime_error(s);}
static void xorbits(vector<uint64_t>&a,const vector<uint64_t>&b){for(size_t i=0;i<a.size();++i)a[i]^=b[i];}
static int highbit(const vector<uint64_t>&v){for(int i=int(v.size())-1;i>=0;--i)if(v[i])return i*64+63-__builtin_clzll(v[i]);return -1;}
int main(int argc,char**argv){
 try {
  need(argc==2,"need original CNF path");
  auto t=chrono::steady_clock::now();
  ifstream f(argv[1]);need(bool(f),"missing source");
  unordered_map<vector<int>,Group,VHash> groups;
  int n=0,declared=-1,clause_count=0;vector<int> cl;string line;
  bool abstain=false;
  while(getline(f,line)){
   istringstream in(line);string token;if(!(in>>token))continue;
   if(token=="c"||token=="%")continue;
   if(token=="p"){string type;need(declared==-1&&cl.empty(),"duplicate DIMACS header");
    need(bool(in>>type>>n>>declared),"bad header");
    need(type=="cnf"&&n>0&&n<=100000&&declared>=0&&declared<=1000000,"bad DIMACS bounds");continue;}
   do{
    need(declared>=0,"before header");
    size_t consumed=0;int literal=stoi(token,&consumed);
    need(consumed==token.size()&&literal>=-n&&literal<=n,"bad DIMACS literal");
    if(literal!=0)cl.push_back(literal);
    else{
     ++clause_count;need(clause_count<=declared,"too many clauses");
     if(cl.size()>=2&&cl.size()<=4){
      vector<int> vs;for(int v:cl)vs.push_back(abs(v));sort(vs.begin(),vs.end());
      if(unique(vs.begin(),vs.end())==vs.end()){
       unsigned mask=0;
       for(size_t i=0;i<vs.size();++i)if(find(cl.begin(),cl.end(),-vs[i])!=cl.end())mask|=1u<<i;
       if(groups.size()<100000||groups.find(vs)!=groups.end())groups[vs].seen|=uint16_t(1u<<mask);
       else abstain=true;
      }
     }cl.clear();
    }
   }while(in>>token);
  }
  need(declared>=0&&clause_count==declared&&cl.empty(),"DIMACS clause count mismatch");
  vector<Eq> eqs;
  if(!abstain)for(const auto&item:groups){
   const auto&vs=item.first;int k=int(vs.size());
   for(int p=0;p<2;++p){
    uint16_t required=0;
    for(unsigned mask=0;mask<(1u<<k);++mask)if((__builtin_popcount(mask)&1)==p)required|=uint16_t(1u<<mask);
    if((item.second.seen&required)==required)eqs.push_back({vs,1-p});
   }
  }
  sort(eqs.begin(),eqs.end(),[](const Eq&a,const Eq&b){return a.vars==b.vars?a.rhs<b.rhs:a.vars<b.vars;});
  if(eqs.size()>5000){eqs.clear();abstain=true;}
  int nw=(n+63)/64,cw=(int(eqs.size())+63)/64;
  vector<Basis> basis(n);vector<bool> active(n,false);
  bool contradiction=false;vector<int> ids;int rank=0;
  for(int j=0;j<int(eqs.size());++j){
   vector<uint64_t> lhs(nw,0),comb(cw,0);
   for(int v:eqs[j].vars)lhs[(v-1)/64]^=1ull<<((v-1)%64);
   comb[j/64]|=1ull<<(j%64);int rhs=eqs[j].rhs;
   while(true){
    int p=highbit(lhs);
    if(p<0){if(rhs){contradiction=true;for(int x=0;x<int(eqs.size());++x)if((comb[x/64]>>(x%64))&1ull)ids.push_back(x);}break;}
    if(!active[p]){active[p]=true;basis[p]={move(lhs),move(comb),rhs};rank++;break;}
    xorbits(lhs,basis[p].lhs);xorbits(comb,basis[p].comb);rhs^=basis[p].rhs;
   }if(contradiction)break;
  }
  double ms=chrono::duration<double,milli>(chrono::steady_clock::now()-t).count();
  cout<<"GF2_S1_RESULT {\"vars\":"<<n<<",\"clauses\":"<<clause_count<<",\"xor_equations\":"<<eqs.size()
   <<",\"rank\":"<<rank<<",\"xor_unsat\":"<<(contradiction?"true":"false")
   <<",\"abstained\":"<<(abstain?"true":"false")
   <<",\"scan_ms\":"<<ms<<",\"certificate_ids\":[";
  for(size_t i=0;i<ids.size();++i){if(i)cout<<",";cout<<ids[i];}
  cout<<"]}"<<endl;return 0;
 }catch(const exception&e){cerr<<"GF2_S1_FAIL_CLOSED "<<e.what()<<endl;return 2;}
}
