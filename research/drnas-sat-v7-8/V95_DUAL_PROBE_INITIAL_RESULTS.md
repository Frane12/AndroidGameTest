# DRNAS v9.5 dual-state initial results — official SAT Competition 2026
2026-10-31

Successful original run + raw artifacts: https://github.com/Frane12/AndroidGameTest/actions/runs/41236194691
Isolated branch: experiment/drnas-sat-v95-dual-probe-separated-20261031

## Protocol
Twelve previously-viewed official SAT Competition 2026 CNFs frozen in v9.4 manifest (6 SAT / 6 UNSAT), CaDiCaL 3.0.1 pinned, five methods, two repeats, 15s wall clock cap, 30s PAR2 timeout. 120 attempted solver processes, 4 Github Ubuntu runner shards, matched hardware affinity. Both probe and continuation time included. No changes to frozen v7.6 or v9.2.

## Full 12-case per-attempt mean PAR2 (seconds, lower better)
| Method | Solved/24 | Mean PAR2 |
|---|---:|---:|
| v95_dual_probe | 14 | 14.46907 |
| orig_v76_plain | 12 | 16.91522 |
| orig_v76 | 12 | 16.98483 |
| v92_sparse | 12 | 17.25561 |
| ca_plain | 12 | 17.32407 |

v95 vs ca: approx 16.48% lower mean PAR2 on THIS SEEN cohort (not holdout), plus two solved attempts. On six SAT cases, mean PAR2 3.2070 s vs 12.3943 s Ca; six UNSAT cases mean PAR2 25.7312 s vs 22.2539 s Ca (a large regression).

## Individual wins and loss
- 9ef9243ff051... SAT: v95 1.646 s, ALL four controls PAR2=30s because they time out at 15s; PAR2 ratio 18.22x (NOT actual solver speedup, true censored reference runtime unknown).
- 2b35377a7b95... SAT: v95 5.781 s, ALL four controls PAR2=30s; PAR2 ratio 5.19x.
- 5de866bc7ff4... SAT: v95 0.120 s vs plain Ca 0.883 s, sparse 0.365 s, V7.6 no-hint 0.725 s.
- ee44c3f46423... SAT: v95 0.478 s vs plain Ca 2.446 s; V7.6 no-hint 0.480 s, so no improvement over the best previously known method.
- 12cd0c319658... UNSAT: v95 timed out at 15s (PAR2 30s); Ca 8.848 s; V7.6 guided 4.590 s and Sparse 5.289 s. The regression is genuine and sizable.

## CRITICAL MECHANISM CAVEAT
In ALL v95 cases that completed and reported gate_reason, the selector chose 'v95_choose_plain'. It NEVER selected the Sparse state among successful completed runs. Timeout rows contain no gate telemetry; they cannot be assumed to have selected any particular mode.
Therefore the observed improvements should NOT be attributed to learned-quality discrimination between two arms. A 96-conflict plain checkpoint followed by continuation may by itself change CaDiCaL's search trajectory enough to explain both wins and regressions.
Required critical ablation has therefore been launched separately: https://github.com/Frane12/AndroidGameTest/actions/runs/41236927249
Four paired arms: CaDiCaL plain, frozen V7.6 no-hints, SINGLE 96-conflict plain solver followed by unlimited continuation in the SAME state, and original 96+96 dual probe.

## Limitations
Same 12 official CNFs already inspected in v9.4; model not prospectively assessed on a newly unseen cohort. Industrial SAT 2026 samples are size-filtered. Two repetitions share deterministic solver path, so wall-time noise matters. UNSAT proof certificates not independently checked. No world record, general superiority, or theory breakthrough established.
