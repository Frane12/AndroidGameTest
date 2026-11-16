#pragma once
// Experimental IPG1 integer configuration-cover UNSAT guard.
//
// Supported input is the *original* DIMACS: disjoint 3-way positive ALO
// clauses covering every variable, source pairwise AMO within every job,
// and source negative-only per-machine forbidding clauses.
// We ONLY reason from these already-present clauses, ignoring all others.
// Exhaustively enumerate allowed subsets per machine and test if three such
// subsets partition every job. No partition => original CNF UNSAT.
// The search is deliberately incomplete and exponential (n <= 15).
//
// Output is a structural certificate requiring INDEPENDENT source-bound
// checking. It is NOT DRAT, LRAT or VeriPB. Unsupported / timeout => UNKNOWN.
#include <array>
#include <algorithm>
#include <chrono>
#include <cstdint>
#include <set>
#include <sstream>
#include <string>
#include <utility>
#include <vector>

namespace drnas_ipg1 {
using Clock=std::chrono::steady_clock;

struct Result {
    bool supported=false;
    bool verified=false; // complete internal exact enumeration, external check still mandatory
    std::string reason="unsupported";
    int groups=0;
    int selected_negative_clauses=0;
    std::array<int,3> admissible{0,0,0};
    uint64_t checked_partitions=0;
    double seconds=0.0;
    std::string certificate_json;
};

inline uint64_t pairKey(int a,int b) {
    if (a>b) std::swap(a,b);
    return (uint64_t(uint32_t(a))<<32)|uint32_t(b);
}

inline Result analyze(const std::vector<std::vector<int>>& clauses,
                      int variable_count, const std::string& sha256,
                      double budget_seconds) {
    const auto start=Clock::now();
    Result result;
    auto finish=[&](const char* reason) {
        result.reason=reason;
        result.seconds=std::chrono::duration<double>(Clock::now()-start).count();
        return result;
    };
    if (budget_seconds<=0.0) return finish("budget_zero");
    if (variable_count<9 || variable_count>45 ||
        clauses.empty() || clauses.size()>3000)
        return finish("size_gate");
    std::vector<std::array<int,3>> groups;
    for (const auto& c:clauses) {
        if (c.size()==3 && c[0]>0 && c[1]>0 && c[2]>0) {
            if (c[0]==c[1] || c[1]==c[2] || c[0]==c[2])
                return finish("duplicate_group_literal");
            groups.push_back({c[0],c[1],c[2]});
        }
    }
    const int n=static_cast<int>(groups.size());
    if (n<3 || n>15 || 3*n!=variable_count) return finish("group_gate");
    std::vector<int> owner(static_cast<size_t>(variable_count+1),-1);
    std::vector<int> position(static_cast<size_t>(variable_count+1),-1);
    for (int j=0;j<n;++j) {
        for (int k=0;k<3;++k) {
            const int x=groups[static_cast<size_t>(j)][static_cast<size_t>(k)];
            if (x<1 || x>variable_count || owner[static_cast<size_t>(x)]!=-1)
                return finish("overlap_or_out_of_range");
            owner[static_cast<size_t>(x)]=j;
            position[static_cast<size_t>(x)]=k;
        }
    }
    for (int x=1;x<=variable_count;++x)
        if (owner[static_cast<size_t>(x)]<0) return finish("uncovered_variable");
    std::set<uint64_t> mutex;
    for (const auto& c:clauses) if (c.size()==2 && c[0]<0 && c[1]<0 &&
                                    c[0]!=c[1])
        mutex.insert(pairKey(-c[0],-c[1]));
    for (const auto& g:groups) {
        for (int a=0;a<3;++a) for (int b=a+1;b<3;++b)
            if (!mutex.count(pairKey(g[static_cast<size_t>(a)],
                                     g[static_cast<size_t>(b)])))
                return finish("missing_source_amo");
    }
    result.supported=true;
    result.groups=n;

    std::array<std::vector<int>,3> forbidden;
    for (const auto& c:clauses) {
        if (c.empty() || !std::all_of(c.begin(),c.end(),[](int lit){return lit<0;}))
            continue;
        const int first=-c[0];
        if (first<1 || first>variable_count) continue;
        const int machine=position[static_cast<size_t>(first)];
        int mask=0;
        bool valid=true;
        for (int lit:c) {
            const int x=-lit;
            if (x<1 || x>variable_count ||
                position[static_cast<size_t>(x)]!=machine) {valid=false;break;}
            mask|=1<<owner[static_cast<size_t>(x)];
        }
        if (valid) forbidden[static_cast<size_t>(machine)].push_back(mask);
    }
    for (auto& machine:forbidden) {
        std::sort(machine.begin(),machine.end());
        machine.erase(std::unique(machine.begin(),machine.end()),machine.end());
        result.selected_negative_clauses += static_cast<int>(machine.size());
    }
    if (!result.selected_negative_clauses) return finish("no_source_capacity_clauses");
    const int total=1<<n;
    const int all=total-1;
    std::array<std::vector<uint8_t>,3> allowed;
    for (int machine=0;machine<3;++machine) {
        auto& v=allowed[static_cast<size_t>(machine)];
        v.assign(static_cast<size_t>(total),1);
        for (int block:forbidden[static_cast<size_t>(machine)]) {
            // Each job subset containing an ORIGINAL negative clause is
            // impossible for that particular machine.
            const int free=all^block;
            int rem=free;
            while (true) {
                v[static_cast<size_t>(block|rem)]=0;
                if (!rem) break;
                rem=(rem-1)&free;
            }
        }
        result.admissible[static_cast<size_t>(machine)]=
            static_cast<int>(std::count(v.begin(),v.end(),uint8_t(1)));
    }

    // Exact-cover feasibility, not a capacity inequality or LP relaxation.
    // A satisfying assignment must choose precisely one of 3 machines per
    // job. Hence its three machine-subsets must be disjoint and partition all.
    for (int a=0;a<total;++a) {
        if (!allowed[0][static_cast<size_t>(a)]) continue;
        const int rest=all^a;
        int b=rest;
        while (true) {
            ++result.checked_partitions;
            if (allowed[1][static_cast<size_t>(b)] &&
                allowed[2][static_cast<size_t>(rest^b)])
                return finish("feasible_relaxed_partition");
            if ((result.checked_partitions&16383ULL)==0 &&
                std::chrono::duration<double>(Clock::now()-start).count()>budget_seconds)
                return finish("budget_exhausted");
            if (!b) break;
            b=(b-1)&rest;
        }
    }
    result.verified=true;
    result.reason="integer_cover_unsat_internal";
    result.seconds=std::chrono::duration<double>(Clock::now()-start).count();
    std::ostringstream out;
    out<<"{\"version\":\"drnas-ipg1-exact-cover-v1\","
       <<"\"source_sha256\":\""<<sha256<<"\","
       <<"\"source_variables\":"<<variable_count<<","
       <<"\"source_clauses\":"<<clauses.size()<<","
       <<"\"group_count\":"<<n<<","
       <<"\"machine_count\":3,"
       <<"\"selected_negative_clauses\":"<<result.selected_negative_clauses<<","
       <<"\"admissible_subsets\":["
       <<result.admissible[0]<<","<<result.admissible[1]<<","<<result.admissible[2]<<"],"
       <<"\"checked_partitions\":"<<result.checked_partitions<<","
       <<"\"claim\":\"UNSAT_EXHAUSTIVE_SOURCE_CLAUSE_COVER\"}";
    result.certificate_json=out.str();
    return result;
}
} // namespace drnas_ipg1
