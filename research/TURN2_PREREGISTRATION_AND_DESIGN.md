# DRNAS TURN2 — structural representation pivot (preregistered)

**Status:** Experimental, TURN1 immutable. Freeze TURN2 code before measuring new formulas.

## Grounded motivation from TURN1
- TURN1 audited all 144 source-paired attempts on 12 official SAT2026 originals, cap 60 s.
- Primary random-both Kissat representation: PAR2 **2519.866846 s** versus native Kissat **2478.684865 s**, ratio **0.983657**: rejected.
- The SAT original `ee44c3f4...` improved from 3.03 to 2.00 s in both reps using the combined random intervention.
- The UNSAT original `ae48df65...` regressed from 36.31 to 57.93 s.
- On other 10 sources the Kissat comparison censored at 60 s (no timing information from solves). Generic UNSAT lacks independent LRAT.
- One representation seed was reused for all sources; no causal explanation of *why* a transform worked.

## What TURN2 changes

**A fixed structural representation, not a learned outcome-selected router:**
1. Compute degree and polarity counts from the exact original CNF.
2. `struct_signed`: map most-occurring variables to lower new variable IDs and flip variables with more negative than positive occurrences.
3. `struct_order`: preserve variable numbering/signs but sort each clause by variable-degree priority and all clauses by length then total degree (deterministic tie-break).
4. `struct_both`: combine those operations.
5. Full clause-multiset inverse replay including empty and duplicate clauses, exhaustive toy SAT equivalence, original SAT model validation.

Two frozen comparison arms: `kissat_plain` and the exact original TURN1 fixed `kissat_turn1_both`. `cms_plain` is a non-primary backend reference. All six arms are run on the same SHA-locked original, on one CPU, serially in randomized order.

**Primary**: `kissat_struct_both` versus `kissat_plain`.
**Ablations**: `kissat_struct_signed`, `kissat_struct_order`.
**Secondary controls**: exact TURN1 random both representation and CMS plain.

## Prospective protocol
- First 12 next eligible original SAT2026 CNFs from the existing frozen 400-source queue.
- Exclude by exact source ID and source SHA from TURN1 and all nine previously enumerated manifest/exclusion collections. A fresh dataset relative to known manifests is not *globally blind*.
- Size eligibility and URL identity are precommitted; **no runtime outcomes select sources**.
- **12 originals × 6 modes × 3 repetitions = 216 attempts**, one 60-second wall cap including Python worker startup, DIMACS parsing, feature extraction, transformation, writing, solver run, model inversion and verification.
- Each original stays on a single CPU-pinned shard. 12 shards, max 6 running in parallel.
- Hash-pin source, transformations, binary, queue, and exclusions before paired tests.
- Record exact end-to-end PAR2, solved counts, SAT witness, per-formula paired gains, regressions and 5000 source-cluster bootstraps. End-to-end CPU and RSS snapshots are optional successful-solve telemetry.
- Score a timeout as PAR2=120 s, never compare solved runtime to timeout 60 s without censoring awareness.
- Mark the primary performance signal only if ratio >1.05, bootstrap low95 >1, at most one source with >10% paired PAR2 regression and no reduction in solved attempts.
- **No solver promotion:** generic UNSAT answers do not have independent proof certificates.
- No seed search, no machine-learning calibration, and no new outcome-dependent decisions after source freeze.

## Separate CDCL early-dynamics diagnostics AFTER audit
A distinct GitHub Actions post-audit job runs native Kissat on each original using:
- `--conflicts=5000 --statistics`, wall cap 8 seconds;
- Original, fixed TURN1 combined, and TURN2 structural combined representations;
- Extract statistics **only when unambiguously emitted**; retain raw lines for conflicts, decisions, restarts, propagations; mark missing fields `null`.
These runs are **not** part of 216 scored attempts and may be censored by the 8-second cap. This is observational work, not a causal performance claim.

## Decisions after audit
If the main result fails, retain TURN2 as research evidence; do not promote it or reinterpret a favorable single source as the primary win. Explore an independent source-only selector only on a separate development cohort, freeze before a different blind holdout.
