# DRNAS ATLAS-MAP2 — full first-run audit

**Date:** 2026-11-11 · **Author:** Frane Drnas  
**Source branch:** `experiment/drnas-atlasmap2-live-relations-20261111`  
**GitHub Actions:** [run 42938394455](https://github.com/Frane12/AndroidGameTest/actions/runs/42938394455), **SUCCESS**, five jobs (correctness + four independent benchmark shards).  
**Status:** exploratory. Original-CNF UNSAT proofs are NOT independently certified; this benchmark uses satisfiable formulas only.

## What changed from MAP1

1. Original-CNF **complete XOR-2** source encodings enter a bounded parity union-find map. Transitive relations are mathematically entailed by exact GF(2) cancellation.
2. A native C++ event scheduler subscribes to the CDCL assignment trail, checks at BCP intervals and after restarts, and can insert **source-entailed binary explanation clauses** directly into the own R3C solver.
3. `MAP2_SHADOW` records the same proposals without changing the solver; `MAP2_COMBO` runs existing MAP1 source replacement before the new live interaction.
4. The source table is built before search but implication **delivery is online**. MAP2 does *not* yet learn equivalences from newly learned CDCL clauses, nor does it use the optional persistent MAP1 statistical memory to select live interventions.

## Independent QA

The correctness job returned:

```text
ATLASMAP2_SELFTEST_PASS randomized_cases=240 independent_oracle_attempts=720
 verified_SAT=90 live_source_pairs=2 live_groups=1
 live_implications=2 live_completed_reasons=2 shadow_opportunities=2
 incomplete_pair_rejected=1 contradictory_cycle_fallback=1 original_UNSAT_LRAT=0
ATLASMAP2_SMOKE_PASS
```

- 720 mode-specific oracle checks across 240 small source-structured CNFs (baseline/native active/shadow); SAT models verified on original CNF. Random trials include SAT and UNSAT, but **UNSAT is validated here only by exhaustive small-case oracle**, not by independently checked large-CNF LRAT.
- The deterministic mixed and parity-chain controls produced two **actual live implications with complete CDCL reason clauses**, versus two passive shadow opportunities.
- Missing halves of parity encodings are rejected. Contradictory GF(2) cycles safely disable the new map instead of making unsupported certification claims.

## Benchmark design: 112 matched attempts

Four public SATLIB families, SHA-derived rank 58, two repetitions, seven arms, two **separately labeled** formula cohorts, 6-second wall-style per-arm time cap plus external grace, one logical CPU per arm; PAR-2 charges **12 seconds per timeout**. The C++ native R3C backend is identical across native arms; Kissat and CaDiCaL are **comparator solvers**, not part of the native code.

**IMPORTANT:** `original` is the unmodified source-normalized SATLIB input. `mixed_augmented` is the same input **plus a synthetic independent six-variable parity chain (10 binary clauses + one unit)**, so it is an algorithmic positive control, not a second original/official benchmark. All SAT results were independently model-checked on their exact cohort source CNF.

### Original SATLIB inputs — aggregate 4 shards, 8 trials per arm

| Arm | SAT verified / 8 | PAR-2 total (s) | PAR-2 ratio vs native A |
| --- | ---: | ---: | ---: |
| Native R3C A | 6/8 | **24.333869** | 1.0000× |
| ATLAS-MAP1 | 6/8 | **24.314033** | 1.0008× |
| MAP2 live | 6/8 | **24.337811** | 0.9998× |
| MAP2 shadow | 6/8 | **24.339582** | 0.9998× |
| MAP2 combo | 6/8 | **24.312410** | 1.0009× |
| Kissat (pinned ref) | 8/8 | **0.333068** | Comparator only |
| CaDiCaL | 8/8 | **0.245806** | Comparator only |

All original-SATLIB MAP2 arms registered **zero source-certified connected groups and zero live implications**. The three easier source families were solved in both repeats by all modes; **uf250-1065** timed out in both native repetitions at the six-second cap while both reference solvers solved it. Ratios close to one are not reliable improvements at these durations and sample sizes. MAP1/COMBO fluctuations on tiny cases do not establish a causal speedup.

### Deliberately synthetic mixed augmentation — separately reported

| Arm | SAT verified / 8 | PAR-2 total (s) | Live implications | Shadow opportunities |
| --- | ---: | ---: | ---: | ---: |
| Native R3C A | 6/8 | **24.333815** | 0 | 0 |
| ATLAS-MAP1 | 6/8 | **24.340195** | 0 | 0 |
| MAP2 live | 6/8 | **24.336618** | **30** | 0 |
| MAP2 shadow | 6/8 | **24.333522** | 0 | **30** |
| MAP2 combo | 6/8 | **24.335425** | **30** | 0 |
| Kissat (pinned ref) | 8/8 | **1.302229** | — | — |
| CaDiCaL | 8/8 | **0.241063** | — | — |

The 30 live CDCL implications include **five per solved attempt** on the synthetic six-variable chain, 6 solved native attempts. The hardest SATLIB family timed out in the native modes; its timeout trials are not counted as certified successful solves. These extra assignments are valid CDCL events but likely accelerate no search because ordinary watched-literal propagation already solves this simple chain. This is a proof of *functional integration*, not a speed claim.

### Per-source frozen SHA of normalized original DIMACS

| Family | Selected SATLIB file | SHA-256 |
| --- | --- | --- |
| uf100-430 | `uf100-0939.cnf` | `faf371805f67cd51bd6e4abe93b7623ec17dd2657c20877cf5e1eec62028f0fd` |
| uf150-645 | `uf150-071.cnf` | `7efdc6e2ea804ac83e86d13333ffb88c04f888aa80f6d69d80017cdeb453ad4b` |
| uf200-860 | `uf200-023.cnf` | `2ecd67735e9fbfebb065ab8d6face3abb2868918143d877b6452c00f27924628` |
| uf250-1065 | `uf250-079.cnf` | `7d007b015095cde333fb213a6b1b41171734149d6f9ef7c225ed6dfdca079d7b` |

CI shard artifacts contain the exact selected archive entry and raw input SHA, generated original and mixed CNF, `source.json`, trial-level JSON/telemetry and `audit.json`. Artifacts may expire; preserve the checksums and audit log when making a permanent public release.

## Interpretation / decisions

**Confirmed:**
- MAP2 compiles and its source proof/DSU coupling survives an exhaustive small-CNF oracle plus original SAT witness checks.
- MAP2 enters live native CDCL (the reason and assignment counters are nonzero in positive cases).
- In the negative-control random 3-SAT corpus the structural gate does not fabricate nonexistent XOR equivalences.

**Not established:**
- No additional original problem solved, no convincing end-to-end speedup, no standalone native superiority over Kissat/CaDiCaL.
- No independent original UNSAT LRAT, no verified benefit in genuinely complex mixed XOR formulas, no live learning of additional source-independent relation classes.
- 30 additional propagations on an *augmented* input should never be presented as 30 novel solutions.

**Recommended next experiment:** On a **separate branch**, prioritize source-certified mixed XOR+CNF cases with real chained implications that watched BCP cannot derive cheaply at the same stage. Measure **net** conflict reduction, decision reduction, reason-reuse, memory, and E2E PAR-2 versus plain R3C, shadow and MAP2. Add strict cost-aware activation and only then consider incremental relation learning from proof-audited binary CDCL lemmas.

`main` untouched. No promotion of this experimental candidate is justified by these data alone.
