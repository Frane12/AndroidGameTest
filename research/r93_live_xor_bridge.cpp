// DRNAS R93: experimental live CDCL <-> XOR clause communication (CaDiCaL IPASIR-UP).
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

class DrnasBridge : public CaDiCaL::ExternalPropagator {
public:
    vector<XorRow> rows;
    vector<signed char> assigned;
    vector<int> trail;
    vector<size_t> marks;
    vector<int> outgoing;
    size_t send_index = 0;
    set<vector<int>> published;
    long notifications = 0, backtracks = 0, callbacks = 0, clauses_emitted = 0;
    long feasible_signals = 0;
    bool disabled = false;

    DrnasBridge(vector<XorRow> in, int n): rows(std::move(in)), assigned(n+1,0) {}

    void notify_assignment(const vector<int>& lits) override {
        notifications += (long)lits.size();
        for (int lit : lits) {
            int var = abs(lit);
            if (var <= 0 || var >= (int)assigned.size()) {
                disabled = true;
                continue;
            }
            signed char value = lit > 0 ? 1 : -1;
            if (assigned[var] == value) continue;
            if (assigned[var] != 0) {
                disabled = true;
                continue;
            }
            assigned[var] = value;
            trail.push_back(lit);
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
                assigned[abs(lit)] = 0;
            }
        }
    }
    bool cb_check_found_model(const vector<int>&) override { return true; }
    int cb_propagate() override { return 0; }

    bool cb_has_external_clause(bool& is_forgettable) override {
        is_forgettable = true;
        if (disabled || clauses_emitted >= 64 || callbacks++ >= 60000) return false;
        if (!outgoing.empty()) return true;
        for (const XorRow& row: rows) {
            int unknown = 0, absent = 0, parity = 0;
            vector<int> clause;
            clause.reserve(row.vars.size());
            for (int v: row.vars) {
                if (v <= 0 || v >= (int)assigned.size()) { disabled=true; return false; }
                int a = assigned[v];
                if (a == 0) { unknown++; absent = v; }
                else {
                    parity ^= (a == 1);
                    clause.push_back(a == 1 ? -v : v);
                }
            }
            // Only emit when parity genuinely constrains the current CDCL trail.
            if (unknown > 1) continue;
            if (unknown == 1) {
                int implied = parity ^ row.rhs;
                clause.push_back(implied ? absent : -absent);
            } else if (parity == row.rhs) continue;
            if (clause.empty()) continue; // refuse unproved empty clause.
            ++feasible_signals;
            sort(clause.begin(),clause.end(),[](int a,int b) {
                return abs(a)!=abs(b) ? abs(a)<abs(b) : a<b;
            });
            if (published.insert(clause).second) {
                outgoing = std::move(clause);
                send_index = 0;
                ++clauses_emitted;
                return true;
            }
        }
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
        if (argc != 4 || (string(argv[1]) != "clean" && string(argv[1]) != "active")) {
            cerr << "usage: r93_bridge clean|active input.cnf certified_rows.tsv\n";
            return 2;
        }
        string mode = argv[1], source = argv[2], cert = argv[3];
        CaDiCaL::Solver solver;
        int n;
        auto clauses = load_cnf(source, solver, n);
        vector<XorRow> rows = (mode == "active") ? load_rows(cert,n) : vector<XorRow>{};
        DrnasBridge bridge(std::move(rows), n);
        if (mode == "active" && !bridge.rows.empty()) {
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
        cout << "R93_RESULT status=" << (result==10?"SAT":"UNSAT")
             << " solve_s=" << solve_s
             << " xor_rows=" << bridge.rows.size()
             << " assignments=" << bridge.notifications
             << " backtracks=" << bridge.backtracks
             << " live_callbacks=" << bridge.callbacks
             << " live_signals=" << bridge.feasible_signals
             << " clauses_emitted=" << bridge.clauses_emitted
             << " disabled=" << bridge.disabled
             << " sat_model_checked=" << (result==10) << "\n";
        return result;
    } catch (const exception& ex) {
        cerr << "R93_FAIL_CLOSED " << ex.what() << "\n";
        return 2;
    }
}
