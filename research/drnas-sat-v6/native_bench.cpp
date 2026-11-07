// DRNAS Structural SAT v6: native C++ vs CaDiCaL 3.0.1 (same process).
// Deterministic pre-selected DIMACS, solver calls via official cadical.hpp API.
// Timing includes separator search, conditioning, renumbering, solver allocation
// and solving; excludes DIMACS input I/O for every strategy equally.
#include "cadical.hpp"
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <numeric>
#include <random>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_set>
#include <utility>
#include <vector>

using CNF = std::vector<std::vector<int>>;
using Clock = std::chrono::steady_clock;

struct Formula {
    CNF clauses;
    int vars = 0;
};
struct Cut {
    std::vector<int> vertices;
    std::vector<std::vector<int>> components;
    int inspected = 0;
};
struct Answer {
    bool sat = false;
    bool selected = false;
    int cut_size = 0;
    int components = 1;
    int calls = 0;
    int inspected = 0;
};
struct Case {
    std::string id, family, path;
    int vars = 0, clauses = 0;
};

Formula read_dimacs(const std::string &path) {
    std::ifstream in(path);
    if (!in) throw std::runtime_error("Cannot read DIMACS: " + path);
    Formula f;
    std::string line;
    std::vector<int> clause;
    while (std::getline(in, line)) {
        if (line.empty() || line[0] == 'c') continue;
        if (line[0] == 'p') {
            std::istringstream head(line);
            std::string p, kind;
            int count = 0;
            head >> p >> kind >> f.vars >> count;
            if (kind != "cnf" || f.vars < 0) throw std::runtime_error("Bad DIMACS header");
            continue;
        }
        std::istringstream tokens(line);
        int literal;
        while (tokens >> literal) {
            if (literal == 0) {
                f.clauses.push_back(std::move(clause));
                clause.clear();
            } else {
                f.vars = std::max(f.vars, std::abs(literal));
                clause.push_back(literal);
            }
        }
    }
    if (!clause.empty()) throw std::runtime_error("Unterminated DIMACS clause " + path);
    return f;
}

int solve_api(const Formula &f) {
    CaDiCaL::Solver solver;
    for (const auto &clause : f.clauses) {
        for (int lit : clause) solver.add(lit);
        solver.add(0);
    }
    int result = solver.solve();
    if (result != 10 && result != 20) throw std::runtime_error("CaDiCaL returned UNKNOWN");
    return result;
}

void fill_api(CaDiCaL::Solver &solver, const Formula &f) {
    for (const auto &clause : f.clauses) {
        for (int lit : clause) solver.add(lit);
        solver.add(0);
    }
}

struct Graph {
    std::vector<std::vector<int>> neighbors;
    std::vector<int> active;
    double mean_degree = 0.0;
};

Graph make_graph(const Formula &f) {
    std::vector<std::unordered_set<int>> sets(f.vars + 1);
    for (const auto &c : f.clauses) {
        for (int a : c) {
            int x = std::abs(a);
            for (int b : c) {
                int y = std::abs(b);
                if (x != y) sets[x].insert(y);
            }
        }
    }
    Graph g;
    g.neighbors.resize(f.vars + 1);
    for (int x = 1; x <= f.vars; x++) {
        if (!sets[x].empty()) {
            g.active.push_back(x);
            g.neighbors[x].assign(sets[x].begin(), sets[x].end());
            g.mean_degree += g.neighbors[x].size();
        }
    }
    if (!g.active.empty()) g.mean_degree /= g.active.size();
    return g;
}

std::vector<std::vector<int>> components_after(const Graph &g, const std::vector<int> &cut) {
    std::vector<char> seen(g.neighbors.size(), 0);
    for (int x : cut) seen[x] = 1;
    std::vector<std::vector<int>> out;
    for (int x : g.active) {
        if (seen[x]) continue;
        seen[x] = 1;
        std::vector<int> component, queue = {x};
        for (size_t idx = 0; idx < queue.size(); idx++) {
            int u = queue[idx];
            component.push_back(u);
            for (int v : g.neighbors[u]) {
                if (!seen[v]) {
                    seen[v] = 1;
                    queue.push_back(v);
                }
            }
        }
        out.push_back(std::move(component));
    }
    std::sort(out.begin(), out.end(), [](const auto &a, const auto &b) {
        return a.size() > b.size();
    });
    return out;
}

