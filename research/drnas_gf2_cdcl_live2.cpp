// DRNAS GF2CDCL-LIVE2: bounded, flushed in-thread CDCL callbacks snapshot.
// Its telemetry survives forcible timeout via partial stderr; no async data races.
// Ready events are POTENTIAL unit parity signals, not necessarily new CDCL implications.
// DRNAS GF2CDCL-LIVE1 extends R96 reversible XOR IPASIR-UP bridge.
// Externally certified source XOR rows only, with direct-source-unit novelty.
// DRNAS R96-C: reversible incremental XOR state and readiness-gated cooperation of experimental live CDCL <-> XOR clause communication (CaDiCaL IPASIR-UP).
// Every dynamic clause is a logical consequence of a parity row independently
// certified in the Python source-to-XOR exporter; NOT a world-record solver.
#include "cadical.hpp"
#include <algorithm>
#include <chrono>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>
#include <cmath>

using namespace std;

struct XorRow {
    vector<int> vars;
    int rhs = 0;
};

// R96-C: exact, reversible incremental parity + two-unassigned-variable
// readiness gate + an optional overhead budget. R95 is retained as baseline.
// The readiness gate is semantically equivalent to needing <2 unassigned
// variables before a parity row can imply a unit/conflict; it is NOT a
// conventional moving two-watch data structure.
struct RowStats {
    int unknown = 0;
    int parity = 0;  // XOR of assigned variables whose value is true.
};

class DrnasBridge : public CaDiCaL::ExternalPropagator {
public:
    vector<XorRow> rows;
    vector<signed char> assigned;
    vector<int> trail;
    vector<size_t> marks;
    vector<int> outgoing;
    size_t send_index = 0;
    set<vector<int>> published;
    vector<vector<size_t>> reverse_index;
    vector<RowStats> stats;
    vector<unsigned char> queued;
    vector<size_t> dirty;
    size_t next_dirty = 0;
    long rows_scanned = 0, rows_enqueued = 0, empty_callbacks = 0;
    long row_updates = 0, row_literal_reads = 0, state_checks = 0;
    long notifications = 0, backtracks = 0, callbacks = 0, clauses_emitted = 0;
    long feasible_signals = 0;
    long ready_events = 0, unit_candidates = 0, conflict_candidates = 0;
    long no_unit_rows = 0, satisfied_rows = 0, duplicate_signals = 0;
    long telemetry_ticks = 0, telemetry_snapshots = 0;
    chrono::steady_clock::time_point heartbeat_origin=chrono::steady_clock::now();
    chrono::steady_clock::time_point heartbeat_last=heartbeat_origin;
    void heartbeat(bool force=false) {
        // Single CDCL thread snapshot (never read mutable counters on another thread).
        // 512-event throttle avoids introducing a clock query on every assignment.
        if(!force && ((++telemetry_ticks & 511L)!=0)) return;
        auto now=chrono::steady_clock::now();
        if(!force && chrono::duration<double>(now-heartbeat_last).count()<0.75) return;
        heartbeat_last=now;
        ++telemetry_snapshots;
        cerr<<"GF2CDCL_LIVE2_HEARTBEAT "
            <<"elapsed_ms="<<chrono::duration_cast<chrono::milliseconds>(now-heartbeat_origin).count()
            <<" xor_rows="<<rows.size()
            <<" assignments="<<notifications
            <<" backtracks="<<backtracks
            <<" live_callbacks="<<callbacks
            <<" row_updates="<<row_updates
            <<" rows_scanned="<<rows_scanned
            <<" rows_enqueued="<<rows_enqueued
            <<" ready_events="<<ready_events
            <<" unit_candidates="<<unit_candidates
            <<" conflict_candidates="<<conflict_candidates
            <<" no_unit_rows="<<no_unit_rows
            <<" satisfied_rows="<<satisfied_rows
            <<" live_signals="<<feasible_signals
            <<" duplicate_signals="<<duplicate_signals
            <<" clauses_emitted="<<clauses_emitted
            <<" source_unit_suppressed="<<source_unit_suppressed
            <<" source_unit_checks="<<source_unit_checks
            <<" budget_off="<<budget_off
            <<" disabled="<<disabled
            <<endl;
    }
    bool disabled = false;
    bool budget_off = false;
    bool emit_enabled = true;
    bool selective_gate = false;
    bool novelty_gate = false;
    long source_unit_suppressed = 0;
    long source_unit_checks = 0;
    vector<vector<int>> source_clauses;
    vector<vector<int>> occurrences;
    void load_original_clauses(const vector<vector<int>>& input) {
        source_clauses = input;
        occurrences.resize(assigned.size());
        for (size_t i=0;i<input.size();++i) {
            for (int lit:input[i]) if(abs(lit)>0 && abs(lit)<(int)assigned.size())
                occurrences[abs(lit)].push_back((int)i);
        }
    }
    // Skip an XOR implication only if an original CNF clause is already
    // unit with the same literal on this observed trail. This is a
    // conservative source-UP control, not a learned-clause novelty oracle.
    bool source_has_same_unit(int implied) {
        ++source_unit_checks;
        int v=abs(implied);
        if(v >= (int)occurrences.size() || occurrences[v].size()>512) return false;
        for(int ci:occurrences[v]){
            bool target=false, all_other_false=true;
            for(int l:source_clauses[ci]){
                if(l==implied){target=true;continue;}
                int w=abs(l);
                if(w<=0 || w>=(int)assigned.size()){all_other_false=false;break;}
                auto a=assigned[w];
                if(!a || ((a>0)==(l>0))){all_other_false=false;break;}
            }
            if(target && all_other_false) return true;
        }
        return false;
    }

