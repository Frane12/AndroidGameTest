// ATLAS28 native C++ theorem gate (prospective paired test). Exact CNF subformula check, fallback to native solver.
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
 int p=0,h=0;
 if(check(cls,p,h)){
  auto micros=chrono::duration_cast<chrono::microseconds>(chrono::steady_clock::now()-start).count();
  cout<<"s UNSATISFIABLE\n";
  cout<<"c ATLAS28_PHP_THEOREM pigeons="<<p<<" holes="<<h<<" detector_us="<<micros
      <<" independent_LRAT=0\n";
  return 20;
 }
 vector<char*> args;args.push_back(argv[2]);args.push_back(argv[1]);
 for(int i=3;i<argc;i++)args.push_back(argv[i]);
 args.push_back(nullptr);
 execvp(argv[2],args.data());perror("native fallback execvp");return 127;
}
