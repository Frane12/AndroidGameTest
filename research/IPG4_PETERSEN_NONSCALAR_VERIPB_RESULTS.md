# DRNAS IPG4 — genuinely non-scalar PCMAX UNSAT, two VeriPB 3.0.2 certificates

**Experimental branch, 2026-11-16.**

## What is proved

We use a 15-job, 3-identical-machine PCMAX instance reconstructed
from the Petersen graph. Every job corresponds to an edge e=(u,v)
on ten vertices, with integer processing time

  p_e = 3^u + 3^v,       T = sum_(v=0..9) 3^v = 29524.

Total job processing time is exactly 3T = 88572, so any feasible
3-machine schedule must fill each machine to EXACTLY T.
Each vertex has degree 3, hence the ternary digits of a machine's
load T force exactly one incident graph edge to be assigned to
that machine at every vertex. Thus each machine's jobs would
form a perfect matching and the three machines would form a
3-edge-coloring of the Petersen graph. But Petersen is not
3-edge-colorable: no three pairwise disjoint perfect matchings exist.

The original DIMACS source is pinned to SHA256:

  c2fefeffc1f9644ffd6f85728106a21c82dfc01d0d021f32d4d73569cc2bfb70

It has 45 Boolean assignment variables and 300 original clauses.
The source is independently reconstructed from ALL inclusion-minimal
capacity-violating job subsets, plus one-hot assignment clauses.

## Stronger claim: NO nonnegative scalar capacity cut exists

The Petersen graph has six perfect matchings M_1,...,M_6.
Every M_i has exactly five jobs and total processing time T,
so all six are allowed single-machine bin configurations.
Each edge/job occurs in exactly two of these six matchings.

For ANY vector of nonnegative weights w_e, set

  K(w) = max_{S feasible in one machine} sum_(e in S) w_e.

Since every M_i is feasible,

  6 K(w) >= sum_(i=1..6) sum_(e in M_i) w_e
         = 2 sum_e w_e.

Therefore 3 K(w) >= sum_e w_e for ALL w>=0.
The familiar strict weighted demand > 3 * capacity criterion
cannot certify this UNSAT, even with optimally selected weights.
This is a constructive fractional packing: choose coefficient
1/2 for each of the six matchings, covering each job once
with total fractional bin mass 3. No floating-point LP result
is used to justify the universal scalar inequality.

## Two certified but DIFFERENT proof routes

**A. Direct mathematical parity/case-split proof, graph CNF**

An independently reconstructed 45v/150c direct Petersen
three-edge-coloring CNF uses the SAME edge/job indexing.
An original-source checker verifies both CNF encodings
against the exact same graph and weighted scheduling instance.

Without using CDCL, `research/ipg4_petersen_parity_proof.py`:

- Lists six perfect matchings for color/machine 1.
- For each matching finds an odd cycle in its complement.
- Uses the odd cycle to construct two guarded source-RUP lemmas
  and resolve a matching no-good (18 RUP steps).
- At each cubic vertex derives the first-color at-least-one
  clause using the 3 incident edges / 2 remaining colors
  pigeonhole (30 RUP steps).
- Uses 6 conflict leaves + 5 internal proof-tree resolution
  steps to derive the final empty clause (11 RUP steps).

TOTAL: 59 independently UP-replayed RUP lemmas,
2,201-byte standard VeriPB 3.0 proof.
External VeriPB 3.0.2 accepted the exact graph CNF and proof.
Original graph source SHA-256 is bound into the gap certificate.

**B. Original weighted 45v/300c source, native CDCL RUP**

Run the existing (frozen) native `drnas-mg7-scc` C++ solver
on the ORIGINAL weighted source with DRAT enabled.
Native output: 1,605-byte DRAT trace; independent drat-trim accepted.

`research/ipg4_rup_drat_to_veripb.py` independently replays every
one of the 92 DRAT additions using unit propagation on the
unchanged original input plus earlier learned RUP clauses.
It rejects non-RUP/RAT-only steps and incorrect source hashes.
Then it emits a 3,746-byte VeriPB 3.0 RUP proof.
External VeriPB 3.0.2 independently accepted the proof
against the ORIGINAL 45v/300c source.

***Scientific distinction:*** The original 300-clause proof's
derivation uses CDCL search. It does NOT establish that the
new parity/cutting-plane module can directly compile an arbitrary
IPG-BDD3 JSON proof to VeriPB, or that it solves general PCMAX
in polynomial time. Only the separately generated graph-coloring
source proof is explicitly combinatorial/parity-guided.
The mathematical equivalence between graph coloring and weighted
packing is independently verified, but does not itself turn the
graph proof into a VeriPB trace on the weighted source.

## Verifier-gated evidence

Completed successful GitHub Actions run:
https://github.com/Frane12/AndroidGameTest/actions/runs/43846527861

| Check | Result |
|---|---|
| Original weighted source SHA verified | PASS |
| Original 300-clause encoding reconstructed independently | PASS |
| Six fractional configurations, each job twice | PASS |
| Nonnegative scalar capacity separation impossible | PROVEN |
| 150-clause parity-guided VeriPB proof | ACCEPTED, 59 RUP |
| Original 300-clause native DRAT | ACCEPTED, 92 RUP |
| Original 300-clause converted VeriPB proof | ACCEPTED, 92 RUP |
| Tampered original CNF bytes | REJECTED |
| Tampered fractional configuration certificate | REJECTED |

All source and checker paths are pinned in the `results/ipg4_nonscalar_petersen`
GitHub Actions artifact. These were known retrospective constructions,
not a blind competition benchmark; no performance PAR2 claim is made.

## Reproduce

  cargo install veripb --version 3.0.2 --locked --root veripb-tool
  make -C drat-trim drat-trim
  cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
  cmake --build build --target drnas-mg7-scc -j2
  python3 -u research/ipg4_nonscalar_veripb_benchmark.py

Every reported proof is accepted only after external VeriPB:

  veripb-tool/bin/veripb --cnf SOURCE.cnf proof.pbp

on the exact unmodified source bytes. Status on unsupported
instances must be UNKNOWN; never replace proof verification
with a filename, known target label, or model-generated claim.

## Next real research opportunity

Generate source-bound PB cutting planes / case splits directly
from the IPG-BDD3 integer-count DP and derive a NON-SCALAR
VeriPB proof for the original weighted source WITHOUT first
running CDCL. This would generalize the compact mathematical
parity approach to richer BDD PCMAX structures. It remains
unimplemented; no such claim follows from this experiment.

Do not merge experimental changes to main without prospective
holdout verification and verification-inclusive PAR2 regression tests.
