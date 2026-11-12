#include "drnas_s4_utility.hpp"
#include <array>
#include <cassert>
#include <iostream>
#include <random>
#include <vector>
struct CNF {std::vector<std::vector<int>> clauses;};
bool sat(const CNF& c,unsigned assignment) {
  for(const auto& clause:c.clauses) {
    bool satisfied=false;
    for(int lit:clause) {
      bool v=(assignment>>(std::abs(lit)-1))&1u;
      if(v==(lit>0)) {satisfied=true;break;}
    }
    if(!satisfied)return false;
  }
  return true;
}
void check(const CNF& input,unsigned vars) {
  for(unsigned mode:{16u,32u}) {
    CNF output=input;
    auto stats=drnas_s4::enrich(output,mode,false);
    assert(stats.selected<=mode);
    assert(stats.selected==stats.selected_xor+stats.selected_resolution);
    for(unsigned mask=0;mask<(1u<<vars);++mask)
      assert(sat(input,mask)==sat(output,mask));
  }
}
void xor3(CNF& c,std::array<int,3> v,int rhs) {
  for(int bits=0;bits<8;++bits) {
    if((__builtin_popcount(static_cast<unsigned>(bits))&1)==rhs)continue;
    c.clauses.push_back({(bits&1)?-v[0]:v[0],
                         (bits&2)?-v[1]:v[1],
                         (bits&4)?-v[2]:v[2]});
  }
}
int main(){
  CNF xor_pair;
  xor3(xor_pair,{1,2,3},0);
  xor3(xor_pair,{1,2,4},1);
  check(xor_pair,4);
  for(unsigned mode:{16u,32u}) {
    CNF x=xor_pair;
    auto s=drnas_s4::enrich(x,mode,false);
    assert(s.selected_xor>0);
    assert(s.selected<=mode);
  }
  CNF known_binary{{{1,2},{-2,3},{1},{-3,4},{-1,3}}};
  check(known_binary,4);
  CNF contradiction{{{1},{-1},{2,3},{-2,-3}}};
  check(contradiction,3);
  CNF mixed=xor_pair;
  mixed.clauses.push_back({5,6,1});
  mixed.clauses.push_back({-5,-6});
  check(mixed,6);
  std::mt19937 rng(4102026);
  for(int k=0;k<400;++k) {
    CNF random;
    for(int i=0;i<16;++i) {
      unsigned width=1+rng()%4;
      std::vector<int> c;
      for(unsigned j=0;j<width;++j) {
        int v=1+int(rng()%6);
        c.push_back((rng()%2)?v:-v);
      }
      random.clauses.push_back(c);
    }
    if(k%4==0)xor3(random,{1,2,3},int(rng()%2));
    if(k%8==0)xor3(random,{1,2,4},int(rng()%2));
    check(random,6);
  }
  std::cout<<"S4_EXHAUSTIVE_SELFTEST_PASS 400 random + XOR + mixed CNFs, both caps\n";
}
