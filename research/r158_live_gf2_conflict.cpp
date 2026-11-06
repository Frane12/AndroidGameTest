// R158: source-certified complete XOR conflict feedback into CaDiCaL CDCL.
// Adds globally sound conflicting-row CNF clauses to R157's direct unit reasons.
// R153/R157 baseline sources unchanged. This variant requires an independent
// full-run audit; initial test is known-source development, not blind validation.
// R158 live GF(2) CDCL: original R148 proven reason & reversible watch design
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
    enum Mode { FREEZE, WATCH, CLAUSE, DIRECT, DIRECT_CONFLICT };
    Mode mode;
    std::map<int,std::vector<int>> reasons;
    std::map<int,size_t> reason_pos;
    long direct_proposals=0, direct_reason_requests=0;
    long direct_reason_lits=0, direct_ready_checks=0;
    long direct_no_units=0, direct_expired=0;
    long direct_conflicts_queued=0, direct_conflicts_emitted=0, direct_conflicts_repeated=0;
    size_t peak_reason_cache=0;

    unsigned long callback_events=0;
    chrono::steady_clock::time_point last_telemetry=chrono::steady_clock::now();
    void notify_assignment(const vector<int>&lits) override {
        DrnasBridge::notify_assignment(lits);
        // A bounded, low-cost telemetry checkpoint that survives external
        // timeout, so real mixed SAT search activity can be measured.
        if(mode!=DIRECT && mode!=DIRECT_CONFLICT) return;
        if((++callback_events & 4095UL)!=0) return;
        auto now=chrono::steady_clock::now();
        if(now-last_telemetry < chrono::seconds(1))return;
        last_telemetry=now;
        cout<<"R158_PROGRESS mode="<<(mode==DIRECT?"direct":"directconflict")<<" assignments="<<notifications
            <<" backtracks="<<backtracks
            <<" rows_scanned="<<rows_scanned
            <<" direct_proposals="<<direct_proposals
            <<" reason_requests="<<direct_reason_requests
            <<" conflicts_queued="<<direct_conflicts_queued
            <<" conflicts_emitted="<<direct_conflicts_emitted
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
        if (mode==DIRECT_CONFLICT) {
            forgettable=false;  // Source-XOR entailed conflict clause, globally sound.
            return !outgoing.empty();
        }
        if (mode!=CLAUSE) { forgettable=true; return false; }
        return DrnasBridge::cb_has_external_clause(forgettable);
    }
    int cb_add_external_clause_lit() override {
        if (mode==DIRECT_CONFLICT) {
            if(send_index<outgoing.size())return outgoing[send_index++];
            outgoing.clear();send_index=0;
            ++direct_conflicts_emitted;
            return 0;
        }
        return mode==CLAUSE ? DrnasBridge::cb_add_external_clause_lit() : 0;
    }

    // IPASIR-UP: return a directly implied literal; the immutable reason
    // is cached before return, rather than reconstructing from a later trail.
    int cb_propagate() override {
        if ((mode!=DIRECT && mode!=DIRECT_CONFLICT) || disabled || budget_off) return 0;
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
            if(unknown==0) {
                if(mode==DIRECT_CONFLICT && assigned_parity!=row.rhs) {
                    // Exact source-certified XOR row rules out this *complete*
                    // assignment. The disjunction of its negated literals is
                    // a globally entailed CNF conflict clause; safe across undo.
                    // Do not overwrite an unconsumed clause.
                    sort(clause.begin(),clause.end(),[](int a,int b) {
                        return abs(a)!=abs(b) ? abs(a)<abs(b) : a<b;
                    });
                    if(!outgoing.empty()) {++direct_conflicts_repeated;continue;}
                    if(published.insert(clause).second) {
                        outgoing=std::move(clause);send_index=0;
                        ++direct_conflicts_queued;
                        return 0;
                    }
                    ++direct_conflicts_repeated;
                }
                ++direct_no_units;
                continue;
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
        if(mode!=DIRECT && mode!=DIRECT_CONFLICT) return 0;
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
        // XOR(1,2)=0 forbids {1,-2}: the exact 2-literal clause is -1 OR 2.
        R148Bridge conflict(vector<XorRow>{{{1,2},0}},2,DIRECT_CONFLICT);
        conflict.notify_new_decision_level();
        conflict.notify_assignment({1,-2});
        if(conflict.cb_propagate()!=0)throw runtime_error("R158_CONFLICT_SHOULD_NOT_PROPAGATE");
        bool forgettable=true;
        if(!conflict.cb_has_external_clause(forgettable) || forgettable)
            throw runtime_error("R158_CONFLICT_NOT_QUEUED");
        vector<int> explanation;
        for(;;) {
            int lit=conflict.cb_add_external_clause_lit();
            if(!lit)break;
            explanation.push_back(lit);
        }
        if(explanation!=vector<int>({-1,2}) ||
           conflict.direct_conflicts_queued!=1 ||
           conflict.direct_conflicts_emitted!=1 ||
           conflict.disabled)
            throw runtime_error("R158_CONFLICT_REASON_UNSOUND");
        // Verify globally: every model of source XOR satisfies emitted clause.
        for(int a=0;a<2;a++)for(int b=0;b<2;b++) {
            if((a^b)==0 && !((a==0)||(b==1)))
                throw runtime_error("R158_CONFLICT_NOT_ENTAILED");
        }
        conflict.notify_backtrack(0);
        if(conflict.disabled)throw runtime_error("R158_CONFLICT_UNDO_UNSAFE");
        cout<<"R158_DIRECT_CONFLICT_SELFTEST_PASS unit=-3 second=3 reason_length=3 conflict_clause=-1,2 rollback=1"<<endl;
    }
};

