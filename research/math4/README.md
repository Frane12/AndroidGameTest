# DRNAS MATH4 — Original-CNF XOR + root-unit proof (experimental)

## What was actually demonstrated

On one **unmodified SAT Competition 2026 Main Track lights-out** CNF
(GBD file ID `667341ee8c1dea3db613db317e2b2c33`,
SHA256 `fdbc59eb282bcbaade34eaba724c3f8332d4c8ae2e1b0c21dd9341891154b661`,
2,279 variables; 7,529 clauses) the optional native C++ MATH4 guard
produced an independently checked UNSAT certificate.

- 1,750 source-entailed XOR equations were detected.
- 529 root assignments were independently derivable by original-CNF unit propagation.
- The verified contradiction uses 596 XOR equations and 172 such root assignments.
- On GitHub Actions run [43645811293](https://github.com/Frane12/AndroidGameTest/actions/runs/43645811293), native discovery took 0.010209 s and independent checking took 0.017125 s.
- The same original source under `--hall3 --pcmax-only` returned UNKNOWN in that paired smoke; MATH4 returned verified UNSAT.

This is a **new, independently checkable proof path on a real CNF**;
it is **not** a new general SAT algorithm, proof of polynomial SAT solving,
or evidence of globally superior competition speed.

## Soundness argument

For each claimed XOR row on variables (S), the checker demands that
**every** original CNF clause excluding assignments with one chosen parity
is present. Those (2^{|S|-1}) source clauses entail a parity equation
over (GF(2)).

For every claimed root assignment, the checker **independently recomputes
unit propagation from the original CNF** and accepts only assignments that
are actually forced.

If an explicitly listed collection of such source-derived XOR equations
and forced assignments has zero variables after XOR summation and
right-hand side 1, then it derives (0=1) and the original formula
is unsatisfiable. The proof has no dependencies on the native producer's
heuristics, clause learning, solver result, or official catalog label.

The certificate format is `drnas-math4-xor-unit-v1`, checked by
`research/math4/check_xor_units.py`; it is **not DRAT/LRAT**.
Mutated source hashes, flipped parity, omitted XOR rows and inverted units
are rejected by regression tests.

## Native architecture

- Compiled into the **same CF7 process and one logical CPU**.
- Explicit opt-in `--math4` before HALL3, then unchanged CF7 CDCL fallback.
- The algebra stage has an upper wall budget of 0.23 s, also bounded by
  35% of the optional guard's budget; fallback gets the remaining budget.
- Conservative gates: <=6,000 variables; <=100,000 clauses;
  <=1,500,000 literals; XOR support width 2–6; <=4,096 detected XOR rows.
- Unsupported, over-budget or incomplete proof yields UNKNOWN or normal
  CDCL fallback, never a guessed SAT/UNSAT decision.
- Files and reports live on experimental branches; the repository's
  `main` and frozen reference binaries are unchanged.

## Evidence and limitations

- [24-original-source read-only algebra audit](https://github.com/Frane12/AndroidGameTest/actions/runs/43645009195):
  7 of 24 have fully identifiable XOR source constraints, but only
  combining them with source-derived root units produced a contradiction
  in the investigated cases.
- [Independent Python-source proof](https://github.com/Frane12/AndroidGameTest/actions/runs/43645444390):
  one original lights-out UNSAT certified, four other examined sources UNKNOWN.
- [Native CF7-integrated proof and fallback smoke](https://github.com/Frane12/AndroidGameTest/actions/runs/43645811293):
  new lights-out source-certified UNSAT; SAT fallback and old Hall regression pass.
- Broad PAR2 runs must score **solve + independent checker E2E** and penalize
  timeout, bad proof, and missing certificate as unsolved.
- The 24-original retrospective Main Track subset is already studied.
  A separate precommitted, source-disjoint 15-source catalog set is on
  `experiment/drnas-math4-unseen15-original-20261114`. Its outcome must
  not be assumed before the independent run finishes.

## Reproduce

Build (experimental branch only):

```sh
g++ -std=c++20 -O3 -DNDEBUG -Wall -Wextra -Wpedantic -Werror \
  -DDRNAS_PCMAX_MODULE src/drnas_hall3.cpp -lcrypto -o build/drnas-math4
```

Run `build/drnas-math4 INPUT.cnf --mode core --time 7 --math4 --pcmax-only --pcmax-budget-ms 750 --pcmax-certificate NEW_CERTIFICATE.json`
and validate the output with
`python3 research/math4/check_xor_units.py INPUT.cnf NEW_CERTIFICATE.json`.

Research note: this is structural proof discovery, not a claim of a newly
invented mathematical theorem; GF(2) elimination and unit propagation
are established techniques. The contribution under test is their safe,
automatic discovery and coupling from unmodified original CNF clauses.
