#pragma once
// DRNAS STRUCTURE-GATE1: bounded, observational, single-process CNF analyzer.
// Produces ONLY a scheduling hint for the existing MATH5 proof engine.
// NEVER infers SAT/UNSAT. No changes to clauses or CDCL state.
// A rejected/timed-out gate routes to the original CDCL code.
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <map>
#include <string>
#include <unordered_set>
#include <utility>
#include <vector>

namespace drnas_structure_gate {
using Clock = std::chrono::steady_clock;

struct Decision {
    bool use_math5 = false;
    bool timed_out = false;
    std::string reason = "OFF";
    int source_clauses = 0;
    int binary_clauses = 0;
    int negative_binary = 0;
    int positive_alo = 0;
    int candidate_eo = 0;
    int complete_xor = 0;
    int mixed_clauses = 0;
    std::uint64_t inspected_literals = 0;
    double wall_ms = 0;
};

inline std::uint64_t key(int a, int b, int nvars) {
    // Distinguish positive and negative signed literals.
    const std::uint32_t x=std::uint32_t(a+nvars);
    const std::uint32_t y=std::uint32_t(b+nvars);
    return (std::uint64_t(std::min(x,y))<<32)|std::max(x,y);
}

template<class Clauses>
Decision inspect(const Clauses& clauses, int nvars, int original_count,
                 double max_ms) {
    Decision d;
    auto started=Clock::now();
    auto finish=[&]() {
        d.wall_ms=std::chrono::duration<double,std::milli>(
            Clock::now()-started).count();
        return d;
    };
    if (!(max_ms>0) || !std::isfinite(max_ms)) return finish();
    if (nvars<=0 || nvars>6000 || original_count<2 || original_count>100000) {
        d.reason="SIZE_GUARD";return finish();
    }
    const auto deadline=started+std::chrono::duration_cast<Clock::duration>(
        std::chrono::duration<double,std::milli>(max_ms));
    auto expired=[&](){return Clock::now()>=deadline;};
    // Collect just the small indexing keys and potential ALO rows.
    std::vector<std::pair<int,int>> binary;
    binary.reserve(std::min(original_count,100000));
    std::vector<std::vector<int>> alo;
    std::vector<std::vector<int>> xor_short;
    const int max_short_rows=16000;
    for(const auto& clause:clauses) {
        if(clause.learnt)continue;
        const auto& v=clause.lits;
        ++d.source_clauses;
        d.inspected_literals+=v.size();
        if(d.inspected_literals>1500000) {
            d.reason="LITERALS_GUARD";return finish();
        }
        if ((d.source_clauses & 511)==0 && expired()) {
            d.reason="TIME_GUARD_SCAN";d.timed_out=true;return finish();
        }
        if(v.size()==2) {
            ++d.binary_clauses;
            if(v[0]<0 && v[1]<0)++d.negative_binary;
            if(v[0]!=v[1] && v[0]!=-v[1])binary.emplace_back(v[0],v[1]);
        }
        if(v.size()>=3 && v.size()<=128) {
            bool positive=true,negative=true;
            for(int x:v) {positive &= x>0;negative &= x<0;}
            if(positive)++d.positive_alo;
            if(!positive && !negative)++d.mixed_clauses;
            // Build possible exactly-one premises, including signed groups.
            // A broad candidate set is safe: only fully present mutexes count.
            if(alo.size()<4096)alo.push_back(v);
            if(v.size()<=6 && xor_short.size()<max_short_rows)
                xor_short.push_back(v);
        }
    }
    if(d.source_clauses!=original_count) {
        d.reason="CLAUSE_COUNT_GUARD";return finish();
    }
    if(expired()){d.reason="TIME_GUARD_SCAN";d.timed_out=true;return finish();}
    if(binary.size()<3 && xor_short.size()<4){
        d.reason="NO_STRUCTURAL_SIGNAL";return finish();
    }

    // A source-backed exactly-one group is an ALO with every pairwise
    // complement mutex in ORIGINAL source binary clauses. One ALO alone
    // does NOT certify exact-one. These counts trigger only a proof attempt.
    if(binary.size()>=3 && alo.size()>=2){
        std::unordered_set<std::uint64_t> keys;
        keys.reserve(binary.size()*2+1);
        for(size_t i=0;i<binary.size();++i){
            if((i&1023)==0 && expired()){
                d.reason="TIME_GUARD_INDEX";d.timed_out=true;return finish();
            }
            keys.insert(key(binary[i].first,binary[i].second,nvars));
        }
        for(size_t i=0;i<alo.size();++i){
            if(expired()) {
                d.reason="TIME_GUARD_EO";d.timed_out=true;return finish();
            }
            const auto& row=alo[i];
            if(row.size()<3 || row.size()>128)continue;
            bool complete=true;
            std::uint64_t scans=0;
            for(size_t j=1;j<row.size() && complete;++j){
                for(size_t k=0;k<j;++k){
                    ++scans;
                    if((scans & 1023)==0 && expired()) {
                        d.reason="TIME_GUARD_EO";d.timed_out=true;return finish();
                    }
                    if(!keys.count(key(-row[j],-row[k],nvars))){
                        complete=false;break;
                    }
                }
            }
            if(complete) {
                ++d.candidate_eo;
                if(d.candidate_eo>=2) {
                    d.use_math5=true;d.reason="EXACT_ONE_MULTIGROUP";
                    return finish();
                }
            }
        }
    }

    // Fully represented XOR parity on a short shared variable support:
    // 2^(k-1) source clauses forbidding the same assignment parity.
    // This never asserts an actual contradiction; MATH5 independently
    // validates all source premises and proves UNSAT before returning 20.
    if(xor_short.size()>=4) {
        std::map<std::vector<int>,std::uint64_t> support_masks;
        for(size_t i=0;i<xor_short.size();++i) {
            if((i&127)==0 && expired()){
                d.reason="TIME_GUARD_XOR";d.timed_out=true;return finish();
            }
            const auto& row=xor_short[i];
            const int width=int(row.size());
            if(width<3 || width>6)continue;
            std::vector<int> support;
            support.reserve(row.size());
            for(int lit:row)support.push_back(std::abs(lit));
            std::sort(support.begin(),support.end());
            if(std::adjacent_find(support.begin(),support.end())!=support.end())continue;
            unsigned mask=0;
            for(int j=0;j<width;++j){
                // The bit is one when the corresponding source literal is negated.
                for(int lit:row){
                    if(std::abs(lit)==support[j] && lit<0){mask |= (1u<<j);break;}
                }
            }
            support_masks[support] |= (std::uint64_t(1)<<mask);
        }
        for(const auto& entry:support_masks){
            if(expired()){d.reason="TIME_GUARD_XOR";d.timed_out=true;return finish();}
            const int n=int(entry.first.size());
            const std::uint64_t bits=entry.second;
            int even=0,odd=0;
            for(unsigned mask=0;mask<(1u<<n);++mask){
                if((bits>>mask)&1u){
                    if(__builtin_popcount(mask)&1)++odd;
                    else ++even;
                }
            }
            if(even==(1<<(n-1)) || odd==(1<<(n-1))) {
                ++d.complete_xor;
                if(d.complete_xor>=2 || d.candidate_eo>=1){
                    d.use_math5=true;d.reason="XOR_PARITY_MULTIGROUP";
                    return finish();
                }
            }
        }
    }
    d.reason="NO_VALID_MULTIGROUP";
    return finish();
}
} // namespace drnas_structure_gate
