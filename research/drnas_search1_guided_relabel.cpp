// DRNAS SEARCH1: proof-preserving variable RENAMING (not a native CDCL heuristic).
// Source-only signed binary SCC + complete XOR3 motifs + degree prior;
// guided, opposite guidance and source-independent random placebo all preserve
// clauses exactly, literals/signs exactly, and original SAT/UNSAT semantics.
// No original CNF mutation, no source-driven branch if unsupported by evidence.
#include <algorithm>
#include <array>
#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <map>
#include <numeric>
#include <random>
#include <stdexcept>
#include <string>
#include <vector>
using namespace std;
static void need(bool ok,const string& why){
 if(!ok)throw runtime_error("SEARCH1_CPP_FAIL_CLOSED "+why);
}
struct CNF {int n=0;vector<vector<int>> clauses;};
static CNF parse(const string& path){
 ifstream f(path);need(bool(f),"open input");
 CNF a;int expected=-1;string token;vector<int> current;uint64_t lits=0;
 while(f>>token){
  if(token=="c"){string s;getline(f,s);continue;}
  if(token=="%")break;
  if(token=="p"){
   string t;need(expected<0&&current.empty()&&bool(f>>t>>a.n>>expected),"header");
   need(t=="cnf"&&a.n>0&&a.n<=200000&&expected>0&&expected<=700000,"geometry");
   continue;
  }
  need(expected>=0,"missing p cnf");
  size_t used=0;int lit=0;
  try{lit=stoi(token,&used);}catch(...){throw runtime_error("bad literal");}
  need(used==token.size(),"literal token");
  if(lit==0){a.clauses.push_back(move(current));current.clear();
    need((int)a.clauses.size()<=expected,"excess clauses");
  }else{
   need(lit!=(-2147483647-1)&&abs(lit)<=a.n,"literal range");
   current.push_back(lit);need(++lits<=8000000,"literal budget");
  }
 }
 need(expected>=0&&current.empty()&&(int)a.clauses.size()==expected,"count mismatch");
 return a;
}
static int node(int lit){return 2*(abs(lit)-1)+(lit<0);}
static vector<int> scc_size(const CNF& a,vector<int>& degree){
 int nn=2*a.n;vector<vector<int>> g(nn),r(nn);
 for(const auto& c:a.clauses){
  if(c.size()==1){
    int p=node(-c[0]),q=node(c[0]);g[p].push_back(q);r[q].push_back(p);
  }else if(c.size()==2){
    int x=c[0],y=c[1];if(x==-y)continue;
    if(x==y){int p=node(-x),q=node(x);g[p].push_back(q);r[q].push_back(p);}
    else{
     for(auto edge:array<pair<int,int>,2>{{{-x,y},{-y,x}}}){
      int p=node(edge.first),q=node(edge.second);
      g[p].push_back(q);r[q].push_back(p);
      degree[abs(edge.first)]++;degree[abs(edge.second)]++;
     }
    }
  }
 }
 vector<unsigned char> seen(nn,0);vector<int> order;order.reserve(nn);
 for(int st=0;st<nn;st++)if(!seen[st]){
  seen[st]=1;vector<pair<int,size_t>> dfs{{st,0}};
  while(!dfs.empty()){
   auto &cur=dfs.back();
   if(cur.second<g[cur.first].size()){
    int v=g[cur.first][cur.second++];
    if(!seen[v]){seen[v]=1;dfs.emplace_back(v,0);}
   }else{order.push_back(cur.first);dfs.pop_back();}
  }
 }
 vector<int> component(nn,-1);vector<int> lengths;
 for(auto it=order.rbegin();it!=order.rend();++it)if(component[*it]<0){
  int id=(int)lengths.size(),count=0;vector<int> st{*it};component[*it]=id;
  while(!st.empty()){
   int u=st.back();st.pop_back();count++;
   for(int v:r[u])if(component[v]<0){component[v]=id;st.push_back(v);}
  }lengths.push_back(count);
 }
 vector<int> sizes(a.n+1,0);
 for(int v=1;v<=a.n;v++){
  sizes[v]=max(lengths[component[node(v)]],lengths[component[node(-v)]]);
 }
 return sizes;
}
int main(int argc,char**argv){
 try{
  need(argc==6,"usage: search1-relabel guided|reverse|placebo orig.cnf out.cnf mapping.map numeric_seed");
  string mode=argv[1];
  need(mode=="guided"||mode=="reverse"||mode=="placebo","bad mode");
  CNF cnf=parse(argv[2]);
  uint64_t seed=0;
  try{seed=stoull(argv[5]);}catch(...){throw runtime_error("seed");}
  vector<int> degree(cnf.n+1,0),freq(cnf.n+1,0),xorhits(cnf.n+1,0);
  map<array<int,3>,uint8_t> triple_masks;
  for(const auto& clause:cnf.clauses){
   for(int lit:clause)freq[abs(lit)]++;
   if(clause.size()!=3)continue;
   array<int,3> vars{{abs(clause[0]),abs(clause[1]),abs(clause[2])}};
   sort(vars.begin(),vars.end());
   if(vars[0]==vars[1]||vars[1]==vars[2])continue;
   uint8_t mask=0;
   for(int bit=0;bit<3;bit++)
    for(int lit:clause)if(abs(lit)==vars[bit]&&lit<0)mask|=uint8_t(1u<<bit);
   triple_masks[vars]|=uint8_t(1u<<mask);
  }
  int complete=0;
  for(auto entry:triple_masks){
   uint8_t x=entry.second;
   // Four 3-clauses of each parity form exact 3-variable XOR/CNF.
   int occurrences=((x&0x69)==0x69)+((x&0x96)==0x96);
   if(occurrences){
    complete+=occurrences;
    for(int v:entry.first)xorhits[v]+=occurrences;
   }
  }
  vector<int> scc=scc_size(cnf,degree);
  vector<int> order(cnf.n);
  iota(order.begin(),order.end(),1);
  auto score=[&](int v)->uint64_t{
   // Feature weights are fixed before E2E outcomes.
   uint64_t xor_s=uint64_t(min(xorhits[v],2000))*100000;
   uint64_t scc_s=uint64_t(min(max(0,scc[v]-1),5000))*1000;
   uint64_t binary_s=uint64_t(min(degree[v],200000))*8;
   return xor_s+scc_s+binary_s+uint64_t(freq[v]);
  };
  stable_sort(order.begin(),order.end(),[&](int x,int y){
   return score(x)>score(y);
  });
  if(mode=="reverse")reverse(order.begin(),order.end());
  if(mode=="placebo"){
   iota(order.begin(),order.end(),1);
   mt19937_64 rng(seed);shuffle(order.begin(),order.end(),rng);
  }
  vector<int> old_to_new(cnf.n+1,0);
  for(int i=0;i<cnf.n;i++)old_to_new[order[i]]=i+1;
  vector<uint8_t> seen(cnf.n+1,0);
  for(int v=1;v<=cnf.n;v++){
   need(old_to_new[v]>0&&old_to_new[v]<=cnf.n,"permutation range");
   need(!seen[old_to_new[v]],"permutation not bijective");
   seen[old_to_new[v]]=1;
  }
  ofstream out(argv[3]),mapping(argv[4]);
  need(bool(out)&&bool(mapping),"write open");
  out<<"p cnf "<<cnf.n<<" "<<cnf.clauses.size()<<"\n";
  for(const auto& clause:cnf.clauses){
   for(int l:clause)out<<(l>0?old_to_new[l]:-old_to_new[-l])<<" ";
   out<<"0\n";
  }
  mapping<<"p perm "<<cnf.n<<"\n";
  for(int v=1;v<=cnf.n;v++)mapping<<v<<" "<<old_to_new[v]<<"\n";
  need(bool(out)&&bool(mapping),"write failed");
  cerr<<"SEARCH1_RENAME {\"mode\":\""<<mode
      <<"\",\"variables\":"<<cnf.n
      <<",\"clauses\":"<<cnf.clauses.size()
      <<",\"complete_xor3\":"<<complete
      <<",\"variables_with_xor\":"<<count_if(xorhits.begin()+1,xorhits.end(),[](int x){return x>0;})
      <<",\"vars_with_nontrivial_SCC\":"<<count_if(scc.begin()+1,scc.end(),[](int x){return x>1;})
      <<"}\n";
  return 0;
 }catch(const exception& e){cerr<<e.what()<<"\n";return 78;}
}
