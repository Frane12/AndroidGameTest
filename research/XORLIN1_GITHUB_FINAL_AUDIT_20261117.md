# DRNAS XOR-LIN1 — completed GitHub CI independently certified original CNF result

**Completed GitHub Actions run**:
https://github.com/Frane12/AndroidGameTest/actions/runs/44053818490

Date: 2026-11-17. **All seven jobs successful** (prepare,
paired shards 0–4 and final aggregate).
The run used SHA-pinned originals and reference solver/verifier
binaries from original frozen run 44049316105. No changes to
main, older source archives, APK, or original solver binaries.

## Final STRICT external-proof-checked E2E score

10 original SAT-competition GBD CNFs × 2 repeats × 6 serial solver
arms = **120 completed trials**. Each solver had exactly 8 seconds
wall-clock, including original SHA verification, solver startup,
source-only GF2 detection (on XORLIN1), independent source
checker, PBP emission, external VeriPB acceptance, DRAT/FRAT or
SAT-model verification. One logical CPU per trial, no parallel
portfolio within an arm. Timeout/unsupported/unverified=PAR2 16s.
Final aggregate critical errors: **0**.

| Arm | Strict source-verified /20 | Distinct sources | Strict PAR2 (s) |
|---|---:|---:|---:|
| **XORLIN1_SOURCE_ONLY** | **18** | **9** | **36.403869** |
| XOR234_NATIVE_VERIPB | 12 | 6 | 131.947587 |
| Kissat | 2 | 1 | 288.259969 |
| CaDiCaL | 2 | 1 | 288.239807 |
| CryptoMiniSat | 2 | 1 | 288.358116 |
| X59_MATH5_VERIPB (old EO-only export) | 0 | 0 | 320.000000 |

**Strict PAR2 reduction on this set:** 87.3703% vs
best reference CaDiCaL; 72.4104% vs prior native XOR234.
These are end-to-end paired scores on an already-studied
retrospective source set, **not** a new blind or universal solver
performance claim.

The entire 9-source proof set was independently accepted by
**VeriPB 3.0.2**, from ORIGINAL unmodified CNFs, in both
repetitions. The source-only detector found the exact GF(2)
contradictory combinations by grouping all original
forbidden-assignment CNF clauses and performing Gaussian
elimination with original row selection provenance. No native
MATH5/any competing solver output was needed by
\`XORLIN1_SOURCE_ONLY\`.

**ID6** from the same source archive remained
\`XORLIN1_SAFE_UNKNOWN\` twice. It is a different very large
13,313-variable /26,968-clause source whose exact clause
support did not yield complete XOR2..6 groups under the
bounded source-only extractor. This is correct UNKNOWN,
not UNSAT or SAT.

Most important generality extension beyond earlier
source-only exact-two-incidence:
- GF(2) finds any source-supported subset whose XOR sum
  is 0=1 rather than depending on all source XOR rows.
- The standard VeriPB compiler supports source XOR
  widths 2,3,4,5,6 by RED XOR extension and RUP
  original-source-derived reductions.
- Even incidence 2,4,6,... rather than only incidence 2
  suffices for the proof's final cutting-planes division.
- 24/24 synthetically contradictory systems with unrelated
  XOR rows produced accepted VeriPB proofs;
  48 explicit SAT control models returned UNKNOWN;
  a degree-four K5 support accepted direct and selected
  source proof; forged SHA was rejected.

## Honest significance and next test

This experiment **began after** inspecting the previous
results on these exact ten originals. Accordingly this is
**retrospective development**, even though source hashes
were originally frozen before the prior XOR234 run.
It verifies correctness and improved E2E performance on
the exact development examples; it does not establish
prospective improvement on unseen SAT competition problems.
All ten sources also belong to one broad Tseitin
graph family, so no family-cluster statistical
generalization conclusion is justified.

Preserve this experimental branch and benchmark as the
frozen engineering reference. Next choose a new group of
original CNFs by GBD metadata only, SHA-freeze selected
sources *before* any XOR-LIN1 evaluation, and compare
under identical 8s/30s proof-inclusive caps with current
Kissat/CaDiCaL/CryptoMiniSat. Add true SAT controls and
XOR-coded inputs that cannot be detected as complete
forbidden-assignment clause blocks.

Run artifact: \`xorlin1-original10-final-strict-E2E-PAR2\`.
No automatic promotion to main.
