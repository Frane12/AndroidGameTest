// DRNAS DECOMP1: exact incidence-graph articulation screening (no solving).
// Removing an articulation variable separates the CNF into conditionally
// independent clause components. Only a source-graph diagnostic, not a solver.
#include <algorithm>
#include <chrono>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <numeric>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>
using namespace std;
using Clock=chrono::steady_clock;
using Clause=vector<int>;
struct Deadline {
 Clock::time_point until;
 explicit Deadline(int ms):until(Clock::now()+chrono::milliseconds(ms)){}
 void check()const {if(Clock::now()>until)throw runtime_error("time_budget");}
};
struct CNF {int n=0,declared=-1;vector<Clause> cs;long long incidences=0;};
static CNF parse(const string &path,const Deadline& d){
 ifstream f(path);if(!f)throw runtime_error("input_missing");
 CNF z;string line;Clause part;size_t lines=0;
 while(getline(f,line)){
   if((++lines&255)==0)d.check();
   auto k=line.find_first_not_of(" \t\r");
   if(k==string::npos||line[k]=='c'||line[k]=='%')continue;
   if(line[k]=='p'){
     istringstream is(line.substr(k));string marker,fmt;
     int n,m;is>>marker>>fmt>>n>>m;
     if(z.declared!=-1||fmt!="cnf"||n<0||m<0||n>400000||m>400000)
       throw runtime_error("header_unsupported");
     z.n=n;z.declared=m;continue;
   }
   if(z.declared<0)throw runtime_error("no_header");
   istringstream is(line.substr(k));long long lit;
   while(is>>lit){
     if(lit==0){
       sort(part.begin(),part.end());
       part.erase(unique(part.begin(),part.end()),part.end());
       z.incidences+=part.size();
       if(z.incidences>2200000LL)throw runtime_error("incidence_cap");
       z.cs.push_back(std::move(part));part.clear();
       if(z.cs.size()>size_t(z.declared))throw runtime_error("clause_count");
     } else {
       if(llabs(lit)>z.n)throw runtime_error("literal_out_of_range");
       part.push_back(int(llabs(lit))); // signed polarity irrelevant to incidence
     }
   }
 }
 if(z.declared<0||!part.empty()||z.cs.size()!=size_t(z.declared))
   throw runtime_error("bad_dimacs");
 d.check();return z;
}
struct Candidate {
 int var=0,component_clauses=0;
 vector<int> parts;
 int second=0;
};
struct Result {
 int n=0,m=0,clause_components=0,large_components=0,articulation_vars=0;
 long long edges=0;
 Candidate best;
};
static Result scan(const CNF &f,const Deadline& d,int min_clause_part=10){
 const int n=f.n,m=int(f.cs.size()),nn=n+m;
 if(nn>800000)throw runtime_error("node_cap");
 vector<vector<int>> g(nn);
 for(int ci=0;ci<m;++ci){
   if((ci&255)==0)d.check();
   for(int v:f.cs[ci]){
     int a=v-1,b=n+ci;
     g[a].push_back(b);g[b].push_back(a);
   }
 }
 vector<int> tin(nn,-1),low(nn),par(nn,-1),cur(nn),sub(nn,0),comp(nn,-1),roots;
 vector<vector<int>> split_children(n);
 int timer=0,cid=0;
 vector<int> totals;
 for(int root=0;root<nn;++root){
   if(tin[root]!=-1)continue;
   int sizeclauses=0;
   vector<int> st={root};
   tin[root]=low[root]=timer++;
   sub[root]=(root>=n);
   comp[root]=cid;
   while(!st.empty()){
     if((timer&4095)==0)d.check();
     int u=st.back();
     if(cur[u]<int(g[u].size())){
       int v=g[u][cur[u]++];
       if(v==par[u])continue;
       if(tin[v]<0){
         par[v]=u;
         tin[v]=low[v]=timer++;
         sub[v]=(v>=n);
         comp[v]=cid;
         st.push_back(v);
       }else low[u]=min(low[u],tin[v]);
     }else{
       st.pop_back();
       if(par[u]!=-1){
         int p=par[u];
         if(p<n&&low[u]>=tin[p])split_children[p].push_back(sub[u]);
         sub[p]+=sub[u];
         low[p]=min(low[p],low[u]);
       }
     }
   }
   totals.push_back(sub[root]);
   if(sub[root]>0){++sizeclauses;}
   (void)sizeclauses;
   ++cid;
 }
 Result r;r.n=n;r.m=m;r.edges=f.incidences;
 for(int c:totals) {
   if(c>0)++r.clause_components;
   if(c>=min_clause_part)++r.large_components;
 }
 for(int v=0;v<n;++v){
   if((v&4095)==0)d.check();
   const auto &children=split_children[v];
   if(children.empty())continue;
   int all=totals[comp[v]],separated=0;
   vector<int> parts;
   for(int ct:children){separated+=ct;if(ct>0)parts.push_back(ct);}
   int remaining=all-separated;
   if(remaining>0)parts.push_back(remaining);
   if(parts.size()>=2)++r.articulation_vars;
   sort(parts.begin(),parts.end(),greater<int>());
   int useful=0;for(int x:parts)if(x>=min_clause_part)++useful;
   if(useful<2)continue;
   int score=parts[1];
   if(score>r.best.second || (score==r.best.second && v+1<r.best.var)){
     r.best={v+1,all,parts,score};
   }
 }
 return r;
}
static void print(const Result&r){
 cout<<"DECOMP1_SCAN {\"status\":\"OK\",\"vars\":"<<r.n<<",\"clauses\":"<<r.m
     <<",\"incidence_edges\":"<<r.edges
     <<",\"clause_components\":"<<r.clause_components
     <<",\"large_components\":"<<r.large_components
     <<",\"articulation_variables\":"<<r.articulation_vars
     <<",\"best_separator_var\":"<<r.best.var
     <<",\"best_separator_component_clauses\":"<<r.best.component_clauses
     <<",\"best_second_largest_part\":"<<r.best.second
     <<",\"best_clause_parts\":[";
 for(size_t i=0;i<r.best.parts.size();++i){
   if(i)cout<<",";
   cout<<r.best.parts[i];
 }
 cout<<"]}\n";
}
static void selftest(){
 Deadline d(10000);
 CNF f;f.n=4;f.cs={{1,2},{1,2},{1,3},{1,3},{4}};
 f.incidences=9;
 auto r=scan(f,d,2);
 if(r.clause_components!=2||r.best.var!=1||r.best.second!=2||
    r.best.parts.size()!=2 || r.best.parts[0]!=2)
     throw runtime_error("articulation_selftest_failed");
 CNF g;g.n=3;g.cs={{1,2,3},{1,2,3}};g.incidences=6;
 auto z=scan(g,d,1);
 if(z.best.var!=0)throw runtime_error("biconnected_selftest_failed");
 cout<<"DECOMP1_SELFTEST_PASS {\"articulation_separator\":1,\"two_independent_clause_parts\":true}\n";
}
int main(int argc,char **argv){
 try{
   if(argc==2&&string(argv[1])=="selftest"){selftest();return 0;}
   if(argc!=3)throw runtime_error("usage source.cnf budget_ms");
   int ms=stoi(argv[2]);if(ms<100||ms>10000)throw runtime_error("invalid_budget");
   Deadline d(ms);
   auto f=parse(argv[1],d);
   print(scan(f,d,10));
   return 0;
 }catch(const exception &e){
   cout<<"DECOMP1_ABSTAIN {\"reason\":\""<<e.what()<<"\"}\n";
   return 75;
 }
}
