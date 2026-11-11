# DRNAS ATLAS1 — exact local Boolean equivalence (experimental)

**Status:** experimental only; no changes to the stable solver or frozen ARL baselines.

## Objective

Precompute a reusable atlas of all Boolean functions with two to four inputs,
identified by input permutations, input negations and output negations (NPN).
The catalog generator constructs 4, 14, and 222 NPN classes, respectively.
For each canonical representative, store **two distinct** equivalent CNF
recipes: for the representative and for its Boolean complement. Output
negation is NOT an equivalence of SAT constraints; it only selects a different
fully verified recipe before exact input reorientation.

## Soundness

* All candidate rewrites operate on a **complete set of selected ORIGINAL CNF
  clauses** whose variable support is contained in 2–4 variables.
* Build the conjunction truth table; select the atlas recipe; map back through
  the recorded permutation and signed input polarity; verify all 4, 8, or 16
  assignments for exact equality before changing a clause.
* A replacement must not increase the number of clauses and must save at least
  one literal. All unrelated clauses remain unchanged. The original variable
  set is preserved. Thus neither satisfiability nor the full set of satisfying
  assignments is changed.
* No deduction is accepted from NPN class ID **alone**.
* The executable's `--atlas-selftest` exhaustively verifies **65,808**
  reconstructed truth tables; the generator also independently checks every
  stored canonical recipe.
* On SAT, check the returned assignment against **original CNF**; UNSAT does
  **not** have independent LRAT certification and is not claimed as certified.
* Under budget failure or lack of profitable patterns: **SLEEP** and run native
  CDCL unchanged. One bounded preprocessing cycle, no repeated probes.

## Scope and limitations

The first implementation scans at most 1,400 original clauses, considers
2–4-variable modules and applies at most one locally profitable transformation,
with a 0.75 ms probe cap. It is deliberately conservative and cannot discover
all mathematically possible reductions. The generator's greedy CNF covering
procedure is exact in semantics but **not guaranteed to yield a minimum CNF**.
The atlas is not a general proof that preprocessing accelerates all formulas.

NPN class IDs are diagnostic metadata, not an instruction to flip the output of
a constraint. The changed CNF and original CNF must remain logically equivalent
over the same variables; SAT witness reconstruction is unnecessary for this
particular type of local rewrite.

## Reproduce

```sh
python3 research/drnas_atlas1_generate.py --out mre_atlas1/atlas1_table.hpp
mkdir -p mre_atlas1/bin
g++ -std=c++17 -O2 -I mre_atlas1 research/drnas_atlas1.cpp -o mre_atlas1/bin/drnas_atlas
mre_atlas1/bin/drnas_atlas --atlas-selftest
python3 research/drnas_atlas1_smoke.py
mre_atlas1/bin/drnas_atlas original.cnf --mode ATLAS1 --time 30
```

`drnas-atlas1.yml` compares `A` (exact same native solver without atlas)
against `ATLAS1`, pinned Kissat, and installed CaDiCaL on four original
SATLIB SHA-locked source-selected rank-14 formulas:
`uf100-430`, `uf150-645`, `uf200-860`, `uf250-1065`.
Three matched repetitions, 30-second caps, one logical CPU per solver. Compute
PAR2 as observed E2E seconds for solved trials and 60 s for an UNKNOWN trial.
Only separately verified original-model SAT outcomes count as solved.

This benchmark is a first **feasibility/soundness** study, not a statistically
powered conclusion about improvement. Stronger evidence requires more frozen,
unseen, especially **structured** formulas where recurring Boolean blocks exist.

Background: 4-input NPN equivalence classes and Boolean matching (e.g.,
`https://apetkovska.gitlab.io/papers/sat16-satnpn.pdf`); SAT preprocessing
overview `https://fmv.jku.at/papers/BiereJarvisaloKiesl-SAT-Handbook-2021-Preprocessing-Chapter-Manuscript.pdf`.
