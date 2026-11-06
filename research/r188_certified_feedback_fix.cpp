// DRNAS R177 certified XOR-CNF resolution/2-hop communication; R174/R176 controls preserved.
// R174-B/C: isolated extension of R166x. Original R173 baseline stays untouched.
// R166x: inherited R166X + proven short 2..8 GF2 implications and derived source-equivalent units.
// No guessed rows; all extra TSVs are independently reconstructed and replay-checked on original CNF.
// R158x causal CDCL/GF2: preserve source-certified IPASIR-UP direct reasons.
// All native trial modes compiled ONCE into the same binary; timeout via
// CaDiCaL Terminator exposes genuine conflict/decision/propagation counters.
// R157 live GF(2) CDCL: original R148 proven reason & reversible watch design
// with timeout-surviving propagation progress telemetry. Source rows are
// independently certified from original SHA CNF before solver invocation.
// R148 research-only, direct GF(2) user propagation with source-certified reasons.
// Reuses unchanged R133c reversible XOR watches, exact GF(2) pairwise closure,
// original CNF SAT model verification, and pinned CaDiCaL 2.1.0 IPASIR-UP.
// Pure CNF remains unmodified. No claim of independent UNSAT certification.
#define main drnas_r133c_internal_entry
#include "r133c_native_gf2_cdcl_bridge.cpp"
#undef main
#include <map>
#include <cstdint>
#include <iomanip>
#include <deque>

// R176: every added equation has an explicit 2- or 3-row GF(2) source trace.
// CNF-guided ranking is ONLY a heuristic: soundness depends exclusively on the
// independently certified source equations, not on variable frequencies.
// Derived rows are fed to the existing IPASIR-UP propagator, where CDCL
// assignments (including CNF deductions) can make them unit.
struct R176Closure {
    vector<XorRow> rows;
    long added_pairs=0, added_triples=0, mixed_clause_edges=0;
    long checked_traces=0;
};
static XorRow r176_xor_row(const XorRow&a,const XorRow&b){
    XorRow c; c.rhs=a.rhs^b.rhs;
    set_symmetric_difference(a.vars.begin(),a.vars.end(),
        b.vars.begin(),b.vars.end(),back_inserter(c.vars));
    return c;
}
static R176Closure r176_cnf_guided_closure(
    const vector<XorRow>& source,const vector<vector<int>>&cnf,
    bool use_triples,size_t limit=32){
    R176Closure out;out.rows=source;
    if(source.empty()||limit==0)return out;
    int maxvar=0;
    for(const auto&r:source)for(int v:r.vars)maxvar=max(maxvar,v);
    vector<unsigned char> gfvar(maxvar+1,0);
    for(const auto&r:source)for(int v:r.vars)gfvar[v]=1;
    vector<int> weight(maxvar+1,0);
    for(const auto& clause:cnf){
        if(clause.size()<2||clause.size()>5)continue;
        bool has_gf=false,has_other=false;
        for(int lit:clause){
            int v=abs(lit);
            if(v<=maxvar&&gfvar[v])has_gf=true;
            else has_other=true;
        }
        if(!has_gf)continue;
        if(has_other)++out.mixed_clause_edges;
        for(int lit:clause){
            int v=abs(lit);
            if(v<=maxvar&&gfvar[v])
                weight[v]=min(1000000,weight[v]+(has_other?8:1));
        }
    }
    struct Candidate{XorRow row;vector<int> proof;int score=0;};
    auto rating=[&](const XorRow&r){
        int score=0;
        for(int v:r.vars)score+=weight[v];
        return score;
    };
    vector<Candidate> proposals,pairs;
    set<pair<vector<int>,int>> existing;
    for(const auto&r:source)existing.insert({r.vars,r.rhs});
    for(size_t i=0;i<source.size();++i)for(size_t j=i+1;j<source.size();++j){
        XorRow r=r176_xor_row(source[i],source[j]);
        if(r.vars.size()<2||r.vars.size()>12)continue;
        Candidate cand{std::move(r),{int(i),int(j)},0};
        cand.score=rating(cand.row);
        if(cand.row.vars.size()<=8)proposals.push_back(cand);
        if(use_triples)pairs.push_back(std::move(cand));
    }
    auto better=[](const Candidate&a,const Candidate&b){
        // Optimize for CNF boundary relevance and low-width propagation.
        if(a.row.vars.size()!=b.row.vars.size())
            return a.row.vars.size()<b.row.vars.size();
        if(a.score!=b.score)return a.score>b.score;
        if(a.proof.size()!=b.proof.size())return a.proof.size()>b.proof.size();
        if(a.row.vars!=b.row.vars)return a.row.vars<b.row.vars;
        return a.row.rhs<b.row.rhs;
    };
    if(use_triples){
        // Limit preprocessing independently of formula difficulty.
        sort(pairs.begin(),pairs.end(),better);
        const size_t max_pairs=min(size_t(256),pairs.size());
        size_t operations=0;
        for(size_t p=0;p<max_pairs&&operations<24000;++p){
            const Candidate&mid=pairs[p];
            for(size_t k=0;k<source.size()&&operations<24000;++k){
                if(int(k)==mid.proof[0]||int(k)==mid.proof[1])continue;
                // Only combine equations that actually overlap.
                size_t i=0,j=0;bool shared=false;
                while(i<mid.row.vars.size()&&j<source[k].vars.size()){
                    if(mid.row.vars[i]==source[k].vars[j]){shared=true;break;}
                    if(mid.row.vars[i]<source[k].vars[j])++i;
                    else ++j;
                }
                if(!shared)continue;
                ++operations;
                XorRow r=r176_xor_row(mid.row,source[k]);
                if(r.vars.size()<2||r.vars.size()>8)continue;
                Candidate c{std::move(r),
                    {mid.proof[0],mid.proof[1],int(k)},0};
                c.score=rating(c.row);
                proposals.push_back(std::move(c));
            }
        }
    }
    sort(proposals.begin(),proposals.end(),better);
    // Reserve slots for actual 3-source consequences in triple mode:
    // otherwise abundant pair reductions can hide the causal intervention.
    size_t three_quota=use_triples?limit/2:0,three_used=0;
    auto admit=[&](const Candidate&c){
        if(out.rows.size()-source.size()>=limit)return;
        auto key=make_pair(c.row.vars,c.row.rhs);
        if(existing.count(key))return;
        XorRow reconstructed=source[c.proof[0]];
        for(size_t i=1;i<c.proof.size();++i)
            reconstructed=r176_xor_row(reconstructed,source[c.proof[i]]);
        ++out.checked_traces;
        if(reconstructed.vars!=c.row.vars||reconstructed.rhs!=c.row.rhs)
            throw runtime_error("R176_GF2_TRACE_INVALID");
        if(c.row.vars.size()<2||c.row.vars.size()>8)
            throw runtime_error("R176_ROW_WIDTH_INVALID");
        existing.insert(std::move(key));
        out.rows.push_back(c.row);
        if(c.proof.size()==3){++out.added_triples;++three_used;}
        else ++out.added_pairs;
    };
    if(use_triples)for(const Candidate&c:proposals){
        if(three_used>=three_quota)break;
        if(c.proof.size()==3)admit(c);
    }
    for(const Candidate&c:proposals){
        if(out.rows.size()-source.size()>=limit)break;
        admit(c);
    }
    return out;
}
static void r176_closure_selftest(){
    vector<XorRow> src={{{1,2,3},0},{{3,4,5},1},{{5,6,7},1}};
    vector<vector<int>> cnf={{1,8},{-7,-8},{2,4,8}};
    auto p=r176_cnf_guided_closure(src,cnf,false,32);
    auto t=r176_cnf_guided_closure(src,cnf,true,32);
    if(p.added_pairs==0||p.added_triples!=0||t.added_triples==0||
       p.checked_traces!=p.added_pairs||
       t.checked_traces!=t.added_pairs+t.added_triples)
        throw runtime_error("R176_PROVENANCE_SELFTEST_FAIL");
    auto satisfies=[](const XorRow&r,int mask){
        int x=0;for(int v:r.vars)x^=(mask>>(v-1))&1;return x==r.rhs;
    };
    for(int mask=0;mask<256;++mask){
        bool source_sat=true;
        for(const auto&r:src)source_sat&=satisfies(r,mask);
        if(!source_sat)continue;
        for(const auto&r:p.rows)if(!satisfies(r,mask))
            throw runtime_error("R176_PAIR_UNSOUND");
        for(const auto&r:t.rows)if(!satisfies(r,mask))
            throw runtime_error("R176_TRIPLE_UNSOUND");
    }
    // An XOR consequence becomes a unit under a CNF-implied partial trail.
    cout<<"R176_GF2_CNF_CLOSURE_SELFTEST_PASS pairs="<<p.added_pairs
        <<" triples="<<t.added_triples<<" crossing_clauses="<<t.mixed_clause_edges<<"\n";
}


