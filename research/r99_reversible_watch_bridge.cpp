// DRNAS R99: reversible watch-move undo journal and event-indexed XOR with certified parity with certified full-row explanation of experimental live CDCL <-> XOR clause communication (CaDiCaL IPASIR-UP).
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

// R99: certified full-row parity explanations, assignment-only watch lists,
// with O(changes-made) LIFO rollback instead of scanning incidences on undo.
class DrnasBridge : public CaDiCaL::ExternalPropagator {
public:
    vector<XorRow> rows;
    vector<signed char> assigned;
    vector<int> trail;
    vector<size_t> marks;
    vector<int> outgoing;
    size_t send_index = 0;
    set<vector<int>> published;
    struct WatchRef { size_t row; unsigned generation; };
    vector<vector<WatchRef>> watch_index;
    vector<int> watch_a, watch_b;
    vector<size_t> scan_cursor;
    struct WatchUndo { size_t row; bool slot_a; int old_var; };
    vector<WatchUndo> watch_history;
    vector<size_t> watch_history_marks;
    vector<unsigned> generation_a, generation_b;
    vector<unsigned char> queued;
    vector<size_t> dirty;
    size_t next_dirty = 0;
    long rows_scanned = 0, rows_enqueued = 0, empty_callbacks = 0;
    long row_updates = 0, row_literal_reads = 0, state_checks = 0;
    long watch_lookups = 0, watch_literal_probes = 0, watch_replacements = 0;
    long watch_backtrack_repairs = 0;
    long assignment_events = 0, undo_incidence_visits = 0, stale_watch_refs = 0;
    long undo_journal_actions = 0, undo_events = 0, max_history = 0;
    long notifications = 0, backtracks = 0, callbacks = 0, clauses_emitted = 0;
    long feasible_signals = 0;
    bool disabled = false;
    bool budget_off = false;
    bool emit_enabled = true;
    bool selective_gate = false;
    int max_emit_width = 0;
    long selective_rejected = 0;

    DrnasBridge(vector<XorRow> in, int n, bool emit, bool gate, int width=0):
        rows(std::move(in)), assigned(n+1,0), watch_index(n+1), watch_a(rows.size()), watch_b(rows.size()),
        generation_a(rows.size(),1), generation_b(rows.size(),1), scan_cursor(rows.size(),0), queued(rows.size(),0),
        emit_enabled(emit), selective_gate(gate), max_emit_width(width) {
        for (size_t i = 0; i < rows.size(); ++i) {
            if (rows[i].vars.size() < 2) throw runtime_error("XOR watch arity < 2");
            watch_a[i] = rows[i].vars[0];
            watch_b[i] = rows[i].vars[1];
            for (int v : rows[i].vars)
                if (v <= 0 || v > n) throw runtime_error("Invalid XOR variable");
            watch_index[watch_a[i]].push_back({i,generation_a[i]});
            watch_index[watch_b[i]].push_back({i,generation_b[i]});
        }
    }

