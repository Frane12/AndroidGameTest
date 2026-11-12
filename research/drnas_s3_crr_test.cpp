#include "drnas_s3_crr.hpp"
#include <cassert>
#include <iostream>
#include <random>
#include <vector>
struct CNF {std::vector<std::vector<int>> clauses;};
bool sat(const CNF& c,unsigned assignment) {
  for(const auto& clause:c.clauses) {
    bool true_clause=false;
    for(int lit:clause) {
      const bool value=(assignment>>(std::abs(lit)-1))&1u;
      if(value==(lit>0)){true_clause=true;break;}
    }
    if(!true_clause)return false;
  }
  return true;
}
void equivalent(CNF c,unsigned vars,bool expect_added) {
  CNF before=c;
  auto first=drnas_s3::enrich(c,false);
  if(expect_added) assert(first.added()>0);
  for(unsigned m=0;m<(1u<<vars);++m)
    assert(sat(before,m)==sat(c,m));
  auto second=drnas_s3::enrich(c,false);
  for(unsigned m=0;m<(1u<<vars);++m)
    assert(sat(before,m)==sat(c,m)); // further resolution stays sound
}
void xor3(CNF& c,std::array<int,3> vars,int rhs) {
  for(int mask=0;mask<8;++mask){
    if((__builtin_popcount(static_cast<unsigned>(mask))&1)==rhs)continue;
    c.clauses.push_back({(mask&1)?-vars[0]:vars[0],
                         (mask&2)?-vars[1]:vars[1],
                         (mask&4)?-vars[2]:vars[2]});
  }
}
int main() {
  CNF resolution{{{1,2},{-2,3}}};
  equivalent(resolution,3,true);
  CNF gf2;
  xor3(gf2,{1,2,3},0);
  xor3(gf2,{1,2,4},1);
  equivalent(gf2,4,true);
  CNF mixed=gf2;
  mixed.clauses.push_back({1,4,5});
  mixed.clauses.push_back({-5,6});
  mixed.clauses.push_back({-2,5});
  equivalent(mixed,6,true);
  CNF incomplete=gf2;
  incomplete.clauses.erase(incomplete.clauses.begin()+1);
  equivalent(incomplete,4,false); // missing parity clause must not fabricate an XOR row
  std::mt19937 rng(31973);
  for(int k=0;k<250;++k) {
    CNF c;
    for(int i=0;i<16;++i) {
      int width=1+int(rng()%4),a=0;
      std::vector<int> clause;
      for(int j=0;j<width;++j) {
        int v=1+int(rng()%6);
        int sign=rng()%2?-1:1;
        clause.push_back(v*sign);
      }
      c.clauses.push_back(clause);
    }
    if(k%4==0) xor3(c,{1,2,3},int(rng()%2));
    if(k%8==0) xor3(c,{1,2,4},int(rng()%2));
    equivalent(c,6,false);
  }
  std::cout<<"S3_CRR_EXHAUSTIVE_TEST_PASS 250_random_CNF + XOR + mixed + binary_resolution\n";
}
