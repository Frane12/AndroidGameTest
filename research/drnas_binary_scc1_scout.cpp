// DRNAS BINARY-SCC1 native source-only proof scout.
// Original clauses are NEVER modified. Directed edge (not a -> b) for (a OR b).
// Unit (a) creates edge -a -> a. SCC equivalences imply logical equivalence;
// SCC(x) == SCC(-x) gives a binary/unit subformula contradiction.
// No SAT solving, no transformed solver input, no claim of LRAT certification.
#include <algorithm>
#include <chrono>
#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>
using namespace std;
using Clock=chrono::steady_clock;
static void req(bool x,const string& m){if(!x)throw runtime_error("BINARY_SCC_FAIL_CLOSED "+m);}
static int node(int l){return 2*(abs(l)-1)+(l<0);}
static int lit(int i){return (i/2+1)*(i%2?-1:1);}
static double elapsed(Clock::time_point t){return chrono::duration<double,milli>(Clock::now()-t).count();}
struct Scan{
 int n=0,declared=-1,count=0,binary=0,unit=0,empty=0;
 long long literals=0,edges=0,taut_binary=0;
 vector<vector<int>> g,rg;
 void add(int from,int to){
   g[node(from)].push_back(node(to));
   rg[node(to)].push_back(node(from));
   ++edges;
   req(edges<=500000,"edge limit");
 }
 void clause(const vector<int>& c){
   ++count;req(count<=declared,"too many clauses");
   if(c.empty()){empty++;return;}
   if(c.size()==1){unit++;add(-c[0],c[0]);return;}
   if(c.size()==2){
     ++binary;
     if(c[0]==-c[1]){++taut_binary;return;}
     // Duplicate literals (a OR a) are exactly the unit clause a.
     if(c[0]==c[1]){add(-c[0],c[0]);return;}
     add(-c[0],c[1]);add(-c[1],c[0]);
   }
 }
};
static Scan load(const string& name){
 ifstream f(name);req(bool(f),"cannot open original source");
 Scan a;string t;vector<int> clause;
 while(f>>t){
   if(t=="c"){string rest;getline(f,rest);continue;}
   if(t=="%")break;
   if(t=="p"){
     string fmt;req(a.declared<0 && clause.empty() &&
                    bool(f>>fmt>>a.n>>a.declared),"DIMACS header");
     req(fmt=="cnf" && a.n>0 && a.n<=200000 &&
         a.declared>=0 && a.declared<=500000,"CNF geometry");
     a.g.resize(2*a.n);a.rg.resize(2*a.n);continue;
   }
   req(a.declared>=0,"header missing");
   size_t k=0;long long v=0;
   try{v=stoll(t,&k);}catch(...){throw runtime_error("invalid literal token");}
   req(k==t.size() && v>=-a.n && v<=a.n,"literal range");
   if(v==0){
     a.clause(clause);clause.clear();
   }else{
     clause.push_back(int(v));
     req(++a.literals<=8000000,"literal budget");
   }
 }
 req(a.declared>=0 && clause.empty() && a.count==a.declared,
     "incomplete or incorrect original DIMACS");
 return a;
}
static vector<int> path(const Scan& a,int from,int to){
 const int N=2*a.n;vector<int> pred(N,-1),queue;queue.reserve(N);
 int s=node(from),target=node(to);pred[s]=s;queue.push_back(s);
 for(size_t head=0;head<queue.size() && pred[target]<0;++head){
   for(int v:a.g[queue[head]])if(pred[v]<0){
     pred[v]=queue[head];queue.push_back(v);
   }
 }
 req(pred[target]>=0,"expected directed implication path absent");
 vector<int> out;int x=target;
 while(x!=s){out.push_back(lit(x));x=pred[x];}
 out.push_back(from);reverse(out.begin(),out.end());
 req(int(out.size())<=N+1,"path length overflow");
 return out;
}
static void emit_path(const vector<int>& p){
 cout<<"[";for(size_t i=0;i<p.size();++i){if(i)cout<<",";cout<<p[i];}cout<<"]";
}
int main(int argc,char**argv){
 try{
   req(argc==2,"usage: binary_scc_scout original.cnf");
   auto begin=Clock::now();Scan a=load(argv[1]);
   double parse_ms=elapsed(begin);const int N=2*a.n;
   vector<unsigned char> seen(N,0);vector<int> order;order.reserve(N);
   for(int root=0;root<N;++root)if(!seen[root]){
     seen[root]=1;vector<pair<int,size_t>> stack{{root,0}};
     while(!stack.empty()){
       auto& f=stack.back();
       if(f.second<a.g[f.first].size()){
         int v=a.g[f.first][f.second++];
         if(!seen[v]){seen[v]=1;stack.push_back({v,0});}
       }else{order.push_back(f.first);stack.pop_back();}
     }
   }
   vector<int> comp(N,-1),sz,canon;
   for(auto it=order.rbegin();it!=order.rend();++it)if(comp[*it]<0){
     int cid=int(sz.size());vector<int> stack{*it};comp[*it]=cid;
     int csize=0,best=0;
     while(!stack.empty()){
       int v=stack.back();stack.pop_back();++csize;
       int l=lit(v);
       if(best==0 || abs(l)<abs(best) || (abs(l)==abs(best)&&l>best))best=l;
       for(int u:a.rg[v])if(comp[u]<0){comp[u]=cid;stack.push_back(u);}
     }
     sz.push_back(csize);canon.push_back(best);
   }
   int largest=0,nontrivial=0,conflicts=0;
   vector<pair<int,int>> alias;int first_conflict=0;
   for(int s:sz){largest=max(largest,s);if(s>1)nontrivial++;}
   for(int var=1;var<=a.n;++var){
     int yes=comp[node(var)],no=comp[node(-var)];
     if(yes==no){++conflicts;if(!first_conflict)first_conflict=var;continue;}
     int rep=canon[yes];
     if(abs(rep)<var)alias.push_back({var,rep});
   }
   cout<<"{"
       <<"\"variables\":"<<a.n<<",\"clauses\":"<<a.count
       <<",\"binary_clauses\":"<<a.binary
       <<",\"unit_clauses\":"<<a.unit
       <<",\"empty_clauses\":"<<a.empty
       <<",\"tautological_binary\":"<<a.taut_binary
       <<",\"literal_occurrences\":"<<a.literals
       <<",\"implication_edges\":"<<a.edges
       <<",\"scc_components\":"<<sz.size()
       <<",\"nontrivial_scc\":"<<nontrivial
       <<",\"largest_scc\":"<<largest
       <<",\"contradictory_vars\":"<<conflicts
       <<",\"certifiable_alias_candidates\":"<<alias.size()
       <<",\"binary_ratio\":"<<double(a.binary)/max(1,a.count)
       <<",\"cnf_parse_ms\":"<<parse_ms
       <<",\"total_scout_ms\":"<<elapsed(begin)
       <<",\"alias_map\":[";
   for(size_t k=0;k<alias.size();++k){
     if(k)cout<<",";
     cout<<"["<<alias[k].first<<","<<alias[k].second<<"]";
   }
   cout<<"]";
   if(first_conflict){
     cout<<",\"contradiction_witness_var\":"<<first_conflict
         <<",\"path_positive_to_negative\":";
     emit_path(path(a,first_conflict,-first_conflict));
     cout<<",\"path_negative_to_positive\":";
     emit_path(path(a,-first_conflict,first_conflict));
   }
   cout<<"}"<<endl;
   return 0;
 }catch(const exception& e){
   cerr<<e.what()<<endl;
   return 2;
 }
}
