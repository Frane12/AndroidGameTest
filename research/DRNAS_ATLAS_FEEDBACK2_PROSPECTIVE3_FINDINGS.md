# DRNAS ATLAS — Feedback2 / Prospective3 (11 November 2026)

## Reproducible status
- Run: https://github.com/Frane12/AndroidGameTest/actions/runs/42948039380
- Separate experimental branch; stable main unchanged.
- Feedback2: compile-time native CDCL instrumentation `DRNAS_ATLAS_TRAIN_TRACE`; sampled decision outcomes are `conflict_backjump`, `restart_abandoned`, `sat_retained`, `timeout_censored`. These are observational, **not causal reward labels**. Each records decision ID, literal, decision depth, target depth, cumulative and subsequent conflicts, learned clauses and most recent learned clause width.
- Streaming: line-flushed `DRNAS_CDCL_OUTCOME` and `DRNAS_CDCL_EVENT`, consumed and flushed as JSONL with original source SHA and arm.
- Smoke: source-generated pigeonhole example produced 169 decisions, 147 conflicts, 146 learned clauses, 26 sampled conflict-backjump outcomes; native selftests passed.
- Frozen selector memory SHA-256: `babd097ec82f9d646b8de1d38b4a2d3ae7024c0cba35924895a4d0e6504bc0fa`. No train or holdout memory updates on this run.
- Prospective3: 100 source-SHA-disjoint formulas (5 fresh formulas in each of 20 categories), 2 repetitions, 6 arms, total 1,200 trials; 5-second cap; one logical CPU per solver; 5 shards plus merge completed successfully. 25 original SATLIB sources and 75 deterministic synthetic sources.

## Total results

| Arm | Original SAT witnesses verified / 200 | UNSAT reported, not independently certified | UNKNOWN | PAR2 (reported SAT+UNSAT), sec | PAR2 (independently verified SAT only), sec |
|---|---:|---:|---:|---:|---:|
| DRNAS A | 146 | 40 | 14 | 165.599210 | 549.969700 |
| GF2_SELECTIVE | 146 | 40 | 14 | 165.688367 | 549.993611 |
| MAP2_LIVE | 146 | 40 | 14 | 166.164474 | 550.387793 |
| Frozen POLICY | 146 | 40 | 14 | 165.826511 | 550.231787 |
| Kissat | 150 | 50 | 0 | 24.974034 | 502.984995 |
| CryptoMiniSat (1 thread) | 150 | 40 | 10 | 115.152984 | 506.234270 |

Kissat advantage over DRNAS A on reported-status PAR2 is 6.63×. CryptoMiniSat advantage 1.44×. Reported UNSAT is **not** independent LRAT validation, and should be kept separate from certified solve counts. On independently verified SAT only, all reported UNSAT outcomes incur PAR2 timeout penalty.

## Notable category results (10 trials per category per arm)

| Category | DRNAS A PAR2 reported | Kissat PAR2 reported | CryptoMiniSat PAR2 reported | Observation |
|---|---:|---:|---:|---|
| uf100-430 original SATLIB | 0.056 | 0.188 | 0.036 | DRNAS A 3.36× faster than Kissat on these very short SAT trials; CMS faster than DRNAS |
| uuf100-430 original SATLIB | 0.084 | 0.248 | 0.051 | DRNAS reported faster than Kissat; UNSAT lacks independent proof |
| uf250-1065 original SATLIB | 49.396 | 2.381 | 5.794 | DRNAS only 6/10 reported solved, Kissat 10/10 |
| uuf250-1065 original SATLIB | 87.912 | 20.759 | 84.514 | DRNAS only 2/10 reported solved, Kissat 10/10 |
| pigeonhole_unsat generated | 27.598 | 0.933 | 24.307 | DRNAS 8/10 reported solved, Kissat 10/10 |
| flat200-479 original SATLIB | 0.245 | 0.178 | 0.124 | All 10/10 original SAT witnesses verified |

Other short synthetic categories mostly finished in 0.015–0.031 seconds aggregate over 10 trials. Such timings are especially sensitive to measurement overhead and scheduling.

## Learned selection and feedback
- Previously frozen merged 400-source memory contained 20 categories; its prospective policy selected `A` on **200/200 policy trials**. This is conservative abstention, not evidence of learned per-formula routing improvements.
- Native A: **4,806 sampled backjump outcomes**, **328 sampled restart-abandonments** across 200 trials. Total native decisions: **910,180**, conflicts: **766,989**. These samples are not independent training cases.
- GF2_SELECTIVE: 0 new live CDCL XOR implications on this cohort. Source XOR detection alone did not produce observable propagation wins.
- Trace overhead is included in DRNAS E2E times but not in Kissat/CMS; therefore the cross-solver numbers are diagnostic and should be complemented by a no-trace matched run before making publication-grade absolute speed claims.

## Next controlled experiments
1. Compare native A with and without compile-time feedback tracing on paired source SHAs to quantify instrumentation overhead.
2. Collect genuine GF(2) novelty cases where source-entailment produces implications that watched-clause BCP did not produce; verify each reason and attempt original-CNF UNSAT proof certification.
3. Change route-selection thresholds **on a new training set**, not on these 100 prospective inputs; freeze then test prospectively again. Compare under original E2E and one CPU.
4. Keep per-decision backjump/restart labels diagnostic; train strategy preferences only from matched verified episode outcomes, and guard against formula/category leakage.
