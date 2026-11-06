// R164: causal incremental XOR row status, with native R164 full-row controls.
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
    long component_scan_gate=4096; // 32768 in R164 full mode: protect sparse but useful GF(2) components
    uint64_t propagate_ns=0, propagate_calls=0;
    size_t component_count=0;
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
                throw runtime_error("R164_ROW_STATE_RANGE");
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
    }

    unsigned long callback_events=0;
    chrono::steady_clock::time_point last_telemetry=chrono::steady_clock::now();
    void notify_assignment(const vector<int>&lits) override {
        size_t old_trail=trail.size();
        DrnasBridge::notify_assignment(lits);
        if(incremental_enabled && !disabled)
            for(size_t k=old_trail;k<trail.size();++k) incremental_update(trail[k],true);
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
        vector<int> undone;
        if(incremental_enabled && level<marks.size()){
            size_t start=marks[level];
            if(start>trail.size()) throw runtime_error("R164_BAD_BACKTRACK_MARK");
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
    }

    // For WATCH and DIRECT the original CNF solver handles all conflicts.
    // CLAUSE is the unchanged R133c external-clause baseline.
    bool cb_has_external_clause(bool& forgettable) override {
        if (mode!=CLAUSE) { forgettable=true; return false; }
        return DrnasBridge::cb_has_external_clause(forgettable);
    }
    int cb_add_external_clause_lit() override {
        return mode==CLAUSE ? DrnasBridge::cb_add_external_clause_lit() : 0;
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
        while(next_dirty<dirty.size()) {
            const size_t idx=dirty[next_dirty++];
            if(idx>=rows.size()) {disabled=true;return 0;}
            queued[idx]=0;
            const int ci=component_of_row[idx];
            if(component_feedback && component_blocked[ci]) {
                ++suppressed_rows; continue;
            }
            ++component_scans[ci];
            // Fail-safe per-component abstention; original CNF remains intact.
            if(component_feedback && component_scans[ci]>=component_scan_gate &&
               component_proposals[ci]<2 && component_reasons[ci]==0) {
                component_blocked[ci]=1;
                ++component_gate_events; ++suppressed_rows;
                continue;
            }
            ++direct_ready_checks;
            // R164 fast filter: no full-row scan until an actual XOR unit
            // is possible. Each (un)assignment updates only incident rows.
            if(incremental_enabled && row_unassigned[idx]!=1){
                ++rows_scanned; ++direct_no_units; continue;
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
                    throw runtime_error("R164_INCREMENTAL_PARITY_MISMATCH");
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
        R162Bridge gate({{{1,2,3},0}},3,DIRECT);
        gate.component_feedback=true;
        gate.component_scans[0]=4095;
        gate.notify_new_decision_level();
        gate.notify_assignment({1,2});
        if(gate.cb_propagate()!=0 || gate.component_gate_events!=1 ||
           gate.disabled || gate.reasons.size()!=0)
            throw runtime_error("R164_COMPONENT_GATE_SELFTEST_FAIL");
        cout<<"R164_COMPONENT_GATE_SELFTEST_PASS"<<endl;
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
            cout<<"R164_PROGRESS mode="<<mode
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
static int r162_run(const string& mode,const string& src,
                     const string& proof,double cap_s) {
    CaDiCaL::Solver solver;
    int n=0;
    auto cnf=load_cnf(src,solver,n);
    const bool clean=mode=="clean";
    vector<XorRow> certified=clean?vector<XorRow>{}:load_rows(proof,n);
    const size_t source_rows=certified.size();
    const bool extend=!clean;
    const size_t max_extra=(mode=="direct_full"||mode=="direct_full_feedback"||mode=="direct_incremental")?128:32;
    if(extend)certified=gf2_pairwise_closure(certified,max_extra);
    const long derived=(long)certified.size()-(long)source_rows;
    R162Bridge::Mode m=clean?R162Bridge::FREEZE:
         mode=="watch_boundary"?R162Bridge::WATCH:
         mode=="shadow_boundary"?R162Bridge::SHADOW:R162Bridge::DIRECT;
    R162Bridge bridge(std::move(certified),n,m);
    bridge.adaptive_gate=(mode=="direct_boundary");
    bridge.component_feedback=(mode=="direct_feedback"||mode=="direct_full_feedback");
    bridge.component_scan_gate=(mode=="direct_full_feedback"?32768:4096);
    bridge.incremental_enabled=(mode=="direct_incremental");
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
    cout<<"R164_START mode="<<mode<<" source_rows="<<source_rows
        <<" derived_rows="<<derived<<" clauses="<<cnf.size()
        <<" cap_s="<<cap_s<<"\n"<<flush;
    auto start=chrono::steady_clock::now();
    const int result=solver.solve();
    const double secs=chrono::duration<double>(
        chrono::steady_clock::now()-start).count();
    solver.disconnect_terminator();
    if(result!=10 && result!=20 && result!=0)
        throw runtime_error("R164_UNKNOWN_SOLVER_EXIT");
    if(result==10){
        for(const auto&clause:cnf){
            bool ok=false;
            for(int lit:clause){
                int val=solver.val(abs(lit));
                if(val && ((val>0)==(lit>0))){ok=true;break;}
            }
            if(!ok)throw runtime_error("R164_ORIGINAL_SAT_WITNESS_INVALID");
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
    if(bridge.disabled)throw runtime_error("R164_WATCH_REASON_INVARIANT");
    cout<<fixed<<setprecision(6)
        <<"R164_RESULT mode="<<mode
        <<" status="<<(result==10?"SAT":result==20?"UNSAT":"UNKNOWN")
        <<" solver_s="<<secs<<" source_rows="<<source_rows
        <<" derived_rows="<<derived<<" original_clauses="<<cnf.size()
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
        <<" source_sat_witness_checked="<<(result==10?1:0)
        <<" disabled="<<bridge.disabled<<"\n"<<flush;
    // On 2.1.0 these native statistics include actual CDCL conflicts,
    // decisions, search propagations and learned clauses. The in-solver
    // Terminator guarantees they survive a normal UNKNOWN time cap.
    cout<<"R164_STATS_BEGIN mode="<<mode<<"\n"<<flush;
    solver.statistics();
    cout<<"R164_STATS_END mode="<<mode<<"\n"<<flush;
    return result;
}

int main(int argc,char**argv) {
    try {
        if(argc==2 && string(argv[1])=="selftest"){
            DrnasBridge::watch_selftest();
            gf2_closure_selftest();
            R162Bridge::selftest();
            return 0;
        }
        if(argc!=5) {
            cerr<<"R164_USAGE clean|watch_boundary|shadow_boundary|"
                   "direct_full|direct_full_feedback|direct_incremental|direct_boundary_nogate|direct_boundary|direct_feedback"
                   " ORIGINAL.cnf SOURCE-CERTIFIED.tsv CAP_SECONDS\n";
            return 2;
        }
        const string mode=argv[1];
        if(mode!="clean"&&mode!="watch_boundary"&&mode!="shadow_boundary"&&
           mode!="direct_full"&&mode!="direct_boundary_nogate"&&
           mode!="direct_boundary"&&mode!="direct_feedback"&&
           mode!="direct_full_feedback"&&mode!="direct_incremental")
            throw runtime_error("R164_BAD_MODE");
        const double cap=stod(argv[4]);
        if(!(cap>=1.0&&cap<=120.0))
            throw runtime_error("R164_BAD_CAP");
        return r162_run(mode,argv[2],argv[3],cap);
    }catch(const exception&e){
        cerr<<"R164_FAIL_CLOSED "<<e.what()<<"\n";
        return 2;
    }
}