    DrnasBridge(vector<XorRow> in, int n, bool emit, bool gate, bool novel):
        rows(std::move(in)), assigned(n+1,0), reverse_index(n+1),
        stats(rows.size()), queued(rows.size(),0),
        emit_enabled(emit), selective_gate(gate), novelty_gate(novel) {
        for (size_t i = 0; i < rows.size(); ++i) {
            stats[i].unknown = (int)rows[i].vars.size();
            for (int v : rows[i].vars) {
                if (v <= 0 || v > n) throw runtime_error("Invalid XOR variable");
                reverse_index[v].push_back(i);
            }
        }
    }

    // Both assignment and backtrack use the same reversible delta logic.
    // The counter is exact, so a row with >=2 unknowns cannot yield a unit.
    void on_value_change(int var, signed char old_val, signed char new_val) {
        if (disabled || budget_off) return;
        for (size_t idx : reverse_index[var]) {
            RowStats& st = stats[idx];
            int before_unknown = st.unknown;
            if (old_val == 0 && new_val != 0) --st.unknown;
            else if (old_val != 0 && new_val == 0) ++st.unknown;
            if (old_val == 1) st.parity ^= 1;
            if (new_val == 1) st.parity ^= 1;
            ++row_updates;
            if (old_val==0 && new_val!=0 && before_unknown>1 && st.unknown==1) ++ready_events;
            if (st.unknown < 0 || st.unknown > (int)rows[idx].vars.size()) {
                disabled = true; return;
            }

            // At least two unassigned variables => no unit/conflict yet.
            if (emit_enabled && (!selective_gate || st.unknown <= 1) && !queued[idx]) {
                queued[idx] = 1;
                dirty.push_back(idx);
                ++rows_enqueued;
            }

            // Only R96-C has an overhead safeguard; never changes the CNF
            // solver's logical correctness, merely stops XOR assistance.
            if (selective_gate && row_updates >= 250000 && clauses_emitted == 0) {
                budget_off = true;
                dirty.clear();
                next_dirty = 0;
                fill(queued.begin(), queued.end(), 0);
                return;
            }
        }
    }

    void notify_assignment(const vector<int>& lits) override {
        notifications += (long)lits.size();
        for (int lit : lits) {
            int var = abs(lit);
            if (var <= 0 || var >= (int)assigned.size()) {
                disabled = true; continue;
            }
            signed char value = lit > 0 ? 1 : -1;
            if (assigned[var] == value) continue;
            if (assigned[var] != 0) { disabled = true; continue; }
            assigned[var] = value;
            trail.push_back(lit);
            on_value_change(var, 0, value);
        }
        heartbeat();
    }
    void notify_new_decision_level() override { marks.push_back(trail.size()); }
    void notify_backtrack(size_t new_level) override {
        ++backtracks;
        if (new_level > marks.size()) { disabled = true; return; }
        while (marks.size() > new_level) {
            size_t start = marks.back();
            marks.pop_back();
            while (trail.size() > start) {
                int lit = trail.back(); trail.pop_back();
                int var = abs(lit);
                signed char old_val = assigned[var];
                assigned[var] = 0;
                on_value_change(var, old_val, 0);
            }
        }
        heartbeat();
    }
    bool cb_check_found_model(const vector<int>&) override { return true; }
    int cb_propagate() override { return 0; }

