// DRNAS SAT TRAIL1: reconstruct SAT witnesses from the exact residual
// original CNF under the current CDCL trail. Each candidate is verified
// against EVERY immutable source clause; hints are not implications.
// This header does not access or modify watched clauses or CDCL state.
#pragma once
#include "drnas_sat_local.hpp"
#include <algorithm>
#include <chrono>
#include <cstdint>
#include <string>
#include <vector>

namespace sattrail {
using CNF=satconstruct::CNF;
using Clock=satconstruct::Clock;

struct Outcome {
    std::vector<int8_t> full_model;
    std::vector<int8_t> hints; // nonzero signs are advisory only
    std::string method="UNKNOWN";
    int residual_clauses=0;
    int residual_variables=0;
    int components=0;
    int solved_components=0;
    int xor_patterns=0;
    int hints_count=0;
    bool sat()const{return !full_model.empty();}
};
inline double remaining_ms(Clock::time_point end) {
    return std::chrono::duration<double,std::milli>(end-Clock::now()).count();
}
inline Outcome analyze(int n,const CNF& original,
                       const std::vector<int8_t>& values,double budget_ms) {
    Outcome out;
    if(n<=0||n>2048||original.size()>12000||
       values.size()!=static_cast<size_t>(n)||budget_ms<=0.0)
        return out;
    for(int8_t x:values)if(x!=-1&&x!=0&&x!=1)return out;
    const auto end=Clock::now()+std::chrono::duration_cast<Clock::duration>(
       std::chrono::duration<double,std::milli>(budget_ms));
    CNF reduced;
    reduced.reserve(original.size());
    std::vector<int> map(static_cast<size_t>(n),0);
    int64_t literals=0;
    for(size_t ci=0;ci<original.size();++ci){
        if((ci&127U)==0U && remaining_ms(end)<=0.05)return out;
        const auto& c=original[ci];
        bool satisfied=false;
        std::vector<int> row;
        row.reserve(c.size());
        for(int lit:c){
            if(lit==0||std::abs(static_cast<int64_t>(lit))>n)return out;
            if(++literals>75000)return out;
            const int v=std::abs(lit)-1;
            if(values[v]==(lit>0?1:-1)){satisfied=true;break;}
            if(values[v]==0)row.push_back(lit);
        }
        if(satisfied)continue;
        if(row.empty())return out; // Trail conflict: ordinary CDCL owns it.
        reduced.push_back(std::move(row));
    }
    out.residual_clauses=static_cast<int>(reduced.size());
    // All original clauses have already been satisfied by the current trail.
    // A completed assignment is nevertheless checked against the original.
    if(reduced.empty()){
        std::vector<int8_t> model=values;
        for(auto& x:model)if(!x)x=-1;
        if(satconstruct::verify(n,original,model)){
            out.full_model=std::move(model);
            out.method="TRAIL_SATISFIED";
        }
        return out;
    }
    for(const auto& c:reduced)
        for(int lit:c)map[std::abs(lit)-1]=1;
    int count=0;
    for(int& x:map)if(x)x=++count;
    out.residual_variables=count;
    if(count==0 || remaining_ms(end)<=0.1)return out;
    CNF compact;
    compact.reserve(reduced.size());
    for(const auto& c:reduced){
        std::vector<int> row;
        row.reserve(c.size());
        for(int lit:c){
            const int v=map[std::abs(lit)-1];
            row.push_back(lit>0?v:-v);
        }
        compact.push_back(std::move(row));
    }
    auto combine=[&](const std::vector<int8_t>& local,const char* method)->bool {
        if(local.size()!=static_cast<size_t>(count))return false;
        std::vector<int8_t> model=values;
        for(int v=0;v<n;++v){
            if(map[v]>0){
                if(model[v]!=0)return false;
                model[v]=local[map[v]-1];
            }else if(model[v]==0)model[v]=-1;
        }
        if(!satconstruct::verify(n,original,model))return false;
        out.full_model=std::move(model);
        out.method=method;
        return true;
    };
    // First try cheap exact special classes on the FULL residual.
    if(remaining_ms(end)>0.2){
        satconstruct::Limits limit;
        limit.max_ms=std::min(remaining_ms(end),1.2);
        const auto direct=satconstruct::analyze(count,compact,limit);
        if(direct.sat() && combine(direct.model,"TRAIL_DIRECT"))return out;
    }
    // A connected original may split into independent structural residual
    // components under trail assignments. Reconstruct those components and
    // gather optional XOR-subset phase hints with a strict tiny time cap.
    if(remaining_ms(end)>0.2){
        satlocal::Outcome local=satlocal::analyze(count,compact,
                                                  remaining_ms(end));
        out.components=local.source_components;
        out.solved_components=local.solved_components;
        out.xor_patterns=local.xor_patterns;
        if(local.full() && combine(local.full_model,"TRAIL_COMPONENTS"))return out;
        if(local.hints.size()==static_cast<size_t>(count)){
            out.hints.assign(static_cast<size_t>(n),0);
            for(int v=0;v<n;++v)if(map[v]>0 && values[v]==0) {
                const int8_t sign=local.hints[map[v]-1];
                if(sign!=0){
                    out.hints[v]=sign;
                    ++out.hints_count;
                }
            }
            if(out.hints_count>0)out.method="TRAIL_HINTS";
        }
    }
    return out;
}
} // namespace sattrail
