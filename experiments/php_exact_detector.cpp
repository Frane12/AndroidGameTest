// Standalone exact-PHP CNF recognizer; returns UNKNOWN for all other encodings.
// Compile: g++ -O2 -std=c++17 php_exact_detector.cpp -o php_exact_detector
#include <algorithm>
#include <iostream>
#include <map>
#include <numeric>
#include <string>
#include <vector>
using namespace std;
bool php_unsat(int V, const vector<vector<int>>& clauses) {
  vector<vector<int>> adj(V+1), positive;
  long long edges=0;
  for(const auto& c:clauses) {
    if(c.size()==2 && c[0]<0 && c[1]<0 && c[0]!=c[1]) {
      int a=-c[0],b=-c[1];
      if(a<1||a>V||b<1||b>V) return false;
      adj[a].push_back(b); adj[b].push_back(a); ++edges;
    } else {
      if(c.empty()) return false;
      for(int x:c) if(x<1||x>V) return false;
      positive.push_back(c);
    }
  }
  int n=positive.size();
  if(n<2) return false;
  map<vector<int>,vector<int>> groups;
  for(int i=1;i<=V;++i) {
    auto& a=adj[i]; sort(a.begin(),a.end());
    if(unique(a.begin(),a.end())!=a.end()) return false;
    vector<int> key=a;
    key.insert(lower_bound(key.begin(),key.end(),i),i);
    groups[key].push_back(i);
  }
  int m=groups.size();
  if(n<=m || 1LL*n*m!=V || edges!=1LL*m*n*(n-1)/2) return false;
  vector<int> gid(V+1,-1); int g=0;
  for(const auto& [key,members]:groups) {
    if((int)members.size()!=n || key!=members) return false;
    for(int x:members) gid[x]=g;
    ++g;
  }
  vector<int> seen(V+1,0);
  for(const auto& c:positive) {
    if((int)c.size()!=m) return false;
    vector<char> hit(m,0);
    for(int x:c) {
      if(seen[x]++ || hit[gid[x]]) return false;
      hit[gid[x]]=1;
    }
  }
  for(int i=1;i<=V;++i) if(seen[i]!=1) return false;
  return true;
}
int main() {
  string token; int V=0,C=0; vector<vector<int>> clauses;
  while(cin>>token) {
    if(token=="c") { string s; getline(cin,s); continue; }
    if(token=="p") {string fmt; cin>>fmt>>V>>C; if(fmt!="cnf"||V<=0||C<0) return 2;break;}
    return 2;
  }
  if(V<=0) return 2;
  clauses.reserve(C);
  for(int i=0;i<C;++i) {
    vector<int> c;int x;
    while(cin>>x && x!=0) c.push_back(x);
    if(!cin) return 2;
    clauses.push_back(move(c));
  }
  // Never claim SAT. Exact recognized pigeonhole contradictions only.
  if(php_unsat(V,clauses)) {cout<<"s UNSATISFIABLE\n";return 20;}
  cout<<"s UNKNOWN\n";return 0;
}