Cut find_cut(const Formula &f) {
    Cut result;
    Graph g = make_graph(f);
    const int n = static_cast<int>(g.active.size());
    if (n < 40) return result;
    std::vector<int> ranked = g.active;
    std::sort(ranked.begin(), ranked.end(), [&](int a, int b) {
        if (g.neighbors[a].size() != g.neighbors[b].size())
            return g.neighbors[a].size() > g.neighbors[b].size();
        return a < b;
    });
    // Cheap structural gate, fixed before the benchmark. On globally random
    // formulas it avoids expensive pair separator scans.
    if (g.neighbors[ranked[0]].size() < 1.6 * g.mean_degree) return result;
    std::vector<int> candidates;
    for (int i = 0; i < std::min(n, 20); i++) candidates.push_back(ranked[i]);
    for (int i = std::max(0,n-8); i < n; i++) candidates.push_back(ranked[i]);
    std::sort(candidates.begin(), candidates.end());
    candidates.erase(std::unique(candidates.begin(), candidates.end()), candidates.end());
    // Restore descending degree to try likely cross-module hubs first.
    std::sort(candidates.begin(), candidates.end(), [&](int a, int b) {
        return g.neighbors[a].size() > g.neighbors[b].size();
    });
    auto acceptable = [&](const std::vector<int> &cut,
                          const std::vector<std::vector<int>> &parts) {
        if (parts.size() < 2 || parts[1].size() < 8) return false;
        if (parts[0].size() > 0.80 * (n - static_cast<int>(cut.size()))) return false;
        if ((1 << cut.size()) * parts.size() > 64) return false;
        return true;
    };
    for (int a : candidates) {
        std::vector<int> cut = {a};
        auto parts = components_after(g,cut);
        result.inspected++;
        if (acceptable(cut,parts)) {
            result.vertices=std::move(cut);
            result.components=std::move(parts);
            return result;
        }
    }
    const int max_candidates=std::min(20,static_cast<int>(candidates.size()));
    for (int i=0; i<max_candidates; i++) {
        for (int j=i+1; j<max_candidates; j++) {
            std::vector<int> cut={candidates[i],candidates[j]};
            auto parts = components_after(g,cut);
            result.inspected++;
            if (acceptable(cut,parts)) {
                result.vertices=std::move(cut);
                result.components=std::move(parts);
                return result;
            }
        }
    }
    return result;
}

Answer plain(const Formula &f) {
    return {solve_api(f)==10, false, 0, 1, 1, 0};
}

Answer incremental(const Formula &f) {
    Cut cut=find_cut(f);
    if (cut.vertices.empty()) {
        auto out=plain(f);
        out.inspected=cut.inspected;
        return out;
    }
    CaDiCaL::Solver solver;
    fill_api(solver,f);
    int calls=0, signs=1 << cut.vertices.size();
    for (int mask=0; mask<signs; mask++) {
        for (size_t i=0; i<cut.vertices.size(); i++) {
            int v=cut.vertices[i];
            solver.assume((mask & (1<<i)) ? v : -v);
        }
        calls++;
        int status=solver.solve();
        if (status==10) return {true,true,static_cast<int>(cut.vertices.size()),
                                static_cast<int>(cut.components.size()),calls,cut.inspected};
        if (status!=20) throw std::runtime_error("Incremental CaDiCaL UNKNOWN");
    }
    return {false,true,static_cast<int>(cut.vertices.size()),
            static_cast<int>(cut.components.size()),calls,cut.inspected};
}

