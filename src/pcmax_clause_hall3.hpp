#pragma once
// HALL3: BDD-bounded selector resources plus original-CNF mutex-certified
// clique resources, with a disjoint literal cover. Opt-in, proof-first.
#include "pcmax_clause_hall2.hpp"
#include <chrono>
#include <cstdint>
#include <numeric>
#include <sstream>
#include <unordered_set>
#include <vector>

namespace pcmax {
namespace hall3_detail {
using Clock=std::chrono::steady_clock;

inline std::vector<std::vector<int>> make_cliques(const detail::Graph& g,
                                                  const std::vector<char>& bdd_owned,
                                                  detail::Budget& budget) {
    std::vector<std::vector<int>> cliques;
    size_t ticks=0;
    for (const auto& group:g.groups) {
        for (int v:group) {
            if (bdd_owned[v]) continue;
            if ((++ticks&255)==0)budget.check();
            bool placed=false;
            for (auto& clique:cliques) {
                bool okay=true;
                for (int old:clique) {
                    if (!detail::has(g.clauses,{-v,-old})) {okay=false;break;}
                }
                if(okay){clique.push_back(v);placed=true;break;}
            }
            if(!placed)cliques.push_back({v});
        }
    }
    return cliques;
}

// Integer certificate: disjoint BDD selector ownership and mutex resources.
inline bool candidate(const detail::Graph& g,const std::string& sha,
                      const std::vector<std::vector<int>>& cliques,
                      std::vector<int64_t> weights, detail::Budget& budget, Result& out) {
    budget.check();
    if (weights.size()!=g.groups.size())return false;
    int64_t divisor=0;
    for (int64_t weight:weights) {
        if(weight<0 || weight>1000000)return false;
        divisor=std::gcd(divisor,weight);
    }
    if(divisor==0)return false;
    for(auto& weight:weights)weight/=divisor;
    const int64_t demand=std::accumulate(weights.begin(),weights.end(),int64_t(0));
    const auto bdd=detail::bounds(g,weights,budget);
    int64_t upper=std::accumulate(bdd.capacities.begin(),bdd.capacities.end(),int64_t(0));
    std::vector<int64_t> clique_caps;
    for (const auto& clique:cliques) {
        int64_t maximum=0;
        for(int variable:clique)maximum=std::max(maximum,weights.at(g.membership.at(variable)));
        clique_caps.push_back(maximum);
        upper+=maximum;
    }
    if(demand<=upper)return false;
    // Exact independent Python checker validates every source clause. The
    // BDD-only verifier cannot apply because it rejects non-BDD selectors.
    std::ostringstream os;
    os<<"{\"format\":\"pcmax-hall3-hybrid-v1\",\"source_sha256\":\""<<sha
      <<"\",\"selected_groups\":[";
    std::vector<int64_t> selected;
    bool first=true;
    for(size_t j=0;j<weights.size();++j)if(weights[j]) {
        if(!first)os<<',';
        first=false;
        detail::array(os,g.groups[j]);selected.push_back(weights[j]);
    }
    os<<"],\"group_weights\":";
    detail::array(os,selected);
    os<<",\"required\":"<<demand<<",\"capacity_sum\":"<<upper<<",\"machines\":[";
    for(size_t mid=0;mid<g.machines.size();++mid) {
        const auto& m=g.machines[mid];
        if(mid)os<<',';
        os<<"{\"root\":"<<m.root<<",\"variable_order\":";
        detail::array(os,m.order);
        os<<",\"true_terminal\":"<<m.yes<<",\"false_terminal\":"<<m.no
          <<",\"capacity\":"<<bdd.capacities[mid]<<",\"transitions\":[";
        for(size_t k=0;k<m.nodes.size();++k) {
            if(k)os<<',';
            const int p=m.nodes[k];
            const auto& n=g.nodes[p];
            os<<'['<<p<<','<<n.x<<','<<n.left<<','<<n.right<<']';
        }
        os<<"]}";
    }
    os<<"],\"resource_cliques\":[";
    for(size_t k=0;k<cliques.size();++k) {
        if(k)os<<',';
        detail::array(os,cliques[k]);
    }
    os<<"],\"resource_capacities\":";
    detail::array(os,clique_caps);
    os<<"}\n";
    budget.check();
    out.certificate_json=os.str();
    out.verified=true;out.reason="hall3_hybrid_source_clause_capacity";
    out.groups=std::count_if(weights.begin(),weights.end(),[](int64_t w){return w>0;});
    out.machines=int(g.machines.size()+cliques.size());
    out.demand=demand;out.capacity=upper;
    return true;
}
} // namespace hall3_detail

inline Result analyze_clause_hall3(const std::vector<std::vector<int>>& clauses,int nvars,
                                   const std::string& sha,const Options& opts) {
    using namespace hall3_detail;
    const auto started=Clock::now();
    Result result;result.reason="hall3_no_hybrid_capacity_deficit";
    if(!std::isfinite(opts.seconds)||opts.seconds<=0||opts.seconds>86400||nvars<=0||sha.size()!=64) {
        result.reason="hall3_invalid_input_or_budget";
        return result;
    }
    try {
        detail::Budget limit(opts.seconds);
        const auto g=detail::extract(clauses,nvars,limit);
        std::vector<char> bdd_owned(g.nv+1,0);
        for(const auto& m:g.machines)for(int v:m.order) {
            detail::need(!bdd_owned.at(v),"hall3_duplicate_bdd_selector");
            bdd_owned[v]=1;
        }
        const auto cliques=make_cliques(g,bdd_owned,limit);
        std::vector<char> covered(g.nv+1,0);
        for(const auto& m:g.machines)for(int v:m.order)covered[v]=1;
        for(const auto& clique:cliques)for(size_t i=0;i<clique.size();++i) {
            const int v=clique[i];
            detail::need(!covered[v] && g.membership[v]>=0,"hall3_duplicate_or_nonselector");
            covered[v]=1;
            for(size_t k=0;k<i;++k)
                detail::need(detail::has(g.clauses,{-v,-clique[k]}),"hall3_unverified_clique");
        }
        for(const auto& group:g.groups)for(int v:group)
            detail::need(covered[v],"hall3_uncovered_group_option");
        result.groups=g.groups.size();result.machines=g.machines.size()+cliques.size();
        std::vector<int64_t> w(g.groups.size(),1);
        if(candidate(g,sha,cliques,w,limit,result))return result;
        std::fill(w.begin(),w.end(),0);
        for(int id:g.group_order) {
            w[id]=1;
            if(candidate(g,sha,cliques,w,limit,result))return result;
        }
        std::fill(w.begin(),w.end(),0);
        for(auto it=g.group_order.rbegin();it!=g.group_order.rend();++it) {
            w[*it]=1;
            if(candidate(g,sha,cliques,w,limit,result))return result;
        }
        result.reason="hall3_no_hybrid_capacity_deficit";
    } catch(const detail::Stop& e) {
        result.reason=std::string("hall3_")+e.what();
    } catch(const std::bad_alloc&) {
        result.reason="hall3_allocation_gate";
    } catch(const std::exception&) {
        result.reason="hall3_exception";
    }
    result.elapsed=std::chrono::duration<double>(Clock::now()-started).count();
    return result;
}

// Sequential, single-process gate: HALL3 hybrid -> existing weighted BDD ->
// source-clause HALL1 -> HALL2. Never exceeds the shared discovery budget.
inline Result analyze_clause_hall3_combined(const std::vector<std::vector<int>>& clauses,int nvars,
                                            const std::string& sha,const Options& options) {
    using GateClock=std::chrono::steady_clock;
    const auto started=GateClock::now();
    if(!std::isfinite(options.seconds) || options.seconds<=0) {
        Result bad;bad.reason="hall3_invalid_budget";return bad;
    }
    auto remaining=[&](){
        return options.seconds-std::chrono::duration<double>(GateClock::now()-started).count();
    };
    Result output;
    output.reason="hall3_no_supported_certificate";
    auto attempt=[&](auto operation,double cap){
        double allowance=std::min(remaining(),cap);
        if(allowance<=0.001)return false;
        Options cfg;cfg.seconds=allowance;
        Result trial=operation(clauses,nvars,sha,cfg);
        if(trial.verified){output=std::move(trial);return true;}
        output.reason=trial.reason;
        return false;
    };
    const double hybrid_budget=std::min(options.seconds, std::max(0.06,options.seconds*0.15));
    if(attempt(analyze_clause_hall3,hybrid_budget))goto done;
    if(attempt(analyze,std::max(0.01,options.seconds*0.70)))goto done;
    if(attempt(analyze_clause_hall,std::max(0.01,options.seconds*0.15)))goto done;
    attempt(analyze_clause_hall2,remaining());
  done:
    output.elapsed=std::chrono::duration<double>(GateClock::now()-started).count();
    return output;
}
} // namespace pcmax
