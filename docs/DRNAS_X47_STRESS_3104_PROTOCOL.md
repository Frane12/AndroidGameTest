# DRNAS X47 STRESS 3104 — predeclared bounded campaign

Date: 2026-11-13. Research branch: experiment/drnas-x47-stress3104-20261113.
Native base commit: 1670a8fd3e56ae13f0c527240e30d1037e7bfa8b.
The native solver itself and main branch are not changed by this campaign.

## Question and scope

Does the frozen learned X46 short-probe policy improve verified end-to-end search under a sustained, diverse load, or do rare expensive polarity mistakes erase local wins? What CPU and peak resident-memory costs accompany each arm? This is a benchmark, not another training cycle.

- 3072 synthetic original CNFs: 12 generator families, 256 sources each.
- Per family: 192 small sources with cap 0.25 seconds, 48 medium with cap 2 seconds, and 16 large/hard with cap 15 seconds. Tier membership is selected before solving, not by observed difficulty.
- Totals: 2304 short-cap, 576 medium-cap, 192 long-cap originals.
- 32 original SAT Competition 2024 CNFs in a separate retrospective cohort, cap 15 seconds. Selection is based on archive metadata, resource bounds and decompressed source SHA, not results. This cohort may overlap earlier SAT2024 research and is NOT globally blind.
- Seven arms: CORE, X46_8, X46_128, X46_LEARNED_8, X47_RISKGATE_8, Kissat, CaDiCaL.
- Two timing repetitions per original and arm: 43456 planned measured runs (plus the 168-run preflight). Repetitions are not independent formulas or training cycles.
- One actual fourth-decision intervention checkpoint in the native arms; no repeated learned intervention is implied.

Synthetic families: planted 3-SAT, planted 4-SAT, modular 3-SAT, planted XOR, planted graph 3-coloring, pigeonhole UNSAT, planted binary SAT, exact-one/cardinality SAT, Horn SAT, wide-clause SAT, parity-cycle UNSAT, and unbiased random 3-SAT. Some structural-size stress instances contain approximately 16000–18000 variables, while harder search cohorts use fewer variables. Large variable count is not claimed to imply hardness.

## Bounded execution and provenance

32 source-disjoint synthetic shards, maximum four running concurrently, each restricted to one logical CPU. A separate official job also uses one logical CPU. Trial virtual address space is limited to 1536 MiB, stdout/stderr files to 16 MiB each, CPU and wall deadlines enforced, core dumps disabled. Each synthetic job has an 80-minute ceiling, the official job 145 minutes. This is not an unbounded resource request or a promise of completion time.

All seven arms are serial within each source/repetition, in a deterministic shuffled order. No main-branch changes, no automatic promotion, no mid-test tuning. The two model files are copied from the previously verified reference artifact and checked by SHA:

- X46COST1: 234cb83b155bc5fe5ff5ec0337945480f4c09082f37fcfaacda6a1b7995cb4c4
- X47GUARD1: 7647bf185d8c75a184cfff3e1f4f500434619bf6b553b0516b8c5a9150c223a7

The retained X47 guard is the previously selected NO_PROBE guard. It is an explicit conservative control, not a newly successful learned policy.

Kissat and CaDiCaL are built once from their official repositories. Their resolved commit IDs, compiler version and executable checksums are captured before benchmarking; all workers download the same binary bundle. The campaign is reproducible from those exact resolved commits. No claim that the selected revisions are competition winners or optimal configurations is made.

## What counts as a solution

Every SAT model must satisfy every clause of the exact original CNF. A partial model is acceptable only when it already satisfies every original clause. A contradictory or invalid witness fails the run and preserves evidence.

Pigeonhole UNSAT is credited only after independently checking the full strict pigeonhole constraint core against the original clauses. Parity-cycle UNSAT is credited only after verifying every CNF parity-row encoding and independently deriving a GF(2) contradiction. These are restricted structural certificates, not a general DRAT/LRAT proof checker.

Uncertified UNSAT on random3 and official problems remains explicitly unverified and receives the full PAR2 penalty, regardless of solver identity. Agreement between solvers is not certification. Consequently, the official score is a conservative verified score, not an ordinary unrestricted SAT Competition ranking.

Verified answer count and verified-within-deadline solved count are separate. PAR2 uses actual subprocess plus independent checking time when within the cap, otherwise twice that source's cap. Failed processes, memory/resource failures, timeouts, incomplete output and unverified answers are never silently discarded. A verified SAT witness conflicting with any reported UNSAT fails the correctness audit.

## Measurements and statistical interpretation

Record original SHA, family, tier, repetition, arm, verified/solved state, PAR2, wall and CPU time, peak RSS, return code, native decisions/conflicts, probe time, skips, flips and pre-intervention state digest. GNU time measures the executable's child resource usage rather than incorrectly attributing the Python launcher's high-water RSS to the solver. Missing metering falls back to explicitly marked wrapper rusage; those measurements are not silently called exact.

This campaign measures individual solver processes under a sustained job workload. It does not establish absence of memory leaks in a persistent multi-instance solver service: each trial starts a new process.

The primary comparison is frozen X46_LEARNED_8 versus CORE. Report paired original-source bootstrap confidence intervals, solved counts, ratios, per-family/per-tier scores, p95/peak RSS, p99 elapsed time, and the worst source-level regressions. Multiple secondary arm comparisons are exploratory. Formula SHA identifies a source cluster, not proof of statistical independence across related generator instances. Synthetic families and the official cohort remain separate.

A positive solver-performance claim requires a meaningful end-to-end improvement with no loss of certified solutions and robustness across families; better classification or fewer conflicts alone is insufficient. No promotion follows automatically from this run.

## Failure recovery and artifacts

Trials and source manifests are flushed incrementally, not only at the end. Each shard uploads results even after failure. The final report checks all expected source/arm/repetition combinations and marks missing or failed cohorts incomplete; it cannot label a partial aggregate a successful complete benchmark. Failure CNFs and bounded diagnostic logs are retained. Proof blobs and huge live logs are not generated.

New synthetic sources use the fixed generator salt DRNAS_X47_STRESS_20261113_21000000_V1; the source SHA and exact generator code make them reproducible. This is a new-seed synthetic suite, not a claim that every logical formula is novel up to isomorphism.
