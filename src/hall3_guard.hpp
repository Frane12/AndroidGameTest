#pragma once
// HALL3: bounded cooperation of CLAUSE-HALL2 and the native weighted BDD rule.
// Both inspect the original CNF. UNKNOWN preserves the existing CF7 search.
// A structural certificate is an alternative to DRAT, never a DRAT lemma.
namespace pcmax {
inline Result analyze_hall3(const std::vector<std::vector<int>>& clauses,
                            int nvars, const std::string& sha, const Options& options) {
    const auto begin=std::chrono::steady_clock::now();
    auto elapsed=[&]() {return std::chrono::duration<double>(
        std::chrono::steady_clock::now()-begin).count();};
    size_t binary=0, nonunit=0;
    for(size_t i=0;i<clauses.size();++i) {
        binary+=clauses[i].size()==2;
        nonunit+=clauses[i].size()>=2;
        if((i&8191)==0 && elapsed()>=options.seconds) {
            Result r;r.reason="hall3_prefilter_budget";r.elapsed=elapsed();return r;
        }
    }
    if(binary<2 || nonunit<3) {
        Result r;r.reason="hall3_prefilter_no_capacity_structure";r.elapsed=elapsed();return r;
    }
    Options first=options;
    first.seconds=std::max(0.0,std::min(0.30,options.seconds*0.4)-elapsed());
    Result hall=analyze_clause_hall(clauses,nvars,sha,first);
    if(hall.verified) {hall.reason="hall3_"+hall.reason;hall.elapsed=elapsed();return hall;}
    Options remaining=options;
    remaining.seconds=std::max(0.0,options.seconds-elapsed());
    if(remaining.seconds<=0) {hall.reason="hall3_shared_budget_exhausted";hall.elapsed=elapsed();return hall;}
    Result weighted=analyze(clauses,nvars,sha,remaining);
    weighted.reason="hall3_"+weighted.reason;
    weighted.elapsed=elapsed();
    return weighted;
}
} // namespace pcmax