// R177: certified XOR -> CNF resolution. This is a LOGICAL communication
// bridge, not frequency ranking. Each XOR nogood is a theorem of a source-
// certified GF(2) row. Resolvents combine that theorem with an ORIGINAL CNF
// clause; the optional second hop resolves against another ORIGINAL clause.
// No source clauses are removed. No UNSAT world/certification claims.
struct R177ClauseSet {
    vector<vector<int>> clauses;
    long one_hop=0,two_hop=0,verified=0;
    long xor_nogoods=0,examined=0,tautologies=0;
};
static bool r177_normalize(vector<int>& v){
    sort(v.begin(),v.end(),[](int a,int b){
        return abs(a)==abs(b)?a<b:abs(a)<abs(b);
    });
    vector<int> out;
    for(int lit:v){
        if(!out.empty()&&abs(out.back())==abs(lit)){
            if(out.back()!=lit)return false;
            continue;
        }
        out.push_back(lit);
    }
    v.swap(out);
    return true;
}
static bool r177_resolve(const vector<int>&a,const vector<int>&b,
                          int pivot,vector<int>&out){
    if(pivot==0)return false;
    if(find(a.begin(),a.end(),pivot)==a.end() ||
       find(b.begin(),b.end(),-pivot)==b.end())return false;
    out.clear();
    for(int x:a)if(x!=pivot)out.push_back(x);
    for(int x:b)if(x!=-pivot)out.push_back(x);
    return r177_normalize(out)&&!out.empty();
}
static bool r177_forbidden_xor_nogood(const XorRow&row,int mask,vector<int>&out){
    if(row.vars.size()<2||row.vars.size()>4)return false;
    int parity=0;
    for(size_t i=0;i<row.vars.size();++i)parity^=(mask>>i)&1;
    if(parity==row.rhs)return false;
    out.clear();
    for(size_t i=0;i<row.vars.size();++i)
        out.push_back(((mask>>i)&1)?-row.vars[i]:row.vars[i]);
    if(!r177_normalize(out)||out.size()!=row.vars.size())
        throw runtime_error("R177_FORBIDDEN_NOGOOD_INVALID");
    return true;
}
static R177ClauseSet r177_xor_cnf_resolvents(
    const vector<XorRow>&rows,const vector<vector<int>>&cnf,
    bool twohop,size_t max_clauses=96){
    R177ClauseSet out;
    if(rows.empty()||cnf.empty()||max_clauses==0)return out;
    // Index only short ORIGINAL CNF premises. Sorting never changes
    // the original proof, only the deterministic cost/order of selection.
    map<int,vector<size_t>> opposite_index;
    set<vector<int>> original,seen;
    for(size_t i=0;i<cnf.size();++i){
        vector<int> c=cnf[i];
        if(!r177_normalize(c))continue;
        original.insert(c);
        if(c.size()<2||c.size()>4)continue;
        for(int lit:c)
            if(opposite_index[lit].size()<96)
                opposite_index[lit].push_back(i);
    }
    struct Choice{
        vector<int> clause;
        vector<int> left;
        int pivot=0;
        int source_row=-1;
        size_t source_clause=0;
    };
    vector<Choice> first,second;
    set<vector<int>> emitted_candidates;
    const size_t FIRST_POOL_CAP=2400,SECOND_POOL_CAP=2400;
    for(size_t ri=0;ri<rows.size()&&first.size()<FIRST_POOL_CAP;++ri){
        const XorRow&row=rows[ri];
        if(row.vars.size()<2||row.vars.size()>4)continue;
        // Certified row: variables are unique, sorted, rhs in GF(2).
        if(row.rhs!=0&&row.rhs!=1)
            throw runtime_error("R177_ROW_PARITY_INVALID");
        for(int mask=0;mask<(1<<int(row.vars.size())) &&
            first.size()<FIRST_POOL_CAP;++mask){
            vector<int> nogood;
            if(!r177_forbidden_xor_nogood(row,mask,nogood))continue;
            ++out.xor_nogoods;
            for(int pivot:nogood){
                auto it=opposite_index.find(-pivot);
                if(it==opposite_index.end())continue;
                for(size_t ci:it->second){
                    if(out.examined>=140000||first.size()>=FIRST_POOL_CAP)break;
                    ++out.examined;
                    vector<int> resolvent;
                    if(!r177_resolve(nogood,cnf[ci],pivot,resolvent)){
                        ++out.tautologies;continue;
                    }
                    if(resolvent.size()>5)continue;
                    // Cross-domain: at least one result variable must not
                    // occur in the SAME GF(2) row supplying the XOR theorem.
                    bool external=false;
                    for(int lit:resolvent){
                        if(!binary_search(row.vars.begin(),row.vars.end(),abs(lit))){
                            external=true;break;
                        }
                    }
                    if(!external||original.count(resolvent))continue;
                    if(!emitted_candidates.insert(resolvent).second)continue;
                    first.push_back({std::move(resolvent),nogood,pivot,int(ri),ci});
                }
                if(out.examined>=140000)break;
            }
            if(out.examined>=140000)break;
        }
        if(out.examined>=140000)break;
    }
    auto prefer=[](const Choice&a,const Choice&b){
        if(a.clause.size()!=b.clause.size())
            return a.clause.size()<b.clause.size();
        return a.clause<b.clause;
    };
    sort(first.begin(),first.end(),prefer);
    if(twohop){
        size_t effort=0;
        for(size_t i=0;i<first.size()&&i<240&&
            second.size()<SECOND_POOL_CAP&&effort<40000;++i){
            const auto&one=first[i];
            for(int pivot:one.clause){
                auto it=opposite_index.find(-pivot);
                if(it==opposite_index.end())continue;
                for(size_t ci:it->second){
                    if(effort++>=40000||second.size()>=SECOND_POOL_CAP)break;
                    vector<int> result;
                    if(!r177_resolve(one.clause,cnf[ci],pivot,result)){
                        ++out.tautologies;continue;
                    }
                    if(result.size()>5||original.count(result))continue;
                    // Do not prefer a resolution whose result is no shorter
                    // than both parents unless it introduces an external var.
                    if(!emitted_candidates.insert(result).second)continue;
                    second.push_back({std::move(result),one.clause,pivot,
                                      one.source_row,ci});
                }
            }
        }
        sort(second.begin(),second.end(),prefer);
    }
    set<vector<int>> admitted;
    const size_t first_budget=twohop?max_clauses/2:max_clauses;
    auto admit=[&](const Choice&x,bool is_second) {
        if(admitted.count(x.clause)||out.clauses.size()>=max_clauses)return;
        vector<int> verified;
        if(!r177_resolve(x.left,cnf[x.source_clause],x.pivot,verified)
           ||verified!=x.clause)
            throw runtime_error("R177_RESOLUTION_TRACE_REPLAY_FAIL");
        ++out.verified;
        admitted.insert(x.clause);
        out.clauses.push_back(x.clause);
        if(is_second)++out.two_hop;else ++out.one_hop;
    };
    for(const Choice&x:first){
        if(out.one_hop>=long(first_budget))break;
        admit(x,false);
    }
    for(const Choice&x:second){
        if(out.clauses.size()>=max_clauses)break;
        admit(x,true);
    }
    // Permit all 96 when there are few qualifying two-hop consequences.
    if(twohop)for(const Choice&x:first){
        if(out.clauses.size()>=max_clauses)break;
        admit(x,false);
    }
    return out;
}
static void r177_resolution_selftest(){
    // 1 XOR 2 = 0, (-1 OR 3), (-3 OR 4) imply (-2 OR 4):
    // (1 OR -2) [GF(2)] -> (-2 OR 3) -> (-2 OR 4).
    const vector<XorRow> rows={{{1,2},0}};
    const vector<vector<int>> cnf={{-1,3},{-3,4}};
    const auto one=r177_xor_cnf_resolvents(rows,cnf,false,96);
    const auto two=r177_xor_cnf_resolvents(rows,cnf,true,96);
    auto contains=[](const R177ClauseSet&r,vector<int>c) {
        if(!r177_normalize(c))return false;
        return find(r.clauses.begin(),r.clauses.end(),c)!=r.clauses.end();
    };
    if(one.one_hop==0||one.two_hop!=0||two.two_hop==0||
       !contains(one,{-2,3})||!contains(two,{-2,4}))
        throw runtime_error("R177_TWO_HOP_COMMUNICATION_MISSING");
    if(one.verified!=(long)one.clauses.size() ||
       two.verified!=(long)two.clauses.size())
        throw runtime_error("R177_PROOF_TRACE_COUNTER_INVALID");
    for(int mask=0;mask<16;++mask){
        auto bit=[&](int v){return (mask>>(v-1))&1;};
        if((bit(1)^bit(2))!=0)continue;
        if(bit(1)==1&&bit(3)==0)continue;
        if(bit(3)==1&&bit(4)==0)continue;
        for(const auto&set:{one,two})
          for(const auto&clause:set.clauses){
            bool ok=false;
            for(int lit:clause)
                ok|=(bit(abs(lit))==(lit>0));
            if(!ok)throw runtime_error("R177_DERIVED_MIXED_CLAUSE_UNSOUND");
          }
    }
    // Tautological resolution must be rejected instead of learned.
    vector<int> taut;
    if(r177_resolve({1,2},{-1,-2},1,taut))
        throw runtime_error("R177_TAUTOLOGY_ACCEPTED");
    cout<<"R177_XOR_CNF_RESOLUTION_SELFTEST_PASS first="<<one.one_hop
        <<" twohop="<<two.two_hop<<" checked="<<two.verified<<"\n";
}

