# DRNAS MRE6f — real 35-second SAT2026 benchmark

Date: 2026-11-08.
Experimental branch: experiment/drnas-mre6f-medium-certified-equality-20261108.
Actions workflow: .github/workflows/drnas-mre6f-medium-cert-equality.yml
Run: https://github.com/Frane12/AndroidGameTest/actions/runs/42503866092

## Purpose

Follow up the MRE6e diagnostic (56/56 short 1000/5000-conflict probes,
all CDCL-budget UNKNOWN) with a **real full-solving** benchmark where
some official SAT2026 CNFs are confirmed feasible within a moderate
35-second budget. Preserve all source-disjoint labels and exact source
SHA from the successful MRE7 completed run #42500214333.

## Frozen sources and comparison protocol

- 6 official SAT2026 source CNFs, 3 SAT and 3 UNSAT.
- 2 labeled *reused MRE7 diagnostic* source anchors, confirmed solvable
  using CMS in MRE7 (not blind evidence).
- 4 labeled *precommitted 0.75–15s officially externally reference-timed*
  source CNFs, drawn from the official competition and frozen in MRE7.
  These four were not chosen by MRE6f or its observed runtime.
- SHA verification at preparation, within each shard and during audit.
- 2 paired native solver seeds per formula and 4 configurations per seed:
  6 × 2 × 4 = **48 full solve trials**.
- 35.0s strict total wall budget per trial, including source parsing,
  proof check, XOR scan, variable-quotient rewrite, CMS solve, model
  lifting and original-CNF SAT witness verification.
- PAR2 = actual wall seconds if solved, 70s per timeout.
- Same pinned source revision of CryptoMiniSat 5.11.15
  (upstream SHA 3b709118fd08eb1d15f25e0e239dbc596f967b60),
  OTF Gaussian disabled for all four arms, same native seed on every
  four-way source/repetition comparison.
- Native CPU seconds, decisions, conflicts and propagations are reported
  for completed solves only; never infer them from timed-out attempts.

## Four methods

1. `native_no_xor`: original CMS, no optional source XOR import.
2. `source_xor`: original CMS with mathematically replay-verified CNF
   parity source XOR rows, size-gated by <=35,000 clauses.
3. `all_eq_no_xor`: find ALL original CNF binary implication pairs
   `(¬a∨b) ∧ (a∨¬b)`, certify each, take transitive closure by
   union-find, quotient equivalent variables and reconstruct original
   SAT models.
4. `all_eq_plus_xor`: same all-class quotient, plus verified original
   parity XOR source rows transported through the quotient.

The two equality modes abstain when no certified class is detected.
Large source CNFs intentionally abstain from heavyweight preprocessing.
All such abstentions and their CPU costs are INCLUDED rather than
discarded.

## Prior evidence guiding the design

MRE6e's short bounded probes had zero SAT/UNSAT solves by design, so
its PAR2 is not a valid indication of solver performance. MRE7 solved
36/48 full-solve attempts on this six-source cohort, including all
16 trials on a medium two-source shard. This makes MRE6f more
informative than the earlier 7-source holdout that timed out in 56/56
18-second runs.

## Safety and scientific limitations

- This is a targeted *development diagnostic* and reuses MRE7's original
  formulas; it is NOT a fresh or purely blind holdout.
- Each quotient is justified by two clauses already present in the
  ORIGINAL CNF; no unproved eliminations allowed.
- SAT models must be independently reconstructed and checked against
  the exact original source CNF. UNSAT is checked against published
  official status but no independent LRAT proof is supplied.
- Benchmark data do not authorize promoting a production CPU-aware
  selector. First confirm stable results on new original sources and
  verify full preprocessing overhead and source-disjoint behavior.
