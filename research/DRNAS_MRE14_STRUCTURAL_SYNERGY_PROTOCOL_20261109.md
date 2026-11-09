# DRNAS MRE14 — Structural Synergy (frozen experimental protocol)

**Branch:** `experiment/drnas-mre14-structural-synergy-20261109`  
**GitHub run:** [42548937345](https://github.com/Frane12/AndroidGameTest/actions/runs/42548937345)  
**State:** prepare passed; matched E2E shards launched. No performance conclusion before a complete final audit.

## Mathematical invariants

1. **D_96:** For each novel binary clause `(-a OR c)`, independently verify the existence of two original binary implications `a -> b` and `b -> c` from the unmodified source CNF. All original clauses remain present. No unproved binary lemma is permitted.
2. **C_depth2:** After adding only certified D lemmas, delete a literal `x` from a disjunction only if a replayed path of implications from the original-plus-certified graph establishes `x -> y` for a literal `y` **retained** in that same disjunction. This ensures both directions of clause equivalence under the original source, not merely equisatisfiability.
3. **Spread100:** Use the actual MRE X3 duplicate relocation algorithm, moving canonical duplicate occurrences evenly. Verify the entire raw clause multiset (including duplicate multiplicities) with a counter before passing it to CaDiCaL. No clause is invented or deleted by Spread100.
4. **No Vivify:** Only modifies the solver's search/preprocessing option, not the formula. The selective gate is a frozen, *unvalidated research hypothesis*: `(D_lemmas>=32 AND C_removed>=8) OR (duplicates_moved>=32 AND C_removed>=4)`. It cannot see source SHA/GBD, SAT labels, result times, or prior benchmark outcomes.
5. Every returned SAT model is independently checked against the **unchanged original CNF**, and contradictory SAT/UNSAT results cause a hard audit failure. Current benchmark provides only published reference agreement on UNSAT; independent LRAT/FRAT is **not** claimed.

## Six paired arms

| Arm | Exact operation | Vivification |
|---|---|---|
| `baseline` | Untouched original | on |
| `spread100` | Original + duplicate relocation only | on |
| `cd` | Original + certified D_96 followed by C_depth2 | on |
| `cd_spread` | D_96 + C_depth2 + X3 Spread100 | on |
| `cd_spread_no_vivify` | Identical combined formula; causal ablation | always off |
| `cd_spread_selective` | Identical combined formula; fixed structural gate | off only if gate passes |

All six arms use exactly the same frozen CaDiCaL instrumented executable SHA and identical source SHA/seed pairs. CaDiCaL numerical seed differs across the two repetitions and is the same across all arms within a pair, confirmed by an executable smoke test. Arm order is randomized deterministically.

## Preregistered corpus and timing

Freeze report: **17 original SHA** after retaining all safely transportable earlier C15D/X3 originals and adding four source-disjoint-from-reused-manifests official SAT2026 originals (2 SAT, 2 UNSAT). Three X3 originals overlap C15D and are not duplicated. One earlier C15D UNSAT original (946,106 clauses; SHA `e90397da...`) exceeds the transport cap and is explicitly excluded, never rewritten. Fresh sources were chosen by frozen SALT and resource requirements, **not** by running the solver or measuring their difficulty.

Four parallel shards, six arms, two independently varied numerical seeds: **17 x 6 x 2 = 204 real E2E trials**. Each trial has a hard 12-second elapsed time cap inclusive of hashing, preprocessing, proof verification, solver invocation, and original model verification. A timeout scores 24 seconds in PAR-2. Compare solved count, SAT/UNSAT, total PAR-2, proof counts, duplicate movement, prepass overhead, selective trigger count, and per-original regressions.

The four fresh official originals are new to the two frozen reused input manifests; **no assertion of globally unprecedented sources** is made. Every candidate is experimental; no promotion or main-branch modification. 

## Observed preflight tests

The first prepare ran exhaustive Boolean equivalence checks on **245 bounded CNFs / 3,644 truth assignments**, including all D+C+Spread100 combinations: PASS. Separate CaDiCaL numerical seed smoke test (two different seeds): PASS. Frozen SHA input checks: PASS.

**Promotion gate:** require complete matched audit, no original SAT witness violations, independent UNSAT evidence as applicable, no meaningful regressions, and a gain on genuinely fresh SHA-disjoint instances relative to both untouched and simpler arms. Gains from the earlier MRE X3, MRE13 or C14 experiments are **not additive** and must not be assumed.