static int r148_run(const string& mode,const string& src,const string& proof) {
    CaDiCaL::Solver solver;
    int n=0;
    auto cnf=load_cnf(src,solver,n);
    vector<XorRow> certified = mode=="clean" ? vector<XorRow>{} : load_rows(proof,n);
    const size_t source_rows=certified.size();
    bool extend=(mode=="clause" || mode=="watch" || mode=="direct" || mode=="directconflict");
    if(extend)certified=gf2_pairwise_closure(certified);
    const long derived=(long)certified.size()-(long)source_rows;
    R148Bridge::Mode m=(mode=="freeze")?R148Bridge::FREEZE:
        (mode=="watch")?R148Bridge::WATCH:
        (mode=="clause")?R148Bridge::CLAUSE:
        (mode=="directconflict")?R148Bridge::DIRECT_CONFLICT:R148Bridge::DIRECT;
    R148Bridge bridge(std::move(certified),n,m);
    if(mode!="clean" && !bridge.rows.empty()) {
        solver.connect_external_propagator(&bridge);
        set<int> observed;
        for(const auto& r:bridge.rows)for(int v:r.vars)observed.insert(v);
        for(int v:observed)solver.add_observed_var(v);
    }
    cout<<"R158_START mode="<<mode<<" source_rows="<<source_rows
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
      <<"R158_RESULT mode="<<mode<<" status="<<(result==10?"SAT":"UNSAT")
      <<" solver_s="<<secs<<" source_rows="<<source_rows
      <<" derived_rows="<<derived<<" original_clauses="<<cnf.size()
      <<" assignments="<<bridge.notifications<<" backtracks="<<bridge.backtracks
      <<" watch_lookups="<<bridge.watch_lookups
      <<" rows_scanned="<<bridge.rows_scanned
      <<" clauses_emitted="<<bridge.clauses_emitted
      <<" direct_proposals="<<bridge.direct_proposals
      <<" direct_reason_requests="<<bridge.direct_reason_requests
      <<" direct_conflicts_queued="<<bridge.direct_conflicts_queued
      <<" direct_conflicts_emitted="<<bridge.direct_conflicts_emitted
      <<" direct_conflicts_repeated="<<bridge.direct_conflicts_repeated
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
        if(mode!="clean"&&mode!="freeze"&&mode!="watch"&&mode!="clause"&&mode!="direct0"&&mode!="direct"&&mode!="directconflict")
            throw runtime_error("R148_BAD_MODE");
        return r148_run(mode,argv[2],argv[3]);
    }catch(const exception&e){
        cerr<<"R148_FAIL_CLOSED "<<e.what()<<"\n";return 2;
    }
}
