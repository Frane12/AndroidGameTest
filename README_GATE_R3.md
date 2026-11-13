# DRNAS GATE-R3 — isolated conflict-wake experiment

Base: frozen GATE-R2 commit `9a3f7f4c0f76510dc3022e1aa25044f7d29e642a`.
`main`, all original solver sources, the R2 header/build script and X4.6 are unchanged.
No performance claim is made before the paired experiment completes.

## One policy change

R2 allows an early SLEEP -> CHECK transition after 256 decisions since its last
probe and last conflict-wake check, with at least 128 new conflicts since the
last accepted probe. R3 scales ONLY these conflict-wake thresholds by four:
**1,024 decisions and 512 new conflicts**. Constants are fixed before evaluation.

Hysteresis, local usefulness scoring, online branch weights, forgetting,
CHECK/ACTIVE/SLEEP strides, periodic wakes, cost estimates, 1.25 cost reserve,
0.5 ms + 2% non-probe-time budget and 80%-of-cap cutoff are unchanged.
Denied conflict checks retain their refractory interval. Periodic checks remain
possible even when the early-conflict threshold is not met; no freezeout occurs.

`R3_NO_SHOCK` disables only early conflict-triggered wakes, not adaptive
periodic checks. It distinguishes a better trigger from an unnecessary trigger.
The experiment is NOT a change to logical inference, a persistent memory system,
or a proof of causal seconds saved. Probes restore assignments, not complete
watch ordering. All per-solve learning is reset between formulas and repetitions.

## Frozen six-arm protocol

600 fresh SHA-distinct generated SAT CNFs, 30 structural categories, 20 per
category, three repetitions, six arms, 2-second verified E2E cap: 10,800 runs.
The namespace is `gate-r3-wake-only30-prospective-20261113-v1`. Prior X4.4,
X4.5, X4.6 and R2 manifests are excluded before solving. No runtime-based
filtering or post-result threshold selection is permitted.

Arms: CORE, ADAPTIVE, unchanged X46_GATE, unchanged GATE_R2, GATE_R3 and
R3_NO_SHOCK. One logical CPU per runner; twelve balanced shards. Binaries are
compiled once, hashed and shared across runners; per-run arm orders use
balanced Latin rotations. Every SAT witness is checked independently against
the original input. UNKNOWN costs 2*cap in PAR2. E2E covers process launch,
native work, output parsing and SAT-witness checking. Generation and shared
external input parsing are setup costs, not included in per-arm E2E.

**Primary comparison: R3 versus R2.** Success requires at least 5% lower PAR2,
no fewer solved attempts or stable 3/3 solved inputs, and an upper 95% paired
formula-clustered confidence endpoint below zero. Three repeats are one formula
cluster, not independent examples; resampling is stratified by category.
Category/domain-clustered sensitivity intervals are also reported.

**Promotion reference: original X46_GATE.** Promotion criteria require the
primary rule plus the same rule against X46_GATE. Even a passing exploratory
run should be independently replicated before replacing that reference.
Other comparisons, including NO_SHOCK versus R2, are diagnostic and cannot
replace the preregistered primary endpoint.

All 30 profiles are generated and some share broader domains. This is not
industrial SAT/UNSAT performance evidence. Small UNSAT correctness is tested
with exhaustive oracles, not advertised as large-UNSAT proof certification.

## Audits and reproduction

`research/build_gate_r3.py` validates pinned R2 file hashes, builds unchanged
X46/R2 controls and emits R3 source/header using checked, single-match patches.
The only policy predicate change is the conflict-wake condition. New modes
reuse the R2 telemetry schema with explicit R3 threshold/disabled fields.

Tests cover exact wake boundaries, no-shock periodic checks, denied-wake budget
and timeout checks, and 10,000 feedback events with identical R2/R3/no-shock
schedules when no conflict wake occurs. The native self-test runs all six arms
on 100 exhaustive small-core SAT/UNSAT oracle instances (600 comparisons).
Independent components exercise decisions beyond the gate's startup delay.
A mocked full-result audit tests report aggregation without claiming speed.

Build and run with the checked-in workflow
`.github/workflows/drnas-gate-r3-wake-only30.yml`.
