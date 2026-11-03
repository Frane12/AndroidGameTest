# R24 diagnostic pilot — 2026-11-03

This research-only branch leaves the R22 frozen protocol, previous holdouts and
production solver untouched. R24 adds pre-intervention first-UIP traversal
counters; R24b adds the maximum reverse reason-path depth within that traversed
subgraph and counts edges crossing externally provided community labels. These
are not the whole propagation DAG; a revisit is not proof of independent paths,
and crossings are not a structural graph-theoretic bridge. R24b labels for the
synthetic community family are planted generator labels, not discovered
communities. Non-labelled edges are explicitly counted as unknown.

## Local pilot

32 generated 220-variable formulas: eight per family (random3, community3)
and per split (development, test); two repeats each for instrumented monitor
and a forced restart interval 50 after >=2048 conflicts, 128 executions. The
same binary was used for both arms, order shuffled, one CPU pinned, 2s cap,
PAR-2 on timeout and sum of per-formula medians. SAT assignments checked against
their original CNF; UNSAT claims lack independently verified certificates.
Seeds are different from R21/R22, and pilot hashes are distinct from each other;
no complete check against every historical corpus was carried out. The locally
reconstructed Kissat source matched upstream's 206 `src/` file blobs before
patching, except the generated configuration after build. Hardware is this
workspace, not the earlier GitHub Actions machine.

| Split | Family | Monitor s | Forced s | Gain | Forced >2x regressions |
|---|---|---:|---:|---:|---:|
| Development | random3 | 3.8445 | 4.0218 | -4.61% | 1 |
| Development | community3 | 0.4800 | 0.4934 | -2.79% | 0 |
| Test | random3 | 6.4945 | 6.0493 | +6.85% | 1 |
| Test | community3 | 0.6591 | 0.6834 | -3.68% | 0 |

No timeouts. Across 64 paired repeat/formulas, all 182 common 256/512/1024
pre-intervention checkpoints match exactly. The forced arm changed policy in
50 of 64 attempts; others ended or failed to reach the action. Timing includes
stdout tracing and scheduler overhead. This is exploratory: no selected dynamic
rule was trained prospectively or tested, and this test fold is now exposed.
A fixed-seed 10,000-resample formula bootstrap on random3 test gave an approximate
95% interval [-18.2%, +25.9%] for aggregate gain; only eight formulas, so no
claim of generalization.

An additional exploratory R22-instrumented vs R24-instrumented monitor check
on eight development formulas and two repeats per binary found sums of medians
1.9855s vs 2.0323s, approximately +2.35% instrumentation cost; tiny and
hardware-specific. Raw measurements, manifest and diagnostic outputs are
archived alongside this file. R24b was compiled and tested on four community
development formulas; baseline vs R24b status and R24 trace matched, counters
were nonnegative with no reported errors, and changing community label names
preserved counts. This checks wiring, not the mathematical exactness of all
depths or runtime advantage. Neither R24b overhead nor an independent UNSAT
proof has been measured.

## Reproduction and limitations

Apply `patch_r24_dynamics.py` or `patch_r24b_graph.py` to clean upstream Kissat
commit `8af8e56f174b778aef3aa45af9f739b2a5f492c2`. The work is a shadow-only
diagnostic: no new risk selector has been enabled in the solver, and no claims about P=NP or
universal improvement are justified. Any new predictor must be frozen on a
development set, account for censoring and measurement overhead, and then
validated with fresh formulas and independently checked UNSAT proofs.

## Frozen shadow-selector follow-up

Before the fresh run, a k=3 same-family nearest-neighbor selector was frozen
on development data only (8 eligible random3 and 5 eligible community3
formulas). It uses ratios of 1024-conflict telemetry, requires two nearby
beneficial cases, positive mean benefit and no >2x regression among neighbors.
The model SHA-256 is
`4b5e9d6f17e705cb729431f1c62fffc0629fff5034659750b551f259d60588b4`;
the frozen model was committed as 81fcd032eb82157663234d6a041b5c4c58c8adaa.

A new local paired batch used 32 generated formulas with a separate seed
namespace, all SHA-distinct from the preceding local pilot, two repeats per
mode, 128 attempts; five attempts timed out at 2s. There was no dynamic policy
in the solver: it is an offline counterfactual replay of separately measured
monitor and forced runs, with same-binary telemetry overhead in both arms.

On the 16 new random3 formulas, monitor sum of medians was 12.0139s PAR-2 and
shadow was 11.5675s, a 3.72% difference. The selector chose forced on four:
two were faster, two slower, one of the latter >2x slower (0.0653 to 0.2064s).
A fixed-seed formula bootstrap 95% interval was approximately -2.92% to
+12.56%. On 16 community3 formulas it chose zero, so there was no gain. All
186 paired pre-intervention checkpoints matched; two formulas lacked a usable
1024 snapshot and defaulted to monitor. The selector does not pass the safety
or improvement bar; these observations are not proof of a live speedup.
