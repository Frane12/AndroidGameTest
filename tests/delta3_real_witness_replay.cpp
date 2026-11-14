// Deterministic offline replay of the EXACT two source windows saved in
// original SAT2024 hardware-miter ID30; proves actual generated C++ bridge runs.
#include <algorithm>
#include <array>
#include <bit>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <functional>
#include <iostream>
#include <iterator>
#include <map>
#include <numeric>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>
#include "build/delta_coop1.hpp"
#include "build/delta3_join.hpp"

int main(){
    using namespace drnas_coop4;
    Block a,b;
    a.vars={1,3,771,777};
    a.cnf={{1,-3,771},{3,-771},{-1,-771},
           {-1,-3,777},{1,-777},{3,-777}};
    b.vars={1,3,772};
    b.cnf={{-1,3,772},{1,-772},{-3,-772}};
    std::vector<int8_t> values(777,0);
    values[770]=-1; values[771]=-1;
    const auto ap=analyze(a,values);
    const auto bp=analyze(b,values);
    const auto joined=join_pair(a,ap.feasible,b,bp.feasible,values);
    if(joined.removed<=0)throw std::runtime_error("DELTA3_NO_REAL_TUPLE_REMOVAL");
    auto deadline=Tick::now()+std::chrono::seconds(4);
    const int w=tuple_countermodel(a,ap.feasible,b,bp.feasible,
                                   joined.support.vars,1,deadline);
    if(w<0)throw std::runtime_error("DELTA3_NO_AFFINE_COUNTERMODEL");
    JoinEngine engine;
    engine.join_mode="bridge";
    for(const auto& c:a.cnf)engine.known.insert(canonical(c));
    for(const auto& c:b.cnf)engine.known.insert(canonical(c));
    Output out;
    std::vector<std::vector<int>> proof;
    engine.resolveBridge(a,b,values,
      [&](const std::vector<int>& clause){proof.push_back(clause);},
      out,deadline);
    const auto target=canonical(std::vector<int>{-1,772,777});
    bool found=false;
    for(const auto& clause:out.clauses)if(canonical(clause)==target)found=true;
    if(!found)throw std::runtime_error("DELTA3_EXPECTED_ORIGINAL_RUP_BRIDGE_ABSENT");
    if(out.clauses!=proof)throw std::runtime_error("DELTA3_PROOF_EMISSION_DIVERGENCE");
    if(engine.bridge_injected<1)throw std::runtime_error("DELTA3_NOT_INJECTED");
    std::cout<<"DELTA3_REAL_SOURCE_REPLAY_PASS "
             <<"{\"original_source_id\":30,\"affine_countermodel\":"<<w
             <<",\"tuples_removed\":"<<joined.removed
             <<",\"source_checked_cross_resolvents\":"<<proof.size()
             <<",\"expected_clause\":[-1,772,777]}\n";
}
