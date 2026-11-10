# DRNAS GF-CDCL NOVEL2B — final strict smoke audit, 2026-11-10

Source: https://github.com/Frane12/AndroidGameTest/actions/runs/42821218497
Workflow conclusion: SUCCESS. Same pinned CaDiCaL source/binary used for clean/direct/derived-only/shadow; one logical CPU per child, original SHA checked, two repeats, 6s nominal cap. Two original SHA from the previously seen 40-case XORABC3 cohort, selected using XOR structural properties before NOVEL2B timing; **not a blind holdout**.

## Proven mathematical and software progress
- `GFCDCL_NOVEL2_SELFTEST_PASS`: original complete XOR CNF unit propagation with x3 assigned does not infer x4; source-proved sum of 2 XOR3 rows implies x4 and native IPASIR-UP reason `x4 OR ~x3`. 16-model exhaustive check, rollback and shadow pass.
- `GFCDCL_NOVEL2B_REDUCTIVE_SELFTEST_PASS`: strict width-reducing pairwise XOR closure pass; disjoint XOR2+XOR2 noise rejected; unit-width derived rows explicitly deferred to a separate proof track.
- 40 original SHA were source-only screened. Top two sources: SHA `6e054967f4c71d900b2bba2508fea2054ac13de78fa0b0b6a94753f66e9e95fc` yielded 48 distinct reductive binary relations, `bea05a068fac0c80b91bb09152f6dcdc3f750d359e76e7058ef54a6622e98542` yielded 26.
- Source XOR extraction is independently checked against original SHA CNF. GF2 pairwise consequences are mathematically entailed by the source-certified rows. This is *not* independent original-CNF UNSAT LRAT certification, nor a live CNF-UP novelty oracle for each solver proposal.

## Real E2E outcomes by arm (4 trials/arm)
| Arm | independently verified SAT | timeouts | PAR2 strict SAT-only s | total wall E2E s | derived proposals | completed reason clauses | native CDCL decisions |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| clean | 0 | 4 | 48 | 22.047 | 0 | 0 | 1,151,688 |
| direct (prior closure) | 0 | 4 | 48 | 22.047 | 566 | 184 | 773,831 |
| novel2b (strict shortening) | 0 | 4 | 48 | 22.049 | **734** | **132** | 922,611 |
| novel2b_shadow | 0 | 4 | 48 | 22.047 | 0 | 0 (11,429 shadow candidates) | 912,906 |

NOVEL2B examined 1,054,336 derived-row instances and skipped 1,577,073 source-row events, with 734 direct proposals and 132 completed reason clauses. None of the four arms solved an original problem under the cap. The apparent reduction in decisions relative to clean *at the same timeout* is only a diagnostic, not a speedup. Direct delivers more completed explanations than NOVEL2B (184 versus 132) and has fewer decisions (773,831 versus 922,611), so NOVEL2B is **not** promoted.

## Causal follow-on check against XORABC3 reference logs
Source-only structural scan of the previous frozen 40 SHA found seven sources with strictly reductive GF2 pair candidates. Their CaDiCaL clean reference runs in XORABC3 (two repeats, 10s cap) **all timed out**. Thus the current source-conditioned cohort does not supply a suitable reference-easy case for an immediate E2E speedup demonstration. Do not claim a failure of GF2 math merely because all hard instances time out.

## Decision and next hypotheses
1. **Stop repeated hard-only fixed-cap benchmarks.** Gather a fresh reference-easy/mid source-only crossover cohort with actual cancellation candidates; freeze source SHA and all binaries before candidate timing.
2. Instrument the distinction among *proposed*, *reason requested*, *reason completed*, *new solver assignment*, and *conflict learned*. Current reason-completion is not a unique net-new solver implication.
3. Reduce low-yield 1,054,336 derived scans using event-indexed high-value-row scheduling and a measured CPU-cost budget; preserve exact reasons and reversibility.
4. Consider certified single-literal GF2 pair reductions as a separate proof-first experiment; not represented in the current 2-watched propagator.
5. Promote only after SAT original witness + independently checked UNSAT proofs on unseen original CNF with better matched PAR2 against direct, clean and placebo.

Main branch unchanged.
