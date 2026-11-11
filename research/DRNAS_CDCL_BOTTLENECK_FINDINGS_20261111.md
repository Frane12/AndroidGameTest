# DRNAS R3C — CDCL bottleneck diagnosis (2026-11-11)

## Authoritative source and controls

Experimental code: `experiment/drnas-cdcl-bottleneck-20261111` (stable main unchanged).

GitHub run: https://github.com/Frane12/AndroidGameTest/actions/runs/42949736637

- 7 deterministic previously-seen CNFs: 2 original SATLIB uf250-1065, 2 original SATLIB uuf250-1065, 2 synthetic pigeonhole UNSAT, 1 original SATLIB uf100-430.
- 2 repetitions per source, 8-second cap, one logical CPU per trial, same C++ solver code with five compile-time ablations, same profile instrumentation for all variants.
- Native selftests passed on all five builds, including 240 oracle-checked cases / 720 attempts each.
- A and BLOCKER use the same variable heuristic, identical restart policy, and 1-UIP search; the only switch is `DRNAS_ONE2_BLOCKER` watch entries with cached true-literal blockers. Caching may change watch traversal and consequently the exact search path.
- `FAST100`: force fixed restart interval 100 conflicts. `NEGPHASE`: initialize all decision phases negative. `TRACE`: enable bounded live CDCL event/outcome logging. No training or selector changes.

## Aggregate paired results

| Arm | SAT original verified | UNSAT reported without independent proof | UNKNOWN | Raw E2E sum s | Reported PAR2 s | Conflicts | Decisions | Watch visits | BCP time s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| BASE | 4 | 6 | 4 | 39.240655 | 71.218815 | 246433 | 290503 | 593213760 | 37.659329 |
| BLOCKER | 6 | 8 | 0 | 23.124696 | 23.124696 | 276326 | 325224 | 783980936 | 21.366142 |
| FAST100 | 2 | 6 | 6 | 59.660569 | 107.630079 | 356641 | 464142 | 927415577 | 57.432876 |
| NEGPHASE | 4 | 6 | 4 | 40.882753 | 72.861872 | 282375 | 333198 | 631007547 | 39.0896 |
| TRACE | 4 | 6 | 4 | 39.451156 | 71.429399 | 248290 | 292672 | 602219608 | 37.8096 |

BLOCKER vs BASE:
- Raw E2E sum 1.697× lower, reported PAR2 3.080× lower because BASE hit 4 timeouts vs none for BLOCKER.
- Six verified SAT results vs four, eight **uncertified** UNSAT results vs six. **Do not claim 14 independently certified solves.**
- `uf250-1065` source index 26: BASE TIMEOUT at ~8.005 s for both repetitions; BLOCKER verified SAT at 2.622 and 2.586 s.
- `uuf250-1065` source index 25: BASE UNSAT at 3.660 and 3.497 s; BLOCKER reported UNSAT at 1.331 and 1.344 s.
- `uuf250-1065` source index 26: BASE TIMEOUT twice; BLOCKER reported UNSAT at 7.635 and 7.547 s.
- `pigeonhole_unsat` index 26: BLOCKER slightly slower (0.0132 vs 0.0129 s); there is no universal win.
- `uf250-1065` index 25: changing only initial phase makes SAT ~1.10 s vs BASE ~0.010 s; phases can change search path drastically.
- FAST100: reported PAR2 1.51× **worse** than BASE (107.630 vs 71.219), and four-figure restart count across short runs; do not globally activate this fixed interval.
- TRACE: 0.54% larger E2E sum vs BASE on this small experiment. Timing includes capped trials, so this is a preliminary overhead check, not a rigorous microbenchmark.

## Why the baseline spends so much work

1. **BCP is dominant:** BCP time = 37.659 / 39.241 = 95.97% of base E2E. Branch-variable selection and 1-UIP conflict analysis are far smaller direct CPU expenditures.
2. **Learned watch traffic:** BASE visits 593,213,760 watch entries, of which 559,378,119 (94.30%) are counted as learned-clause watches and 33,835,641 as original-clause watches. On this selected sample it is the learned-clause watch traffic that dominates.
3. **No learned-clause garbage collection:** R3C always appends new learned clauses; `Clause` stores a `std::vector<int>` and a boolean, without LBD and without a learned-clause deletion mechanism.
4. **No clause minimization / LBD-quality policy:** native 1-UIP adds the learned literals as-is. It computes a backjump level and bumps activities but never recursively minimizes learned clauses or ranks their lifetime by LBD.
5. **Static geometric restarts:** first threshold 100 conflicts, interval grows 1.5× toward 30,000 without a quality-dependent restart trigger. A naïve fixed 100-conflict policy was empirically worse, so this must be evaluated adaptively rather than assumed better.
6. **No inprocessing in A baseline:** native A directly loads original CNF, watched BCP and 1-UIP, no substantial preprocessing/vivification/variable elimination; Kissat has highly tuned search and inprocessing. Those differences are plausible contributors but have NOT been isolated by this experiment.

The first test cohort with 100 fresh formulas had 766,989 native A conflicts; 755,841 (98.55%) came from just three categories: `uf250-1065`, `uuf250-1065` and UNSAT pigeonhole (30/200 attempts). On the 146 commonly SAT-verified trials from that prospective benchmark, Kissat's geometric E2E advantage was only about 1.09×; its 6.63× reported PAR2 advantage was driven by hard/timeout instances, not uniform speed across all sources.

## Proposed engineering order

1. **Prioritize `DRNAS_ONE2_BLOCKER` as a candidate native default** on a new experimental branch. Confirm the same paired fresh SHA set with and without trace, 1CPU, 5–10s caps, SAT witness checking and independently proof-certified UNSAT where possible. The existing selftests passed but 7 distinct sources is not enough for rollout.
2. **Reduce learned-clause traffic:** add LBD and reason-use/age metadata; implement safe proof-aware deletion only when a clause is not locked as a current reason. Never delete source clauses, preserve unit and essential binary clauses, and respect proof logging when introduced.
3. **Learned clause minimization:** compare original 1-UIP vs recursive minimization with sound reasons, measuring short clause fraction, median/mean LBD, BCP watch visits, and independently checked SAT/UNSAT.
4. **Adaptive restart & phase experiments:** use sliding-window LBD quality and validated novel activity signals. The fixed-100 ablation is clearly negative here.
5. **Isolate preprocessing and inprocessing** only after the BCP and learned database baseline improves.
6. Keep all performance claims separated into verified SAT, independently certified UNSAT (currently unavailable), timeout/UNKNOWN, raw E2E and PAR2.

## Interpretation boundaries

- This is a small targeted diagnosis of **7 distinct formulas × 2 repetitions**, not a blind 100–500 source generalization result.
- Clock timing includes lightweight profile/watch-count instrumentation in all arms. WATCH counter increments themselves create overhead; this is appropriate for matched diagnosis, not publication-grade absolute speed.
- Watch-list traversal changes can alter which clause is picked first, so BLOCKER's improvement can come from **both** less expensive clause checking and a changed search trajectory. Therefore do not attribute the entire 1.70× raw E2E improvement to cache hits alone.
- UNSAT solver exits are **not independently LRAT-certified**. Any relative solve count with uncertified UNSAT is provisional.
