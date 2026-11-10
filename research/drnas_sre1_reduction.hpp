// DRNAS SRE1: formally truth-preserving structural reduction for native CDCL.
// Copyright (c) 2026 Frane Drnas. All rights reserved.
// No SAT backend: original CNF -> implication SCC, source-certified GF(2)
// 1/2-variable rows, signed substitution, root UP, model reconstruction.
#pragma once
#include <climits>
#include <numeric>
#include <stack>
#include <unordered_set>
#include <sstream>

namespace drnas {
struct SRE1 {
    CNF reduced;
    int original_vars=0;
    std::vector<int> original_to_compact; // signed pre-UP variable
    std::vector<int8_t> fixed;            // +/-1, or 0 if unassigned
    std::vector<int> reindex;             // pre-UP -> post-UP
    bool contradiction=false, budget_skipped=false;
    uint64_t equivalences=0, opposite_equivalences=0;
    uint64_t root_units=0, tautologies=0, dropped_clauses=0;
    uint64_t graph_arcs=0, graph_scc=0, gf2_pairs=0, gf2_units=0;
    uint64_t original_clauses=0, compact_clauses=0;
    double preprocessing_s=0;
    static int at(int lit){return 2*(std::abs(lit)-1)+(lit<0);}
    std::vector<int8_t> lift(const std::vector<int8_t>& answer) const {
        std::vector<int8_t> old(original_vars+1,-1);
        for(int v=1;v<=original_vars;++v){
            int p=original_to_compact[v];
            if(!p)continue; // No constraints on this variable.
            const int c=std::abs(p);
            require(c<(int)fixed.size(),"SRE1 lift: invalid compact variable");
            int x=fixed[c];
            if(!x){
                require(c<(int)reindex.size(),"SRE1 lift: missing reindex");
                const int j=reindex[c];
                x=j?answer.at(j):-1;
                require(x==1 || x==-1,"SRE1 lift: missing solver assignment");
            }
            old[v]=(p<0)?-x:x;
        }
        return old;
    }
};
// All original CNF models map to a reduced model, and every reduced model
// reconstructs one model of the ORIGINAL CNF. The transformations below
// are equivalence preserving; UNSAT here remains uncertified by LRAT.
static SRE1 sre1_reduce(const CNF& input,bool enable_gf2_pairs=true) {
    const auto t0=Clock::now();
    SRE1 z;
    z.original_vars=input.vars;
    z.original_clauses=input.clauses.size();
    z.original_to_compact.assign(input.vars+1,0);
    auto identity=[&]() {
        z.budget_skipped=true;z.reduced=input;
        z.fixed.assign(input.vars+1,0);
        z.reindex.resize(input.vars+1);
        std::iota(z.reindex.begin(),z.reindex.end(),0);
        for(int v=1;v<=input.vars;++v)z.original_to_compact[v]=v;
        z.compact_clauses=z.reduced.clauses.size();
    };
    // Deterministic cost guard; if overhead likely large, abstain safely.
    if(input.vars>60000 || input.clauses.size()>250000){
        identity();
        z.preprocessing_s=std::chrono::duration<double>(Clock::now()-t0).count();
        return z;
    }
    const int n=input.vars;
    std::vector<std::vector<int>> adj(2*n),rev(2*n);
    auto edge=[&](int a,int b){
        adj[SRE1::at(a)].push_back(SRE1::at(b));
        rev[SRE1::at(b)].push_back(SRE1::at(a));
        ++z.graph_arcs;
    };
    auto add_binary=[&](int a,int b){
        if(!a || !b || std::abs(a)>n || std::abs(b)>n)
            throw std::runtime_error("SRE1 implication source literal outside range");
        edge(-a,b);edge(-b,a);
    };
    // All graph arcs are consequences of original binary clauses.
    for(const auto& c:input.clauses){
        if(c.size()==2 && c[0]!=c[1] && c[0]!=-c[1])
            add_binary(c[0],c[1]);
    }
    std::vector<std::vector<int>> certified_extra;
    if(enable_gf2_pairs && n<=20000 && input.clauses.size()<=15000) {
        auto rows=extract_source_xors(input);
        if(rows.size()>64)rows.resize(64);
        auto closed=derive_reductive_xors(rows);
        for(const auto& row:closed) {
            if(row.vars.size()==2){
                int a=row.vars[0],b=row.vars[1];
                std::vector<int> c1,c2;
                if(row.rhs==0){c1={-a,b};c2={a,-b};}
                else {c1={a,b};c2={-a,-b};}
                add_binary(c1[0],c1[1]);
                add_binary(c2[0],c2[1]);
                certified_extra.push_back(c1);
                certified_extra.push_back(c2);
                ++z.gf2_pairs;
            } else if(row.vars.size()==1){
                certified_extra.push_back({row.rhs?row.vars[0]:-row.vars[0]});
                ++z.gf2_units;
            } else if(row.vars.empty() && row.rhs) {
                z.contradiction=true;
            }
        }
    }
    // Kosaraju SCC with explicit DFS stack (no recursion depth risk).
    const int count=2*n;
    std::vector<uint8_t> seen(count,0);
    std::vector<int> order;order.reserve(count);
    std::vector<std::pair<int,size_t>> stack;
    for(int root=0;root<count;++root)if(!seen[root]){
        seen[root]=1;stack.push_back({root,0});
        while(!stack.empty()){
            auto& cur=stack.back();
            if(cur.second<adj[cur.first].size()){
                const int nxt=adj[cur.first][cur.second++];
                if(!seen[nxt]){seen[nxt]=1;stack.push_back({nxt,0});}
            } else {order.push_back(cur.first);stack.pop_back();}
        }
    }
    std::vector<int> comp(count,-1);
    int components=0;
    std::vector<int> todo;
    for(auto it=order.rbegin();it!=order.rend();++it)if(comp[*it]<0){
        comp[*it]=components;todo.push_back(*it);
        while(!todo.empty()){
            const int u=todo.back();todo.pop_back();
            for(int v:rev[u])if(comp[v]<0){comp[v]=components;todo.push_back(v);}
        }
        ++components;
    }
    z.graph_scc=components;
    for(int v=1;v<=n;++v)if(comp[SRE1::at(v)]==comp[SRE1::at(-v)])
        z.contradiction=true;
    if(z.contradiction){
        // A contradictory implication SCC is sound UNSAT (raw/no LRAT).
        z.reduced.vars=0;z.reduced.clauses={{}};
        z.fixed.assign(1,0);z.reindex.assign(1,0);
        z.preprocessing_s=std::chrono::duration<double>(Clock::now()-t0).count();
        return z;
    }
    std::vector<int> root(components,INT_MAX);
    for(int v=1;v<=n;++v){
        int pair=std::min(comp[SRE1::at(v)],comp[SRE1::at(-v)]);
        root[pair]=std::min(root[pair],v);
    }
    std::vector<int> root_index(n+1,0);
    std::vector<int> representative(n+1,0);
    std::vector<uint8_t> inverted(n+1,0);
    int initial=0;
    for(int v=1;v<=n;++v){
        const int p=std::min(comp[SRE1::at(v)],comp[SRE1::at(-v)]);
        const int r=root[p];
        require(r>=1 && r<=n,"SRE1 SCC representative invalid");
        representative[v]=r;
        inverted[v]=(comp[SRE1::at(v)]!=comp[SRE1::at(r)]);
        if(r!=v){++z.equivalences;z.opposite_equivalences+=inverted[v];}
        if(!root_index[r])root_index[r]=++initial;
        const int k=root_index[r];
        z.original_to_compact[v]=inverted[v]?-k:k;
    }
    z.fixed.assign(initial+1,0);
    z.reindex.assign(initial+1,0);
    auto convert=[&](int lit){
        const int v=std::abs(lit);
        require(v>0 && v<=n,"SRE1 CNF variable outside range");
        const int m=z.original_to_compact[v];
        return lit<0?-m:m;
    };
    std::vector<std::vector<int>> clauses;
    clauses.reserve(input.clauses.size()+certified_extra.size());
    auto append=[&](const std::vector<int>& orig){
        std::vector<int> c;
        c.reserve(orig.size());
        for(int l:orig)c.push_back(convert(l));
        std::sort(c.begin(),c.end(),[](int a,int b){
            return std::abs(a)<std::abs(b) ||
              (std::abs(a)==std::abs(b) && a<b);
        });
        std::vector<int> normal;
        bool tautology=false;
        for(int l:c){
            if(!normal.empty() && std::abs(normal.back())==std::abs(l)){
                if(normal.back()==-l){tautology=true;break;}
                continue;
            }
            normal.push_back(l);
        }
        if(tautology){++z.tautologies;return;}
        if(normal.empty())z.contradiction=true;
        clauses.push_back(std::move(normal));
    };
    for(const auto&c:input.clauses)append(c);
    for(const auto&c:certified_extra)append(c);
    // Bounded root-level UP, then rebuild clauses from fixed literals.
    // If the budget expires, the remaining CNF is retained unchanged
    // (modulo already-proven unit assignments).
    size_t visits=0;
    bool changed=true;
    while(changed && !z.contradiction && visits<1500000){
        changed=false;
        for(const auto&c:clauses){
            ++visits;
            int unknown=0,unit=0;
            bool satisfied=false;
            for(int lit:c){
                int val=z.fixed[std::abs(lit)];
                if(val==0){++unknown;unit=lit;}
                else if((lit>0?val:-val)>0){satisfied=true;break;}
            }
            if(satisfied)continue;
            if(unknown==0){z.contradiction=true;break;}
            if(unknown==1){
                int v=std::abs(unit), val=unit>0?1:-1;
                if(z.fixed[v] && z.fixed[v]!=val){z.contradiction=true;break;}
                if(!z.fixed[v]){z.fixed[v]=val;++z.root_units;changed=true;}
            }
            if(visits>=1500000)break;
        }
    }
    if(z.contradiction){
        z.reduced.vars=0;z.reduced.clauses={{}};
        z.preprocessing_s=std::chrono::duration<double>(Clock::now()-t0).count();
        return z;
    }
    std::vector<std::vector<int>> filtered;
    filtered.reserve(clauses.size());
    std::vector<uint8_t> needed(initial+1,0);
    for(const auto&c:clauses){
        std::vector<int> f;
        bool sat=false;
        for(int l:c){
            int val=z.fixed[std::abs(l)];
            if(val==0)f.push_back(l);
            else if((l>0?val:-val)>0){sat=true;break;}
        }
        if(sat){++z.dropped_clauses;continue;}
        if(f.empty()){z.contradiction=true;break;}
        for(int l:f)needed[std::abs(l)]=1;
        filtered.push_back(std::move(f));
    }
    if(z.contradiction){
        z.reduced.vars=0;z.reduced.clauses={{}};
    } else {
        for(int i=1;i<=initial;++i)
            if(needed[i])z.reindex[i]=++z.reduced.vars;
        for(auto&c:filtered){
            for(int&l:c){
                int j=z.reindex[std::abs(l)];
                require(j>0,"SRE1 missing reindexed variable");
                l=l>0?j:-j;
            }
        }
        z.reduced.clauses=std::move(filtered);
    }
    z.compact_clauses=z.reduced.clauses.size();
    z.preprocessing_s=std::chrono::duration<double>(Clock::now()-t0).count();
    return z;
}
} // namespace drnas
