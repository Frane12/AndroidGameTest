// Experimental source-bound CNF mutex clique-cover UNSAT pre-gate.
// Conservative; OFF by default. Certificate is NOT a standard VeriPB/DRAT proof.
#pragma once
#include <algorithm>
#include <chrono>
#include <cstdint>
#include <numeric>
#include <sstream>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <vector>

namespace pcmax_clique {
using Clock = std::chrono::steady_clock;
struct Result {
    bool verified=false;
    std::string reason="not_attempted";
    std::string certificate_json;
    int demand=0, capacity=0, selector_vars=0, bucket_width=0;
};
inline uint64_t key(int a,int b) {
    if(a>b) std::swap(a,b);
    return (uint64_t(uint32_t(a))<<32)|uint32_t(b);
}
struct Budget {
    Clock::time_point end;
    uint64_t steps=0;
    explicit Budget(double seconds):end(Clock::now()+std::chrono::duration_cast<Clock::duration>(std::chrono::duration<double>(seconds))){}
    bool ok() {return (++steps&1023ULL) != 0 || Clock::now()<end;}
};
struct IndexedGroup {size_t clause_index;std::vector<int> lits;};
inline Result analyze(const std::vector<std::vector<int>>& clauses,int nvars,
                      const std::string& sha,double budget_seconds) {
    Result out;
    if(budget_seconds<=0){out.reason="budget_exhausted";return out;}
    if(nvars<=0 || nvars>200000 || clauses.size()>1000000){out.reason="size_gate";return out;}
    Budget budget(budget_seconds);
    std::unordered_map<size_t,std::vector<IndexedGroup>> by_width;
    std::unordered_set<uint64_t> mutex;
    mutex.reserve(clauses.size());
    for(size_t i=0;i<clauses.size();++i) {
        if(!budget.ok()){out.reason="budget_exhausted_during_extract";return out;}
        const auto& c=clauses[i];
        if(c.size()==2 && c[0]<0 && c[1]<0 && c[0]!=c[1])
            mutex.insert(key(-c[0],-c[1]));
        if(c.size()<2 || c.size()>64)continue;
        if(!std::all_of(c.begin(),c.end(),[](int x){return x>0;}))continue;
        std::unordered_set<int> distinct(c.begin(),c.end());
        if(distinct.size()!=c.size())continue;
        by_width[c.size()].push_back({i,c});
    }
    std::vector<size_t> widths;
    for(auto &p:by_width) {
        if(p.second.size()>=3 && p.second.size()<=24)widths.push_back(p.first);
    }
    std::sort(widths.begin(),widths.end(),[&](size_t a,size_t b){
        if(by_width[a].size()!=by_width[b].size())return by_width[a].size()<by_width[b].size();
        return a>b;
    });
    for(size_t width:widths){
        if(!budget.ok()){out.reason="budget_exhausted_search";return out;}
        auto &bucket=by_width[width];
        if(bucket.size()*width>256)continue;
        std::vector<int> selectors;
        std::unordered_set<int> distinct;
        bool collision=false;
        for(const auto &g:bucket)for(int x:g.lits){
            if(!distinct.insert(x).second)collision=true;
            selectors.push_back(x);
        }
        if(collision)continue;
        const size_t n=selectors.size();
        std::vector<std::vector<uint8_t>> edge(n,std::vector<uint8_t>(n,0));
        for(size_t u=0;u<n;++u)for(size_t v=u+1;v<n;++v){
            if(!budget.ok()){out.reason="budget_exhausted_pair_checks";return out;}
            if(mutex.count(key(selectors[u],selectors[v])))edge[u][v]=edge[v][u]=1;
        }
        std::vector<uint8_t> left(n,1);
        size_t remaining=n;
        std::vector<std::vector<int>> cover;
        while(remaining && cover.size()<bucket.size()){
            if(!budget.ok()){out.reason="budget_exhausted_cliques";return out;}
            std::vector<std::pair<int,int>> degree;
            degree.reserve(remaining);
            for(size_t u=0;u<n;++u)if(left[u]){
                int cnt=0;for(size_t v=0;v<n;++v)if(left[v]&&edge[u][v])++cnt;
                degree.push_back({cnt,int(u)});
            }
            std::sort(degree.begin(),degree.end(),[](auto a,auto b){
                return a.first!=b.first ? a.first>b.first : a.second<b.second;
            });
            std::vector<int> best;
            const size_t seeds=std::min<size_t>(32,degree.size());
            for(size_t si=0;si<seeds;++si){
                int start=degree[si].second;
                std::vector<int> clique{start},candidates;
                for(size_t v=0;v<n;++v)if(left[v]&&edge[start][v])candidates.push_back(int(v));
                while(!candidates.empty()){
                    if(!budget.ok()){out.reason="budget_exhausted_greedy";return out;}
                    int chosen=-1,score=-1,global=-1;
                    for(int v:candidates){
                        int s=0,g=0;
                        for(int q:candidates)s+=edge[v][q];
                        for(size_t q=0;q<n;++q)if(left[q])g+=edge[v][q];
                        if(s>score || (s==score&&g>global)){chosen=v;score=s;global=g;}
                    }
                    clique.push_back(chosen);
                    std::vector<int> update;
                    for(int v:candidates)if(edge[chosen][v])update.push_back(v);
                    candidates.swap(update);
                }
                if(clique.size()>best.size())best.swap(clique);
            }
            if(best.empty())break;
            std::vector<int> proof_clique;
            for(int v:best){
                if(!left[v]){out.reason="internal_overlap";return out;}
                proof_clique.push_back(selectors[v]);left[v]=0;--remaining;
            }
            cover.push_back(std::move(proof_clique));
        }
        if(remaining || cover.size()>=bucket.size())continue;
        std::unordered_set<int> covered;
        bool valid=true;
        for(const auto &cl:cover){
            for(size_t i=0;i<cl.size();++i){
                if(!covered.insert(cl[i]).second)valid=false;
                for(size_t j=i+1;j<cl.size();++j)
                    if(!mutex.count(key(cl[i],cl[j])))valid=false;
            }
        }
        if(!valid || covered.size()!=selectors.size())continue;
        std::ostringstream cert;
        cert<<"{\"format\":\"pcmax-scale6-clique-cover-v1\",\"source_sha256\":\""<<sha
            <<"\",\"job_clause_indices\":[";
        for(size_t i=0;i<bucket.size();++i){if(i)cert<<',';cert<<bucket[i].clause_index;}
        cert<<"],\"mutex_cliques\":[";
        for(size_t i=0;i<cover.size();++i){if(i)cert<<',';cert<<'[';
            for(size_t j=0;j<cover[i].size();++j){if(j)cert<<',';cert<<cover[i][j];}
            cert<<']';
        }
        cert<<"],\"demand\":"<<bucket.size()<<",\"capacity\":"<<cover.size()
            <<",\"claim\":\"UNSAT\"}";
        out.certificate_json=cert.str();out.verified=true;
        out.reason="source_mutex_clique_cover";
        out.demand=int(bucket.size());out.capacity=int(cover.size());
        out.selector_vars=int(selectors.size());out.bucket_width=int(width);
        return out;
    }
    out.reason="no_source_clique_cover_witness";
    return out;
}
} // namespace pcmax_clique
