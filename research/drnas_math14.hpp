#pragma once
#include <vector>
#include <map>
#include <set>
#include <array>
#include <algorithm>
#include <iterator>
#include <iostream>
namespace math14 {
// Certified XOR3 extraction: all four forbidden assignments must be present.
// Pair addition over GF(2) then emits only width-two consequences.
template<class CNF> unsigned enrich(CNF& cnf){
 if(cnf.clauses.size()>20000)return 0;
 std::map<std::array<int,3>,unsigned> groups;
 for(const auto& c:cnf.clauses){
  if(c.size()!=3)continue;
  std::array<int,3> vs={std::abs(c[0]),std::abs(c[1]),std::abs(c[2])};
  std::sort(vs.begin(),vs.end());if(vs[0]==vs[1]||vs[1]==vs[2])continue;
  unsigned mask=0;for(int v:c)if(v<0)mask|=1u<<std::distance(vs.begin(),std::find(vs.begin(),vs.end(),-v));
  groups[vs]|=1u<<mask;
 }
 struct Row{std::array<int,3> v;int rhs;};std::vector<Row> rows;
 for(const auto& g:groups){
  if((g.second&0x69)==0x69)rows.push_back({g.first,1}); // even assignments forbidden
  if((g.second&0x96)==0x96)rows.push_back({g.first,0});
  if(rows.size()>256)return 0;
 }
 std::set<std::vector<int>> known,added;
 for(auto c:cnf.clauses)if(c.size()==2){std::sort(c.begin(),c.end());known.insert(c);}
 unsigned pairs=0;
 for(size_t i=0;i<rows.size();++i)for(size_t j=i+1;j<rows.size();++j){
  std::vector<int> v;
  std::set_symmetric_difference(rows[i].v.begin(),rows[i].v.end(),rows[j].v.begin(),rows[j].v.end(),std::back_inserter(v));
  if(v.size()!=2)continue;
  ++pairs;int rhs=rows[i].rhs^rows[j].rhs;
  for(int mask=0;mask<4;++mask){
   if(((mask&1)^((mask>>1)&1))==rhs)continue;
   std::vector<int> c={(mask&1)?-v[0]:v[0],(mask&2)?-v[1]:v[1]};std::sort(c.begin(),c.end());
   if(!known.count(c))added.insert(c);
  }
  if(added.size()>=128)goto done;
 }
 done:
 for(const auto& c:added)cnf.clauses.push_back(c);
 std::cout<<"c MATH14 rows="<<rows.size()<<" pairs="<<pairs<<" binary_added="<<added.size()<<"\n";
 return added.size();
}
}