class R162Bridge final : public DrnasBridge {
public:
    enum Mode { FREEZE, WATCH, CLAUSE, DIRECT, SHADOW };
    Mode mode;
    std::map<int,std::vector<int>> reasons;
    std::map<int,size_t> reason_pos;
    long direct_proposals=0, direct_reason_requests=0;
    long direct_reason_lits=0, direct_ready_checks=0;
    long direct_no_units=0, direct_expired=0;
    size_t peak_reason_cache=0;
    // R174-B: globally entailed nogoods from certified source XOR rows.
    // R175 selective source-certified conflict admission; same solver as R174.
    bool feedback_clauses=false,feedback_shadow=false;
    int feedback_max_width=0;
    size_t feedback_max_clauses=64,feedback_outgoing_width=0;
    long feedback_candidates=0,feedback_candidates_width4=0,feedback_duplicates=0;
    long feedback_rejected_width=0,feedback_rejected_budget=0;
    long feedback_shadow_admitted=0,feedback_delivered_width4=0,feedback_sum_width_delivered=0;
    std::deque<std::vector<int>> feedback_pending;
    std::set<std::vector<int>> feedback_published;
    long feedback_conflicts_detected=0,feedback_clauses_consumed=0;
    // R174-C: utility measured per 256 scanned certified rows, not CDCL conflicts.
    bool utility_gate=false;
    long utility_windows=0,utility_bad_windows=0,utility_sleeps=0,utility_wakes=0,utility_skipped=0;
    long utility_last_scans=0,utility_last_reasons=0,utility_last_export=0;
    uint64_t utility_last_ns=0;
    long utility_sleep_until=0,utility_episodes=0;
    bool adaptive_gate=false;
    long adaptive_gate_events=0;
    long reason_clauses_completed=0;
    long shadow_candidates=0;
    long source_direct_admissions=0;
    bool component_feedback=false;
    vector<int> component_of_row;
    vector<long> component_scans, component_proposals, component_reasons;
    vector<unsigned char> component_blocked;
    map<int,int> reason_component;
    long component_gate_events=0, suppressed_rows=0;
    long component_scan_gate=4096; // 32768 in R166X full mode: protect sparse but useful GF(2) components
    uint64_t propagate_ns=0, propagate_calls=0;
    size_t component_count=0;
    // R166X: two-watch fast rejection eliminates full-row parity scanning
    // without the 504M R166X per-incidence updates. Source-certified rows
    // and complete literal reasons remain unchanged.
    bool watchlazy_enabled=false, cooldown_enabled=false;
    long cheap_watch_rejects=0, watch_invariant_audits=0;
    vector<long> component_sleep_until, component_epoch_start;
    vector<long> component_epoch_proposal_start, component_epoch_reason_start;
    vector<long> component_sleep_episodes;
    long cooldown_wakes=0, cooldown_skips=0;
    uint64_t assignment_notify_ns=0, backtrack_notify_ns=0, incremental_upd_ns=0;
    bool incremental_enabled=false;
    vector<vector<size_t>> row_incidence;
    vector<int> row_unassigned, row_parity;
    long incremental_row_events=0, incremental_reason_checks=0;
    void initialize_incremental() {
        row_incidence.assign(assigned.size(),{});
        row_unassigned.clear(); row_parity.clear();
        row_unassigned.reserve(rows.size()); row_parity.reserve(rows.size());
        for(size_t idx=0;idx<rows.size();++idx){
            row_unassigned.push_back(int(rows[idx].vars.size()));
            row_parity.push_back(0);
            for(int v:rows[idx].vars) row_incidence[v].push_back(idx);
        }
    }
    void incremental_update(int lit,bool add){
        for(size_t idx:row_incidence[abs(lit)]){
            row_unassigned[idx]+=add?-1:1;
            row_parity[idx]^=(lit>0);
            ++incremental_row_events;
            if(row_unassigned[idx]<0 || row_unassigned[idx]>int(rows[idx].vars.size()))
                throw runtime_error("R166X_ROW_STATE_RANGE");
        }
    }
    long components_with_reasons() const {
        return count_if(component_reasons.begin(),component_reasons.end(),[](long x){return x>0;});
    }
    long blocked_components() const {
        return count_if(component_blocked.begin(),component_blocked.end(),[](unsigned char x){return x!=0;});
    }
    void initialize_components() {
        vector<int> parent(assigned.size());
        for(size_t v=0;v<parent.size();++v)parent[v]=int(v);
        auto root=[&parent](int v) {
            while(parent[v]!=v){parent[v]=parent[parent[v]];v=parent[v];}
            return v;
        };
        for(const auto &r:rows) for(size_t k=1;k<r.vars.size();++k)
            parent[root(r.vars[k])]=root(r.vars[0]);
        map<int,int> ids;
        for(const auto &r:rows) {
            const int rt=root(r.vars[0]);
            auto it=ids.find(rt);
            if(it==ids.end())it=ids.emplace(rt,int(ids.size())).first;
            component_of_row.push_back(it->second);
        }
        component_count=ids.size();
        component_scans.assign(component_count,0);
        component_proposals.assign(component_count,0);
        component_reasons.assign(component_count,0);
        component_blocked.assign(component_count,0);
        component_sleep_until.assign(component_count,0);
        component_epoch_start.assign(component_count,0);
        component_epoch_proposal_start.assign(component_count,0);
        component_epoch_reason_start.assign(component_count,0);
        component_sleep_episodes.assign(component_count,0);
    }

