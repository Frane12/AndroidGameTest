#pragma once
// DRNAS S3 CRR: source-CNF implied XOR2 and binary-resolution consequences.
// All additions are logical consequences of ORIGINAL clauses. The header
// does not claim a general proof of UNSAT. External SAT model validation
// and independent original-CNF UNSAT certification remain mandatory.
#include <algorithm>
#include <array>
#include <cstdlib>
#include <iostream>
#include <iterator>
#include <map>
#include <set>
#include <utility>
#include <vector>

namespace drnas_s3 {

struct Stats {
  unsigned original_clauses=0;
  unsigned binary_input=0;
  unsigned xor_rows=0;
  unsigned xor_pairs=0;
  unsigned xor_binary_added=0;
  unsigned binary_resolvents_added=0;
  unsigned binary_units_added=0;
  unsigned resolution_pairs_checked=0;
  bool skipped_large=false;
  unsigned added() const {return xor_binary_added+binary_resolvents_added;}
};

inline std::vector<int> canon(int a,int b) {
  if(a==-b) return {}; // tautology
  if(a==b) return {a}; // unit resolvent is valid
  if(a>b) std::swap(a,b);
  return {a,b};
}
inline bool proper(const std::vector<int>& c) {
  return c.size()==2&&c[0]!=0&&c[1]!=0&&c[0]!=-c[1];
}

template<class CNF> Stats enrich(CNF& cnf,bool telemetry=true) {
  Stats s;
  s.original_clauses=static_cast<unsigned>(cnf.clauses.size());
  constexpr unsigned MAX_INPUT=45000,MAX_GROUPS=8000,MAX_ROWS=1200;
  constexpr unsigned MAX_XOR_BINARY=96,MAX_RESOLVE=96,MAX_CANDIDATES=5000;
  if(cnf.clauses.size()>MAX_INPUT) {
    s.skipped_large=true;
    if(telemetry)std::cout<<"c S3_CRR skip=large clauses="<<s.original_clauses<<"\n";
    return s;
  }
  std::map<std::array<int,3>,unsigned> groups;
  std::set<std::vector<int>> known;
  for(const auto& c:cnf.clauses) {
    if(c.size()==1) known.insert(c);
    if(proper(c)) {
      auto b=c;std::sort(b.begin(),b.end());
      known.insert(b);
      ++s.binary_input;
    }
    if(c.size()!=3) continue;
    std::array<int,3> vars={std::abs(c[0]),std::abs(c[1]),std::abs(c[2])};
    std::sort(vars.begin(),vars.end());
    if(vars[0]==vars[1]||vars[1]==vars[2]) continue;
    unsigned sign=0;
    for(int lit:c)if(lit<0) {
      for(int i=0;i<3;++i) if(vars[i]==-lit)sign|=(1u<<i);
    }
    groups[vars]|=(1u<<sign);
    if(groups.size()>MAX_GROUPS) {
      s.skipped_large=true;
      if(telemetry)std::cout<<"c S3_CRR skip=groups\n";
      return s;
    }
  }
  struct Row {std::array<int,3> vars;int rhs;};
  std::vector<Row> rows;
  for(const auto& kv:groups) {
    // Complete forbidden assignment sets imply XOR3, even if other clauses
    // also use these variables. Additional forbidden assignments don't
    // invalidate the implication (though they may render the CNF UNSAT).
    if((kv.second&0x69)==0x69)rows.push_back({kv.first,1});
    if((kv.second&0x96)==0x96)rows.push_back({kv.first,0});
    if(rows.size()>MAX_ROWS) {s.skipped_large=true;return s;}
  }
  s.xor_rows=static_cast<unsigned>(rows.size());

  std::set<std::vector<int>> xor_added;
  std::map<std::pair<int,int>,std::vector<unsigned>> by_pair;
  for(unsigned i=0;i<rows.size();++i) {
    const auto& row=rows[i];
    for(int x=0;x<3;++x)for(int y=x+1;y<3;++y) {
      auto key=std::make_pair(row.vars[x],row.vars[y]);
      auto& prev=by_pair[key];
      for(unsigned j:prev) {
        if(xor_added.size()>=MAX_XOR_BINARY) break;
        std::vector<int> diff;
        std::set_symmetric_difference(
          rows[i].vars.begin(),rows[i].vars.end(),
          rows[j].vars.begin(),rows[j].vars.end(),
          std::back_inserter(diff));
        if(diff.size()!=2) continue;
        ++s.xor_pairs;
        const int rhs=rows[i].rhs^rows[j].rhs;
        // Forbid assignments violating derived XOR2.
        for(int mask=0;mask<4;++mask) {
          if(((mask&1)^((mask>>1)&1))==rhs)continue;
          auto c=canon((mask&1)?-diff[0]:diff[0],(mask&2)?-diff[1]:diff[1]);
          if(!c.empty()&&!known.count(c)) xor_added.insert(c);
        }
      }
      if(prev.size()<12)prev.push_back(i); // bounded sharing fanout
    }
  }
  s.xor_binary_added=static_cast<unsigned>(xor_added.size());
  known.insert(xor_added.begin(),xor_added.end());

  // Resolution on binary clauses: (a|b) and (-b|c) entails (a|c).
  // Only one round, with strict pair/derived-clause caps.
  std::map<int,std::vector<int>> incidence;
  auto index_binary=[&](const std::vector<int>& c) {
    if(!proper(c))return;
    incidence[c[0]].push_back(c[1]);
    incidence[c[1]].push_back(c[0]);
  };
  for(auto c:cnf.clauses)if(proper(c)){
    std::sort(c.begin(),c.end());index_binary(c);
  }
  for(const auto& c:xor_added)index_binary(c);

  std::set<std::vector<int>> resolve_added;
  bool stop=false;
  for(const auto& kv:incidence) {
    const int pivot=kv.first;
    if(pivot<=0)continue;
    auto neg=incidence.find(-pivot);
    if(neg==incidence.end())continue;
    const auto& lhs=kv.second;
    const auto& rhs=neg->second;
    for(unsigned i=0;i<lhs.size()&&i<40&&!stop;++i)
      for(unsigned j=0;j<rhs.size()&&j<40;++j) {
        if(++s.resolution_pairs_checked>MAX_CANDIDATES) {stop=true;break;}
        auto resolvent=canon(lhs[i],rhs[j]);
        if(resolvent.empty()||known.count(resolvent))continue;
        resolve_added.insert(resolvent);
        if(resolve_added.size()>=MAX_RESOLVE) {stop=true;break;}
      }
    if(stop)break;
  }
  for(const auto& c:resolve_added)if(c.size()==1)++s.binary_units_added;
  s.binary_resolvents_added=static_cast<unsigned>(resolve_added.size());
  for(const auto& c:xor_added)cnf.clauses.push_back(c);
  for(const auto& c:resolve_added)cnf.clauses.push_back(c);
  if(telemetry) {
    std::cout<<"c S3_CRR original="<<s.original_clauses
             <<" binary_input="<<s.binary_input
             <<" xor_rows="<<s.xor_rows
             <<" xor_pairs="<<s.xor_pairs
             <<" xor_binary_added="<<s.xor_binary_added
             <<" resolution_added="<<s.binary_resolvents_added
             <<" units="<<s.binary_units_added
             <<" resolution_checked="<<s.resolution_pairs_checked<<"\n";
  }
  return s;
}
} // namespace drnas_s3
