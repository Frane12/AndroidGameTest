// DRNAS SRE2-A: source-certified exact-one, color-conflict graph, connected
// components and clique obstruction. No heuristic UNSAT assertion.
#pragma once
#include <set>
#include <map>
#include <queue>
#include <functional>
namespace drnas {
struct SRE2A {
 int exact_one=0, at_most_one=0, graph_vertices=0, graph_edges=0;
 int components=0, largest_clique=0, colors=0;
 bool certified_unsat=false, abstained=false;
 std::vector<std::vector<int>> groups;
 std::vector<std::pair<int,int>> conflicts;
 double scan_s=0;
};
static SRE2A sre2a_scan(const CNF& f){
 auto started=Clock::now();
 SRE2A out;
 if(f.vars>20000 || f.clauses.size()>100000){out.abstained=true;return out;}
 // Only a POSITIVE source clause can certify the at-least-one half.
 // Every pairwise negative clause must be present to certify at-most-one.
 std::set<std::pair<int,int>> negative;
 std::set<std::vector<int>> positive;
 for(const auto& c:f.clauses){
  if(c.size()==2 && c[0]<0 && c[1]<0 && c[0]!=c[1]){
   int a=-c[0],b=-c[1];
   if(a>b)std::swap(a,b);
   negative.insert({a,b});
  }
  if(c.size()>=2 && c.size()<=8){
   bool all_positive=true;
   std::vector<int> v=c;
   for(int l:v)if(l<=0 || l>f.vars)all_positive=false;
   if(all_positive){
    std::sort(v.begin(),v.end());
    if(std::adjacent_find(v.begin(),v.end())==v.end())positive.insert(v);
   }
  }
 }
 for(const auto& g:positive){
  bool complete=true;
  for(size_t i=0;i<g.size();++i)
   for(size_t j=i+1;j<g.size();++j)
    if(!negative.count({g[i],g[j]}))complete=false;
  if(complete){out.groups.push_back(g);++out.exact_one;++out.at_most_one;}
 }
 // Conservative coloring recognition: disjoint, equal-width exact-one
 // groups, with ALL same-index exclusion clauses for every inferred edge.
 // No assumption about semantics, only literal positions in each group.
 const int k=out.groups.empty()?0:(int)out.groups.front().size();
 bool uniform=k>=2 && k<=6;
 std::vector<int> used(f.vars+1,0);
 for(const auto& g:out.groups){
  if((int)g.size()!=k)uniform=false;
  for(int v:g)if(++used[v]!=1)uniform=false;
 }
 if(uniform){
  const int n=(int)out.groups.size();
  out.colors=k;out.graph_vertices=n;
  std::vector<std::vector<int>> adj(n);
  for(int a=0;a<n;++a)for(int b=a+1;b<n;++b){
   bool complete=true;
   for(int c=0;c<k;++c){
    int x=out.groups[a][c],y=out.groups[b][c];
    if(x>y)std::swap(x,y);
    if(!negative.count({x,y})){complete=false;break;}
   }
   if(complete){
    out.conflicts.push_back({a,b});++out.graph_edges;
    adj[a].push_back(b);adj[b].push_back(a);
   }
  }
  std::vector<uint8_t> visited(n,0);
  for(int i=0;i<n;++i)if(!visited[i]){
   ++out.components;std::queue<int> q;q.push(i);visited[i]=1;
   while(!q.empty()){
    int u=q.front();q.pop();
    for(int v:adj[u])if(!visited[v]){visited[v]=1;q.push(v);}
   }
  }
  // A clique of k+1 vertices forces k+1 different colors. This
  // conclusion is sound even if extra CNF constraints exist.
  // Limit exhaustive clique checking to <=60 vertices and <=6 colors.
  if(n<=60){
   std::vector<std::vector<uint8_t>> matrix(n,std::vector<uint8_t>(n,0));
   for(auto [a,b]:out.conflicts)matrix[a][b]=matrix[b][a]=1;
   std::vector<int> clique;
   size_t visits=0;
   std::function<void(int)> extend=[&](int start){
    if(out.certified_unsat || ++visits>200000)return;
    out.largest_clique=std::max(out.largest_clique,(int)clique.size());
    if((int)clique.size()>k){out.certified_unsat=true;return;}
    for(int v=start;v<n;++v){
     bool good=true;
     for(int u:clique)if(!matrix[u][v]){good=false;break;}
     if(!good)continue;
     clique.push_back(v);extend(v+1);clique.pop_back();
     if(out.certified_unsat || visits>200000)return;
    }
   };
   extend(0);
  }
 }
 out.scan_s=std::chrono::duration<double>(Clock::now()-started).count();
 return out;
}
} // namespace drnas
