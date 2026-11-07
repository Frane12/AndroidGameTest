# DRNAS SAT v8.8/v8.8b — low-level evidence, 2026-10-31

Research only. No general SAT speedup, complexity theorem, world record, or hardware cache benefit established.

## Implementation
- Frozen CaDiCaL 3.0.1 and original v7.6/v7.7 sources are hash-verified and not patched.
- v88_lowlevel_probe.cpp: 256-conflict initial solve; read public redundant() and active() counters only at checkpoints. No clause-learner callback on the new lowlevel_v88 mode, integer-only branch decisions, same solver and learned-clause database. Preserve v7.6 durable path (768 conflicts). Near-threshold cases can sample another 128, then conditionally continue.
- v88b_delayed_probe.cpp: 256-conflict initial solve with no phase hints; if retained learning passes the original durable threshold, apply phase hints only to the next 768 conflicts; remove them before unbounded resume. Same solver object throughout.
- Matched no-hint controls assess contribution of phase guidance. All models are checked for SAT; UNSAT certificates are not independently checked.
- These changes remove callback overhead on the new experimental path; they do not change the fundamental conflict-driven search complexity. No hardware performance counters were recorded.

## v8.8 fresh 30 CNFs × 3 repeats × 7 modes = 630 attempts
Run: https://github.com/Frane12/AndroidGameTest/actions/runs/41226463135
PAR2 sums of per-formula medians (3 s cap; timeout costs 6 s):
- ca_plain: 58.39163 s
- orig_v76: 61.80261 s
- orig_v76_plain: 56.21829 s
- adaptive_two_checkpoint: 65.21917 s
- adaptive_guarded_v87: 65.20309 s
- lowlevel_v88: 61.95462 s
- lowlevel_v88_no_hints: 56.22166 s
No SAT/UNSAT contradictions detected. Added v8.8 gate did not yield a general aggregate win.

## v8.8b fresh 25 CNFs × 3 repeats × 6 modes = 450 attempts
Run: https://github.com/Frane12/AndroidGameTest/actions/runs/41226986357
PAR2 sums of per-formula medians:
- ca_plain: 40.04418 s
- orig_v76: 37.69604 s
- orig_v76_plain: 36.64113 s
- lowlevel_v88: 37.62426 s
- delayed_v88b: 36.95592 s
- delayed_v88b_no_hints: 36.61991 s
No SAT/UNSAT contradictions detected. Delayed hints improved aggregate relative to always-guided v7.6 on this set, but were still worse than the no-hints control.

## Decision
- Keep the proven v7.6 working code untouched. The best total-time no-hints setting is an existing v7.6 control, not a new record.
- Treat delayed hints as an opt-in research mode; it has not generalized across all cases.
- To claim low-level benefit, measure CPU instructions, cycles, branch misses, cache misses, time, and effects of callback and phase overhead on fixed hardware. GitHub-hosted runners may disallow perf counters.
- To claim algorithmic generalization, use independent harder problems, fixed inclusion criteria and timeout penalties, matched repeated runs, and independently verified UNSAT proofs.

The key open question: which early learning-dynamics signals predict when phase hints help beyond the same bounded schedule without hints?