Answer hybrid(const Formula &f) {
    Cut cut=find_cut(f);
    if (cut.vertices.empty()) {
        auto out=plain(f);
        out.inspected=cut.inspected;
        return out;
    }
    const int number_parts=static_cast<int>(cut.components.size());
    std::vector<int> owner(f.vars+1,-1),local(f.vars+1,0);
    for (int p=0;p<number_parts;p++) {
        for (size_t i=0;i<cut.components[p].size();i++) {
            int v=cut.components[p][i];
            owner[v]=p;
            local[v]=static_cast<int>(i)+1;
        }
    }
    std::vector<int> fixed(f.vars+1,0);
    int calls=0, num_assignments=1 << cut.vertices.size();
    for (int mask=0;mask<num_assignments;mask++) {
        std::fill(fixed.begin(),fixed.end(),0);
        for (size_t i=0;i<cut.vertices.size();i++)
            fixed[cut.vertices[i]] = (mask & (1<<i)) ? 1 : -1;
        std::vector<Formula> sub(number_parts);
        for (int p=0;p<number_parts;p++)
            sub[p].vars=static_cast<int>(cut.components[p].size());
        bool contradiction=false;
        for (const auto &c : f.clauses) {
            bool fulfilled=false;
            std::vector<int> residual;
            int group=-1;
            for (int lit : c) {
                int v=std::abs(lit);
                if (fixed[v]!=0) {
                    if ((lit>0 && fixed[v]>0)||(lit<0 && fixed[v]<0)) {
                        fulfilled=true;
                        break;
                    }
                } else {
                    int local_id=local[v];
                    int owned=owner[v];
                    if (owned<0 || local_id<=0) throw std::runtime_error("Missing residual variable");
                    if (group!=-1 && group!=owned) throw std::runtime_error("Invalid graph separator");
                    group=owned;
                    residual.push_back(lit>0?local_id:-local_id);
                }
            }
            if (fulfilled) continue;
            if (residual.empty()) {
                contradiction=true;
                break;
            }
            sub[group].clauses.push_back(std::move(residual));
        }
        if (contradiction) continue;
        bool every_piece_sat=true;
        for (auto &part : sub) {
            if (part.clauses.empty()) continue;
            calls++;
            if (solve_api(part)==20) {
                every_piece_sat=false;
                break;
            }
        }
        if (every_piece_sat) {
            return {true,true,static_cast<int>(cut.vertices.size()),number_parts,calls,cut.inspected};
        }
    }
    return {false,true,static_cast<int>(cut.vertices.size()),number_parts,calls,cut.inspected};
}

std::vector<Case> read_manifest(const std::string &path) {
    std::ifstream in(path);
    if (!in) throw std::runtime_error("Cannot read manifest " + path);
    std::string line;
    std::getline(in,line);
    std::vector<Case> out;
    while(std::getline(in,line)) {
        if (line.empty()) continue;
        std::istringstream s(line);
        Case item;
        std::string nv,nc;
        std::getline(s,item.id,',');
        std::getline(s,item.family,',');
        std::getline(s,item.path,',');
        std::getline(s,nv,',');
        std::getline(s,nc,',');
        item.vars=std::stoi(nv);
        item.clauses=std::stoi(nc);
        out.push_back(std::move(item));
    }
    return out;
}

int main(int argc,char **argv) {
    try {
        if (argc<4) {
            std::cerr<<"Usage: native_bench manifest.csv results.csv REPS [SEED]\n";
            return 2;
        }
        const std::string manifest=argv[1],csvpath=argv[2];
        const int reps=std::stoi(argv[3]);
        const uint32_t seed=argc>4?std::stoul(argv[4]):20261117u;
        if (reps<1 || reps>30) throw std::runtime_error("Bad reps");
        auto items=read_manifest(manifest);
        std::ofstream csv(csvpath);
        if (!csv) throw std::runtime_error("Cannot write results");
        csv<<"case,family,method,rep,elapsed_us,result,selected,cut_size,components,calls,inspected,variables,clauses\n";
        csv<<std::fixed<<std::setprecision(4);
        const std::vector<std::string> methods={"cadical_plain","native_hybrid","cut_assumptions"};
        int idx=0;
        for (const auto &item:items) {
            Formula f=read_dimacs(item.path);
            int expected=-1;
            for (int rep=0;rep<reps;rep++) {
                std::vector<std::string> order=methods;
                std::mt19937 rng(seed+idx*997u+rep);
                std::shuffle(order.begin(),order.end(),rng);
                for (const auto &method:order) {
                    const auto t0=Clock::now();
                    Answer ans=method=="cadical_plain"?plain(f):
                               method=="native_hybrid"?hybrid(f):incremental(f);
                    const auto t1=Clock::now();
                    double elapsed=std::chrono::duration<double,std::micro>(t1-t0).count();
                    if (expected<0) expected=ans.sat?1:0;
                    if (expected!=(ans.sat?1:0)) {
                        throw std::runtime_error("SAT/UNSAT MISMATCH on " + item.id +" in "+ method);
                    }
                    csv<<item.id<<','<<item.family<<','<<method<<','<<rep<<','
                       <<elapsed<<','<<(ans.sat?"SAT":"UNSAT")<<','
                       <<(ans.selected?1:0)<<','<<ans.cut_size<<','
                       <<ans.components<<','<<ans.calls<<','<<ans.inspected<<','
                       <<item.vars<<','<<item.clauses<<"\n";
                }
            }
            csv.flush();
            std::cerr<<"Verified "<<++idx<<"/"<<items.size()<<" "<<item.family
                     <<" "<<(expected==1?"SAT":"UNSAT")<<"\n";
        }
        return 0;
    } catch (const std::exception &e) {
        std::cerr<<"ERROR: "<<e.what()<<"\n";
        return 1;
    }
}
