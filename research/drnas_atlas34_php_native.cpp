// ATLAS34 native C++ conservative PHP substructure theorem gate (prospective paired test). Exact CNF subformula check, fallback to native solver.
// Theorem certificate is NOT LRAT. No family names, SHA or source labels used; conservative structural gate.
#include <algorithm>
#include <chrono>
#include <fstream>
#include <iostream>
#include <map>
#include <numeric>
#include <set>
#include <string>
#include <vector>
#include <unistd.h>
using namespace std;
static bool check(const vector<vector<int>>& clauses,int& p,int& h){
 vector<vector<int>> groups;
 for(auto&c:clauses)if(c.size()>=2&&all_of(c.begin(),c.end(),[](int x){return x>0;}))groups.push_back(c);
 p=(int)groups.size();if(p<3)return false;
 h=(int)groups[0].size();if(h<2||p<=h)return false;
 map<int,int> owner;vector<int> vars;
 for(int i=0;i<p;i++){
  if((int)groups[i].size()!=h)return false;
  set<int> local(groups[i].begin(),groups[i].end());
  if((int)local.size()!=h)return false;
  for(int v:groups[i]){if(owner.count(v))return false;owner[v]=i;vars.push_back(v);}
 }
 map<int,set<int>> adj;
 for(auto&c:clauses)if(c.size()==2&&c[0]<0&&c[1]<0){
  int a=-c[0],b=-c[1];
  if(owner.count(a)&&owner.count(b)&&owner[a]!=owner[b]){adj[a].insert(b);adj[b].insert(a);}
 }
 set<int> seen;
 int holes=0;
 for(int v:vars){
  if(seen.count(v))continue;
  set<int> component;vector<int> stack{v};
  while(!stack.empty()){
   int u=stack.back();stack.pop_back();
   if(!component.insert(u).second)continue;
   for(int w:adj[u])if(!component.count(w))stack.push_back(w);
  }
  if((int)component.size()!=p)return false;
  set<int> owners;
  for(int u:component){
   owners.insert(owner[u]);
   int neighbours=0;
   for(int w:component)if(w!=u&&adj[u].count(w))++neighbours;
   if(neighbours!=p-1)return false;
  }
  if((int)owners.size()!=p)return false;
  seen.insert(component.begin(),component.end());++holes;
 }
 return holes==h&&seen.size()==vars.size();
}

static bool check_substructure(const vector<vector<int>>& clauses,int& p,int& h){
 // Pick only connected candidate positive groups, not every positive
 // clause in the entire CNF. Every selected clause is an original clause.
 // All disjoint partitions are checked by the unchanged exact checker.
 map<int,vector<vector<int>>> by_width;
 for(const auto&c:clauses)
   if(c.size()>=2&&c.size()<=64&&
      all_of(c.begin(),c.end(),[](int x){return x>0;}))
       by_width[(int)c.size()].push_back(c);
 for(auto &bucket:by_width){
   const int width=bucket.first;
   const auto&g=bucket.second;
   if(g.size()<size_t(width+1)||g.size()>512)continue;
   map<int,int> owner;
   vector<char> ambiguous(g.size(),0);
   for(size_t i=0;i<g.size();++i){
     set<int> local(g[i].begin(),g[i].end());
     if(local.size()!=g[i].size()){ambiguous[i]=1;continue;}
     for(int v:g[i]){
       auto it=owner.find(v);
       if(it!=owner.end()){ambiguous[i]=1;ambiguous[it->second]=1;}
       else owner[v]=(int)i;
     }
   }
   vector<int> parent(g.size());iota(parent.begin(),parent.end(),0);
   auto find=[&](int x){while(parent[x]!=x){parent[x]=parent[parent[x]];x=parent[x];}return x;};
   for(const auto&c:clauses)if(c.size()==2&&c[0]<0&&c[1]<0){
      auto a=owner.find(-c[0]),b=owner.find(-c[1]);
      if(a!=owner.end()&&b!=owner.end()&&a->second!=b->second &&
         !ambiguous[a->second]&&!ambiguous[b->second]){
        int u=find(a->second),v=find(b->second);
        if(u!=v)parent[u]=v;
      }
   }
   map<int,vector<int>> components;
   for(size_t i=0;i<g.size();++i)if(!ambiguous[i])
      components[find((int)i)].push_back((int)i);
   for(const auto&kv:components){
      const auto& ids=kv.second;
      if(ids.size()<=size_t(width) || ids.size()>128)continue;
      vector<vector<int>> selected;
      selected.reserve(ids.size()+clauses.size());
      for(int i:ids)selected.push_back(g[i]);
      for(const auto&c:clauses)
         if(c.size()==2&&c[0]<0&&c[1]<0)selected.push_back(c);
      int pp=0,hh=0;
      if(check(selected,pp,hh)){p=pp;h=hh;return true;}
   }
 }
 return false;
}

