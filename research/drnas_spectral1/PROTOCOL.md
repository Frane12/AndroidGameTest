# DRNAS SPECTRAL1 — exact local Walsh guidance integrated into CDCL

Status: Experimental C++ branch, feature flag --spectral1.
Original frozen reference: X5_FROZEN. main, frozen binaries and sealed holdouts unchanged.

## Exact mathematics

For each local bounded subset W of clauses from the ORIGINAL CNF, with k<=8 Boolean
variables, define f_W(x)=1 iff ALL clauses in W are satisfied by x; else f_W(x)=0.
Compute exact integer Walsh coefficients W_W(s)=Σ_x f_W(x)*(-1)^(s·x).
No floating-point FFT, smoothing, training label, filename gate, or learned model.

The spectral support is S={s!=0 : W_W(s)!=0}. The GF(2) span rank
r_spec(W)=rank_GF2(S) measures the exact number of independent XOR coordinates
needed to describe the local satisfaction indicator. For parity across 3
variables W(0)=4 and W(111)=4, r_spec=1. For a 3-way OR constraint r_spec=3.

The hypercube graph Laplacian has eigenvalue 2*|s| for Walsh mode s.
The pure C++ module records Σ_{s!=0}2|s|W(s)^2 as a local spectral energy.
This is a DISCRETE graph Laplacian, not the continuous Laplace transform or
the Z-transform for time-series signals.

## Actual solver integration

- src/drnas_spectral1.hpp: pure exact local Walsh analysis, GF2 rank, high-order influences.
- src/drnas_spectral1.cpp: calls spectral1Preprocess in Solver::finishParsing before branching,
  and uses normalized high-order spectral energy to alter existing branch base scores.
- Same candidate binary OFF/ON, with only --spectral1 differing.
- No spectral deduction ever changes the CNF, adds a learned clause, or asserts SAT/UNSAT.
  Original CDCL conflict analysis and proof output remain in control.

Bounded costs: up to 64 evenly spaced local windows, each looking ahead at most
96 original clauses, keeping up to 12 clauses and 8 variables, each evaluated on
at most 256 assignments. Skip source variables >1,000,000. Spectral bonus per
variable capped at 0.75; preprocessing is included in runtime and timeout.

Caution: r_spec(W) measures a LOCAL function only, not the whole SAT formula.
Low rank does not prove easy SAT; overlapping windows can double-count patterns.

## Verification

Workflow: .github/workflows/drnas-spectral1-walsh.yml

(1) Compile C++20 -O3 -Werror; frozen binary and original-CNF SHA checks.
(2) Exact math test: parity rank1, OR rank3, Boolean 0/1, Laplacian energy,
    constant and contradiction, invalid local variable scope.
(3) 17 small planted/contradictory formula tests, same-binary OFF vs ON;
    every reported SAT model checked on FULL original CNF, every UNSAT
    independently checked via DRAT; a parity case must exercise spectral analysis.
(4) Retrospective SAT Competition 2024 REAL36 (36 original formulas, 7 families);
    two repetitions at 5 seconds with one logical CPU per solver and five arms:
    X5_FROZEN, SPECTRAL1_OFF, SPECTRAL1_ON, Kissat and CaDiCaL.
    Expected 360 attempts, 72 per arm.
(5) Report verified PAR2, distinct solved sources, proof check, maxRSS,
    source/family bootstrap 95% intervals, active/reduced-rank windows and
    preprocessing overhead; no invented outcomes, no automatic promotion.

No 2025 results are pooled with 2024. This is retrospective development,
NOT an independent fresh blind holdout. Further model promotion requires
separate precommitted truly unseen family-disjoint validation.

## Next experiment

If the first A/B shows evidence of benefit:
- conditional local Walsh transform after CDCL assignments (new bounded experiment);
- compare score construction vs purely observational spectrum;
- estimate true value of r_spec, high-order Fourier mass and preprocessing cost;
- introduce XOR deductions only with independent proof certificates and
  unchanged SAT/UNSAT soundness constraints.

Do not claim a complexity breakthrough or performance improvement until
complete frozen paired verified data demonstrate it.
