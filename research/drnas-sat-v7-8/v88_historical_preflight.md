# DRNAS SAT V8.8 — Historical preflight (NOT the 30-CNF holdout)

Date: 2026-10-31. Historical input: archived `DRNAS-V86-adaptive-prospective-results.zip`, mode `orig_v76`, 14 distinct CNFs, 3 paired repetitions each.

## Falsifiable observation before interpreting V8.8 benchmarks

Using the exact first-checkpoint rule in `v88_lowlevel_probe.cpp`:

- 39 / 42 archived V7.6 runs (13 / 14 formulas) satisfy `active_256>0 && learned_delta>=threshold` ("durable").
- The remaining 3 / 42 runs all belong to `color3-180-s0`, which V7.6 solved before the checkpoint. They are **not** examples of rejected useful probes.
- Thus the proposed V8.8 near-threshold / 128-conflict extension cannot trigger on **any** of these 14 historical formulas, assuming the same first-stage measurements. Under these conditions V8.8 predicts the V7.6 continuation schedule (256 then 768) on 13 formulas, and an early solve on one formula.

**Interpretation:** This rules out expecting meaningful new adaptive selectivity on the historical V8.6 set. V8.8 might reduce observer overhead relative to V8.6/V8.7, but it should not be assumed to beat the original V7.6. Historical data cannot be used as an independent prospective confirmation.

## Honest prospective gate

The separate V8.8 branch runs 30 *new* seeded formulas across 5 families; 7 matched modes, 3 repeats, 3-second cap: 630 attempts. It compares plain CaDiCaL, frozen V7.6 with and without hints, V8.6, guarded V8.7, V8.8 with and without hints.

Required reporting: all cases including regressions and timeouts (PAR-2); independent SAT witness checking; no claimed UNSAT proof verification unless actual proof checking is added; report the fraction of decisions actually deviating from V7.6. Different repeated seeds may legitimately result in different gate decisions, and must be retained instead of triggering aggregation failure.

**Next research priority after this frozen holdout:** introduce a staged 64/128/256 conflict-progress signal and *matched staged controls* to separate the signal effect from extra solver stop/resume overhead. Do not use this already-inspected V8.6 sample as a blind evaluation set; do not optimize a threshold based on V8.8 holdout and then reuse it for a success claim.
