# DRNAS MRE6g — signed implication-SCC + GF(2) certified equality

Date: 2026-11-08
Branch: experiment/drnas-mre6g-implication-scc-gf2-20261108
Active Actions: https://github.com/Frane12/AndroidGameTest/actions/runs/42505129743
Frozen six-source input: exactly the SHA-locked MRE7/MRE6f originals
from completed MRE6f run 42503866092. These are DEVELOPMENT controls,
not new blind sources. No sources were added or filtered by MRE6g outcome.

## Problem addressed

MRE6f completed 48/48 source-paired 35s real solves, 40/48 solved,
but discovered ZERO applicable original-CNF direct positive equality
classes across six tested formulas. It therefore measured fallback and
preprocessing overhead rather than an active mathematical reduction.

MRE6g tests two strictly wider, independently provable relation sources:

1. SCC of signed Boolean binary implication graph: CNF (a OR b) entails
   (not a -> b) and (not b -> a), so SCC literal paths prove equivalence
   even when no direct two-clause pair exists. Certified negative
   equivalences x_i == NOT x_j are allowed, not just x_i == x_j.
2. Certified GF(2) and resolution lemma records may extend the graph
   ONLY following full independent MRE1 source-CNF proof replay. GF(2)
   derivation runs in a killable child process, with HARD wall cap 1.45s.
   The graph SCC itself has a separate 0.42s budget and path replay,
   capped at 64 substitutions per formula.

Each selected variable equivalence has two explicit implication paths
within a source-proved binary graph, independently replaying every
edge as an original or MRE1-certifiable clause. A representative can be
positive or negative. On quotient all original CNF clauses and
certified imported GF(2) rows are correctly transformed; for negative
substitution the parity RHS flips, repeated variables cancel. SAT
witness reconstruction assigns eliminated variables using the signed
representative and checks the exact original SHA-locked SAT2026 source.

## Five matched modes (60 total full actual solve trials)

Each source has 2 fixed native seeds; 6 original sources, 3 SAT/3 UNSAT,
35 seconds FULL end-to-end wall per attempt, exactly the same pinned
instrumented CryptoMiniSat 5.11.15 backend and OTF Gauss OFF:

- native_no_xor: original CMS, no optional GF(2) import
- source_xor: original CMS plus proof-verified source XOR rows
- direct_all_eq: unchanged original-CNF direct positive EQ MRE6f approach
- graph_scc: ORIGINAL binary implication-SCC + signed quotient
- graph_scc_gf2: original-SCC + optional proven MRE1 GF(2) derived
  binary clauses if >=2 certified source XOR rows and original CNF
  size 2400–35000; before any use, all source and derived lemma
  certificates are independently replayed against the ORIGINAL CNF.

Instrument logs report: active/abstained gate, 0.42s SCC budget,
1.45s capped GF(2) subprocess status, discovered original/derived
binary clause counts, SCC count, proof path lengths, number of
eliminated variables, signed complements, resulting CNF/XOR counts,
actual completed CDCL propagations/conflicts/decisions, native CPU
for completed solves, all preprocessing wall/CPU, full wall and PAR2.
A timeout costs exactly 70 PAR2 seconds.

## Required correctness and scientific boundaries

- Same original SHA/seed across all five arms.
- No post-hoc source or failed timeout exclusion.
- Original SAT witness independently validated.
- Published official UNSAT status crosschecked, but no independent
  LRAT proof; never claim an UNSAT certificate that was not produced.
- Unverified GF(2) proof, budget exceed, source-size guard or absent
  SCC equivalence -> safe original-CNF fallback; still charge overhead.
- One reused development cohort cannot establish fresh blind speedup.
- No online CPU-aware selector is promoted from these results. Follow
  with source-disjoint blinded formulas only after positive evidence.

## What success would mean

First, demonstrate actual certified relations NOT detected by MRE6f on
one or more formulas. Second, obtain a solved-versus-solved reduction
in full wall time and native CPU on multiple paired seeds AFTER
subtraction of derivation and reconstruction costs. Otherwise preserve
negative results and prioritize cheaper detection/abstention.