    unsigned long callback_events=0;
    chrono::steady_clock::time_point last_telemetry=chrono::steady_clock::now();
    void notify_assignment(const vector<int>&lits) override {
        auto notify_begin=chrono::steady_clock::now();
        size_t old_trail=trail.size();
        DrnasBridge::notify_assignment(lits);
        auto before_incremental=chrono::steady_clock::now();
        if(incremental_enabled && !disabled)
            for(size_t k=old_trail;k<trail.size();++k) incremental_update(trail[k],true);
        auto notify_end=chrono::steady_clock::now();
        assignment_notify_ns+=(uint64_t)chrono::duration_cast<chrono::nanoseconds>(notify_end-notify_begin).count();
        if(incremental_enabled)
            incremental_upd_ns+=(uint64_t)chrono::duration_cast<chrono::nanoseconds>(notify_end-before_incremental).count();
        // A bounded, low-cost telemetry checkpoint that survives external
        // timeout, so real mixed SAT search activity can be measured.
        if(mode!=DIRECT && mode!=SHADOW) return;
        if((++callback_events & 4095UL)!=0) return;
        auto now=chrono::steady_clock::now();
        if(now-last_telemetry < chrono::seconds(1))return;
        last_telemetry=now;
        cout<<"R157_PROGRESS mode=direct assignments="<<notifications
            <<" backtracks="<<backtracks
            <<" rows_scanned="<<rows_scanned
            <<" direct_proposals="<<direct_proposals
            <<" reason_requests="<<direct_reason_requests
            <<" budget_off="<<budget_off
            <<" disabled="<<disabled<<"\n"<<flush;
    }

    R162Bridge(vector<XorRow> input, int n, Mode m):
        DrnasBridge(std::move(input),n,m!=FREEZE,m==CLAUSE),mode(m) {initialize_components();}

    void notify_backtrack(size_t level) override {
        auto backtrack_start=chrono::steady_clock::now();
        vector<int> undone;
        if(incremental_enabled && level<marks.size()){
            size_t start=marks[level];
            if(start>trail.size()) throw runtime_error("R166X_BAD_BACKTRACK_MARK");
            undone.assign(trail.begin()+start,trail.end());
        }
        DrnasBridge::notify_backtrack(level);
        if(incremental_enabled && !disabled)
            for(auto it=undone.rbegin();it!=undone.rend();++it)
                incremental_update(*it,false);
        for(auto it=reasons.begin();it!=reasons.end();) {
            int v=abs(it->first);
            if(v<=0 || v>=(int)assigned.size() || assigned[v]==0) {
                reason_pos.erase(it->first);
                reason_component.erase(it->first);
                it=reasons.erase(it);
                ++direct_expired;
            } else ++it;
        }
        backtrack_notify_ns+=(uint64_t)chrono::duration_cast<chrono::nanoseconds>(
            chrono::steady_clock::now()-backtrack_start).count();
    }

    // For WATCH and DIRECT the original CNF solver handles all conflicts.
    // CLAUSE is the unchanged R133c external-clause baseline.
    bool cb_has_external_clause(bool& forgettable) override {
        if(mode==CLAUSE)return DrnasBridge::cb_has_external_clause(forgettable);
        forgettable=true;
        if(!feedback_clauses || feedback_shadow || disabled)return false;
        if(!outgoing.empty())return true;
        if(feedback_pending.empty())return false;
        outgoing=std::move(feedback_pending.front());
        feedback_outgoing_width=outgoing.size();
        feedback_pending.pop_front();send_index=0;
        return true;
    }
    int cb_add_external_clause_lit() override {
        if(mode==CLAUSE)return DrnasBridge::cb_add_external_clause_lit();
        if(!feedback_clauses || feedback_shadow || outgoing.empty())return 0;
        int lit=DrnasBridge::cb_add_external_clause_lit();
        if(lit==0) {
            ++feedback_clauses_consumed;
            feedback_sum_width_delivered+=(long)feedback_outgoing_width;
            if(feedback_outgoing_width<=4)++feedback_delivered_width4;
            feedback_outgoing_width=0;
        }
        return lit;
    }

