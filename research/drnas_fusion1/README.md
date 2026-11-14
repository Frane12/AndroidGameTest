# DRNAS FUSION-GUARD1b — native CDCL primary, proof modules conditional

Experimental branch experiment/drnas-fusion-guard1b-20261114. Main untouched.

## Core contract

The native CDCL engine is always the sole search, decision, BCP, reason,
learning and SAT/UNSAT authority. In the explicit FUSION CORE mode all
math modules are OFF. It must reproduce exact native decision/conflict
counts on source-matched verified cases versus the reference
drnas-deltax-signal SHA256
46252501f59b279165cfcb55b000cb357d5217fde32a94ee693ae47e3bb495e0.
The repository default main branch is a research index, not the current C++
native CDCL source; therefore the exact pinned native solver fork is used.

## Modes and conditional math

FUSION CORE: no math, no cold-source copy, baseline branching unchanged.
FUSION SHADOW: only cheap gate observes; math remains OFF and no CNF copied.
FUSION GUARDED: modules see original clauses ONLY after O(1) guard
authorization and a short, state-derived analysis window.

Proof-compatible mathematical modules already integrated on the native
solver source lineage:

- COOP4 GF(2) / Walsh-based exact local parity consequences, in own
  source-proof gate (only currently asserting useful clauses).
- DELTAX proof-carrying conditional Boolean equality, with original-
  source resolution, SIGNAL8 reach prefilter, and bounded serialized
  same-state cloned CDCL risk guard before any real clause insertion.

MATH-GUARD3, COOP55 and R153/160 are different native forks or routes and
are NOT silently mixed without explicit compatible proof and state-lifetime
integration. No secondary parallel solver, no generic portfolio switch,
no external backend presented as native CDCL.

## Pre-gate

A bounded original-CNF parser-time observation detects:
- short binary-rich graph-like source structure, without graph labels;
- exact four-clause three-variable XOR parity signatures, 0x69 / 0x96,
  with at most 1024 tracked triples;
- standard CDCL conflict/decision pressure and existing binary edges.

Source names, status labels and benchmark classes never enter the gate.
No mathematical tables, clone solver allocations, global learning or
nonlinear discovery are run on a vetoed window.

This is a cheap source-blind heuristic utility/risk estimate; it does NOT
guarantee that an activated module makes the solver faster.

An authorized analysis window has mandatory source proof checks, limited
time/candidate budgets, a max of six activations and a cooldown after
unproductive results. No post-commit global rollback is claimed.

## Reproducible evaluation

Five modes on the same source files: frozen core, fused core, fused shadow,
fused guard, frozen full SIGNAL8/GUARD1. Retrospective collection: 8 graphs,
12 mixed SAT/UNSAT synthetic and 4 original SAT2024 CNFs. Five serial
single-logical-CPU arms, proof-verified SAT models and independent UNSAT DRAT.

The first FUSION1 implementation achieved 120 complete attempts, 21/24
certified solved in each arm, 42 core OFF equivalence pairs and only two
verified search improvements with no solved-case regressions. It also
restarted math analyses unnecessarily on some PHP / XOR/3SAT cases.
FUSION1b tests whether a stricter cheap gate reduces those overheads.

This is NOT a blind holdout, mathematical novelty proof, general
runtime improvement or promotion into main.
