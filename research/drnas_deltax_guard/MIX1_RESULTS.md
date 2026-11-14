# DELTAX-GUARD MIX1 — source-paired mixed transfer findings

**Run:** https://github.com/Frane12/AndroidGameTest/actions/runs/43597372358  
**Branch:** experiment/drnas-deltax-guard-mix1-20261114  
**Date:** 2026-11-14

## Frozen protocol

The **unchanged** GUARD1 executable from run 43596056826 was used in
four serial modes (JOIN, DELTAX-SHADOW, DELTAX, DELTAX-GUARD) on one logical
CPU. 32 sources x four arms = 128 trials, cap five seconds each.

The source mix comprised 24 freshly seeded SHA-disjoint synthetic CNFs from
five families (6 planted3, 5 random3, 4 XOR/Tseitin, 4 pigeonhole UNSAT,
5 graph 3-coloring SAT/UNSAT), plus eight original 2024 SAT competition
instances. All original SAT2024 instances are **retrospective**, not unseen
blind holdout; all generated sources use previously investigated conditional
equivalence motifs, though their source hashes and hard cores are new.

Every credited SAT model was independently checked on its ORIGINAL CNF.
Every credited UNSAT verdict was independently checked by drat-trim on
the ORIGINAL CNF. All four modes verified 27 of 32 sources:
12 SAT and 15 UNSAT, with five UNKNOWN original SAT2024 instances.
Every synthetic source was solved and verified: 24/24.
Three retrospective originals were solved; five remained UNKNOWN.

## GUARD outcomes

- 32 bounded same-state guard candidate checks: **six accepted and 26 vetoed**.
- Six certified RUP clauses injected by GUARD; ten genuine CDCL reason
  enqueues attributed to those clauses. Zero invalid source steps and
  zero contradictory completed clone results.
- All six accepted clauses came from three NEW graph-coloring sources;
  no guard candidate was accepted in planted/random3, PHP, XOR or
  original SAT2024 categories. Four additional graph candidates were vetoed.
- In the 27 both-solved pairs, GUARD reduced decisions *and* conflicts
  versus JOIN in three cases and increased neither in any pair:
    - mix_graph3_v23_planted: decisions 29 -> 28; conflicts 2 -> 1.
    - mix_graph3_v27_unsat: decisions 21 -> 19; conflicts 17 -> 16.
    - mix_graph3_v31_planted: decisions 11 -> 10; conflicts 1 -> 0.
- There are no matched, verified decision/conflict gains in the other
  mixed source families on this single-seed dataset.
- Pure unguarded DELTAX sometimes had fewer conflicts than GUARD,
  including on two PHP cases. The conservative guard therefore can
  reject helpful clauses. On the larger PHP 9/8 case, however, GUARD
  also avoided the substantially worse unrestricted DELTAX trajectory.
- Five original SAT2024 instances were UNKNOWN in all four arms. Partial
  conflict or decision counts for those cases are *not* evidence of
  winning, losing, or a proven safe fallback.

## Aggregate evidence, with caution

| Arm | Original verified / 32 | Synthetic verified / 24 | Injected clauses | Genuine reason enqueues |
|---|---:|---:|---:|---:|
| JOIN | 3/8 | 24/24 | 0 | 0 |
| SHADOW | 3/8 | 24/24 | 0 | 0 |
| DELTAX | 3/8 | 24/24 | 34 | 4,299 |
| DELTAX-GUARD1 | 3/8 | 24/24 | 6 | 10 |

Decisions and conflicts summed across runs that ended UNKNOWN are NOT
comparable with completed solve counters. The per-source, verified-only
comparisons above are the relevant measure of progress.

## Scientific interpretation

This mixed test supports a **limited transfer** of GUARD's cautious
decision policy to three new graph-coloring formulas. It does not
establish improvement in the real competition sample or independent
3-SAT/XOR/PHP categories. Most of the benefit is restricted to one
synthetic family and has only one repetition per source, so no statistical
confidence or general speed claim is warranted.

Next: construct novel cross-family interaction cases, including those
where a selected guarded equality changes the CDCL conflict graph; use
fresh holdout seeds and independently validated wrong-clause fault
injection. No main promotion.
