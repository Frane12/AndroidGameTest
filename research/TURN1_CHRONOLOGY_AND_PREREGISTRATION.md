# DRNAS TURN1 — chronology and radical representation pivot

Date: 7 November 2026. Experimental only; stable solver unchanged.

## Why change direction

| Period / experiment | Evidence and limitation | Decision for TURN1 |
|---|---|---|
| 31 Oct, v5/v6 structural decomposition | v5 hybrid 4.59 times slower on 40 synthetic formulas. Native v6 removed process overhead but 28 modular formulas remained 3.24 times slower; incremental control 2.11 times slower. Separate subproblems lost useful shared search. | One solver invocation per attempt. |
| 1 Nov, v16.5 | Historical discussion reports 6/12 solved for both; selected examples faster but overall PAR2 about 1.6% worse. This row is conversation history, not a newly reaudited artifact. | No cherry-picking large single-instance ratios. |
| 2–3 Nov, early dynamics / R27b | Audited 720 attempts: guarded restart 109.416983 PAR2 seconds versus monitor 104.523776; worse overall. One selected XOR case regressed into timeout. | No learned/threshold restart selector or disruptive restart. |
| 3 Nov, R28–R32k | Exact parity route is powerful in its domain. R32k: same certified units help one case and harm another; fewer conflicts need not mean less wall time. | Do not assume mathematical information is useful search information. |
| 4–6 Nov, XOR specialization / ORION | Manuscript records R115 SAT in 0.002465–0.003064 seconds versus both references timing out at 60 seconds; valid censored lower bounds on one parity source. Mixed-residual transfer remains unproved. | Keep specialization evidence separate from general SAT improvement. |
| 7 Nov, TA3/R199 | Recovered SAT2026 TA3 PAR2 1582.844897 versus Kissat 1705.965230 and CMS 1723.827576, but known R115 source is present and bootstrap includes 1. A routing error costs roughly 31 times on another source. | Remove the learned choice of backend from the new primary contrast. |
| 7 Nov, TA7 | Final 576 attempts: TA7 guarded 2498.16305 versus TA3 2498.023082 seconds; zero changed decisions. TA6 2412.742584 on the same evaluation cohort is an encouraging secondary result, not a universal gain. | Additional structural scans can merely add overhead. |
| 7 Nov, TA8 | Final 144 attempts: active certified pretest 419.95115 versus TA3 419.810491 PAR2 seconds. Zero certified hits/shortcuts; both 4/24 solved attempts. | Stop spending this experiment's budget on another XOR gate. |
| 7 Nov, TA7H60 | Final 144 attempts: Kissat 4/24, 2478.174331 PAR2 seconds; TA3 2/24, 2642.511858; CMS 0/24, 2880. Longer time alone does not repair routing. Generic UNSAT was not independently LRAT checked. | Use a 60-second cap and retain all timeouts. |

## New falsifiable hypothesis

A fixed bijective change of representation may alter CDCL preprocessing, tie-breaking,
initial polarity and subsequent search enough to improve time to solution, without
extracting XORs or adding lemmas. This is a different experimental axis, not a claim
that variable renaming or clause permutation is a new algorithm.

Each attempt uses exactly one unmodified backend invocation. A fixed permutation
renames variables and independently flips their signs. Another fixed seed shuffles
clauses and literals. The mapping is invertible; an independent inverse replay
compares the complete original clause multiset, including duplicates and empty clauses.
No clauses or variables are added or removed. SAT assignments are mapped back and
checked against every original clause. A second parent check validates the saved model.

Six frozen arms: native Kissat, native CMS, Kissat signed renaming, Kissat order-only,
Kissat both, CMS both. Main comparison: **Kissat both versus native Kissat**.
Other comparisons are exploratory and cannot replace a failed primary result.

## Frozen protocol

- First 12 next eligible originals from the existing frozen 400-source SAT2026 queue.
- Exclude source IDs and SHA values from R189, R199, TA3, SAT2026 TA3, R200, TA6,
  TA7, TA7H, TA8 and the existing excluded-hash list. This enumerated exclusion is
  not evidence of global blindness; other historical experiments may have seen a source.
- Eligibility uses source identity, size and valid DIMACS only, never observed runtime.
- 6 arms × 12 originals × 2 repetitions = 144 paired attempts; each original stays
  on one runner. Twelve shards, at most six concurrently. All attempts within a
  runner execute serially on one pinned CPU inherited by children.
- Every attempt has one 60-second parent wall deadline covering Python worker startup,
  DIMACS parsing, transformation, inverse replay, writing, backend execution,
  model inversion and original-clause verification. Parent kills the whole process
  group at the deadline. Additional parent verification is outside scored time.
- Same fixed transformation seeds across sources and repeats; no seed search.
- Source, code and binary hashes pinned before benchmark trials. Preparation smoke
  tests use only toy SAT/UNSAT formulas.
- Primary performance signal requires >5% total PAR2 improvement, source-bootstrap
  lower 95% ratio >1, no fewer solved attempts and at most one source with >10%
  summed PAR2 regression. Report 5,000 source-cluster bootstrap samples and all losses.
- Generic UNSAT results are backend/exit and cross-arm consistency checked, without
  an independent proof checker. Therefore this experiment cannot promote a solver.
- A green CI run means protocol completion, not a performance win.

## Sources reviewed

- v6 report: https://github.com/Frane12/AndroidGameTest/actions/runs/41189605621
- R27b: experiments/drnas_v16/R27_GENERALIZATION_FINDINGS.md (run 41609273740)
- R32k: experiments/drnas_v16/R32K_SINGLE_SOLVER_CAUSAL_FINDINGS.md (run 41646235624)
- ORION research manuscript dated 6 Nov 2026, current version reviewed from saved report.
- Recovered TA3: research/drnas_worldsim_w1_status_20261107.md (run 42397916379)
- TA7 final audit job 128526487957, run 42411409945
- TA8 final audit job 128530502710, run 42413969004
- TA7H60 final audit job 128535095268, run 42414292632

This file records the decision and historical evidence for future work. It does not
convert conversation memories into new audited measurements.
