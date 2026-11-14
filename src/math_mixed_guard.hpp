#pragma once
// Experimental source-clause proof-first mixed mathematical guard.
// Produces a bounded independent-checker-readable proof; never accepts guesses.
// The CDCL engine and its heuristics remain unchanged.
#include "pcmax_capacity.hpp"
#include <algorithm>
#include <array>
#include <chrono>
#include <cstdint>
#include <functional>
#include <map>
#include <numeric>
#include <queue>
#include <set>
#include <sstream>
#include <tuple>
#include <utility>
#include <vector>

namespace pcmax::mixed {
using Clock=std::chrono::steady_clock;
using Clauses=std::vector<std::vector<int>>;
struct Window {
    Clock::time_point deadline;
    explicit Window(double s):deadline(Clock::now()+std::chrono::duration_cast<Clock::duration>(
        std::chrono::duration<double>(s))){}
    bool live() const{return Clock::now()<deadline;}
};
inline int litnode(int l){return 2*(std::abs(l)-1)+(l<0);}
inline int nodelit(int i){return (i&1)?-(i/2+1):(i/2+1);}
inline std::string list(const std::vector<int>& a){
    std::ostringstream o;o<<'[';
    for(size_t i=0;i<a.size();++i){if(i)o<<',';o<<a[i];}
    o<<']';return o.str();
}
inline std::string prefix(const std::string& hash,const std::string& method){
    return "{\"format\":\"drnas-mixed-unsat1\",\"source_sha256\":\""+hash+
           "\",\"method\":\""+method+"\"";
}
inline std::vector<int> path(const std::vector<std::vector<int>>& g,
                             const std::vector<int>& comp,int src,int dst,
                             const Window& budget){
    std::vector<int> par(g.size(),-1);
    std::queue<int> q;
    par[src]=src;q.push(src);
    while(!q.empty()){
        if(!budget.live())return {};
        int u=q.front();q.pop();
        if(u==dst)break;
        for(int v:g[u])if(comp[u]==comp[v] && par[v]<0){
            par[v]=u;q.push(v);
        }
    }
    if(par[dst]<0)return {};
    std::vector<int> p;
    for(int x=dst;x!=src;x=par[x])p.push_back(nodelit(x));
    p.push_back(nodelit(src));
    std::reverse(p.begin(),p.end());
    return p;
}
inline bool binary_cycle(const Clauses& cs,int nv,const std::string& hash,
                         const Window& budget,Result& result){
    // The binary subset alone can prove a contradiction even when other
    // higher-width clauses are present. Bounded linear-time Kosaraju.
    if(nv<=0||nv>10000||cs.size()>200000)return false;
    const int n=2*nv;
    std::vector<std::vector<int>> g(n),rev(n);
    size_t edges=0;
    auto edge=[&](int a,int b){
        g[litnode(a)].push_back(litnode(b));
        rev[litnode(b)].push_back(litnode(a));
        ++edges;
    };
    for(size_t ci=0;ci<cs.size();++ci){
        if((ci&2047)==0 && !budget.live())return false;
        const auto& c=cs[ci];
        if(c.size()==1 && c[0]!=0)edge(-c[0],c[0]);
        if(c.size()==2 && c[0]!=0 && c[1]!=0){
            edge(-c[0],c[1]);edge(-c[1],c[0]);
        }
    }
    if(edges<2)return false;
    std::vector<char> seen(n,0);
    std::vector<int> order;order.reserve(n);
    for(int root=0;root<n;++root){
        if(seen[root])continue;
        std::vector<std::pair<int,size_t>> stack{{root,0}};
        seen[root]=1;
        while(!stack.empty()){
            if((order.size()&4095)==0 && !budget.live())return false;
            auto& top=stack.back();
            int u=top.first;
            if(top.second<g[u].size()){
                int v=g[u][top.second++];
                if(!seen[v]){seen[v]=1;stack.emplace_back(v,0);}
            }else{order.push_back(u);stack.pop_back();}
        }
    }
    std::vector<int> comp(n,-1);
    int component=0;
    for(auto it=order.rbegin();it!=order.rend();++it){
        if(comp[*it]>=0)continue;
        std::vector<int> stack{*it};
        comp[*it]=component;
        while(!stack.empty()){
            if(!budget.live())return false;
            int u=stack.back();stack.pop_back();
            for(int v:rev[u])if(comp[v]<0){
                comp[v]=component;stack.push_back(v);
            }
        }
        ++component;
    }
    for(int v=1;v<=nv;++v){
        if(comp[litnode(v)]!=comp[litnode(-v)])continue;
        auto forward=path(g,comp,litnode(v),litnode(-v),budget);
        auto backward=path(g,comp,litnode(-v),litnode(v),budget);
        if(forward.empty()||backward.empty())return false;
        std::ostringstream o;
        o<<prefix(hash,"binary_cycle")<<",\"pivot\":"<<v
         <<",\"pos_to_neg\":"<<list(forward)
         <<",\"neg_to_pos\":"<<list(backward)<<'}';
        result.verified=true;result.reason="mixed_2sat_scc_verified";
        result.certificate_json=o.str();
        return true;
    }
    return false;
}
struct XorBlock{std::vector<int> vars;int forbid=0;};
inline bool xor_rows(const Clauses& cs,int nv,const std::string& hash,
                     const Window& budget,Result& result){
    if(nv<=0||nv>5000||cs.size()>50000)return false;
    std::map<std::vector<int>,std::array<std::set<int>,2>> parity_masks;
    for(size_t i=0;i<cs.size();++i){
        if((i&1023)==0 && !budget.live())return false;
        const auto& clause=cs[i];
        if(clause.size()<3||clause.size()>8)continue;
        std::vector<int> vs;vs.reserve(clause.size());
        for(int l:clause)vs.push_back(std::abs(l));
        std::sort(vs.begin(),vs.end());
        if(vs.front()==0||std::unique(vs.begin(),vs.end())!=vs.end())continue;
        int mask=0;
        for(int l:clause){
            if(l<0){
                auto it=std::lower_bound(vs.begin(),vs.end(),-l);
                mask|=(1<<std::distance(vs.begin(),it));
            }
        }
        parity_masks[vs][__builtin_popcount(static_cast<unsigned>(mask))%2].insert(mask);
        if(parity_masks.size()>10000)return false;
    }
    std::vector<XorBlock> blocks;
    for(const auto& [vs,parities]:parity_masks){
        for(int p=0;p<2;++p)if(static_cast<int>(parities[p].size())==(1<<(vs.size()-1))){
            blocks.push_back({vs,p});
            if(blocks.size()>=32)break;
        }
        if(blocks.size()>=32)break;
    }
    if(blocks.size()<2)return false;
    using Row=std::tuple<std::set<int>,int,uint32_t>;
    std::map<int,Row> bases;
    for(size_t i=0;i<blocks.size();++i){
        if(!budget.live())return false;
        std::set<int> vars(blocks[i].vars.begin(),blocks[i].vars.end());
        int rhs=1-blocks[i].forbid;
        uint32_t trace=(1u<<i);
        while(!vars.empty()){
            int pivot=*vars.begin();
            auto it=bases.find(pivot);
            if(it==bases.end()){bases.emplace(pivot,Row{vars,rhs,trace});break;}
            const auto& [mask,base_rhs,base_trace]=it->second;
            std::set<int> updated;
            std::set_symmetric_difference(vars.begin(),vars.end(),
                                          mask.begin(),mask.end(),
                                          std::inserter(updated,updated.end()));
            vars.swap(updated);rhs^=base_rhs;trace^=base_trace;
        }
        if(vars.empty() && rhs==1){
            std::ostringstream o;
            o<<prefix(hash,"xor_gf2")<<",\"blocks\":[";
            for(size_t j=0;j<blocks.size();++j){
                if(j)o<<',';
                o<<"{\"vars\":"<<list(blocks[j].vars)
                 <<",\"forbidden_parity\":"<<blocks[j].forbid<<'}';
            }
            o<<"],\"combine\":[";
            bool first=true;
            for(size_t j=0;j<blocks.size();++j)if((trace>>j)&1u){
                if(!first)o<<',';
                first=false;o<<j;
            }
            o<<"]}";
            result.verified=true;result.reason="mixed_gf2_xor_verified";
            result.certificate_json=o.str();return true;
        }
    }
    return false;
}
inline bool dpll_tree(const Clauses& cs,int nv,const std::string& hash,
                      const Window& budget,Result& result){
    if(nv<=0||nv>8||cs.size()>512)return false;
    std::vector<int> assign(nv+1,-1);
    int nodes=0;
    std::function<bool(std::string&)> prove=[&](std::string& out)->bool{
        if(++nodes>350||!budget.live())return false;
        int best=99999,variable=0;
        for(const auto& clause:cs){
            bool sat=false;
            int possible=0,unbound=0;
            for(int lit:clause){
                const int value=assign[std::abs(lit)];
                if(value<0){++possible;unbound=std::abs(lit);}
                else if(value==(lit>0)){sat=true;break;}
            }
            if(sat)continue;
            if(possible==0){out="{\"clause\":"+list(clause)+"}";return true;}
            if(possible<best){best=possible;variable=unbound;}
        }
        if(!variable)return false;
        std::string left,right;
        assign[variable]=0;
        bool l=prove(left);
        assign[variable]=1;
        bool r=l?prove(right):false;
        assign[variable]=-1;
        if(!l||!r)return false;
        out="{\"split\":"+std::to_string(variable)+
            ",\"false\":"+left+",\"true\":"+right+"}";
        return true;
    };
    std::string tree;
    if(!prove(tree))return false;
    result.verified=true;result.reason="mixed_dpll_tree_verified";
    result.certificate_json=prefix(hash,"dpll_tree")+",\"tree\":"+tree+"}";
    return true;
}
inline Result analyze(const Clauses& cs,int nv,const std::string& hash,
                      const Options& options){
    const auto started=Clock::now();
    Result r;
    r.reason="mixed_no_bounded_proof";
    if(!std::isfinite(options.seconds)||options.seconds<=0||hash.size()!=64 ||
       nv<=0||nv>200000||cs.size()>1000000){
        r.reason="mixed_size_or_budget_gate";return r;
    }
    Window budget(options.seconds);
    if(binary_cycle(cs,nv,hash,budget,r)){}
    else if(budget.live()&&xor_rows(cs,nv,hash,budget,r)){}
    else if(budget.live())dpll_tree(cs,nv,hash,budget,r);
    if(!r.verified && !budget.live())r.reason="mixed_budget_exhausted";
    r.elapsed=std::chrono::duration<double>(Clock::now()-started).count();
    return r;
}
} // namespace pcmax::mixed