    // IPASIR-UP: return a directly implied literal; the immutable reason
    // is cached before return, rather than reconstructing from a later trail.
    int cb_propagate() override {
        struct ScopeNs {
            uint64_t &total;
            chrono::steady_clock::time_point begin;
            ~ScopeNs() {total+=(uint64_t)chrono::duration_cast<chrono::nanoseconds>(
                chrono::steady_clock::now()-begin).count();}
        } scope{propagate_ns,chrono::steady_clock::now()};
        ++propagate_calls;
        if ((mode!=DIRECT && mode!=SHADOW) || disabled || budget_off) return 0;
        if(utility_gate) {
            if(utility_sleep_until) {
                if(notifications<utility_sleep_until) {
                    ++utility_skipped;
                    dirty.clear();next_dirty=0;
                    fill(queued.begin(),queued.end(),0);
                    return 0;
                }
                utility_sleep_until=0;utility_bad_windows=0;++utility_wakes;
                utility_last_scans=rows_scanned;
                utility_last_reasons=reason_clauses_completed;
                utility_last_export=feedback_clauses_consumed;
                utility_last_ns=propagate_ns;
            }
            if(rows_scanned-utility_last_scans>=256) {
                ++utility_windows;
                const long useful=(reason_clauses_completed-utility_last_reasons)
                                  +(feedback_clauses_consumed-utility_last_export);
                const uint64_t cost=propagate_ns-utility_last_ns;
                if(useful==0 && cost>=100000)++utility_bad_windows;
                else utility_bad_windows=0;
                utility_last_scans=rows_scanned;
                utility_last_reasons=reason_clauses_completed;
                utility_last_export=feedback_clauses_consumed;
                utility_last_ns=propagate_ns;
                if(utility_bad_windows>=3) {
                    // No permanent disabling: reawaken after bounded new assignments.
                    const long shift=std::min(5L,utility_episodes);
                    utility_sleep_until=notifications+(4096L<<shift);
                    ++utility_episodes;++utility_sleeps;
                    dirty.clear();next_dirty=0;
                    fill(queued.begin(),queued.end(),0);
                    return 0;
                }
            }
        }
        while(next_dirty<dirty.size()) {
            const size_t idx=dirty[next_dirty++];
            if(idx>=rows.size()) {disabled=true;return 0;}
            queued[idx]=0;
            const int ci=component_of_row[idx];
            if(component_feedback && component_blocked[ci]) {
                ++suppressed_rows; continue;
            }
            // R166X: NEVER permanently disable an XOR component. Skip
            // work for bounded notification epochs, then wake and probe.
            if(cooldown_enabled && component_sleep_until[ci]!=0){
                if(notifications < component_sleep_until[ci]){
                    ++cooldown_skips; ++suppressed_rows; continue;
                }
                component_sleep_until[ci]=0;
                component_epoch_start[ci]=component_scans[ci];
                component_epoch_proposal_start[ci]=component_proposals[ci];
                component_epoch_reason_start[ci]=component_reasons[ci];
                ++cooldown_wakes;
            }
            ++component_scans[ci];
            // Fail-safe per-component abstention; original CNF remains intact.
            if(component_feedback && component_scans[ci]>=component_scan_gate &&
               component_proposals[ci]<2 && component_reasons[ci]==0) {
                component_blocked[ci]=1;
                ++component_gate_events; ++suppressed_rows;
                continue;
            }
            if(cooldown_enabled && component_scans[ci]-component_epoch_start[ci]>=32768 &&
               component_proposals[ci]-component_epoch_proposal_start[ci]<2 &&
               component_reasons[ci]-component_epoch_reason_start[ci]==0) {
                // Exponential but BOUNDED cooldown, not a permanent veto.
                const long shift=min(5L,component_sleep_episodes[ci]);
                component_sleep_until[ci]=notifications+(65536L<<shift);
                ++component_sleep_episodes[ci];
                ++component_gate_events; ++suppressed_rows;
                continue;
            }
            ++direct_ready_checks;
            // R166X fast filter: no full-row scan until an actual XOR unit
            // is possible. Each (un)assignment updates only incident rows.
            if(incremental_enabled && row_unassigned[idx]!=1){
                ++rows_scanned; ++direct_no_units; continue;
            }
            if(watchlazy_enabled){
                // Exact two-watch invariant: when a row has exactly one
                // unassigned variable, exactly one of its TWO watches is
                // unassigned. If both watch states match, no unit exists.
                // Audit a deterministic sample against the full source row.
                const bool a=(assigned[watch_a[idx]]==0);
                const bool b=(assigned[watch_b[idx]]==0);
                if(a==b && (!feedback_clauses || a)){
                    ++cheap_watch_rejects;
                    if((cheap_watch_rejects & 16383L)==1){
                        ++watch_invariant_audits;
                        int nfree=0;
                        for(int v:rows[idx].vars)nfree+=(assigned[v]==0);
                        if(nfree==1)throw runtime_error("R166X_WATCH_UNIT_INVARIANT");
                    }
                    ++rows_scanned; ++direct_no_units; continue;
                }
            }
            const auto& row=rows[idx];
            int unknown=0, unassigned=0, assigned_parity=0;
            vector<int> clause;
            clause.reserve(row.vars.size());
            for(int v:row.vars) {
                if(v<=0 || v>=(int)assigned.size()) {disabled=true;return 0;}
                int a=assigned[v];
                ++row_literal_reads;
                if(a==0) { ++unknown; unassigned=v; }
                else {
                    assigned_parity ^= (a>0);
                    clause.push_back(a>0 ? -v : v);
                }
            }
            ++rows_scanned;
            if(incremental_enabled){
                ++incremental_reason_checks;
                if(unknown!=row_unassigned[idx] || assigned_parity!=row_parity[idx])
                    throw runtime_error("R166X_INCREMENTAL_PARITY_MISMATCH");
            }
            // Runtime budget is ONLY a selective abstention; already-proven
            // source equations and existing reasons are never altered.
            if(adaptive_gate && rows_scanned>=100000 && direct_proposals<3) {
                ++adaptive_gate_events;
                budget_off=true;
                dirty.clear(); next_dirty=0;
                fill(queued.begin(),queued.end(),0);
                return 0;
            }
            if(unknown==0 && assigned_parity!=row.rhs && feedback_clauses) {
                // Every satisfying assignment of this XOR satisfies the nogood.
                if(clause.size()!=row.vars.size())
                    throw runtime_error("R174_CONFLICT_REASON_WIDTH");
                sort(clause.begin(),clause.end(),[](int a,int b){
                    return abs(a)!=abs(b)?abs(a)<abs(b):a<b;
                });
                ++feedback_candidates;
                if(clause.size()<=4)++feedback_candidates_width4;
                if(feedback_max_width && (int)clause.size()>feedback_max_width)
                    ++feedback_rejected_width;
                else if(feedback_published.count(clause))
                    ++feedback_duplicates;
                else if(feedback_published.size()>=feedback_max_clauses)
                    ++feedback_rejected_budget;
                else {
                    feedback_published.insert(clause);
                    if(feedback_shadow)++feedback_shadow_admitted;
                    else {
                        feedback_pending.push_back(std::move(clause));
                        ++feedback_conflicts_detected;
                    }
                }
            }
            if(unknown!=1) { ++direct_no_units; continue; }
            const int implied=((assigned_parity ^ row.rhs)!=0) ? unassigned : -unassigned;
            // The XOR equation entails this CNF reason under all assignments.
            // The reason starts with the propagated literal as expected by
            // CaDiCaL and includes all negated current row assignments.
            clause.insert(clause.begin(),implied);
            if(clause.size()<2 || clause.size()!=row.vars.size()) {
                disabled=true;return 0;
            }
            if(mode==SHADOW) {
                // Exact same parity check, but never affect the CDCL trail:
                // isolates work of observing and scanning from utility.
                ++shadow_candidates;
                continue;
            }
            reasons[implied]=std::move(clause);
            reason_pos[implied]=0;
            ++direct_proposals;
            ++component_proposals[ci];
            reason_component[implied]=ci;
            peak_reason_cache=max(peak_reason_cache,reasons.size());
            return implied;
        }
        dirty.clear(); next_dirty=0;
        return 0;
    }

    // Called lazily by CaDiCaL for the original, immutable reason.
    int cb_add_reason_clause_lit(int propagated_lit) override {
        if(mode!=DIRECT) return 0;
        auto it=reasons.find(propagated_lit);
        if(it==reasons.end()) {
            // Fail closed on an unexplained external propagation.
            throw runtime_error("R148_MISSING_DIRECT_REASON");
        }
        ++direct_reason_requests;
        size_t& pos=reason_pos[propagated_lit];
        if(pos==it->second.size()) {
            ++reason_clauses_completed;
            auto c=reason_component.find(propagated_lit);
            if(c!=reason_component.end())++component_reasons[c->second];
            pos=0;
            return 0;
        }
        ++direct_reason_lits;
        return it->second[pos++];
    }

    static void selftest() {
        // 1 xor 2 xor 3 = 0; if 1 and 2 are true then -3 must follow.
        vector<XorRow> x{{{1,2,3},0}};
        R162Bridge b(std::move(x),3,DIRECT);
        b.notify_new_decision_level();
        b.notify_assignment({1,2});
        int imp=b.cb_propagate();
        if(imp!=-3) throw runtime_error("R148_SELFTEST_NO_DIRECT_IMPLICATION");
        vector<int> reason;
        while(true) {int lit=b.cb_add_reason_clause_lit(imp);if(!lit)break;reason.push_back(lit);}
        if(reason.size()!=3 || reason[0]!=-3 || reason[1]!=-1 || reason[2]!=-2)
            throw runtime_error("R148_SELFTEST_WRONG_REASON");
        // Exhaustive source-backed reason tautology over the XOR solutions.
        for(int mask=0;mask<8;++mask) {
            int a=(mask&1)!=0, c=(mask&2)!=0, d=(mask&4)!=0;
            if((a^c^d)!=0)continue;
            if(!(!a||!c||!d))throw runtime_error("R148_REASON_NOT_ENTAILED");
        }
        b.notify_assignment({-3});
        b.notify_backtrack(0);
        if(b.disabled || !b.reasons.empty())
            throw runtime_error("R148_SELFTEST_UNDO_FAILURE");
        b.notify_new_decision_level();
        b.notify_assignment({-1,2});
        int second=b.cb_propagate();
        if(second!=3)throw runtime_error("R148_SELFTEST_REPROPAGATION_FAILURE");
        cout<<"R148_DIRECT_SELFTEST_PASS unit=-3 second=3 reason_length=3 rollback=1"<<endl;
        R162Bridge wake({{{1,2,3},0}},3,DIRECT);
        wake.watchlazy_enabled=true;
        wake.cooldown_enabled=true;
        wake.component_scans[0]=32767;
        wake.notify_new_decision_level();
        wake.notify_assignment({1,2});
        if(wake.cb_propagate()!=0 || wake.component_gate_events!=1 ||
           wake.component_sleep_until[0]<=wake.notifications)
            throw runtime_error("R166X_COOLDOWN_SLEEP_SELFTEST_FAIL");
        wake.enqueue_ready(0);
        if(wake.cb_propagate()!=0 || wake.cooldown_skips!=1)
            throw runtime_error("R166X_COOLDOWN_SKIP_SELFTEST_FAIL");
        wake.notifications=wake.component_sleep_until[0];
        wake.enqueue_ready(0);
        if(wake.cb_propagate()!=-3 || wake.cooldown_wakes!=1)
            throw runtime_error("R166X_COOLDOWN_WAKE_SELFTEST_FAIL");
        cout<<"R166X_COOLDOWN_REAWAKEN_SELFTEST_PASS"<<endl;
        R162Bridge lazy({{{1,2,3},0}},3,DIRECT);
        lazy.watchlazy_enabled=true;
        lazy.notify_new_decision_level();
        lazy.notify_assignment({1,2});
        if(lazy.cb_propagate()!=-3)throw runtime_error("R166X_LAZY_UNIT_TEST_FAIL");
        lazy.notify_assignment({-3});
        lazy.notify_backtrack(0);
        if(lazy.disabled)throw runtime_error("R166X_LAZY_BACKTRACK_TEST_FAIL");
        cout<<"R166X_LAZY_SOURCE_REASON_SELFTEST_PASS"<<endl;
        R162Bridge gate({{{1,2,3},0}},3,DIRECT);
        gate.component_feedback=true;
        gate.component_scans[0]=4095;
        gate.notify_new_decision_level();
        gate.notify_assignment({1,2});
        if(gate.cb_propagate()!=0 || gate.component_gate_events!=1 ||
           gate.disabled || gate.reasons.size()!=0)
            throw runtime_error("R166X_COMPONENT_GATE_SELFTEST_FAIL");
        cout<<"R166X_COMPONENT_GATE_SELFTEST_PASS"<<endl;
    }
};


