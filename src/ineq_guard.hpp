#pragma once
// DRNAS INEQ-GUARD1: bounded source-clause parity-cycle detector.
// Hamming triangle and deterministic CHSH4 are instances of inconsistent
// signed equality / inequality constraints, not quantum Bell experiments.
// No solver subprocess, no learning-state changes, no SAT classification.
// UNSAT is reported only with a source-bound structural certificate.
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <functional>
#include <map>
#include <numeric>
#include <queue>
#include <sstream>
#include <string>
#include <utility>
#include <vector>

namespace pcmax {
namespace ineq_detail {
using Clock=std::chrono::steady_clock;
struct Edge { int u,v,p; };
inline std::string classify(size_t n) {
    if(n==3)return "triangle";
    if(n==4)return "chsh4";
    return "parity_cycle";
}
inline std::string json_proof(const std::string& source,
                             const std::vector<Edge>& edges) {
    std::ostringstream s;
    s << "{\"format\":\"drnas-ineq-guard-v1\",\"source_sha256\":\""
      << source << "\",\"witness\":\"" << classify(edges.size())
      << "\",\"edges\":[";
    for(size_t i=0;i<edges.size();++i) {
        if(i)s << ',';
        s << '[' << edges[i].u << ',' << edges[i].v << ','
          << edges[i].p << ']';
    }
    s << "]}";
    return s.str();
}
} // namespace ineq_detail

inline Result analyze_ineq_guard(const std::vector<std::vector<int>>& clauses,
                                 int nvars,const std::string& source_sha,
                                 const Options& opts) {
    using namespace ineq_detail;
    const auto began=Clock::now();
    Result out;
    out.reason="ineq_no_complete_signed_pair_cycle";
    auto finish=[&]() {
        out.elapsed=std::chrono::duration<double>(Clock::now()-began).count();
        return out;
    };
    if(!std::isfinite(opts.seconds) || opts.seconds<=0 ||
       nvars<2 || nvars>50000 || clauses.size()>200000 ||
       source_sha.size()!=64) {
        out.reason="ineq_input_or_budget_gate";
        return finish();
    }
    const auto deadline=began+std::chrono::duration_cast<Clock::duration>(
        std::chrono::duration<double>(opts.seconds));
    // Key = sorted variable pair. Mask stores clauses by sign pattern:
    // 0 = ( x v y), 1 = ( x v -y), 2 = (-x v y), 3 = (-x v -y).
    std::map<std::pair<int,int>,unsigned char> patterns;
    for(size_t i=0;i<clauses.size();++i) {
        if((i&1023)==0 && Clock::now()>=deadline){
            out.reason="ineq_scan_budget";return finish();
        }
        const auto& c=clauses[i];
        if(c.size()!=2)continue;
        const int a=std::abs(c[0]), b=std::abs(c[1]);
        if(a==0||b==0||a>nvars||b>nvars||a==b)continue;
        const int u=std::min(a,b),v=std::max(a,b);
        const int first=(a==u?c[0]:c[1]);
        const int second=(a==u?c[1]:c[0]);
        const unsigned pattern=(first<0?2u:0u)|(second<0?1u:0u);
        const auto key=std::make_pair(u,v);
        if(patterns.size()>=100000 && patterns.find(key)==patterns.end()){
            out.reason="ineq_pair_limit";return finish();
        }
        patterns[key]|=static_cast<unsigned char>(1u<<pattern);
    }
    std::vector<int> parent(size_t(nvars)+1),rank(size_t(nvars)+1,0),
                     sign(size_t(nvars)+1,0);
    std::iota(parent.begin(),parent.end(),0);
    std::function<std::pair<int,int>(int)> root=[&](int x)->std::pair<int,int>{
        if(parent[size_t(x)]==x)return {x,0};
        const auto [r,p]=root(parent[size_t(x)]);
        sign[size_t(x)]^=p; parent[size_t(x)]=r;
        return {r,sign[size_t(x)]};
    };
    std::vector<Edge> spanning;
    std::vector<std::vector<std::pair<int,int>>> adj(size_t(nvars)+1);
    for(const auto& item:patterns) {
        if(Clock::now()>=deadline){
            out.reason="ineq_union_budget";return finish();
        }
        const int u=item.first.first,v=item.first.second;
        const unsigned mask=item.second;
        // Full original clauses, never an incomplete XOR guess.
        const bool eq=(mask&(1u<<1)) && (mask&(1u<<2));
        const bool neq=(mask&(1u<<0)) && (mask&(1u<<3));
        for(int p=0;p<=1;++p){
            if(!(p?neq:eq))continue;
            const auto [ru,pu]=root(u);
            const auto [rv,pv]=root(v);
            if(ru!=rv) {
                int a=ru,b=rv;
                if(rank[size_t(a)]>rank[size_t(b)])std::swap(a,b);
                parent[size_t(a)]=b;
                sign[size_t(a)]=pu^pv^p;
                if(rank[size_t(a)]==rank[size_t(b)])++rank[size_t(b)];
                const int id=static_cast<int>(spanning.size());
                spanning.push_back({u,v,p});
                adj[size_t(u)].push_back({v,id});
                adj[size_t(v)].push_back({u,id});
            } else if((pu^pv)!=p) {
                // The spanning forest path plus this edge is an odd-parity
                // closed walk. Only its original clauses justify the proof.
                std::vector<int> prev(size_t(nvars)+1,-1),
                                 via(size_t(nvars)+1,-1);
                std::queue<int> q; q.push(u); prev[size_t(u)]=u;
                size_t visits=0;
                while(!q.empty() && prev[size_t(v)]<0) {
                    if((++visits&1023)==0 && Clock::now()>=deadline){
                        out.reason="ineq_path_budget";return finish();
                    }
                    int cur=q.front();q.pop();
                    for(const auto& [to,id]:adj[size_t(cur)]) {
                        if(prev[size_t(to)]>=0)continue;
                        prev[size_t(to)]=cur; via[size_t(to)]=id;
                        q.push(to);
                    }
                }
                if(prev[size_t(v)]<0){out.reason="ineq_path_missing";return finish();}
                std::vector<Edge> witness;
                for(int cur=v;cur!=u;cur=prev[size_t(cur)]){
                    if(witness.size()>=256){
                        out.reason="ineq_witness_too_long";return finish();
                    }
                    witness.push_back(spanning[size_t(via[size_t(cur)])]);
                }
                witness.push_back({u,v,p});
                int xor_sum=0;
                std::map<int,int> degrees;
                for(const auto& e:witness){
                    xor_sum^=e.p;
                    degrees[e.u]^=1;degrees[e.v]^=1;
                }
                if(xor_sum!=1 || !std::all_of(degrees.begin(),degrees.end(),
                    [](const auto& z){return z.second==0;})){
                    out.reason="ineq_local_witness_invalid";return finish();
                }
                out.verified=true;
                out.groups=static_cast<int>(witness.size());
                out.demand=1;
                out.capacity=0;
                out.reason="ineq_"+classify(witness.size())+"_source_contradiction";
                out.certificate_json=json_proof(source_sha,witness);
                return finish();
            }
        }
    }
    return finish();
}
} // namespace pcmax
