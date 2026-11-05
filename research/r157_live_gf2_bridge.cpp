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

class R148Bridge final : public DrnasBridge {
public:
    enum Mode { FREEZE, WATCH, CLAUSE, DIRECT };
    Mode mode;
    std::map<int,std::vector<int>> reasons;
    std::map<int,size_t> reason_pos;
    long direct_proposals=0, direct_reason_requests=0;
    long direct_reason_lits=0, direct_ready_checks=0;
    long direct_no_units=0, direct_expired=0;
    size_t peak_reason_cache=0;

    unsigned long callback_events=0;
    chrono::steady_clock::time_point last_telemetry=chrono::steady_clock::now();
    void notify_assignment(const vector<int>&lits) override {
        DrnasBridge::notify_assignment(lits);
        // A bounded, low-cost telemetry checkpoint that survives external
        // timeout, so real mixed SAT search activity can be measured.
        if(mode!=DIRECT) return;
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

    R148Bridge(vector<XorRow> input, int n, Mode m):
        DrnasBridge(std::move(input),n,m!=FREEZE,m==CLAUSE),mode(m) {}

    void notify_backtrack(size_t level) override {
        DrnasBridge::notify_backtrack(level);
        for(auto it=reasons.begin();it!=reasons.end();) {
            int v=abs(it->first);
            if(v<=0 || v>=(int)assigned.size() || assigned[v]==0) {
                reason_pos.erase(it->first);
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
        if (mode!=DIRECT || disabled || budget_off) return 0;
        while(next_dirty<dirty.size()) {
            const size_t idx=dirty[next_dirty++];
            if(idx>=rows.size()) {disabled=true;return 0;}
            queued[idx]=0;
            ++direct_ready_checks;
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
            if(unknown!=1) { ++direct_no_units; continue; }
            const int implied=((assigned_parity ^ row.rhs)!=0) ? unassigned : -unassigned;
            // The XOR equation entails this CNF reason under all assignments.
            // The reason starts with the propagated literal as expected by
            // CaDiCaL and includes all negated current row assignments.
            clause.insert(clause.begin(),implied);
            if(clause.size()<2 || clause.size()!=row.vars.size()) {
                disabled=true;return 0;
            }
            reasons[implied]=std::move(clause);
            reason_pos[implied]=0;
            ++direct_proposals;
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
        if(pos==it->second.size()) {pos=0;return 0;}
        ++direct_reason_lits;
        return it->second[pos++];
    }

    static void selftest() {
        // 1 xor 2 xor 3 = 0; if 1 and 2 are true then -3 must follow.
        vector<XorRow> x{{{1,2,3},0}};
        R148Bridge b(std::move(x),3,DIRECT);
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
    }
};

static int r148_run(const string& mode,const string& src,const string& proof) {
    CaDiCaL::Solver solver;
    int n=0;
    auto cnf=load_cnf(src,solver,n);
    vector<XorRow> certified = mode=="clean" ? vector<XorRow>{} : load_rows(proof,n);
    const size_t source_rows=certified.size();
    bool extend=(mode=="clause" || mode=="watch" || mode=="direct");
    if(extend)certified=gf2_pairwise_closure(certified);
    const long derived=(long)certified.size()-(long)source_rows;
    R148Bridge::Mode m=(mode=="freeze")?R148Bridge::FREEZE:
        (mode=="watch")?R148Bridge::WATCH:
        (mode=="clause")?R148Bridge::CLAUSE:R148Bridge::DIRECT;
    R148Bridge bridge(std::move(certified),n,m);
    if(mode!="clean" && !bridge.rows.empty()) {
        solver.connect_external_propagator(&bridge);
        set<int> observed;
        for(const auto& r:bridge.rows)for(int v:r.vars)observed.insert(v);
        for(int v:observed)solver.add_observed_var(v);
    }
    cout<<"R157_START mode="<<mode<<" source_rows="<<source_rows
        <<" derived_rows="<<derived<<" clauses="<<cnf.size()
        <<" observed_vars="<<(bridge.assigned.size()?bridge.assigned.size()-1:0)
        <<"\n"<<flush;
    auto start=chrono::steady_clock::now();
    const int result=solver.solve();
    double secs=chrono::duration<double>(chrono::steady_clock::now()-start).count();
    if(result!=10 && result!=20)throw runtime_error("R148_UNKNOWN_RESULT");
    if(result==10) {
        for(const auto& clause:cnf) {
            bool ok=false;
            for(int lit:clause) {
                const int val=solver.val(abs(lit));
                if(val && ((val>0)==(lit>0))){ok=true;break;}
            }
            if(!ok)throw runtime_error("R148_ORIGINAL_SAT_WITNESS_INVALID");
        }
    }
    if(bridge.disabled)throw runtime_error("R148_WATCH_OR_REASON_INVARIANT");
    cout<<fixed<<setprecision(7)
      <<"R157_RESULT mode="<<mode<<" status="<<(result==10?"SAT":"UNSAT")
      <<" solver_s="<<secs<<" source_rows="<<source_rows
      <<" derived_rows="<<derived<<" original_clauses="<<cnf.size()
      <<" assignments="<<bridge.notifications<<" backtracks="<<bridge.backtracks
      <<" watch_lookups="<<bridge.watch_lookups
      <<" rows_scanned="<<bridge.rows_scanned
      <<" clauses_emitted="<<bridge.clauses_emitted
      <<" direct_proposals="<<bridge.direct_proposals
      <<" direct_reason_requests="<<bridge.direct_reason_requests
      <<" direct_reason_lits="<<bridge.direct_reason_lits
      <<" direct_ready_checks="<<bridge.direct_ready_checks
      <<" direct_no_units="<<bridge.direct_no_units
      <<" reason_cache_peak="<<bridge.peak_reason_cache
      <<" sat_witness_checked="<<(result==10?1:0)
      <<" disabled="<<bridge.disabled<<"\n";
    return result;
}

int main(int argc,char**argv) {
    try{
        if(argc==2 && string(argv[1])=="selftest"){
            DrnasBridge::watch_selftest();
            gf2_closure_selftest();
            R148Bridge::selftest();
            return 0;
        }
        if(argc!=4){cerr<<"R148 usage: clean|freeze|watch|clause|direct0|direct INPUT.cnf CERTIFIED.tsv\n";return 2;}
        string mode=argv[1];
        if(mode!="clean"&&mode!="freeze"&&mode!="watch"&&mode!="clause"&&mode!="direct0"&&mode!="direct")
            throw runtime_error("R148_BAD_MODE");
        return r148_run(mode,argv[2],argv[3]);
    }catch(const exception&e){
        cerr<<"R148_FAIL_CLOSED "<<e.what()<<"\n";return 2;
    }
}
