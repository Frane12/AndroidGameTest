# DRNAS BLOCKER × C6 KEEP — audited result (11 November 2026)

GitHub source run: https://github.com/Frane12/AndroidGameTest/actions/runs/42971898599 (20 benchmark shards succeeded; first aggregation failed because historical SHA registries were not present in that branch).

Successful recovery/merge without rerunning any solver: https://github.com/Frane12/AndroidGameTest/actions/runs/42972588238

Machine-readable results: `research/drnas_blocker_c6_cross_summary.json`.

## Frozen experimental protocol
- New source SHA cohort: 100 source files, 20 SAT families × 5 files; 25 SATLIB originals and 75 deterministic synthetic files.
- Source indices 85–89 (ATLAS16 pass1 indices 35–59; pass2/3 indices 60–84). Historical frozen WIDE500, prospective and BLOCKER-BLIND100 SHA registries cross-checked in recovery merge.
- Each formula run with three repetitions and five arms: native A, native BLOCKER, native C6_KEEP, native BLOCKER_C6_KEEP, pinned Kissat; 1,500 matched single-thread runs total; 8s E2E cap per attempt.
- Native A and C6_KEEP use the same binary without `DRNAS_ONE2_BLOCKER`. Native BLOCKER and combo use the same binary compiled with `DRNAS_ONE2_BLOCKER`. C6_KEEP is selected by runtime mode; both C6 modes use identically frozen family policy (default 1.0,0.85; uf250-1065 0.85,0.90).
- No `DRNAS_PROFILE`, no `DRNAS_WATCH_DIAG` and no live CDCL logging in performance builds. Solver outputs checked against original CNF SAT models.
- For candidate UNSAT source CNFs, independently generate a reference Kissat DRAT trace and check it with pinned `drat-trim`; do this AFTER timed solver E2E. Proven original UNSAT holds for all arms on that source; it does NOT certify each native solver's own learning/reason trace.
- Proof files are deleted immediately after checks, max 16 MiB; 27 original-source proofs passed on 27 distinct CNFs. Some Kissat-reported UNSAT sources exceeded proof budgets and must remain unverified.

## Complete benchmark

| Arm | Original SAT witnesses verified | Original UNSAT independently DRAT verified | UNKNOWN | Independently verified solved /300 | Verified PAR2 s | Reported PAR2 s | Raw E2E s |
|---|---:|---:|---:|---:|---:|---:|---:|
| A | 201 | 72 | 27 | 273 | 470.990206 | 470.990206 | 255.218478 |
| BLOCKER | 207 | 72 | 21 | **279** | **402.657314** | 402.657314 | 234.865776 |
| C6_KEEP | 198 | 72 | 30 | 270 | 490.310221 | 490.310221 | 250.761775 |
| BLOCKER_C6_KEEP | 198 | 73 | 29 | 271 | 496.244572 | 496.244572 | 264.791327 |
| KISSAT | 210 | 81 | 0 | 291 | 170.190607 | 70.988378 | 70.988378 |

Native BLOCKER verified-PAR2 ratio vs A: **1.1697× faster**.
BLOCKER_C6_KEEP vs BLOCKER: **1.2324× slower** on verified PAR2.
BLOCKER_C6_KEEP vs A: **1.0536× slower**.
Kissat (verified-PAR2) vs BLOCKER: **2.3659× better**; 9 Kissat UNSAT claims remain uncertified by DRAT under proof budget.

### Severe family regressions (all 15 attempts per arm per family)
- `uf250-1065`: A 6/15 verified, PAR2 168.295 s; BLOCKER **12/15**, PAR2 **106.621 s**; C6_KEEP 3/15, PAR2 195.117 s; combo **3/15**, PAR2 **211.716 s**; Kissat 15/15, PAR2 3.871 s. This category dominates the combo's regression.
- `uuf250-1065`: all native arms 0/15 verified, PAR2 240 s; Kissat 6/15 independently verified, PAR2 162.459 s. Native solver's CDCL remains the principal bottleneck.
- `pigeonhole_unsat`: A 12/15 verified, PAR2 60.864 s; BLOCKER 12/15, 54.369 s; C6_KEEP 12/15, 53.341 s; combo **13/15**, **42.798 s**. On this specific family combining optimizations helps.
- `flat200-479`: all 15/15 SAT verified; A 0.486 s, BLOCKER **0.345 s**, C6 0.484 s, combo 0.372 s.

### Memory and search
- Across all attempts, native peak estimated clause storage: A **13.79 MiB decimal**, BLOCKER **20.56 MB**, C6_KEEP **12.03 MB**, combo **18.37 MB**; maxima come from different source attempts and are not paired memory differences.
- `ru_maxrss` returned approximately 40,360 KiB maximum on all native variants and cannot discriminate memory substantially at this sampling resolution.
- C6_KEEP deleted **125,755** learned clauses with **29** compactions. Combo deleted **278,485** with **55** compactions, despite *worse* performance. Native BLOCKER A mode does not enable C6 deletion.
- Conflicts: A 1,782,453; BLOCKER 2,479,651; C6 1,678,356; combo 2,367,008. More conflicts does not imply faster solving; outcome counts and E2E/verified PAR2 are primary.

## Important static code audit for next cycle (not altered mid-benchmark)

1. **C6 cadence mismatch**: `research/drnas_atlas15_cdcl_patch.py` invokes `atlas15_reduce_db()` only at conflicts divisible by **10,000**. `research/drnas_atlas16_build.py` additionally gates its C6 method on `stats_.conflicts % 1,500 == 0`. In combination, the C6 reduce-body only runs at conflict counts divisible by **30,000** (least common multiple), NOT every 1,500 as originally described. A corrected matched baseline needs to change the caller and explicitly preregister the revised policy.
2. **Stale learned-clause lifetime bookkeeping**: The C6 removal path erases `atlas15_lbd_` but does not erase `atlas15_born_` or decrement `atlas15_live_learned_` (both are updated in the legacy C5 reduce path). During compaction, C6 remaps `atlas15_lbd_` but not `atlas15_born_`. The latter is not used in C6 current candidate choice, but this is still stale metadata/memory growth and can distort the live-clause cap.
3. Do not assume these issues explain all regressions. The 2×2 crossed experiment isolates the combination's observed performance, not the root cause of each SAT search path. Changing watch order and learned reasons changes search trajectory, even with unchanged semantics.
4. A true production-default decision needs an additional source-disjoint blind test AFTER these fixes, with original SAT models and independent native UNSAT proof workflow if implemented.

## Next recommended build
`C6_FIX1`: retain the same 2×2 arm separation but (a) fix reduce cadence to the intended threshold with no nested modulo mismatch; (b) clean LBD/born metadata at deletion, reindex born map during safe compaction, and accurately decrement live counter; (c) add runtime audit counters for live clause invariants and retained/locked reasons; (d) compare against untouched A/BLOCKER and original C6 on *new* hard SATLIB plus pigeonhole formulas. Prespecify as experimental, not automatically merge to main.

**Disposition**: BLOCKER alone remains the best tested DRNAS variant on this cohort. Keep combination off as default; stable main unchanged.
