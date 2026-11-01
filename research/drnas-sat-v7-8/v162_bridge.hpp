// DRNAS V16.2: proof-origin SCC -> full XOR pattern -> GF(2) -> units.
// Exact inferences only. This module does not issue SAT or UNSAT decisions:
// any contradiction or incomplete evidence returns to original Kissat API.
// Input type Cnf and libkissat bridge are defined by the including solver.
#ifndef DRNAS_V162_BRIDGE_HPP
#define DRNAS_V162_BRIDGE_HPP
#include <map>
#include <set>
#include <unordered_map>
#include <vector>
#include <stack>
#include <algorithm>
#include <cstdint>

struct V162Row { std::set<int> vars; int rhs=0; };
struct V162Relations {
 bool contradiction=false;
 unsigned full_xor=0, scc_aliases=0, source_units=0, learned_units=0;
 std::vector<int> units;
};
static inline void v162_xor(V162Row& a,const V162Row& b) {
 std::set<int> result;
 std::set_symmetric_difference(a.vars.begin(),a.vars.end(),
   b.vars.begin(),b.vars.end(),std::inserter(result,result.end()));
 a.vars.swap(result); a.rhs^=b.rhs;
}
static V162Relations v162_derive(const Cnf& f) {
 V162Relations out;
 if(f.n<=0 || f.n>512 || f.clauses.size()>12000)return out;
 const int n=f.n;
 const int nodes=2*n;
 auto litnode=[](int x){return 2*(std::abs(x)-1)+(x<0);};
 std::vector<std::vector<int>> edges(nodes),rev(nodes);
 std::map<std::vector<int>,uint64_t> supports;
 std::vector<V162Row> rows;
 unsigned binary=0;
 for(const auto& clause:f.clauses) {
  const int w=(int)clause.size();
  if(w==1){
   V162Row row;row.vars.insert(std::abs(clause[0]));row.rhs=int(clause[0]>0);
   rows.push_back(std::move(row));++out.source_units;
  }
  if(w==2){
   int a=clause[0],b=clause[1];
   int u=litnode(-a),v=litnode(b);
   edges[u].push_back(v);rev[v].push_back(u);
   u=litnode(-b);v=litnode(a);
   edges[u].push_back(v);rev[v].push_back(u);
   ++binary;
  }
  if(w>=2&&w<=5){
   std::vector<int> key;key.reserve(w);
   for(int x:clause)key.push_back(std::abs(x));
   std::sort(key.begin(),key.end());
   if(std::adjacent_find(key.begin(),key.end())!=key.end())continue;
   unsigned mask=0;
   for(int j=0;j<w;j++){
    int var=key[j];
    for(int lit:clause)if(lit==-var){mask|=(1u<<j);break;}
   }
   supports[key]|=(uint64_t(1)<<mask);
  }
 }
 // Full (not partial or guessed) half-cube of CNF clauses => parity.
 for(const auto& item:supports){
  const auto& vars=item.first;
  const int width=int(vars.size());
  const int total=1<<width;
  for(int forbidden_parity=0;forbidden_parity<2;forbidden_parity++){
   uint64_t required=0;
   for(int mask=0;mask<total;mask++){
    int p=__builtin_popcount((unsigned)mask)&1;
    if(p==forbidden_parity)required|=uint64_t(1)<<mask;
   }
   if((item.second&required)!=required)continue;
   V162Row row;
   row.vars.insert(vars.begin(),vars.end());
   row.rhs=1-forbidden_parity;
   rows.push_back(std::move(row));++out.full_xor;
  }
 }
 if(rows.empty())return out;
 // Kosaraju SCC of the original binary implication graph.
 // Edges from (a OR b) are (~a => b) and (~b => a).
 std::vector<unsigned char> seen(nodes,0);
 std::vector<int> order;order.reserve(nodes);
 for(int i=0;i<nodes;i++)if(!seen[i]){
  std::vector<std::pair<int,size_t>> st{{i,0}};seen[i]=1;
  while(!st.empty()){
   auto& top=st.back();
   if(top.second<edges[top.first].size()){
    int v=edges[top.first][top.second++];
    if(!seen[v]){seen[v]=1;st.push_back({v,0});}
   } else {order.push_back(top.first);st.pop_back();}
  }
 }
 std::vector<int> comp(nodes,-1);
 int nr=0;
 for(auto it=order.rbegin();it!=order.rend();it++){
  if(comp[*it]>=0)continue;
  std::vector<int> q{*it};comp[*it]=nr;
  while(!q.empty()){
   int u=q.back();q.pop_back();
   for(int v:rev[u])if(comp[v]<0){comp[v]=nr;q.push_back(v);}
  }
  ++nr;
 }
 struct Alias {int root=0; int invert=0;};
 std::vector<Alias> alias(n+1);
 std::map<int,int> root_of_component_pair;
 for(int v=1;v<=n;v++){
  int pos=comp[2*(v-1)],neg=comp[2*(v-1)+1];
  if(pos==neg){out.contradiction=true;return out;}
  int id=std::min(pos,neg);
  auto it=root_of_component_pair.find(id);
  if(it==root_of_component_pair.end()){
   root_of_component_pair[id]=v;alias[v]={v,0};
  } else {
   int root=it->second;
   int rp=comp[2*(root-1)];
   alias[v]={root,int(rp!=pos)};
   ++out.scc_aliases;
  }
 }
 // Substitute x = root XOR inversion into each exact parity equation.
 std::vector<V162Row> normalized;
 normalized.reserve(rows.size());
 for(auto& row:rows){
  V162Row mapped;mapped.rhs=row.rhs;
  for(int v:row.vars){
   Alias a=alias[v];mapped.rhs^=a.invert;
   auto it=mapped.vars.find(a.root);
   if(it==mapped.vars.end())mapped.vars.insert(a.root);
   else mapped.vars.erase(it);
  }
  normalized.push_back(std::move(mapped));
 }
 // Sparse GF2 elimination; all rows have full-source exact proof origins.
 // Work cap is fixed so arbitrary CNF cannot force expensive preflight.
 if(normalized.size()>1024 || supports.size()>10000)return V162Relations{};
 std::map<int,V162Row> basis;
 for(auto row:normalized){
  while(!row.vars.empty()){
   int pivot=*row.vars.begin();
   auto b=basis.find(pivot);
   if(b==basis.end()){basis.emplace(pivot,std::move(row));break;}
   v162_xor(row,b->second);
  }
  if(row.vars.empty()&&row.rhs){
   out.contradiction=true;return out;
  }
 }
 // Back-substitution makes hidden units visible, even across XOR chains.
 for(auto it=basis.rbegin();it!=basis.rend();++it){
  int pivot=it->first;
  for(auto earlier=basis.begin();earlier!=basis.end()&&earlier->first<pivot;++earlier){
   if(earlier->second.vars.count(pivot))v162_xor(earlier->second,it->second);
  }
 }
 std::map<int,int> assigned;
 for(const auto& [pivot,row]:basis)if(row.vars.size()==1){
  assigned[pivot]=row.rhs;
 }
 // Propagate proven root value through all SCC-equivalent literals.
 for(int v=1;v<=n;v++){
  const Alias a=alias[v];
  auto it=assigned.find(a.root);
  if(it!=assigned.end()){
   int bit=it->second ^ a.invert;
   out.units.push_back(bit?v:-v);
   if(out.units.size()>=128)break;
  }
 }
 out.learned_units=(unsigned)out.units.size();
 return out;
}
#endif
