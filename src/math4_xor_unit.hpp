#pragma once
// MATH4 -- strictly source-certified XOR algebra + root unit propagation.
// Discovery is bounded and optional; it never edits clauses, learned reasons,
// CDCL heuristics or solver state. Every UNSAT must carry a checkable original-
// CNF certificate. UNKNOWN falls through to unchanged HALL3 + CF7.
#include <algorithm>
#include <array>
#include <bit>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <functional>
#include <map>
#include <memory>
#include <numeric>
#include <sstream>
#include <string>
#include <tuple>
#include <utility>
#include <vector>

namespace pcmax {
namespace math4 {
using Clock=std::chrono::steady_clock;
struct Window {
    Clock::time_point until;
    explicit Window(double seconds)
      :until(Clock::now()+std::chrono::duration_cast<Clock::duration>(
          std::chrono::duration<double>(seconds))){}
    bool live() const {return Clock::now()<until;}
};
struct Equation {
    std::vector<int> vars;
    int forbidden_parity=0;
};
struct ElimRow {
    std::vector<uint64_t> mask;
    std::vector<uint64_t> trace;
    int rhs=0;
};
inline int high_bit(const std::vector<uint64_t>& x) {
    for(int w=int(x.size())-1;w>=0;--w) {
        if(x[size_t(w)])
            return w*64+63-int(std::countl_zero(x[size_t(w)]));
    }
    return -1;
}
inline bool has_bit(const std::vector<uint64_t>& x,size_t i){
    return (x[i>>6]>>(i&63))&uint64_t(1);
}
inline std::string emit_certificate(const std::string& digest,
                                    const std::vector<Equation>& xor_rows,
                                    const std::vector<int>& assigned_units,
                                    const std::vector<uint64_t>& trace,
                                    int& selected_xor,int& selected_units){
    std::ostringstream os;
    os<<"{\"format\":\"drnas-math4-xor-unit-v1\",\"source_sha256\":\""
      <<digest<<"\",\"xor_rows\":[";
    bool first=true;
    selected_xor=selected_units=0;
    for(size_t i=0;i<xor_rows.size();++i) {
        if(!has_bit(trace,i))continue;
        if(!first)os<<',';
        first=false;
        os<<"{\"vars\":[";
        for(size_t j=0;j<xor_rows[i].vars.size();++j){
            if(j)os<<',';
            os<<xor_rows[i].vars[j];
        }
        os<<"],\"forbidden_parity\":"<<xor_rows[i].forbidden_parity<<'}';
        ++selected_xor;
    }
    os<<"],\"root_units\":[";
    first=true;
    for(size_t i=0;i<assigned_units.size();++i) {
        if(!has_bit(trace,xor_rows.size()+i))continue;
        if(!first)os<<',';
        first=false;
        os<<assigned_units[i];
        ++selected_units;
    }
    os<<"]}";
    return os.str();
}
inline Result xor_unit(const std::vector<std::vector<int>>& clauses,
                       int nvars,const std::string& digest,double budget_s){
    Result out;
    out.reason="math4_no_eligible_xor_proof";
    const auto start=Clock::now();
    auto finish=[&](){
        out.elapsed=std::chrono::duration<double>(Clock::now()-start).count();
        return out;
    };
    if(!std::isfinite(budget_s)||budget_s<=0 || nvars<=0||nvars>6000 ||
       clauses.size()>100000||digest.size()!=64){
        out.reason="math4_size_or_budget_gate";return finish();
    }
    Window deadline(budget_s);
    using ParitySets=std::array<uint64_t,2>;
    std::map<std::vector<int>,ParitySets> patterns;
    // Only a complete parity half-cube of ORIGINAL clauses is an equation.
    size_t literals_seen=0;
    for(size_t ci=0;ci<clauses.size();++ci){
        if((ci&511)==0&&!deadline.live()){
            out.reason="math4_xor_scan_budget";return finish();
        }
        const auto& c=clauses[ci];
        literals_seen+=c.size();
        if(literals_seen>1500000){out.reason="math4_literal_limit";return finish();}
        const size_t w=c.size();
        if(w<2||w>6)continue;
        std::vector<int> support;
        support.reserve(w);
        for(int lit:c) {
            if(!lit||std::abs(lit)>nvars) {
                out.reason="math4_bad_literal";return finish();
            }
            support.push_back(std::abs(lit));
        }
        std::sort(support.begin(),support.end());
        if(std::adjacent_find(support.begin(),support.end())!=support.end())
            continue;
        unsigned mask=0;
        for(int lit:c)if(lit<0){
            const auto it=std::lower_bound(support.begin(),support.end(),-lit);
            mask|=1u<<unsigned(it-support.begin());
        }
        if(patterns.size()>=50000 && patterns.find(support)==patterns.end()){
            out.reason="math4_support_limit";return finish();
        }
        patterns[support][std::popcount(mask)&1u]|=uint64_t(1)<<mask;
    }
    std::vector<Equation> equations;
    for(const auto& item:patterns){
        const auto& support=item.first;
        const auto& halves=item.second;
        for(int p=0;p<2;++p){
            const int pop=std::popcount(halves[size_t(p)]);
            if(pop==(1<<(support.size()-1)))
                equations.push_back(Equation{support,p});
        }
        if(!deadline.live()){out.reason="math4_xor_gather_budget";return finish();}
    }
    if(equations.size()<2){
        out.reason="math4_no_complete_source_xor_rows";return finish();
    }
    if(equations.size()>4096){
        out.reason="math4_xor_rows_limit";return finish();
    }
    // Derive every unit by untrusted discovery; the INDEPENDENT checker
    // recomputes the full propagation closure and checks each claimed unit.
    std::vector<int8_t> forced(size_t(nvars)+1,-1);
    bool closed=false;
    for(int pass=0;pass<=nvars && deadline.live();++pass){
        bool any=false;
        for(size_t ci=0;ci<clauses.size();++ci){
            if((ci&511)==0&&!deadline.live()){
                out.reason="math4_unit_budget";return finish();
            }
            const auto& c=clauses[ci];
            bool satisfied=false;
            int pending=0,remaining=0;
            for(int lit:c){
                int v=std::abs(lit);
                int8_t val=forced[size_t(v)];
                if(val<0){++pending;remaining=lit;}
                else if((val==1)==(lit>0)){satisfied=true;break;}
            }
            if(satisfied)continue;
            if(pending==0){
                // Could have a simpler UP contradiction, but this certificate
                // format is specifically GF2+UP. Fail closed to CDCL.
                out.reason="math4_root_up_conflict_no_certificate";return finish();
            }
            if(pending==1){
                const size_t v=size_t(std::abs(remaining));
                const int8_t value=remaining>0?1:0;
                if(forced[v]>=0 && forced[v]!=value){
                    out.reason="math4_root_up_inconsistent";return finish();
                }
                if(forced[v]<0){forced[v]=value;any=true;}
            }
        }
        if(!any){closed=true;break;}
    }
    if(!closed){out.reason="math4_root_up_budget";return finish();}
    std::vector<int> units;
    for(int i=1;i<=nvars;++i)if(forced[size_t(i)]>=0)
        units.push_back(forced[size_t(i)]==1?i:-i);
    const size_t total=equations.size()+units.size();
    const size_t width=(size_t(nvars)+63)/64, provenance_width=(total+63)/64;
    std::vector<std::unique_ptr<ElimRow>> basis(size_t(nvars));
    for(size_t ri=0;ri<total;++ri){
        if((ri&15)==0&&!deadline.live()){
            out.reason="math4_elimination_budget";return finish();
        }
        std::vector<uint64_t> mask(width,0),trace(provenance_width,0);
        int rhs=0;
        if(ri<equations.size()){
            const auto& eq=equations[ri];
            for(int v:eq.vars){
                const size_t j=size_t(v-1);
                mask[j>>6]^=uint64_t(1)<<(j&63);
            }
            rhs=1-eq.forbidden_parity;
        }else{
            int lit=units[ri-equations.size()];
            const size_t j=size_t(std::abs(lit)-1);
            mask[j>>6]^=uint64_t(1)<<(j&63);
            rhs=lit>0?1:0;
        }
        trace[ri>>6]=uint64_t(1)<<(ri&63);
        while(true){
            if(!deadline.live()){
                out.reason="math4_elimination_budget";return finish();
            }
            int pivot=high_bit(mask);
            if(pivot<0){
                if(rhs==1){
                    int nx=0,nu=0;
                    std::string certificate=emit_certificate(
                        digest,equations,units,trace,nx,nu);
                    if(nx<=0){
                        out.reason="math4_empty_xor_trace_rejected";return finish();
                    }
                    out.verified=true;
                    out.reason="math4_xor_plus_root_up_verified";
                    out.certificate_json=std::move(certificate);
                    out.groups=nx;
                    out.machines=nu;
                    out.demand=nx;
                    out.capacity=nu;
                    return finish();
                }
                break;
            }
            auto& b=basis[size_t(pivot)];
            if(!b){
                b=std::make_unique<ElimRow>();
                b->mask=std::move(mask);
                b->trace=std::move(trace);
                b->rhs=rhs;
                break;
            }
            for(size_t j=0;j<width;++j)mask[j]^=b->mask[j];
            for(size_t j=0;j<provenance_width;++j)trace[j]^=b->trace[j];
            rhs^=b->rhs;
        }
    }
    out.reason="math4_xor_up_consistent";
    return finish();
}
} // namespace math4

// Run only the cheapest, strongest algebra candidate first. If no checked
// proof is proposed, spend the remaining time with existing HALL3/BDD.
// The unchanged CF7 CDCL starts after that. One process, one CPU, one proof.
inline Result analyze_math4(const std::vector<std::vector<int>>& clauses,
                            int nvars,const std::string& digest,
                            const Options& budget){
    const auto start=math4::Clock::now();
    auto elapsed=[&](){return std::chrono::duration<double>(
        math4::Clock::now()-start).count();};
    if(!std::isfinite(budget.seconds)||budget.seconds<=0){
        Result r;r.reason="math4_invalid_budget";return r;
    }
    const double algebra_s=std::min(budget.seconds*0.35,0.23);
    Result x=math4::xor_unit(clauses,nvars,digest,algebra_s);
    if(x.verified){x.elapsed=elapsed();return x;}
    Options remaining=budget;
    remaining.seconds=std::max(0.0,budget.seconds-elapsed());
    if(remaining.seconds<=0){x.reason="math4_budget_no_hall3";x.elapsed=elapsed();return x;}
    Result h=analyze_hall3(clauses,nvars,digest,remaining);
    h.reason="math4_fallback_"+h.reason;
    h.elapsed=elapsed();
    return h;
}
} // namespace pcmax
