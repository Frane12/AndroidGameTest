// Small deterministic gate-only controls. Never equate an eligibility decision
// with a SAT/UNSAT proof: the existing math5 proof checker remains mandatory.
#include "drnas_structure_gate.hpp"
#include <cassert>
#include <iostream>
#include <set>
#include <vector>
struct Clause {std::vector<int> lits; bool learnt=false;};
using Clauses=std::vector<Clause>;

void add_exact_one(Clauses& f, const std::vector<int>& row) {
    f.push_back({row,false});
    for(size_t j=1;j<row.size();++j)
        for(size_t i=0;i<j;++i)
            f.push_back({{-row[i],-row[j]},false});
}
int main() {
    Clauses eo;
    add_exact_one(eo,{1,2,3,4});
    add_exact_one(eo,{1,2,5,6});
    add_exact_one(eo,{3,4,5,6});
    const auto yes=drnas_structure_gate::inspect(eo,6,int(eo.size()),100.);
    assert(yes.use_math5);
    assert(yes.reason=="EXACT_ONE_MULTIGROUP");
    assert(yes.candidate_eo>=2);

    Clauses only_one;
    add_exact_one(only_one,{1,2,3,4});
    only_one.push_back({{1,5,6},false});
    const auto no=drnas_structure_gate::inspect(
        only_one,6,int(only_one.size()),100.);
    assert(!no.use_math5);

    Clauses mixed;
    for(int i=1;i<=100;++i) {
        mixed.push_back({{i,-i-1},false});
        mixed.push_back({{i,i+1,-i-2},false});
    }
    const auto no2=drnas_structure_gate::inspect(
        mixed,103,int(mixed.size()),100.);
    assert(!no2.use_math5);

    Clauses xorrows;
    for(std::vector<int> group:std::vector<std::vector<int>>{{1,2,3},{3,4,5}}) {
        for(int mask=0;mask<8;++mask){
            if(__builtin_popcount(unsigned(mask))%2)continue;
            std::vector<int> row;
            for(int i=0;i<3;++i)row.push_back(
                mask&(1<<i)?-group[i]:group[i]);
            xorrows.push_back({row,false});
        }
    }
    const auto xor_gate=drnas_structure_gate::inspect(
        xorrows,5,int(xorrows.size()),100.);
    assert(xor_gate.use_math5);
    assert(xor_gate.reason=="XOR_PARITY_MULTIGROUP");
    assert(xor_gate.complete_xor>=2);

    const auto off=drnas_structure_gate::inspect(eo,6,int(eo.size()),0);
    assert(!off.use_math5 && off.reason=="OFF");
    std::cout<<"STRUCTURE_GATE_UNIT_PASS "
             <<"{\"exact_one_groups\":"<<yes.candidate_eo
             <<",\"xor_rows\":"<<xor_gate.complete_xor
             <<",\"mixed_rejected\":true}"<<std::endl;
}
