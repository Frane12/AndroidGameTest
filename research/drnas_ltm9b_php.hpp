// DRNAS LTM9: sound cardinality/graph-injection contradiction detector.
// A certificate consists of R > K disjoint positive-choice clauses of size K.
// With a consistent K-column matching and pairwise exclusions in every column,
// each choice column serves at most one row, making all R rows impossible.
// No label or generator index is consulted. Other CNF clauses only strengthen it.
#pragma once
#include <algorithm>
#include <cstdint>
#include <unordered_set>
#include <vector>

namespace ltm9_php {
struct Result { bool proved=false; unsigned rows=0, cols=0; std::vector<std::vector<int>> witness; };
inline std::uint64_t edge(int a, int b) {
    const auto lo=static_cast<std::uint32_t>(std::min(a,b));
    const auto hi=static_cast<std::uint32_t>(std::max(a,b));
    return (std::uint64_t(lo)<<32)|hi;
}
template<class CNF> Result prove(const CNF& formula) {
    std::unordered_set<std::uint64_t> exclusions;
    std::vector<std::vector<int>> positive;
    for (const auto& c:formula.clauses) {
        if (c.size()==2 && c[0]<0 && c[1]<0 && c[0]!=c[1]) {
            exclusions.insert(edge(-c[0],-c[1]));
        }
        if (c.size()<2 || c.size()>32) continue;
        bool valid=true;
        std::unordered_set<int> uniq;
        for (int lit:c) {
            if (lit<=0 || !uniq.insert(lit).second) { valid=false; break; }
        }
        if (valid) positive.push_back(c);
    }
    const auto incompatible=[&](int a,int b) {
        return exclusions.find(edge(a,b))!=exclusions.end();
    };
    for (std::size_t ai=0; ai<positive.size(); ++ai) {
        const auto& anchor=positive[ai];
        const auto k=anchor.size();
        // Precompute every candidate's uniquely matched anchor-column mapping.
        // Greedy selection is NOT permutation invariant: a distractor row can
        // block a genuine (K+1)-clique. Backtrack with a fixed effort budget.
        std::vector<std::vector<int>> candidates;
        for (std::size_t ri=0;ri<positive.size();++ri) {
            if (ri==ai || positive[ri].size()!=k)continue;
            std::vector<int> mapped(k,0);
            bool ok=true;
            for (int lit:positive[ri]) {
                if (std::find(anchor.begin(),anchor.end(),lit)!=anchor.end()) {
                    ok=false;break;
                }
                int slot=-1;
                for (std::size_t j=0;j<k;++j)if(incompatible(lit,anchor[j])){
                    if(slot!=-1){slot=-2;break;}
                    slot=static_cast<int>(j);
                }
                if(slot<0 || mapped[static_cast<std::size_t>(slot)]){
                    ok=false;break;
                }
                mapped[static_cast<std::size_t>(slot)]=lit;
            }
            if(ok)candidates.push_back(std::move(mapped));
        }
        std::vector<std::vector<int>> rows{anchor};
        std::unordered_set<int> used(anchor.begin(),anchor.end());
        std::size_t searched=0;
        auto extend=[&](auto&& self,std::size_t first)->bool {
            if(rows.size()>k)return true;
            if(rows.size()+candidates.size()-first<=k)return false;
            if(++searched>50000)return false; // bounded: abstain, never infer.
            for(std::size_t ri=first;ri<candidates.size();++ri){
                const auto& mapped=candidates[ri];
                bool ok=true;
                for(int v:mapped)if(used.count(v)){ok=false;break;}
                if(!ok)continue;
                for(const auto& old:rows){
                    for(std::size_t col=0;col<k;++col){
                        if(!incompatible(old[col],mapped[col])){
                            ok=false;break;
                        }
                    }
                    if(!ok)break;
                }
                if(!ok)continue;
                for(int v:mapped)used.insert(v);
                rows.push_back(mapped);
                if(self(self,ri+1))return true;
                rows.pop_back();
                for(int v:mapped)used.erase(v);
            }
            return false;
        };
        if(extend(extend,0))
            return {true,static_cast<unsigned>(rows.size()),
                    static_cast<unsigned>(k),rows};
    }
    return {};
}
}  // namespace ltm9_php
