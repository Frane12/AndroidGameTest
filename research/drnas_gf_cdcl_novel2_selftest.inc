// Positive control: two independently source-entailed XOR rows whose
// GF(2) sum forces x4 from x3, even though original CNF UP cannot.
static vector<vector<int>> novel2_encode(const XorRow& row){
    vector<vector<int>> out;int k=(int)row.vars.size();
    if(k<2||k>8)throw runtime_error("NOVEL2_BAD_ARITY");
    for(int mask=0;mask<(1<<k);++mask){
        if((__builtin_popcount((unsigned)mask)&1)==row.rhs)continue;
        vector<int> clause;
        for(int i=0;i<k;++i)clause.push_back((mask&(1<<i))?-row.vars[i]:row.vars[i]);
        out.push_back(std::move(clause));
    }
    return out;
}
static vector<signed char> novel2_original_cnf_up(
    const vector<vector<int>>& cnf,int n){
    vector<signed char> val(n+1,0);bool changed=true;
    while(changed){
        changed=false;
        for(const auto&clause:cnf){
            bool satisfied=false;int unknown=0,last=0;
            for(int lit:clause){
                int v=abs(lit);
                if(v<1||v>n)throw runtime_error("NOVEL2_BAD_CNF");
                if(!val[v]){++unknown;last=lit;}
                else if((val[v]>0)==(lit>0)){satisfied=true;break;}
            }
            if(satisfied)continue;
            if(!unknown)throw runtime_error("NOVEL2_CNF_UP_CONFLICT");
            if(unknown!=1)continue;
            int v=abs(last);signed char litval=last>0?1:-1;
            if(val[v]&&val[v]!=litval)
                throw runtime_error("NOVEL2_CNF_UP_CONFLICT");
            if(!val[v]){val[v]=litval;changed=true;}
        }
    }
    return val;
}
static void gfcdcl2_selftest(){
    vector<XorRow> source={{{1,2,3},0},{{1,2,4},0}};
    vector<vector<int>> cnf;
    for(const auto& row:source){
        auto block=novel2_encode(row);
        cnf.insert(cnf.end(),block.begin(),block.end());
    }
    cnf.push_back({3});
    auto up=novel2_original_cnf_up(cnf,4);
    if(up[3]!=1||up[4]!=0)
        throw runtime_error("NOVEL2_NOT_NOVEL_VS_ORIGINAL_CNF_UP");
    auto closed=gf2_pairwise_closure(source,32);
    if(closed.size()<3||closed[2].vars!=vector<int>({3,4})||closed[2].rhs!=0)
        throw runtime_error("NOVEL2_CROSS_ROW_NOT_FOUND");
    for(int mask=0;mask<16;++mask){
        auto holds=[&](const XorRow& row){
            int parity=0;for(int v:row.vars)parity^=(mask>>(v-1))&1;
            return parity==row.rhs;
        };
        if(holds(source[0])&&holds(source[1])&&!holds(closed[2]))
            throw runtime_error("NOVEL2_UNSOUND_CLOSURE");
    }
    R158XBridge single(source,4,R158XBridge::DIRECT);
    single.notify_new_decision_level();single.notify_assignment({3});
    if(single.cb_propagate())throw runtime_error("NOVEL2_SINGLE_ROW_UNIT");
    R158XBridge b(closed,4,R158XBridge::DIRECT);
    b.source_row_count=source.size();b.derived_only=true;
    b.notify_new_decision_level();b.notify_assignment({3});
    int implied=b.cb_propagate();
    if(implied!=4||b.derived_direct_proposals!=1||b.source_direct_proposals)
        throw runtime_error("NOVEL2_DERIVED_PROPAGATION_MISSING");
    vector<int> reason;for(;;){
        int lit=b.cb_add_reason_clause_lit(implied);if(!lit)break;reason.push_back(lit);
    }
    if(reason!=vector<int>({4,-3})||b.reason_clauses_completed!=1)
        throw runtime_error("NOVEL2_WRONG_REASON");
    for(int mask=0;mask<16;++mask){
        int a=mask&1,b2=(mask>>1)&1,c=(mask>>2)&1,d=(mask>>3)&1;
        if((a^b2^c)==0&&(a^b2^d)==0&&!(!c||d))
            throw runtime_error("NOVEL2_REASON_NOT_ENTAILED");
    }
    b.notify_assignment({4});b.notify_backtrack(0);
    if(b.disabled||!b.reasons.empty())
        throw runtime_error("NOVEL2_ROLLBACK_FAILURE");
    R158XBridge shadow(closed,4,R158XBridge::SHADOW);
    shadow.source_row_count=source.size();shadow.derived_only=true;
    shadow.notify_new_decision_level();shadow.notify_assignment({3});
    if(shadow.cb_propagate()!=0||shadow.derived_shadow_candidates!=1)
        throw runtime_error("NOVEL2_SHADOW_FAILURE");
    cout<<"GFCDCL_NOVEL2_SELFTEST_PASS original_CNF_UP_x4=unassigned"
        <<" derived_x4=1 sound_masks=16 reason=2 shadow=1 backtrack=1"<<endl;
}
