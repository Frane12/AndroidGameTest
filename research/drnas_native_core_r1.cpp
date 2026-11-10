// DRNAS Native Core R1 — original self-contained CDCL SAT solver.
// Copyright (c) 2026 Frane Drnas. All rights reserved.
// Does NOT link to Kissat, CaDiCaL, CryptoMiniSat, or another SAT solver.
// DIMACS -> watched-literal BCP -> 1-UIP learning -> nonchronological backtrack
// -> activity-based branching -> restarts -> SAT, UNSAT or resource-limited UNKNOWN.
// UNSAT proof logging is NOT implemented; independently validate UNSAT externally.
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <random>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace drnas {
using Clock = std::chrono::steady_clock;
struct CNF {
    int vars = 0;
    std::vector<std::vector<int>> clauses;
};
static void require(bool ok, const std::string& message) {
    if (!ok) throw std::runtime_error(message);
}
static CNF read_dimacs(const std::string& filename) {
    std::ifstream file(filename);
    require(bool(file), "cannot open original CNF file");
    CNF f;
    std::string word;
    bool header = false;
    size_t declared = 0;
    std::vector<int> current;
    while (file >> word) {
        if (word == "c") { std::string comment; std::getline(file, comment); continue; }
        if (word == "p") {
            require(!header, "duplicate DIMACS header");
            std::string fmt;
            file >> fmt >> f.vars >> declared;
            require(bool(file) && fmt == "cnf" && f.vars >= 0 && f.vars <= 1000000,
                    "invalid or excessive DIMACS header");
            require(declared <= 10000000, "excessive DIMACS clause count");
            header = true;
            continue;
        }
        require(header, "DIMACS clause before header");
        size_t used = 0;
        long long num = 0;
        try { num = std::stoll(word, &used); }
        catch (...) { throw std::runtime_error("invalid integer in original DIMACS"); }
        require(used == word.size() && num >= -f.vars && num <= f.vars,
                "literal out of DIMACS declared range");
        if (!num) {
            f.clauses.push_back(std::move(current));
            current.clear();
            require(f.clauses.size() <= declared, "extra DIMACS clause");
        } else {
            current.push_back(static_cast<int>(num));
            require(current.size() <= 2000000, "excessively long DIMACS clause");
        }
    }
    require(header && current.empty() && f.clauses.size() == declared,
            "missing terminator or DIMACS clause count mismatch");
    return f;
}

struct Clause {
    std::vector<int> lits;
    bool learned = false;
};
struct Statistics {
    uint64_t conflicts = 0, decisions = 0, propagations = 0;
    uint64_t watch_visits = 0, learned_clauses = 0, restarts = 0;
};
class NativeCDCL {
    const int n_;
    std::vector<Clause> clauses_;
    std::vector<std::vector<int>> watches_;
    std::vector<int8_t> values_, phases_;
    std::vector<int> levels_, reasons_, trail_;
    std::vector<size_t> decision_marks_;
    std::vector<double> activity_;
    size_t propagation_head_ = 0;
    bool root_contradiction_ = false;
    double bump_ = 1.0, decay_ = 0.95;
    uint64_t next_restart_ = 100, restart_window_ = 100;
    Clock::time_point start_;
    double cap_s_ = 10.0;
    bool resource_limit_ = false;
    Statistics stats_;

    static int var(int lit) { return std::abs(lit); }
    static int watch_index(int lit) {
        return 2 * (std::abs(lit) - 1) + (lit < 0 ? 1 : 0);
    }
    int level() const { return static_cast<int>(decision_marks_.size()); }
    int lit_value(int lit) const {
        int value = values_[var(lit)];
        return lit > 0 ? value : -value;
    }
    bool enqueue(int lit, int from_clause) {
        int v = var(lit);
        int8_t desired = lit > 0 ? 1 : -1;
        if (values_[v]) return values_[v] == desired;
        values_[v] = desired;
        phases_[v] = desired;
        levels_[v] = level();
        reasons_[v] = from_clause;
        trail_.push_back(lit);
        return true;
    }
    void attach(int index) {
        const auto& c = clauses_[index].lits;
        if (c.size() >= 2) {
            watches_[watch_index(c[0])].push_back(index);
            watches_[watch_index(c[1])].push_back(index);
        }
    }
    void bump_variable(int v) {
        activity_[v] += bump_;
        if (activity_[v] > 1e100) {
            for (int i = 1; i <= n_; ++i) activity_[i] *= 1e-100;
            bump_ *= 1e-100;
        }
    }
    bool timed_out() const {
        return std::chrono::duration<double>(Clock::now() - start_).count() >= cap_s_;
    }
    // Watch the two front literals in each nonunit clause. Every original or
    // learned clause is stored explicitly, not outsourced to any solver.
    // Return -1: no conflict; -2: timed out; otherwise conflicting clause ID.
    int propagate() {
        while (propagation_head_ < trail_.size()) {
            if ((stats_.propagations & 1023ULL) == 0 && timed_out()) return -2;
            const int true_lit = trail_[propagation_head_++];
            ++stats_.propagations;
            auto& list = watches_[watch_index(-true_lit)];
            size_t read = 0, write = 0;
            while (read < list.size()) {
                const int cid = list[read++];
                ++stats_.watch_visits;
                auto& clause = clauses_[cid].lits;
                require(clause.size() >= 2, "broken watch on unit clause");
                if (clause[0] == -true_lit) std::swap(clause[0], clause[1]);
                require(clause[1] == -true_lit, "watch invariant violated");
                if (lit_value(clause[0]) == 1) {
                    list[write++] = cid;
                    continue;
                }
                size_t candidate = clause.size();
                for (size_t k = 2; k < clause.size(); ++k) {
                    if (lit_value(clause[k]) != -1) { candidate = k; break; }
                }
                if (candidate != clause.size()) {
                    std::swap(clause[1], clause[candidate]);
                    watches_[watch_index(clause[1])].push_back(cid);
                    continue;
                }
                list[write++] = cid;
                if (lit_value(clause[0]) == -1 || !enqueue(clause[0], cid)) {
                    // The remaining watcher IDs must stay installed even when
                    // propagation exits early on this conflict.
                    while (read < list.size()) list[write++] = list[read++];
                    list.resize(write);
                    return cid;
                }
            }
            list.resize(write);
        }
        return -1;
    }
    void cancel_to(int target_level) {
        if (level() <= target_level) return;
        require(target_level >= 0, "negative backtrack level");
        const size_t target = decision_marks_[target_level];
        for (size_t i = trail_.size(); i > target; --i) {
            const int v = var(trail_[i - 1]);
            values_[v] = 0;
            reasons_[v] = -1;
            levels_[v] = 0;
        }
        trail_.resize(target);
        decision_marks_.resize(target_level);
        propagation_head_ = std::min(propagation_head_, target);
    }
    // Resolve the conflict with reasons until precisely one literal comes
    // from the current decision level: the asserting 1-UIP clause.
    std::pair<std::vector<int>, int> analyze(int conflict) {
        std::vector<uint8_t> seen(n_ + 1, 0);
        std::vector<int> learned(1, 0);
        int pending = 0, resolved_lit = 0;
        size_t reverse_pos = trail_.size();
        do {
            require(conflict >= 0 && conflict < static_cast<int>(clauses_.size()),
                    "broken conflict reason in 1-UIP");
            for (int lit : clauses_[conflict].lits) {
                const int v = var(lit);
                if (v == var(resolved_lit) || seen[v] || levels_[v] == 0) continue;
                seen[v] = 1;
                bump_variable(v);
                if (levels_[v] == level()) ++pending;
                else learned.push_back(lit);
            }
            require(pending > 0, "1-UIP has no current-level conflict path");
            do {
                require(reverse_pos > 0, "1-UIP trail unexpectedly exhausted");
                resolved_lit = trail_[--reverse_pos];
            } while (!seen[var(resolved_lit)]);
            seen[var(resolved_lit)] = 0;
            --pending;
            if (pending) conflict = reasons_[var(resolved_lit)];
        } while (pending);
        learned[0] = -resolved_lit;
        int backtrack_level = 0;
        if (learned.size() >= 2) {
            size_t best = 1;
            for (size_t i = 2; i < learned.size(); ++i) {
                if (levels_[var(learned[i])] > levels_[var(learned[best])])
                    best = i;
            }
            std::swap(learned[1], learned[best]);
            backtrack_level = levels_[var(learned[1])];
        }
        return {std::move(learned), backtrack_level};
    }
    int pick_branch_variable() const {
        int selected = 0;
        double best = -1;
        for (int v = 1; v <= n_; ++v) {
            if (values_[v] == 0 && activity_[v] > best) {
                best = activity_[v];
                selected = v;
            }
        }
        return selected;
    }

public:
    explicit NativeCDCL(int n) : n_(n), watches_(size_t(n) * 2),
          values_(n + 1, 0), phases_(n + 1, 1),
          levels_(n + 1, 0), reasons_(n + 1, -1),
          activity_(n + 1, 0) {
        require(n >= 0 && n <= 1000000, "invalid SAT variable count");
    }
    void add_original(const std::vector<int>& input) {
        require(trail_.size() == 0 || level() == 0,
                "input clauses can only be added at decision level zero");
        if (root_contradiction_) return;
        std::vector<int> lits = input;
        std::sort(lits.begin(), lits.end(), [](int a, int b) {
            return var(a) < var(b) || (var(a) == var(b) && a < b);
        });
        std::vector<int> normal;
        for (int lit : lits) {
            require(lit && var(lit) <= n_, "original literal outside declared range");
            if (!normal.empty() && var(normal.back()) == var(lit)) {
                if (normal.back() != lit) return;  // exact tautology: ignore clause
                continue;                          // identical duplicate literal
            }
            normal.push_back(lit);
        }
        if (normal.empty()) { root_contradiction_ = true; return; }
        for (int lit : normal) activity_[var(lit)] += 1.0;
        const int cid = static_cast<int>(clauses_.size());
        clauses_.push_back({std::move(normal), false});
        attach(cid);
        if (clauses_[cid].lits.size() == 1 &&
            !enqueue(clauses_[cid].lits[0], cid)) root_contradiction_ = true;
    }
    void add_cnf(const CNF& cnf) {
        require(n_ == cnf.vars, "input variable count drift");
        for (const auto& clause : cnf.clauses) add_original(clause);
    }
    int solve(double time_limit_s) {
        require(std::isfinite(time_limit_s) && time_limit_s > 0,
                "positive time limit required");
        cap_s_ = time_limit_s;
        start_ = Clock::now();
        if (root_contradiction_) return 20;
        while (true) {
            if (timed_out()) return 0;
            if (clauses_.size() > 1500000 || stats_.learned_clauses > 500000) {
                resource_limit_ = true;
                return 0;
            }
            const int conflicting = propagate();
            if (conflicting == -2) return 0;
            if (conflicting >= 0) {
                ++stats_.conflicts;
                if (level() == 0) return 20;
                auto [learned, target] = analyze(conflicting);
                cancel_to(target);
                const int cid = static_cast<int>(clauses_.size());
                const int assertion = learned[0];
                clauses_.push_back({std::move(learned), true});
                attach(cid);
                ++stats_.learned_clauses;
                require(enqueue(assertion, cid), "learned 1-UIP clause not asserting");
                bump_ /= decay_;
                if (stats_.conflicts >= next_restart_ && level() > 0) {
                    cancel_to(0);
                    ++stats_.restarts;
                    restart_window_ = std::min<uint64_t>(restart_window_ * 3 / 2 + 1,
                                                          30000);
                    next_restart_ = stats_.conflicts + restart_window_;
                }
            } else {
                const int v = pick_branch_variable();
                if (!v) return 10;
                ++stats_.decisions;
                decision_marks_.push_back(trail_.size());
                require(enqueue(phases_[v] >= 0 ? v : -v, -1),
                        "selected decision variable was already assigned");
            }
        }
    }
    const Statistics& statistics() const { return stats_; }
    bool hit_resource_limit() const { return resource_limit_; }
    double solve_elapsed_s() const {
        return std::chrono::duration<double>(Clock::now() - start_).count();
    }
    const std::vector<int8_t>& assignments() const { return values_; }
    bool verify_original(const CNF& cnf) const {
        require(cnf.vars == n_, "model validation on different original CNF");
        for (const auto& clause : cnf.clauses) {
            bool satisfied = false;
            for (int lit : clause) if (lit_value(lit) == 1) { satisfied = true; break; }
            if (!satisfied) return false;
        }
        return true;
    }
};

// These correctness tests enumerate every assignment of small CNFs and compare
// to the independently computed SAT truth table; no external solver runs.
static bool brute_sat(const CNF& f) {
    require(f.vars <= 15 && f.vars >= 0, "brute SAT intended for small CNF only");
    for (unsigned mask = 0; mask < (1u << f.vars); ++mask) {
        bool all = true;
        for (const auto& clause : f.clauses) {
            bool sat = false;
            for (int lit : clause) {
                bool value = bool(mask & (1u << (std::abs(lit) - 1)));
                if (value == (lit > 0)) { sat = true; break; }
            }
            if (!sat) { all = false; break; }
        }
        if (all) return true;
    }
    return false;
}
static CNF pigeonhole(int pigeons, int holes) {
    CNF f;
    f.vars = pigeons * holes;
    auto cell = [holes](int p, int h) { return p * holes + h + 1; };
    for (int p = 0; p < pigeons; ++p) {
        std::vector<int> at_least_one;
        for (int h = 0; h < holes; ++h) at_least_one.push_back(cell(p, h));
        f.clauses.push_back(at_least_one);
    }
    for (int h = 0; h < holes; ++h)
        for (int a = 0; a < pigeons; ++a)
            for (int b = a + 1; b < pigeons; ++b)
                f.clauses.push_back({-cell(a, h), -cell(b, h)});
    return f;
}
static void selftest() {
    std::mt19937 rng(0xD123A71u);
    unsigned checked = 0, verified_sat = 0, verified_unsat = 0;
    const auto one = [&](const CNF& f) {
        NativeCDCL s(f.vars);
        s.add_cnf(f);
        int got = s.solve(12.0);
        bool expected = brute_sat(f);
        require(got == (expected ? 10 : 20), "R1 exhaustive status disagreement");
        if (expected) {
            require(s.verify_original(f), "R1 produced invalid original SAT assignment");
            ++verified_sat;
        } else ++verified_unsat;
        ++checked;
    };
    one({0, {}});      // vacuously SAT
    one({1, {{}}});    // empty clause UNSAT
    one({1, {{1}, {-1}}});
    one({2, {{1, -1}, {-2, -2}, {2}}});
    one({3, {{1, 2, 3}, {-1, -2, 3}, {1, -3}}});
    one(pigeonhole(3, 2));
    one(pigeonhole(4, 3));
    // All eight 3-variable assignments forbidden: strict UNSAT conflict tree.
    CNF all_forbidden;
    all_forbidden.vars = 3;
    for (unsigned m = 0; m < 8; ++m) {
        std::vector<int> c;
        for (int v = 1; v <= 3; ++v)
            c.push_back((m & (1u << (v - 1))) ? -v : v);
        all_forbidden.clauses.push_back(std::move(c));
    }
    one(all_forbidden);
    // Many generated formulas contain unit clauses, duplicates, tautologies,
    // arbitrary long clauses, and conflicting paths.
    for (int n = 1; n <= 9; ++n) {
        for (int sample = 0; sample < 90; ++sample) {
            CNF f; f.vars = n;
            const int count = 1 + int(rng() % (4 * n + 3));
            for (int k = 0; k < count; ++k) {
                const int width = int(rng() % (n + 4));
                std::vector<int> clause;
                for (int j = 0; j < width; ++j) {
                    const int v = int(rng() % unsigned(n)) + 1;
                    clause.push_back((rng() & 1u) ? v : -v);
                }
                f.clauses.push_back(std::move(clause));
            }
            one(f);
        }
    }
    std::cout << "DRNAS_NATIVE_R1_SELFTEST_PASS cases=" << checked
              << " independently_bruteforced_sat=" << verified_sat
              << " independently_bruteforced_unsat=" << verified_unsat
              << " external_solver_dependencies=0\n";
}
}  // namespace drnas

