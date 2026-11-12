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
struct Result { bool proved=false; unsigned rows=0, cols=0; };
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
        std::vector<std::vector<int>> rows{anchor};
        std::unordered_set<int> used(anchor.begin(),anchor.end());
        for (std::size_t ri=0;ri<positive.size();++ri) {
            if (ri==ai || positive[ri].size()!=k) continue;
            std::vector<int> mapped(k,0);
            bool ok=true;
            // A row's choices must map bijectively to anchor columns.
            for (int lit:positive[ri]) {
                if (used.count(lit)) { ok=false; break; }
                int slot=-1;
                for (std::size_t j=0;j<k;++j) if (incompatible(lit,anchor[j])) {
                    if (slot!=-1) { slot=-2; break; }
                    slot=static_cast<int>(j);
                }
                if (slot<0 || mapped[static_cast<std::size_t>(slot)]!=0) {
                    ok=false;break;
                }
                mapped[static_cast<std::size_t>(slot)]=lit;
            }
            if (!ok) continue;
            // Every two different rows must conflict in every same column.
            // These negative binary clauses, not names or inferred structure,
            // supply the entire mathematical UNSAT justification.
            for (const auto& old:rows) {
                for (std::size_t j=0;j<k;++j) {
                    if (!mapped[j] || !incompatible(old[j],mapped[j])) {
                        ok=false;break;
                    }
                }
                if (!ok)break;
            }
            if (!ok)continue;
            rows.push_back(mapped);
            used.insert(mapped.begin(),mapped.end());
            if (rows.size()>k)
                return {true,static_cast<unsigned>(rows.size()),static_cast<unsigned>(k)};
        }
    }
    return {};
}
}  // namespace ltm9_php
