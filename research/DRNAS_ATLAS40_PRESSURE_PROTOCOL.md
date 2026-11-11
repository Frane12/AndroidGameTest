# DRNAS ATLAS40 PRESSURE — preregistered decision-tree experiment

Date: 2026-11-11. Experimental branch isolated from stable main.

## Purpose
Test whether the *identity* of deleted clauses can be improved using a
decision tree combining recent conflict-minimization reason use, clause
LBD, age, and (in the pressure arm) cumulative BCP cost.

## Frozen controls
- A36_75 (fixed deletion quota 75%).
- A39_PROTECT (original ATLAS39 protection score of 500).
- Pinned Kissat (independent reference).
- A40_TREE uses a **distinct native mode=3** and the C7 fixed 75% quota.
- No change to solving logic, conflict learning correctness, original
  candidate eligibility, learned-clause LBD guards, or clause-slot
  compaction behavior.
- Instrument actual chosen deletion candidate differences via
  atlas39_changed_rank; count reason-use and metadata overhead.
- SHA-locked SATLIB: regression indices 0/1, extension 10/11, hard
  12/13, with the same family groups as ATLAS39. These are *not
  globally blind*, and were partly inspected during development.
- 26 SHA, two seeds, four arms, 208 trials on one logical CPU each;
  timeout cap 10s regression, 12s extension/hard.
- Report total and cohort PAR2 (reported vs certified), E2E,
  SAT witness verified, UNKNOWN and non-LRAT UNSAT separately.
- Do not promote any tree because of one spectacular single-case win.

## Tree under test
When cumulative watch-visits/propagation > 20, protect reason-reused clauses with LBD <= 15 and reuse count >= 3 using score discount 650; otherwise protect LBD <= 9 and age <= 4500 with discount 250.

## Interpretation and future selection
This is a three-arm exploratory selection, not a confirmatory general
winner. After any provisional selection, lock the policy and test on a
new SHA-disjoint holdout with one CPU and independently checked SAT
witnesses (and independent LRAT for UNSAT when possible). Compare against
A36_75, A39_PROTECT, Kissat and the two alternate A40 trees. If none
beats A36_75 robustly, retain A36_75 as reference.
