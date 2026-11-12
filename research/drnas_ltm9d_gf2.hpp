// LTM9D: bounded native XOR/GF(2) contradiction detector on ORIGINAL CNF.
// Only complete 2^(k-1)-clause truth-table encodings (k<=4) imply a parity row.
// Gaussian elimination may conclude UNSAT only from 0 = 1.
// Abstain otherwise; no unsound learned clauses or speculative propagation.
#pragma once
#include <algorithm>
#include <array>
#include <cstdint>
#include <map>
#include <set>
#include <vector>
namespace ltm9d_gf2 {
struct Result {bool proved=false; unsigned equations=0; unsigned width=0;};
template<class CNF> Result prove(const CNF& f) {
    // This inexpensive version supports variable indices 1..64; otherwise abstain.
    std::map<std::vector<int>,std::set<unsigned>> groups;
    unsigned scanned=0;
    for(const auto& c:f.clauses) {
        if(++scanned>30000)return {};
        if(c.size()<2||c.size()>4)continue;
        std::vector<int> vars;
        bool ok=true;
        for(int lit:c) {
            if(lit==0 || lit>64 || lit< -64){ok=false;break;}
            vars.push_back(lit<0?-lit:lit);
        }
        if(!ok)continue;
        std::sort(vars.begin(),vars.end());
        if(std::adjacent_find(vars.begin(),vars.end())!=vars.end())continue;
        unsigned mask=0;
        for(unsigned j=0;j<vars.size();++j) {
            for(int lit:c)if(lit==-vars[j]){mask|=(1u<<j);break;}
        }
        groups[vars].insert(mask);
        if(groups.size()>4000)return {};
    }
    std::array<std::pair<std::uint64_t,unsigned>,64> basis{};
    std::array<bool,64> occupied{};
    unsigned equations=0;
    for(const auto& g:groups) {
        const auto& vars=g.first;
        const unsigned k=static_cast<unsigned>(vars.size());
        for(unsigned forbidden=0;forbidden<2;++forbidden) {
            bool complete=true;
            for(unsigned m=0;m<(1u<<k);++m) {
                if((static_cast<unsigned>(__builtin_popcount(m))&1u)==forbidden &&
                   !g.second.count(m)){complete=false;break;}
            }
            if(!complete)continue;
            ++equations;
            std::uint64_t bits=0;
            for(int v:vars)bits|=(std::uint64_t{1}<<(v-1));
            unsigned rhs=1u-forbidden;
            while(bits) {
                const unsigned pivot=63u-static_cast<unsigned>(__builtin_clzll(bits));
                if(!occupied[pivot]) {
                    occupied[pivot]=true;
                    basis[pivot]={bits,rhs};
                    break;
                }
                bits^=basis[pivot].first;
                rhs^=basis[pivot].second;
            }
            if(bits==0 && rhs==1u)return {true,equations,k};
        }
    }
    return {false,equations,0};
}
}
