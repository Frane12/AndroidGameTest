# DRNAS SAT — full causal research ledger (2026-11-07, TA/TD/TK)

**Status:** Cumulative source- and protocol-aware review from successful GitHub Actions final audit logs, not a SAT Competition ranking and not a claim that NP-complete SAT has polynomial complexity.

## TA FINAL AUDIT 42353551967 — locked source-disjoint negative result

As of 2026-11-07, all six TA shards, all 300 paired attempts and the independent final audit **PASS**. The 30 SAT2026 original source CNF SHA values are disjoint from the enumerated R1/R2/R193 frozen manifests, but the test is **not globally blind** and may share broader source families. The source and policy thresholds were not changed for this final audit.

| Frozen arm | SAT/UNSAT solved out of 60 | SAT | UNSAT | Within-TA PAR-2 sum (seconds) |
|---|---:|---:|---:|---:|
| R153 | **12/60** | 8 | 4 | **2957.183758** |
| R1A | 10/60 | 6 | 4 | 3066.988472 |
| R2 Clean | 8/60 | 8 | 0 | 3201.353495 |
| R2 Portfolio | 8/60 | 6 | 2 | 3154.929632 |
| R2 Binary | 8/60 | 6 | 2 | 3154.981717 |

Matched Portfolio vs R153: 0 wins, 12 losses, 48 ties, **-197.745874 seconds PAR-2 gain** (negative is worse).

**Per-source failure localization from original `trials.json`, not merely FINAL summary:**

| Frozen source ID prefix | R153 (two reps PAR2 s) | R1A | Clean | Portfolio | Portfolio route / observed cause |
|---|---:|---:|---:|---:|---|
| `8117a2ac` | 10.054536 | 120.000000 | 30.588897 | 120.000000 | Chose R1A and lost both SAT solves that R153 (and Clean) could complete |
| `15e666a4` | 32.857900 | 32.720879 | 120.000000 | 120.000000 | Chose Clean and lost both UNSAT solves of R153/R1A |

The two paired source rows explain **197.087564 / 197.745874 = 99.67%** of the observed portfolio-vs-R153 aggregate loss. This is a diagnosis, NOT permission to hard-code source IDs/hashes, retune the locked holdout or claim better-than-R153 causal performance. More than a timing discrepancy, the two cases reveal different gating failure modes: a clean-route false positive for UNSAT, and a fallback-to-R1A false negative for a source where R153 performs well. A new source/family-disjoint evaluation is mandatory after any modified gate.
 Portfolio vs R1A: 0 wins, 10 losses, 50 ties, -87.941160 seconds. Portfolio vs Clean: 4 wins, 6 losses, 50 ties, **+46.423863 seconds**, but equal 8/60 solved. Portfolio selected 52/60 R1A routes and 8/60 structural Clean routes; Binary has the same aggregate route totals, not necessarily identical per case. These results **falsify transfer of the previously promising R2T source-selector gain to this exact new cohort**; no broad SAT performance claim and no same-TA threshold retuning are justified. SAT witnesses were checked; native UNSAT still lacks independent machine-checked LRAT/FRAT certificates.

Evidence: https://github.com/Frane12/AndroidGameTest/actions/runs/42353551967. Latest SQL cumulative record is `research/drnas_sat_benchmark_history_20261107_ta.sql` on the TA experimental branch, including five exact mode scores, six paired deltas, and two research findings. Next test design: analyze mistakes only on a separately designated development set, then use a newly disjoint holdout; never use the completed TA results to tune and then rebrand TA as blind.

## TD current experimental state

TD lazy source XOR 440-paired, five source-locked 11-arm shards, was launched as https://github.com/Frane12/AndroidGameTest/actions/runs/42356438634. Still active at this review; no final PAR-2 or solver advantage claim. On source SHA 22701e08... (first pair in shard 0), `td_lazy_source` vs `t_source`: repetition 0 0.728388 vs 0.731105 s, repetition 1 0.730978 vs 0.727765 s. Hence no consistent two-repetition gain; both report 0 completed native reasons, and the new method's asserted removed eager incidence update is not a benefit until full paired audit. The 20-source TD exact bucket detector-only audit run 42356263207 found 11912 parity patterns but zero newly recognized source cases; its scan consumed 6.599585 s vs old scan 0.402115 s and did not measure solver PAR-2.


## Verified finished build comparison

**PAR-2 figures below are sums within the indicated experiment. DO NOT compare across rows with unrelated cohorts, caps or number of attempts.** Solved counts use SAT witness checking on unchanged source CNF when the benchmark offers it; native UNSAT certificates are not independently LRAT-checked for many paths.

