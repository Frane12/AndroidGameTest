#pragma once
// EXPERIMENTAL, opt-in, proof-first clause-only pigeonhole / Hall-capacity rule.
// Every inference uses ORIGINAL DIMACS clauses; no BDD or solver subprocess.
// This is a sufficient condition for UNSAT, NOT a complete scheduling method.
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <functional>
#include <limits>
#include <numeric>
#include <sstream>
#include <string>
#include <unordered_set>
#include <vector>

namespace pcmax {
namespace clause_hall_detail {
using Clock = std::chrono::steady_clock;

inline uint32_t keylit(int x) {
    return (static_cast<uint32_t>(x < 0 ? -x : x) << 1) | uint32_t(x < 0);
}
inline uint64_t keypair(int x, int y) {
    uint32_t a = keylit(x), b = keylit(y);
    if (a > b) std::swap(a, b);
    return (uint64_t(a) << 32) | b;
}
inline bool no_both(int x, int y, const std::unordered_set<uint64_t>& mutex) {
    return mutex.find(keypair(x,y)) != mutex.end();
}

inline bool assign_to_cliques(const std::vector<int>& g,
                              std::vector<std::vector<int>>& cliques,
                              const std::unordered_set<uint64_t>& mutex,
                              Clock::time_point deadline) {
    // A bounded exact search for a placement of EVERY option of one ALO group
    // into already existing at-most-one cliques. Branching here only proposes
    // a certificate: verification checks every binary clause separately.
    std::vector<int> order(g.size());
    std::iota(order.begin(),order.end(),0);
    std::sort(order.begin(),order.end(),[&](int ia,int ib){
        auto compatible = [&](int value) {
            int count=0;
            for (const auto& c:cliques) {
                bool ok=true;
                for (int x:c) if (!no_both(value,x,mutex)) {ok=false;break;}
                count+=ok;
            }
            return count;
        };
        return compatible(g[ia])<compatible(g[ib]);
    });
    uint64_t steps=0;
    std::function<bool(size_t)> dfs = [&](size_t at) -> bool {
        if (at==order.size())return true;
        if (++steps > 4096 || Clock::now()>=deadline)return false;
        int l=g[order[at]];
        for (auto& c:cliques) {
            bool ok=true;
            for (int x:c) if (!no_both(l,x,mutex)) {ok=false;break;}
            if (!ok) continue;
            c.push_back(l);
            if (dfs(at+1))return true;
            c.pop_back();
        }
        return false;
    };
    return dfs(0);
}

inline std::string certificate(const std::string& source_hash,
                                const std::vector<std::vector<int>>& groups,
                                const std::vector<std::vector<int>>& resources) {
    std::ostringstream os;
    os << "{\"format\":\"pcmax-clause-hall-v1\",\"source_sha256\":\""
       << source_hash << "\",\"alo_groups\":[";
    for(size_t i=0;i<groups.size();++i){
        if(i)os<<',';
        os<<'[';
        for(size_t j=0;j<groups[i].size();++j){if(j)os<<',';os<<groups[i][j];}
        os<<']';
    }
    os<<"],\"resource_cliques\":[";
    for(size_t i=0;i<resources.size();++i){
        if(i)os<<',';
        os<<'[';
        for(size_t j=0;j<resources[i].size();++j){if(j)os<<',';os<<resources[i][j];}
        os<<']';
    }
    os<<"],\"required_groups\":"<<groups.size()
      <<",\"resource_bound\":"<<resources.size()<<"}";
    return os.str();
}

inline bool check_local(const std::vector<std::vector<int>>& selected,
                        const std::vector<std::vector<int>>& resources,
                        const std::unordered_set<uint64_t>& mutex) {
    if (selected.size()<=resources.size() || resources.empty())return false;
    std::unordered_set<int> used, covered;
    for (const auto& group:selected) {
        if(group.empty())return false;
        for(int lit:group) {
            if(!used.insert(std::abs(lit)).second)return false;
        }
    }
    for (const auto& resource:resources){
        for(size_t i=0;i<resource.size();++i) {
            covered.insert(resource[i]);
            for(size_t j=0;j<i;++j)
                if(!no_both(resource[i],resource[j],mutex))return false;
        }
    }
    for(const auto& group:selected)for(int lit:group)
        if(!covered.count(lit))return false;
    return true;
}
} // namespace clause_hall_detail

inline Result analyze_clause_hall(const std::vector<std::vector<int>>& clauses,int nvars,
                                   const std::string& source_sha256,const Options& options) {
    using namespace clause_hall_detail;
    const auto t0=Clock::now();
    Result result;
    result.reason="clause_no_capacity_contradiction";
    try{
        if(!std::isfinite(options.seconds) || options.seconds<=0 ||
           source_sha256.size()!=64 || nvars<=0 || nvars>200000){
            result.reason="clause_invalid_budget_or_input";
        }else{
            const auto deadline=t0+std::chrono::duration_cast<Clock::duration>(
                std::chrono::duration<double>(options.seconds));
            std::unordered_set<uint64_t> mutex;
            std::vector<std::vector<int>> candidates;
            mutex.reserve(std::min<size_t>(clauses.size(),1000000));
            candidates.reserve(512);
            bool limit=false;
            for(size_t i=0;i<clauses.size();++i) {
                if((i&8191)==0 && Clock::now()>=deadline) {
                    result.reason="clause_budget_exhausted_index";limit=true;break;
                }
                const auto& clause=clauses[i];
                if(clause.size()==2 && clause[0] && clause[1] &&
                   std::abs(clause[0])<=nvars && std::abs(clause[1])<=nvars) {
                    if(mutex.size()<1500000)
                        mutex.insert(keypair(-clause[0],-clause[1]));
                    else {result.reason="clause_mutex_edge_limit";limit=true;break;}
                }
                if(clause.size()>=2 && clause.size()<=12 && candidates.size()<16000){
                    std::unordered_set<int> seen;
                    bool ok=true;
                    for(int l:clause) {
                        if(!l || std::abs(l)>nvars || !seen.insert(std::abs(l)).second) {
                            ok=false;break;
                        }
                    }
                    if(ok)candidates.push_back(clause);
                }
            }
            if(!limit) {
                result.groups=static_cast<int>(candidates.size()); // telemetry: viable original ALO clauses
                // Prioritize different widths so a mass of binary clauses cannot
                // starve an actual k-choice capacity pattern.
                std::vector<size_t> seeds;
                for(size_t width=2;width<=10;++width){
                    unsigned n=0;
                    for(size_t i=0;i<candidates.size() && n<18;++i)
                        if(candidates[i].size()==width) {seeds.push_back(i);++n;}
                }
                for(size_t si:seeds){
                    if(Clock::now()>=deadline) {
                        result.reason="clause_budget_exhausted_search";break;
                    }
                    ++result.rounds;
                    const auto& initial=candidates[si];
                    const size_t k=initial.size();
                    if(k<2 || k>10)continue;
                    std::vector<std::vector<int>> resources(k);
                    std::vector<std::vector<int>> selected(1,initial);
                    std::unordered_set<int> vars;
                    for(size_t j=0;j<k;++j){
                        resources[j].push_back(initial[j]);
                        vars.insert(std::abs(initial[j]));
                    }
                    // All selected ALO groups have disjoint variables. For any
                    // satisfying assignment there are >=number_of_groups true
                    // literals; k source-verified mutex cliques allow <=k.
                    for(size_t gi=0;gi<candidates.size();++gi){
                        if((gi&63)==0 && Clock::now()>=deadline)break;
                        if(gi==si || candidates[gi].size()>k+2)continue;
                        const auto& g=candidates[gi];
                        bool overlap=false;
                        for(int l:g) if(vars.count(std::abs(l))){overlap=true;break;}
                        if(overlap)continue;
                        auto proposed=resources;
                        if(!assign_to_cliques(g,proposed,mutex,deadline))continue;
                        selected.push_back(g);
                        resources.swap(proposed);
                        for(int l:g)vars.insert(std::abs(l));
                        if(selected.size()>k){
                            if(check_local(selected,resources,mutex)){
                                result.verified=true;
                                result.reason="clause_hall_integer_capacity_certificate";
                                result.groups=static_cast<int>(selected.size());
                                result.machines=static_cast<int>(k);
                                result.demand=selected.size();
                                result.capacity=k;
                                result.certificate_json=certificate(source_sha256,selected,resources);
                            }else result.reason="clause_local_certificate_rejected";
                            break;
                        }
                    }
                    if(result.verified)break;
                }
            }
        }
    }catch(const std::bad_alloc&){result.verified=false;result.reason="clause_allocation_guard";}
     catch(const std::exception&){result.verified=false;result.reason="clause_exception_guard";}
    result.elapsed=std::chrono::duration<double>(Clock::now()-t0).count();
    return result;
}
} // namespace pcmax
