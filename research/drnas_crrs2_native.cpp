// DRNAS CRR-S2: conservative, deadline-bounded, proof-first CNF preprocessor.
// Original CNF never mutated. Every appended 1/2-clause is sequentially RUP
// validated by two-watched-literal unit propagation over original + prior RUPs.
// Structural discovery: binary implication SCC, exact XOR(2..4) half-cubes,
// and SCC-substitution of extracted parity constraints. No UNSAT claimed.
// C++17, no external libraries.
#include <algorithm>
#include <array>
#include <chrono>
#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <map>
#include <numeric>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>
using namespace std;
using Clock = chrono::steady_clock;
using Clause = vector<int>;
static constexpr int MAX_CANDIDATES=80;
static constexpr int MAX_ADDED=32;
static int ix(int lit){return 2*(abs(lit)-1)+(lit<0);}
struct Timeout:runtime_error {Timeout():runtime_error("budget"){}};
struct Timer{
  Clock::time_point start,limit;
  explicit Timer(int ms):start(Clock::now()),limit(start+chrono::milliseconds(ms)){}
  void check()const{if(Clock::now()>=limit)throw Timeout();}
  double elapsed()const{return chrono::duration<double>(Clock::now()-start).count();}
};
struct CNF{
 int n=0,declared=-1;
 vector<Clause> cs;
};
static CNF readcnf(const string &p,const Timer &tim){
 ifstream f(p);if(!f)throw runtime_error("missing original CNF");
 CNF a;string s;Clause partial;
 while(getline(f,s)){
   if((a.cs.size()&1023)==0)tim.check();
   istringstream in(s);string first;if(!(in>>first))continue;
   if(first=="c"||first=="%")continue;
   if(first=="p"){
     string type;int n,m;in>>type>>n>>m;
     if(type!="cnf"||n<0||m<0||a.declared!=-1)throw runtime_error("bad header");
     a.n=n;a.declared=m;continue;
   }
   if(a.declared<0)throw runtime_error("clauses before header");
   istringstream ints(s);int v;
   while(ints>>v){
     if(v==0){a.cs.push_back(partial);partial.clear();}
     else{
       if(abs(v)>a.n||v==INT32_MIN)throw runtime_error("bad literal");
       partial.push_back(v);
     }
   }
 }
 if(a.declared<0||!partial.empty()||a.cs.size()!=size_t(a.declared))
    throw runtime_error("bad DIMACS count");
 return a;
}
struct ParityDSU{
 vector<int> p,sz,delta;bool inconsistent=false;
 explicit ParityDSU(int n):p(n+1),sz(n+1,1),delta(n+1,0){iota(p.begin(),p.end(),0);}
 pair<int,int> find(int x){
   int t=x,v=0;
   while(p[t]!=t){v^=delta[t];t=p[t];}
   int root=t; t=x;int prefix=0;
   while(p[t]!=t){int next=p[t],old=delta[t];p[t]=root;delta[t]=v^prefix;prefix^=old;t=next;}
   return {root,v};
 }
 void unite(int a,int b,int relation){
   auto x=find(a),y=find(b);
   if(x.first==y.first){if((x.second^y.second)!=relation)inconsistent=true;return;}
   if(sz[x.first]<sz[y.first])swap(x,y);
   p[y.first]=x.first;
   delta[y.first]=x.second^y.second^relation;
   sz[x.first]+=sz[y.first];
 }
};
static void add_equivalence(vector<Clause> &out,int a,int b,int parity){
 if(a==b)return;
 if(parity==0){out.push_back({-a,b});out.push_back({a,-b});}
 else {out.push_back({-a,-b});out.push_back({a,b});}
}
struct Structural{
 int xor_rows=0,xor4=0,scc_equiv=0,scc_components=0,short_rows=0;
 vector<Clause> proposed;
};
static Structural extract(const CNF &cnf,const Timer &tim){
 Structural r;int n=cnf.n;
 vector<vector<int>> g(2*n),rev(2*n);
 // For each exact original support, record which forbidden assignments exist.
 map<vector<int>,array<uint16_t,2>> masks;
 for(size_t j=0;j<cnf.cs.size();++j){
   if((j&1023)==0)tim.check();
   const auto &c=cnf.cs[j];
   if(c.size()==2 && abs(c[0])!=abs(c[1])){
      int a=-c[0],b=c[1],u=-c[1],v=c[0];
      g[ix(a)].push_back(ix(b));rev[ix(b)].push_back(ix(a));
      g[ix(u)].push_back(ix(v));rev[ix(v)].push_back(ix(u));
   }
   if(c.size()<2||c.size()>4)continue;
   vector<int> vs;for(int lit:c)vs.push_back(abs(lit));
   sort(vs.begin(),vs.end());
   if(unique(vs.begin(),vs.end())!=vs.end())continue;
   int neg=0;
   for(int k=0;k<int(vs.size());++k)
     for(int lit:c)if(abs(lit)==vs[k]&&lit<0)neg|=(1<<k);
   masks[vs][__builtin_popcount(unsigned(neg))&1]|=uint16_t(1u<<neg);
 }
 // Iterative Kosaraju (no recursion and no stack overflow on industrial CNF).
 vector<uint8_t> seen(2*n);
 vector<int> order;order.reserve(2*n);
 for(int root=0;root<2*n;++root){
   if(seen[root])continue;
   seen[root]=1;
   vector<pair<int,size_t>> stack={{root,0}};
   while(!stack.empty()){
      if((order.size()&4095)==0)tim.check();
      auto &z=stack.back();
      if(z.second<g[z.first].size()){
        int v=g[z.first][z.second++];
        if(!seen[v]){seen[v]=1;stack.push_back({v,0});}
      }else{order.push_back(z.first);stack.pop_back();}
   }
 }
 vector<int> component(2*n,-1);
 int compid=0;
 for(auto it=order.rbegin();it!=order.rend();++it){
   if(component[*it]!=-1)continue;
   vector<int> stack={*it};component[*it]=compid;
   while(!stack.empty()){
     int v=stack.back();stack.pop_back();
     for(int w:rev[v])if(component[w]==-1){
       component[w]=compid;stack.push_back(w);
     }
   }
   ++compid;
 }
 ParityDSU dsu(n);
 vector<int> representative(compid,-1);
 for(int litidx=0;litidx<2*n;++litidx){
   int id=component[litidx],lit= (litidx&1)?-(litidx/2+1):(litidx/2+1);
   if(representative[id]==-1){representative[id]=lit;continue;}
   int a=abs(representative[id]),b=abs(lit);
   if(a==b){if(representative[id]!=lit)dsu.inconsistent=true;continue;}
   int parity=(representative[id]<0)^(lit<0);
   dsu.unite(a,b,parity);
   ++r.scc_equiv;
 }
 if(dsu.inconsistent)return r;  // Never use conflicting SCC rows for additions.
 r.scc_components=compid;
 // Pure SCC equivalence clauses: usually redundant, accepted only if RUP.
 for(int i=1;i<=n;++i){
   if((i&4095)==0)tim.check();
   auto [root,par]=dsu.find(i);
   if(root!=i)add_equivalence(r.proposed,i,root,par);
 }
 // A complete parity half cube: every forbidden sign pattern of one parity.
 for(const auto &[vars,m]:masks){
   tim.check();int k=int(vars.size());
   for(int forbidden=0;forbidden<=1;++forbidden){
     unsigned required=0;
     for(int mask=0;mask<(1<<k);++mask){
       if((__builtin_popcount(unsigned(mask))&1)==forbidden)
          required|=1u<<mask;
     }
     if((unsigned(m[forbidden])&required)!=required)continue;
     ++r.xor_rows;if(k==4)++r.xor4;
     int rhs=1^forbidden;
     vector<int> vs; // XOR of representatives, accounting for SCC parities
     for(int var:vars){
       auto [root,delta]=dsu.find(var);
       rhs^=delta;
       auto it=find(vs.begin(),vs.end(),root);
       if(it==vs.end())vs.push_back(root);else vs.erase(it);
     }
     sort(vs.begin(),vs.end());
     if(vs.size()==1){++r.short_rows;r.proposed.push_back({rhs?vs[0]:-vs[0]});}
     else if(vs.size()==2){++r.short_rows;add_equivalence(r.proposed,vs[0],vs[1],rhs);}
   }
 }
 // Deterministic, source independent candidate priority, no outcome oracle.
 for(auto &c:r.proposed)sort(c.begin(),c.end());
 sort(r.proposed.begin(),r.proposed.end(),[](auto &a,auto &b){
    return a.size()==b.size()?a<b:a.size()<b.size();
 });
 r.proposed.erase(unique(r.proposed.begin(),r.proposed.end()),r.proposed.end());
 return r;
}
struct WatchedRUP{
 int n;vector<Clause> clauses;
 vector<array<int,2>> watch;
 vector<vector<int>> watchers;
 vector<int> units;
 vector<int8_t> value;
 vector<int> trail;
 bool empty=false,expired=false;
 explicit WatchedRUP(int nv):n(nv),watchers(2*nv),value(nv+1){}
 void add(const Clause &c){
   int id=clauses.size();clauses.push_back(c);
   watch.push_back({0,int(c.size()>1)});
   if(c.empty()){empty=true;return;}
   watchers[ix(c[0])].push_back(id);
   if(c.size()>1)watchers[ix(c[1])].push_back(id);
   else units.push_back(c[0]);
 }
 int eval(int lit)const {return value[abs(lit)]*(lit>0?1:-1);}
 bool put(int lit){
   auto &v=value[abs(lit)];int b=lit>0?1:-1;
   if(v==b)return true;
   if(v==-b)return false;
   v=b;trail.push_back(lit);return true;
 }
 bool rup(const Clause &lemma,const Timer &tim){
   if(empty)return true;
   fill(value.begin(),value.end(),0);
   trail.clear();expired=false;
   for(int lit:lemma)if(!put(-lit))return true;
   for(int lit:units)if(!put(lit))return true;
   unsigned loops=0;
   for(size_t q=0;q<trail.size();++q){
     if((q&1023)==0&&Clock::now()>=tim.limit){expired=true;return false;}
     int false_lit=-trail[q];
     auto &bucket=watchers[ix(false_lit)];
     for(size_t pos=0;pos<bucket.size();){
       if((++loops&4095)==0&&Clock::now()>=tim.limit){expired=true;return false;}
       int id=bucket[pos];
       auto &c=clauses[id];auto &w=watch[id];
       int side=c[w[0]]==false_lit?0:(c[w[1]]==false_lit?1:-1);
       if(side<0){bucket[pos]=bucket.back();bucket.pop_back();continue;}
       int other=c[w[1-side]];
       if(eval(other)>0){++pos;continue;}
       bool moved=false;
       for(int k=0;k<int(c.size());++k){
         if(k==w[0]||k==w[1])continue;
         if(eval(c[k])>=0){
            w[side]=k;
            watchers[ix(c[k])].push_back(id);
            bucket[pos]=bucket.back();bucket.pop_back();
            moved=true;break;
         }
       }
       if(moved)continue;
       if(eval(other)<0)return true;
       if(!put(other))return true;
       ++pos;
     }
   }
   return false;
 }
};
static void emit(const CNF &cnf,const vector<Clause> &lemmas,const string &path){
 ofstream o(path);if(!o)throw runtime_error("cannot write output CNF");
 o<<"p cnf "<<cnf.n<<" "<<cnf.cs.size()+lemmas.size()<<"\n";
 for(const Clause &c:cnf.cs) {
   for(int lit:c)o<<lit<<" ";
   o<<"0\n";
 }
 for(const Clause &c:lemmas){
   for(int lit:c)o<<lit<<" ";
   o<<"0\n";
 }
 if(!o)throw runtime_error("write failed");
}
static void selftest(){
 Timer t(4000);
 WatchedRUP w(4);
 for(auto c:vector<Clause>{{1},{-1,2},{-2,3}})w.add(c);
 if(!w.rup({3},t)||w.rup({4},t))throw runtime_error("watch RUP test");
 WatchedRUP u(3);
 for(auto c:vector<Clause>{{1,2},{-1,2}})u.add(c);
 if(!u.rup({2},t)||u.rup({-2},t))throw runtime_error("binary unit RUP test");
 CNF cnf;cnf.n=6;
 cnf.cs={{1,2,3},{1,-2,-3},{-1,2,-3},{-1,-2,3},
         {-2,5},{-5,3},{-3,6},{-6,2}};
 auto s=extract(cnf,t);
 if(s.xor_rows<1||s.scc_equiv<1)throw runtime_error("XOR/SCC extraction selftest");
 cout<<"CRRS2_SELFTEST_PASS {\"xor_rows\":"<<s.xor_rows
     <<",\"scc_equiv\":"<<s.scc_equiv<<"}\n";
}
int main(int argc,char **argv){
 try{
   if(argc==2&&string(argv[1])=="selftest"){selftest();return 0;}
   if(argc!=4)throw runtime_error("usage: native original.cnf output.cnf budget_ms");
   string src=argv[1],dest=argv[2];int budget=stoi(argv[3]);
   if(budget<10||budget>10000)throw runtime_error("bad budget");
   Timer tim(budget);
   CNF cnf=readcnf(src,tim);
   Structural x=extract(cnf,tim);
   WatchedRUP checker(cnf.n);
   for(auto &c:cnf.cs)checker.add(c);
   vector<Clause> accepted;
   int checked=0;bool timeout=false;
   for(const auto &c:x.proposed){
     if(checked>=MAX_CANDIDATES||int(accepted.size())>=MAX_ADDED)break;
     if(Clock::now()>=tim.limit){timeout=true;break;}
     ++checked;
     if(checker.rup(c,tim)){
       accepted.push_back(c);checker.add(c);
     }
     if(checker.expired){timeout=true;break;}
   }
   if(Clock::now()>=tim.limit)timeout=true;
   // Output is only consumed on successful completion and independently audited.
   emit(cnf,accepted,dest);
   cout<<"CRRS2_NATIVE {\"original_clauses\":"<<cnf.cs.size()
       <<",\"xor_rows\":"<<x.xor_rows<<",\"xor4\":"<<x.xor4
       <<",\"scc_equiv\":"<<x.scc_equiv<<",\"short_rows\":"<<x.short_rows
       <<",\"candidate_count\":"<<x.proposed.size()<<",\"rup_checked\":"<<checked
       <<",\"added\":"<<accepted.size()<<",\"timed_out\":"
       <<(timeout?"true":"false")<<",\"wall_s\":"<<tim.elapsed()
       <<",\"emitted_lemmas\":[";
   for(size_t i=0;i<accepted.size();++i){
     if(i)cout<<",";
     cout<<"[";
     for(size_t j=0;j<accepted[i].size();++j){
       if(j)cout<<",";cout<<accepted[i][j];
     }
     cout<<"]";
   }
   cout<<"]}\n";
   return 0;
 }catch(const Timeout&){
   cerr<<"CRRS2_ABSTAIN bounded_preprocessing_timeout\n";return 75;
 }catch(const exception &e){
   cerr<<"CRRS2_ERROR "<<e.what()<<"\n";return 2;
 }
}
