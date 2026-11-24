// Experimental PCMAX SCALE3 native Hall proof guard.
// Optional; standalone from CDCL. Strict source-clause checks; UNKNOWN on unsupported input.
// This produces a source-bound JSON Hall certificate, NOT VeriPB/DRAT/LRAT.
#pragma once
#include <algorithm>
#include <chrono>
#include <cstdint>
#include <deque>
#include <functional>
#include <numeric>
#include <sstream>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <vector>

namespace pcmax_hall {
using Clock = std::chrono::steady_clock;
struct Result {
    bool verified = false;
    std::string reason = "not_attempted";
    std::string certificate_json;
    size_t jobs = 0, slots = 0, demand = 0, capacity = 0;
};
struct Stop { std::string reason; };
struct Limit {
    Clock::time_point end;
    uint64_t steps = 0;
    explicit Limit(double seconds) : end(Clock::now() + std::chrono::duration_cast<Clock::duration>(std::chrono::duration<double>(seconds))) {}
    void check() {
        if ((++steps & 1023ULL) == 0 && Clock::now() >= end) throw Stop{"hall_budget_exhausted"};
    }
};
inline uint64_t pairkey(int a, int b) {
    if (a>b) std::swap(a,b);
    return (uint64_t(uint32_t(a))<<32) | uint32_t(b);
}
struct DSU {
    std::vector<int> parent, sz;
    explicit DSU(size_t n) : parent(n+1),sz(n+1,1) { std::iota(parent.begin(),parent.end(),0); }
    int find(int u) { while(parent[u]!=u) { parent[u]=parent[parent[u]];u=parent[u];} return u; }
    void unite(int u,int v) {
        u=find(u);v=find(v);if(u==v)return;
        if(sz[u]<sz[v])std::swap(u,v);
        parent[v]=u;sz[u]+=sz[v];
    }
};
inline Result analyze(const std::vector<std::vector<int>>& cnf, int nvars,
                      const std::string& sha, double budget_seconds) {
    Result out;
    try {
        if (budget_seconds<=0) throw Stop{"hall_budget_exhausted"};
        if (nvars<=0 || nvars>200000 || cnf.size()>1000000) throw Stop{"hall_size_gate"};
        Limit budget(budget_seconds);
        std::vector<int> belongs(nvars+1,-1);
        std::vector<size_t> clause_indexes;
        size_t selectors=0;
        for(size_t ci=0;ci<cnf.size();++ci) {
            budget.check();
            const auto &cl=cnf[ci];
            if(cl.size()<2 || !std::all_of(cl.begin(),cl.end(),[](int lit){return lit>0;}))continue;
            int job=static_cast<int>(clause_indexes.size());
            clause_indexes.push_back(ci);
            if(clause_indexes.size()>10000) throw Stop{"hall_job_limit"};
            for(int lit:cl) {
                if(lit>nvars || belongs[lit]!=-1) throw Stop{"hall_overlapping_positive_demands"};
                belongs[lit]=job;
                if(++selectors>40000)throw Stop{"hall_selector_limit"};
            }
        }
        out.jobs=clause_indexes.size();
        if(out.jobs<2) throw Stop{"hall_no_disjoint_demands"};
        std::unordered_set<uint64_t> mutex;
        mutex.reserve(std::min<size_t>(cnf.size(),1000000));
        DSU dsu(nvars);
        for(const auto &cl:cnf) {
            budget.check();
            if(cl.size()!=2 || cl[0]>=0 || cl[1]>=0)continue;
            int a=-cl[0],b=-cl[1];
            if(a<=0 || b<=0 || a>nvars || b>nvars || a==b)continue;
            mutex.insert(pairkey(a,b));
            if(belongs[a]>=0 && belongs[b]>=0 && belongs[a]!=belongs[b])dsu.unite(a,b);
        }
        std::unordered_map<int,int> root_to_bin;
        std::vector<std::vector<int>> bins;
        for(int v=1;v<=nvars;++v) {
            budget.check();
            if(belongs[v]<0)continue;
            int r=dsu.find(v);
            auto [it,ins]=root_to_bin.emplace(r,static_cast<int>(bins.size()));
            if(ins)bins.emplace_back();
            bins[it->second].push_back(v);
        }
        out.slots=bins.size();
        // Fail closed if a mutex-connected bin is not a literal clique.
        // Bound the quadratic audit before doing it; this remains optional.
        size_t pairs=0;
        for(const auto &bin:bins) {
            size_t s=bin.size();
            if(s>1 && (s-1)>10000000/s) throw Stop{"hall_clique_work_limit"};
            pairs+=s*(s-1)/2;
            if(pairs>2000000) throw Stop{"hall_clique_work_limit"};
        }
        for(const auto& bin:bins)for(size_t i=0;i<bin.size();++i)for(size_t j=i+1;j<bin.size();++j) {
            budget.check();
            if(!mutex.count(pairkey(bin[i],bin[j])))throw Stop{"hall_non_clique_component"};
        }
        std::vector<std::vector<int>> adj(clause_indexes.size());
        std::vector<int> varbin(nvars+1,-1);
        for(size_t b=0;b<bins.size();++b) for(int v:bins[b])varbin[v]=static_cast<int>(b);
        for(size_t j=0;j<clause_indexes.size();++j) {
            for(int v:cnf[clause_indexes[j]])adj[j].push_back(varbin[v]);
            std::sort(adj[j].begin(),adj[j].end());
            adj[j].erase(std::unique(adj[j].begin(),adj[j].end()),adj[j].end());
        }
        // Classical Hopcroft-Karp; no guessing expected SAT/UNSAT labels.
        const int nj=static_cast<int>(adj.size()), nb=static_cast<int>(bins.size());
        std::vector<int> pairu(nj,-1),pairv(nb,-1),dist(nj);
        auto bfs=[&](){
            std::deque<int> q;bool found=false;
            for(int u=0;u<nj;++u){dist[u]=pairu[u]<0?0:nj+1;if(pairu[u]<0)q.push_back(u);}
            while(!q.empty()){
                int u=q.front();q.pop_front();budget.check();
                for(int v:adj[u]){int p=pairv[v];if(p<0)found=true;else if(dist[p]==nj+1){dist[p]=dist[u]+1;q.push_back(p);}}
            }
            return found;
        };
        std::function<bool(int)> dfs=[&](int u){
            budget.check();
            for(int v:adj[u]){
                int p=pairv[v];if(p<0 || (dist[p]==dist[u]+1 && dfs(p))){pairu[u]=v;pairv[v]=u;return true;}
            }
            dist[u]=nj+1;return false;
        };
        int matched=0;
        while(bfs())for(int u=0;u<nj;++u)if(pairu[u]<0 && dfs(u))++matched;
        if(matched==nj){out.reason="hall_no_witness";return out;}
        std::vector<uint8_t> seenj(nj,0),seenb(nb,0);
        std::deque<int> q;
        for(int u=0;u<nj;++u)if(pairu[u]<0){seenj[u]=1;q.push_back(u);}
        while(!q.empty()){
            int u=q.front();q.pop_front();budget.check();
            for(int v:adj[u]){
                if(seenb[v])continue;
                seenb[v]=1;
                if(pairv[v]>=0 && !seenj[pairv[v]]){seenj[pairv[v]]=1;q.push_back(pairv[v]);}
            }
        }
        std::vector<int> jobs, slots;
        for(int i=0;i<nj;++i)if(seenj[i])jobs.push_back(i);
        for(int i=0;i<nb;++i)if(seenb[i])slots.push_back(i);
        if(jobs.size()<=slots.size() || slots.empty())throw Stop{"hall_internal_witness_failure"};
        // Validate source entailment again before reporting UNSAT. Every selected
        // assignment variable belongs to precisely one certified mutex clique.
        std::vector<uint8_t> covered(nvars+1,0);
        for(int b:slots)for(int v:bins[b]){
            if(covered[v]) throw Stop{"hall_overlap_in_certificate"};
            covered[v]=1;
        }
        for(int j:jobs)for(int v:cnf[clause_indexes[j]])if(!covered[v])throw Stop{"hall_uncovered_assignment"};
        for(int b:slots)for(size_t i=0;i<bins[b].size();++i)for(size_t k=i+1;k<bins[b].size();++k)
            if(!mutex.count(pairkey(bins[b][i],bins[b][k])))throw Stop{"hall_invalid_mutex_clause"};
        out.demand=jobs.size();out.capacity=slots.size();
        std::ostringstream s;
        s << "{\"format\":\"pcmax-scale3-hall-source-v1\",\"source_sha256\":\"" << sha << "\",\"job_clause_indices\":[";
        for(size_t i=0;i<jobs.size();++i){if(i)s<<',';s<<clause_indexes[jobs[i]];}
        s<<"],\"mutex_slot_groups\":[";
        for(size_t i=0;i<slots.size();++i){if(i)s<<',';s<<'[';
            const auto &bin=bins[slots[i]];for(size_t j=0;j<bin.size();++j){if(j)s<<',';s<<bin[j];}s<<']';
        }
        s<<"],\"demand\":"<<out.demand<<",\"capacity\":"<<out.capacity<<",\"claim\":\"UNSAT\"}";
        out.certificate_json=s.str();out.verified=true;out.reason="source_hall_certificate";
        return out;
    } catch(const Stop &s){out.reason=s.reason;return out;}
}
}
