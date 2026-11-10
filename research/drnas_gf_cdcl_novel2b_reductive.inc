// NOVEL2B: select only XOR combinations with cancellation that genuinely
// shortens at least one input relation, not disjoint XOR2+XOR2 width4 noise.
// Every output is the exact GF(2) symmetric difference of two certified rows.
static vector<XorRow> gfcdcl2b_reductive_closure(
    const vector<XorRow>& source,size_t max_extra=32){
    vector<XorRow> result=source;
    set<pair<vector<int>,int>> seen;
    for(const auto& row:source)seen.insert({row.vars,row.rhs});
    struct Candidate {vector<int> vars;int rhs;int gain;};
    vector<Candidate> choices;
    for(size_t i=0;i<source.size();++i)
      for(size_t j=i+1;j<source.size();++j){
        const auto&a=source[i].vars;const auto&b=source[j].vars;
        vector<int> derived;
        set_symmetric_difference(a.begin(),a.end(),b.begin(),b.end(),
                                 back_inserter(derived));
        int width=(int)derived.size();
        int gain=max(a.size(),b.size())-derived.size();
        // Strictly reducing source width is a structural precondition
        // for possible new propagation beyond original complete XOR CNF UP.
        if(width<2||width>6||gain<=0)continue;
        int rhs=source[i].rhs ^ source[j].rhs;
        if(!seen.count({derived,rhs}))
            choices.push_back({std::move(derived),rhs,gain});
      }
    sort(choices.begin(),choices.end(),[](const Candidate&a,const Candidate&b){
        if(a.vars.size()!=b.vars.size())return a.vars.size()<b.vars.size();
        if(a.gain!=b.gain)return a.gain>b.gain;
        if(a.vars!=b.vars)return a.vars<b.vars;
        return a.rhs<b.rhs;
    });
    for(const auto&c:choices){
        if(result.size()-source.size()>=max_extra)break;
        if(seen.insert({c.vars,c.rhs}).second)
            result.push_back({c.vars,c.rhs});
    }
    return result;
}
static void gfcdcl2b_reductive_selftest(){
    vector<XorRow> useful={{{1,2,3},0},{{1,2,4},0}};
    auto rows=gfcdcl2b_reductive_closure(useful);
    if(rows.size()!=3||rows.back().vars!=vector<int>({3,4})||
       rows.back().rhs!=0)
        throw runtime_error("NOVEL2B_MISSING_CANCELLATION");
    vector<XorRow> noise={{{1,2},0},{{3,4},1}};
    if(gfcdcl2b_reductive_closure(noise).size()!=noise.size())
        throw runtime_error("NOVEL2B_SPURIOUS_DISJOINT_CLOSURE");
    // Unit rows are intentionally not emitted into the watch bridge.
    vector<XorRow> unit={{{1,2},0},{{1,2,3},1}};
    if(gfcdcl2b_reductive_closure(unit).size()!=unit.size())
        throw runtime_error("NOVEL2B_UNIT_UNSUPPORTED");
    cout<<"GFCDCL_NOVEL2B_REDUCTIVE_SELFTEST_PASS shared_cancel=1"
        <<" disjoint_filtered=1 unit_separate_track=1"<<endl;
}
