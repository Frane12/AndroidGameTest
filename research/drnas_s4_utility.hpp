#pragma once
// DRNAS S4 SELECTIVE UTILITY (EXPERIMENTAL).
// Generate sound consequences through the already exhaustively tested S3
// source-CNF GF(2) + binary resolution code, but retain only high-utility
// candidates. NO proof of UNSAT is claimed by this transformation.
#include "drnas_s3_crr.hpp"
#include <algorithm>
#include <cstdint>
#include <deque>
#include <iostream>
#include <limits>
#include <map>
#include <unordered_map>
#include <utility>
#include <vector>

namespace drnas_s4 {

struct Stats {
  unsigned mode=0,original=0,candidates=0,eligible=0,selected=0;
  unsigned selected_xor=0,selected_resolution=0,root_forcing=0;
  unsigned root_trail=0,skipped=0;
  unsigned xor_rows=0,root_conflict=0;
};
inline void print(const Stats& x) {
  std::cout<<"c S4_UTILITY mode="<<x.mode<<" original="<<x.original
           <<" candidates="<<x.candidates<<" eligible="<<x.eligible
           <<" selected="<<x.selected<<" selected_xor="<<x.selected_xor
           <<" selected_resolution="<<x.selected_resolution
           <<" root_forcing="<<x.root_forcing<<" root_trail="<<x.root_trail
           <<" xor_rows="<<x.xor_rows<<" root_conflict="<<x.root_conflict
           <<" skipped="<<x.skipped<<"\n";
}
template <class CNF> Stats enrich(CNF& cnf,unsigned mode,bool telemetry=true) {
  Stats s;s.mode=mode;s.original=static_cast<unsigned>(cnf.clauses.size());
  const unsigned cap=(mode==16?16:mode==32?32:0);
  // Guard both expected utility and CPU/memory cost of the S3 candidate pass.
  constexpr size_t MAX_CLAUSES=12000, MAX_LITERALS=150000;
  constexpr int MAX_VARS=2500;
  if(cap==0||cnf.clauses.size()>MAX_CLAUSES) {
    s.skipped=1;if(telemetry)print(s);return s;
  }
  size_t lits=0;
  int maxvar=0;
  std::vector<unsigned> binary_degree(MAX_VARS+1,0);
  std::unordered_map<int,std::vector<int>> forward;
  std::vector<int8_t> assigned(MAX_VARS+1,0);
  std::deque<int> pending;
  auto enqueue=[&](int lit)->bool {
    const int v=std::abs(lit),value=lit>0?1:-1;
    if(v<1||v>MAX_VARS)return false;
    if(assigned[v]==-value){s.root_conflict=1;return false;}
    if(assigned[v]==value)return true;
    assigned[v]=static_cast<int8_t>(value);
    pending.push_back(lit);
    return true;
  };
  for(const auto& c:cnf.clauses) {
    lits+=c.size();
    if(lits>MAX_LITERALS){s.skipped=1;if(telemetry)print(s);return s;}
    for(int lit:c) {
      if(lit==0||std::abs(lit)>MAX_VARS) {
        s.skipped=1;if(telemetry)print(s);return s;
      }
      maxvar=std::max(maxvar,std::abs(lit));
    }
    if(c.size()==1)enqueue(c[0]);
    if(c.size()==2) {
      int a=c[0],b=c[1];
      if(a==-b)continue;
      forward[-a].push_back(b);forward[-b].push_back(a);
      ++binary_degree[std::abs(a)];
      ++binary_degree[std::abs(b)];
    }
  }
  // Compute only root trail implied by units and existing binary clauses.
  // This closure is valid for original CNF; it is NEVER used for an UNSAT claim.
  while(!pending.empty()&&!s.root_conflict) {
    int lit=pending.front();pending.pop_front();
    auto it=forward.find(lit);
    if(it==forward.end())continue;
    for(int next:it->second) {
      if(!enqueue(next))break;
    }
  }
  for(int v=1;v<=maxvar;++v)if(assigned[v])++s.root_trail;
  if(s.root_conflict) {s.skipped=1;if(telemetry)print(s);return s;}

  // S3 derives only logical consequences (XOR2 pairs and binary resolvents).
  // Work on a copy so that low-value candidates NEVER reach CDCL.
  CNF tmp=cnf;
  const auto raw=drnas_s3::enrich(tmp,false);
  const size_t original=cnf.clauses.size();
  s.candidates=static_cast<unsigned>(tmp.clauses.size()-original);
  s.xor_rows=raw.xor_rows;
  if(!s.candidates){if(telemetry)print(s);return s;}

  struct Candidate {std::vector<int> clause;int priority=0;bool xor_pair=false;bool force=false;};
  std::vector<Candidate> ranked;
  ranked.reserve(s.candidates);
  for(size_t j=original;j<tmp.clauses.size();++j) {
    auto c=tmp.clauses[j];
    bool satisfied=false;int unassigned=0;
    int hub=0;
    for(int lit:c) {
      const int a=assigned[std::abs(lit)];
      if(a==0)++unassigned;
      else if(a==(lit>0?1:-1))satisfied=true;
      hub+=std::min<unsigned>(binary_degree[std::abs(lit)],100);
    }
    if(satisfied)continue;
    bool forcing=(unassigned<=1);
    bool is_xor=(j-original<raw.xor_binary_added);
    // 16 arm: root-forcing or parity consequence.
    // 32 arm: also keep binary resolvents supported by existing implication hubs.
    const bool useful=forcing||is_xor||(mode==32&&hub>=8);
    if(!useful)continue;
    ++s.eligible;
    int priority=(forcing?100000:0)+(is_xor?2000:0)+hub*20;
    ranked.push_back({std::move(c),priority,is_xor,forcing});
  }
  std::stable_sort(ranked.begin(),ranked.end(),[](const Candidate&a,const Candidate&b){
    if(a.priority!=b.priority)return a.priority>b.priority;
    return a.clause<b.clause;
  });
  for(const auto& cand:ranked) {
    if(s.selected>=cap)break;
    cnf.clauses.push_back(cand.clause);
    ++s.selected;
    s.selected_xor+=cand.xor_pair;
    s.selected_resolution+=!cand.xor_pair;
    s.root_forcing+=cand.force;
  }
  if(telemetry)print(s);
  return s;
}
} // namespace drnas_s4