struct R162Clock final : CaDiCaL::Terminator {
    using Clock=chrono::steady_clock;
    Clock::time_point start=Clock::now();
    Clock::time_point last=start;
    double cap_s;
    const R162Bridge& bridge;
    string mode;
    R162Clock(double cap,const R162Bridge&b,string m):
        cap_s(cap),bridge(b),mode(move(m)) {}
    bool terminate() override {
        const auto now=Clock::now();
        const double secs=chrono::duration<double>(now-start).count();
        if(chrono::duration<double>(now-last).count()>=1.0){
            last=now;
            cout<<"R166X_PROGRESS mode="<<mode
                <<" elapsed="<<fixed<<setprecision(3)<<secs
                <<" assignments="<<bridge.notifications
                <<" backtracks="<<bridge.backtracks
                <<" rows_scanned="<<bridge.rows_scanned
                <<" watch_lookups="<<bridge.watch_lookups
                <<" proposals="<<bridge.direct_proposals
                <<" completed_reasons="<<bridge.reason_clauses_completed
                <<" shadow_candidates="<<bridge.shadow_candidates
                <<" adaptive_gate_events="<<bridge.adaptive_gate_events
                <<" disabled="<<bridge.disabled
                <<"\n"<<flush;
        }
        return secs>=cap_s;
    }
};
static int r166x_add_gauss_units(CaDiCaL::Solver&solver,const string&src,int n) {
    ifstream in(src);
    if(!in)throw runtime_error("R166X_GAUSS_UNITS_FILE_MISSING");
    set<int> seen;
    int var, rhs, total=0;
    string line;
    while(getline(in,line)){
        if(line.empty() || line[0]=='#')continue;
        istringstream ss(line);
        if(!(ss>>var>>rhs) || var<1 || var>n || (rhs!=0&&rhs!=1))
            throw runtime_error("R166X_BAD_CERTIFIED_UNIT");
        string extra;
        if(ss>>extra || !seen.insert(var).second)
            throw runtime_error("R166X_DUPLICATE_CERTIFIED_UNIT");
        solver.add(rhs?var:-var);
        solver.add(0);
        ++total;
    }
    if(total>64)throw runtime_error("R166X_TOO_MANY_CERTIFIED_UNITS");
    return total;
}
static int r162_run(const string& mode,const string& src,
                     const string& proof,double cap_s,const string&units_path="") {
    CaDiCaL::Solver solver;
    int n=0;
    auto cnf=load_cnf(src,solver,n);
    const bool clean=mode=="clean";
    // R188: actual CDCL clause export was omitted for direct_full_feedback in R187.
    const bool r188_feedback=(mode=="direct_full_feedback"||
        mode=="direct_full_feedback_budget8"||mode=="direct_full_feedback_shadow8");
    const bool r175=(mode=="gauss_shadow"||mode=="gauss_short4"||
                      mode=="gauss_budget8");
    const bool r176=(mode=="gauss_bridge_pair"||mode=="gauss_bridge_triple");
    const bool r177=(mode=="gauss_resolve1"||mode=="gauss_resolve2");
    const bool gauss=(mode=="gauss_full"||mode=="gauss_watchlazy"||
                      mode=="gauss_cooldown"||mode=="gauss_feedback"||
                      mode=="gauss_utility"||mode=="gauss_feedback_utility"||r175||r176||r177||
                             mode=="direct_full_feedback_budget8"||mode=="direct_full_feedback_shadow8");
    if(gauss==units_path.empty())
        throw runtime_error("R166X_GAUSS_UNITS_PROTOCOL_MISMATCH");
    const int injected_units=gauss?r166x_add_gauss_units(solver,units_path,n):0;
    vector<XorRow> certified=clean?vector<XorRow>{}:load_rows(proof,n);
    const size_t source_rows=certified.size();
    const bool extend=!clean&&!gauss;
    const size_t max_extra=(mode=="direct_full"||mode=="direct_full_feedback"||
                            mode=="direct_incremental"||mode=="direct_watchlazy"||
                            mode=="direct_cooldown"||r188_feedback)?128:32;
    if(extend)certified=gf2_pairwise_closure(certified,max_extra);
    long r176_pairs=0,r176_triples=0,r176_mixed_edges=0,r176_traces=0;
    if(r176||r177){
        const auto closure=r176_cnf_guided_closure(certified,cnf,
            mode!="gauss_bridge_pair",32);
        r176_pairs=closure.added_pairs;r176_triples=closure.added_triples;
        r176_mixed_edges=closure.mixed_clause_edges;
        r176_traces=closure.checked_traces;
        certified=closure.rows;
    }
    R177ClauseSet r177_export;
    if(r177){
        r177_export=r177_xor_cnf_resolvents(certified,cnf,
            mode=="gauss_resolve2",96);
        for(const auto&clause:r177_export.clauses){
            for(int lit:clause)solver.add(lit);
            solver.add(0);
        }
    }
    const long derived=(long)certified.size()-(long)source_rows;
    R162Bridge::Mode m=clean?R162Bridge::FREEZE:
         mode=="watch_boundary"?R162Bridge::WATCH:
         mode=="shadow_boundary"?R162Bridge::SHADOW:R162Bridge::DIRECT;
    R162Bridge bridge(std::move(certified),n,m);
    bridge.adaptive_gate=(mode=="direct_boundary");
    bridge.component_feedback=(mode=="direct_feedback"||r188_feedback);
    bridge.component_scan_gate=(r188_feedback?32768:4096);
    bridge.incremental_enabled=(mode=="direct_incremental");
    bridge.watchlazy_enabled=(mode=="direct_watchlazy"||mode=="direct_cooldown"||
                              mode=="gauss_watchlazy"||mode=="gauss_cooldown");
    bridge.cooldown_enabled=(mode=="direct_cooldown"||mode=="gauss_cooldown"||
                             mode=="gauss_feedback"||mode=="gauss_utility"||
                             mode=="gauss_feedback_utility"||r175||r176||r177);
    bridge.watchlazy_enabled=bridge.watchlazy_enabled ||
        mode=="direct_full_feedback_budget8"||mode=="direct_full_feedback_shadow8"||
        mode=="gauss_feedback"||mode=="gauss_utility"||
        mode=="gauss_feedback_utility"||r175||r176||r177;
    bridge.feedback_clauses=mode=="gauss_feedback"||
                            mode=="gauss_feedback_utility"||r175||r176||r177||r188_feedback;
    bridge.feedback_shadow=mode=="gauss_shadow"||mode=="direct_full_feedback_shadow8";
    bridge.feedback_max_width=(mode=="gauss_short4"||mode=="direct_full_feedback_budget8"||
        mode=="direct_full_feedback_shadow8")?4:0;
    bridge.feedback_max_clauses=(mode=="gauss_budget8"||mode=="direct_full_feedback_budget8"||
        mode=="direct_full_feedback_shadow8")?8:64;
    bridge.utility_gate=mode=="gauss_utility"||mode=="gauss_feedback_utility";
    if(r188_feedback) {
        cout<<"R188_FEEDBACK_CONFIG mode="<<mode
            <<" enabled="<<bridge.feedback_clauses
            <<" shadow="<<bridge.feedback_shadow
            <<" width="<<bridge.feedback_max_width
            <<" budget="<<bridge.feedback_max_clauses
            <<" watchlazy="<<bridge.watchlazy_enabled
            <<" cooldown="<<bridge.cooldown_enabled<<"\n"<<flush;
        if(!bridge.feedback_clauses)throw runtime_error("R188_FEEDBACK_CONFIG_NOT_ENABLED");
    }
    if(bridge.incremental_enabled)bridge.initialize_incremental();
    if(!clean && !bridge.rows.empty()){
        solver.connect_external_propagator(&bridge);
        set<int> observed;
        for(const auto&row:bridge.rows)
            for(int v:row.vars)observed.insert(v);
        for(int v:observed)solver.add_observed_var(v);
    }
    R162Clock clock(cap_s,bridge,mode);
    solver.connect_terminator(&clock);
    cout<<"R166X_START mode="<<mode<<" source_rows="<<source_rows
        <<" derived_rows="<<derived<<" clauses="<<cnf.size()
        <<" cap_s="<<cap_s<<"\n"<<flush;
    auto start=chrono::steady_clock::now();
    const int result=solver.solve();
    const double secs=chrono::duration<double>(
        chrono::steady_clock::now()-start).count();
    solver.disconnect_terminator();
    if(result!=10 && result!=20 && result!=0)
        throw runtime_error("R166X_UNKNOWN_SOLVER_EXIT");
    if(result==10){
        for(const auto&clause:cnf){
            bool ok=false;
            for(int lit:clause){
                int val=solver.val(abs(lit));
                if(val && ((val>0)==(lit>0))){ok=true;break;}
            }
            if(!ok)throw runtime_error("R166X_ORIGINAL_SAT_WITNESS_INVALID");
        }
    }
    // An independent benchmark checker replays this PARTIAL source model
    // against every original clause. Auxiliary variables are never assumed.
    if(result==10){
        int on_line=0;
        cout<<"v ";
        for(int v=1;v<=n;v++){
            const int val=solver.val(v);
            if(!val)continue;
            cout<<(val>0?v:-v)<<" ";
            if(++on_line==32){cout<<"0\nv ";on_line=0;}
        }
        cout<<"0\n"<<flush;
    }
    if(bridge.disabled)throw runtime_error("R166X_WATCH_REASON_INVARIANT");
    cout<<fixed<<setprecision(6)
        <<"R166X_RESULT mode="<<mode
        <<" status="<<(result==10?"SAT":result==20?"UNSAT":"UNKNOWN")
        <<" solver_s="<<secs<<" source_rows="<<source_rows
        <<" derived_rows="<<derived<<" r176_pairs="<<r176_pairs
         <<" r176_triples="<<r176_triples<<" r176_cross_clauses="<<r176_mixed_edges
         <<" r176_traces="<<r176_traces
         <<" r177_onehop="<<r177_export.one_hop
         <<" r177_twohop="<<r177_export.two_hop
         <<" r177_proof_checks="<<r177_export.verified
         <<" r177_candidate_examined="<<r177_export.examined
         <<" gauss_units="<<injected_units
        <<" original_clauses="<<cnf.size()
        <<" assignments="<<bridge.notifications
        <<" backtracks="<<bridge.backtracks
        <<" rows_scanned="<<bridge.rows_scanned
        <<" watch_lookups="<<bridge.watch_lookups
        <<" direct_proposals="<<bridge.direct_proposals
        <<" reason_clauses_completed="<<bridge.reason_clauses_completed
        <<" direct_reason_requests="<<bridge.direct_reason_requests
        <<" direct_reason_lits="<<bridge.direct_reason_lits
        <<" shadow_candidates="<<bridge.shadow_candidates
        <<" adaptive_gate_events="<<bridge.adaptive_gate_events
        <<" component_count="<<bridge.component_count
        <<" component_gate_events="<<bridge.component_gate_events
        <<" blocked_components="<<bridge.blocked_components()
        <<" suppressed_rows="<<bridge.suppressed_rows
        <<" components_with_reasons="<<bridge.components_with_reasons()
        <<" propagate_calls="<<bridge.propagate_calls
        <<" propagate_ns="<<bridge.propagate_ns
        <<" incremental_row_events="<<bridge.incremental_row_events
        <<" incremental_reason_checks="<<bridge.incremental_reason_checks
        <<" cheap_watch_rejects="<<bridge.cheap_watch_rejects
        <<" watch_invariant_audits="<<bridge.watch_invariant_audits
        <<" cooldown_wakes="<<bridge.cooldown_wakes
        <<" cooldown_skips="<<bridge.cooldown_skips
        <<" assignment_notify_ns="<<bridge.assignment_notify_ns
        <<" backtrack_notify_ns="<<bridge.backtrack_notify_ns
        <<" incremental_upd_ns="<<bridge.incremental_upd_ns
        <<" feedback_conflicts_detected="<<bridge.feedback_conflicts_detected
        <<" feedback_clauses_consumed="<<bridge.feedback_clauses_consumed
        <<" feedback_candidates="<<bridge.feedback_candidates
        <<" feedback_candidates_width4="<<bridge.feedback_candidates_width4
        <<" feedback_duplicates="<<bridge.feedback_duplicates
        <<" feedback_rejected_width="<<bridge.feedback_rejected_width
        <<" feedback_rejected_budget="<<bridge.feedback_rejected_budget
        <<" feedback_shadow_admitted="<<bridge.feedback_shadow_admitted
        <<" feedback_delivered_width4="<<bridge.feedback_delivered_width4
        <<" feedback_sum_width_delivered="<<bridge.feedback_sum_width_delivered
        <<" utility_windows="<<bridge.utility_windows
        <<" utility_sleeps="<<bridge.utility_sleeps
        <<" utility_wakes="<<bridge.utility_wakes
        <<" utility_skipped="<<bridge.utility_skipped
        <<" source_sat_witness_checked="<<(result==10?1:0)
        <<" disabled="<<bridge.disabled<<"\n"<<flush;
    // On 2.1.0 these native statistics include actual CDCL conflicts,
    // decisions, search propagations and learned clauses. The in-solver
    // Terminator guarantees they survive a normal UNKNOWN time cap.
    cout<<"R166X_STATS_BEGIN mode="<<mode<<"\n"<<flush;
    solver.statistics();
    cout<<"R166X_STATS_END mode="<<mode<<"\n"<<flush;
    return result;
}

