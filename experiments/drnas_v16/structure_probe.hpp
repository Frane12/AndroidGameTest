#pragma once
// DRNAS SAT v16: bounded, deterministic CNF structure probe.
// Experimental: classification only. Never changes SAT/UNSAT correctness.
#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <vector>
namespace drnas_v16 {
struct Features {
  uint64_t clauses=0, literals=0, binary=0, ternary=0, long_clauses=0;
  uint64_t positive=0, negative=0, horn=0, empty=0;
  uint64_t xor_like_triplets=0; // reserved; not inferred from clause counts
  double mean_length=0, binary_fraction=0, horn_fraction=0, polarity_balance=0;
  bool truncated=false;
};
enum class Family { Unknown, BinaryHeavy, HornHeavy, Mixed };
struct Decision {
  Family family=Family::Unknown;
  double confidence=0;
  bool enable_experimental=false; // fail-closed until validated on holdout
};
inline Features inspect(const std::vector<std::vector<int>>& cnf,
                        size_t max_clauses=100000, size_t max_literals=1000000) {
  Features f;
  for (const auto& clause : cnf) {
    if (f.clauses>=max_clauses || clause.size()>max_literals-f.literals) {
      f.truncated=true; break;
    }
    ++f.clauses;
    f.literals += clause.size();
    if (clause.empty()) ++f.empty;
    if (clause.size()==2) ++f.binary;
    if (clause.size()==3) ++f.ternary;
    if (clause.size()>3) ++f.long_clauses;
    size_t positives=0;
    for (int lit : clause) {
      if (lit>0) { ++f.positive; ++positives; }
      else if (lit<0) ++f.negative;
      // zero is invalid DIMACS input; validate in parser
    }
    if (positives<=1) ++f.horn;
  }
  if (f.clauses) {
    f.mean_length=double(f.literals)/double(f.clauses);
    f.binary_fraction=double(f.binary)/double(f.clauses);
    f.horn_fraction=double(f.horn)/double(f.clauses);
  }
  const uint64_t signed_lits=f.positive+f.negative;
  if (signed_lits) f.polarity_balance=1.0-std::fabs(double(f.positive)-double(f.negative))/double(signed_lits);
  return f;
}
inline Decision decide(const Features& f) {
  Decision d;
  if (f.truncated || f.empty || f.clauses<32) return d;
  if (f.binary_fraction>=0.75) {
    d.family=Family::BinaryHeavy; d.confidence=f.binary_fraction;
  } else if (f.horn_fraction>=0.90) {
    d.family=Family::HornHeavy; d.confidence=f.horn_fraction;
  } else {
    d.family=Family::Mixed; d.confidence=0.0;
  }
  // Correctness-first gate: no auto-activation prior to independent validation.
  return d;
}
} // namespace drnas_v16
