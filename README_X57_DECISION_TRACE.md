# DRNAS X5.7 Decision Trace — observability for SAT branching policies

**Research only.** This branch does not modify \`main\`, does not ship an APK,
and does not promote CHB or LRB. It is an instrumentation-only fork of
\`src/drnas_x57.cpp\`: \`src/drnas_x57_trace.cpp\`.

## What it records

Enable the optional logger on the actual compiled solver:

\`\`\`bash
build/drnas-x57-decision instance.cnf \
  --mode core --time 8 --x57-branch chb \
  --x53-policy baseline --proof result.drat \
  --x52-proof-deletions --stats \
  --x57-decision-trace decision.jsonl
\`\`\`

The JSON Lines file has a \`meta\` object followed by bounded
\`decision\` objects. **Each is a real chosen variable and literal**;
speculative X46 branch probes and structural probes are excluded.
A decision record includes:

* Actual decision number, variable index, signed literal / saved phase,
  decision level, heuristic score at selection, VSIDS activity and
  original structural base score.
* Before-decision conflicts, propagations, trail length and elapsed time.
* Outcome of the immediately following BCP call: conflict, no conflict,
  timeout, limit or not observed; number of propagated trail assignments
  and added implied literals, with elapsed time after the BCP call.
* If this **immediate** BCP produces a conflict: LBD and size of the
  1-UIP learned clause after minimization, before solver backtracking.

This does **not** assert that a decision *caused* a conflict or caused
later SAT convergence. A conflict and a lower LBD are observational
signals, not a proof of counterfactual value or a correctness label.

The file explicitly says \`counterfactual_known: false\`,
\`results_externally_verified: false\`, and
\`is_causal_effect_known: false\` for each row. External SAT model
verification is performed by the benchmark harness.

## Bounded instrumentation

To keep memory bounded, the logger records all decisions **1–4096**,
then every **512th** decision, up to **8192 rows** total. The trace
metadata identifies the selection policy, total decisions, stored rows,
sampling thresholds and rows omitted due to the cap. This is not an
exhaustive trace for arbitrarily long runs.

The logger allocates the trace buffer only when requested. Nothing
from a trace is read back by the solver's branching heuristic.
With \`--x57-decision-trace\` absent, X5.7 uses its unchanged VSIDS,
CHB or LRB algorithm.

The solver emits \`X57_TRACE_WRITE\` with a solve-end elapsed timestamp
and actual JSONL serialization time so writing overhead is observable,
not accidentally mistaken for search speed.

## Source verification and benchmark

The diagnostic run uses the **10 original SAT2024 REAL36 CNFs** that
had SAT witnesses independently checked in the earlier X5.7 run
\`43418696306\`. Selection requires both repetitions to be SAT_VERIFIED
by each of the four previous X5.7 policies.

These are **9 SIMON and 1 scheduling** formulas. The imbalance is
acknowledged explicitly. The dataset is retrospective, *not a blind
holdout*, and cannot establish global SAT branching superiority.

The benchmark is 10 originals × 2 repetitions × 9 arms = **180 runs**.
For each policy, we compare:

1. Previously frozen X5.7 compiled binary, without logging.
2. New traced-source binary with logging disabled.
3. Same new traced-source binary with logging enabled.

For every formula and repetition, the harness requires exactly
matching completed-search decisions, conflicts, propagations, learned
clauses, binary propagations and reductions across all three matched
variants. SAT models must satisfy the original source CNF.

The previous run's source SHA manifest, previous trial evidence SHA,
and current binary SHA hashes are frozen before the experiment.
SAT decision traces are saved as individual \`jsonl\` files in per-shard
artifacts and source-paired metric reports.

**Never treat lower decision count alone as a performance win:** use
verified SAT solve rate, matched wall time and source-clustered
confidence intervals. For very fast SIMON cases, timing noise may
dominate. The scheduling case is especially interesting for
qualitative inspection of why the policies diverge.

There is no online training or new learned policy in this run.
Only after observing repeatable differences on independent original
families should we consider changing the branch ranking.

GitHub Actions:
https://github.com/Frane12/AndroidGameTest/actions/runs/43430312222

Branch:
\`experiment/drnas-x57-decision-trace-20261113\`
