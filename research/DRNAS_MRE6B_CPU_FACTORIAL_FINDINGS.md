# DRNAS MRE6b — 2×2 CPU interaction between equivalence quotient and source XOR import

**Date:** 2026-11-08
**Branch:** experiment/drnas-mre6-cpu-feedback-principles-20261108
**Original CPU work:** https://github.com/Frane12/AndroidGameTest/actions/runs/42492134752
**Successful independent 48-trial audit:** https://github.com/Frane12/AndroidGameTest/actions/runs/42492372821

Exactly 48 SHA-locked original SAT witness-checked attempts were completed:
4 known *MRE6* seeds × 2 repetitions × 4 factorial arms with trace OFF,
plus 1 trace-ON run per seed/arm for native watched-clause telemetry.

The original workflow had a technical failure in its after-run log
capture (tee opened a non-existing mre6b directory); every trial's JSON
was still saved and uploaded. The separate audit-only workflow downloaded
all 48 trial JSON entries, verified the pinned source and original SAT
models, produced complete summary and appended the factorial interaction
evidence to the MRE6 SQLite database. **No trials rerun for audit**.

This is one REUSED official SAT2026 CNF, not a source-disjoint holdout.
All statistics below report native CPU around cms.solve() only. Proof
replay, quotient creation and SAT model reconstruction need separate
end-to-end CPU charging for practical deployment.

## Native process CPU seconds — four matched combinations

| Original vs certified quotient | Source XOR absent | Source XOR imported |
|---|---:|---:|
| Original CNF | 68.924340 s | 59.040792 s |
| Certified x224:=x12 quotient CNF | **53.296790 s** | 61.438010 s |

Four seed values, two repeats each per cell (8 OFF trials); all original
SAT models independently reconstructed and checked. Same pinned
CryptoMiniSat 5.11.15 library, OTF Gauss off.

**Causal factorial comparisons within the same GitHub run:**

- Quotient saves 15.627550 CPU seconds, or **22.67%**, relative to
  ORIGINAL without imported source XOR. Wins on all four seeds.
- Quotient ADDS 2.397218 CPU seconds, or **4.06%**, relative to
  ORIGINAL with imported XOR rows. Loses on all four seeds.
- Quotient WITHOUT source XOR import beats the practical XOR-only
  reference by 5.744002 CPU seconds, or **9.73%**.
- Positive original-CNF source XOR effect:
  68.924340 - 59.040792 = 9.883548 CPU seconds saved.
- For the quotient representation, adding source XOR rows is harmful:
  61.438010 - 53.296790 = 8.141220 CPU seconds ADDED.
- Difference-in-differences on the quotient CPU benefit:
  (original+XOR - quotient+XOR) -
  (original-noXOR - quotient-noXOR) =
  **-2.253096 seconds per run**, consistent in all eight paired
  repetitions. This represents a strong adverse representation ×
  backend-feature interaction on this original CNF.

The signed interaction is computed from the paired four-way CPU times,
not from biased across-workflow comparisons.

## What exactly was the new mathematical principle?

From MRE1 original-CNF proof-replayed CNF clauses
(-x12 OR x224) AND (x12 OR -x224), obtain equality x12=x224.
Use this equality as an equivalence-relation quotient:
substitute x224:=x12 throughout original CNF, then reconstruct the
removed original model value (x224 <- x12) after SAT solving and verify
the entire source SHA-locked CNF. For GF(2) imports, substitute
variables and cancel mod2; the no-XOR arm safely omits optional source
XOR rows while keeping the original CNF semantic constraints.

On this source the quotient changes only 8 original literal occurrences,
with no decrease in total 8933 CNF clause count and no changed number of
150 source XOR rows when they remain imported.

## Why this matters for CPU-guided mathematical principle construction

**A mathematical reduction is not a universal speedup.**

The value of certified equivalence depends on its **transport into the
target solver's active representations and heuristics**. Rewriting
CNF and separately importing equivalent source XOR structures may
cause counterproductive work. Hence the principle generator should
produce and rank not only a reduction's mathematical relation but also
a COMPATIBLE backend configuration, e.g.:

1. Proof-certified equality quotient + optionally suppress redundant
   imported source XORs.
2. Proof-certified equality as two cooperating binary implications.
3. No transformation (safe baseline fallback).

Record feedback for pairwise representation interactions, rather than
treating every candidate and source-XOR switch as independent.

## Safety and scientific limitations

The source has already been used extensively in MRE2 through MRE6;
four distinct new-to-MRE5 native seeds DO NOT constitute four
independent SAT formulas. The source-specific CPU feedback is safe
to use as an offline generator of hypotheses, but cannot be enabled
as a general new-problem routing policy without truly source-disjoint
training and unseen SAT2026 formula holdouts.

No world-record or general solver superiority is claimed. Correctness
of this SAT source is established by original SAT model reconstruction.
UNSAT proof LRAT is not assessed in this SAT-only pilot.

The next priority is one or two source-disjoint official SAT2026
formulas with similar certified equivalences, plus explicit
time/cpu accounting for extraction, proof replay and rewriting
against the strongest available same-config baseline.
