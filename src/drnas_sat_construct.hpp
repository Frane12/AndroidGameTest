#pragma once
// DRNAS SAT-CONSTRUCT-NATIVE1: conservative SAT WITNESS construction.
// These detectors can return only a FULL, original-CNF-verified SAT model
// or UNKNOWN. They NEVER infer UNSAT. No second solver, no thread/portfolio.
// All functions have a monotonic wall-clock deadline and source size guards.
#include <algorithm>
#include <bit>
#include <chrono>
#include <cstdint>
#include <functional>
#include <map>
#include <numeric>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

namespace satconstruct {
using Clock=std::chrono::steady_clock;
using CNF=std::vector<std::vector<int>>;
struct Outcome {
  std::vector<int8_t> model;
  std::string method="UNKNOWN";
  int equations=0, alo_groups=0, resource_components=0;
  bool sat() const {return method!="UNKNOWN";}
};
struct Limits {
  double max_ms=20.0;
  int max_vars=15000, max_clauses=130000, max_literals=600000;
};
inline bool due(Clock::time_point deadline) {return Clock::now()>=deadline;}
inline bool verify(int n,const CNF& f,const std::vector<int8_t>& model) {
  if ((int)model.size()!=n)return false;
  for (const auto& clause:f) {
    bool satisfied=false;
    for (int lit:clause) {
      int v=(lit>0?lit:-lit)-1;
      if(v<0||v>=n)return false;
      if(model[v]==(lit>0?1:-1)) {satisfied=true;break;}
    }
    if(!satisfied)return false;
  }
  return true;
}
inline bool finish(int n,const CNF& f, std::vector<int8_t>&& model,
                   const char* method, Outcome& out) {
  if(!verify(n,f,model))return false;
  out.model=std::move(model);out.method=method;return true;
}
inline bool try_horn(int n,const CNF& f,Outcome& out,Clock::time_point deadline) {
  std::vector<int> head(f.size(),-1),left(f.size(),0);
  std::vector<std::vector<int>> occ(n);
  std::vector<int8_t> model(n,-1);
  for(size_t i=0;i<f.size();++i) {
    if((i&511)==0&&due(deadline))return false;
    for(int l:f[i]){
      const int v=std::abs(l)-1;
      if(l>0) {
        if(head[i]>=0)return false; // Not Horn.
        head[i]=v;
      } else {
        occ[v].push_back((int)i); ++left[i];
      }
    }
  }
  std::vector<int> queue;
  auto activate=[&](int i)->bool {
    if(head[i]<0)return false; // violated negative-only clause: UNKNOWN.
    const int v=head[i];
    if(model[v]<0){model[v]=1;queue.push_back(v);}
    return true;
  };
  for(size_t i=0;i<f.size();++i)if(!left[i]&&!activate((int)i))return false;
  for(size_t q=0;q<queue.size();++q) {
    if((q&255)==0&&due(deadline))return false;
    for(int ci:occ[queue[q]])if(!--left[ci]&&!activate(ci))return false;
  }
  return finish(n,f,std::move(model),"HORN",out);
}
inline bool try_twosat(int n,const CNF& f,Outcome& out,Clock::time_point deadline){
  for(const auto& c:f)if(c.empty()||c.size()>2)return false;
  auto node=[](int lit) {return 2*(std::abs(lit)-1)+(lit<0);};
  std::vector<std::vector<int>> g(2*n),rg(2*n);
  auto edge=[&](int a,int b){g[a].push_back(b);rg[b].push_back(a);};
  for(size_t i=0;i<f.size();++i){
    if((i&511)==0&&due(deadline))return false;
    int a=node(f[i][0]);
    if(f[i].size()==1)edge(a^1,a);
    else {
      int b=node(f[i][1]);edge(a^1,b);edge(b^1,a);
    }
  }
  std::vector<uint8_t> seen(2*n,0);
  std::vector<int> order;order.reserve(2*n);
  for(int start=0;start<2*n;++start){
    if(seen[start])continue;
    std::vector<std::pair<int,size_t>> stack{{start,0}};
    seen[start]=1;
    while(!stack.empty()){
      int v=stack.back().first; size_t& j=stack.back().second;
      if(j<g[v].size()){
        int w=g[v][j++];
        if(!seen[w]){seen[w]=1;stack.push_back({w,0});}
      }else{order.push_back(v);stack.pop_back();}
    }
    if((start&255)==0&&due(deadline))return false;
  }
  std::vector<int> comp(2*n,-1); int components=0;
  for(auto it=order.rbegin();it!=order.rend();++it){
    if(comp[*it]>=0)continue;
    std::vector<int> stack{*it};comp[*it]=components;
    while(!stack.empty()){
      int v=stack.back();stack.pop_back();
      for(int w:rg[v])if(comp[w]<0){comp[w]=components;stack.push_back(w);}
    }
    ++components;
    if((components&127)==0&&due(deadline))return false;
  }
  std::vector<int8_t> model(n,-1);
  for(int i=0;i<n;++i){
    if(comp[2*i]==comp[2*i+1])return false; // UNKNOWN, not UNSAT.
    model[i]=(comp[2*i]>comp[2*i+1])?1:-1;
  }
  return finish(n,f,std::move(model),"2SAT",out);
}
struct DSU {
  std::vector<int> parent,size;
  explicit DSU(int n):parent(n),size(n,1){std::iota(parent.begin(),parent.end(),0);}
  int root(int x){while(parent[x]!=x){parent[x]=parent[parent[x]];x=parent[x];}return x;}
  void join(int a,int b){
    a=root(a);b=root(b);if(a==b)return;
    if(size[a]<size[b])std::swap(a,b);
    parent[b]=a;size[a]+=size[b];
  }
};
inline bool try_matching(int n,const CNF& f,Outcome& out,Clock::time_point deadline){
  std::vector<std::vector<int>> groups;
  std::vector<std::pair<int,int>> mutex;
  std::vector<int> owner(n,-1);
  std::vector<uint8_t> banned(n,0);
  int64_t selected=0;
  for(size_t ci=0;ci<f.size();++ci){
    if((ci&511)==0&&due(deadline))return false;
    const auto& c=f[ci];
    if(c.empty())return false;
    const bool positive=std::all_of(c.begin(),c.end(),[](int lit){return lit>0;});
    if(positive){
      std::vector<int> group=c;
      std::sort(group.begin(),group.end());
      group.erase(std::unique(group.begin(),group.end()),group.end());
      for(int lit:group) {
        if(owner[lit-1]>=0)return false; // overlapping ALO not supported
        owner[lit-1]=(int)groups.size();
      }
      selected+=group.size();
      if(selected>12000)return false;
      groups.push_back(std::move(group));
    } else if(c.size()==2&&c[0]<0&&c[1]<0) {
      mutex.push_back({-c[0]-1,-c[1]-1});
    } else if(c.size()==1&&c[0]<0) banned[-c[0]-1]=1;
    else return false;
  }
  if(groups.empty())return false;
  DSU uf(n);
  for(auto [a,b]:mutex){
    if(owner[a]>=0&&owner[b]>=0&&owner[a]!=owner[b])uf.join(a,b);
  }
  std::vector<std::vector<std::pair<int,int>>> options(groups.size());
  std::unordered_map<int,int> key;key.reserve((size_t)selected);
  for(size_t g=0;g<groups.size();++g){
    std::map<int,int> local;
    for(int v:groups[g]){
      if(banned[v-1])continue;
      const int rep=uf.root(v-1);
      auto [it,added]=key.emplace(rep,(int)key.size());
      local.emplace(it->second,v);
    }
    if(local.empty())return false;
    for(auto [resource,lit]:local) options[g].push_back({resource,lit});
  }
  const int resources=(int)key.size();
  std::vector<int> occupied(resources,-1),pick(groups.size(),-1);
  std::vector<int> order(groups.size());std::iota(order.begin(),order.end(),0);
  std::stable_sort(order.begin(),order.end(),[&](int a,int b){
    return options[a].size()<options[b].size();});
  // Maximum bipartite matching: distinct component chosen for each ALO group.
  std::function<bool(int,std::vector<uint8_t>&)> augment=
      [&](int job,std::vector<uint8_t>& visited)->bool{
    if(due(deadline))return false;
    for(auto [resource,lit]:options[job]){
      if(visited[resource])continue;
      visited[resource]=1;
      int other=occupied[resource];
      if(other<0||augment(other,visited)){
        occupied[resource]=job;pick[job]=lit;return true;
      }
    }
    return false;
  };
  for(int job:order){
    std::vector<uint8_t> visited(resources,0);
    if(!augment(job,visited))return false;
  }
  std::vector<int8_t> model(n,-1);
  for(int lit:pick)if(lit>0)model[lit-1]=1;
  if(finish(n,f,std::move(model),"MATCH",out)){
    out.alo_groups=(int)groups.size();out.resource_components=resources;return true;
  }
  return false;
}
// Detect complete k-variable XOR CNF patterns (k=2..4), including signed
// literals, as necessary GF(2) rows. Also derive a sound parity row from a
// source-backed exact-one ALO + complete pairwise source mutex.
// Candidate solutions are independently verified against the WHOLE CNF.
inline bool try_gf2(int n,const CNF& f,Outcome& out,Clock::time_point deadline){
  if(n>2048||f.size()>25000)return false;
  struct Blocks{uint16_t mask=0;};
  std::map<std::vector<int>,Blocks> patterns;
  std::map<std::pair<int,int>,bool> negatives;
  for(size_t i=0;i<f.size();++i){
    if((i&255)==0&&due(deadline))return false;
    const auto& c=f[i];int k=(int)c.size();
    if(k==2&&c[0]<0&&c[1]<0){
      int a=-c[0],b=-c[1];if(a>b)std::swap(a,b);
      negatives[{a,b}]=true;
    }
    if(k<2||k>4)continue;
    std::vector<std::pair<int,int>> sorted;
    for(int lit:c)sorted.push_back({std::abs(lit),lit<0?1:0});
    std::sort(sorted.begin(),sorted.end());
    bool distinct=true;
    for(int j=1;j<k;++j)if(sorted[j].first==sorted[j-1].first)distinct=false;
    if(!distinct)continue;
    std::vector<int> vars;vars.reserve(k);
    int forbidden=0;
    for(int j=0;j<k;++j){
      vars.push_back(sorted[j].first);
      forbidden|=sorted[j].second<<j;
    }
    patterns[vars].mask|=uint16_t(1U<<forbidden);
  }
  std::vector<std::pair<std::vector<int>,int>> equations;
  for(auto& [vars,block]:patterns){
    int k=(int)vars.size();
    if(std::popcount((unsigned)block.mask)!=(1<<(k-1)))continue;
    int parity=-1;bool complete=true;
    for(int assignment=0;assignment<(1<<k);++assignment){
      if(!(block.mask&(1U<<assignment)))continue;
      int p=std::popcount((unsigned)assignment)&1;
      if(parity<0)parity=p;
      if(p!=parity){complete=false;break;}
    }
    if(complete) equations.push_back({vars,parity^1});
  }
  for(const auto& c:f){
    if(c.size()==1)equations.push_back({{std::abs(c[0])},c[0]>0?1:0});
    else if(c.size()>=3 && c.size()<=32 &&
            std::all_of(c.begin(),c.end(),[](int l){return l>0;})){
      bool exact=true;
      for(size_t i=0;i<c.size()&&exact;++i){
        for(size_t j=i+1;j<c.size();++j){
          int a=c[i],b=c[j];if(a==b){exact=false;break;}
          if(a>b)std::swap(a,b);
          if(!negatives.count({a,b})){exact=false;break;}
        }
      }
      if(exact)equations.push_back({c,1});
    }
  }
  if(equations.empty()||equations.size()>6000)return false;
  const int words=(n+1+63)/64;
  std::vector<std::vector<uint64_t>> pivots(n);
  std::vector<int> pivot_col;
  auto get=[](const std::vector<uint64_t>&row,int c) {
    return (row[c>>6]>>(c&63))&1ULL;
  };
  for(size_t i=0;i<equations.size();++i){
    if((i&63)==0&&due(deadline))return false;
    std::vector<uint64_t> row(words,0);
    for(int v:equations[i].first)row[(v-1)>>6]^=1ULL<<((v-1)&63);
    if(equations[i].second)row[n>>6]^=1ULL<<(n&63);
    bool installed=false;
    for(int col=0;col<n;++col){
      if(!get(row,col))continue;
      if(pivots[col].empty()){
        pivots[col]=std::move(row);pivot_col.push_back(col);
        installed=true;break;
      }
      for(int w=0;w<words;++w)row[w]^=pivots[col][w];
    }
    if(!installed&&get(row,n))return false; // inconsistent rows: UNKNOWN only
  }
  if(pivot_col.empty())return false;
  std::sort(pivot_col.begin(),pivot_col.end());
  std::vector<int> free_vars;
  for(int i=0;i<n;++i)if(pivots[i].empty())free_vars.push_back(i);
  // Deterministic free-variable variations, no learning from trial labels.
  for(int attempt=0;attempt<8&&!due(deadline);++attempt){
    std::vector<int8_t> model(n,-1);
    for(int v:free_vars) {
      uint32_t z=static_cast<uint32_t>(v*2654435761U+attempt*2246822519U);
      model[v]=(attempt==0 || ((z^(z>>13))&1U)==0)?-1:1;
    }
    for(auto it=pivot_col.rbegin();it!=pivot_col.rend();++it){
      int col=*it;
      int val=(int)get(pivots[col],n);
      for(int x=col+1;x<n;++x)
        if(get(pivots[col],x)&&model[x]>0)val^=1;
      model[col]=val?1:-1;
    }
    if(finish(n,f,std::move(model),"GF2",out)){
      out.equations=(int)equations.size();return true;
    }
  }
  return false;
}
inline Outcome analyze(int n,const CNF& f, Limits limit={}) {
  Outcome out;
  if(n<=0||n>limit.max_vars||(int)f.size()>limit.max_clauses
     ||limit.max_ms<=0)return out;
  int64_t total=0;
  for(const auto& c:f){
    total+=(int64_t)c.size();
    if(total>limit.max_literals)return out;
    for(int l:c)if(!l||(int64_t)std::abs((int64_t)l)>n)return out;
  }
  const auto deadline=Clock::now()+std::chrono::duration_cast<Clock::duration>(
       std::chrono::duration<double,std::milli>(limit.max_ms));
  // Fast inexpensive classes before more expensive structure reconstruction.
  if(try_horn(n,f,out,deadline))return out;
  if(!due(deadline)&&try_twosat(n,f,out,deadline))return out;
  if(!due(deadline)&&try_matching(n,f,out,deadline))return out;
  if(!due(deadline)&&try_gf2(n,f,out,deadline))return out;
  return out;
}
} // namespace satconstruct
