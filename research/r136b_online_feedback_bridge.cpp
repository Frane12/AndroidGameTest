// R136B: monitored native CaDiCaL IPASIR-UP XOR -> CDCL feedback.
// Reuse R133c unchanged; counting callback events never changes clause truth.
// Feedback matches are temporal observations, NOT causal proof of propagation.
// Guarded mode may STOP sending entailed clauses; never changes original CNF.
#define main drnas_r133c_internal_entry
#include "r133c_native_gf2_cdcl_bridge.cpp"
#undef main

#include <cstdint>

struct FeedbackBridge : DrnasBridge {
    struct Pending { int lit; long notified_at; long backtracks_at; };
    vector<Pending> pending;
    bool monitor = false, gated = false;
    long value_stops = 0;
    long feedback_callbacks = 0, feedback_candidates = 0;
    long feedback_units_emitted = 0, feedback_conflicts_emitted = 0;
    long feedback_reason_width_sum = 0;
    long feedback_confirmed = 0, feedback_opposite = 0;
    long feedback_expired = 0, feedback_backtrack = 0;
    long feedback_derived_emitted = 0, feedback_short_emitted = 0;
    long observed_assignment_events = 0, observed_backtrack_events = 0;
    size_t source_count = 0;

    FeedbackBridge(vector<XorRow> in, int n, bool emit, bool gate,
                   bool monitor_on, bool stop_on_low_yield, size_t sources) :
        DrnasBridge(std::move(in), n, emit, gate),
        monitor(monitor_on), gated(stop_on_low_yield), source_count(sources) {}

    void notify_assignment(const vector<int>& lits) override {
        // Match only assignments observed AFTER the clause was emitted.
        // We cannot infer which reason CaDiCaL actually used.
        if (monitor) for (int lit : lits) {
            ++observed_assignment_events;
            for (size_t j = 0; j < pending.size();) {
                const auto e = pending[j];
                if (abs(e.lit) == abs(lit)) {
                    if (e.lit == lit) ++feedback_confirmed;
                    else ++feedback_opposite;
                    pending.erase(pending.begin()+j);
                } else if (observed_assignment_events-e.notified_at > 32) {
                    ++feedback_expired;
                    pending.erase(pending.begin()+j);
                } else ++j;
            }
        }
        DrnasBridge::notify_assignment(lits);
    }

    void notify_backtrack(size_t level) override {
        if (monitor) {
            ++observed_backtrack_events;
            // Backtracking before observed propagation is distinct from CDCL
            // conflict count; no causal attribution is made.
            feedback_backtrack += (long)pending.size();
            pending.clear();
        }
        DrnasBridge::notify_backtrack(level);
    }

    bool cb_has_external_clause(bool& forgettable) override {
        if (monitor) {
            ++feedback_callbacks;
            if (gated && !budget_off && outgoing.empty() &&
                ((watch_lookups >= 15000 && clauses_emitted == 0) ||
                 (watch_lookups >= 80000 && feedback_confirmed == 0))) {
                // Safe suppression: all equations remain consequences;
                // not sending them never removes any original clauses.
                budget_off=true;
                ++value_stops;
                pending.clear();
            }
        }
        const long before = clauses_emitted;
        bool yes = DrnasBridge::cb_has_external_clause(forgettable);
        if (monitor && yes && clauses_emitted > before) {
            ++feedback_candidates;
            feedback_reason_width_sum += (long)outgoing.size();
            if(outgoing.size() <= 4) ++feedback_short_emitted;
            int unknowns=0, candidate=0;
            for (int lit : outgoing) {
                int v=abs(lit);
                if (v < 1 || v >= (int)assigned.size())
                    throw runtime_error("R136B_INVALID_REASON_LITERAL");
                if (assigned[v] == 0) {++unknowns;candidate=lit;}
                else if ((assigned[v] > 0) == (lit > 0))
                    throw runtime_error("R136B_NOT_UNIT_OR_CONFLICT");
            }
            if (unknowns == 1) {
                ++feedback_units_emitted;
                pending.push_back({candidate,observed_assignment_events,
                                   observed_backtrack_events});
            } else if (unknowns == 0) {
                ++feedback_conflicts_emitted;
            } else throw runtime_error("R136B_BAD_REASON_UNASSIGNED");
            // Outgoing clauses cannot carry original row ID through R99.
            // Count derived rows supplied separately, not message origin.
        }
        return yes;
    }

