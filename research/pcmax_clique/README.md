# PCMAX-SCALE6 source clique-cover guard (experimental)

This branch extends DRNAS with optional --pcmax-clique and --pcmax-clique-only. It is OFF by default; the existing CDCL solver remains untouched.

## Soundness

Select J original positive clauses with disjoint selector literals. They require at least J distinct true selectors. Every pair in each certificate clique has its own original negative binary mutex clause (-a OR -b), so every clique has at most one true selector. When the selected clauses are entirely covered by C cliques and J > C, the unchanged original CNF is UNSAT.

The independent Python checker verifies SHA-256, exact source clause indices, disjoint demands, all mutex pairs, selector coverage, and strict deficiency. This is an established combinatorial argument. The current certificate is NOT a standard VeriPB, DRAT or LRAT proof.

## Reproduction

1. Compile drnas-pcmax with CMake as before.
2. Run drnas-pcmax input.cnf --mode core --time 6 --pcmax-clique-only --pcmax-clique-budget-ms 4000 --pcmax-certificate new-proof.json
3. Run python3 research/pcmax_clique/verify_clique.py input.cnf new-proof.json
4. Run the SHA-frozen reproductions from .github/workflows/drnas-pcmax-scale6-clique.yml.

The only mode returns UNKNOWN if no witness is found, never CDCL fallback. The integrated guard may continue to original CDCL, which must be recorded as an unresolved structural failure, not as structural success.

Retrospective development experiments on existing SCALE5 scheduling CNFs are not a blind industrial holdout, a universal SAT speed record or an O(n) proof. Candidate detection limits: groups 3 to 24 of equal positive clause width, width up to 64, up to 256 chosen selectors, plus original native CNF capture limits. Other encodings can remain UNKNOWN.

CI provenance: https://github.com/Frane12/AndroidGameTest/actions/runs/45343139610
