# DRNAS New Horizon NMR R3 — event-driven utility and callback feedback

**Research pilot:** code on `experiment/drnas-nmr-r3-utility-feedback-20261107`. No claim that the model provides a provable speedup or correctly identifies every mixed formula.

## Core hypothesis

The controller must learn three separate policies:
- **REST (no neural work):** for small-source formulas (<70,000 bytes), limits <1 s, or training calibration with insufficient positive net benefit, run a clean pinned CaDiCaL solver without structural scanning, neural inference, or duplicate-solver allocation.
- **OBSERVE (sparse):** on high-value candidates, run early 128/256-conflict windows on a warm default solver, preserving all learned clauses. For stable telemetry use wide windows (up to 2,048 conflicts); for sudden signal drift use 64-conflict windows.
- **REACT (deferred):** C++ callbacks update cheap counters; only when the rate of short clauses changes sharply across 64-offer buckets does the callback set a pending event. The CaDiCaL terminator checks that event and can end the current bounded solve at a safe checkpoint. The Python controller evaluates neural utility **after** control returns, never inside the hot callback. A second solver is created lazily only when estimated benefit exceeds measured costs and the probability threshold.

This does **not** sample every CPU cycle or observe all CDCL internals. The learner callback offers only learned-clause size and timing proxies, not actual LBD, complete propagation counts, or a mathematical guarantee of future performance.

## Cost-aware decision

For feature vector x, persistent MLP estimate p(x), training-only empirical mean savings among positive paired cases G, empirical mean losses among non-positive cases L, and mean activation cost C, the controller estimates:

`expected_gain = p(x) * G - (1 - p(x)) * L - C`

Activate only if:
- positive training evidence: at least four calibrated trials, at least one win, aggregate gain > aggregate loss + activation overhead;
- `expected_gain > 0.020 s`;
- `p(x) >= 0.75`;
- at least one second of cap remains.

These are **pre-registered heuristic thresholds**, not calibrated probability guarantees. Initial labeled feedback comes from training-only clean-vs-forced runtime comparisons including PAR2 timeout penalty; it is not the shortest learned-clause proxy used in R2. Once running, a within-formula proxy update can affect a private neural copy but held-out results never update the shared memory.

## What persists

R3 migrates the SQLite weights saved in R2, creates a `utility` calibration table, and writes training episodes transactionally. After process shutdown a new invocation restores those parameters from disk, or a GitHub Actions cache/artifact. The benchmark uses read-only checkpoints in each evaluation job; frozen SHA hashes are validated before and after.

## Controls and falsification

Four SHA-disjoint evaluation shards: 40 held-out formulas x two repetitions x five modes = **400 paired attempts**.

- `clean`: pinned unmodified CaDiCaL.
- `feedback_only`: learning callbacks and variable-resolution observation without duplicate expert.
- `forced_probe`: always create the additional solver if a pilot is unresolved.
- `utility_gate`: cost gating + event-triggered reassessment.
- `utility_gate_no_period`: same gating, recurrence features disabled.

The controlled dataset includes prior external sources and known synthetic generators, and is **not blind to generating families**. SAT witnesses must satisfy the original CNF; native UNSAT lacks independently verified LRAT. Account for the complete controller and solver wall clock (including Python/SQLite overhead) and track callback wakes, windows, activation count, solved count and PAR2.

## Important distinctions

1. A detected recurrence of observed learned-clause statistics does not prove the CNF has a mathematically periodic structure.
2. Finite categories need not explain the optimal solution policy for all arbitrary SAT formulas.
3. An unexpected callback or positive classifier score is evidence to evaluate **possible** action, not a command to perturb proof-critical solver state.
4. A failed intervention is a useful negative experience and must affect future calibration.
5. The best outcome may be **no intervention at all**; the baseline is itself a valid expert.

Reference: R2 complete 400-trial audit (run 42322672422): 66/80 clean vs 64/80 live; PAR2 283.57617 vs 293.63601. This motivates a true abstention policy rather than continuous neural work.