    // Only current watched-variable events are processed on assignment.
    // Every watch move has one rollback record; all are reverted in exact
    // reverse assignment order. Backtracking never scans reverse incidences.
    // Rows still require a complete parity rebuild to publish a clause.
    void enqueue_ready(size_t idx) {
        if (!queued[idx]) {
            queued[idx] = 1;
            dirty.push_back(idx);
            ++rows_enqueued;
        }
    }
    void on_value_change(int var, signed char old_val, signed char new_val) {
        if (!emit_enabled || disabled || budget_off) return;
        if (old_val != 0 || new_val == 0) { disabled = true; return; }
        ++assignment_events;
        auto& refs = watch_index[var];
        // R100: bound accumulated stale watch references without changing
        // any current watch or undo-journal entry. Compaction is deliberately
        // local to the notified bucket, and is never used as a correctness gate.
        if (refs.size() >= 32) {
            size_t live = 0;
            for (const WatchRef& ref : refs) {
                if (ref.row >= rows.size()) { disabled = true; return; }
                const bool a = watch_a[ref.row] == var &&
                               generation_a[ref.row] == ref.generation;
                const bool b = watch_b[ref.row] == var &&
                               generation_b[ref.row] == ref.generation;
                if (a && b) { disabled = true; return; }
                live += (a || b);
            }
            if (live * 2 <= refs.size()) {
                refs.erase(remove_if(refs.begin(), refs.end(),
                    [&](const WatchRef& ref) {
                        return !((watch_a[ref.row] == var &&
                                  generation_a[ref.row] == ref.generation) ||
                                 (watch_b[ref.row] == var &&
                                  generation_b[ref.row] == ref.generation));
                    }), refs.end());
            }
        }
        size_t kept = 0;
        const size_t sz = refs.size();
        for (size_t k=0; k<sz; ++k) {
            WatchRef ref = refs[k];
            const size_t idx = ref.row;
            if (idx >= rows.size()) { disabled=true; return; }
            bool is_a = watch_a[idx] == var && generation_a[idx] == ref.generation;
            bool is_b = watch_b[idx] == var && generation_b[idx] == ref.generation;
            if (!is_a && !is_b) { ++stale_watch_refs; continue; }
            if (is_a && is_b) { disabled=true; return; }
            ++watch_lookups;
            int other = is_a ? watch_b[idx] : watch_a[idx];
            int replacement = 0;
            // R101: rotate the starting point after each successful watch
            // relocation. We still examine the COMPLETE row if needed, so
            // the invariant and fail-closed behavior are unchanged.
            const auto& vars = rows[idx].vars;
            const size_t count = vars.size();
            for (size_t probe = 0; probe < count; ++probe) {
                const size_t pos = (scan_cursor[idx] + probe) % count;
                const int v = vars[pos];
                ++watch_literal_probes;
                if (v != other && assigned[v] == 0) {
                    replacement = v;
                    scan_cursor[idx] = (pos + 1) % count;
                    break;
                }
            }
            if (replacement != 0) {
                watch_history.push_back({idx,is_a,var});
                if ((long)watch_history.size()>max_history)
                    max_history=(long)watch_history.size();
                if (is_a) {
                    watch_a[idx] = replacement;
                    ++generation_a[idx];
                    watch_index[replacement].push_back({idx,generation_a[idx]});
                } else {
                    watch_b[idx] = replacement;
                    ++generation_b[idx];
                    watch_index[replacement].push_back({idx,generation_b[idx]});
                }
                ++watch_replacements; ++row_updates;
            } else {
                enqueue_ready(idx);
                refs[kept++] = ref;
            }
            if (selective_gate && watch_lookups >= 250000 &&
                clauses_emitted == 0) {
                budget_off = true;
                dirty.clear();
                next_dirty = 0;
                fill(queued.begin(),queued.end(),0);
                return;
            }
        }
        refs.resize(kept);
    }
    void rewind_watches_to(size_t history_start) {
        if (history_start > watch_history.size()) {
            disabled=true; return;
        }
        while (watch_history.size()>history_start) {
            WatchUndo u = watch_history.back();
            watch_history.pop_back();
            if (u.row >= rows.size() ||
                u.old_var <= 0 || u.old_var >= (int)assigned.size()) {
                disabled=true; return;
            }
            if (u.slot_a) {
                watch_a[u.row] = u.old_var;
                ++generation_a[u.row];
                watch_index[u.old_var].push_back({u.row,generation_a[u.row]});
            } else {
                watch_b[u.row] = u.old_var;
                ++generation_b[u.row];
                watch_index[u.old_var].push_back({u.row,generation_b[u.row]});
            }
            ++undo_journal_actions;
        }
    }

