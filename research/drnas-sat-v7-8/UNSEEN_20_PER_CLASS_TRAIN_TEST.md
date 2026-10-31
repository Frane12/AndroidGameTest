# DRNAS SAT V8.9 — 20 unseen train + 20 unseen test per class

Date: 2026-10-31. Research status: experimental; results must be measured, not presumed.

## User-requested balanced split

| SAT family | Train | Holdout |
|---|---:|---:|
| Random 3-SAT | 20 | 20 |
| Random 4-SAT | 20 | 20 |
| 3-coloring graph CNF | 20 | 20 |
| XOR-SAT | 20 | 20 |
| Generalized pigeonhole UNSAT | 20 | 20 |
| **Total** | **100** | **100** |

- One SHA-256 identity per generated DIMACS formula, separate train/test generator domains.
- Strict preflight validates all 200 hashes differ from one another and reconstructed V8.8 (30), V8.8b (25), V8.9 yield (25), V8.9 structural pilot (40) experiment fingerprints. This is an **exact-hash** audit of these 120 earlier formulas; it is NOT an exhaustive mathematical isomorphism test of all historical CNFs. New random draws use independent deterministic seeds.
- Pigeonhole instances use 40 distinct (hole count, pigeon surplus) parameters, checkerboard split (20 per split): each hole count 3..12 appears twice in both splits; each surplus 2..5 appears five times in both splits; no parameter combination shared. All are UNSAT by pigeonhole principle. This intentionally avoids copying older standard p=h+1 pigeonhole instances by permuting literal labels.
- Other families use 4 sizes, 5 independent generated instances of each size in TRAIN, then 5 further independent instances of each size in HOLDOUT.

## Execution protocol

1. **verify-novelty**: deterministic 200-fingerprint audit against known old experiments; static-feature permutation/sign-invariance self-test. Stops pipeline on any collision.
2. **train-shard**: 100 train formulas, three repeats each, 3 reference modes (CaDiCaL plain, v7.6 guided, v7.6 plain): **900 solves**. Five single-core shards.
3. **fit-train-only**: select from a small predeclared set of one-feature threshold rules. Uses only TRAIN measurements and features, or defaults to fixed always-plain/always-guided when benefit is insufficient; never uses family ID as classifier input.
4. **holdout-shard**: 100 test formulas, three repeats each, 4 modes (three frozen controls and the **frozen trained selector**): **1,200 solves**. Includes feature calculation cost in selector time.
5. **holdout-audit**: compare exact frozen model checksums on all runners, check hashes disjoint from training, calculate PAR-2 including timeouts and paired bootstrap intervals resampling formulas, not repeated runs.

**Total: 2,100 solve attempts** under 3-second individual solver time cap. Timeout penalized as PAR-2=6 seconds. All formula seeds/repeat-order seeds/hardware descriptions and raw CSVs are uploaded to artifacts. C++ v7.6/v7.7 frozen source hashes verified. Solver model checks for SAT and logical pigeonhole UNSAT are included; **arbitrary UNSAT proofs are not independently certified**.

## Confirmed historical measurements — not comparable across distinct benchmark sets

V8.8 (30 formulas, run 41226463135): CaDiCaL 58.39163, V7.6 guided 61.80261, V7.6 plain **56.21829**, experimental V8.8 61.95462 seconds of sum of per-formula median PAR-2.

V8.8b (25 formulas, run 41226986357): CaDiCaL 40.04418, V7.6 guided 37.69604, V7.6 plain **36.64113**, experimental delayed V8.8b 36.95592 seconds.

Within each benchmark, the unhinted frozen V7.6 control is the strongest aggregate measured comparator. V8.8b improved versus always-guided V7.6 but was slower than no-hint v7.6. No world record, general structural SAT subclass or asymptotic complexity claim follows.

New V8.9 200-formula experiment values must come from the new GitHub Actions artifact. Do not reuse or interpret preliminary training fit as an independent held-out improvement.