int main(int argc, char** argv) {
    try {
        if (argc == 2 && std::string(argv[1]) == "--selftest") {
            drnas::selftest();
            return 0;
        }
        if (!(argc == 4 && std::string(argv[2]) == "--time")) {
            std::cerr << "Usage: drnas-native-core-r1 FORMULA.cnf --time SECONDS\n"
                      << "       drnas-native-core-r1 --selftest\n";
            return 2;
        }
        double seconds = std::stod(argv[3]);
        drnas::require(seconds > 0 && seconds <= 3600 && std::isfinite(seconds),
                       "time cap must be 0 < seconds <= 3600");
        const auto overall_start = drnas::Clock::now();
        const auto input = drnas::read_dimacs(argv[1]);
        const auto parse_s = std::chrono::duration<double>(
            drnas::Clock::now() - overall_start).count();
        drnas::NativeCDCL solver(input.vars);
        solver.add_cnf(input);
        double remaining = seconds - std::chrono::duration<double>(
            drnas::Clock::now() - overall_start).count();
        int status = remaining > 0 ? solver.solve(remaining) : 0;
        if (status == 10) {
            drnas::require(solver.verify_original(input),
                           "invalid original CNF SAT model, refuse SAT");
        }
        const auto e2e_s = std::chrono::duration<double>(
            drnas::Clock::now() - overall_start).count();
        std::cout << std::fixed << std::setprecision(6);
        const auto& s = solver.statistics();
        std::cout << "c DRNAS_NATIVE_R1_RESULT status="
                  << (status == 10 ? "SAT" : status == 20 ? "UNSAT" : "UNKNOWN")
                  << " solver_s=" << (remaining > 0 ? solver.solve_elapsed_s() : 0)
                  << " e2e_s=" << e2e_s << " input_parse_s=" << parse_s
                  << " conflicts=" << s.conflicts << " decisions=" << s.decisions
                  << " propagations=" << s.propagations
                  << " learned=" << s.learned_clauses
                  << " restarts=" << s.restarts
                  << " watch_visits=" << s.watch_visits
                  << " resource_limited=" << int(solver.hit_resource_limit())
                  << " original_model_checked=" << int(status == 10)
                  << " UNSAT_independent_LRAT=0"
                  << " third_party_solver_calls=0\n";
        if (status == 10) {
            std::cout << "s SATISFIABLE\nv ";
            const auto& model = solver.assignments();
            for (int v = 1; v <= input.vars; ++v) {
                std::cout << (model[v] == -1 ? -v : v) << " ";
                if (v % 30 == 0) std::cout << "0\nv ";
            }
            std::cout << "0\n";
        } else if (status == 20) std::cout << "s UNSATISFIABLE\n";
        else std::cout << "s UNKNOWN\n";
        return status == 10 ? 10 : status == 20 ? 20 : 0;
    } catch (const std::exception& e) {
        std::cerr << "DRNAS_NATIVE_R1_FAIL_CLOSED " << e.what() << "\n";
        return 2;
    }
}
