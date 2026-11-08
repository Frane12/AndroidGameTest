# DRNAS MRE6 — certified CPU-feedback and equivalence-quotient exploratory results

**Date:** 2026-11-08
**Experiment branch:** experiment/drnas-mre6-cpu-feedback-principles-20261108
**Successful 84-trial GitHub run:** https://github.com/Frane12/AndroidGameTest/actions/runs/42491590558

## What was implemented

1. research/mre6_cpu_feedback.py — CPU-labelled mathematical principle
   learning and conservative frozen dispatch rule, with normalized
   experiment evidence in SQLite (principles and actual native CPU,
   decisions, conflicts, propagations and watched-event scans).
2. research/mre6_principles.py — proof-replayed positive equivalence
   quotient: substitute x224:=x12 in CNF and source GF(2) rows, rebuild
   original SAT witnesses using x224=x12 and validate every ORIGINAL clause.
3. research/mre6_pilot.py — four fresh native CMS seeds, two independent
   timing repeats, seven arms and trace OFF plus trace ON on repeat zero.
   All inputs, library, original SHA and seed choices are pinned.
4. A calibration checkpoint is frozen using *older* MRE5 results before
   opening new seed results. It automatically ABSTAINS from deploying an
   unproven strategy on real new formulas.

## Formula and limitations

One previously researched official SAT2026 formula:
official-28dcc4119e1bbb5fbd3fdd8f4140f28d.cnf
SHA256 b2c2008e5d24a7aa82499d1486af2550a53a7167e46836c4b9977846204ad483.

8,933 original clauses, 2,702 declared variables and 150 certified source
XOR rows. Two replay-certified binary clauses:
A=(-12,224), B=(12,-224), which together prove x12=x224.

The quotient replaced eight literal occurrences but **did not reduce**
the CNF clause count (still 8,933) nor XOR row count (still 150).
This is an exact representation change but not a guaranteed cheaper
form for CMS.

This is an UNSEEN-SEED study on a REUSED formula, **not blind source
holdout**. All 84 runs completed, all SAT models were checked against
the original SHA-locked formula. No UNSAT LRAT claim is made.

## Actual native CPU around cms.solve(), trace OFF

Four new native seed values x 2 independent wall-clock repeats per arm;
8 paired measurements per arm. MRE1 mathematical proofs and
CNF rewriting were precomputed ONCE per shard outside these solve
CPU measurements; practical deployment must also account for them.

| Certified representation | CPU sum (8 trials) | Difference vs XOR-only | Seeds where CPU wins |
|---|---:|---:|---:|
| CMS + source XOR baseline | 62.824623 s | reference | — |
| Only certified clause A | 67.896208 s | +8.07% (worse) | 1/4 |
| Only certified clause B | 63.593350 s | +1.22% (worse) | 1/4 |
| A and B as two watched binary clauses | **56.074929 s** | **-10.74% (better)** | **4/4** |
| Canonical-only no-quota (same semantics, no CNF clauses removed) | 63.148417 s | +0.52% | 3/4 |
| Proof-certified x224:=x12 quotient, source XOR retained/transformed | 66.626705 s | +6.05% (worse) | 0/4 |
| Same quotient, source XOR import omitted | 56.824762 s | -9.55% (better) | 4/4 |

**Do not confuse quotient-no-XOR success with a proven gain from quotient.**
Removing source-XOR import itself can change runtime. The MRE6b 2×2
factorial introduces original-CNF-without-XOR as a missing causal control.

## New mathematical principle-design inference

The two individually expensive binary implication clauses become beneficial
when combined: this is a NONADDITIVE interaction.
A useful principle generator should learn equivalence motifs and bundles,
not merely independently score individual redundant lemmas by unit count.

The quotient form carrying the exact same proven equality is slower with
source XOR import, suggesting that the representation interacts strongly
with the native CMS XOR-handling and search heuristics. Equivalence does not
guarantee equal or faster propagation topology.

The calibration model trained on only one source and two native seeds
appropriately abstained from enabling any CPU-based automatic selector:
policy remains 'xor' until multiple source-disjoint training CNFs and
a separate truly unused formula holdout validate stable savings.

## Next exact causal question (MRE6b)

Measure 2×2:
- Original CNF without XOR import
- Original CNF with source XOR
- Certified quotient CNF without XOR import
- Certified quotient CNF with transformed XOR import

Same four seeds and same patched CMS. CPU interaction =
[CPU(quota+XOR)-CPU(original+XOR)] -
[CPU(quota-XOR)-CPU(original-XOR)].
This isolates whether the quotient itself or its interaction with CMS
source XOR is the driver. Extra ablation measurements also append
an interaction table to the same SQLite feedback store.

**No broad SAT solver acceleration claim** is supported by a single
reused problem even when all 4 new seeds agree.