    static void feedback_selftest() {
        vector<XorRow> one{{{1,2,3},0}};
        FeedbackBridge f(std::move(one),3,true,true,true,false,1);
        f.notify_new_decision_level();
        f.notify_assignment({1,2});
        bool forgettable=false;
        if(!f.cb_has_external_clause(forgettable))
            throw runtime_error("R136B_NO_UNIT_SIGNAL");
        int last=0; int count=0;
        for (;;) {
            int lit=f.cb_add_external_clause_lit();
            if(!lit)break;
            ++count;
            if (abs(lit)==3)last=lit;
        }
        if(count!=3||last!=-3||f.feedback_units_emitted!=1)
            throw runtime_error("R136B_SIGNAL_REASON_FAIL");
        f.notify_assignment({-3});
        if(f.feedback_confirmed!=1 || f.feedback_opposite!=0 ||
           !f.pending.empty())
            throw runtime_error("R136B_FEEDBACK_MATCH_FAIL");
        f.notify_backtrack(0);
        if(f.disabled)
            throw runtime_error("R136B_BACKTRACK_INVALID");
        cout<<"R136B_FEEDBACK_SELFTEST_PASS unit="<<f.feedback_units_emitted
            <<" confirmed="<<f.feedback_confirmed<<" backtracks="
            <<f.observed_backtrack_events<<"\n";
    }
};

int main(int argc, char** argv) {
    try {
        if(argc==2 && string(argv[1])=="feedback-selftest") {
            FeedbackBridge::feedback_selftest();return 0;
        }
        if(argc==2 && string(argv[1])=="gf2selftest") {
            gf2_closure_selftest();return 0;
        }
        if(argc==2 && string(argv[1])=="selftest") {
            DrnasBridge::watch_selftest();return 0;
        }
        if(argc!=4) {cerr<<"R136B usage: clean|active|gf2|feedback|guard CNF proof-certified-rows\n";return 2;}
        string mode=argv[1];
        if(mode!="clean"&&mode!="active"&&mode!="gf2"&&
           mode!="feedback"&&mode!="guard") {
            cerr<<"R136B unknown mode\n";return 2;
        }
        CaDiCaL::Solver solver;
        int n;
        string source=argv[2],cert=argv[3];
        auto original_cnf=load_cnf(source,solver,n);
        vector<XorRow> rows=mode=="clean" ? vector<XorRow>{} : load_rows(cert,n);
        size_t source_rows=rows.size();
        if(mode=="gf2"||mode=="feedback"||mode=="guard")
            rows=gf2_pairwise_closure(rows);
        size_t derived_rows=rows.size()-source_rows;
        bool monitored=(mode=="feedback"||mode=="guard");
        FeedbackBridge bridge(std::move(rows),n,mode!="clean",
                              mode!="clean"&&mode!="active",
                              monitored,mode=="guard",source_rows);
        if(mode!="clean"&&!bridge.rows.empty()) {
            solver.connect_external_propagator(&bridge);
            set<int> observed;
            for(const auto& row:bridge.rows)
                for(int v:row.vars)observed.insert(v);
            for(int v:observed)solver.add_observed_var(v);
        }
        auto start=chrono::steady_clock::now();
        int result=solver.solve();
        double wall=chrono::duration<double>(chrono::steady_clock::now()-start).count();
        if(result==10) {
            for(const auto& clause:original_cnf) {
                bool satisfied=false;
                for(int lit:clause) {
                    int val=solver.val(abs(lit));
                    if(val&&((val>0)==(lit>0))) {satisfied=true;break;}
                }
                if(!satisfied)throw runtime_error("R136B_CNF_SAT_WITNESS_INVALID");
            }
        }else if(result!=20) throw runtime_error("R136B_UNKNOWN_SOLVER_STATUS");
        if(bridge.disabled)throw runtime_error("R136B_WATCH_INVARIANT_DISABLED");
        cout<<"R136B_RESULT mode="<<mode
            <<" status="<<(result==10?"SAT":"UNSAT")
            <<" solve_s="<<wall
            <<" source_rows="<<source_rows
            <<" derived_rows="<<derived_rows
            <<" clauses_emitted="<<bridge.clauses_emitted
            <<" rows_scanned="<<bridge.rows_scanned
            <<" watch_lookups="<<bridge.watch_lookups
            <<" row_literal_reads="<<bridge.row_literal_reads
            <<" callbacks="<<bridge.callbacks
            <<" assignments="<<bridge.notifications
            <<" backtracks="<<bridge.backtracks
            <<" feedback_callbacks="<<bridge.feedback_callbacks
            <<" feedback_candidates="<<bridge.feedback_candidates
            <<" unit_messages="<<bridge.feedback_units_emitted
            <<" conflict_messages="<<bridge.feedback_conflicts_emitted
            <<" width_sum="<<bridge.feedback_reason_width_sum
            <<" short_messages="<<bridge.feedback_short_emitted
            <<" observed_after_emit_matches="<<bridge.feedback_confirmed
            <<" observed_after_emit_opposites="<<bridge.feedback_opposite
            <<" observed_after_emit_expired="<<bridge.feedback_expired
            <<" observed_after_emit_backtracks="<<bridge.feedback_backtrack
            <<" feedback_unresolved="<<bridge.pending.size()
            <<" feedback_guard_stops="<<bridge.value_stops
            <<" bridge_budget_off="<<bridge.budget_off
            <<" source_sat_witness_checked="<<(result==10)
            <<" disabled="<<bridge.disabled<<"\n";
        return result;
    }catch(const exception& ex){
        cerr<<"R136B_FAIL_CLOSED "<<ex.what()<<"\n";
        return 2;
    }
}
