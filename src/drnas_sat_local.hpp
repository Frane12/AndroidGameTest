// DRNAS SAT LOCAL-HYBRID1: source-closed component SAT construction and
// bounded XOR-pattern hints inside an otherwise unchanged single-core CDCL.
// No new UNSAT claims. Hints are never clauses or proof steps.
#pragma once
#include "drnas_sat_construct.hpp"
#include <algorithm>
#include <bit>
#include <chrono>
#include <cstdint>
#include <map>
#include <numeric>
#include <unordered_map>
#include <utility>
#include <vector>

namespace satlocal {
using satconstruct::CNF;
using Clock = satconstruct::Clock;

struct Outcome {
    std::vector<int8_t> full_model;
    std::vector<int8_t> hints;        // -1/0/+1, always advisory unless RUP-tested
    int source_components=0;
    int solved_components=0;
    int xor_patterns=0;
    int hinted_variables=0;
    bool full() const { return !full_model.empty(); }
};
inline double left_ms(Clock::time_point deadline) {
    return std::chrono::duration<double,std::milli>(deadline-Clock::now()).count();
}
struct DSU {
    std::vector<int> p, sz;
    explicit DSU(int n):p(n),sz(n,1) { std::iota(p.begin(),p.end(),0); }
    int root(int a) { while(p[a]!=a) {p[a]=p[p[a]];a=p[a];} return a; }
    void join(int a,int b) {
        a=root(a);b=root(b);if(a==b)return;
        if(sz[a]<sz[b])std::swap(a,b);
        p[b]=a;sz[a]+=sz[b];
    }
};
inline Outcome analyze(int n,const CNF& f,double budget_ms) {
    Outcome out;
    if(n<=0||n>15000||f.size()>130000||budget_ms<=0.0)return out;
    out.hints.assign(static_cast<size_t>(n),0);
    const auto deadline=Clock::now()+std::chrono::duration_cast<Clock::duration>(
        std::chrono::duration<double,std::milli>(budget_ms));
    int64_t litcount=0;
    DSU uf(n);
    std::vector<uint8_t> present(n,0);
    for(size_t ci=0;ci<f.size();++ci) {
        if((ci&511)==0 && left_ms(deadline)<=0)return out;
        const auto& c=f[ci];
        if(c.empty())return out;
        litcount+=static_cast<int64_t>(c.size());
        if(litcount>600000)return out;
        int lead=std::abs(c.front())-1;
        if(lead<0||lead>=n)return out;
        present[lead]=1;
        for(int lit:c) {
            int v=std::abs(lit)-1;
            if(v<0||v>=n)return out;
            present[v]=1;uf.join(lead,v);
        }
    }
    // A component is *closed*: no original clause shares its variables
    // with any other component. Thus independently verified SAT witnesses
    // can be combined, but a witness for a non-closed subset is ONLY a hint.
    std::map<int,std::vector<int>> vars;
    std::map<int,std::vector<size_t>> clauses;
    for(int v=0;v<n;++v) if(present[v])vars[uf.root(v)].push_back(v);
    for(size_t ci=0;ci<f.size();++ci) {
        const int root=uf.root(std::abs(f[ci][0])-1);
        clauses[root].push_back(ci);
    }
    out.source_components=static_cast<int>(vars.size());
    bool all_closed_solved=out.source_components>1;
    if(out.source_components>1) {
        // Small components first, so useful partial models are kept even
        // when one large component is unsupported or budget-exhausted.
        std::vector<int> order;
        for(const auto& [root,ids]:vars)order.push_back(root);
        std::stable_sort(order.begin(),order.end(),[&](int a,int b) {
            return clauses[a].size()<clauses[b].size();
        });
        std::vector<int> local_index(n,-1);
        for(int key:order) {
            if(left_ms(deadline)<0.2){all_closed_solved=false;break;}
            const auto& ids=vars[key];
            if(ids.size()>15000){all_closed_solved=false;continue;}
            for(size_t i=0;i<ids.size();++i)local_index[ids[i]]=static_cast<int>(i)+1;
            CNF local;
            local.reserve(clauses[key].size());
            for(size_t ci:clauses[key]) {
                std::vector<int> c;
                c.reserve(f[ci].size());
                for(int lit:f[ci]) {
                    const int v=local_index[std::abs(lit)-1];
                    c.push_back(lit>0?v:-v);
                }
                local.push_back(std::move(c));
            }
            const double remain=left_ms(deadline);
            satconstruct::Limits lim;
            lim.max_ms=std::min(remain,6.0);
            const auto result=satconstruct::analyze(static_cast<int>(ids.size()),local,lim);
            if(result.sat()) {
                ++out.solved_components;
                for(size_t i=0;i<ids.size();++i)
                    out.hints[ids[i]]=result.model[i];
            } else all_closed_solved=false;
            for(int v:ids)local_index[v]=-1;
        }
        if(all_closed_solved && out.solved_components==out.source_components) {
            std::vector<int8_t> model(n,-1);
            for(int v=0;v<n;++v)if(out.hints[v])model[v]=out.hints[v];
            if(satconstruct::verify(n,f,model)) {
                out.full_model=std::move(model);
                out.hinted_variables=static_cast<int>(std::count_if(
                    out.hints.begin(),out.hints.end(),[](int8_t x){return x!=0;}));
                return out;
            }
        }
    }
    if(left_ms(deadline)<0.3 || n>4096 || f.size()>30000)return out;

    // Find parity blocks from signed source clauses. A complete parity
    // pattern has exactly 2^(k-1) different forbidden assignments for k
    // variables (k=2..4). The subset is never treated as independent
    // of other original clauses. Its satisfying model is advisory only.
    struct Pattern {
        uint16_t mask=0;
        std::vector<std::vector<int>> clauses;
    };
    std::map<std::vector<int>,Pattern> patterns;
    for(size_t ci=0;ci<f.size();++ci) {
        if((ci&255)==0 && left_ms(deadline)<=0.2)return out;
        const auto& c=f[ci];
        const int k=static_cast<int>(c.size());
        if(k<2||k>4)continue;
        std::vector<std::pair<int,int>> sorted;
        for(int lit:c)sorted.push_back({std::abs(lit),lit<0?1:0});
        std::sort(sorted.begin(),sorted.end());
        bool distinct=true;int sign=0;
        std::vector<int> key;key.reserve(k);
        for(int i=0;i<k;++i){
            if(i && sorted[i].first==sorted[i-1].first)distinct=false;
            sign|=sorted[i].second<<i;
            key.push_back(sorted[i].first);
        }
        if(!distinct)continue;
        Pattern& p=patterns[key];
        p.mask|=static_cast<uint16_t>(1U<<sign);
        p.clauses.push_back(c);
    }
    CNF xor_clauses;
    std::vector<int> xor_vars;
    std::vector<uint8_t> xor_used(n,0);
    for(const auto& [ids,p]:patterns) {
        const int k=static_cast<int>(ids.size());
        uint16_t even=0,odd=0;
        for(int a=0;a<(1<<k);++a){
            if(std::popcount(static_cast<unsigned>(a))&1)odd|=static_cast<uint16_t>(1U<<a);
            else even|=static_cast<uint16_t>(1U<<a);
        }
        if(p.mask!=even && p.mask!=odd)continue;
        ++out.xor_patterns;
        for(int v:ids) {
            if(!xor_used[v-1]) {xor_used[v-1]=1;xor_vars.push_back(v);}
        }
        for(const auto& c:p.clauses)xor_clauses.push_back(c);
        if(xor_clauses.size()>16000)break;
    }
    if(out.xor_patterns && xor_vars.size()<=2048 &&
       xor_clauses.size()<=16000 && left_ms(deadline)>0.5) {
        std::sort(xor_vars.begin(),xor_vars.end());
        std::vector<int> index(n,-1);
        for(size_t i=0;i<xor_vars.size();++i)index[xor_vars[i]-1]=static_cast<int>(i)+1;
        CNF local;local.reserve(xor_clauses.size());
        for(const auto& c:xor_clauses) {
            std::vector<int> row;
            for(int lit:c) {
                const int v=index[std::abs(lit)-1];
                if(!v)continue;
                row.push_back(lit>0?v:-v);
            }
            local.push_back(std::move(row));
        }
        satconstruct::Limits lim;
        lim.max_ms=std::min(6.0,left_ms(deadline));
        auto cand=satconstruct::analyze(static_cast<int>(xor_vars.size()),local,lim);
        if(cand.sat()) {
            for(size_t i=0;i<xor_vars.size();++i) {
                const int v=xor_vars[i]-1;
                if(!out.hints[v])out.hints[v]=cand.model[i];
            }
        }
    }
    out.hinted_variables=static_cast<int>(std::count_if(out.hints.begin(),
        out.hints.end(),[](int8_t x){return x!=0;}));
    if(out.hinted_variables>0) {
        std::vector<int8_t> model(n,-1);
        for(int v=0;v<n;++v)if(out.hints[v])model[v]=out.hints[v];
        // A lucky complete candidate is SAT only after the ENTIRE original
        // CNF is checked, never from a partial XOR solution alone.
        if(satconstruct::verify(n,f,model))out.full_model=std::move(model);
    }
    return out;
}
} // namespace satlocal
