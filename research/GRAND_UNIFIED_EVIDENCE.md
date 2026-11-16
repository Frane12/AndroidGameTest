# DRNAS GRAND-UNIFIED-EVIDENCE: proof-gated research union and real-original PAR2

Date: 2026-11-16. Branch:
`experiment/drnas-unified-evidence-par2-20261116`.
**No changes to main, frozen references or APK. No auto-promotion.**

## What is genuinely integrated

The **existing tested C++ single-process** native target
`drnas-pcmax-mg7-ipg1-bdd3` (based on
`experiment/drnas-ipg-bdd3-native-3count-20261116`) already combines:

1. PCMAX source-BDD weighted-capacity proof-first analysis, source
   certificate + original-source VeriPB proof;
2. IPG1 exact integer configuration cover (up to 15 jobs), **exponential**,
   project-specific independently checked original-source certificate;
3. IPG-BDD2 polynomial-in-explicit-BDD two-class count analysis,
   project-specific independent original-source certificate;
4. IPG-BDD3 three-count source-BDD profiles,
   project-specific independent original-source certificate;
5. MG7 residual SCC with DRAT-checkable reason clauses;
6. Native CDCL fallback with DRAT and independently checkable SAT models.

All modules remain opt-in, bounded, and return UNKNOWN on unsupported
structures. Existing C++ binaries are unchanged.

## Additional safe, research-stage integration

`CXX_UNION` is a **SERIAL, proof-gated research pipeline**:
`research/unified_evidence/precheck.py` first attempts, under a
strict bounded wall-time and source-size gate:

* binary/unit CNF implication-subformula contradiction;
* STRUCTURE1 (MATCH1/Hall and exact-one/parity);
* MATCH2 capacitated Hall on source forbidding tuples;
* MATCH2-BDD-MASK1 exact source-derived job mask partition DP.

An UNSAT claim requires `check_preproof.py` to re-read and verify
the exact original source, independently invoking the relevant
structural checker (or rechecking binary mutual reachability).
Otherwise execution falls through to the single native C++ union
above **with the remaining global time**. This does not execute
two SAT solvers concurrently, and every process is CPU-pinned, but
it **is not yet one compiled C++ process**: Python source analysis
and C++ fallback are sequential separate processes.

The X59 GF(2)/SAT constructor/ARG3/MATH5 family is a **separate
certified comparison arm** (`X59_MATH5`), NOT silently merged into
the unrelated X5 C++ engine. A green build never proves all individual
historical R/X/CF variants are jointly beneficial. Unsupported
unverified experimental proposals (unverified algebraic claims,
cross-instance memory learning without independent holdout, proofless
UNSAT) are not promoted into this candidate.

## Real-original paired benchmark

Frozen inputs and reference binaries are restored from the already
completed GitHub Actions run `43712040086`,
artifact `realblind100-frozen`. Its original SAT Competition 2026
Main-track sources were selected earlier, with exact SHA-256 manifest,
prespec file, family labels, and copies of Kissat, CaDiCaL,
CryptoMiniSat, native X59, X59+MATH5, drat-trim and frat-rs.

**This is a RETROSPECTIVE DEVELOPMENT/REGRESSION benchmark.**
The source set and several methods have already been evaluated.
The original request targeted 100 sources but only 67 were accessible
in the frozen previous run; the benchmark MUST report actual N and
never assume all 100 were obtained. It is **not a newly blind
prospective holdout**, and previous 2026 sources must not be counted as
fresh independent scientific evidence.

Arms (nine, each run on identical frozen original CNF bytes):
`X59_OFF`, `X59_MATH5`, `CXX_BASE`, `CXX_BDD3`,
`CXX_UNION`, `CORE1_FROZEN`, `Kissat`, `CaDiCaL`, `CryptoMiniSat`.

* Two serial, shuffled repetitions per source and nine arms.
* 8-second **E2E** wall cap including stage preprocessing, solver
  startup, source SHA checks, proof generation and proof verification.
* One logical CPU per solver/attempt (pinned affinity); no concurrent
  solver portfolio within a trial.
* 4 GiB process address-space limit and 256 MiB output-proof limit.
* Native result SAT accepted only with a model satisfying all original
  CNF clauses; source labels never authorize solving claims.
* Native UNSAT counted only on independently accepted original-source
  VeriPB, DRAT/FRAT, or (separately labeled) project-specific source
  checks of BDD2, BDD3, IPG1, MATH5, and the union prechecks.
* `strict_PAR2`: model, independent DRAT/FRAT, or **standard VeriPB**.
  Custom structural JSON, however source-checked, is *not* counted as
  competition-standard proof.
* `structural_PAR2`: standard proofs plus accepted custom source
  checks; keep this separate from `strict_PAR2`.
* All UNKNOWN, TIMEOUT, incomplete proofs, excessive checker runtime
  and invalid outputs receive PAR2 penalty `2*cap = 16s`.
  An invalid model or unverified proof is a hard critical condition,
  never counted as a successful result.
* Per-source paired E2E comparisons with both individual-source
  bootstrap and source-**family** clustered 95% interval.
  Two repeats on the same source are not independent families.
* Proof files are transient and verified; binary/source SHA manifests,
  per-trial results, logs and aggregated statistical report are archived.
* No claims of world ranking, official competition result,
  statistically proven universal speedup or P=NP.

Expected trials = `actual_N * 2 * 9` (1206 if N=67).
The previously validated native **CORE1** SAT constructors, ARG3, MATH5 and Hall/BDD proof guards are restored from pinned run `43717935841` and compared as their own immutable `CORE1_FROZEN` arm, with its independent Hall/MATH5/capacity certificate checker. This is not represented as native integration into the X5 CDCL code.\nNo posthoc pruning of slow/failed source families.
The best reference is selected among the three fixed standard solvers
on the SAME trial matrix (not from a different benchmark).

## Reproduce

Workflow:
`.github/workflows/drnas-grand-unified-evidence.yml`

`preflight`: restore pinned originals/binaries; build native CXX
baseline + BDD3 C++; cargo-install VeriPB 3.0.2; check Python syntax
and source-tamper smoke tests; SHA-pin complete execution inputs.

`paired`: 10 shards / max 5 workers, serial per-shard paired 9-arm
trials, one CPU each.

`aggregate`: require complete exact source-ID/rep/arm matrix, check
source SHA, reject contradictory certified answers, output two PAR2
tracks and family-block bootstrap results in
`unified_evidence_results/final.json`.

This workflow may not have completed when the branch is first committed.
A *completed success* final artifact is REQUIRED before reporting new
benchmark numbers. If unavailable, state no results rather than
estimating.

## Required next research

* Port proved MATCH2/MASK/parity source guards to native C++ one-process
  with independent checker contracts and strict proof budgets.
* Export full standard DRAT/VeriPB certificates for BDD2/3 and MASK,
  not only project-specific JSON certificates.
* Measure CXX_BDD3 vs CXX_UNION to quantify extra source-check overhead,
  and report which modules individually cause regressions.
* Freeze a NEW, source-family-disjoint prospective 2027/novel original
  holdout before any production promotion.
* Never merge into main without explicit approval and a verified
  improvement over best reference including checker costs.
