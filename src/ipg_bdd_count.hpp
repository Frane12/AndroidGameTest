#pragma once
// DRNAS IPG-BDD2: bounded, single-process, SOURCE-CLAUSE-DERIVED native C++
// count-profile UNSAT guard. Not a generic polynomial PCMAX algorithm.
//
// The existing native pcmax::detail::extract validates one-hot groups,
// asserted roots/terminals, implication clauses and reduced BDD node ordering.
// This module (a) builds a two-count-class exact SUPerset of accepting BDD
// paths (skipped variables may be true or false), (b) convolves all machine
// profiles, (c) claims UNSAT ONLY if a source-demand count is unreachable.
//
// Every UNSAT claim requires a source-bound STRUCTURAL certificate accepted by
// the independent research/ipg_bdd_checker.py checker, NOT DRAT/LRAT/VeriPB.
// This file is only compiled into opt-in experiment targets. No subprocess,
// Python runtime, second SAT solver or parallel portfolio is used.
#include "pcmax_capacity.hpp"
#include <openssl/evp.h>
#include <algorithm>
#include <array>
#include <chrono>
#include <cstdint>
#include <limits>
#include <map>
#include <numeric>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

namespace drnas_ipgbdd2 {
using Clock=std::chrono::steady_clock;
using Pair=std::array<int,2>;
using Profile=std::vector<unsigned char>;
constexpr uint64_t kOpsMax=10000000;
constexpr int kStateMax=1200;
constexpr int kGroupMax=56;
constexpr int kMachineMax=48;

struct Result {
    bool verified=false; // SOURCE-BOUND INTERNAL candidate; external check REQUIRED
    std::string reason="unknown";
    std::string graph_json, certificate_json;
    int groups=0,machines=0, source_transitions=0;
    int chosen_a=0,chosen_b=0,attempted=0;
    uint64_t machine_ops=0, global_ops=0;
    double seconds=0.0;
};

inline std::string sha256(const std::string& source) {
    unsigned char digest[EVP_MAX_MD_SIZE];
    unsigned int n=0;
    if (EVP_Digest(source.data(),source.size(),digest,&n,EVP_sha256(),nullptr)!=1 || n!=32)
        throw std::runtime_error("IPG_BDD_sha256_failed");
    constexpr char hex[]="0123456789abcdef";
    std::string output;
    output.reserve(64);
    for (unsigned i=0;i<n;++i) {
        output.push_back(hex[digest[i]>>4]);
        output.push_back(hex[digest[i]&15]);
    }
    return output;
}
template<typename T> inline void json_array(std::ostream& out, const std::vector<T>& v) {
    out<<'[';
    for(size_t i=0;i<v.size();++i) {
        if(i)out<<',';
        out<<v[i];
    }
    out<<']';
}
inline void json_pairs(std::ostream& out, const std::vector<Pair>& v) {
    out<<'[';
    for(size_t i=0;i<v.size();++i) {
        if(i)out<<',';
        out<<'['<<v[i][0]<<','<<v[i][1]<<']';
    }
    out<<']';
}
inline std::vector<int> source_order(const pcmax::detail::Graph& g,
                                     const std::vector<int>& lookup) {
    std::vector<int> order;
    for(int j:g.group_order)if(lookup[static_cast<size_t>(j)]>=0)
        order.push_back(lookup[static_cast<size_t>(j)]);
    return order;
}
inline std::string graph_canonical(const pcmax::detail::Graph& g,
                                    const std::string& source_sha,int nclauses,
                                    const std::vector<int>& eligible,
                                    const std::vector<int>& ordered) {
    // UTF-8 ASCII, sorted object keys, no whitespace. SHA256 of this text
    // equals Python json.dumps(graph, sort_keys=True, separators=(',',':')).
    std::ostringstream out;
    out<<"{\"eligible_group_order\":";
    json_array(out,ordered);
    out<<",\"eligible_groups\":[";
    for(size_t i=0;i<eligible.size();++i) {
        if(i)out<<',';
        json_array(out,g.groups[static_cast<size_t>(eligible[i])]);
    }
    out<<"],\"format\":\"IPG-BDD1-SOURCE-GRAPH-V1\",\"machine_graphs\":[";
    for(size_t i=0;i<g.machines.size();++i) {
        const auto& m=g.machines[i];
        if(i)out<<',';
        out<<"{\"false_terminal\":"<<m.no<<",\"root\":"<<m.root
           <<",\"transitions\":[";
        for(size_t j=0;j<m.nodes.size();++j) {
            if(j)out<<',';
            int p=m.nodes[j];
            const auto& nd=g.nodes[static_cast<size_t>(p)];
            out<<'['<<p<<','<<nd.x<<','<<nd.left<<','<<nd.right<<']';
        }
        out<<"],\"true_terminal\":"<<m.yes<<",\"variable_order\":";
        json_array(out,m.order);
        out<<'}';
    }
    out<<"],\"source_clauses\":"<<nclauses
       <<",\"source_sha256\":\""<<source_sha<<"\",\"source_variables\":"<<g.nv<<'}';
    return out.str();
}

struct Gate {
    int limit_a=0,limit_b=0,width=0;
    uint64_t operations=0;
    Clock::time_point deadline;
    explicit Gate(int a,int b,Clock::time_point stop)
        :limit_a(a),limit_b(b),width(b+1),deadline(stop) {}
    void check() const {
        if(Clock::now()>deadline)
            throw std::runtime_error("time_budget");
        if(operations>kOpsMax)
            throw std::runtime_error("operations_gate");
    }
    size_t index(int a,int b) const {
        return static_cast<size_t>(a*width+b);
    }
    Profile blank() const {
        return Profile(static_cast<size_t>((limit_a+1)*width),0);
    }
    Profile unit() const {
        auto s=blank();s[0]=1;return s;
    }
    int count(const Profile& p) const {
        return static_cast<int>(std::count(p.begin(),p.end(),static_cast<unsigned char>(1)));
    }
    void optional_in_place(Profile& p,int type) {
        if(type==1) {
            for(int a=limit_a-1;a>=0;--a)for(int b=0;b<=limit_b;++b)
                if(p[index(a,b)])p[index(a+1,b)]=1;
        }else if(type==2) {
            for(int a=0;a<=limit_a;++a)for(int b=limit_b-1;b>=0;--b)
                if(p[index(a,b)])p[index(a,b+1)]=1;
        }
    }
    void mandatory_in_place(Profile& p,int type) {
        if(type==0)return;
        auto q=blank();
        for(int a=0;a<=limit_a;++a)for(int b=0;b<=limit_b;++b)if(p[index(a,b)]) {
            if(type==1 && a<limit_a)q[index(a+1,b)]=1;
            else if(type==2 && b<limit_b)q[index(a,b+1)]=1;
        }
        p.swap(q);
    }
    std::vector<Pair> pairs(const Profile& p) const {
        std::vector<Pair> out;
        for(int a=0;a<=limit_a;++a)for(int b=0;b<=limit_b;++b)
            if(p[index(a,b)])out.push_back({a,b});
        return out;
    }
};

inline std::vector<Pair> machine_profile(const pcmax::detail::Graph& g,
                            const pcmax::detail::Machine& m,
                            const std::vector<int>& type,Gate& gate) {
    std::unordered_map<int,Profile> state;
    // Each profile is an exact set of count pairs along paths consistent
    // with source BDD implications, while any SKIPPED source selector is free.
    // This is a relaxation of all original clauses (safe for UNSAT).
    Profile initial=gate.unit();
    for(int i=0;i<g.level[static_cast<size_t>(m.root)];++i)
        gate.optional_in_place(initial,type[static_cast<size_t>(m.order[static_cast<size_t>(i)])]);
    state.emplace(m.root,std::move(initial));
    size_t visits=0;
    for(auto it=m.nodes.rbegin();it!=m.nodes.rend();++it) {
        if((++visits&63)==0)gate.check();
        const int parent=*it;
        auto found=state.find(parent);
        if(found==state.end())continue;
        // Preserve the source profile across unordered_map insertions:
        // insertion may rehash and invalidate all iterators.
        const Profile parent_profile=found->second;
        const auto& node=g.nodes[static_cast<size_t>(parent)];
        const int at=g.level[static_cast<size_t>(parent)];
        for(int branch=0;branch<2;++branch) {
            int child=branch?node.right:node.left;
            if(child==m.no)continue;
            Profile current=parent_profile;
            if(branch)gate.mandatory_in_place(current,type[static_cast<size_t>(node.x)]);
            for(int i=at+1;i<g.level[static_cast<size_t>(child)];++i)
                gate.optional_in_place(current,type[static_cast<size_t>(m.order[static_cast<size_t>(i)])]);
            gate.operations+=static_cast<uint64_t>(gate.count(parent_profile)) *
                             static_cast<uint64_t>(1+g.level[static_cast<size_t>(child)]-at);
            gate.check();
            auto [slot,newone]=state.try_emplace(child,gate.blank());
            auto& target=slot->second;
            for(size_t k=0;k<target.size();++k)
                target[k]=static_cast<unsigned char>(target[k]||current[k]);
            if(gate.count(target)>kStateMax)
                throw std::runtime_error("state_limit");
        }
        state.erase(parent);
    }
    auto end=state.find(m.yes);
    if(end==state.end())return {};
    return gate.pairs(end->second);
}
inline std::pair<bool,std::vector<int>> global_profile(const std::vector<std::vector<Pair>>& all,
                                  Gate& gate,uint64_t& operations) {
    Profile dp=gate.unit();
    std::vector<int> row_sizes{1};
    for(const auto& patterns:all) {
        gate.check();
        Profile next=gate.blank();
        for(int a=0;a<=gate.limit_a;++a)for(int b=0;b<=gate.limit_b;++b)
            if(dp[gate.index(a,b)])for(const auto& p:patterns) {
                ++operations;
                if(a+p[0]<=gate.limit_a&&b+p[1]<=gate.limit_b)
                    next[gate.index(a+p[0],b+p[1])]=1;
                if(operations>kOpsMax)throw std::runtime_error("global_operation_gate");
            }
        dp.swap(next);
        row_sizes.push_back(gate.count(dp));
    }
    return {dp[gate.index(gate.limit_a,gate.limit_b)]==0,std::move(row_sizes)};
}
inline std::pair<std::vector<std::vector<Pair>>,std::vector<int>> compute(
    const pcmax::detail::Graph& g,
    const std::vector<int>& eligible,
    const std::vector<int>& a,const std::vector<int>& b,
    Gate& gate,uint64_t& global_ops) {
    std::vector<int> type(static_cast<size_t>(g.nv+1),0);
    for(int j:a)
        for(int x:g.groups[static_cast<size_t>(eligible[static_cast<size_t>(j)])])
            type[static_cast<size_t>(x)]=1;
    for(int j:b)
        for(int x:g.groups[static_cast<size_t>(eligible[static_cast<size_t>(j)])])
            type[static_cast<size_t>(x)]=2;
    std::vector<std::vector<Pair>> all;
    all.reserve(g.machines.size());
    for(const auto& m:g.machines)
        all.push_back(machine_profile(g,m,type,gate));
    auto [unsat,rows]=global_profile(all,gate,global_ops);
    if(!unsat)return {{},{}};
    return {std::move(all),std::move(rows)};
}
inline std::vector<std::pair<std::vector<int>,std::vector<int>>>
proposals(const pcmax::detail::Graph& g,const std::vector<int>& eligible,
          const std::vector<int>& topo) {
    const int n=static_cast<int>(eligible.size());
    std::vector<int> sequence(static_cast<size_t>(n));
    std::iota(sequence.begin(),sequence.end(),0);
    std::vector<int> use_count(static_cast<size_t>(n),0);
    std::vector<int> group_to_local(g.groups.size(),-1);
    for(int j=0;j<n;++j)
        group_to_local[static_cast<size_t>(eligible[static_cast<size_t>(j)])]=j;
    for(const auto& m:g.machines)for(int p:m.nodes) {
        int x=g.nodes[static_cast<size_t>(p)].x;
        int group=g.membership[static_cast<size_t>(x)];
        int local=group_to_local[static_cast<size_t>(group)];
        if(local>=0)++use_count[static_cast<size_t>(local)];
    }
    auto priority=sequence;
    std::sort(priority.begin(),priority.end(),[&](int x,int y) {
        return use_count[static_cast<size_t>(x)]!=use_count[static_cast<size_t>(y)]?
            use_count[static_cast<size_t>(x)]>use_count[static_cast<size_t>(y)]:x<y;
    });
    std::vector<std::pair<std::vector<int>,std::vector<int>>> out;
    std::set<std::pair<std::vector<int>,std::vector<int>>> seen;
    auto push=[&](std::vector<int> a,std::vector<int> b) {
        if(a.empty())return;
        std::sort(a.begin(),a.end());std::sort(b.begin(),b.end());
        if(seen.insert({a,b}).second)out.emplace_back(std::move(a),std::move(b));
    };
    push(sequence,{});
    const int half=n/2;
    push({sequence.begin(),sequence.begin()+half},{sequence.begin()+half,sequence.end()});
    std::vector<int> odd,even;
    for(int j=0;j<n;++j)(j%2?odd:even).push_back(j);
    push(even,odd);
    push({priority.begin(),priority.begin()+half},
         {priority.begin()+half,priority.end()});
    for(const auto& order:{topo,priority}) {
        for(int k=3;k<=n;++k) {
            std::vector<int> prefix(order.begin(),order.begin()+k);
            push(prefix,{});
            if(k>=6)push({prefix.begin(),prefix.begin()+k/2},
                         {prefix.begin()+k/2,prefix.end()});
        }
        for(int k=3;k<n;++k)push({order.end()-k,order.end()},{});
    }
    return out;
}
inline std::string certificate_json(const pcmax::detail::Graph& g,
            const std::string& sha,const std::string& graphhash,
            int source_clauses,const std::vector<int>& eligible,
            const std::vector<int>& a,const std::vector<int>& b,
            const std::vector<std::vector<Pair>>& profiles,
            const std::vector<int>& rows,uint64_t machine_ops,uint64_t global_ops) {
    std::ostringstream out;
    out<<"{\"format\":\"DRNAS-IPG-BDD1-COUNT-CERT-V1\","
       <<"\"source_sha256\":\""<<sha<<"\","
       <<"\"graph_sha256\":\""<<graphhash<<"\","
       <<"\"source_variables\":"<<g.nv<<","
       <<"\"source_clauses\":"<<source_clauses<<","
       <<"\"status\":\"UNSAT_SOURCE_BDD_COUNT_UNCHECKED\","
       <<"\"reason\":\"global_two_class_count_profile_gap\","
       <<"\"machine_count\":"<<g.machines.size()<<","
       <<"\"eligible_jobs\":"<<eligible.size()<<","
       <<"\"classes\":[";
    json_array(out,a);out<<',';json_array(out,b);
    out<<"],\"per_machine_profiles\":[";
    for(size_t i=0;i<profiles.size();++i) {
        if(i)out<<',';
        json_pairs(out,profiles[i]);
    }
    out<<"],\"global_reachable_sizes\":";
    json_array(out,rows);
    out<<",\"machine_transition_ops\":"<<machine_ops
       <<",\"global_count_ops\":"<<global_ops<<"}\n";
    return out.str();
}
inline Result analyze(const std::vector<std::vector<int>>& clauses,int nvars,
                      const std::string& digest,double budget_seconds) {
    Result r;
    const auto started=Clock::now();
    try{
        if(budget_seconds<=0.0 || budget_seconds>86400.0)
            throw std::runtime_error("budget_zero_or_invalid");
        const auto deadline=started+std::chrono::duration_cast<Clock::duration>(
                                std::chrono::duration<double>(budget_seconds));
        pcmax::detail::Budget source_budget(budget_seconds);
        auto g=pcmax::detail::extract(clauses,nvars,source_budget);
        r.machines=static_cast<int>(g.machines.size());
        if(r.machines<1 || r.machines>kMachineMax)
            throw std::runtime_error("machine_count_gate");
        std::vector<int> eligible;
        std::vector<int> index(g.groups.size(),-1);
        for(size_t j=0;j<g.groups.size();++j)
            if(g.eligible[j]) {
                index[j]=static_cast<int>(eligible.size());
                eligible.push_back(static_cast<int>(j));
            }
        r.groups=static_cast<int>(eligible.size());
        if(r.groups<3 || r.groups>kGroupMax)
            throw std::runtime_error("group_count_gate");
        auto topo=source_order(g,index);
        const auto graph=graph_canonical(g,digest,
                     static_cast<int>(clauses.size()),eligible,topo);
        const auto graphhash=sha256(graph);
        for(const auto& m:g.machines)r.source_transitions+=static_cast<int>(m.nodes.size());
        for(const auto& [a,b]:proposals(g,eligible,topo)) {
            ++r.attempted;
            Gate gate(static_cast<int>(a.size()),static_cast<int>(b.size()),deadline);
            uint64_t globalops=0;
            auto [profiles,rows]=compute(g,eligible,a,b,gate,globalops);
            if(!rows.empty()) {
                r.verified=true;
                r.reason="source_BDD_count_UNSAT_candidate";
                r.chosen_a=static_cast<int>(a.size());
                r.chosen_b=static_cast<int>(b.size());
                r.machine_ops=gate.operations;
                r.global_ops=globalops;
                r.graph_json=graph+"\n";
                r.certificate_json=certificate_json(g,digest,graphhash,
                        static_cast<int>(clauses.size()),eligible,a,b,profiles,
                        rows,gate.operations,globalops);
                break;
            }
            if(Clock::now()>=deadline)
                throw std::runtime_error("time_budget");
        }
        if(!r.verified)r.reason="no_two_class_count_contradiction";
    }catch(const pcmax::detail::Stop& exc) {
        r.reason=exc.what();
    }catch(const std::exception& exc) {
        r.reason=exc.what();
    }catch(const std::bad_alloc&) {
        r.reason="allocation_gate";
    }
    if(!r.verified){r.graph_json.clear();r.certificate_json.clear();}
    r.seconds=std::chrono::duration<double>(Clock::now()-started).count();
    return r;
}
} // namespace drnas_ipgbdd2
