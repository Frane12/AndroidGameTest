# DRNAS RIT2 — source-locked relation intersection screening (2026-11-09)

Branch: experiment/drnas-rit2-original-sha-screen-20261109.
This is ONE isolated diagnostic experiment. It never launches Kissat, CaDiCaL or CDCL.
It does not change original DIMACS, stable binaries, main, or reference proofs.

## Original input and classification

- Exactly 24 unique original SHA-256 inputs from immutable completed X22 Actions
  run 42591977333, artifact `x22-frozen-originals-and-cpp` (11.52 MB).
- Their sources were used earlier by X21/X22 and X24. They are **seen development replay**,
  not new official blind holdout. Never report selection on these as blind speedup.
- Validate X22 manifest provenance and sha256sum before and after screening;
  reject duplicate/missing original SHA. No original formulas in final artifact.

## Deterministic scan

Two shards x twelve distinct source SHA, one measurement per source (no seeds or CDCL).
Bounded 9-second analysis per case, at most 4,096 extracted source relations, 12,000
pivot-pair combinations and 24 original-CNF RUP candidate checks.
Any limit is represented as incomplete/truncated and is NOT silently a negative result.

For each case record:
- Original variable/clause/binary counts and SHA.
- Exactly source-derived complete 2/3-variable XOR equation counts.
- Signed binary implication SCC equivalences and exact/opposite equation overlaps.
- Variable-level overlap, each side's GF(2) rank and joint rank, contradiction signals.
- Algebraically implied short clauses found in the limited closure, including
  *joint-only* consequences absent from GF(2)-only **and** SCC-only spans.
- Separate original-CNF RUP checks for each candidate, pass/fail, checked count.
- Elapsed analysis time, completeness flags, reason for any timeout, up to 8 example lemmas.

Joint-only algebraic is not automatically RUP. Some mathematically justified XOR
consequences require stronger-than-UP proof. Never count RUP-rejected or unchecked
clauses as appended to a solver.

## Output and next decision

A small JSON + CSV per-source table, summary counters, and source-SHA-ranked candidates;
select up to six completed cases with actual joint-only RUP lemmas.
If zero, report zero; do not cherry-pick synthetic cases or start expensive E2E testing.
The rank is a *screening score*, not evidence of SAT speedup.
No E2E/PAR2/solved/timeout figures can be inferred from RIT2. SAT/UNSAT = NOT_RUN;
independent UNSAT LRAT = false. Full LRAT pipeline and prospective unseen holdout
are later, separately preregistered experiments.
