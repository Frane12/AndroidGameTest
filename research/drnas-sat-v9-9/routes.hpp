#pragma once
#include <algorithm>
#include <cstddef>
#include <cstdlib>
#include <utility>
#include <vector>

namespace drnas99 {
using Clauses = std::vector<std::vector<int>>;
enum class Route { horn, dual_horn, binary, single96 };

inline Route classify(const Clauses& clauses) {
    bool horn = true, dual = true, binary = true;
    for (const auto& clause : clauses) {
        if (clause.size() > 2) binary = false;
        size_t positive = 0;
        for (int lit : clause) positive += lit > 0;
        horn = horn && positive <= 1;
        dual = dual && clause.size() - positive <= 1;
        if (!horn && !dual && !binary) return Route::single96;
    }
    if (horn) return Route::horn;
    if (dual) return Route::dual_horn;
    return binary ? Route::binary : Route::single96;
}

// A Horn clause is an implication from all negative occurrences to its
// one positive head (or to false). Negating every variable handles dual Horn.
inline bool solve_horn(int vars, const Clauses& clauses, bool dual,
                       std::vector<char>& model) {
    std::vector<std::vector<size_t>> uses(size_t(vars) + 1);
    std::vector<size_t> missing(clauses.size());
    std::vector<int> head(clauses.size());
    std::vector<int> queue;
    model.assign(size_t(vars) + 1, false);
    auto imply = [&](int v) {
        if (v && !model[v]) {
            model[v] = true;
            queue.push_back(v);
        }
        return v != 0;
    };
    for (size_t i = 0; i < clauses.size(); ++i) {
        for (int lit : clauses[i]) {
            if (dual) lit = -lit;
            if (lit > 0) head[i] = lit;
            else {
                ++missing[i];
                uses[-lit].push_back(i);
            }
        }
        if (!missing[i] && !imply(head[i])) return false;
    }
    for (size_t i = 0; i < queue.size(); ++i) {
        for (size_t clause : uses[queue[i]]) {
            if (--missing[clause] == 0 && !imply(head[clause])) return false;
        }
    }
    if (dual) {
        for (auto& value : model) value = !value;
    }
    return true;
}

// Iterative Kosaraju. For every implication a -> b the graph contains
// not b -> not a, so reverse neighbors of v are complements of neighbors of not v.
inline bool solve_binary(int vars, const Clauses& clauses, std::vector<char>& model) {
    const size_t nodes = 2 * size_t(vars);
    std::vector<std::vector<size_t>> edges(nodes);
    auto node = [](int lit) { return 2 * size_t(std::abs(lit) - 1) + (lit < 0); };
    for (const auto& c : clauses) {
        if (c.empty()) return false;
        size_t a = node(c.front()), b = node(c.back());
        edges[a ^ 1].push_back(b);
        if (a != b) edges[b ^ 1].push_back(a);
    }
    std::vector<char> seen(nodes);
    std::vector<size_t> order;
    std::vector<std::pair<size_t, size_t>> stack;
    for (size_t root = 0; root < nodes; ++root) {
        if (seen[root]) continue;
        seen[root] = true;
        stack.emplace_back(root, 0);
        while (!stack.empty()) {
            auto& [v, i] = stack.back();
            if (i == edges[v].size()) {
                order.push_back(v);
                stack.pop_back();
                continue;
            }
            const size_t next = edges[v][i++];
            if (!seen[next]) {
                seen[next] = true;
                stack.emplace_back(next, 0);
            }
        }
    }
    std::vector<size_t> component(nodes, nodes), pending;
    size_t id = 0;
    for (auto it = order.rbegin(); it != order.rend(); ++it) {
        if (component[*it] != nodes) continue;
        component[*it] = id;
        pending.push_back(*it);
        while (!pending.empty()) {
            const size_t v = pending.back();
            pending.pop_back();
            for (size_t opposite : edges[v ^ 1]) {
                const size_t pred = opposite ^ 1;
                if (component[pred] == nodes) {
                    component[pred] = id;
                    pending.push_back(pred);
                }
            }
        }
        ++id;
    }
    model.assign(size_t(vars) + 1, false);
    for (int v = 1; v <= vars; ++v) {
        const size_t yes = node(v), no = yes ^ 1;
        if (component[yes] == component[no]) return false;
        model[v] = component[yes] > component[no];
    }
    return true;
}
}
