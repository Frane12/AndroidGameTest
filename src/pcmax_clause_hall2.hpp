#pragma once
// HALL2: exact deficient-subset detection from ORIGINAL CNF ALO and binary
// exclusion clauses. A matching search only PROPOSES a witness; the unchanged
// independent HALL1 checker validates all original-clause implications.
#include "pcmax_clause_hall.hpp"
#include <queue>
#include <unordered_map>

namespace pcmax {
namespace hall2_detail {
using namespace clause_hall_detail;
struct Deficit {
    std::vector<size_t> group_ids, resource_ids;
};

// An alternating-tree Hall witness exists iff the group-to-clique bipartite
// graph has no matching covering every ALO group. Resource cliques already
// cover every choice literal and certify that at most one member can be TRUE.
inline Deficit find_deficit(const std::vector<std::vector<int>>& groups,
                           const std::vector<std::vector<int>>& cliques,
                           Clock::time_point deadline) {
    Deficit out;
    const size_t ng=groups.size(), nk=cliques.size();
    if(ng<2 || nk==0 || ng>128 || nk>96)return out;
    std::unordered_map<int,int> location;
    for(size_t r=0;r<nk;++r)
        for(int x:cliques[r])
            if(!location.emplace(x,int(r)).second)return out;
    std::vector<std::vector<int>> adj(ng);
    for(size_t g=0;g<ng;++g) {
        for(int x:groups[g]) {
            const auto it=location.find(x);
            if(it==location.end())return out;
            adj[g].push_back(it->second);
        }
        std::sort(adj[g].begin(),adj[g].end());
        adj[g].erase(std::unique(adj[g].begin(),adj[g].end()),adj[g].end());
    }
    std::vector<int> owner(nk,-1), mate(ng,-1);
    for(size_t gi=0;gi<ng;++gi) {
        if(Clock::now()>=deadline)return out;
        std::vector<bool> seen(nk,false);
        std::function<bool(int)> augment=[&](int g)->bool {
            for(int r:adj[g]) {
                if(seen[r])continue;
                seen[r]=true;
                if(owner[r]<0 || augment(owner[r])) {
                    owner[r]=g;mate[g]=r;return true;
                }
            }
            return false;
        };
        augment(int(gi));
    }
    std::queue<int> q;
    std::vector<bool> gs(ng,false),rs(nk,false);
    for(size_t g=0;g<ng;++g)
        if(mate[g]<0){q.push(int(g));gs[g]=true;}
    if(q.empty())return out;
    while(!q.empty()) {
        if(Clock::now()>=deadline)return {};
        const int g=q.front();q.pop();
        for(int r:adj[g]) {
            rs[r]=true;
            const int next=owner[r];
            if(next>=0 && !gs[next]){gs[next]=true;q.push(next);}
        }
    }
    for(size_t g=0;g<ng;++g)if(gs[g])out.group_ids.push_back(g);
    for(size_t r=0;r<nk;++r)if(rs[r])out.resource_ids.push_back(r);
    if(out.group_ids.size()<=out.resource_ids.size())return {};
    return out;
}
} // namespace hall2_detail

inline Result analyze_clause_hall2(const std::vector<std::vector<int>>& clauses,int nvars,
                                   const std::string& source_sha256,const Options& options) {
    using namespace clause_hall_detail;
    using namespace hall2_detail;
    const auto t0=Clock::now();
    Result result;result.reason="hall2_no_subset_deficit";
    try {
        if(!std::isfinite(options.seconds) || options.seconds<=0 || nvars<1 ||
           nvars>200000 || source_sha256.size()!=64){
            result.reason="hall2_invalid_budget_or_input";
        } else {
            auto deadline=t0+std::chrono::duration_cast<Clock::duration>(
                std::chrono::duration<double>(options.seconds));
            std::unordered_set<uint64_t> mutex;
            mutex.reserve(std::min<size_t>(clauses.size(),600000));
            std::vector<std::vector<int>> small,wide;
            small.reserve(800);wide.reserve(100);
            bool hit_limit=false;
            for(size_t i=0;i<clauses.size();++i) {
                if((i&4095)==0 && Clock::now()>=deadline){hit_limit=true;break;}
                const auto& c=clauses[i];
                if(c.size()==2 && mutex.size()<1500000)
                    mutex.insert(keypair(-c[0],-c[1]));
                if(c.size()<2 || c.size()>96)continue;
                const bool w=c.size()>12;
                if((w && wide.size()>=250) || (!w && small.size()>=12000))continue;
                std::unordered_set<int> seen;
                bool ok=true;
                for(int x:c)if(!x || std::abs(x)>nvars ||
                    !seen.insert(std::abs(x)).second || (w && x<0)){ok=false;break;}
                if(ok){if(w)wide.push_back(c);else small.push_back(c);}
            }
            if(hit_limit){result.reason="hall2_budget_index";}
            else {
                result.groups=int(small.size()+wide.size());
                std::vector<size_t> seeds;
                for(size_t width=2;width<=10;++width){
                    size_t n=0;
                    for(size_t i=0;i<small.size() && n<18;++i)
                        if(small[i].size()==width){seeds.push_back(i);++n;}
                }
                for(size_t si:seeds) {
                    if(Clock::now()>=deadline){result.reason="hall2_budget_search";break;}
                    ++result.rounds;
                    const auto& first=small[si];
                    const size_t k=first.size();
                    std::vector<std::vector<int>> cliques(k),selected(1,first);
                    std::unordered_set<int> used;
                    for(size_t r=0;r<k;++r){
                        cliques[r].push_back(first[r]);
                        used.insert(std::abs(first[r]));
                    }
                    size_t attempts=0;
                    for(size_t ci=0;ci<small.size();++ci){
                        if((++attempts&31)==0 && Clock::now()>=deadline)break;
                        if(selected.size()>k+6)break;
                        if(ci==si)continue;
                        const auto& g=small[ci];
                        if(g.size()>k+2)continue;
                        bool overlap=false;
                        for(int x:g)if(used.count(std::abs(x))){overlap=true;break;}
                        if(overlap)continue;
                        auto proposed=cliques;
                        if(!assign_to_cliques(g,proposed,mutex,deadline))continue;
                        selected.push_back(g);cliques.swap(proposed);
                        for(int x:g)used.insert(std::abs(x));
                        const Deficit violator=find_deficit(selected,cliques,deadline);
                        if(violator.group_ids.empty())continue;
                        std::vector<std::vector<int>> subset,resources;
                        std::unordered_set<int> needed;
                        for(size_t gidx:violator.group_ids){
                            subset.push_back(selected[gidx]);
                            for(int lit:selected[gidx])needed.insert(lit);
                        }
                        for(size_t ridx:violator.resource_ids){
                            std::vector<int> restricted;
                            for(int lit:cliques[ridx])
                                if(needed.count(lit))restricted.push_back(lit);
                            if(!restricted.empty())resources.push_back(std::move(restricted));
                        }
                        if(!check_local(subset,resources,mutex))continue;
                        result.verified=true;
                        result.reason="clause_hall2_subset_certificate";
                        result.groups=int(subset.size());
                        result.machines=int(resources.size());
                        result.demand=subset.size();
                        result.capacity=resources.size();
                        result.certificate_json=certificate(source_sha256,subset,resources);
                        break;
                    }
                    if(result.verified)break;
                }
            }
        }
    } catch(const std::bad_alloc&){
        result.verified=false;result.reason="hall2_allocation_guard";
    } catch(const std::exception&){
        result.verified=false;result.reason="hall2_exception_guard";
    }
    result.elapsed=std::chrono::duration<double>(Clock::now()-t0).count();
    return result;
}
} // namespace pcmax
