# DRNAS SAT R31 — certified consistent GF(2) gap vs root contradiction, measured on native CDCL

**Date:** 2026-11-03
**Full successful and audited GitHub run:** https://github.com/Frane12/AndroidGameTest/actions/runs/41628224957
**Final 240-attempt artifact:** https://github.com/Frane12/AndroidGameTest/actions/runs/41628224957/artifacts/13226523615
**Code:** \`r31_consistent_gf2_test.py\` and read-only \`patch_r31_passive_final.py\`.

## Experimental design and caveats

- Frozen 28 new deterministic synthetic CNFs (seven categories, four cases each), plus 2 previously seen **original SAT Competition 2026 GBD CNFs** for out-of-distribution/guard control: 30 unique SHA-pinned formulas.
- Two matched repeats × four modes (clean pinned Kissat, passive read-only native Kissat, external proof-checked shadow preprocessing + passive Kissat, external proof-checked unit injection + passive Kissat) = **240 completed attempts**, all with matching source/binary fingerprints.
- Per-attempt timeout 4.0 s, timeout PAR-2 penalty 8.0 s. Results on different suites should not be conflated. Each paired source uses the exact same pinned Kissat solving policy; the GF2 injected arm changes **input CNF by adding only independently verified entailed unit clauses**.
- Wall times for GF2 shadow/injected arms include actual Python parity recognition, resolution, Boolean root propagation and GF2 elimination; injected also includes writing the temporary augmented DIMACS. This is **not** a native in-process optimized implementation.
- The intentionally constructed synthetic consistent XOR instances have known planted SAT witnesses (verified), and complete parity patterns; SAT outputs are checked on the **original** DIMACS. The root UNSAT category is mathematically certified by contradiction in the exact verified GF2 subset. Baseline/native UNSAT results are not independently checked with LRAT/DRAT.
- None of these results proves universal SAT acceleration or a new result concerning P vs NP.

## Critical correction and strict state taxonomy

Earlier R30: eight nominal "GF2 extra units" arose entirely from three globally UNSAT parity formulas. R31 prevents that invalid interpretation:

1. \`ROOT_GF2_UNSAT\` has an independently checked contradictory GF2 source combination and is **never counted as a useful unit**, never used to inject individual units.
2. \`CONSISTENT_EXTRA_UNITS\` requires a **consistent**, source-verified full-parity subsystem and a separately reproduced root-BCP closure. Every injected unit has an XOR row-combination proof against source equations and root BCP units.
3. \`CONSISTENT_NO_UNITS\` means no safe new unconditional root unit (may still have conditional branch deductions).
4. \`INPUT_GUARD\` abstains; no made-up structural claim.

Observed classification across 30 distinct formulas:
- 12 \`CONSISTENT_EXTRA_UNITS\`: four visible, four hidden, four mixed; **8 or 12** certified root units per formula (120 per unique formula corpus).
- 4 \`ROOT_GF2_UNSAT\`: contradictory original XOR subsystem, no novel unit injection.
- 12 \`CONSISTENT_NO_UNITS\`: conditional XOR, partial XOR decoys, and planted 3-SAT controls.
- 2 \`INPUT_GUARD\`: prior original GBD competition CNFs, unsuitable for the bounded parser; all strategies timeout with the 4s cap.

At real conflict-free native snapshot **mark=0**, six attempted snapshots (three formula SHA × two repeats) detect 12 algebra-only units: \`x4=x8=x12=x16=x20=x24=x28=x32=x36=x40=x44=x48=1\`. These snapshots have **no GF2 contradiction** and root original-CNF BCP does not imply the 12 variables. The fact that the majority of easy formulas are solved during preprocessing and yield no search snapshots is a coverage limitation, not zero gap.

## Native CDCL conflict-count comparisons at identical solver policy

At these three snapshot-bearing formulas, two repeats agree on the native final conflict counter:

| Formula | Verified root units | Native conflicts, shadow | Native conflicts, units injected | Median PAR2 shadow (s) | Median PAR2 injected (s) |
|---|---:|---:|---:|---:|---:|
| consistent_visible_01.cnf | 12 | 6 | **4** | 0.027616 | 0.028233 |
| consistent_mixed_01.cnf | 12 | 8 | **6** | 0.024942 | 0.025843 |
| consistent_hidden_03.cnf | 12 | **28** | 37 | 0.038456 | 0.037907 |

**Mechanism takeaway:** a certified extra unit can reduce or increase learned-CDCL search conflicts and has no guaranteed correlation with whole-process wall time. At these millisecond scales timing noise/preprocessing costs matter. This is a controlled input-augmentation comparison, not a causal identification of specific learned-clause graph edges.

Across all *finished* R31 shadow vs injected native runs: total conflicts **16624 vs 16634**, a net **increase of 10 conflicts**; native conflict totals exclude timeout cases, and differ in composition only when root units were actually added. In controls without units, native search counts match exactly.

## Time and overall performance

| Category | Clean PAR2 sum (s) | Passive read-only PAR2 (s) | GF2 shadow PAR2 (s) | GF2 inject PAR2 (s) |
|---|---:|---:|---:|---:|
| **ALL** | **32.908673** | **32.916457** | **33.158323** | **33.123279** |
| Visible consistent parity | 0.101134 | 0.101344 | 0.135382 | 0.125237 |
| Hidden consistent parity | 0.122137 | 0.121223 | 0.164091 | 0.150209 |
| Mixed consistent parity | 0.123338 | 0.122996 | 0.162839 | 0.162380 |
| Conditional parity, no root units | 0.162579 | 0.163101 | 0.202477 | 0.202153 |
| Root XOR contradiction | 0.027787 | 0.026959 | 0.063210 | 0.063463 |
| Incomplete XOR decoys | 0.025355 | 0.025440 | 0.029523 | 0.029658 |
| Planted random 3-SAT | 0.346343 | 0.355394 | 0.400801 | 0.390179 |
| Previously seen official GBD controls | 32.000000 | 32.000000 | 32.000000 | 32.000000 |

All modes solved 28/30 cases; two official GBD cases timed out under 4s in all modes.

For the **12 genuinely consistent root-unit formulas alone**, GF2 injection improved **external GF2 shadow preprocessing PAR2** from **0.462312s to 0.437826s** (5.30% lower) but still consumed **26.3% more whole-process time than plain Kissat** (0.346609s). This is **not** a successful overall general solver optimization; the Python preprocessing implementation is the dominant overhead on easy examples. Against the clean Kissat, global R31 is ~0.65% worse (censored official timeouts dominate the denominator).

R31 is a successful *diagnostic and mathematical classification* test. It **refutes** the simplistic policy that more provably entailed units universally means fewer CDCL conflicts or faster execution. This does not refute the potential of a cheaper in-process GF2 mechanism on harder, genuinely out-of-distribution CNFs.

## Next principled experiment

- Develop a bounded **native, in-process** GF2 shadow probe under a strict time budget; never use a Python process and disk rewrite as if measuring in-process overhead.
- Verify an actual \`CONSISTENT_GAP\` at matched conflict checkpoints, with separate \`ROOT_UNSAT\` and \`BRANCH_UNSAT\` signals. Report the exact dynamic assigned variables, graph interfaces, clause use and CDCL conflicts before/after.
- Include **mixed hard SAT/UNSAT**, official cryptographic/algebraic benchmark categories (not exclusively GBD), longer caps (30–120 seconds), new SHA identities, proper SAT model and UNSAT proof verification.
- On an independent development set only, test predictor \`estimated benefit > probe cost\`; freeze before evaluating a new blind set, with explicit abstention and worst-case slowdown controls.
- Keep stable V15.3.1 unchanged.