    static void watch_selftest() {
        unsigned seed = 0x91837abU;
        auto rnd = [&]() -> unsigned {
            seed ^= seed << 13; seed ^= seed >> 17; seed ^= seed << 5;
            return seed;
        };
        const int n = 16;
        vector<XorRow> sample;
        for (int i = 0; i < 72; ++i) {
            XorRow r;
            int len = 2 + (int)(rnd() % 7);
            while ((int)r.vars.size() < len) {
                int v = 1 + (int)(rnd()%n);
                if (find(r.vars.begin(),r.vars.end(),v) == r.vars.end()) r.vars.push_back(v);
            }
            r.rhs = (int)(rnd() & 1);
            sample.push_back(std::move(r));
        }
        DrnasBridge bridge(std::move(sample),n,true,true);
        long backtrack_levels = 0, assignments = 0, assertions = 0;
        auto verify = [&]() {
            for (size_t i=0;i<bridge.rows.size();++i) {
                int u=0;
                for (int v:bridge.rows[i].vars) u+=(bridge.assigned[v]==0);
                if (u>=2 && (bridge.watch_a[i]==bridge.watch_b[i] ||
                    bridge.assigned[bridge.watch_a[i]]!=0 ||
                    bridge.assigned[bridge.watch_b[i]]!=0))
                    throw runtime_error("R98_WATCH_COVERAGE_FAIL");
                if (u<=1 && !bridge.queued[i])
                    throw runtime_error("R98_MISSING_READY_NOTIFICATION");
                ++assertions;
            }
            for (size_t i=0;i<bridge.rows.size();++i) {
                auto has_current=[&](int v,unsigned gen) {
                    for (auto e:bridge.watch_index[v])
                        if (e.row==i && e.generation==gen) return true;
                    return false;
                };
                if (!has_current(bridge.watch_a[i],bridge.generation_a[i]) ||
                    !has_current(bridge.watch_b[i],bridge.generation_b[i]))
                    throw runtime_error("R99_WATCH_REF_MISSING");
            }
            if (bridge.disabled || bridge.budget_off)
                throw runtime_error("R99_UNEXPECTED_DISABLE");
        };
        verify();
        for (int step=0;step<3200;++step) {
            vector<int> free;
            for (int v=1;v<=n;++v) if (bridge.assigned[v]==0) free.push_back(v);
            if (!bridge.marks.empty() && (free.empty() || rnd()%5==0)) {
                size_t level = (size_t)(rnd()%bridge.marks.size());
                backtrack_levels += (long)(bridge.marks.size()-level);
                bridge.notify_backtrack(level);
            } else if (!free.empty()) {
                int v=free[rnd()%free.size()];
                bridge.notify_new_decision_level();
                bridge.notify_assignment({rnd()%2 ? v : -v});
                ++assignments;
            }
            verify();
        }
        if (!bridge.marks.empty()) bridge.notify_backtrack(0);
        verify();
        if (!bridge.watch_history.empty() || !bridge.watch_history_marks.empty())
            throw runtime_error("R99_UNDRAINED_UNDO_JOURNAL");
        if (assignments<100 || backtrack_levels<100 ||
            bridge.watch_replacements<100 || bridge.undo_journal_actions<100 ||
            assertions<100000)
            throw runtime_error("R99_SELFTEST_INSUFFICIENT_EVENTS");
        cout << "R99_WATCH_SELFTEST_PASS assignments=" << assignments
             << " undo_levels=" << backtrack_levels
             << " watch_hits=" << bridge.watch_lookups
             << " replacements=" << bridge.watch_replacements
             << " stale=" << bridge.stale_watch_refs
             << " backtrack_visits=" << bridge.undo_incidence_visits
             << " undo_journal_actions=" << bridge.undo_journal_actions
             << " invariants=" << assertions << "\n";
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
            watch_history_marks.push_back(watch_history.size());
            on_value_change(var, 0, value);
        }
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
                if (watch_history_marks.empty()) { disabled = true; return; }
                size_t saved = watch_history_marks.back();
                watch_history_marks.pop_back();
                assigned[var] = 0;
                rewind_watches_to(saved);
                ++undo_events;
                if (disabled) return;
            }
        }
    }
    bool cb_check_found_model(const vector<int>&) override { return true; }
    int cb_propagate() override { return 0; }

    bool cb_has_external_clause(bool& is_forgettable) override {
        is_forgettable = true;
        ++callbacks;
        if (!emit_enabled || disabled || budget_off ||
            clauses_emitted >= 64 || callbacks >= 60000) return false;
        if (!outgoing.empty()) return true;

        while (next_dirty < dirty.size()) {
            size_t idx = dirty[next_dirty++];
            queued[idx] = 0;
            const XorRow& row = rows[idx];
            ++rows_scanned;
            // This queued event can become stale after backtracking.
            if (assigned[watch_a[idx]] == 0 && assigned[watch_b[idx]] == 0)
                continue;

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
            if (unknown > 1) {
                disabled = true;
                cerr << "R99_WATCH_INVARIANT row=" << idx << "\n";
                return false;
            }
            if (unknown == 1) {
                int implied = parity ^ row.rhs;
                clause.push_back(implied ? absent : -absent);
            } else if (parity == row.rhs) continue;
            if (clause.empty()) continue; // Keep R95's no-empty-clause guard.
            ++feasible_signals;
            sort(clause.begin(), clause.end(), [](int a, int b) {
                return abs(a)!=abs(b) ? abs(a)<abs(b) : a<b;
            });
            if (max_emit_width && (int)clause.size() > max_emit_width) {
                ++selective_rejected;
                continue;
            }
            if (published.insert(clause).second) {
                outgoing = std::move(clause);
                send_index = 0;
                ++clauses_emitted;
                return true;
            }
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
        if (argc==2 && string(argv[1])=="selftest") {
            DrnasBridge::watch_selftest();
            return 0;
        }
        if (argc != 4 || (string(argv[1]) != "clean" && string(argv[1]) != "active" && string(argv[1]) != "monitor" && string(argv[1]) != "incremental" && string(argv[1]) != "select3" && string(argv[1]) != "select4")) {
            cerr << "usage: r96_bridge clean|monitor|incremental|active input.cnf certified_rows.tsv\n";
            return 2;
        }
        string mode = argv[1], source = argv[2], cert = argv[3];
        CaDiCaL::Solver solver;
        int n;
        auto clauses = load_cnf(source, solver, n);
        vector<XorRow> rows = (mode != "clean") ? load_rows(cert,n) : vector<XorRow>{};
        DrnasBridge bridge(std::move(rows), n, mode == "active" || mode == "incremental" || mode == "select3" || mode == "select4", mode == "active", mode == "select3" ? 3 : mode == "select4" ? 4 : 0);
        if (mode != "clean" && !bridge.rows.empty()) {
            solver.connect_external_propagator(&bridge);
            set<int> observed;
            for (const auto& row : bridge.rows)
                for (int v : row.vars) observed.insert(v);
            for (int v : observed) solver.add_observed_var(v);
        }
        auto t0 = chrono::steady_clock::now();
        int result = solver.solve();
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
        cout << "R99_RESULT status=" << (result==10?"SAT":"UNSAT")
             << " solve_s=" << solve_s
             << " xor_rows=" << bridge.rows.size()
             << " assignments=" << bridge.notifications
             << " backtracks=" << bridge.backtracks
             << " live_callbacks=" << bridge.callbacks
             << " live_signals=" << bridge.feasible_signals
             << " clauses_emitted=" << bridge.clauses_emitted
             << " selective_rejected=" << bridge.selective_rejected
             << " rows_scanned=" << bridge.rows_scanned
             << " rows_enqueued=" << bridge.rows_enqueued
             << " watch_lookups=" << bridge.watch_lookups
             << " watch_literal_probes=" << bridge.watch_literal_probes
             << " watch_replacements=" << bridge.watch_replacements
             << " watch_backtrack_repairs=" << bridge.watch_backtrack_repairs
             << " assignment_events=" << bridge.assignment_events
             << " undo_incidence_visits=" << bridge.undo_incidence_visits
             << " undo_journal_actions=" << bridge.undo_journal_actions
             << " undo_events=" << bridge.undo_events
             << " max_history=" << bridge.max_history
             << " stale_watch_refs=" << bridge.stale_watch_refs
             << " row_updates=" << bridge.row_updates
             << " row_literal_reads=" << bridge.row_literal_reads
             << " state_checks=" << bridge.state_checks
             << " budget_off=" << bridge.budget_off
             << " empty_callbacks=" << bridge.empty_callbacks
             << " disabled=" << bridge.disabled
             << " sat_model_checked=" << (result==10) << "\n";
        return result;
    } catch (const exception& ex) {
        cerr << "R99_FAIL_CLOSED " << ex.what() << "\n";
        return 2;
    }
}