int main(int argc,char**argv) {
    try {
        if(argc==2 && string(argv[1])=="selftest"){
            DrnasBridge::watch_selftest();
            gf2_closure_selftest();
            r176_closure_selftest();
            r177_resolution_selftest();
            {
                // Four assignments may be CNF-propagated: the newly derived
                // triple-source XOR row becomes a single correct IPASIR-UP unit.
                vector<XorRow> src={{{1,2,3},0},{{3,4,5},1},{{5,6,7},1}};
                vector<vector<int>> clauses={{1,8},{-7,-8},{2,4,8}};
                auto proof=r176_cnf_guided_closure(src,clauses,true,32);
                bool demonstrated=false;
                for(const auto&r:proof.rows){
                    if(r.vars!=vector<int>({1,2,4,6,7})||r.rhs!=0)continue;
                    R162Bridge b({r},8,R162Bridge::DIRECT);
                    b.watchlazy_enabled=true;
                    b.notify_new_decision_level();
                    b.notify_assignment({1,2,4,6});
                    const int implication=b.cb_propagate();
                    if(implication!=-7)
                        throw runtime_error("R176_TRIPLE_REASON_MISSING");
                    vector<int> reason;
                    for(int lit=0;(lit=b.cb_add_reason_clause_lit(-7))!=0;)
                        reason.push_back(lit);
                    if(reason.size()!=5 || reason[0]!=-7)
                        throw runtime_error("R176_TRIPLE_REASON_INVALID");
                    for(int mask=0;mask<128;++mask){
                        bool src_sat=true;
                        for(const auto&orig:src){
                            int parity=0;
                            for(int v:orig.vars)parity^=(mask>>(v-1))&1;
                            src_sat&=(parity==orig.rhs);
                        }
                        if(!src_sat)continue;
                        bool clause_sat=false;
                        for(int lit:reason){
                            bool val=((mask>>(abs(lit)-1))&1)!=0;
                            clause_sat|=(val==(lit>0));
                        }
                        if(!clause_sat)
                            throw runtime_error("R176_CNF_GUIDED_REASON_NOT_ENTAILED");
                    }
                    demonstrated=true;break;
                }
                if(!demonstrated)
                    throw runtime_error("R176_TRIPLE_ROW_NOT_GENERATED");
                cout<<"R176_GF2_CNF_PROPAGATION_SELFTEST_PASS\n";
            }
            R162Bridge::selftest();
            {
                R162Bridge inc({{{1,2,3},0}},3,R162Bridge::DIRECT);
                inc.incremental_enabled=true;
                inc.initialize_incremental();
                inc.notify_new_decision_level();
                inc.notify_assignment({1,2});
                if(inc.row_unassigned[0]!=1 || inc.row_parity[0]!=0 ||
                   inc.cb_propagate()!=-3)throw runtime_error("R166X_INCREMENTAL_UNIT_TEST_FAIL");
                inc.notify_backtrack(0);
                if(inc.row_unassigned[0]!=3 || inc.row_parity[0]!=0 ||
                   inc.incremental_row_events!=4)
                    throw runtime_error("R166X_INCREMENTAL_BACKTRACK_TEST_FAIL");
                cout<<"R166X_INCREMENTAL_SELFTEST_PASS"<<"\n";
            }
            {
                CaDiCaL::Solver units_s;
                units_s.add(1);units_s.add(0);
                if(units_s.solve()!=10 || units_s.val(1)<=0)
                    throw runtime_error("R166X_DERIVED_UNIT_NATIVE_SELFTEST_FAIL");
                cout<<"R166X_DERIVED_UNIT_NATIVE_SELFTEST_PASS\n";
            }
            {
                // XOR (1,2,3)=0 forbids all three positive.
                R162Bridge b({{{1,2,3},0}},3,R162Bridge::DIRECT);
                b.feedback_clauses=true;b.watchlazy_enabled=true;
                b.notify_new_decision_level();
                b.notify_assignment({1,2,3});
                if(b.cb_propagate()!=0 || b.feedback_conflicts_detected!=1)
                    throw runtime_error("R174_CONFLICT_MISSING");
                bool forgettable=false;
                if(!b.cb_has_external_clause(forgettable))
                    throw runtime_error("R174_EXTERNAL_CLAUSE_MISSING");
                vector<int> clause;
                while(true){
                    int lit=b.cb_add_external_clause_lit();
                    if(!lit)break;
                    clause.push_back(lit);
                }
                if(clause!=vector<int>({-1,-2,-3}) || b.feedback_clauses_consumed!=1)
                    throw runtime_error("R174_CONFLICT_REASON_WRONG");
                for(int mask=0;mask<8;mask++) {
                    int parity=((mask>>0)&1)^((mask>>1)&1)^((mask>>2)&1);
                    bool satisfied=false;
                    for(int lit:clause) {
                        bool val=bool(mask&(1<<(abs(lit)-1)));
                        satisfied|=(val==(lit>0));
                    }
                    if(parity==0 && !satisfied)
                        throw runtime_error("R174_CLAUSE_NOT_ENTAILED");
                }
                cout<<"R174_B_CERTIFIED_CONFLICT_SELFTEST_PASS\n";
            }
            {
                R162Bridge g({{{1,2,3},0}},3,R162Bridge::DIRECT);
                g.utility_gate=true;g.notifications=10;
                g.rows_scanned=768;g.propagate_ns=300000;
                g.utility_bad_windows=2;
                if(g.cb_propagate()!=0 || g.utility_sleeps!=1 ||
                   g.utility_sleep_until<=g.notifications)
                    throw runtime_error("R174_C_SLEEP_FAIL");
                g.notifications=g.utility_sleep_until;
                g.cb_propagate();
                if(g.utility_wakes!=1 || g.disabled)
                    throw runtime_error("R174_C_WAKE_FAIL");
                cout<<"R174_C_UTILITY_WAKE_SELFTEST_PASS\n";
            }
            {
                // Three deterministic causal controls on the same verified XOR reason.
                auto probe=[](int kind) {
                    R162Bridge b({{{1,2,3},0}},3,R162Bridge::DIRECT);
                    b.feedback_clauses=true;b.watchlazy_enabled=true;
                    b.feedback_shadow=(kind==0);
                    b.feedback_max_width=(kind==1?2:0);
                    b.feedback_max_clauses=(kind==2?0:64);
                    b.notify_new_decision_level();
                    b.notify_assignment({1,2,3});
                    if(b.cb_propagate()!=0 || b.feedback_candidates!=1)
                        throw runtime_error("R175_CANDIDATE_FAIL");
                    bool forgettable=false;
                    if(b.cb_has_external_clause(forgettable))
                        throw runtime_error("R175_ABLATION_LEAKED_CLAUSE");
                    if(b.feedback_clauses_consumed!=0)
                        throw runtime_error("R175_UNEXPECTED_DELIVERY");
                    if(kind==0 && b.feedback_shadow_admitted!=1)
                        throw runtime_error("R175_SHADOW_NOT_COMPUTED");
                    if(kind==1 && b.feedback_rejected_width!=1)
                        throw runtime_error("R175_WIDTH_GATE_FAIL");
                    if(kind==2 && b.feedback_rejected_budget!=1)
                        throw runtime_error("R175_BUDGET_GATE_FAIL");
                };
                probe(0);probe(1);probe(2);
                cout<<"R175_SHADOW_SHORT4_BUDGET8_SELFTEST_PASS\n";
            }
            return 0;
        }
        if(argc!=5 && argc!=6) {
            cerr<<"R166X_USAGE clean|gauss_full|gauss_watchlazy|gauss_cooldown|watch_boundary|shadow_boundary|"
                   "direct_full|direct_full_feedback|direct_incremental|direct_watchlazy|direct_cooldown|direct_boundary_nogate|direct_boundary|direct_feedback"
                   " ORIGINAL.cnf SOURCE-CERTIFIED.tsv CAP_SECONDS\n";
            return 2;
        }
        const string mode=argv[1];
        if(mode!="clean"&&mode!="watch_boundary"&&mode!="shadow_boundary"&&
           mode!="direct_full"&&mode!="direct_boundary_nogate"&&
           mode!="direct_boundary"&&mode!="direct_feedback"&&
           mode!="direct_full_feedback"&&mode!="direct_full_feedback_budget8"&&
           mode!="direct_full_feedback_shadow8"&&mode!="direct_incremental"&&
           mode!="direct_watchlazy"&&mode!="direct_cooldown"&&
           mode!="gauss_full"&&mode!="gauss_watchlazy"&&mode!="gauss_cooldown"&&
           mode!="gauss_feedback"&&mode!="gauss_utility"&&
           mode!="gauss_feedback_utility"&&
           mode!="gauss_shadow"&&mode!="gauss_short4"&&
           mode!="gauss_budget8"&&mode!="gauss_bridge_pair"&&
            mode!="gauss_bridge_triple"&&mode!="gauss_resolve1"&&
            mode!="gauss_resolve2")
            throw runtime_error("R166X_BAD_MODE");
        const double cap=stod(argv[4]);
        if(!(cap>=1.0&&cap<=120.0))
            throw runtime_error("R166X_BAD_CAP");
        return r162_run(mode,argv[2],argv[3],cap,argc==6?argv[5]:"");
    }catch(const exception&e){
        cerr<<"R166X_FAIL_CLOSED "<<e.what()<<"\n";
        return 2;
    }
}
