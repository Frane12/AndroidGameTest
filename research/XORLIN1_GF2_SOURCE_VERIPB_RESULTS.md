# DRNAS XOR-LIN1: source-only Gaussian parity reasoning with standard VeriPB proof

**Experimental branch:** \`experiment/drnas-xorlin1-gf2-source-veripb-20261117\`.  
**Date:** 2026-11-17. No main changes, no APK, no frozen baseline updates.

## Previous exact original benchmark and its scope

The original 10-source SAT competition Tseitin/Urquhart evaluation
[44049316105](https://github.com/Frane12/AndroidGameTest/actions/runs/44049316105)
was selected and source SHA-frozen **before** solver evaluation. Its
unchanged XOR234 emitter independently certified six original
UNSAT sources twice, strict PAR2 131.760913s against CaDiCaL
288.172005s, on 20 paired attempts (8s E2E cap).
IDs 5, 7 and 9 were source-UNSAT via MATH5 but failed the
old XOR234 proof exporter because their source XOR widths were
5/6. ID6 (13,313 vars, 26,968 clauses) timed out and no native
source-supported XOR proof was found under the 8s cap.

**Crucial distinction:** XOR-LIN1 was built *after* examining those
originals. Everything in this work is **retrospective development
evidence**, NOT another unseen/prospective benchmark. No claim of
general SAT algorithm improvement or breakthrough proof-complexity theorem.

## Source-only XOR-LIN1 algorithm

### Step 1 — recognize complete original XOR rows

Parse exact unchanged source DIMACS. A candidate variable support
\`S\` of width 2..6 is an XOR constraint only if the source
contains the **complete** set of \`2^(|S|-1)\` forbidden-value
clauses for one and only one parity. This structural check
needs no original graph naming, labels, native MATH5 certificate,
or SAT/UNSAT oracle. All input clause/variable checks are bounded.

### Step 2 — GF(2) elimination with source-row provenance

For recognized equation \`row_i\` define bitset \`a_i\` and RHS
\`b_i = 1 - forbidden_parity_i\`. Perform Gaussian elimination
over \`GF(2)\` while carrying the bitmask of source equations
used to derive each pivot.

When an incoming equation reduces to \`0=1\`, return its exact
source row subset \`I\` with

\`\`\`
XOR_{i in I} a_i = 0
XOR_{i in I} b_i = 1
\`\`\`

The selected source variables may have **any even multiplicity**,
not just 2; unselected unrelated XOR equations are discarded.
If no contradiction exists, return **UNKNOWN**, never guessed UNSAT.

### Step 3 — independent source and standard proof check

Build a SHA-bound MATH5-compatible JSON certificate containing
only those source XOR equations. The independent existing
\`research/math5/check_math5.py\` checks the source SHA,
every original XOR forbidden-assignment clause and odd parity
with vanishing variable incidence.

The VeriPB exporter \`research/xorlin1/emit_veripb.py\` handles
XOR2..6. For width >= 4, introduce fresh RED variable
\`q=x XOR y\` and derive by source/previous-stage RUP each
new reduced XOR clause. Iterate until all rows are width2/3.
Represent row integer parity using fresh carry bits, RED/RUP,
and cutting-planes inequalities. Sum all selected rows and
divide both bounds by 2; all variable coefficients are even,
but summed RHS is odd, yielding \`0>=1\`.

Only the external **VeriPB 3.0.2** checking the **exact
unchanged original CNF** may label an attempted proof
\`UNSAT_VERIFIED\`.

This is a known polynomial-time GF(2) technique for extracted
XOR systems and a restricted extended cutting-planes proof
compiler; it makes **no** claim that arbitrary CNF SAT is in P.

## Local source and proof results

Originals from the previous source-frozen 10 GBD archive,
not any generated substitute. SHA-256 checked for each original.
A local original-source-only extractor and the new standard proof
compiler produced externally accepted VeriPB 3.0.2 proofs for
all 9 **supported** original CNFs: IDs 0,1,2,3,4,5,7,8,9.
No native MATH5 certificate was used for proof discovery.

For ID6, source-only XOR2..6 recognition found **zero**
complete parity groups, so it correctly returned UNKNOWN.
This is neither SAT nor UNSAT. For the three newly covered
cases, all of their unchanged source CNFs were accepted:

| ID | Source XOR widths | PBP bytes | External proof |
|---:|---|---:|---|
| 5 | 8 XOR3, 24 XOR4, 18 XOR5 | 94,219 | VeriPB ACCEPT |
| 7 | 32 XOR5 | 98,530 | VeriPB ACCEPT |
| 9 | 2 XOR4, 10 XOR5, 8 XOR6 | 80,333 | VeriPB ACCEPT |

The proof producer also generated valid independently verified
results for the six previously supported ID0-4 and ID8
source formulas with no native solver involvement.

### Independent negative controls and generalized incidence

Before submitting the new CI benchmark:
- 24 synthetic source-level contradictory GF2 systems, each
  with two unrelated XOR rows, where the source-only Gaussian
  selector picked only the needed three contradictory rows;
  VeriPB independently accepted **all 24** emitted proofs.
- 24 even-charge known-SAT controls, with checked all-false
  satisfying assignments, all returned UNKNOWN.
- 24 known-SAT controls formed by deleting the required source
  clause, with updated source SHA and checked all-false models,
  all returned UNKNOWN.
- K5 ten-edge XOR system with each original variable appearing
  **four times** (not 2): external VeriPB accepted the
  complete-source certificate, and independently accepted the
  strictly smaller GF2-selected subset.

These safety controls are generated **only to audit soundness**,
not to claim competitive performance on unseen contest formulas.

## GitHub E2E regression benchmark

The dedicated workflow is:
\`.github/workflows/drnas-xorlin1-original10.yml\`.

10 original CNFs × 2 paired repeats × 6 serial arms = **120 trials**
at the same 8s total E2E wall cap with 16s PAR2 penalties.
One logical CPU per solver process, never a parallel solver
portfolio. Source recognition, GF2 extraction, independent source
check, external VeriPB, and all subprocess overhead are included.

Arms:
- XORLIN1_SOURCE_ONLY: new source-only recognition, Gaussian
  contradiction extraction, independent proof production/check.
- XOR234_NATIVE_VERIPB: unchanged old native MATH5+XOR234 exporter.
- X59_MATH5_VERIPB: unchanged MATH5 with restricted EO standard proof.
- Kissat, CaDiCaL, CryptoMiniSat (identical source-frozen reference
  binaries and DRAT/FRAT/model checking).

All original inputs, binaries and checker hashes are restored from
run \`44049316105\`; a complete original input SHA manifest must be
present before any solver test begins. Every accepted SAT model
and UNSAT proof must refer to the exact original. Critical
inconsistencies and missing/duplicate trials fail aggregation.
No main promotion. Source-only accuracy and E2E practicality
are the questions being tested, **not** an independent blind
generalization claim.

### Next prospective test

After certifying this reference and freezing code, choose a
fresh source-only 2023–2026 XOR/CNF sample by metadata; freeze
original source GBD hash/isohashes and literal SHA before any
solver run. Compare the frozen new approach with standard
native solvers at 8s, 30s, 60s caps. Include real SAT controls,
non-XOR CNFs, and different XOR encoding/width distributions.
