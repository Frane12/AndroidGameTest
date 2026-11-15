// DRNAS PHP guard integration adapter (experimental, shadow-only).
// This adapter is deliberately NOT allowed to return UNSAT until the
// witness verifier and independently checkable certificate are implemented.
// Compile into the existing solver and call php_guard::inspect(cnf) at input load.
// No subprocess, threads, second solver, or modification to CDCL decisions.
#pragma once
#include <vector>
#include <algorithm>
#include <unordered_set>
#include <cstdint>
namespace php_guard {
struct Report {
  bool candidate=false;
  unsigned rows=0, holes=0;
  uint64_t clauses_scanned=0;
};
inline Report inspect(const std::vector<std::vector<int>>& cnf,
                      uint64_t clause_budget=200000) {
  Report r;
  // Cheap conservative gate: detect positive rows and negative binary clauses.
  // A candidate is NOT a proof; no solver result may depend on it.
  std::vector<std::vector<int>> rows;
  std::unordered_set<uint64_t> negpairs;
  auto pairkey=[](uint32_t a,uint32_t b)->uint64_t {
    if(a>b) std::swap(a,b);
    return (uint64_t(a)<<32)|b;
  };
  for(const auto& c:cnf) {
    if(++r.clauses_scanned>clause_budget) return r;
    if(c.size()>=2 && c.size()<=256) {
      bool positive=true;
      for(int x:c) if(x<=0) {positive=false;break;}
      if(positive) {
        auto row=c;
        std::sort(row.begin(),row.end());
        if(std::adjacent_find(row.begin(),row.end())==row.end())
          rows.push_back(std::move(row));
      }
    }
    if(c.size()==2 && c[0]<0 && c[1]<0 && c[0]!=c[1])
      negpairs.insert(pairkey(uint32_t(-int64_t(c[0])),
                              uint32_t(-int64_t(c[1]))));
  }
  // A lightweight signal for later exact witness reconstruction.
  for(const auto& row:rows) {
    unsigned m=row.size(),n=0;
    for(const auto& other:rows) if(other.size()==m) ++n;
    if(n>m && !negpairs.empty()) {
      r.candidate=true;r.rows=n;r.holes=m;break;
    }
  }
  return r;
}
} // namespace php_guard
