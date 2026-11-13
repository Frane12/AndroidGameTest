# DRNAS MATH Ω4.1 — first audited result, 2026-11-13

**Outcome: lower mathematical scanning overhead, no end-to-end solver improvement on this development cohort.**

Primary evidence: [GitHub Actions run 43516316741](https://github.com/Frane12/AndroidGameTest/actions/runs/43516316741) · [raw audit artifact 14081290912](https://github.com/Frane12/AndroidGameTest/actions/runs/43516316741/artifacts/14081290912).

Exact measured native binary SHA-256: `0530ff16016980e79ddecb1ea4e9107757305c0eb852e9b9b630aea503161264`.

## Protocol

CaDiCaL 2.1.0 IPASIR-UP; four runtime modes of one native executable (clean, shadow, full live Ω4, cost-gated live Ω4.1); one logical CPU per solver. Original CNF source verified by SHA-256; source XOR rows independently replayed from exact original clauses. Source-only cohort: 8 certified-XOR-positive and 8 certified-XOR-negative known original formulas, plus 4 synthetic controls. Two matched repetitions, 5-second E2E cap, 4 CI shards. **160 arm trials total**. This was a development/replay cohort, not a blind holdout.

Gate rule frozen before running: first 128 distinct trail scans unchanged; then skip 7/8 new trail states if (independently completed reason clauses + delivered conflict clauses)*64 < completed scans; gated maximum 6000 scans vs 12000 for full Ω4. Skipping deductions is sound abstention. All emitted reasons maintain source-row ancestry and are independently reconstructed against the current CDCL trail. The primary outcome is reported PAR-2 including measured preprocessing overhead.

## Original external cohort (16 sources × 2 repetitions)

| Mode | Original backend UNSAT reported / 32 | Unresolved / 32 | Reported PAR-2 s | Strictly independently verified PAR-2 s |
| --- | ---: | ---: | ---: | ---: |
| Clean CaDiCaL | 4 | 28 | **280.063737** | 320 |
| Shadow | 4 | 28 | 280.175147 | 320 |
| Full live Ω4 | 4 | 28 | 280.175037 | 320 |
| Gated Ω4.1 | 4 | 28 | 280.175056 | 320 |

The four UNSAT outcomes for each arm are **backend UNSAT reports without independent original-CNF LRAT/DRAT proof**, and no native SAT model was returned on this subset. The 28 unresolved attempts are 22 UNKNOWN and 6 TIMEOUT. The 16 external instances are previously seen, not a new evaluation of generalization. The strict independent score penalizes all UNSAT without proof.

### Mathematical/CDCL mechanism telemetry, original cohort only

| Metric | Full Ω4 | Gated Ω4.1 |
| --- | ---: | ---: |
| Actual GF(2) scans | 192,016 | **91,162** |
| GF(2) scan wall time | 698.023 ms | **430.893 ms** |
| GF(2) row XOR operations | 2,200,258 | **1,059,454** |
| Completed IPASIR-UP reasons | 60 | **114** |
| External conflict clauses | 28 | **172** |
| Proposed external units | 554 | **654** |
| Mean source proof depth of checked rows | 5.488 | 3.235 |
| Mean selected reason width (includes not consumed) | 3.368 | 5.521 |

Scans reduced **52.52%**, scanning wall time reduced **38.27%**. More emitted/accepted explanations are *not* equivalent to better SAT solving: both modes have the same solved count, and the same PAR-2 to reported precision. Repetition is limited to 2; dynamic trail divergence means raw proposal counts across arms do not measure direct causal usefulness.

On cases where native CDCL counters were available, sum of CaDiCaL-reported conflicts was 4,797,856 for clean vs 4,321,047 for gated; decisions 15,508,933 vs 12,323,251. Coverage only 26/32 for conflict and 22/32 for decision data. Because most runs are **time-capped without solving**, fewer total conflicts or decisions do not necessarily indicate faster progress; these counts cannot establish an algorithmic win.

### Synthetic controls

4 formulas × 2 reps × 4 modes: SAT models for 6 attempts per arm independently verified on the original formula, and 2 UNSAT outcomes supported by an independently brute-force-checked small synthetic oracle. Same logical verdicts in all four modes. Clean CaDiCaL reported PAR-2 0.020229 s, full live 0.039249 s, gated 0.039296 s: on trivial instances Ω4.1 overhead loses.

## Interpretation and next decision

**Verified mechanical gain:** source-certified Gauss–Jordan can run online on real CaDiCaL assignments, produce replayable reasons, and abstain to reduce scanning overhead by ~half.

**Not verified:** improvement in solved count, reported PAR-2, independently verified UNSAT speed, or generalization. Do **not** promote Ω4.1 into a global champion or claim a new mathematical theorem.

A justified Ω4.2 experiment would isolate cost from search progress using fixed-conflict/decision budgets, optimize no-XOR pre-gating, measure unique conflict/propagation usefulness, and finally test an unseen SHA- and family-disjoint cohort against clean CaDiCaL and CryptoMiniSat with independent original-CNF UNSAT proof checking. Keep only research branches; no changes to `main`.

## Reproducibility

- Code: `research/omega4_live_gf2.cpp`, `research/omega41_benchmark.py`
- Immutable source archive: R42809444478, 40 CNF manifest SHA-256 `c9610b199a70b73420e0a4687b81ce01c94d51ff487bd188aade83062c98cb3a`.
- CI workflow: `.github/workflows/drnas-math-omega41.yml`
- Raw source hashes, binary pins, per-case JSON and scores are in the audit artifact; results must be cited together with the run SHA.