| Run / experiment | Relevant matched arms | Solved (matched) | PAR-2 sum (s) | Causal interpretation |
|---|---|---:|---:|---|
| [Ultimate R1 42344094697](https://github.com/Frane12/AndroidGameTest/actions/runs/42344094697) | R153 / Ultimate R1 / Kissat | 30/90, 30/90, 4/90 | 3621.489201 / 3621.517500 / 4661.255632 | R1 inherits R153's source-GF(2) routing; no improvement over R153; 26/50 specialty historical attempts solved by R1 vs Kissat 0/50 |
| [Original R2 42346485260](https://github.com/Frane12/AndroidGameTest/actions/runs/42346485260) | R153 / Clean / Live | 14/40, 18/40, 18/40 | 1383.061857 / 1170.721950 / 1176.449248 | Clean native CDCL fallback helps some originals; Live adds 40 completed native reasons in development but worse net PAR-2 |
| [R2x 42348940571](https://github.com/Frane12/AndroidGameTest/actions/runs/42348940571) | R153 / Clean / Live | 14/40, 18/40, 18/40 | 1378.713012 / 1166.599241 / 1169.270087 | Preprocessing cost better bounded; six Live-selected timeouts lack terminal native counters |
| [R2T 42350937691](https://github.com/Frane12/AndroidGameTest/actions/runs/42350937691) | R153 / Clean / Portfolio | 14/40, 18/40, 18/40 | 1382.240624 / 1168.671126 / **1155.276228** | Same-run feature-gated portfolio saves 13.394898 PAR-2 sec vs Clean; policy tuned after seeing corpus; requires disjoint confirmation |
| [T phase 1 42351079758](https://github.com/Frane12/AndroidGameTest/actions/runs/42351079758) | Clean / true Shadow / Source / Adaptive / Derived | All 18/40 | 1153.728945 / **1152.536897** / 1152.638359 / 1152.965614 / 1155.944610 | Source no reasons, Shadow slightly faster; Derived 108 proposals/40 completed reasons only development but no aggregate benefit |
| [R193 dual 42295688082](https://github.com/Frane12/AndroidGameTest/actions/runs/42295688082) | default / dual_keep_default | 154/204 / 156/204 | 3020.972903 / **2927.163077** | Two extra solves trace to previously seen original external family; not general learned-clause advantage |
| [R194 recovered 42351373958](https://github.com/Frane12/AndroidGameTest/actions/runs/42351373958) | default / dual_keep_default | 0/24 / 6/24 | 1440 / **1139.035484** | 12 seeds x two orders for ONE external SAT formula; strong candidate for TK, not independent family |
| [R196 42337423044](https://github.com/Frane12/AndroidGameTest/actions/runs/42337423044) | default / split256 | 6/32 / 8/32 | 2376.768142 / **2257.102753** | Development R195 subset +2 solves; correct split size crucial, rebuilding/512 variants regress |
| [R197 42340570480](https://github.com/Frane12/AndroidGameTest/actions/runs/42340570480) | default / split256 | development 6/16 / 8/16; blind 0/24 / 0/24 | dev 933.928855 / 820.251829; blind both 2160 | Improvement did not transfer to new hard originals within the cap |
| [New Horizon R4f 42341425816](https://github.com/Frane12/AndroidGameTest/actions/runs/42341425816) | Clean / R4d / R4e / R4f_select | All 584/616 | 129.025717 / 128.878152 / **128.874675** / 128.977387 | Strong source-exact 2-SAT/GF(2) routing on small structural classes; subsecond policy gains, no solve-count improvement overall |
| [Neural R5 42338136053](https://github.com/Frane12/AndroidGameTest/actions/runs/42338136053) | clean / neural | 66/80 / 66/80 | 283.376300 / 283.370511 | Zero actual alternate activations; no established learned policy benefit |
| [R193 short 42333938947](https://github.com/Frane12/AndroidGameTest/actions/runs/42333938947) | default / SAT | 88/88 / 88/88 | 0.185802 / 0.174878 | Trivial synthetic microbenchmark, not general SAT gain |
| [New Horizon R6 42333805417](https://github.com/Frane12/AndroidGameTest/actions/runs/42333805417) | default / dual_keep_default | 4/32 / 2/32 | 706.688481 / 736.341879 | Negative control: keeping extra state can LOSE previously solved SAT formulas |

## Critical reverse-engineering finding: why T is not yet a breakthrough

Let F be the original CNF, E certified XOR equations and C the residual CNF. Correctness requires F entails E; an imported XOR reason must be valid on the unchanged original source. Under a CDCL partial assignment alpha, one XOR row produces a new unit only if exactly one of its variables is unassigned, or a contradiction if none remain and assigned parity disagrees.

T's live Source and matched Shadow both updated **~82.3 million row incidences** across this cohort; neither produced a completed native reason. Source 82,277,463; Shadow 82,669,868; Adaptive 82,186,161. Doing repeated incidence bookkeeping with no new units cannot establish a causal SAT advantage. By contrast Derived produced 108 proposals and 40 completed reasons (development only) but matched Clean/Shadow in solved count and was slower in aggregate. A reason emitted after clean BCP already forces the literal can be logically sound yet operationally redundant. The timing of the implication matters, not merely that the proof exists.

## Three independent T successors

### TA — source-only algorithm selection, *frozen protocol; final result above*

The best validated cheap opportunity is selecting a fixed CDCL profile based on source binary/Horn density. R2T's same-source 13.394898-s gain is small (~1.15%) but comparatively less expensive to test than another full Gaussian preprocessing variant. Freeze **30 new original SAT2026 SHA-disjoint CNFs** against R1/R2/R193 manifests, with no outcome-based selection. Five arms: R153, R1A, Clean, frozen R2T Portfolio, new Binary density-only TA. 2 repetitions, 30-s limit, 6 shards = 300 attempts. This is **not globally blind** because other DRNAS historical test sets exist and source families may overlap; it is formally new to the explicit exclusion manifests.

Falsification: TA portfolio loses to clean on source-disjoint originals, or gain disappears under seed/family stratification. Preserve all negative cases and do not modify rule thresholds after seeing TA results.

Run https://github.com/Frane12/AndroidGameTest/actions/runs/42353551967 (latest executable permission fix); PR https://github.com/Frane12/AndroidGameTest/pull/21.

### TD — *lazy source variant built and running, results pending*

The candidate mechanism is **lazy certified derived GF(2) frontier**: avoid expensive per-assignment incidence updates across irrelevant XOR components until a low-degree row approaches unit/conflict status. On source-certified rows use a reversible lazy two-watch invariant and independently checked sparse Gaussian derivations only for components incident to active residual clauses. Do not repeatedly process 82M events without a candidate propagation signal.

Controls: Clean; full runtime Shadow; source-only; precomputed derived; TD lazy derived; adaptive gated TD. Collect per-clause real CDCL conflicts/backtracks, reasons before clean BCP, row-event count, total wall and PAR-2. A technical reduction in event count alone is NOT a SAT speedup. Preserve full original CNF and proof-replayed derived rows.

### TK — *proposed, not built*

Test keeping learned clauses and restart/phase information inside CDCL, motivated by R193/R194 but **contradicted in the broad New Horizon R6 control**. In SAT 2026 *Factoring Learned Clauses* (Pollitt et al.) proposes proof-conscious factoring of XOR/ITE gates within **learned** clauses, not only original CNF. This is relevant as a future inprocessing idea, but would require independent proof checking and a separate ablation; it must not be casually mixed into TA/TD conclusions.

Paper https://drops.dagstuhl.de/entities/document/10.4230/LIPIcs.SAT.2026.28

Controls: clean CDCL, dual_keep_default, learned-preserving vs reset with identical seeds, bounded pilot/selector overhead, initially previously seen development, then 30 SHA-disjoint originals with independent SAT witnesses and ideally LRAT/FRAT native UNSAT proof.

## Promotion and automation rules

1. Every hourly execution searches for newly completed GitHub Actions builds and audits source SHAs, solved counts, PAR-2, true paired deltas, actual GF(2) reason completion and regressions. Failed/cancelled builds are flagged, not invented as complete.
2. Store each verified build in cumulative SQL with precise status, source family, original SHA, causal conclusion and negative controls.
3. On an actual actionable bottleneck, implement *one new testable idea per new build* on a separate TA/TD/TK experimental branch. Reuse frozen controls and source-provenance verification. A running equivalent test must finish before launching duplicates.
4. Main, frozen original references and user research manuscript remain unchanged. No PR merges absent explicit approval. No world-record, general polynomial-time or P-versus-NP claim from any bounded sample.
5. For research-grade SAT, validate every SAT witness and independently replay certified GF(2) derivations. Native UNSAT without machine-checkable LRAT/FRAT remains a declared limitation.
