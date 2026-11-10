// DRNAS SRE2-B: exact CNF automorphism screening, single safe lex-leader,
// and verified GF(2)/SCC substitution inherited from SRE1.
// SAT-preserving symmetry breaking: if swapping a,b preserves the entire CNF,
// at least one satisfying model has a<=b. Only ONE leader per run.
#pragma once
#include <map>
namespace drnas {
struct SRE2B {
 int symmetry_a=0,symmetry_b=0,probes=0;
 int original_clauses=0,augmented_clauses=0;
 bool abstained=false,leader_added=false;
 double scan_s=0;
};
static std::vector<int> sre2b_canon(std::vector<int> c){
 std::sort(c.begin(),c.end());
 c.erase(std::unique(c.begin(),c.end()),c.end());
 return c;
}
static SRE2B sre2b_symmetry(const CNF& original,CNF& augmented,bool enable){
 const auto t=Clock::now();
 SRE2B out;
 augmented=original;
 out.original_clauses=(int)original.clauses.size();
 out.augmented_clauses=out.original_clauses;
 if(!enable)return out;
 if(original.vars>200 || original.clauses.size()>2500){
  out.abstained=true;return out;
 }
 using Clause=std::vector<int>;
 std::map<Clause,int> source;
 std::vector<int> positive(original.vars+1,0),negative(original.vars+1,0);
 for(const auto& clause:original.clauses){
  auto c=sre2b_canon(clause);
  ++source[c];
  for(int l:c)if(l>0)++positive[l];else ++negative[-l];
 }
 for(int a=1;a<=original.vars;++a){
  for(int b=a+1;b<=original.vars;++b){
   if(positive[a]!=positive[b]||negative[a]!=negative[b])continue;
   if(++out.probes>2500){out.abstained=true;break;}
   std::map<Clause,int> swapped;
   for(const auto& clause:original.clauses){
    Clause c=clause;
    for(int& lit:c){
     const int v=std::abs(lit);
     if(v==a)lit=lit>0?b:-b;
     else if(v==b)lit=lit>0?a:-a;
    }
    ++swapped[sre2b_canon(std::move(c))];
   }
   if(swapped==source){
    out.symmetry_a=a;out.symmetry_b=b;
    // If a=1,b=0, the swapped assignment has a=0,b=1.
    // Thus at least one satisfying assignment obeys (!a OR b).
    augmented.clauses.push_back({-a,b});
    out.leader_added=true;
    out.augmented_clauses=(int)augmented.clauses.size();
    break;
   }
  }
  if(out.leader_added||out.abstained)break;
 }
 out.scan_s=std::chrono::duration<double>(Clock::now()-t).count();
 return out;
}
} // namespace drnas
