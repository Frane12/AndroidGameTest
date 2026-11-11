# DRNAS MAP2-L — first persistent-memory and frozen-holdout results

**2026-11-11** · experimental branch `experiment/drnas-atlasmap2-persistent-learning-20261111`  
**Verified GitHub Actions:** [run 42939965673](https://github.com/Frane12/AndroidGameTest/actions/runs/42939965673), **SUCCESS**.

## Experiment: 6 training SHA + 6 disjoint holdout SHA

Twelve *deterministically constructed*, satisfiable **mixed parity+3-CNF** formulas, 24 variables, 7 certified source XOR-2 edges plus 90 planted 3-clauses and a unit. The six training source SHA and six holdout SHA are disjoint. Every cohort is measured with 3 repeats of A, MAP2 shadow and MAP2 live (18 matched trials per arm per cohort), one logical CPU, 2-second cap. All SAT assignments independently checked on the exact original input. No original UNSAT LRAT claim.

**These are engineered positive-control formulas, NOT unseen original SAT competition problems.**

### Training: 18 repeats per arm

| Arm | SAT solved | Total PAR-2 (s) | Live CDCL implications | Shadow opportunities | Decisions | Conflicts |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| A | 18/18 | 0.045044 | 0 | 0 | 45 | 0 |
| SHADOW | 18/18 | 0.045043 | 0 | 144 | 45 | 0 |
| LIVE | 18/18 | 0.044832 | 144 | 0 | 45 | 0 |

### Frozen holdout: 18 repeats per arm

| Arm | SAT solved | Total PAR-2 (s) | Live CDCL implications | Shadow opportunities | Decisions | Conflicts |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| A | 18/18 | 0.044396 | 0 | 0 | 39 | 3 |
| SHADOW | 18/18 | 0.043387 | 0 | 144 | 39 | 3 |
| LIVE | 18/18 | 0.042810 | 144 | 0 | 39 | 3 |

- Holdout total A/LIVE ratio: **1.0370×**, equivalent to ~3.6% less measured time on these tiny trials. **Not statistically established**: each solve is only ~2.4 ms, so process-launch and scheduling noise can dominate.
- Despite 144 live CDCL implications per cohort, **decision and conflict counts are identical** across arms. No causal search reduction demonstrated.
- The strategy selector chose **A for all six frozen holdout formulas**, because the training evidence did not satisfy the conservative 10% relative **and 5 ms absolute median** E2E improvement gate. This is the scientifically appropriate conservative outcome.
- Training memory was **byte-identical** before and after holdout. Repeated training SHA was ignored; all six holdout SHA were excluded from training records.
- The memory JSON includes per-source **source structure, actual measured methods, SAT verification, live reason counts, observed ratios, decision/conflict deltas, explanation and explicit uncertainty**.

## Cross-run persistence is operational

The CI job restored the preceding versioned GitHub Actions training cache and added a **new source-distinct training formula**:

- Previous rolling memory: 1 source SHA.
- Current rolling memory: **2 distinct source SHA**.
- Current source SHA: `079780edf608090267694f6dcf542b8c7a07e459d6ea91a105625a97997528f7`.
- Example observed E2E A 0.001786 s, LIVE 0.001227 s, SHADOW 0.001359 s; **8 actual live reasons**, 8 shadow opportunities; decisions unchanged at 3, conflicts 0.
- Memory selector remains **A**. The apparent 1.46× individual ratio is not actionable: absolute measured difference is **0.559 ms** and the dataset has only two distinct source SHA.
- Versioned cache was saved for the **next workflow run** under `map2-rolling-experiment/drnas-atlasmap2-persistent-learning-20261111-42939965673`.

GitHub cache is best-effort and subject to eviction, restore-prefix ordering and concurrent-run races. Each successful run also uploads the journal, full audit and explanations as artifacts; do not treat caches as a transactional database.

## Decision

**Confirmed:** persistent cross-run source-distinct training memory, explainable per-source evidence, frozen holdout, correct original SAT models, and actual MAP2 live/shadow events.  
**Not confirmed:** genuine speedup or fewer conflicts/decisions on independent difficult mixed SAT instances. These tiny constructed formulas do not justify a speed claim or promotion to `main`.

Next meaningful experiment: **harder, source-frozen mixed CNF** where a transitive relation can cause early propagation that normal BCP does not already deliver, matched against A/SHADOW/LIVE, with longer 5–20 s caps and independent original UNSAT proof checking where relevant.
