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
#include <map>
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

// HALL2: find a complete matching between randomly ordered ALO options
// and the resource cliques. Every accepted edge is independently backed
// by ORIGINAL binary mutex clauses; a failed match cannot imply SAT.
inline bool match_wide_alo(const std::vector<int>& group,
                          std::vector<std::vector<int>>& resources,
                          const std::unordered_set<uint64_t>& mutex,
                          Clock::time_point deadline) {
    const size_t width=resources.size();
    if(group.size()!=width || !width)return false;
    std::vector<std::vector<int>> allowed(width);
    for(size_t i=0;i<width;++i) {
        if((i&3)==0 && Clock::now()>=deadline)return false;
        for(size_t col=0;col<width;++col) {
            bool all_mutex=true;
            for(int prior:resources[col]) {
                if(!no_both(group[i],prior,mutex)) {all_mutex=false;break;}
            }
            if(all_mutex)allowed[i].push_back(static_cast<int>(col));
        }
        if(allowed[i].empty())return false;
    }
    std::vector<int> assigned(width,-1);
    std::function<bool(int,std::vector<char>&)> augment=
        [&](int i,std::vector<char>& seen)->bool {
            for(int col:allowed[i]) {
                if(seen[col])continue;
                seen[col]=1;
                if(assigned[col]<0 || augment(assigned[col],seen)) {
                    assigned[col]=i;
                    return true;
                }
            }
            return false;
        };
    for(size_t i=0;i<width;++i) {
        if(Clock::now()>=deadline)return false;
        std::vector<char> seen(width,0);
        if(!augment(static_cast<int>(i),seen))return false;
    }
    for(size_t col=0;col<width;++col) {
        if(assigned[col]<0)return false;
        resources[col].push_back(group[assigned[col]]);
    }
    return true;
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
            std::vector<std::vector<int>> wide_alo;
            mutex.reserve(std::min<size_t>(clauses.size(),1000000));
            candidates.reserve(512);
            wide_alo.reserve(512);
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
                // Wide positive ALO groups often encode scheduling slots.
                // Keep them separately: millions of binary constraints must
                // never crowd out the source ALO clauses.
                if(clause.size()>12 && clause.size()<=96 && wide_alo.size()<1200){
                    std::unordered_set<int> uniq;
                    bool alo=true;
                    for(int v:clause)
                        if(v==0 || v < -nvars || v>nvars ||
                           !uniq.insert(std::abs(v)).second) {alo=false;break;}
                    if(alo)wide_alo.push_back(clause);
                }
            }
            if(!limit) {
                result.groups=static_cast<int>(candidates.size()+wide_alo.size()); // viable original ALO clauses
                // Fast, rigorously checked Hall columns: if n disjoint jobs
                // each need one of k slots and every cross-job same-column
                // pair is blocked by a source binary clause, n>k proves UNSAT.
                // This accepts wide time-slot CNFs (e.g. 75 jobs / 65 slots)
                // without BDD extraction, learned clauses, or CDCL search.
                std::map<size_t,std::vector<size_t>> by_width;
                for(size_t gi=0;gi<wide_alo.size();++gi)
                    by_width[wide_alo[gi].size()].push_back(gi);
                for(const auto& [width,indices]:by_width) {
                    if(result.verified || width<13 || indices.size()<=width)continue;
                    const size_t tries=std::min<size_t>(20,indices.size());
                    for(size_t ti=0;ti<tries&&!result.verified;++ti) {
                        if(Clock::now()>=deadline) {
                            result.reason="clause_wide_budget_exhausted";break;
                        }
                        size_t first=indices[(ti*indices.size())/tries];
                        std::vector<std::vector<int>> chosen(1,wide_alo[first]);
                        std::vector<std::vector<int>> resources(width);
                        std::unordered_set<int> used;
                        for(size_t col=0;col<width;++col) {
                            resources[col].push_back(wide_alo[first][col]);
                            used.insert(wide_alo[first][col]);
                        }
                        for(size_t gidx:indices) {
                            if((chosen.size()&15)==0 && Clock::now()>=deadline)break;
                            if(gidx==first)continue;
                            const auto& g=wide_alo[gidx];
                            bool compatible=true;
                            for(int v:g)if(used.count(v)){compatible=false;break;}
                            if(!compatible)continue;
                            for(size_t col=0;col<width && compatible;++col)
                                for(int earlier:resources[col])
                                    if(!no_both(g[col],earlier,mutex)){
                                        compatible=false;break;
                                    }
                            if(!compatible)continue;
                            chosen.push_back(g);
                            for(size_t col=0;col<width;++col) {
                                resources[col].push_back(g[col]);
                                used.insert(g[col]);
                            }
                            if(chosen.size()>width) {
                                if(check_local(chosen,resources,mutex)) {
                                    result.verified=true;
                                    result.reason="clause_hall_wide_columns_verified";
                                    result.groups=static_cast<int>(chosen.size());
                                    result.machines=static_cast<int>(width);
                                    result.demand=chosen.size();
                                    result.capacity=width;
                                    result.certificate_json=certificate(source_sha256,chosen,resources);
                                } else result.reason="clause_wide_local_certificate_rejected";
                                break;
                            }
                        }
                    }
                }
                // HALL2 fallback: order-independent signed wide Hall witnesses.
                // The original fast aligned-column path above is unchanged and
                // keeps its existing timing on previously solved SAT2026 sources.
                if(!result.verified) {
                    for(const auto& [width,indices]:by_width) {
                        if(result.verified || indices.size()<=width)continue;
                        const size_t tries=std::min<size_t>(12,indices.size());
                        for(size_t ti=0;ti<tries && !result.verified;++ti) {
                            if(Clock::now()>=deadline) {
                                result.reason="clause_hall2_budget_exhausted";break;
                            }
                            const size_t first=indices[(ti*indices.size())/tries];
                            std::vector<std::vector<int>> chosen(1,wide_alo[first]);
                            std::vector<std::vector<int>> resources(width);
                            std::unordered_set<int> used;
                            for(size_t col=0;col<width;++col) {
                                const int l=wide_alo[first][col];
                                resources[col].push_back(l);
                                used.insert(std::abs(l));
                            }
                            for(size_t idx:indices) {
                                if(Clock::now()>=deadline)break;
                                if(idx==first)continue;
                                const auto& group=wide_alo[idx];
                                bool disjoint=true;
                                for(int l:group)if(used.count(std::abs(l))) {
                                    disjoint=false;break;
                                }
                                if(!disjoint)continue;
                                auto proposed=resources;
                                if(!match_wide_alo(group,proposed,mutex,deadline))
                                    continue;
                                resources.swap(proposed);
                                chosen.push_back(group);
                                for(int l:group)used.insert(std::abs(l));
                                if(chosen.size()>width) {
                                    if(check_local(chosen,resources,mutex)) {
                                        result.verified=true;
                                        result.reason="clause_hall2_permutation_verified";
                                        result.groups=static_cast<int>(chosen.size());
                                        result.machines=static_cast<int>(width);
                                        result.demand=chosen.size();
                                        result.capacity=width;
                                        result.certificate_json=certificate(
                                            source_sha256,chosen,resources);
                                    } else result.reason="clause_hall2_local_certificate_rejected";
                                    break;
                                }
                            }
                        }
                    }
                }
                // Prioritize different widths so a mass of binary clauses cannot
                // starve an actual k-choice capacity pattern.
                std::vector<size_t> seeds;
                for(size_t width=2;width<=10;++width){
                    unsigned n=0;
                    for(size_t i=0;i<candidates.size() && n<18;++i)
                        if(candidates[i].size()==width) {seeds.push_back(i);++n;}
                }
                for(size_t si:seeds){
                    if(result.verified)break;
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
