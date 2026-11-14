# DELTAX-GUARD MIX1 — mixed formula transfer test

Purpose: check whether an unchanged native DELTAX-GUARD1 proof/clone policy
transfers beyond the earlier HARD28 synthetic benchmark.

## Data

32 CNFs in total:
- **24 fresh SHA-disjoint synthetic sources:** six planted 3SAT; five
  unplanted random 3SAT; four Tseitin XOR parity UNSAT; four PHP
  pigeonhole UNSAT; five graph 3-coloring planted SAT / K4 UNSAT.
  All synthetic cores are connected to two or three guarded equivalence
  motifs, so the nonlinear module has a plausible place to interact with
  CDCL. Many cases remap all variable IDs and shuffle clauses.
- **8 original SAT2024 REAL36 sources**, spread across structural families
  selected by family/byte size, never by solver outcomes: bitvector,
  hardware verification/miter, planning, scheduling, cryptography, etc.
  These originals are *retrospective*: REAL36 was studied before.

The synthetic SHA files are new relative to HARD28; this does NOT make
the mixed benchmark a statistically independent blind holdout, because
the common guarded-equivalence motif and original REAL36 collection are
known from prior work.

## Immutable solver contract

No new solver logic is compiled or trained here. The four arms are modes
of the exact same prior GUARD1 native executable restored from successful
run 43596056826, with SHA-verified drat-trim and historical original CNFs:
JOIN, DELTAX-SHADOW, unrestricted DELTAX, and DELTAX-GUARD1.

Four shards, 5s solve cap, serial one-logical-CPU per solver. Every SAT
model must satisfy its exact original CNF. Every credited UNSAT verdict
requires drat-trim validation on that same CNF; UNKNOWN is unverified.
All emitted guarded clauses have independently verified original parent
resolution, and duplicate/original SHA mismatches stop the workflow.

## What to interpret

- Compare whether GUARD1 accepts proof-safe clauses on distinct families.
- Count native CDCL decisions/conflicts ONLY on cases both arms have
  independently verified to a compatible status. Do not compare a
  timed-out run's partial counters with a completed solve as evidence of
  better search.
- Explicitly report false rejections of useful clauses and failure to
  prevent regressions; a clone risk estimate is NOT an infallible oracle.
- Record how often each arm solves and report certified-only PAR2, but
  do not claim speed improvements from one attempt per source.
- No main promotion, new champions, new mathematics theorem or accuracy
  guarantee; this is an exploratory mixed transfer benchmark.
