# DRNAS MRE8 — ABCX causal mathematical-representation breakthrough search

Date: 2026-11-08. Experimental branch: `experiment/drnas-mre8-abcx-ablation-20261108`.

This is an exploratory, post-hoc *development* test on the exact sixteen MRE7e pilot originals, not a prospective, blind or source-disjoint holdout relative to MRE7e. Neither the original main branch nor a promoted solver is changed.

## Hypothesis and why this experimental design

MRE7e found two contrasting SAT2023 examples. On `fdfcd52a…` 1,318 positively equivalent variables and 7,361 clauses were removed, but net wall improved in only one seed. On `037d21e0…` only six equivalent variables yielded a dramatic reduction in native conflicts and propagations, but the old quotient's expensive preprocessing erased the end-to-end advantage.

The experiment must distinguish changes in CDCL search, equivalent variable elimination, syntax cleanup, original clause order, and overhead. Merely removing more clauses is NOT evidence that a change helps search.

## Locked modes (8)

| Arm | Source-level change | Purpose |
|---|---|---|
| `N_native` | Exact original CNF | Baseline with no preprocessing |
| `A_rename` | Certified positive equality substitution, **without deduplicating/removing tautologies** | Isolate variable renaming/elimination |
| `B_clean` | Remove original syntactic duplicate/tautological clauses and repeated literals, **without variable renaming** | Isolate CNF normalization |
| `C_joint` | A followed by B, slow complete parsed reference implementation | Combined effect and existing mathematical strategy |
| `D_length_order` | Stable ascending clause length, no other changes | Identify a purely clause order/procedural effect |
| `Xs_stream_rename` | Byte-efficient original-CNF direct equality discovery + A-only streaming rewrite | Isolate the cost of detecting/rewriting small equivalent variable sets |
| `Xc_stream_joint` | Byte-efficient direct equality discovery + C-equivalent streaming rewrite | Same semantic CNF as C, potentially cheaper preprocessing |
| `Xr_route` | Fixed input-only structural route, mapping≥64: Xc, mapping≥2: Xs, otherwise original | Avoid dense preprocessing when equality structure is tiny or absent |

`Xs` and `Xc` must emit **byte-for-byte identical CNF** as A and C respectively for the same original input; fail the aggregate audit if not. Fast streaming is allowed only for a verified standalone-clause-per-line original DIMACS; otherwise it declines transformation. This is exact source-certified SAT-equivalence, not an unsupported XOR heuristic.

## Frozen benchmark and verification

- Exactly 16 SHA-locked originals from run [42505042425](https://github.com/Frane12/AndroidGameTest/actions/runs/42505042425), 8 arms, 4 precommitted deterministic paired seeds, total **512 actual solver trials**, 8 shards.
- Reuse the pinned CryptoMiniSat native solver binary and shared library from the same MRE7e artifact. All arms run sequentially within the same GitHub runner shard, order independently deterministic-shuffled per source and repetition.
- Each arm receives an 8-second **entire wall clock** cap; it includes Python discovery, mapping, rewriting, process startup, CDCL, and original-CNF SAT model reconstruction plus checking. PAR-2 charges 16 seconds for a timeout.
- Count SAT only when original-model witness is replay-verified; the baseline's original UNSAT has CaDiCaL agreement from preselection but **no independent LRAT**. Do not promote uncertified UNSAT to LRAT.
- Collect native conflicts, decisions and propagations when the solver reports a normal verdict, as diagnostic counters only. Solved SAT/UNSAT and PAR-2 determine performance claims.
- Predeclared structural router does not read test outputs or use formula identity.
- Strict audit: 16 exact sources, 512 source-rep-arm tuples, equal seeds within each 8-arm comparison, original SHA integrity, both A/Xs and C/Xc exact transformed SHA identity. **No automatic production promotion.**

## Next acceptance criteria

The useful direction is not merely lowest *single* solve time. Prefer positive solved and aggregate PAR-2 differences over native across independent seeds, equal proof validity, stable native-counter improvements, and a faster route relative to full Python preprocessing. Future blind source-disjoint tests are mandatory before a performance claim.

GitHub Actions: https://github.com/Frane12/AndroidGameTest/actions/runs/42506577511