    bool cb_has_external_clause(bool& is_forgettable) override {
        is_forgettable = true;
        ++callbacks;
        heartbeat();
        if (!emit_enabled || disabled || budget_off ||
            clauses_emitted >= 64 || callbacks >= 60000) return false;
        if (!outgoing.empty()) return true;

        while (next_dirty < dirty.size()) {
            size_t idx = dirty[next_dirty++];
            queued[idx] = 0;
            const XorRow& row = rows[idx];
            const RowStats& st = stats[idx];
            ++rows_scanned;
            if (st.unknown > 1) { ++no_unit_rows; continue; }

            // Fail-closed consistency check is paid only for eligible rows.
            int unknown = 0, absent = 0, parity = 0;
            vector<int> clause;
            clause.reserve(row.vars.size());
            for (int v : row.vars) {
                if (v <= 0 || v >= (int)assigned.size()) {
                    disabled = true; return false;
                }
                ++row_literal_reads;
                int a = assigned[v];
                if (a == 0) { ++unknown; absent = v; }
                else {
                    parity ^= (a == 1);
                    clause.push_back(a == 1 ? -v : v);
                }
            }
            ++state_checks;
            if (unknown != st.unknown || parity != st.parity) {
                disabled = true;
                cerr << "R96_STATE_MISMATCH row=" << idx << "\n";
                return false;
            }
            if (unknown == 1) {
                ++unit_candidates;
                int implied = parity ^ row.rhs;
                int implied_lit=implied ? absent : -absent;
                if (novelty_gate && source_has_same_unit(implied_lit)) {
                    ++source_unit_suppressed;
                    continue;
                }
                clause.push_back(implied_lit);
            } else if (parity == row.rhs) { ++satisfied_rows; continue; }
            else ++conflict_candidates;
            if (clause.empty()) continue; // Keep R95's no-empty-clause guard.
            ++feasible_signals;
            sort(clause.begin(), clause.end(), [](int a, int b) {
                return abs(a)!=abs(b) ? abs(a)<abs(b) : a<b;
            });
            if (published.insert(clause).second) {
                outgoing = std::move(clause);
                send_index = 0;
                ++clauses_emitted;
                heartbeat(true);
                return true;
            }
            ++duplicate_signals;
        }
        dirty.clear();
        next_dirty = 0;
        ++empty_callbacks;
        return false;
    }
    int cb_add_external_clause_lit() override {
        if (send_index < outgoing.size()) return outgoing[send_index++];
        outgoing.clear(); send_index=0;
        return 0;
    }
};

static vector<vector<int>> load_cnf(const string& path, CaDiCaL::Solver& solver, int& n) {
    ifstream in(path);
    if (!in) throw runtime_error("CNF unreadable");
    string line;
    int expected = -1;
    vector<vector<int>> clauses;
    vector<int> pending;
    n = -1;
    while (getline(in,line)) {
        istringstream ss(line);
        string first;
        if (!(ss >> first) || first == "c") continue;
        if (first == "%") break;
        if (first == "p") {
            string fmt; ss >> fmt >> n >> expected;
            if (fmt != "cnf" || n <= 0 || n > 150000 || expected < 0 || expected > 160000)
                throw runtime_error("Invalid CNF header");
            continue;
        }
        if (n < 0) throw runtime_error("Missing CNF header");
        istringstream tokens(line);
        int lit;
        while (tokens >> lit) {
            if (abs(lit) > n) throw runtime_error("Invalid literal");
            solver.add(lit);
            if (lit) pending.push_back(lit);
            else {
                clauses.push_back(pending);
                pending.clear();
            }
        }
    }
    if (!pending.empty() || (int)clauses.size() != expected)
        throw runtime_error("Invalid DIMACS clause count");
    return clauses;
}

static vector<XorRow> load_rows(const string& filename, int n) {
    ifstream in(filename);
    if (!in) throw runtime_error("Missing independently certified XOR rows");
    string line;
    vector<XorRow> rows;
    while (getline(in,line)) {
        if (line.empty() || line[0] == '#') continue;
        istringstream ss(line);
        int k, rhs;
        if (!(ss >> k >> rhs) || k < 2 || k > 8 || (rhs != 0 && rhs != 1))
            throw runtime_error("Invalid XOR row");
        XorRow row; row.rhs = rhs;
        int v;
        for (int i=0;i<k;i++) {
            if (!(ss >> v) || v < 1 || v > n) throw runtime_error("Invalid XOR variable");
            row.vars.push_back(v);
        }
        if (ss >> v) throw runtime_error("Trailing XOR row data");
        sort(row.vars.begin(),row.vars.end());
        if (unique(row.vars.begin(),row.vars.end()) != row.vars.end())
            throw runtime_error("Repeated XOR variable");
        rows.push_back(std::move(row));
        if (rows.size() > 300) throw runtime_error("Too many XOR rows");
    }
    return rows;
}

