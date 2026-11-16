#pragma once
// DRNAS experimental residual 2-CNF SCC test.
// The caller supplies ONLY clauses of residual width <=2 under the current
// CDCL trail. Contradictory SCC is a sufficient UNSAT condition even when
// other source clauses still have more than two unassigned literals.
// This header makes NO SAT claim when the binary subformula is consistent.
#include <algorithm>
#include <cstdlib>
#include <utility>
#include <vector>
#include <cstddef>
#include <cstdint>

namespace drnas_residual {
inline int contradiction_witness(int n, const std::vector<std::pair<int,int>>& clauses) {
    const int N = 2*n;
    std::vector<std::vector<int>> g(static_cast<size_t>(N));
    std::vector<std::vector<int>> rev(static_cast<size_t>(N));
    auto vertex=[](int lit) { return (std::abs(lit)-1)*2 + (lit<0); };
    auto edge=[&](int a,int b) {
        g[static_cast<size_t>(a)].push_back(b);
        rev[static_cast<size_t>(b)].push_back(a);
    };
    for (auto [a,b] : clauses) {
        const int ia=vertex(a);
        if (!b) edge(ia^1,ia);
        else {
            const int ib=vertex(b);
            edge(ia^1,ib);
            edge(ib^1,ia);
        }
    }
    std::vector<uint8_t> seen(static_cast<size_t>(N),0);
    std::vector<int> order;
    order.reserve(static_cast<size_t>(N));
    for (int start=0;start<N;++start) {
        if (seen[static_cast<size_t>(start)]) continue;
        std::vector<std::pair<int,size_t>> st;
        st.emplace_back(start,0);
        seen[static_cast<size_t>(start)]=1;
        while (!st.empty()) {
            const int v=st.back().first;
            size_t& i=st.back().second;
            if (i<g[static_cast<size_t>(v)].size()) {
                const int w=g[static_cast<size_t>(v)][i++];
                if (!seen[static_cast<size_t>(w)]) {
                    seen[static_cast<size_t>(w)]=1;
                    st.emplace_back(w,0);
                }
            } else {
                order.push_back(v);
                st.pop_back();
            }
        }
    }
    std::vector<int> comp(static_cast<size_t>(N),-1);
    int next_comp=0;
    for (auto it=order.rbegin();it!=order.rend();++it) {
        if (comp[static_cast<size_t>(*it)]>=0) continue;
        std::vector<int> st{*it};
        comp[static_cast<size_t>(*it)]=next_comp;
        while (!st.empty()) {
            const int v=st.back();st.pop_back();
            for (int w:rev[static_cast<size_t>(v)]) {
                if (comp[static_cast<size_t>(w)]<0) {
                    comp[static_cast<size_t>(w)]=next_comp;
                    st.push_back(w);
                }
            }
        }
        ++next_comp;
    }
    for (int v=0;v<n;++v) {
        if (comp[static_cast<size_t>(2*v)]==comp[static_cast<size_t>(2*v+1)])
            return v+1;
    }
    return 0;
}
} // namespace drnas_residual
