# DRNAS MATH5 XOR3-carry → independently accepted standard VeriPB 3.0

Research date: 2026-11-17.

**No main change.** Experimental branch:
\`experiment/drnas-xor3carry-veripb-tseitin-20261117\`.

## Frozen original source, prior results and scope

The original SAT Competition 2025 Main Tseitin CNF ID6 of the
\`DRNAS GRAPH seven-family size-eligible\` run is:
\`tseitin_n188_d3.cnf.xz\`;
exact source GBD hash \`42f1311ce504db8cc0cb590a568da20a\`;
uncompressed source SHA-256
\`9e4c57b9739f39a924d03267f05542831dc87fec9e9e2238f5e4ba11886378f4\`.

**Original DIMACS:** 282 variables, 752 clauses. From run
[43913499707](https://github.com/Frane12/AndroidGameTest/actions/runs/43913499707),
the previously frozen X59+MATH5 native solver found an independently
SOURCE-VERIFIED XOR contradiction in ~0.07s on each of two trials,
while Kissat and CryptoMiniSat TIMEOUT, and CaDiCaL reached a resource
limit under the 8s cap. The original source-supported MATH5 JSON
proof had 8,230 bytes, but the existing restricted exact-one
VeriPB exporter did not support XOR-only certificates: all prior
arms received strict PAR2 320s over ten source instances.

The current method was developed after viewing ID6's original
CNF and MATH5 certificate. **Retrospective development result**,
not independent blind validation. No world-ranking claim.

## Source-backed mathematical proof

The MATH5 source checker verifies each selected XOR row's four
original forbidden-assignment clauses, the source SHA, the row's
variables and parity, and the global contradictory parity.

For the selected 188 rows, each is three-variable XOR:
\`x_i + y_i + z_i ≡ b_i (mod 2)\`. Every selected original
variable occurs in exactly two rows, and the sum of all row
right-hand sides \`B = Σ b_i\` is odd.

Introduce a fresh carry Boolean \`t_i\` per row such that
\`x_i+y_i+z_i - 2 t_i = b_i\`.
For \`b_i=1\`, the extension is \`t_i=x_i AND y_i AND z_i\`.
For \`b_i=0\`, it is \`t_i=MAJ(x_i,y_i,z_i)\`.
The emitter introduces their Boolean definitions using **VeriPB RED
with explicit witnesses**.

From original XOR clauses and these extensions, construct
source-grounded reverse unit propagation and cutting-planes
derivations of both pseudo-Boolean inequalities:

\`\`\`
x_i + y_i + z_i + 2(1-t_i) >= b_i + 2
(1-x_i)+(1-y_i)+(1-z_i)+2t_i >= 3-b_i
\`\`\`

The source-supported RUP steps are:
- \`b=1\`: \`(~x OR ~y OR t)\` for the 3 literal pairs,
  derived from forbidden parity clauses and \`t=xyz\`.
- \`b=0\`: \`(~x OR t)\`, \`(~y OR t)\`, \`(~z OR t)\`,
  derived from forbidden parity clauses and \`t=majority\`.

Taking CP combinations and dividing by 2 or 3 gives the
integer inequalities exactly. Summing over every original row:
every original x occurs **twice**, so both aggregated inequalities
have even coefficients. Since \`B\` is odd, division by 2 with
rounding and final addition derives the contradiction \`0 >= 1\`.

No CDCL search is required to derive this proof. This is a
restricted, known extended cutting-planes method. It makes NO
claim that ordinary cutting planes or arbitrary SAT have
polynomial proofs.

## First independent local result

Original unchanged CNF, native frozen DRNAS MATH5 JSON,
new generic source-bound exporter, external
**VeriPB 3.0.2**:
\`s VERIFIED UNSATISFIABLE\`.

- Source SHA: \`9e4c57b9...6378f4\`
- 188 selected XOR rows; 188 fresh carry variables.
- Proof: **76,967 bytes**, SHA-256
  \`70b7f97138400c4ab8167822f85ce4f00b9bb9fda616440911e0b72ed7b5a48a\`.
- Formula: 282 variables, 752 clauses.
- 942 RED, 564 RUP and 757 CP steps.
- Two local repetitions (native source-cert generation, proof emission,
  external VeriPB verification) both passed under 8 seconds.
  Local setup was not the exact CI E2E full pipeline; use CI below
  for strictly standardized comparisons.

## Controls

Using 3-regular ring/matching Tseitin graph sources, a local
adversarial pilot produced:
- **24/24** independent external VeriPB-accepted synthetic
  odd-charge UNSAT proofs;
- **24/24** explicitly SAT even-charge controls rejected;
- **24/24** explicitly SAT missing-one-clause controls rejected.

Both SAT control types carry an independently checked all-false
assignment, and the single-clause-removed control cert's SHA was
updated to the changed CNF to prevent trivial SHA-only rejection.

The GitHub selftest adds 24 forged source-SHA controls, for
96 total safety checks (24 external UNSAT passes + 72 rejections).

## Reproduction and 8s E2E

New source-bound emitter:
\`research/math5/emit_veripb_xor3_carry.py\`

Safety tests:
\`research/math5/xor3_carry_selftest.py\`

Source-frozen 5-arm (new standard MATH5, old MATH5,
Kissat/CaDiCaL/CryptoMiniSat), 2-repeat benchmark:
\`research/math5/xor3_tseitin_id6.py\`.

GitHub workflow:
\`.github/workflows/drnas-math5-xor3carry-tseitin.yml\`

The CI restores the frozen original archive and all original
reference binaries and proof checkers from *completed original
run* \`43913499707\`. It verifies original source SHA, pinned
binary SHA, and 24+72 control outcomes; all solver arms run
serially, with one logical CPU and an inclusive 8s E2E
budget counting native solver + independent MATH5 source check +
new proof emission + external VeriPB.

Strict PAR2 for an unverified or timed-out trial is 16s.
Any contradictory SAT/UNSAT external checker outcome is fatal.
No automatic main promotion.

**Do not quote provisional CI comparison statistics before
the workflow finishes.** New algorithm must also be tested
on independently selected prospective unseen XOR graph formulas
to support a genuine generalization claim.