int main(int argc,char**argv){
 if(argc<3){cerr<<"usage: drnas_php_native CNF native_solver [native solver args...]\n";return 2;}
 auto start=chrono::steady_clock::now();
 ifstream f(argv[1]);if(!f){cerr<<"CNF not readable\n";return 2;}
 string tok;int n=0,m=0;vector<vector<int>> cls;vector<int> clause;
 while(f>>tok){
  if(tok=="c"){string line;getline(f,line);continue;}
  if(tok=="p"){string kind;f>>kind>>n>>m;if(kind!="cnf"||n<1||m<0)return 2;continue;}
  int lit=0;try{lit=stoi(tok);}catch(...){return 2;}
  if(lit==0){cls.push_back(clause);clause.clear();}
  else{if(abs(lit)>n||n==0)return 2;clause.push_back(lit);}
 }
 if(!clause.empty()||(int)cls.size()!=m)return 2;
 // Conservative O(total literals) PHP prefilter. It rejects only cases
 // with no possible pigeon-positive clause (direct or unit-encoded), or
 // no negative binary exclusion. False negatives are possible for more
 // elaborate encodings; this is an optional experimental optimization.
 int positive=0, encoded=0, exclusions=0;
 vector<unsigned char> positive_unit(n+1,0);
 for(const auto& c:cls)if(c.size()==1&&c[0]>0)positive_unit[c[0]]=1;
 for(const auto& c:cls){
   if(c.size()==2&&c[0]<0&&c[1]<0)++exclusions;
   if(c.size()<2)continue;
   int neg=0,negvar=0;
   for(int lit:c)if(lit<0){++neg;negvar=-lit;}
   if(neg==0)++positive;
   else if(neg==1&&c.size()>=3&&positive_unit[negvar])++encoded;
 }
 if(exclusions==0||positive+encoded<3){
   vector<char*> fallback{argv[2],argv[1]};
   for(int i=3;i<argc;i++)fallback.push_back(argv[i]);
   fallback.push_back(nullptr);
   execvp(argv[2],fallback.data());perror("native fallback execvp");return 127;
 }
 // Sound bounded unit propagation before structural detection:
 // simplify under explicitly forced unit literals; preserve the original
 // CNF for the fallback solver and never infer SAT from simplification.
 // A contradiction under units proves UNSAT, but this gate only accepts PHP.
 vector<int> units(n+1,0);
 bool conflict=false;
 for(int round=0;round<3&&!conflict;round++){
  bool changed=false;
  for(const auto& c:cls){
   bool satisfied=false;int unassigned=0,last=0;
   for(int lit:c){
    int val=units[abs(lit)];
    if(val==0){++unassigned;last=lit;}
    else if(val==(lit>0?1:-1)){satisfied=true;break;}
   }
   if(satisfied)continue;
   if(unassigned==0){conflict=true;break;}
   if(unassigned==1){
    int v=abs(last),sign=last>0?1:-1;
    if(units[v]&&units[v]!=sign){conflict=true;break;}
    if(!units[v]){units[v]=sign;changed=true;}
   }
  }
  if(!changed)break;
 }
 vector<vector<int>> reduced;
 if(!conflict){
  for(const auto& c:cls){
   bool satisfied=false;vector<int> out;
   for(int lit:c){
    int val=units[abs(lit)];
    if(val==(lit>0?1:-1)){satisfied=true;break;}
    if(val==0)out.push_back(lit);
   }
   if(!satisfied)reduced.push_back(move(out));
  }
 }
 int p=0,h=0;
 if(!conflict&&(check(reduced,p,h)||check_substructure(reduced,p,h))){
  auto micros=chrono::duration_cast<chrono::microseconds>(chrono::steady_clock::now()-start).count();
  cout<<"s UNSATISFIABLE\n";
  cout<<"c ATLAS34_PHP_THEOREM pigeons="<<p<<" holes="<<h<<" detector_us="<<micros
      <<" independent_LRAT=0\n";
  return 20;
 }
 vector<char*> args;args.push_back(argv[2]);args.push_back(argv[1]);
 for(int i=3;i<argc;i++)args.push_back(argv[i]);
 args.push_back(nullptr);
 execvp(argv[2],args.data());perror("native fallback execvp");return 127;
}
