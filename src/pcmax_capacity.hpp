#pragma once
// Bounded native PCMAX guard. Float LP proposes; exact clause checks certify.
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <limits>
#include <map>
#include <numeric>
#include <queue>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_set>
#include <utility>
#include <vector>
namespace pcmax {
struct Options {
    double seconds = 0.25;
};
struct Result {
    bool verified = false;
    std::string reason, certificate_json;
    int groups = 0, machines = 0, rounds = 0;
    int64_t demand = 0, capacity = 0;
    double elapsed = 0;
};
namespace detail {
using Clock = std::chrono::steady_clock;
struct Stop : std::runtime_error {
    using std::runtime_error::runtime_error;
};
struct Budget {
    Clock::time_point until;
    explicit Budget(double seconds)
        : until(Clock::now() + std::chrono::duration_cast<Clock::duration>(
                                   std::chrono::duration<double>(seconds))) {}
    void check() const {
        if (Clock::now() >= until)
            throw Stop("budget_exhausted");
    }
};
inline void need(bool ok, const char *reason) {
    if (!ok)
        throw Stop(reason);
}
struct VecHash {
    size_t operator()(const std::vector<int> &v) const {
        size_t h = 0xcbf29ce484222325ULL;
        for (int x : v) {
            h ^= uint32_t(x);
            h *= 0x100000001b3ULL;
        }
        return h;
    }
};
using Clauses = std::unordered_set<std::vector<int>, VecHash>;
inline std::vector<int> canonical(std::vector<int> v) {
    std::sort(v.begin(), v.end());
    v.erase(std::unique(v.begin(), v.end()), v.end());
    return v;
}
inline bool has(const Clauses &cs, std::initializer_list<int> c) {
    return cs.count(canonical(std::vector<int>(c))) != 0;
}
inline uint64_t pair_key(int a, int b) {
    if (a > b)
        std::swap(a, b);
    return (uint64_t(uint32_t(a)) << 32) | uint32_t(b);
}
struct Node {
    int x = 0, left = 0, right = 0;
};
struct Machine {
    int root = 0, yes = 0, no = 0;
    std::vector<int> order, nodes;
};
struct Graph {
    int nv = 0;
    Clauses clauses;
    std::vector<std::vector<int>> groups;
    std::vector<int> membership, level, group_order;
    std::vector<char> eligible;
    std::vector<Node> nodes;
    std::vector<Machine> machines;
};
inline Graph extract(const std::vector<std::vector<int>> &input, int nv, Budget &budget) {
    need(nv > 0 && nv <= 200000 && input.size() <= 1000000, "size_gate");
    Graph g;
    g.nv = nv;
    g.membership.assign(nv + 1, -1);
    g.nodes.resize(nv + 1);
    g.level.assign(nv + 1, -1);
    std::unordered_set<uint64_t> negative;
    size_t literals = 0;
    for (size_t i = 0; i < input.size(); ++i) {
        if ((i & 1023) == 0)
            budget.check();
        need(input[i].size() <= 1024, "clause_width_gate");
        literals += input[i].size();
        need(literals <= 10000000, "literal_gate");
        for (int x : input[i])
            need(x != 0 && x >= -nv && x <= nv, "invalid_literal");
        auto c = canonical(input[i]);
        if (c.size() == 2 && c.back() < 0)
            negative.insert(pair_key(-c[0], -c[1]));
        g.clauses.insert(std::move(c));
    }
    size_t visited = 0;
    for (const auto &c : g.clauses) {
        if ((++visited & 1023) == 0)
            budget.check();
        if (c.size() < 2 || c.front() <= 0 || c.size() > 128)
            continue;
        bool ok = true;
        for (size_t i = 0; i < c.size() && ok; ++i)
            for (size_t j = i + 1; j < c.size(); ++j)
                if (!negative.count(pair_key(c[i], c[j]))) {
                    ok = false;
                    break;
                }
        if (ok) {
            need(g.groups.size() < 128, "assignment_group_gate");
            g.groups.push_back(c);
        }
    }
    need(g.groups.size() >= 3 && g.groups.size() <= 128, "assignment_group_gate");
    std::sort(g.groups.begin(), g.groups.end());
    for (size_t j = 0; j < g.groups.size(); ++j)
        for (int x : g.groups[j]) {
            need(g.membership[x] < 0, "overlapping_groups");
            g.membership[x] = int(j);
        }
    for (const auto &c : g.clauses) {
        if ((++visited & 1023) == 0)
            budget.check();
        if (c.size() != 3)
            continue;
        int selector = 0, count = 0;
        std::vector<int> ends;
        for (int lit : c) {
            if (g.membership[std::abs(lit)] >= 0) {
                selector = lit;
                ++count;
            } else
                ends.push_back(lit);
        }
        if (count != 1 || ends.size() != 2 || ends[0] >= 0 || ends[1] <= 0)
            continue;
        int parent = -ends[0], child = ends[1];
        auto &node = g.nodes[parent];
        need(node.x == 0 || node.x == std::abs(selector), "ambiguous_selector");
        node.x = std::abs(selector);
        int &edge = selector > 0 ? node.left : node.right;
        need(edge == 0 || edge == child, "ambiguous_transition");
        edge = child;
    }
    std::vector<char> children(nv + 1, 0);
    std::vector<int> roots;
    size_t node_count = 0;
    for (int p = 1; p <= nv; ++p)
        if (g.nodes[p].x) {
            const auto &n = g.nodes[p];
            need(n.left && n.right, "incomplete_transition");
            need(p != n.x && p != n.left && p != n.right && n.x != n.left && n.x != n.right,
                 "aliased_transition");
            children[n.left] = children[n.right] = 1;
            ++node_count;
        }
    need(node_count > 0, "missing_bdd");
    for (int p = 1; p <= nv; ++p)
        if (g.nodes[p].x && !children[p])
            roots.push_back(p);
    need(!roots.empty() && roots.size() <= 128, "machine_gate");
    std::vector<int> owner(nv + 1, -1), selector_owner(nv + 1, -1);
    std::vector<std::set<int>> successors(g.groups.size());
    for (int root : roots) {
        budget.check();
        need(has(g.clauses, {root}), "unasserted_root");
        Machine m;
        m.root = root;
        int mid = int(g.machines.size());
        std::vector<int> todo{root};
        std::set<int> variables, ends;
        while (!todo.empty()) {
            if ((++visited & 1023) == 0)
                budget.check();
            int p = todo.back();
            todo.pop_back();
            if (owner[p] == mid)
                continue;
            need(owner[p] < 0, "shared_machine_states");
            owner[p] = mid;
            need(g.membership[p] < 0, "state_is_selector");
            const auto &n = g.nodes[p];
            if (!n.x) {
                ends.insert(p);
                continue;
            }
            m.nodes.push_back(p);
            variables.insert(n.x);
            todo.push_back(n.left);
            todo.push_back(n.right);
            for (int q : {n.left, n.right})
                if (g.nodes[q].x) {
                    int a = g.membership[n.x], b = g.membership[g.nodes[q].x];
                    need(a != b, "repeated_job_level");
                    successors[a].insert(b);
                }
        }
        need(ends.size() == 2, "terminal_gate");
        for (int q : ends) {
            bool yes = has(g.clauses, {q}), no = has(g.clauses, {-q});
            need(yes != no, "ambiguous_terminal");
            if (yes)
                m.yes = q;
            else
                m.no = q;
        }
        need(m.yes && m.no, "missing_terminals");
        std::set<int> jobs;
        for (int x : variables) {
            need(selector_owner[x] < 0, "shared_selector");
            selector_owner[x] = mid;
            need(jobs.insert(g.membership[x]).second, "repeated_job_selector");
        }
        m.order.assign(variables.begin(), variables.end());
        g.machines.push_back(std::move(m));
    }
    // Reduced BDDs may omit selectors. Such groups get zero proof weight:
    // no demand involving an unbounded literal is allowed into a certificate.
    g.eligible.assign(g.groups.size(), 1);
    for (int v = 1; v <= nv; ++v) {
        if (g.nodes[v].x || children[v])
            need(owner[v] >= 0, "unreachable_state");
        if (g.membership[v] >= 0 && selector_owner[v] < 0)
            g.eligible[g.membership[v]] = 0;
    }
    std::vector<int> degree(g.groups.size(), 0), rank(g.groups.size(), -1);
    for (const auto &next : successors)
        for (int j : next)
            ++degree[j];
    std::priority_queue<int, std::vector<int>, std::greater<int>> ready;
    for (size_t j = 0; j < degree.size(); ++j)
        if (!degree[j])
            ready.push(int(j));
    while (!ready.empty()) {
        int j = ready.top();
        ready.pop();
        rank[j] = int(g.group_order.size());
        g.group_order.push_back(j);
        for (int k : successors[j])
            if (!--degree[k])
                ready.push(k);
    }
    need(g.group_order.size() == g.groups.size(), "cyclic_job_order");
    for (auto &m : g.machines) {
        std::sort(m.order.begin(), m.order.end(),
                  [&](int a, int b) { return rank[g.membership[a]] < rank[g.membership[b]]; });
        std::map<int, int> positions;
        for (size_t i = 0; i < m.order.size(); ++i)
            positions[m.order[i]] = int(i);
        g.level[m.yes] = g.level[m.no] = int(m.order.size());
        for (int p : m.nodes)
            g.level[p] = positions.at(g.nodes[p].x);
        for (int p : m.nodes) {
            const auto &n = g.nodes[p];
            need(g.level[n.left] > g.level[p] && g.level[n.right] > g.level[p], "unordered_bdd");
        }
        std::sort(m.nodes.begin(), m.nodes.end(), [&](int a, int b) {
            return std::make_pair(g.level[a], a) > std::make_pair(g.level[b], b);
        });
    }
    for (const auto &c : g.clauses) {
        if ((++visited & 1023) == 0)
            budget.check();
        int positive = 0;
        for (int x : c)
            positive += x > 0 && g.membership[x] < 0;
        need(positive <= 1, "residual_not_horn");
    }
    return g;
}

template <class T> struct Bounds {
    std::vector<T> capacities;
    std::vector<std::vector<int>> patterns;
};
template <class T>
inline Bounds<T> bounds(const Graph &g, const std::vector<T> &w, Budget &budget,
                        bool patterns = false) {
    Bounds<T> out;
    std::vector<T> best(g.nv + 1, T(-1));
    std::vector<char> take(g.nv + 1, 0);
    size_t visits = 0;
    for (const auto &m : g.machines) {
        budget.check();
        std::vector<T> prefix(1, T(0));
        for (int x : m.order)
            prefix.push_back(prefix.back() + w[g.membership[x]]);
        best[m.yes] = 0;
        best[m.no] = -1;
        for (int p : m.nodes) {
            if ((++visits & 1023) == 0)
                budget.check();
            const auto &n = g.nodes[p];
            int i = g.level[p];
            T lo =
                best[n.left] < 0 ? T(-1) : best[n.left] + prefix[g.level[n.left]] - prefix[i + 1];
            T hi = best[n.right] < 0 ? T(-1)
                                     : best[n.right] + prefix[g.level[n.right]] - prefix[i + 1] +
                                           w[g.membership[n.x]];
            take[p] = hi > lo;
            best[p] = std::max(lo, hi);
        }
        need(best[m.root] >= 0, "no_accepting_path");
        out.capacities.push_back(best[m.root] + prefix[g.level[m.root]]);
        if (patterns) {
            std::vector<int> chosen;
            for (int i = 0; i < g.level[m.root]; ++i)
                chosen.push_back(g.membership[m.order[i]]);
            int p = m.root;
            while (g.nodes[p].x) {
                const auto &n = g.nodes[p];
                int q = take[p] ? n.right : n.left;
                if (take[p])
                    chosen.push_back(g.membership[n.x]);
                for (int i = g.level[p] + 1; i < g.level[q]; ++i)
                    chosen.push_back(g.membership[m.order[i]]);
                p = q;
            }
            need(p == m.yes, "bad_pattern_terminal");
            std::sort(chosen.begin(), chosen.end());
            out.patterns.push_back(std::move(chosen));
        }
    }
    return out;
}

// Independent exact recurrence against source clauses; numerical answers are
// not trusted. Bounds: <=128 groups and machines, each weight <=1,000,000.
// Thus each capacity <=128,000,000 and their sum <=16,384,000,000 < INT64_MAX.
inline bool verify(const Graph &g, const std::vector<int64_t> &weights,
                   const std::vector<int64_t> &claimed, Budget &budget) {
    need(weights.size() == g.groups.size() && claimed.size() == g.machines.size(),
         "bad_certificate_size");
    need(weights.size() <= 128 && claimed.size() <= 128, "certificate_size_gate");
    std::vector<int64_t> literal_weight(g.nv + 1, 0);
    std::vector<char> selected(g.nv + 1, 0), used(g.nv + 1, 0), states(g.nv + 1, 0);
    int64_t demand = 0, total = 0;
    for (size_t j = 0; j < weights.size(); ++j) {
        need(weights[j] >= 0 && weights[j] <= 1000000, "weight_range");
        if (!weights[j])
            continue;
        demand += weights[j];
        need(g.clauses.count(canonical(g.groups[j])) != 0, "missing_demand_clause");
        for (int x : g.groups[j]) {
            need(x > 0 && x <= g.nv && !selected[x], "bad_demand_literal");
            selected[x] = 1;
            literal_weight[x] = weights[j];
        }
    }
    std::vector<int64_t> value(g.nv + 1, -1);
    std::vector<int> level(g.nv + 1, -1);
    for (size_t mi = 0; mi < g.machines.size(); ++mi) {
        budget.check();
        const auto &m = g.machines[mi];
        std::set<int> local_nodes(m.nodes.begin(), m.nodes.end());
        need(local_nodes.size() == m.nodes.size() && local_nodes.count(m.root),
             "invalid_certificate_root");
        need(m.yes != m.no && !local_nodes.count(m.yes) && !local_nodes.count(m.no),
             "aliased_certificate_terminal");
        auto local_states = local_nodes;
        local_states.insert(m.yes);
        local_states.insert(m.no);
        need(has(g.clauses, {m.root}) && has(g.clauses, {m.yes}) && has(g.clauses, {-m.no}),
             "missing_graph_unit");
        std::map<int, int> variable_level;
        std::vector<int64_t> suffix(m.order.size() + 1, 0);
        for (size_t i = 0; i < m.order.size(); ++i) {
            int x = m.order[i];
            need(x > 0 && x <= g.nv && !used[x], "overlapping_machine_selector");
            used[x] = 1;
            variable_level[x] = int(i);
        }
        for (size_t i = m.order.size(); i-- > 0;)
            suffix[i] = suffix[i + 1] + literal_weight[m.order[i]];
        for (int p : m.nodes) {
            need(p > 0 && p <= g.nv && !states[p], "overlapping_state");
            states[p] = 1;
            const auto &n = g.nodes[p];
            need(local_states.count(n.left) && local_states.count(n.right),
                 "foreign_certificate_child");
            need(p != n.x && p != n.left && p != n.right && n.x != n.left && n.x != n.right,
                 "aliased_certificate_transition");
            need(variable_level.count(n.x) != 0, "missing_order_selector");
            need(has(g.clauses, {-p, n.x, n.left}) && has(g.clauses, {-p, -n.x, n.right}),
                 "missing_transition_clause");
            level[p] = variable_level[n.x];
        }
        for (int p : {m.yes, m.no}) {
            need(p > 0 && p <= g.nv && !states[p], "bad_terminal");
            states[p] = 1;
            level[p] = int(m.order.size());
        }
        value[m.yes] = 0;
        value[m.no] = -1;
        auto ordered = m.nodes;
        std::sort(ordered.begin(), ordered.end(),
                  [&](int a, int b) { return level[a] > level[b]; });
        size_t visits = 0;
        for (int p : ordered) {
            if ((++visits & 1023) == 0)
                budget.check();
            const auto &n = g.nodes[p];
            int i = level[p];
            need(level[n.left] > i && level[n.right] > i, "invalid_certificate_order");
            int64_t answer = -1;
            for (auto branch : {std::make_pair(n.left, int64_t(0)),
                                std::make_pair(n.right, literal_weight[n.x])}) {
                int child = branch.first;
                if (value[child] < 0)
                    continue;
                int64_t skipped = suffix[i + 1] - suffix[level[child]];
                answer = std::max(answer, value[child] + skipped + branch.second);
            }
            value[p] = answer;
        }
        need(value[m.root] >= 0, "empty_certificate_path");
        int64_t cap = value[m.root] + suffix[0] - suffix[level[m.root]];
        need(cap == claimed[mi], "capacity_mismatch");
        total += cap;
    }
    for (int v = 1; v <= g.nv; ++v) {
        need(!(states[v] && used[v]), "state_selector_alias");
        if (selected[v])
            need(used[v], "uncovered_demand");
    }
    return demand > total;
}

// Two-phase simplex adapted from KACTL content/numerical/Simplex.h.
// Author: Stanford; Source: Stanford Notebook; License: MIT.
// Copyright (c) 2018 Jaehyun Park. Full notice in third_party/stanford-simplex/LICENSE.
// Numerical stability is not guaranteed; only proposes exact integer witnesses.
class Simplex {
    int m, n;
    std::vector<int> N, B;
    std::vector<std::vector<long double>> D;
    Budget &budget;
    int pivots = 0;
    static constexpr long double eps = 1e-12L;
    void pivot(int r, int s) {
        budget.check();
        need(++pivots <= 20000, "pivot_limit");
        long double *a = D[r].data();
        long double inv = 1 / a[s];
        need(std::isfinite(inv), "lp_numeric");
        for (int i = 0; i < m + 2; ++i)
            if (i != r && D[i][s] != 0) {
                if ((i & 127) == 0)
                    budget.check();
                long double *b = D[i].data();
                long double inv2 = b[s] * inv;
                for (int j = 0; j < n + 2; ++j)
                    b[j] -= a[j] * inv2;
                b[s] = a[s] * inv2;
            }
        for (int j = 0; j < n + 2; ++j)
            if (j != s)
                D[r][j] *= inv;
        for (int i = 0; i < m + 2; ++i)
            if (i != r)
                D[i][s] *= -inv;
        D[r][s] = inv;
        std::swap(B[r], N[s]);
    }
    bool simplex(int phase) {
        int x = m + phase - 1;
        for (;;) {
            budget.check();
            int s = -1;
            // Fast reduced-cost pivots, then Bland after 500 pivots for degeneration.
            for (int j = 0; j < n + 1; ++j) {
                need(std::isfinite(D[x][j]), "lp_numeric");
                if (N[j] != -phase && D[x][j] < -eps) {
                    if (s == -1 ||
                        (pivots >= 500 ? N[j] < N[s]
                                       : (D[x][j] < D[x][s] - eps ||
                                          (std::abs(D[x][j] - D[x][s]) <= eps && N[j] < N[s]))))
                        s = j;
                }
            }
            if (s < 0)
                return true;
            int r = -1;
            for (int i = 0; i < m; ++i) {
                if (D[i][s] <= eps)
                    continue;
                long double ratio = D[i][n + 1] / D[i][s];
                need(std::isfinite(ratio), "lp_numeric");
                if (r == -1 || ratio < D[r][n + 1] / D[r][s] - 1e-14L ||
                    (std::abs(ratio - D[r][n + 1] / D[r][s]) <= 1e-14L && B[i] < B[r]))
                    r = i;
            }
            if (r == -1)
                return false;
            pivot(r, s);
        }
    }

