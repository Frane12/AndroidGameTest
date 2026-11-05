# DRNAS SAT R14 — frozen dual-signal rescue and structured-family transfer
Preregistered 2026-11-02, before any R14 formula or benchmark results.

## Previous discovery / falsifiable hypothesis

R13 120-formula random-3SAT data showed a few strong response reversals:
old rescue50 selected n>=220, 0<p<46.5, g>=0.95 at conflict 512
and changed native Kissat restartint to 50 at conflict 2048. This gate
showed +2.26% total test PAR-2 but 95% formula-bootstrap CI included zero.
After examining *both* R13 folds retrospectively, we observed six
n=240 formula instances with variable-degree CV>=0.285,
propagations-per-conflict p>=43, and lower early LBD/glue ratio g<0.95:
the always-forced 2048/50 arm was faster on all six and saved ~8.90s in
the three-repeat aggregated formula timings. This is a SMALL post-hoc
sample selected by multiple hypothesis searches. R13's earlier reserved
fold is now consumed and is **NOT** an independent confirmation of R14.

**Primary frozen R14 hypothesis:** combining the two disjoint rules
under identical in-process native Kissat execution yields reproducible
PAR-2 improvement and fewer large regressions than unselective forcing.

## Rules frozen before prospective data

* Early decision checkpoint: first 512 solver conflicts (same Kissat process)
* Input structural CV: population stddev(variable occurrence degree)/mean
* Old R13 rescue: n>=220 AND 0<p<46.5 AND g>=0.95
* New complementary gate: n==240 AND degree_cv>=0.285 AND p>=43 AND g<0.95
* Proposed primary R14 dual50: rescue OR complement -> native
  restartint=50 starting on conflict 2048. Otherwise never alter the
  solver's restart policy. NO process restart; learned clauses retained.

### 10 paired arms (all identical generated CNF, pinned CPU, three repeats)
- passive `monitor` — same instrumented Kissat binary, no action
- `r11_2048_50` — always intervene at 2048 (positive potential & risk control)
- `r13_rescue50` — frozen previous old rescue only (incremental-gain control)
- `r14_complement50` — only new complementary rule (ablation)
- `r14_dual50` — **PRIMARY** two-sided frozen rule
- `r14_dual25` — same selection, stronger restart interval=25 (intensity control)
- `r14_guarded50` — old rescue OR tighter p>=45 new complement (sensitivity)
- `r13_inverse50` — R13 inverse low-glue as negative/overbroad control
- pinned `original_kissat` — uninstrumented reference program
- unchanged `stable_v1531` — frozen V15.3.1 reference (separate architecture)

Eight policies share the exact same newly compiled patched Kissat
binary (the monitor, two earlier policies and four new policies plus
inverse). Original Kissat and frozen V15.3.1 are not same-binary
causal controls.

## Real prospective testing, two distinct formula families

**Primary random3**: 120 completely new deterministic unbiased Random
3-SAT formulas n=200/220/240 (40 per size), clause/variable ratio
round(4.23*n). Exactly 60 development and 60 RESERVED new test
formulas, two 10-formula shards per n/fold. No outcome-based selection.

**External-family-like transfer (not official)**: 40 additional newly
generated 3-CNF formulas n=220/240 with four variable communities and
65% of clauses sampled entirely within one community; 20 development
and 20 RESERVED test. This is a **synthetic differently structured
family**, not an official benchmark or an externally sourced SAT
Competition formula. Different generator seeds and SHA IDs.
Report transfer independently; do not pool with the primary endpoint.

All 160 formulas generated deterministically:
`seed=614140000 + n*10000 + (test?1000:0) + shardpart*10 + j
      + (community?20000:0)`
No source formula reuse. Historical SHA256 registry contains 1774
canonical project formula identities from R7–R13; all new CNF SHA must
be absent and mutually unique.

**Workload:** 160 CNFs × 10 modes × 3 repetitions = 4800 individual
SAT invocations in 16 shard runners, each runner CPU-pinned within
shard. Use wall time PAR-2 cap=12s, penalty 24s. Interleave mode
ordering reproducibly. Preserve all inputs, raw telemetry JSONL,
measurements CSV, manifests, SHA256 of inputs and executables,
rule SHA, frozen source revisions, Git commit, runner, CPU ID,
random generator seed and actual switching event.

## Validity, metrics and documentation gate

1. All 4800 attempt rows must be present; each formula/mode/rep pair
   exactly once. Verify 160 distinct SHA-256 identifiers and no
   overlap with frozen registry, unchanged solver source pins and
   same runner/CPU for each within-formula comparison.
2. Every SAT answer must have a satisfying witness; reject any
   invalid assignments or SAT/UNSAT disagreement. Uncertified UNSAT
   claims remain preliminary and must NOT be called formal proofs.
3. At conflict <=384 the monitor and modified policies must have
   identical conflict-checkpoint telemetry (propagations, restarts,
   LBD/glue, learned clauses, decisions etc). Validate native
   R14_CHOICE marker against Python frozen-rule reconstruction,
   and before/after learned clause counts and restart interval.
4. Primary endpoint: *R14 dual50 vs passive monitor on ONLY the
   60 randomly generated NEW reserved random3_test formulas*.
   Report exact seconds, 3-replicate formula-level PAR-2, absolute
   gain, total percentage and 95% stratified formula-block bootstrap
   confidence intervals. Assess incremental comparison dual50 vs
   old rescue50, severe >2x regressions, >2x gains and gate activations.
5. Secondary: separate 60 random3 development, 20 community
   development and 20 community test formulas, plus subgroups n.
   Report placebo/ablation/intensity controls and scatterplots of
   early p, early g, degree CV against log2 formula-level speedups,
   with negative outcomes preserved.
6. No formal positive claim if the primary CI spans zero or correctness
   is not independently established. Positive synthetic-family
   evidence requires future different, genuinely external/official
   classes with known certificates and independent frozen validation.

V15.3.1, R11, R12, R13 source and historical experimental results
remain unchanged. R14 uses a new isolated branch; do not overwrite
other experimental reports or the SQLite analytical database unless
a separate evidence-verified ingestion run succeeds.
