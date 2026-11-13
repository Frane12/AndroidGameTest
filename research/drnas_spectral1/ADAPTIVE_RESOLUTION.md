# DRNAS SPECTRAL1C — adaptive discrete spectral resolution, residual CDCL

Status: implemented ONLY on experiment/drnas-spectral1c-adaptive-resolution-20261113.
No main modifications, no model promotion, frozen reference X5 untouched, blind holdout sealed.

## Mathematical definition

At a stable CDCL state with partial trail assignment α, choose a strictly
bounded window W of ORIGINAL CNF clauses. Apply α to every clause: delete
satisfied clauses, remove false literals from surviving clauses. Select
at most k unassigned variables and at most 10 residual clauses, all
within the local scope. For k <= 8 form the exact local indicator:

  f_(W|α)(x) = 1 iff all selected residual clauses are satisfied by x.

Compute the integer Walsh-Hadamard coefficients
  W(s) = Σ_{x∈GF(2)^k} f_(W|α)(x) (-1)^(s·x)

and the local effective GF(2) frequency rank
  r_spec = rank_GF2(span({s != 0 : W(s) != 0})).

A local high-order energy estimate may inform the variable branching
score ONLY if r_spec < k, nonconstant energy >0, nonlinear energy >0,
feasible assignments >0, and nonlinear mass >= 0.12.

The rank is LOCAL and does NOT imply the global problem was reduced
from n to r_spec variables. Spectral analysis neither claims SAT/UNSAT
nor produces learned clauses or proof steps.

## Adaptive resolution schedule

No analysis before 256 CDCL conflicts. On a stable BCP fixpoint:
- 256..1023 conflicts: local scope k<=4.
- 1024..4095: k<=6.
- >=4096: k<=8.
- If at most 128 free variables remain, cap k at 4.

Updates are spaced 256/768/1536 conflicts by difficulty, capped at
12 passes. Each pass samples at most 12 deterministic original-CNF
windows, each scanning at most 64 neighboring source clauses,
max 10 selected clauses and 8 independent unassigned variables.
A 1 ms per-pass and 10 ms cumulative analysis-time budget is
checked; 5 s solve-time limit still applies end to end.

## Same-binary isolation

SPECTRAL1C_OFF: untouched original X5-style solver path.
SPECTRAL1C_OBSERVE: computes conditional spectra and rank but does
not change branch scores.
SPECTRAL1C_ON: reuses exact same binary and sampled spectra to
apply bounded temporary VSIDS base-score adjustments, replacing
older bonuses each pass. SAT/UNSAT proof machinery is identical.

Immutable X5_FROZEN, Kissat and CaDiCaL are independent references.
All binaries frozen by SHA before the first trial. Each solver uses
one logical CPU, serial input execution, randomized arm order.

## Safety and statistics

The preflight must pass exact parity/OR Walsh mathematics and SAT/UNSAT
certification for 17 synthetic CNFs under all three modes. In actual
benchmark, every credited SAT model is checked against entire ORIGINAL
CNF, every credited UNSAT is independently DRAT verified. Contradictory
certified answers fail the run.

Retrospective development cohort: REAL36, SAT Competition 2024
original CNFs, 36 unique formulas from 7 families, 2 repetitions,
5 seconds per attempt; 6 arms and expected 432 paired attempts.
Never claim that this is a fresh blind holdout.
Summarize PAR2, solved counts, CPU/RSS, k=4/6/8 distribution, passes,
local ranks, conditioned literals, applied decisions and 95%
family-clustered paired CIs. Solver PAR2 and verification walltime
are separate. Report all regressions. Promotion is disabled.

## What would justify another experimental version

1. No regression in verified solved count in unseen distinct families.
2. Separately measure OFF→OBS overhead and OBS→ON decision benefit;
   do not attribute differences to spectral math until isolated.
3. If the phase-shifted spectrum helps, test conditional spectral
   variation over successive CDCL rounds without labelling this
   a proof of P=NP or general SAT complexity improvement.