  public:
    Simplex(const std::vector<std::vector<double>> &A, const std::vector<double> &b,
            const std::vector<double> &c, Budget &budget_)
        : m(int(b.size())), n(int(c.size())), N(n + 1), B(m),
          D(m + 2, std::vector<long double>(n + 2)), budget(budget_) {
        for (int i = 0; i < m; ++i) {
            for (int j = 0; j < n; ++j)
                D[i][j] = A[i][j];
            B[i] = n + i;
            D[i][n] = -1;
            D[i][n + 1] = b[i];
        }
        for (int j = 0; j < n; ++j) {
            N[j] = j;
            D[m][j] = -c[j];
        }
        N[n] = -1;
        D[m + 1][n] = 1;
    }
    bool solve(std::vector<double> &x) {
        int r = 0;
        for (int i = 1; i < m; ++i)
            if (D[i][n + 1] < D[r][n + 1])
                r = i;
        if (D[r][n + 1] < -eps) {
            pivot(r, n);
            if (!simplex(2) || D[m + 1][n + 1] < -eps)
                return false;
            for (int i = 0; i < m; ++i)
                if (B[i] == -1) {
                    int s = 0;
                    for (int j = 1; j < n + 1; ++j)
                        if (std::make_pair(D[i][j], N[j]) < std::make_pair(D[i][s], N[s]))
                            s = j;
                    pivot(i, s);
                }
        }
        if (!simplex(1))
            return false;
        x.assign(n, 0);
        for (int i = 0; i < m; ++i)
            if (B[i] >= 0 && B[i] < n)
                x[B[i]] = D[i][n + 1];
        for (double v : x)
            if (!std::isfinite(v))
                return false;
        return true;
    }
};

template <class T> inline void array(std::ostream &os, const std::vector<T> &values) {
    os << '[';
    bool first = true;
    for (const auto &v : values) {
        if (!first)
            os << ',';
        first = false;
        os << v;
    }
    os << ']';
}
inline std::string certificate(const Graph &g, const std::string &sha,
                               const std::vector<int64_t> &w, const std::vector<int64_t> &caps) {
    std::ostringstream os;
    os << "{\"format\":\"pcmax-capacity-v1\",\"source_sha256\":\"" << sha
       << "\",\"selected_groups\":[";
    bool first = true;
    std::vector<int64_t> positive;
    for (size_t j = 0; j < w.size(); ++j)
        if (w[j]) {
            if (!first)
                os << ',';
            first = false;
            array(os, g.groups[j]);
            positive.push_back(w[j]);
        }
    os << "],\"group_weights\":";
    array(os, positive);
    os << ",\"required\":" << std::accumulate(w.begin(), w.end(), int64_t(0))
       << ",\"capacity_sum\":" << std::accumulate(caps.begin(), caps.end(), int64_t(0))
       << ",\"machines\":[";
    for (size_t i = 0; i < g.machines.size(); ++i) {
        if (i)
            os << ',';
        const auto &m = g.machines[i];
        os << "{\"root\":" << m.root << ",\"variable_order\":";
        array(os, m.order);
        os << ",\"true_terminal\":" << m.yes << ",\"false_terminal\":" << m.no
           << ",\"capacity\":" << caps[i] << ",\"transitions\":[";
        for (size_t k = 0; k < m.nodes.size(); ++k) {
            if (k)
                os << ',';
            int p = m.nodes[k];
            const auto &n = g.nodes[p];
            os << '[' << p << ',' << n.x << ',' << n.left << ',' << n.right << ']';
        }
        os << "]}";
    }
    os << "]}\n";
    return os.str();
}
inline bool candidate(const Graph &g, std::vector<int64_t> w, const std::string &sha,
                      Budget &budget, Result &result) {
    int64_t divisor = 0;
    for (int64_t x : w) {
        need(x >= 0 && x <= 1000000, "weight_range");
        divisor = std::gcd(divisor, x);
    }
    if (!divisor)
        return false;
    for (auto &x : w)
        x /= divisor;
    auto found = bounds(g, w, budget);
    int64_t demand = std::accumulate(w.begin(), w.end(), int64_t(0)),
            capacity =
                std::accumulate(found.capacities.begin(), found.capacities.end(), int64_t(0));
    if (demand <= capacity)
        return false;
    need(verify(g, w, found.capacities, budget), "native_verifier_rejected");
    budget.check();
    result.certificate_json = certificate(g, sha, w, found.capacities);
    budget.check();
    result.demand = demand;
    result.capacity = capacity;
    result.verified = true;
    result.reason = "integer_capacity_certificate";
    return true;
}
} // namespace detail

inline Result analyze(const std::vector<std::vector<int>> &clauses, int nvars,
                      const std::string &source_sha256, const Options &options) {
    using namespace detail;
    auto start = Clock::now();
    Result result;
    try {
        need(std::isfinite(options.seconds) && options.seconds > 0 && options.seconds <= 86400,
             "invalid_or_exhausted_budget");
        need(source_sha256.size() == 64 && std::all_of(source_sha256.begin(), source_sha256.end(),
                                                       [](char c) {
                                                           return (c >= '0' && c <= '9') ||
                                                                  (c >= 'a' && c <= 'f');
                                                       }),
             "invalid_source_hash");
        Budget budget(options.seconds);
        auto g = extract(clauses, nvars, budget);
        result.groups = int(g.groups.size());
        result.machines = int(g.machines.size());
        int n = result.groups, k = result.machines;
        std::vector<int64_t> integer(n, 0);
        for (int j : g.group_order) {
            if (!g.eligible[j])
                continue;
            integer[j] = 1;
            if (candidate(g, integer, source_sha256, budget, result))
                break;
        }
        if (!result.verified) {
            auto initial = bounds(g, std::vector<double>(n, 1), budget, true);
            std::vector<std::set<std::vector<int>>> patterns(k);
            for (int m = 0; m < k; ++m)
                patterns[m].insert(initial.patterns[m]);
            for (int round = 0; round < 200 && !result.verified; ++round) {
                budget.check();
                result.rounds = round + 1;
                size_t rows = 2;
                for (const auto &p : patterns)
                    rows += p.size();
                for (bool eligible : g.eligible)
                    if (!eligible)
                        ++rows;
                need(rows <= 4000 && rows * size_t(n + k) <= 1000000, "lp_matrix_gate");
                std::vector<std::vector<double>> A(rows, std::vector<double>(n + k, 0));
                std::vector<double> b(rows, 0), c(n + k, 0);
                size_t row = 0;
                for (int m = 0; m < k; ++m) {
                    c[n + m] = -1;
                    for (const auto &pattern : patterns[m]) {
                        for (int j : pattern)
                            A[row][j] = 1;
                        A[row][n + m] = -1;
                        ++row;
                    }
                }
                for (int j = 0; j < n; ++j)
                    if (!g.eligible[j]) {
                        A[row][j] = 1;
                        ++row;
                    }
                for (int j = 0; j < n; ++j) {
                    A[row][j] = 1;
                    A[row + 1][j] = -1;
                }
                b[row] = 1;
                b[row + 1] = -1;
                std::vector<double> solution;
                need(Simplex(A, b, c, budget).solve(solution), "lp_no_solution");
                std::vector<double> w(n);
                for (int j = 0; j < n; ++j)
                    w[j] = g.eligible[j] ? std::max(0.0, solution[j]) : 0.0;
                auto current = bounds(g, w, budget, true);
                double demand = std::accumulate(w.begin(), w.end(), 0.0),
                       capacity = std::accumulate(current.capacities.begin(),
                                                  current.capacities.end(), 0.0);
                if (capacity < demand - 1e-8) {
                    std::set<double> thresholds;
                    for (double v : w)
                        if (v > 1e-8)
                            thresholds.insert(v);
                    for (double threshold : thresholds) {
                        for (int j = 0; j < n; ++j)
                            integer[j] = w[j] >= threshold - 1e-9;
                        if (candidate(g, integer, source_sha256, budget, result))
                            break;
                    }
                    for (int64_t scale : {10, 100, 1000, 10000, 100000, 1000000}) {
                        if (result.verified)
                            break;
                        for (int j = 0; j < n; ++j) {
                            need(std::isfinite(w[j]) && w[j] <= 1.00001, "lp_weight_range");
                            integer[j] =
                                std::clamp<int64_t>(std::llround(w[j] * scale), 0, 1000000);
                        }
                        candidate(g, integer, source_sha256, budget, result);
                    }
                }
                if (result.verified)
                    break;
                bool changed = false;
                for (int m = 0; m < k; ++m)
                    if (current.capacities[m] > solution[n + m] + 1e-7)
                        changed |= patterns[m].insert(current.patterns[m]).second;
                if (!changed) {
                    result.reason = "no_capacity_contradiction";
                    break;
                }
                result.reason = "lp_round_limit";
            }
        }
    } catch (const Stop &e) {
        result.verified = false;
        result.certificate_json.clear();
        result.reason = e.what();
    } catch (const std::bad_alloc &) {
        result.verified = false;
        result.certificate_json.clear();
        result.reason = "allocation_gate";
    } catch (const std::exception &) {
        result.verified = false;
        result.certificate_json.clear();
        result.reason = "guard_exception";
    }
    result.elapsed = std::chrono::duration<double>(Clock::now() - start).count();
    return result;
}
} // namespace pcmax
