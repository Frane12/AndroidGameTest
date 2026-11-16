# DRNAS STRUCTURE-1 — MATCH-1 and INTEGER-PARITY-1 (2026-11-16)

Status: **experimental source-bound Python prototype**. Frozen base:
`experiment/drnas-ipg2-poly-classes-20261116`; this branch does
not modify `main`, DRNAS reference builds or C++ solver.

## MATCH-1 (Hall resource shortage)
Recognize original DIMACS clauses with disjoint positive ALO selector
groups of equal width r (positions represent resource slots). For every
pair of jobs and each slot s, an original negative binary clause
`(-x[j,s] -x[k,s])` is REQUIRED. Original negative unit clauses
`(-x[j,s])` exclude resource choices. If some set S of jobs has fewer
allowed resources N(S) than jobs, source CNF is UNSAT:

  |N(S)| < |S|.

The producer finds an alternating-tree Hall witness after bipartite
matching. An independently implemented source checker verifies all ALO
and cross-job mutex clauses, original forbidden units, SHA-256, and Hall
deficiency. False classifications are prevented by returning UNKNOWN
if the strict positional decoder fails.

This does NOT yet reconstruct arbitrary permutation-insensitive slot
mappings, generic Hall encodings, or the earlier 300-clause PCMAX CNF.

## INTEGER-PARITY-1 (exactly-one versus even XOR)
For a positive ALO group of 2..7 Boolean selectors, verify original
negative pairwise AMO clauses, establishing exactly one true. Separately
verify all original full-width clauses blocking ODD-parity assignments,
which establishes even parity. Exactly-one is odd, so the source
is UNSAT. Each required blocking clause is independently rechecked
against the original DIMACS; source SHA mismatch rejects the proof.

This is a bounded *joint* structural detector, not a generic modular
linear-integer + GF(2) conflict engine. More complicated projected XOR
and PB interactions remain future research.

## Test evidence and limits

`python3 research/structure1_bench.py`

Local baseline: 22 generated CNFs, 15 source-bound UNSAT certificates
accepted by an independent project checker, 7 SAT controls, 22 separate
tiny exact-DPLL oracle verdicts, and 8 forged/changed-source
certificates rejected. One logical CPU, deterministic seed. CI repeats
those checks and archives original DIMACS bytes and certificate JSON.
These are NOT official SAT2024/2025/2026 blind holdouts or PAR2 gains.

The project-specific witness checker is **not** a standard DRAT/LRAT/
VeriPB verifier. No claims of broad PCMAX applicability, P=NP, new
complexity-theoretic algorithms or superiority to Kissat/CaDiCaL/CMS
follow from these tests. Next stage is independent source-frozen
corpora, cross-encoding detection, proper standard certificate bridge,
and single-core C++ guard with strict time budget and fallbacks.

## Safety discipline

* UNSAT is surfaced only as `UNSAT_UNCHECKED` until source checker passes.
* Unsupported structure returns UNKNOWN. No SAT models are fabricated.
* Tests include missing mutex, missing XOR blocking clause, SAT control,
  falsified proof fields, source modification, and variable relabeling.
* No APK, no auto-promotion, no main change, no replacement of reference.
