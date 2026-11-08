# DRNAS MRE6 — CPU feedback guides construction of new mathematical reductions

**Date:** 2026-11-08
**Branch:** experiment/drnas-mre6-cpu-feedback-principles-20261108
**Workflow:** .github/workflows/drnas-mre6-quotient-feedback.yml

## Research question

Do not optimize merely the *number* of mathematically proven extra CNF clauses,
new bounded UP implications, or solver decisions. Optimize whether a certified
representation change saves actual native solver CPU while preserving an
original SAT witness, deducting extraction, proof, transformation and
reconstruction costs before making a practical deployment claim.

## Feedback data flow

1. Read exact prior MRE5 pinned source/seed measurements (32 trials) from
   GitHub Actions #42490090624. These are calibration data, never holdout.
2. Commit a machine-readable CPU-feedback ledger to an SQLite experiment
   artifact: one row per source SHA/seed/repeat/arm/telemetry setting,
   identifying CPU seconds, solver wall seconds, native decisions, conflicts,
   propagations, scans, direct watched-clause units and proof metadata.
3. Aggregate *paired* CPU savings vs CMS+XOR with watcher pressure and
   decision savings as explanatory secondary metrics, not as the sole reward.
4. Freeze the activation policy **BEFORE** opening new trial outcomes. The
   initial policy is XOR-only because only one source exists, with two
   native seeds and mixed/negative CPU effects. Recommending a reduction for
   an unseen problem based on its actual CPU performance is prohibited.
5. Validate newly derived principles on four different, deterministically
   SHA-locked native seeds, two repetitions each, seven arms, with separate
   trace-ON/-OFF controls. This is an unseen-SEED evaluation, **not**
   an unseen-FORMULA evaluation.
6. Audit every original SAT witness and every paired run and append results
   to the SQLite feedback base and final JSON report.

### Policy for eventual automatic activation

To avoid cherry-picked optimization, require at least three mutually
source-disjoint training CNFs with three native seeds each and at least
3% CPU savings even in the worst source/seed pair, then validate on
completely untouched official SAT problems. Until then the live gate
falls back to CMS+XOR. This threshold is an experimental safeguard,
not a theorem that predicts CPU savings.

## New mathematical candidate: proof-certified equivalence quotient

The original SAT2026 source CNF
official-28dcc4119e1bbb5fbd3fdd8f4140f28d.cnf, SHA256
b2c2008e5d24a7aa82499d1486af2550a53a7167e46836c4b9977846204ad483,
entails two replay-certified binary clauses:

- A: (not x12 OR x224)
- B: (x12 OR not x224)

Together they prove x12 = x224. Instead of adding A and B to the
watched-clause sets, MRE6 replaces each occurrence of x224 with x12
throughout the original CNF. This is a quotient / elimination of
an equivalent variable, not an arbitrary heuristic rewriting.

Certified source GF(2) / XOR rows are simultaneously transformed:
identical variables cancel modulo 2; empty true equations are
discarded, empty false equations fail closed, and one-variable rows
become CNF unit constraints.

Canonicalize duplicates and tautologies separately. Include a
**canonical-only, no-quotient control** so that removing duplicates
cannot be mistaken for gains due specifically to variable merging.

During SAT model verification, set reconstructed x224 = solved x12
and check ALL original SHA-locked clauses. The native CryptoMiniSat
bridge also verifies its own transformed input. No original constraint
is silently dropped without a proved equivalence and model lift.

## Seven matched arms

1. Original CMS + certified source XORs (baseline)
2. Original + certified binary lemma A
3. Original + certified binary lemma B
4. Original + both A+B
5. Canonical original CNF only (remove tautologies and duplicates)
6. Quotient x224:=x12, plus transformed original XOR rows
7. Same quotient without imported XOR rows (causal XOR ablation)

All use the exact same previously pinned, CPU-instrumented
CryptoMiniSat 5.11.15 library with on-the-fly Gaussian disabled.
All source formulas, seeds, source proof metadata and native build hashes
are checked. No new native C++ compilation is necessary; reuse MRE5
binary/input artifacts.

## Limitations

- Only one previously used SAT2026 source is tested in this exploratory
  pilot. Four new seeds are a narrower, non-independent holdout.
- Solving CPU excludes the up-front MRE1 extraction, replay and CNF
  transformation, so a useful real-world deployment must pay those costs.
- CPU changes include altered search order; a measured difference does
  not allocate exact causal nanoseconds to one individual watcher.
- No independent UNSAT LRAT proof is available in this SAT-only pilot.
- No new formula class becomes "certified to accelerate" until a
  source-disjoint, independently audited validation.

## Scientific importance

The feedback loop is intended to generate the next *mathematical
representations*, not just tune clause-import thresholds. A reduction
that removes whole equivalence classes of variables or constraints may
do better than adding redundant logical facts to a conventional CDCL
solver. This is a testable hypothesis, not a claimed speedup.
