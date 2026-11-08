# DRNAS MRE8 — native C++ A/B/C/D/E/X factorial ablation

**Frozen before observed MRE8 timing (2026-11-08).** Branch:
experiment/drnas-mre8-abcx-native-ablation-20261108.

## Hypothesis

A few mathematically certified substitutions can change CDCL's branching and propagation trajectory disproportionately to removed clauses. Full preprocessing is not always worth its wall-clock price. Disentangle quotienting equivalent variables, clause deduplication, tautology elimination, and cheap structural gates.

## Arms — identical source SHA and CMS backend

| Arm | Treatment |
|---|---|
| N | pinned original native CryptoMiniSat, exactly original SHA |
| A | original formula: remove duplicate clauses only |
| B | substitute certified equivalent variables, preserve duplicates and tautologies |
| C | substitute variables + remove tautologies, preserve duplicate clauses |
| D | substitute variables + remove duplicate clauses, preserve tautologies |
| E | substitute variables + remove tautologies + deduplication |
| X5 | accept full E only when >=5 exact original positive equality pairs |
| X50 | accept full E only when >=50 such pairs; otherwise use original native input |

All seven treated arms use the same compiled native C++ transformer at research/mre8_abcx_transform.cpp; native C++ preprocessing cost is **included**. Both X gates incur reading and original binary-pair detection even when abstaining.

A positive equality a=b is accepted only from the **two original binary clauses** (-a OR b) and (a OR -b), followed by a transitive DSU closure. No uncertified GF(2) inference. For SAT, eliminated variables are lifted to their root value and the model is independently checked on original source. UNSAT is consistent with the pre-frozen CaDiCaL screen, but there is **no independently checked LRAT**.

**Ablation caveat:** CryptoMiniSat can itself clean duplicate literals, clauses and tautologies. These arms isolate external *input representation* choices and their net native effect, not a clean internal CMS per-subroutine speed profile.

## Protocol

- Exactly **16 SHA-locked originals** SAT2021–SAT2025 selected for MRE7e based on reference CMS easiness. The MRE7e source-selection step failed the independent 20+ criterion; this 16-case pilot is **reused developmental data**, never a new blind holdout.
- Four deterministic paired CMS seeds per source. Repetitions 0 and 1 reuse the MRE7e seed function; 2 and 3 are additional deterministic paths.
- Eight arms x four seeds x sixteen originals = **512** source-paired trials, balanced arm execution order, eight shards, parallelism at most four.
- **8.0 s full wall cap per arm**, including native C++ transform and writing the rewritten DIMACS, native CMS, model lifting and original witness verification; PAR-2 timeout penalty is **16.0 s**.
- Report solved SAT/UNSAT, timeout, full wall, PAR-2 and speedup x vs native N, prep cost, conflicts, decisions, propagations, gate-acceptance rate and strongest paired regressions.
- Must pass complete strict **512/512 audit** before any verified total can be reported. UNSAT is cross-solver-consistent but without independent LRAT.

## Promotion policy

The focus formulas fdfcd52a... and 037d21e0... were examined in the previous MRE7e pilot; favorable numbers are hypothesis-generation, not new-generalization confirmation. New source-disjoint blind original benchmark with complete SAT and independently verified UNSAT proof is required before promotion; main remains unchanged.

[GitHub MRE8 512 paired CI run](https://github.com/Frane12/AndroidGameTest/actions/runs/42507588566)
