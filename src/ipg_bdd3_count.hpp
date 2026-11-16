#pragma once
// Experimental DRNAS IPG-BDD3: SOURCE-BOUND polynomial count profiles
// for three fixed job classes, all inside one native C++ SAT solver process.
// No claim of general PCMAX polytime: underlying BDD can be exponential.
// No SAT claim. UNSAT needs independent external ORIGINAL-CNF verifier.
// Compact source-bound JSON is NOT VeriPB, DRAT, or LRAT.
#include "ipg_bdd_count.hpp"
#include <array>
#include <chrono>
#include <cstdint>
#include <map>
#include <numeric>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>

namespace drnas_ipgbdd3 {
using Clock=std::chrono::steady_clock;
using Triple=std::array<int,3>;
using Profile=std::vector<unsigned char>;
constexpr uint64_t kOperations=24000000ULL;
constexpr int kStateLimit=4200;
constexpr int kGroups=56;
constexpr int kMachines=48;

struct Result {
    bool candidate=false; // not accepted without separate source verifier
    std::string reason="not_applicable";
    std::string graph_json, certificate_json;
    int groups=0,machines=0,source_transitions=0,attempted=0;
    std::array<int,3> class_sizes{0,0,0};
    uint64_t operations=0;
    double seconds=0.0;
};
struct Gate {
    Triple caps;
    int width_b=0,width_c=0;
    uint64_t ops=0;
    Clock::time_point deadline;
    Gate(const Triple& sizes,Clock::time_point stop)
      :caps(sizes),width_b(sizes[1]+1),width_c(sizes[2]+1),deadline(stop) {
        const size_t states=static_cast<size_t>(sizes[0]+1)*
                            static_cast<size_t>(sizes[1]+1)*
                            static_cast<size_t>(sizes[2]+1);
        if(states>kStateLimit)throw std::runtime_error("three_class_dense_state_gate");
    }
    size_t index(int a,int b,int c) const {
        return (static_cast<size_t>(a)*width_b+static_cast<size_t>(b))*width_c+
               static_cast<size_t>(c);
    }
    Profile blank() const {
        return Profile(static_cast<size_t>(caps[0]+1)*width_b*width_c,0);
    }
    Profile unit() const {
        Profile p=blank();p[0]=1;return p;
    }
    int count(const Profile& p) const {
        return static_cast<int>(std::count(p.begin(),p.end(),static_cast<unsigned char>(1)));
    }
    void check() const {
        if(Clock::now()>=deadline)throw std::runtime_error("time_gate");
        if(ops>kOperations)throw std::runtime_error("operation_gate");
    }
    void optional(Profile& p,int cls) {
        if(cls==0)return;
        // Descending in the chosen coordinate makes each skipped selector
        // independently free to be false or true, without selecting twice.
        if(cls==1) {
            for(int a=caps[0]-1;a>=0;--a)
                for(int b=0;b<=caps[1];++b)
                    for(int c=0;c<=caps[2];++c)
                        if(p[index(a,b,c)])p[index(a+1,b,c)]=1;
        } else if(cls==2) {
            for(int a=0;a<=caps[0];++a)
                for(int b=caps[1]-1;b>=0;--b)
                    for(int c=0;c<=caps[2];++c)
                        if(p[index(a,b,c)])p[index(a,b+1,c)]=1;
        } else if(cls==3) {
            for(int a=0;a<=caps[0];++a)
                for(int b=0;b<=caps[1];++b)
                    for(int c=caps[2]-1;c>=0;--c)
                        if(p[index(a,b,c)])p[index(a,b,c+1)]=1;
        }
    }
    void mandatory(Profile& p,int cls) {
        if(!cls)return;
        Profile next=blank();
        for(int a=0;a<=caps[0];++a)
            for(int b=0;b<=caps[1];++b)
                for(int c=0;c<=caps[2];++c)if(p[index(a,b,c)]) {
                    if(cls==1 && a<caps[0])next[index(a+1,b,c)]=1;
                    else if(cls==2 && b<caps[1])next[index(a,b+1,c)]=1;
                    else if(cls==3 && c<caps[2])next[index(a,b,c+1)]=1;
                }
        p.swap(next);
    }
    std::vector<Triple> entries(const Profile& p) const {
        std::vector<Triple> out;
        for(int a=0;a<=caps[0];++a)
            for(int b=0;b<=caps[1];++b)
                for(int c=0;c<=caps[2];++c)
                    if(p[index(a,b,c)])out.push_back({a,b,c});
        return out;
    }
};

inline std::vector<Triple> machine_profile(
        const pcmax::detail::Graph& g,const pcmax::detail::Machine& machine,
        const std::vector<int>& selector_class,Gate& gate) {
    std::map<int,Profile> paths;
    Profile prefix=gate.unit();
    for(int rank=0;rank<g.level[static_cast<size_t>(machine.root)];++rank)
        gate.optional(prefix,selector_class[static_cast<size_t>(
            machine.order[static_cast<size_t>(rank)])]);
    paths.emplace(machine.root,std::move(prefix));

    size_t step=0;
    for(auto it=machine.nodes.rbegin();it!=machine.nodes.rend();++it) {
        if((++step&63)==0)gate.check();
        const int parent=*it;
        auto node_path=paths.find(parent);
        if(node_path==paths.end())continue;
        const Profile previous=node_path->second;
        const auto& node=g.nodes[static_cast<size_t>(parent)];
        const int from=g.level[static_cast<size_t>(parent)];
        for(int pick=0;pick<2;++pick) {
            const int child=pick?node.right:node.left;
            if(child==machine.no)continue;
            Profile local=previous;
            if(pick)gate.mandatory(local,selector_class[static_cast<size_t>(node.x)]);
            const int to=g.level[static_cast<size_t>(child)];
            for(int rank=from+1;rank<to;++rank)
                gate.optional(local,selector_class[static_cast<size_t>(
                    machine.order[static_cast<size_t>(rank)])]);
            gate.ops+=static_cast<uint64_t>(gate.count(previous))*
                      static_cast<uint64_t>(1+to-from);
            gate.check();
            auto [dest,created]=paths.try_emplace(child,gate.blank());
            auto& target=dest->second;
            for(size_t k=0;k<target.size();++k)
                target[k]=static_cast<unsigned char>(target[k]||local[k]);
            if(gate.count(target)>kStateLimit)
                throw std::runtime_error("node_profile_state_gate");
        }
        paths.erase(parent);
    }
    auto found=paths.find(machine.yes);
    return found==paths.end()?std::vector<Triple>{}:gate.entries(found->second);
}
inline std::pair<bool,std::vector<int>>
combine(const std::vector<std::vector<Triple>>& per_machine, Gate& gate) {
    Profile current=gate.unit();
    std::vector<int> rows{1};
    for(const auto& allowed:per_machine) {
        gate.check();
        Profile next=gate.blank();
        for(int a=0;a<=gate.caps[0];++a)
            for(int b=0;b<=gate.caps[1];++b)
                for(int c=0;c<=gate.caps[2];++c)
                    if(current[gate.index(a,b,c)])
                        for(const Triple& d:allowed) {
                            ++gate.ops;
                            if(gate.ops>kOperations)
                                throw std::runtime_error("convolution_operation_gate");
                            if(a+d[0]<=gate.caps[0] &&
                               b+d[1]<=gate.caps[1] &&
                               c+d[2]<=gate.caps[2])
                                next[gate.index(a+d[0],b+d[1],c+d[2])]=1;
                        }
        current.swap(next);
        rows.push_back(gate.count(current));
    }
    return {current[gate.index(gate.caps[0],gate.caps[1],gate.caps[2])]==0,
            std::move(rows)};
}
struct Witness {
    std::array<std::vector<int>,3> classes;
    std::vector<int> row_sizes,profile_sizes;
};
inline std::vector<Witness> proposals(const pcmax::detail::Graph& g,
                   const std::vector<int>& eligible,
                   const std::vector<int>& source_order) {
    const int n=static_cast<int>(eligible.size());
    std::vector<Witness> out;
    std::set<std::array<std::vector<int>,3>> seen;
    auto push=[&](std::array<std::vector<int>,3> C) {
        for(auto& v:C)std::sort(v.begin(),v.end());
        const int total=static_cast<int>(C[0].size()+C[1].size()+C[2].size());
        if(total<3 || total>n || (C[0].empty()&&C[1].empty()) ||
           C[2].empty() || C[0].empty() || C[1].empty())return;
        if(seen.insert(C).second)out.push_back({C,{},{}});
    };
    std::vector<int> all(static_cast<size_t>(n));
    std::iota(all.begin(),all.end(),0);
    std::vector<int> priority=all;
    std::vector<int> local(g.groups.size(),-1);
    for(size_t j=0;j<eligible.size();++j)local[static_cast<size_t>(eligible[j])]=static_cast<int>(j);
    std::vector<int> freq(static_cast<size_t>(n),0);
    for(const auto& m:g.machines)for(int p:m.nodes) {
        const auto& node=g.nodes[static_cast<size_t>(p)];
        int orig=g.membership[static_cast<size_t>(node.x)];
        if(local[static_cast<size_t>(orig)]>=0)
            ++freq[static_cast<size_t>(local[static_cast<size_t>(orig)])];
    }
    std::sort(priority.begin(),priority.end(),[&](int a,int b) {
        return freq[static_cast<size_t>(a)]!=freq[static_cast<size_t>(b)]?
               freq[static_cast<size_t>(a)]>freq[static_cast<size_t>(b)]:a<b;
    });
    const std::vector<std::vector<int>> sequences={all,source_order,priority};
    for(const auto& ord:sequences) {
        for(int k=3;k<=n;++k) {
            std::vector<int> subset(ord.begin(),ord.begin()+k);
            // Equal consecutive partitions, and residue-class partition
            std::array<std::vector<int>,3> C;
            for(int j=0;j<k;++j)C[static_cast<size_t>(std::min(2,(3*j)/k))]
                .push_back(subset[static_cast<size_t>(j)]);
            push(C);
            C={};
            for(int j=0;j<k;++j)C[static_cast<size_t>(j%3)]
                .push_back(subset[static_cast<size_t>(j)]);
            push(C);
        }
    }
    return out;
}
inline std::string certificate_json(const pcmax::detail::Graph& g,
            const std::string& source_sha,const std::string& graph_hash,
            int source_clauses,const std::array<std::vector<int>,3>& classes,
            const std::vector<int>& machine_sizes,const std::vector<int>& global_rows) {
    // Short source-bound certificate: independent verifier recomputes every
    // machine BDD profile and every global DP state, rather than trusting
    // producer-supplied potentially huge profile tables.
    std::ostringstream out;
    out<<"{\"format\":\"DRNAS-IPG-BDD3-3COUNT-CERT-V1\","
       <<"\"source_sha256\":\""<<source_sha<<"\","
       <<"\"graph_sha256\":\""<<graph_hash<<"\","
       <<"\"source_variables\":"<<g.nv<<","
       <<"\"source_clauses\":"<<source_clauses<<","
       <<"\"status\":\"UNSAT_SOURCE_BDD3_COUNT_UNCHECKED\","
       <<"\"reason\":\"global_three_class_count_profile_gap\","
       <<"\"machine_count\":"<<g.machines.size()<<",\"classes\":[";
    for(int i=0;i<3;++i) {
        if(i)out<<',';
        drnas_ipgbdd2::json_array(out,classes[static_cast<size_t>(i)]);
    }
    out<<"],\"machine_profile_sizes\":";
    drnas_ipgbdd2::json_array(out,machine_sizes);
    out<<",\"global_reachable_sizes\":";
    drnas_ipgbdd2::json_array(out,global_rows);
    out<<"}\n";
    return out.str();
}
inline Result analyze(const std::vector<std::vector<int>>& clauses,int nvars,
             const std::string& source_sha,double budget_seconds) {
    Result result;
    const auto started=Clock::now();
    try{
        if(!(budget_seconds>0.0 && budget_seconds<=86400.0))
            throw std::runtime_error("invalid_budget");
        const auto deadline=started+std::chrono::duration_cast<Clock::duration>(
                                std::chrono::duration<double>(budget_seconds));
        pcmax::detail::Budget budget(budget_seconds);
        auto g=pcmax::detail::extract(clauses,nvars,budget);
        if(g.machines.size()>kMachines)
            throw std::runtime_error("machines_size_gate");
        std::vector<int> eligible,index(g.groups.size(),-1);
        for(size_t j=0;j<g.groups.size();++j)
            if(g.eligible[j]) {
                index[j]=static_cast<int>(eligible.size());
                eligible.push_back(static_cast<int>(j));
            }
        result.groups=static_cast<int>(eligible.size());
        result.machines=static_cast<int>(g.machines.size());
        if(result.groups<3||result.groups>kGroups)
            throw std::runtime_error("eligible_group_gate");
        auto order=drnas_ipgbdd2::source_order(g,index);
        if(order.size()!=eligible.size())
            throw std::runtime_error("source_order_incomplete");
        std::string canonical=drnas_ipgbdd2::graph_canonical(g,source_sha,
             static_cast<int>(clauses.size()),eligible,order);
        std::string graph_hash=drnas_ipgbdd2::sha256(canonical);
        for(const auto& m:g.machines)
            result.source_transitions+=static_cast<int>(m.nodes.size());
        const auto candidates=proposals(g,eligible,order);
        for(const auto& proposal:candidates) {
            ++result.attempted;
            const auto& C=proposal.classes;
            Triple bound{static_cast<int>(C[0].size()),
                         static_cast<int>(C[1].size()),
                         static_cast<int>(C[2].size())};
            Gate gate(bound,deadline);
            std::vector<int> cls(static_cast<size_t>(g.nv+1),0);
            for(int t=0;t<3;++t)
                for(int j:C[static_cast<size_t>(t)])
                    for(int sel:g.groups[static_cast<size_t>(
                            eligible[static_cast<size_t>(j)])])
                        cls[static_cast<size_t>(sel)]=t+1;
            std::vector<std::vector<Triple>> all;
            std::vector<int> sizes;
            for(const auto& m:g.machines) {
                auto P=machine_profile(g,m,cls,gate);
                sizes.push_back(static_cast<int>(P.size()));
                all.emplace_back(std::move(P));
            }
            auto [unreachable,rows]=combine(all,gate);
            if(!unreachable)continue;
            result.candidate=true;
            result.reason="source_BDD_three_class_gap";
            result.class_sizes=bound;
            result.operations=gate.ops;
            result.graph_json=canonical+"\n";
            result.certificate_json=certificate_json(g,source_sha,graph_hash,
                static_cast<int>(clauses.size()),C,sizes,rows);
            break;
        }
        if(!result.candidate)
            result.reason="no_three_class_gap";
    }catch(const pcmax::detail::Stop& error){
        result.reason=error.what();
    }catch(const std::bad_alloc&){
        result.reason="bad_alloc_gate";
    }catch(const std::exception& error){
        result.reason=error.what();
    }
    if(!result.candidate) {
        result.graph_json.clear();
        result.certificate_json.clear();
    }
    result.seconds=std::chrono::duration<double>(Clock::now()-started).count();
    return result;
}
} // namespace drnas_ipgbdd3
