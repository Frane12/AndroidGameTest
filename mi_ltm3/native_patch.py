"""Build an isolated LTM3 decision-hook source from the pinned ATLAS15 engine.

Run after warm/CDCL generation. Never edit the frozen reference sources.
The learned policy opts into a bounded structural branching heuristic, not
into an imported assignment, propagation, clause or mathematical conclusion.
"""
from pathlib import Path


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError("Native hook anchor drift: " + old[:80])
    return text.replace(old, new)


def generate():
    out = Path("mre_ltm3")
    out.mkdir(exist_ok=True)
    source = Path("mre_atlas15/drnas_native_core_c.hpp").read_text()
    hook = r'''
    bool ltm3_enabled_ = false;
    std::vector<double> ltm3_structure_;
    uint64_t ltm3_checks_ = 0, ltm3_overrides_ = 0;
    uint64_t ltm3_hash_ = 1469598103934665603ULL;
    int ltm3_pick_branch() {
        const int base = heap_[0];
        // At most 16 early interventions, 16 candidates per intervention.
        // VSIDS remains dominant; stop after 64 decisions.
        if (!ltm3_enabled_ || stats_.decisions >= 64 || stats_.decisions % 4)
            return base;
        ++ltm3_checks_;
        int best = base;
        const double scale = std::max(1e-12, activity_[base]);
        double score = 1.0 + 0.35 * ltm3_structure_[base];
        for (size_t i = 1; i < std::min<size_t>(16, heap_.size()); ++i) {
            const int v = heap_[i];
            require(!values_[v], "LTM3 candidate must be unassigned");
            const double activity = activity_[v] / scale;
            if (activity < 0.80) continue;
            const double candidate = activity + 0.35 * ltm3_structure_[v];
            if (candidate > score) { best = v; score = candidate; }
        }
        if (best != base) ++ltm3_overrides_;
        return best;
    }
public:
    void ltm3_enable(const CNF& original) {
        require(original.vars == n_ && stats_.decisions == 0,
                "LTM3 setup requires original source before search");
        std::vector<double> pos(n_+1,0.0), neg(n_+1,0.0);
        // Two-sided short-clause incidence. No planted model or prior IDs.
        for (const auto& clause : original.clauses) {
            if (clause.empty() || clause.size() > 8) continue;
            const double weight = std::ldexp(1.0, -int(clause.size()));
            for (int lit : clause)
                (lit > 0 ? pos : neg)[var(lit)] += weight;
        }
        ltm3_structure_.assign(n_+1,0.0);
        double maximum = 0.0;
        for (int v=1; v<=n_; ++v) {
            ltm3_structure_[v] = std::sqrt(pos[v]*neg[v]);
            maximum = std::max(maximum, ltm3_structure_[v]);
        }
        if (maximum > 0)
            for (double& score : ltm3_structure_) score /= maximum;
        ltm3_enabled_ = true;
    }
    uint64_t ltm3_checks() const { return ltm3_checks_; }
    uint64_t ltm3_overrides() const { return ltm3_overrides_; }
    uint64_t ltm3_decision_hash() const { return ltm3_hash_; }
private:
'''
    source = replace_once(source, "    int pick_branch_variable() {", hook + "    int pick_branch_variable() {")
    source = replace_once(source, "        return v;\n    }\n\npublic:",
                          "        return ltm3_pick_branch();\n    }\n\npublic:")
    source = replace_once(source,
                          "                require(enqueue(phases_[v] >= 0 ? v : -v, -1),",
                          "                ltm3_hash_ ^= uint64_t(2*v + (phases_[v] < 0));\n"
                          "                ltm3_hash_ *= 1099511628211ULL;\n"
                          "                require(enqueue(phases_[v] >= 0 ? v : -v, -1),")
    (out/"drnas_native_core_c.hpp").write_text(source)
    main = Path("research/drnas_atlas15_native.cpp").read_text()
    main = replace_once(main, 'drnas::require(mode=="A"||',
                         'drnas::require(mode=="LTM_NATIVE"||mode=="A"||')
    main = replace_once(main, "   solver.add_cnf(work);",
                         '   solver.add_cnf(work);\n   if(mode=="LTM_NATIVE")solver.ltm3_enable(orig);')
    main = replace_once(main, '           <<" trial_seed="',
                         '           <<" ltm3_branch_checks="<<solver.ltm3_checks()\n'
                         '           <<" ltm3_branch_overrides="<<solver.ltm3_overrides()\n'
                         '           <<" ltm3_decision_hash="<<solver.ltm3_decision_hash()\n'
                         '           <<" trial_seed="')
    (out/"native.cpp").write_text(main)
    print("LTM3_NATIVE_HOOK_GENERATED", out)


if __name__ == "__main__":
    generate()
