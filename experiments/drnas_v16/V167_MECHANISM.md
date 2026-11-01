# DRNAS V16.7 — Why nearly identical random-3SAT formulas react oppositely

## Controlled finding from already completed V16.6 ablation

Source GitHub Actions run: https://github.com/Frane12/AndroidGameTest/actions/runs/41284992655

All four configurations used **the same upstream Kissat 4.0.4 binary**, on the same runner. Factor 1: targeting parameter `--target=2`, factor 2: restart interval `--restartint=50`. The `--sat` profile combines them.

| configuration | random3 165000 median wall s | conflicts 165000 | random3 165001 median wall s | conflicts 165001 |
| --- | ---: | ---: | ---: | ---: |
| default | 1.3697 | 63,618 | 3.3173 | 130,399 |
| target only | 1.5656 | 65,567 | 16.3722 | 549,208 |
| restart only | 3.7483 | 178,267 | 1.4623 | 70,602 |
| both (`--sat`) | 0.2818 | 14,585 | 16.8749 | 605,358 |

On instance 165000 the **combination** is ~4.86x faster than default, even though *neither individual factor* was faster. On 165001 the *restart-only* configuration is ~2.27x faster than default, while the combination is ~5.09x slower.

A descriptive multiplicative interaction ratio
`I = t(both)*t(default) / (t(target-only)*t(restart-only))`
is approximately 0.0658 on 165000 and 2.338 on 165001. The ratios are *post hoc descriptive measures*, not a model or proof of causation across instances.

**Implication:** a solver-profile selector that independently tests whether targeting and restart changes are "good" can fail. Their interaction changes the conflict trajectory of the full CDCL search. No simple static feature has yet predicted that interaction reliably on unrelated instances.

## V16.7 preflight hypothesis

Instead of inferring an answer from similar clause densities, measure early solver dynamics under fixed conflict budgets 64 and 256. Capture raw pinned Kissat `-s` statistics for BOTH default and `--sat` in separate diagnostic runs, including decisions, restarts, conflicts, propagations and learned clauses **when the pinned binary exposes these counters**. Missing counters are recorded as null, not estimated.

Important: **two independent probes are not free**. Each starts Kissat fresh and cannot transfer its learned clauses to the full solve. A future online selector must include probe overhead in total time. The V16.7 experiment is *mechanism investigation*, not yet an online selection algorithm.

The suite is frozen before probing:

- Development only (previously seen): 165000, 165001, 165004, 165005.
- Independent fresh random-3SAT seeds: 167700..167707.
- Two off-density controls: 167708, 167709.

Full solves compare upstream default against `--sat` on each CNF; development-only cases additionally run each isolated factor. Every SAT witness is evaluated on the original clauses. All timeouts count as PAR-2; UNSAT assertions are by upstream Kissat (no LRAT/DRAT checker).

## Interpretation requirements

1. Compare **pre-specified early counters** against eventual result, avoiding target leak from filename or seed.
2. Report every new seed, including timeout and slower cases. Do not select convenient cases after measuring.
3. Do not fit selector thresholds using the new seeds and then call it a blind validation.
4. If no measurable early difference exists, say that this simple early dynamics probe did not reveal a useful predictor.
5. Any new selection algorithm requires a separate, future holdout across diverse external families.

This investigation's GitHub Action: https://github.com/Frane12/AndroidGameTest/actions/runs/41285894380
