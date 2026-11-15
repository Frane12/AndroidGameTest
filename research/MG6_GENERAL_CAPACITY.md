# MG6 GENERAL CAPACITY — experimental proof-first pilot (2026-11-15)

## Scope

This is a deliberately conservative **generic CNF clause-level prototype**, not an integrated DRNAS CDCL build and not an optimized new general SAT solver. It discovers disjoint positive at-least-one clauses and partitions their selectors into source-verified pairwise mutex cliques. It does not require PCMAX names, a BDD encoding, external label metadata, or an SAT oracle.

If the number of required groups **G** exceeds the number of pairwise-incompatible resource cliques **R**, it emits a VeriPB 3.0 cutting-planes derivation from the original, unmodified DIMACS clause IDs. Its producer output status is `PROOF_EMITTED_UNCHECKED`, **not UNSAT**. A separate pinned VeriPB 3.0.2 checker must accept the proof to obtain `VERIPB_UNSAT_VERIFIED`.

## Soundness argument

Each selected positive source clause `(v_1 OR ... OR v_k)` implies `sum(v_i) >= 1`. Selected groups have disjoint variable sets. Every selected variable occurs in exactly one clique. Within each clique, every pair `a,b` has an **original** source clause `(-a OR -b)`, i.e. `~a + ~b >= 1`.

From the pairwise clauses the generator derives `sum_{a in clique} ~a >= size(clique)-1`, or `sum a <= 1`, using verified cutting planes additions and integer divisions. For one-element cliques `a <= 1` is tautological and no step is needed. Adding positive group clauses and all machine bounds yields a contradiction when `G > R`.

No user-provided labels or structural inferences are trusted as axioms in the proof: every referenced source clause must exist in the original CNF. The external checker is authoritative.

## Boundaries

* Only positive source groups of width 2–8; simple bounded greedy candidate search (48 groups, 256 selectors), 12 seeds per width.
* Only unit capacities justified by complete pairwise negative source clauses.
* No BDD capacity >1, arbitrary PB coefficients, XOR, clique maximum weight, learned clauses, CDCL integration or performance claims.
* May return UNKNOWN for UNSAT even when stronger capacity certificates exist.
* The first CI pilot is **synthetic**: three positive PHP instances, two known-SAT PHP controls, and 40 planted-SAT controls, all on original generated DIMACS; not a blind holdout or representative real benchmark.

## Reproduce

```bash
python3 research/mg6_general_capacity.py --cnf sample.cnf \
  --proof sample.pbp --report sample.json
veripb --cnf sample.cnf sample.pbp
```

Do not invoke VeriPB on UNKNOWN cases where no proof is emitted. Examine the GitHub Actions logs and attached artifacts to assess the exact independent-check outcome.

## Next gates

1. Cross-check the formal derivation and mutation-resistant SAT controls.
2. Freeze source-disjoint original SAT2024/2026 CNFs and compare coverage against the existing specialized PCMAX guard.
3. Integrate as a cheap same-process, one-logical-CPU pre-gate in a dedicated C++ experimental target, only after proof pipeline correctness is established.
4. Use verification-inclusive PAR2 and frozen Kissat/CaDiCaL/CMS baselines. Never merge into `main` without independently verified nonregression.