int main(int argc, char** argv) {
    try {
        if (argc != 4 || (string(argv[1]) != "clean" && string(argv[1]) != "active" && string(argv[1]) != "monitor" && string(argv[1]) != "incremental" && string(argv[1]) != "novel")) {
            cerr << "usage: gf2cdcl_bridge clean|monitor|incremental|active|novel input.cnf certified_rows.tsv\n";
            return 2;
        }
        string mode = argv[1], source = argv[2], cert = argv[3];
        CaDiCaL::Solver solver;
        int n;
        auto clauses = load_cnf(source, solver, n);
        vector<XorRow> rows = (mode != "clean") ? load_rows(cert,n) : vector<XorRow>{};
        DrnasBridge bridge(std::move(rows), n,
            mode=="active" || mode=="incremental" || mode=="novel",
            mode=="active" || mode=="novel",
            mode=="novel");
        if(mode=="novel") bridge.load_original_clauses(clauses);
        if (mode != "clean" && !bridge.rows.empty()) {
            solver.connect_external_propagator(&bridge);
            set<int> observed;
            for (const auto& row : bridge.rows)
                for (int v : row.vars) observed.insert(v);
            for (int v : observed) solver.add_observed_var(v);
        }
        auto t0 = chrono::steady_clock::now();
        bridge.heartbeat(true);
        int result = solver.solve();
        bridge.heartbeat(true);
        double solve_s = chrono::duration<double>(chrono::steady_clock::now()-t0).count();
        if (result == 10) {
            for (const auto& clause : clauses) {
                bool satisfied = false;
                for (int lit : clause) {
                    int v = solver.val(abs(lit));
                    if (v && ((v>0) == (lit>0))) { satisfied=true; break; }
                }
                if (!satisfied) throw runtime_error("SAT model failed source CNF verification");
            }
        } else if (result != 20) throw runtime_error("unexpected unknown SAT result");
        cout << "GF2CDCL_LIVE2_RESULT status=" << (result==10?"SAT":"UNSAT")
             << " solve_s=" << solve_s
             << " xor_rows=" << bridge.rows.size()
             << " assignments=" << bridge.notifications
             << " backtracks=" << bridge.backtracks
             << " live_callbacks=" << bridge.callbacks
             << " live_signals=" << bridge.feasible_signals
             << " clauses_emitted=" << bridge.clauses_emitted
             << " ready_events=" << bridge.ready_events
             << " unit_candidates=" << bridge.unit_candidates
             << " conflict_candidates=" << bridge.conflict_candidates
             << " no_unit_rows=" << bridge.no_unit_rows
             << " satisfied_rows=" << bridge.satisfied_rows
             << " duplicate_signals=" << bridge.duplicate_signals
             << " telemetry_snapshots=" << bridge.telemetry_snapshots
             << " rows_scanned=" << bridge.rows_scanned
             << " rows_enqueued=" << bridge.rows_enqueued
             << " row_updates=" << bridge.row_updates
             << " row_literal_reads=" << bridge.row_literal_reads
             << " state_checks=" << bridge.state_checks
             << " budget_off=" << bridge.budget_off
             << " empty_callbacks=" << bridge.empty_callbacks
             << " source_unit_suppressed=" << bridge.source_unit_suppressed
             << " source_unit_checks=" << bridge.source_unit_checks
             << " disabled=" << bridge.disabled
             << " sat_model_checked=" << (result==10) << "\n";
        cout<<"s "<<(result==10?"SATISFIABLE":"UNSATISFIABLE")<<"\n";
        if(result==10){
            cout<<"v ";
            int printed=0;
            for(int i=1;i<=n;++i){
                int val=solver.val(i);
                if(val){cout<<val<<" ";if((++printed)%40==0)cout<<"0\nv ";}
            }
            cout<<"0\n";
        }
        return result;
    } catch (const exception& ex) {
        cerr << "R96_FAIL_CLOSED " << ex.what() << "\n";
        return 2;
    }
}
