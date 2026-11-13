# DRNAS GATE-R2 — hysteretic probe scheduler

Separate experiment based on frozen X4.6 GATE30 commit
`098839b5da1d686eff0e48598a2ae459af81f3c5`. Original sources, X4.6 builder and
`main` are unchanged. This is a software relay plus scheduler, not a new
SAT inference rule and not a learned causal predictor of seconds saved.

## Controller

Three states: CHECK (128-decision probe interval), ACTIVE (96), SLEEP
(512–4096). Initial check after 64 decisions. An exponentially smoothed
local-usefulness score enables ACTIVE at 0.65 and disables it at 0.35,
with at least four real outcomes before changing CHECK/ACTIVE state.
After eight inconclusive CHECK outcomes the controller returns to SLEEP.
Sleep still permits sparse rechecks, and sufficiently separated conflict
bursts request a CHECK, never directly ACTIVE. Old usefulness evidence moves
halfway toward neutral on re-entry from SLEEP. The criteria and thresholds
are frozen before evaluation; they are not fitted on its results.

All probe calls reserve 1.25 times estimated round cost before entry.
Budget = 0.5 ms + 2% of elapsed non-probe time. Predictions can be wrong:
a round can overshoot its estimate; actual overshoot is logged and subsequent
rounds remain blocked until affordable. No probe starts beyond 80% of the
solver time cap. Cheap schedule checks avoid clock reads on most decisions.
The final end-to-end measurement includes the full cost of the gate,
probe and scoring code, launching the native process, output parsing and
independent SAT-witness verification.

The unchanged X4.5 online two-weight scorer still controls branch selection.
The gate uses its actual-branch feedback, changed-branch flag and proxy score
gap. Propagation/structural gain is NOT proof of faster eventual solving.
Speculative probes roll back assignments but not watch ordering, so this is
not a fully matched-state counterfactual experiment. No original clauses,
logical inference or correctness conditions are modified by the new gate.
All memory resets per formula and repetition; no cross-formula persistence.

## Frozen six-arm test

600 fresh SHA-distinct formulas, 30 generated structural profiles, 20 per
profile, three repetitions, six arms, two-second E2E cap: 10,800 native runs.
The namespace is `gate-r2-relay30-prospective-20261113-v1` and historical
X4.4/X4.5/X4.6 manifests are excluded before solving. Hidden satisfying
witnesses validate generation but are not passed to solvers. These are fresh
instances of known synthetic generators, NOT new industrial families.

Arms: CORE, ADAPTIVE, unchanged X45_ONLINE, unchanged X46_GATE,
R2_FIXED and GATE_R2. R2_FIXED has the same predicted-cost reservation and
online branch scorer as GATE_R2 but always uses a 192-decision interval.
This ablation distinguishes adaptive scheduling from merely fewer probes.
Paired orders use balanced Latin rotations within each single-CPU runner.
Identical compiled binaries are shared across twelve balanced shards.

Primary preregistered success against X46_GATE: at least 5% lower verified
PAR2, no loss in solved attempts or stable 3/3 solved inputs, and a negative
upper endpoint of the paired formula-clustered 95% bootstrap interval.
All other comparisons are reported, not hidden. Three repetitions are one
formula cluster; category- and domain-clustered sensitivity intervals are
reported too. No formula is filtered by observed runtime. No superiority to
industrial solvers or large-UNSAT performance is claimed.

Self-tests cover hysteresis, dwell, budget/shock isolation, cost overshoot,
periodic rechecks, forgetting, fixed-policy isolation and controller fuzzing;
600 native correctness runs use 100 exhaustively checked six-variable cores
(including independently satisfiable components to exercise the gate after
64 decisions), plus generation/verification smoke tests and aggregation checks.

## Build

```
python3 research/build_gate_r2.py
g++ -std=c++20 -O3 -Wall -Wextra -Wpedantic -Werror build/drnas_gate_r2.cpp -o build/drnas-gate-r2
g++ -std=c++20 -O2 -Wall -Wextra -Wpedantic -Werror tests/test_gate_r2.cpp -o build/test-gate-r2
```

Compile immutable CORE/ADAPTIVE/X45/X46 controls as specified in the workflow
before running `python3 research/gate_r2_trial.py selftest`.
