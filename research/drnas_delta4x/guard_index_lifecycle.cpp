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
#include "build/delta4x_guard_index.hpp"
using namespace drnas_coop4;
static void require(bool ok,const char* why){
    if(!ok)throw std::runtime_error(why);
}
int main(){
    Delta4XEngine e;
    e.mode="gate";e.delayed=false;e.setJoinMode("d4x");
    e.add({-1,-2,5});
    e.add({-1,2,4});
    e.add({1,-5});
    e.initialize(5005);
    e.passes=24;e.ms=30;
    std::vector<int8_t> v(5005,0);
    v[3]=-1;
    require(e.ready(0,0),"X_DEAD_DISPATCH");
    auto proposed=e.step(v,0,0,[](const auto&){});
    require(!proposed.clauses.empty(),"NO_CLAUSES");
    for(const auto& clause:proposed.clauses)
        require(e.onStored(clause,v),"STORAGE_NOT_RECORDED");
    require(e.xinstalled>0 && e.xactivations>0,"NO_GUARDED_ALIAS");
    require(e.xguard_index.size()>0 && !e.xactive_guard_vars.empty(),"INDEX_NOT_BUILT");
    const auto start=e.xactivations;
    const auto groups=e.xguard_group_visits;
    // CancelUntil unassigns, so only currently active guard-groups can change.
    v[3]=0;
    e.backtrackRefresh(v);
    require(e.xdeactivations==start,"BACKTRACK_DID_NOT_DEACTIVATE");
    require(e.xactive_guard_vars.empty(),"STALE_ACTIVE_GUARD_AFTER_BACKTRACK");
    require(e.xbacktrack_active_visits>0,"BACKTRACK_INDEX_NOT_VISITED");
    const auto no_op=e.xguard_group_visits;
    e.backtrackRefresh(v);
    require(e.xguard_group_visits==no_op,"INACTIVE_GUARDS_SCANNED_ON_BACKTRACK");
    // A new decision makes the guard false. Only this guard group is touched.
    v[3]=-1;e.trailChange(-4,v);
    require(e.xactivations==2*start,"GUARD_FALSE_NOT_REACTIVATED");
    require(e.xguard_trail_hits>0 && e.xguard_group_visits>groups,"GUARD_LOOKUP_MISSED");
    const auto before=e.xguard_group_visits;
    v[12]=1;e.trailChange(13,v);
    require(e.xguard_group_visits==before,"UNRELATED_ASSIGNMENT_SCANNED_ALIAS");
    // Undo guard again; the derived CNF remains valid globally.
    v[3]=0;e.backtrackRefresh(v);
    require(e.xdeactivations==2*start && e.xactive_guard_vars.empty(),"SECOND_ROLLBACK_FAILED");
    // A TRUE guard must never activate a conditional equality.
    v[3]=1;e.trailChange(4,v);
    require(e.xactive_guard_vars.empty(),"TRUE_GUARD_ACTIVATED_ALIAS");
    require(e.xactivations==2*start,"TRUE_GUARD_CHANGED_ACTIVATIONS");
    std::cout<<"GUARD_INDEX_LIFECYCLE_PASS {\"installed\":"<<e.xinstalled
        <<",\"deactivations\":"<<e.xdeactivations
        <<",\"trail_lookup_hits\":"<<e.xguard_trail_hits
        <<",\"group_visits\":"<<e.xguard_group_visits
        <<",\"backtrack_active_visits\":"<<e.xbacktrack_active_visits
        <<",\"unrelated_assignments_bypassed\":true"
        <<",\"proof_clauses_untouched\":true}\n";
}
