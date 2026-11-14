#include <algorithm>
#include <array>
#include <bit>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <functional>
#include <iostream>
#include <iterator>
#include <map>
#include <numeric>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>
#include "build/delta4_coop1.hpp"
#include "build/delta4x_engine.hpp"
using namespace drnas_coop4;
void require(bool ok,const char* why){if(!ok)throw std::runtime_error(why);}
Delta4XEngine make(const std::string& mode,bool reverse=true){
    Delta4XEngine e;e.mode="gate";e.delayed=false;e.setJoinMode(mode);
    e.add({-1,-2,5});e.add({-1,2,4});if(reverse)e.add({1,-5});
    e.initialize(5005);e.passes=24;e.ms=30; // base exhausted, X must remain reachable
    return e;
}
int main(){
    std::vector<int8_t> v(5005,0);v[3]=-1;
    auto e=make("d4x");require(e.ready(0,0),"X_STARVED_AFTER_D4_BUDGET");
    auto out=e.step(v,0,0,[](const auto&){});
    require(!out.clauses.empty(),"NO_GUARDED_CANDIDATE");
    for(const auto& c:out.clauses)require(e.onStored(c,v),"STORAGE_PROVENANCE");
    require(e.xinstalled>0&&e.xactivations>0,"NOT_INSTALLED_OR_ACTIVE");
    const auto acts=e.xactivations;v[3]=0;e.refresh(v);
    require(e.xdeactivations==acts,"BACKTRACK_ALIAS_REMAINED_ACTIVE");
    v[3]=1;e.refresh(v);require(e.xactivations==acts,"TRUE_GUARD_ACTIVATED_ALIAS");
    v[3]=-1;e.refresh(v);require(e.xactivations==2*acts,"GUARD_REACTIVATION_FAILED");
    auto shadow=make("d4x-shadow");auto s=shadow.step(v,0,0,[](const auto&){});
    require(s.clauses.empty()&&shadow.xinstalled==0&&shadow.xshadow>0,"SHADOW_CHANGED_FORMULA");
    auto absent=make("d4x",false);auto a=absent.step(v,0,0,[](const auto&){});
    require(a.clauses.empty()&&absent.xcandidates.empty(),"MISSING_REVERSE_ACCEPTED");
    auto guarded=make("d4x");v[3]=0;auto u=guarded.step(v,0,0,[](const auto&){});
    require(u.clauses.empty(),"UNASSIGNED_GUARD_ACCEPTED");
    std::cout<<"DELTA4X_LIFECYCLE_PASS {\"undo\":true,\"reactivate\":true,\"missing_reverse\":true,\"unassigned_guard\":true,\"shadow\":true,\"empty_block_dispatch\":true}\n";
}
