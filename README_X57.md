# DRNAS X5.7 — controlled variable-branching CHB / LRB experiment

**Status:** research-only isolated branch. The repository's **main branch is
untouched**. No APK, binary release or solver promotion.

## Motivation

The X5.4–X5.6 experiments improved BCP operation counts and memory layout
but did not establish lower verified PAR2 on original SAT2024 applications.
This experiment modifies **which decision variable is chosen**, rather than
how efficiently the same decisions are propagated.

The implementation is inspired by the CHB exponential-recency-weighted
averaging and LRB learning-rate work of Liang, Ganesh, Poupart and
Czarnecki (AAAI 2016 and SAT 2016):

- CHB paper: https://doi.org/10.1609/aaai.v30i1.10439
- LRB paper: https://doi.org/10.1007/978-3-319-40970-2_9

**These are explicitly simplified experimental versions**, not
source-equivalent reproductions of the reference MiniSat, MapleSAT, or
CryptoMiniSat implementations, and not the original papers' full
reason-side / locality improvements.

## CLI and safety

\`src/drnas_x57.cpp\` accepts one of:

- \`--x57-branch vsids\` (default): exact same VSIDS heap/activity scoring as
  the frozen X5.5b control, with the same tie-breaking.
- \`--x57-branch chb\`: conflict-history EMA branch scores.
- \`--x57-branch lrb\`: learned-clause-membership-rate EMA scores.

All three retain the same **polarity saving**, BCP watched literals,
binary implication representation, clause minimization, proof output,
1-UIP conflict analysis, restarting and reduction policy.

The alternative policies are **local to a single formula**. No model,
outcome labels, future benchmark source information, filename, ground
truth or global SQL memory reaches the solver.

The score arrays are allocated only for the alternative policies.
For CNFs declaring more than two million variables, the experiment
falls back to VSIDS with \`fallback=true\` in \`X57_STATS\` to avoid
unbounded additional memory pressure; such runs **must not** be counted as
effective CHB/LRB tests.

## Policy details

A separate score array drives a priority heap. The old VSIDS
\`activity + base\` path remains unchanged when policy=VSIDS.

**CHB**: conflict-analysis variables are marked with the number of the
current conflict. At unassignment, an EMA update uses a reward
\`1/(conflicts - last_conflict + 1)\` only when the variable was involved
in conflict analysis since its last assignment. Otherwise reward is 0.
This encourages variables that repeatedly appear *recently* in
conflict-analysis work without assuming that every conflict is useful.

**LRB**: after 1-UIP analysis and clause minimization but before
backtracking, each variable in the final learned clause receives one
participation credit. At unassignment, the reward is
\`min(1, hits/(1 + conflicts - assignment_conflict))\`, an estimate of
the rate of learned clause participation while assigned.

For both policies the EMA learning rate is fixed in advance:
\`alpha=max(0.06, 0.4 - 1e-6 * conflict_count)\`.
Scores update **at unassignment**, and a variable's heap entry
recalculates on re-offer. This is a **fixed ablation** with no fitted
weights or tuning on the evaluation outcomes.

\`X57_STATS\` reports actual policy, memory-size fallback, decisions
selected by the policy, score updates, positive rewards, learned-clause
hits and alpha. \`X57_PROGRESS\` provides bounded telemetry on long
solves (including partially observed timeouts).

## Correctness and benchmark

\`tests/test_x57_chb_lrb.py\` runs independent brute-force SAT-oracle
checks on small formulas, plus pigeonhole UNSAT instances, and requires
DRAT-trim to certify **every UNSAT result** on the original CNF.

Four solvers are tested: frozen X5.5b reference, rebuilt X57 VSIDS,
CHB and LRB. The frozen reference vs rebuilt X57 VSIDS must have
**identical** conflicts, decisions, propagations, learned clauses,
binary propagations and reduced clause counts.

The test also requires that CHB and LRB actually **update scores and
change at least one search trajectory**, rather than acting as inert
flags. The initial GitHub Actions selftest passed: 61 sources,
244 executions, 140 independently checked UNSAT proofs,
2,457 CHB score updates and 1,720 LRB score updates.

The 36-original benchmark uses a previously SHA-frozen REAL36
SAT Competition 2024 source set, two repeats each, six serial arms:
\`X55B_FROZEN\`, \`X57_VSIDS\`, \`X57_CHB\`, \`X57_LRB\`,
\`KISSAT\`, \`CADICAL\`.

That is **432** solve attempts total, 10-second wall cap,
PAR2=20s for unsolved or unverified, one logical CPU per solver.
Proof output capped at 512 MiB. Independent verification and full
binary/source SHA auditing required.

A **per-original SHA-cluster bootstrap** respects dependence of the two
repetitions. The final report records overall / per-family solved
numbers, verified PAR2, process CPU, maxRSS and score feedback.
Do not credit unverified UNSAT, no matter which policy reports it.

### Limitations and promotion gate

This is a **retrospective** source set. It is not a new blind or
family-held-out benchmark. Even a promising CHB/LRB result on this
known set **does not** justify production promotion.

After selecting a winner from a predeclared validation protocol,
require a new family-disjoint original SAT holdout with independently
verified SAT/UNSAT, paired PAR2 confidence intervals, and no material
regressions in CPU and peak memory. The intended project-wide target
is at least 10% verified PAR2 benefit, **not a claim** at this stage.

GitHub Actions:
https://github.com/Frane12/AndroidGameTest/actions/runs/43418696306

Branch:
\`experiment/drnas-x57-chb-lrb-20261113\`
