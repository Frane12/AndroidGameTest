#include "cadical.hpp"
#include "routes.hpp"
#include <charconv>
#include <climits>
#include <fstream>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>

using drnas99::Clauses;
using drnas99::Route;

struct Formula {
    int vars = 0;
    Clauses clauses;
};

static Formula read_dimacs(const char* path) {
    std::ifstream input(path);
    if (!input) throw std::runtime_error("cannot open input");
    Formula f;
    std::vector<int> clause;
    int count = -1;
    std::string line;
    while (std::getline(input, line)) {
        std::istringstream words(line);
        std::string token;
        if (!(words >> token) || token.front() == 'c') continue;
        if (token == "p") {
            std::string format;
            if (count != -1 || !(words >> format >> f.vars >> count) || format != "cnf" ||
                f.vars < 0 || f.vars == INT_MAX || count < 0 || (words >> token))
                throw std::runtime_error("invalid DIMACS header");
            continue;
        }
        if (count < 0) throw std::runtime_error("missing DIMACS header");
        do {
            int lit;
            const char* end = token.data() + token.size();
            auto parsed = std::from_chars(token.data(), end, lit);
            if (parsed.ec != std::errc{} || parsed.ptr != end || lit < -f.vars || lit > f.vars)
                throw std::runtime_error("invalid DIMACS literal");
            if (lit) clause.push_back(lit);
            else {
                f.clauses.emplace_back();
                f.clauses.back().swap(clause);
                if (f.clauses.size() > size_t(count)) throw std::runtime_error("too many clauses");
            }
        } while (words >> token);
    }
    if (input.bad() || count < 0 || !clause.empty() || f.clauses.size() != size_t(count))
        throw std::runtime_error("incomplete DIMACS input");
    return f;
}

// Same unhinted single-state conflict schedule and large-input fallback as V9.6/V9.7.
static bool solve_cdcl(const Formula& f, int budget, std::vector<char>& model) {
    CaDiCaL::Solver solver;
    for (const auto& clause : f.clauses) {
        for (int lit : clause) solver.add(lit);
        solver.add(0);
    }
    int status;
    if (f.vars <= 300000 && f.clauses.size() <= 1200000) {
        if (!solver.limit("conflicts", budget)) throw std::runtime_error("invalid probe limit");
        status = solver.solve();
        if (!status) {
            if (!solver.limit("conflicts", -1)) throw std::runtime_error("invalid continuation limit");
            status = solver.solve();
        }
    } else {
        status = solver.solve();
    }
    if (status == 20) return false;
    if (status != 10) throw std::runtime_error("unknown solver result");
    model.assign(size_t(f.vars) + 1, false);
    // Declared but unused variables may exceed CaDiCaL's internal variable range.
    const int last = solver.vars();
    for (int v = 1; v <= last; ++v) model[v] = solver.val(v) > 0;
    return true;
}

int main(int argc, char** argv) {
    try {
        const std::string mode = argc == 3 ? argv[1] : "--auto";
        if ((argc != 2 && argc != 3) ||
            (mode != "--auto" && mode != "--single96" && mode != "--single128"))
            throw std::runtime_error("usage: drnas-sat [--auto|--single96|--single128] file.cnf");
        const Formula f = read_dimacs(argv[argc - 1]);
        const bool bounded = f.vars <= 300000 && f.clauses.size() <= 1200000;
        Route route = mode == "--auto" && bounded ? drnas99::classify(f.clauses) : Route::single96;
        bool sat;
        const char* name;
        std::vector<char> model;
        if (route == Route::horn || route == Route::dual_horn) {
            name = route == Route::horn ? "horn" : "dual-horn";
            sat = drnas99::solve_horn(f.vars, f.clauses, route == Route::dual_horn, model);
        } else if (route == Route::binary) {
            name = "2sat";
            sat = drnas99::solve_binary(f.vars, f.clauses, model);
        } else {
            name = mode == "--single128" ? "single128" : "single96";
            sat = solve_cdcl(f, mode == "--single128" ? 128 : 96, model);
        }
        if (sat) {
            for (const auto& c : f.clauses)
                if (std::none_of(c.begin(), c.end(), [&](int lit) {
                    return bool(model[std::abs(lit)]) == (lit > 0);
                })) throw std::runtime_error("invalid SAT model");
        }
        std::cout << "c route " << name << "\ns " << (sat ? "SATISFIABLE" : "UNSATISFIABLE") << '\n';
        if (sat) {
            std::cout << 'v';
            for (int v = 1; v <= f.vars; ++v) std::cout << ' ' << (model[v] ? v : -v);
            std::cout << " 0\n";
        }
        return sat ? 10 : 20;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
