# DRNAS GF-CDCL NOVEL1 — preregistered experiment (2026-11-10)

## Objective
Test whether a native, proof-checked GF(2) propagator integrated with a real CDCL trail reduces end-to-end CPU time on original CNF instances, beyond a cost-matched placebo. This document is a protocol, not a claim of implementation or benchmark success.

## Prior runs to audit
XORABC2 / XORABC3, GF-GATE1, COMBO6, AB4, MRE6f (reference). Collect per-shard run IDs, job conclusions, original SHA256, arm, repetition, CPU time, E2E wall time, solved status, SAT witness verification, UNSAT proof verification, GF2 proposals, completed reasons, unique implications, duplicate implications, conflicts, emitted clauses and time spent in GF2. Missing or failed runs remain explicitly missing; do not silently drop them.

## Mechanism
1. Extract only sound XOR constraints from original CNF. Preserve an independent derivation/proof for each XOR row; no heuristic XOR row may become an active constraint.
2. Maintain incremental row state under CDCL trail assignments, with decision-level undo. Track row parity and unassigned-variable count.
3. On a row with exactly one unassigned variable, derive its forced literal. On zero unassigned variables and wrong parity, derive conflict.
4. Construct the CNF reason clause from the *actual assigned antecedents* and the implied literal, or a conflict clause from all row assignments. Independently verify that the original CNF entails the reason before delivery (via a sound proof chain or checker). Do not equate row-local validity with original-CNF entailment.
5. Deduplicate against existing CNF assignments/implications; count genuinely novel propagations. Deliver reasons to the native CDCL interface; no out-of-process restart as a proxy for integration.
6. Budget gate: track CPU time spent in GF2; disable active work if budget exceeded. Shadow-only arm performs the same monitoring without modifying the trail.

## Experimental arms
- clean CDCL baseline
- shadow GF2 (read-only)
- active GF2 (proof checked)
- cost-matched placebo (same accounting and gate, no GF2 conclusions)
- MRE6f reference when reproducible
- CryptoMiniSat native XOR reference

## Test protocol
- First: compile + unit tests for parity, trail backtrack, reason soundness, duplicate suppression and disabled gate.
- Then: 4 known frozen SHA smoke, one logical CPU, original CNF, cap 8s, 2 repetitions.
- Then: 24–30 source-frozen previously unseen original SHA, 3 repetitions, one logical CPU, cap 15s. Holdout source and exclusion registry must be recorded *before* measuring candidate.
- Same environment and pinned solver binaries for all arms; paired order randomization.
- SAT must have original-CNF model verification. UNSAT must have independently checked original-CNF proof (LRAT or explicitly verified GF2 certificate). UNKNOWN and TIMEOUT are unsolved.
- Report solved SAT/UNSAT, PAR2=sum(actual seconds for solved, 2*cap for unsolved), E2E CPU and wall time, paired speedup, regressions, GF2 unique implications/conflicts, proof failures and overhead.
- No claims of generic speedup from bounded CDCL diagnostics or special XOR instances.

## Decision gates
Advance to NOVEL2 only if: all correctness checks pass; at least one original CNF has a genuinely novel delivered implication/conflict; and no material unexplained regressions. Advance to NOVEL3 only after a preregistered holdout shows net benefit against clean CDCL and placebo. Otherwise inspect XOR extraction, CDCL scheduling and propagation order, rather than launching another broad variant.

## Current status
Protocol created. Existing workflow completion and artifact audit pending. No native engine change or benchmark is claimed by this file.
