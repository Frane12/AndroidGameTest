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


## 2026-11-09 — C11/C8/C12 incremental reconciliation

GitHub Actions latest-attempt job check (not a full artifact-content audit):
- [C11A 42534747410](https://github.com/Frane12/AndroidGameTest/actions/runs/42534747410): policy-recovery job success. Previously reported development C8D 38/38, PAR2 94.70 vs Kissat 253.68 (2.68x); C9C 8/24 PAR2 2154.72 tie; C10B 4/16 PAR2 1564.78 vs Kissat 1701.96. These are **different development cohorts**, never aggregate as paired or extrapolate to blind holdout.
- [C8H 42533156950](https://github.com/Frane12/AndroidGameTest/actions/runs/42533156950): five jobs success including final audit. Three original sources, 81 trials, 9 arms. Default PAR2 9.400; without BVE 27.527; without BVE and vivification 9.140. Nonadditive interaction is an observation, not a proven universal mechanism.
- [C11B 42535319191](https://github.com/Frane12/AndroidGameTest/actions/runs/42535319191): source pretest and 4/4 benchmark shards success, **FINAL audit failure**. Audit artifact exists. Root cause, verified paired results, and source SHA details pending inspection. No promotion.
- [C12 42535300094](https://github.com/Frane12/AndroidGameTest/actions/runs/42535300094): prepare, 4/4 shards and final 128-trial audit job success. Numerical paired solved/PAR2, original SHA and UNSAT proof caveats must be extracted from audit artifact before SQL benchmark_modes insert.
- [C8I 42534555190](https://github.com/Frane12/AndroidGameTest/actions/runs/42534555190): prepare, 4/4 shards and final audit job success. Numerical paired metrics still require artifact-content verification.

### Open failures / falsification checklist

| Expectation | Observation | Candidate explanation, not yet proven | One next action | Accept/reject criterion |
|---|---|---|---|---|
| C11B policy transfers to new originals | Final audit failed despite successful shards | Audit schema/provenance issue OR real correctness discrepancy | Inspect C11B final job log and audit ZIP | Complete SHA/witness audit and paired solved/PAR2; reject on unresolved audit |
| Early BVE gate reduces total E2E time | C8H shows BVE/vivification interaction only on 3 originals | Learned-clause path changes with preprocessing | Extract C8I and C12 final paired tables | Better solved/PAR2 on matched SHA without regression |
| GF2 reasons reduce CDCL search | T6A Active 16/40 PAR2 1242.089 vs Clean 16/40 1240.934 | Delivered reasons may be redundant or late | Instrument reasons consumed before baseline BCP | Causal advantage vs true runtime Shadow on new SHA |

SQL status records updated in research/drnas_sat_benchmark_history_20261107_ta.sql. This update intentionally contains no invented C11B/C12/C8I PAR2 or UNSAT proof assertions.


## 2026-11-09 — Verified follow-up audit: C11B, C12, C8I, C7, MRE X2/X3, T6A

**Evidence provenance:** exact FINAL JSON lines were read from successful GitHub Actions jobs. The first C11B final failed due to `KeyError: c10_structural`, then independent audit-only workflow [42537036902](https://github.com/Frane12/AndroidGameTest/actions/runs/42537036902) checked the original 50 rows without rerunning solvers. SQL check [42537735665](https://github.com/Frane12/AndroidGameTest/actions/runs/42537735665) passed after correcting two invalid evidence_level enum values. SQLite audit reports 48 cohorts, 283 modes, 46 findings, 271 telemetry rows, 38 paired-comparison rows, 18 frontier rows, 38 build-status rows. No frozen originals or main changes.

| Exact source-scoped run | Cohort / cap | Candidate solved | Candidate PAR2_s | Matched reference solved / PAR2_s | Outcome and constraints |
|---|---|---:|---:|---|---|
| [C11B original 42535319191](https://github.com/Frane12/AndroidGameTest/actions/runs/42535319191) and [repaired audit 42537036902](https://github.com/Frane12/AndroidGameTest/actions/runs/42537036902) | 5 original SAT SHA x2, 60s | triple 0/10 | 1200.000000 | Kissat 0/10 1200; CaDiCaL noelim 2/10 995.448839 | No transfer; 5/5 source routes to CaDiCaL and missed noelim SAT source. Error was final script KeyError c10_structural, not solver failures. |
| [C12 42535300094](https://github.com/Frane12/AndroidGameTest/actions/runs/42535300094) | 8 original SHA x2, 30s | C12 hybrid 8/16 | 556.150674 | Kissat 6/16 656.354789, C11 static 6/16 636.240943, CaDiCaL 4/16 740.464353 | Hybrid 15.27% lower PAR2 vs Kissat, 2 additional SAT solves on 1 source. R28-Kissat 6/16 656.272084 nearly identical to Kissat, so benefit cannot be credited to R28 GF2 itself. |
| [C8I 42534555190](https://github.com/Frane12/AndroidGameTest/actions/runs/42534555190) | 12 official SHA x2, 20s | gate16 2/24 | 880.295279 | plain CaDiCaL 2/24 880.296445 | 0/24 gate decisions; 11/12 original sources timed out for all modes; no gate benefit. |
| [C7 42523071479](https://github.com/Frane12/AndroidGameTest/actions/runs/42523071479) | 6 development SHA x2, 25s | CMS dedup+nobve 12/12 | 40.227623 | CMS default 11/12 96.434132 | 58.29% lower PAR2, 2.397x score ratio but development-only, external seed repeats not independent. |
| [MRE X2 42523269582](https://github.com/Frane12/AndroidGameTest/actions/runs/42523269582) | 13 development SHA x4 seeds, 12s | duplicate_spread 52/52 | 85.501258 | original 49/52 160.787333 | Same exact clause multiset and frozen binary. PAR2 down 46.82%; UNSAT independent LRAT absent. |
| [MRE X3 42524524856](https://github.com/Frane12/AndroidGameTest/actions/runs/42524524856) | 5 development SHA x4 seeds, 12s | spread100 20/20 | 32.361865 | original 17/20 106.722620 | PAR2 down 69.68%; spread25 worsens PAR2 to 120.058033. Separate 84 bounded CDCL diagnostics are not E2E. |
| [T6A 42485138094](https://github.com/Frane12/AndroidGameTest/actions/runs/42485138094) | 20 frozen original SHA x2, 20/30s | T6A Active 16/40 | 1242.088566 | Clean 16/40 1240.933749; Shadow 16/40 1241.929969 | 44.86% lower cumulative GF2 certification cost than T5 Active (7.512506->4.142488s), but Active 0.158597s worse than matched Shadow; 48 completed reason clauses without proven PAR2 benefit. |

**Accuracy boundaries:** SAT witnesses checked on unchanged original CNFs where each workflow reports them; comparison of UNSAT statuses to prior reference is not an independently checked LRAT proof. C8I/C11B/C12 external solver repeats not independent seeds. C11B official source list was frozen independently of previous C8D/C9c/C10b/C11a indexed developments but this is not global blindness. C7/X2/X3 are development sets. Comparisons across separate rows are not paired.

### Open negative findings, 2026-11-09

| Hypothesis | Counter-evidence | Most likely open mechanism | Next single falsifiable test |
|---|---|---|---|
| Frozen three-way backend router generalizes | C11B triple 0/10 vs CaDiCaL noelim 2/10 | Source-only rule failed to choose noelim on one SAT source | Hold rule frozen; validate source-disjoint randomized original SAT/UNSAT without tuning on C11B |
| Early BVE gate improves new official formulas | C8I 0/24 actual gate decisions, no PAR2 gain | Trigger not reached/observed before stop; source and solver process behavior to inspect | Reconstruct why no gate event in logs on a positive source before scheduling a larger new benchmark |
| C12 speedup comes from certified GF2 rather than routing | C12 R28+Kissat ~ identical to Kissat; source b2c2008... gains from selecting Kissat over C11 static CaDiCaL timeout | Backend-selection effect dominates observed gain | C13 factorial source-paired ablation with hybrid minus GF2/early BVE and corresponding no-op controls |
| GF2 propagation helps beyond runtime shadow | T6A Active loses 0.158597s to Shadow despite 48 completed reasons | Late/redundant CDCL clauses and preprocessing overhead | Log first nonredundant BCP consumption of certified reason; prove benefit on new original SHA |
| All duplicate placement dose improves CDCL | MRE X3 spread25 loses vs original | Nonlinear order-dependent branching/restarts | Repeat fixed-dose interpolation on new SHA-disjoint sources with identical order multiset and multiple seeds |

**Active test at time of this audit:** [C13 follow-up 42537515529](https://github.com/Frane12/AndroidGameTest/actions/runs/42537515529) has successful source preparation, four E2E shards in progress, no final decision. Earlier [C13 42537361190](https://github.com/Frane12/AndroidGameTest/actions/runs/42537361190) failed at preparation because missing `research/c13_r28_bve_prospective.py`; newer branch already contains workflow correction, so do not duplicate. This section records observations without launching a new cohort.


### R166x original Gaussian lineage (separate from 25-source R165 comparison)

[Original R166x mixed-Gaussian audit 42149883686](https://github.com/Frane12/AndroidGameTest/actions/runs/42149883686): 8 frozen original source SHA x2 repeats x9 arms=144 attempts; mixed caps 5s/30s. Clean plus direct/full/feedback/incremental/watchlazy/cooldown all 0/16 solved PAR2 560. Certified Gaussian variants 2/16 solved PAR2 about 540.576, improvement 3.4686% vs Clean; these two attempts may be the same source repeated, thus not two independent formula wins. Gaussian cooldown had 65,803 proposed GF2 implications, 1,968 native completed reasons, 130 Gaussian units. Direct incremental had 558,396,914 row events but no solved cases. This is development evidence with no independent UNSAT LRAT; do not extrapolate to all mixed CNF.

[Separate R165 world crosscheck 42149824021](https://github.com/Frane12/AndroidGameTest/actions/runs/42149824021): 25 originals x2, 11 configurations, R165 exact router 26/50 PAR2 640.896460 vs pure CaDiCaL/Kissat 0/50 PAR2 900 and CMS 8/50 PAR2 847.049336. This is a **different** original cohort; median uncensored paired speedup vs Clean is undefined due to zero jointly solved cases. Never present 42149824021 and 42149883686 as a paired R165-to-R166x regression comparison.


## 2026-11-09 — C13 official and easy post-audit update

**Official C13 [42537515529](https://github.com/Frane12/AndroidGameTest/actions/runs/42537515529)**: commit `3261b25bd9d0d6f8bdd4cf57a8702510efa99ffd`. Freeze PASS, 4/4 source-paired 30s shards PASS, FINAL PASS. 12 new-to-indexed-history original official2026 SHA x3 repeats x6 arms = 216 end-to-end attempts. Source SHA checked, SAT original models verified; UNSAT matches published reference only, independent LRAT unavailable; external repeats are not new solver seeds, not global blind. All methods solve 6/36 (3 SAT, 3 UNSAT), with 30/36 timeout each. CaDiCaL PAR2 1832.327424, C13 no-R28 1832.842004, hybrid 1833.126825, no-gate 1833.168501, C11 static 1833.202184 and Kissat 1839.522720. **No demonstrated causal contribution from C13 hybrid/R28 or BVE gate on these originals.** Hybrid is +0.799401s PAR2 worse than pure CaDiCaL, 0.0436% on this cohort. The C13 FINAL field `R28_activated_sources=8` actually counts size-eligible sources (`nvars<=3000 && bytes<=12MiB`) by source code, and **does not** verify executed certified native GF2 propagations or consumed reasons. C13 script records route `r28_kissat` for those inputs but no GF2-native reason counts.

**C13 Easy [42538022970](https://github.com/Frane12/AndroidGameTest/actions/runs/42538022970)**: commit `7e7c47308606718d51a268e95c0c40ffa15c12a5`, 4/4 shards and FINAL PASS, 12 synthetic planted SAT sources x3 repeats x6 arms = 216. All arms 36/36 SAT solved, no UNSAT test. Hybrid PAR2 1.935681; no-gate 1.936880; Kissat 1.864059; C11 static 6.900285; no-R28 6.899067; CaDiCaL 23.842335. Hybrid lowers PAR2 71.949% vs static, but Kissat alone is 3.84% faster than hybrid. The `no_gate` result essentially equals hybrid; the causal mechanism is **consistent with backend routing to Kissat** rather than an established GF2 or BVE advantage. Synthetic planted instances are unsuitable evidence for broad real-CNF speedup.

**Most useful next falsification:** isolate whether certified GF2 or early-BVE produces actual additional completed/consumed CDCL reason clauses versus the simpler backend choice. Instrument true GF2 execution, certified/replayed outputs and BCP consumption, source SHA, elapsed preprocess and fallback time. On new pre-registered official mixed SAT/UNSAT originals, pair `c13_hybrid`, `c13_no_r28`, `c13_no_gate`, pure CaDiCaL, pure Kissat and true shadow. Require non-regressed solved/PAR2 vs both backends and native witness/independent UNSAT proof. Avoid the already-completed official/easy cohorts as prospective blind tests.

**Database:** Existing experimental SQL already contained both C13 audited cohorts and all 12 paired mode totals before this review. This update adds only a distinct correction finding for the misleading `R28_activated_sources` name; it does not duplicate or overwrite completed trials or alter main.


## 2026-11-09 — C14 54-trial matched vivification factorial

**[C14 final run 42540665293](https://github.com/Frane12/AndroidGameTest/actions/runs/42540665293)**; branch `experiment/drnas-c14-bve-vivify-causal-20261109`; commit `52529ebc2b5095a16686b5a236797dd200604e86`. GitHub status **completed/success**: preparation PASS, all three 18-trial original-shard jobs PASS, FINAL audit PASS; five available artifacts including `C14-DEV3-54-PAIRED-BVE-VIVIFY-CAUSAL-RESULTS`. Original SHA verified in shard records; model witnesses checked on original CNFs. All attempts original-source E2E status with 30s hard cap and timeout PAR2 charge 60s. Three development sources, three repetitions, six arms = **54/54**. The five matched arms share solver binary SHA `622bea3b3524eb84c355fb51eb12efb4680c783f4ced67070782250fa57f6d0c`; upstream_default is a distinct binary `ef3067ff8d84bad054f769517ebc099a93810721c0280003f093305f3fde61d8`. Repetitions shuffle arm order but **do not change solver seed**. No independent UNSAT LRAT, not blind; no promotion.

| Arm | Solved / 9 | PAR2 seconds | Compared with matched default |
|---|---:|---:|---|
| no_vivify | **9/9** | **52.409243** | **75.2933% less** PAR2; 4.04748x ratio; +3 solved |
| skip_bve_no_vivify | 9/9 | 78.039563 | 63.21% less; +3 solved |
| legacy_noelim | 9/9 | 85.626210 | 59.63% less; +3 solved |
| skip_bve | 6/9 | 212.005010 | 0.057% less; same solved |
| matched_default | 6/9 | 212.125544 | reference |
| upstream_default | 6/9 | 212.128175 | different binary, not matched |

**Per-original source forensic**:
- SAT `4a3dde8588b06f42b73b96ba1e610a4b23d8cd239d44d17981c0638911c77aee` / GBD `3ed56242f55e3653dbceeb4a70221787`: matched_default, skip_bve and upstream_default all 0/3 with PAR2 180. no_vivify 3/3 SAT with PAR2 22.629743 (~7.543s avg); skip_bve_no_vivify 3/3 PAR2 48.602993; legacy_noelim 3/3 PAR2 54.252543. This **one original** accounts for all three additional solved attempts and almost all observed aggregate gain.
- SAT `dc3a17e19c6d2c076ed475b7dc342bb1474033bfd4d96f69a217f0e0e282ceac`: all arms 3/3; matched_default PAR2 3.198397 vs no_vivify 1.571514.
- UNSAT `e90397dabd4bf5e868edb9e8fe070d7d7de350a63ea70f6467e767fdf2f4f607`: all arms 3/3 by published status agreement, independent LRAT absent; matched_default PAR2 28.927147 vs no_vivify 28.207986.

**Causal interpretation:** removing BVE while retaining vivification (skip_bve) does not fix the problematic source, while removing vivification (no_vivify) fixes its 3/3 timeout attempts; skip_bve+no_vivify retains the solves but is slower. So **vivification is the primary ablated factor correlated with the benefit** in this frozen development test. This does not establish that vivification generally harms SAT, nor isolate the precise mechanism via learned-clause traces. On source `4a3dde85...`, one no_vivify rep0 completed with 242,888 conflicts and 350,466 decisions in 7.635786s vs skip_bve_no_vivify 548,432 conflicts and 839,445 decisions in 16.368250s. Timeout arms do not supply directly comparable terminal counters; no proof of a unique internal cause from these values.

**Follow-up**: [C15D 42541912605](https://github.com/Frane12/AndroidGameTest/actions/runs/42541912605) already started on branch `experiment/drnas-c15d-no-vivify-20261109` commit `88f4476cb86b0102956d2c6df4a90a880be7cf4f`. Preparation succeeded and six development+prospective paired benchmark shards are in progress at this report. Do not create competing no-vivify test, or assert its solved/PAR2 before final audit.

**Hypothesis to falsify:** selectively disable vivification by an independently observable, pre-solution signal, without losing solves on new source-disjoint SAT and UNSAT. Reject if no prospectively paired solved/PAR2 advantage versus the frozen default and a no-elim control, or if UNSAT model/proof consistency fails. Never select by source hash or tune against the C14/C15D holdout.


## 2026-11-09 — completed C15D and proof-preserving MRE12 (source-scoped audit)

### C15D — selective no-vivify remains an experiment, not a permanent switch

[Final C15D 42541912605](https://github.com/Frane12/AndroidGameTest/actions/runs/42541912605) completed success, 6/6 shards, 144/144 matched 30s attempts. Frozen 12 original sources (6 development, 6 new-to-indexed previous history), 3 repeats without independently varied solver seeds, four arms; SAT original witness checked and UNSAT status reference-matched without independent LRAT.

| C15D cohort | no-vivify solved / PAR2s | matched default solved / PAR2s | Kissat solved / PAR2s |
|---|---|---|---|
| C14 development | 9/9 / 44.350261 | 6/9 / 211.261324 | 6/9 / 217.847413 |
| C8H development | 9/9 / 13.869957 | 9/9 / 10.313095 | 9/9 / 16.334644 |
| Earlier-new official sources | 0/18 / 1080.0 | 0/18 / 1080.0 | **3/18 / 950.119349** |
| Total, NOT a blind generalization statistic | 18/36 / 1138.220218 | 15/36 / 1301.574419 | 18/36 / 1184.301406 |

The apparent aggregate C15D 12.55% lower PAR2 than default is driven by already-known development instances. **No prospective advantage** was demonstrated; permanent default disabling is rejected. A runtime selector may be explored, but must be falsified on new family-disjoint original SHA, not trained on these outcomes.

### MRE12 — exact signed equality quotient with original-implication proof

The new branch [experiment/drnas-mre12-exact-scc-quotient-20261109](https://github.com/Frane12/AndroidGameTest/tree/experiment/drnas-mre12-exact-scc-quotient-20261109) implements SCC detection in the binary implication graph and **independent two-way path replay using only original binary clauses**. An alias v := signed representative is applied only if original F entails both directions. Q(F) is solution-equivalent **under explicit reconstruction/projection**, and its SAT witness is checked on unchanged source F. Proof rejection or resource limit means untouched F; source SHA unchanged. This is not arbitrary same-assignment equivalence for removed variables.

[Original 96-trial run 42544834313](https://github.com/Frane12/AndroidGameTest/actions/runs/42544834313): prepare PASS, 4/4 paired 8s shards PASS. Final audit failed only because downloaded shard JSONs nested one extra directory. [Audit-only recovery 42545266420](https://github.com/Frane12/AndroidGameTest/actions/runs/42545266420) completed SUCCESS **using all 96 frozen original rows without rerunning solvers**. Local and GitHub 506 small-CNF 6,232 assignment equivalence checks + intentionally tampered proof rejection PASSED.

| MRE12 arm | Solved | PAR2s | Actual intervention |
|---|---:|---:|---|
| baseline unchanged CaDiCaL | **10/24** | **245.816939** | none |
| exact SCC quotient | 8/24 | 265.190497 | 2/24 trials on ONE official original, 48 independently replayed signed aliases per intervention |
| selective no-vivify | 8/24 | 265.246671 | 2/24 interventions on the same source; unvalidated gate threshold >=2 aliases |
| shadow | 8/24 | 265.318308 | full prepass, unchanged original |

No original SAT witness violations were observed. **No E2E benefit**: exact quotient PAR2 7.8813% higher than baseline. Two baseline successes on prior C14 UNSAT source bf8c8761... at PAR2 13.163808 became timeouts for quotient, shadow, and selective no-vivify, even though they had zero aliases on that source. This directly isolates a crucial failure: **preparation overhead rather than an unsound transform or quotient choice** consumed enough of the 8-second budget to lose solves. On prior official source e67d733d... the 48 proof-verified equalities were activated in both quotient repeats, but all arms timed out.

The tested selector **did not identify the known C14 NoVivify-winning SAT source** (zero certified SCC aliases), so do not promote the >=2 SCC-alias NoVivify gate. This is an empirical counterexample to the *selector*, not to Boolean algebra or logical equivalence.

**Next shortest falsifiable move:** reduce the cost of eligibility detection to an extremely cheap, bounded prepass; seek provable equalities from XOR/GF(2) only where source structure supports them and measure real *consumed* CDCL effect. Compare baseline, true shadow, quotient and independent no-vivify on new SHA before adoption. Keep all logical proof steps and original-source witness reconstruction. No unsound speed claim, no P/NP claim, no automatic merge.
