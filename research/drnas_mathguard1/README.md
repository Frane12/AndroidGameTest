# DRNAS MATH-GUARD1 — proof-first CDCL experiment

Status: experimental, no measured speed claim.

Goal: extract cheap **proven** consequences of the original SAT formula before expensive CDCL search, using only one native solver process on one pinned logical CPU.

## Mathematics

For two original clauses (p OR A) and (not p OR B), the resolvent (A OR B) is entailed. The guard creates only new non-tautological unit or binary resolvents. Each is a RUP-compatible proof step, injected into the same CDCL clause database. Root contradictions can prove UNSAT; structural scores and timeouts NEVER do.

The pass is opt-in via --math-guard and defaults off. Hard caps: at most 12000 scanned originals, eight parents of each polarity per pivot, 40000 parent pairs, 128 learned short clauses and approximately 4 milliseconds of bounded wall time. No second solver, no cloning or parallel computation.

This first iteration proves that in-solver reductions can be constructed and verified. It DOES NOT yet exploit the DELTA nonlinear structure mathematically; those signals are used only to define a relevant retrospective evaluation cohort. Direct short resolution is established mathematics, not a new theorem.

## Audit

Build: python3 research/drnas_mathguard1/build.py
Preflight: python3 tests/test_drnas_mathguard1.py
Run: build/drnas-mathguard1 source.cnf --mode core --time 10 --math-guard --math-guard-budget-ms 4 --stats --proof output.drat

The build preserves the native frozen X59 source file and creates a separate derived executable. Compare one identical executable with guard OFF versus ON. Check every model against the unchanged source CNF and every UNSAT proof with drat-trim. Use small independent exhaustive oracles and lemma-level RUP checks in preflight.

Real cohort: up to 12 original SAT2024 CNFs with a prior certified SAT/UNSAT solve and recorded nonlinear/nonaffine structural telemetry in DELTA4, two repeats per arm, 10-second cap. Prior TIMEOUT/UNKNOWN examples are not credited as previously solved. The cohort is retrospective, not blind, so there is no promotion without fresh holdout validation.

Report verified PAR2, wall and CPU time, max RSS, guard lemma activity, both-verified paired speedups and any regressions. If no qualifying source exists, report zero rather than invent a result.

Branch: experiment/drnas-mathguard1-proof-first-20261114. Do not modify main or frozen reference builds.
