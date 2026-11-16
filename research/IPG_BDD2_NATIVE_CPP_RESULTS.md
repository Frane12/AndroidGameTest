# DRNAS IPG-BDD2 — native C++ source-BDD two-count proof-first guard

## Status and evidence — 2026-11-16

**Completed single-process C++ integration on an experimental branch.**
No `main` change, no APK, no parallel/portfolio solver, and no Python
inside the native solve. All prior modules remain opt-in and can coexist:

  PCMAX weighted BDD capacity / VeriPB
  -> IPG1 exact integer cover / independent exhaustive certificate
  -> IPG-BDD2 two-class source-BDD count profiles / independent count checker
  -> CDCL + MG7 residual SCC / DRAT

The proof paths remain distinguished in the solver output. There is
no conversion of the IPG-BDD2 structural certificate to DRAT or VeriPB.

Completed audit:
https://github.com/Frane12/AndroidGameTest/actions/runs/43838231167

- 16 generated BDD-encoded original-source CNFs for two/three machines.
- Native C++ identified 12/12 expected UNSAT, independently checked
  from original source clauses; 4/4 generated SAT controls returned valid
  full SAT models via CDCL fallback, no false UNSAT.
- 7 frozen original PCMAX benchmarks: 1 independently source-verified
  (PCMAX m11-1517-6802 #44), 6 UNKNOWN at the configured budget.
- PCMAX #44: 21 eligible one-hot groups; the proof selects 16;
  11 machines and 1,250 source-supported BDD transition rows.
- IPG-BDD2 module: about 0.00894 s; native executable invocation
  about 0.01526 s on one GitHub runner (single trial, cache not flushed).
- All IPG-BDD2 generated profiles, count-class selections, and machine
  reachability rows matched the separate Python reference producer.
- Every claimed IPG-BDD2 UNSAT passed the independent backward profile
  checker and checked the source SHA256, original one-hot clauses,
  original BDD implication clauses, asserted roots/terminals, and
  count-state elimination.
- Mutated source, graph edges, profile claims, target count classes,
  and SHA proof binding were rejected by the independent checker.
- Historical native union without IPG-BDD2 was also compiled and
  exercised as a regression reference.

These are retrospective original PCMAX formulas, NOT a blind source-disjoint
holdout or performance ranking. The #44 UNSAT was previously solved by
the old capacity module; IPG-BDD2 is a distinct mathematically valid route,
not a new previously-unsolved benchmark. The IPG-BDD2 structure is currently
limited by 56 selected jobs, 48 machines, 1,200 count states per BDD node
and a bounded operation/time budget.

## How the proof works

Each selected original CNF clause

  x_(j,1) OR x_(j,2) OR ... OR x_(j,m)

is source checked, including pairwise at-most-one clauses. A satisfying
assignment picks exactly one selector in each selected group. The
existing PCMAX source extractor proves BDD machine roots and
transitions from original DIMACS clauses (never the filename/labels).

Split any source-checked subset of these jobs into two disjoint
classes A,B. Other jobs are ignored, so this is a relaxation.
For every machine i, profile P_i contains count pairs (a,b)
realizable on some accepting BDD path. All skipped BDD selector
levels are treated as freely true/false to remain conservative.

Let R_0={(0,0)}. Then compute exactly:

 R_(i+1) = {r+p : r in R_i, p in P_i,
                    r_A+p_A <= |A|, r_B+p_B <= |B|}.

Whenever (|A|,|B|) is absent from R_m, the original CNF is UNSAT.
This is a sufficient structural proof with polynomial count states
in the size of the EXPLICIT original BDD for a fixed 2-class
dimension; it is neither complete nor a general polynomial PCMAX
algorithm (the encoding BDD can itself grow exponentially).

Native source extractor and count profiles are implemented together
in `src/ipg_bdd_count.hpp`. The standalone Python checker
`research/ipg_bdd_checker.py` uses an independent BACKWARD recurrence.
It checks ORIGINAL DIMACS source clauses and does not import C++
or rely on claimed SAT/UNSAT labels.

## Reproduce

    cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
    cmake --build build --target drnas-pcmax-mg7-ipg1-bdd2 -j2

    ./build/drnas-pcmax-mg7-ipg1-bdd2 SOURCE.cnf \
      --mode core --time 5 --stats \
      --pcmax-capacity --pcmax-budget-ms 0 \
      --pcmax-certificate source.capacity.json \
      --ipg-bdd2 --ipg-bdd2-budget-ms 750 \
      --ipg-bdd2-graph source.graph.json \
      --ipg-bdd2-certificate source.count.json \
      --residual-scc --proof source.drat

Use --pcmax-budget-ms 0 ONLY when you specifically wish to
test IPG-BDD2 in isolation against the same source as old capacity.
For normal operation, give the existing PCMAX capacity guard
a positive small budget so it can solve its known successful cases.

The C++ solver prints:

  c PCMAX_UNIFIED_PROOF_KIND IPG_BDD2_JSON_NEEDS_INDEPENDENT_CHECKER

When this is the UNSAT route, verify on original bytes:

    python3 research/ipg_bdd_checker.py \
      --cnf SOURCE.cnf --graph source.graph.json \
      --certificate source.count.json

Accept only IPG_BDD_ACCEPT / return code 0. The structural certificate
is NOT DRAT, LRAT, or VeriPB and must not be entered into
DRAT-verified PAR2 scores.

Run all source-bound native vs independent checker regression tests:

    python3 -u research/ipg_bdd2_native_benchmark.py

## Next acceptance gates

1. Implement a compact source-derived VeriPB certificate for count
   infeasibility, rather than the experimental JSON structural proof.
2. Test on source-disjoint, future original PCMAX formulas and measure
   verification-inclusive PAR2 / peak RSS against old frozen references.
3. Add richer fixed-dimensional count signatures without a systematic
   exponential state search; reject unsupported structure safely.
4. Promote only if no false SAT/UNSAT, no regressions and verified PAR2
   acceptance criteria are satisfied.

Main branch and frozen comparison builds have not been changed.
