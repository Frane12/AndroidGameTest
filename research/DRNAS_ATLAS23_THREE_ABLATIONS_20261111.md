# DRNAS ATLAS23 — three experimental native variants (2026-11-11)

Branch: experiment/drnas-atlas23-21m-three-ablations-20261111
Parent: ATLAS22 / generated ATLAS19 native engine; main unchanged.

## Evidence and motivation
ATLAS21M run 42992456551: on SAT source be9bb644... (two attempts) native A took 0.426s, C7 13.801s and Kissat 0.085s. One C7 attempt had 131880 conflicts and over 217 million watch visits; A had 9103 conflicts and 6.39 million watch visits. This is a search-path regression, not merely per-operation overhead.

## New variants
- V23_A_MIN: enable only the existing reason-checked learned clause minimizer on A. Keep A branching, restart logic and no learned-clause deletion.
- V23_C7_AGE: C7 plus a learned-clause age gate (20000 conflicts); missing age metadata is protected. Birth metadata is remapped during clause compaction alongside LBD metadata.
- V23_C7_STABLE: C7 with stochastic phase flipping disabled. This also changes random-number consumption and thus potentially later branching decisions; it is a behavioral ablation, NOT a pure causal phase-flip isolation.

The new C++ is generated under mre_atlas23; older generator files and original SHA/CNF are unchanged.

## Benchmark design
Build + native selftest + smoke, then two parallel cohorts, one logical CPU per solver and matched seed/order.
- Regression: ten exact ATLAS21M SHA, five SATLIB families, indices 0..1, two repetitions, 10-second wall cap; explicitly nonblind.
- Extension: six SATLIB SHA, three families, indices 10..11, two repetitions, 12-second wall cap. Disjoint from the ATLAS21M/ATLAS22 subsets but NOT globally blind; earlier WIDE500 work used initial archive entries.
- Arms: A, C6_KEEP, C7_ADAPT, V23_A_MIN, V23_C7_AGE, V23_C7_STABLE, pinned Kissat, CMS.
SAT witnesses are checked on the exact source CNF. UNSAT without independent LRAT/GF2 certificate is NOT verified. Keep strict-verified PAR-2 separate from reported PAR-2 and never pool the 10s and 12s cohorts.

Decision: prioritize improved SAT-verified solved count, strict PAR-2, fewer absolute conflicts and watch visits on the original regression cohort, no correctness divergence, and non-regression across unrelated formulas. Later validate winning mode on a genuinely untouched source-disjoint real-original cohort.

Workflow: .github/workflows/drnas-atlas23-three-ablations.yml
Builder: research/drnas_atlas23_build.py
Runner: research/drnas_atlas23_benchmark.py
