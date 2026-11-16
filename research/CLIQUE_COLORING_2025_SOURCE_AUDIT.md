# DRNAS — original SAT2025 clique-vs-coloring source analysis (2026-11-16)

**Status:** Complete original-source structural diagnosis; NO new benchmark and NO
standard proof export for these 10 sources yet. Do not alter strict PAR2.

## Benchmark result BEFORE analysis

The completed source-frozen run
[43891106380](https://github.com/Frane12/AndroidGameTest/actions/runs/43891106380)
evaluated 10 previously untested-by-this-study original SAT2025 graph CNFs,
2 repeats, 6 serial arms, 120 trials. All jobs PASS, 0 critical errors.
All six arms scored strict PAR2 **320.0 seconds** (0/20 independently
verified SAT/UNSAT results per arm) at cap 8s and timeout penalty 16s.

The frozen source archive is
`graph-unseen25-all-sources-and-frozen-binaries`, artifact id `14236907251`.
No overlap with the old 67 frozen original source GBD ids or GBD isohashes.

## Important: these are NOT fixed-graph k-coloring instances

All ten original SAT2025 CNF byte streams were inspected directly.
They are source encodings of the classical **clique-versus-coloring principle**:
a graph on n vertices is asserted both to contain a clique of size k,
and to admit c=k-1 colors. The graph itself is encoded by edge *variables*,
so the previously successful GRAPH-CLIQUE recognizer (fixed graph and
direct negative source binary clauses for its k+1-clique) is the wrong
structural extractor for this family.

The source decomposes into the three variable classes:
- `E_uv` for each graph edge, n(n-1)/2 booleans;
- `P_i,u` for clique position i in 0..k-1 and vertex u in 0..n-1: k*n;
- `C_u,t` for vertex u and color t in 0..c-1: n*c.

The exact source variable count is therefore `n(n-1)/2 + n(k+c)`.
Two different widths of positive source clauses are ALWAYS present:
k position clauses of width n, and n vertex-color clauses of width c.
That heterogeneity alone defeats the old graph recognizer, and graph
color conflicts require ternary clauses with edge variables rather than
source negative binary graph clauses.

| ID | n | k | c | Variables | Source clauses | P->edge source triples checked |
|---:|---:|---:|---:|---:|---:|---:|
| 0 | 100 | 6 | 5 | 6050 | 205556 | 148500 |
| 1 | 30 | 7 | 6 | 825 | 25042 | 18270 |
| 2 | 50 | 6 | 5 | 1775 | 51531 | 36750 |
| 3 | 30 | 11 | 10 | 1065 | 60026 | 47850 |
| 4 | 40 | 6 | 5 | 1220 | 33026 | 23400 |
| 5 | 30 | 9 | 8 | 945 | 40674 | 31320 |
| 6 | 26 | 7 | 6 | 663 | 18844 | 13650 |
| 7 | 15 | 7 | 6 | 300 | 6337 | 4410 |
| 8 | 14 | 7 | 6 | 273 | 5530 | 3822 |
| 9 | 32 | 5 | 4 | 784 | 14933 | 9920 |

**9/10** contain the full canonical clause grammar. **ID8** includes one
negative source unit `-92` in place of one binary P-AMO clause. This
does NOT invalidate the k>c argument; P-AMO is not needed for the
subset-proof.

## Original clauses that suffice for UNSAT

1. `OR_u P_i,u` for every clique position i.
2. `~P_i,u OR ~P_j,u` for every i<j and vertex u (distinct positions).
3. `~P_i,u OR ~P_j,v OR E_uv` for i<j, u!=v (selected clique edges).
4. `OR_t C_u,t` for every vertex u (some color).
5. `~E_uv OR ~C_u,t OR ~C_v,t` for each u<v, color t
   (endpoints of an edge may not share any color).

Suppose a satisfying assignment exists. Rule (1) selects at least one
vertex per position. Rule (2) makes the k selected vertices distinct.
Rule (3) forces all pairs of selected vertices to be edges. Rules (4)
and (5) force these k vertices to have pairwise different colors. This
would inject k values into c=k-1 colors, a pigeonhole contradiction.

The source-level checker rechecked every needed original clause and the
original source SHA256. **All 10** were admitted as SOURCE-SUPPORTED
mathematical UNSAT subformula witnesses. 80 constructed small UNSAT
encodings were accepted, and **80 SAT controls with explicit satisfying
assignments** were rejected as UNKNOWN after removing one required
clause (20 each: position ALO, clique injectivity, clique-edge link,
edge-color conflict). An additional valid negative unit was accepted.

## What this proves, and what it DOES NOT

The mathematical UNSAT family and the certificate structure are
well-known. A successful custom source-backed checker is **NOT** a
VeriPB/DRAT/LRAT/FRAT proof and must **NOT** earn strict PAR2 credit.
No short independent external VeriPB proof was produced for these ten
sources in this analysis. The 320s benchmark result is unchanged.

More subtly, clique-coloring is a **classical proof-complexity hard
family** for syntactic Cutting Planes in appropriate parameter regimes
(Pudlak 1997). Therefore, extrapolating our earlier small direct
graph-coloring cutting-plane proof generator here would be scientifically
misleading. OBDD proof systems with conjunction and weakening have
polynomial-size proofs of clique-coloring (Buss et al., CCC 2018).
VeriPB 3.0 offers redundant-constraint (`red`) and subproof facilities
that might serve as a certificate bridge, but no such bridge has been
built or externally verified here.

Sources:
- https://cnfgen.readthedocs.io/en/stable/cnfformula.families.cliquecoloring.html
- https://drops.dagstuhl.de/entities/document/10.4230/LIPIcs.CCC.2018.16
- https://veripb.org/overview.html
- https://mathweb.ucsd.edu/~sbuss/ResearchWeb/Caleidoscope/talkslides1.pdf

## Recommended follow-up, not yet a benchmark

Implement a conservative bounded, SHA-bound **source-only recognizer**
for the five clauses above, with a formally checkable source certificate.
Keep it independent from the strict VeriPB path.
Then explore a proof-logging module based on reification / extension
variables, OBDD or source-guided proof interpolation, and demand
external proof checker PASS on the smallest original (ID8: 273 vars,
5530 clauses; ID7: 300 vars, 6337 clauses) before a new paired E2E
benchmark. A successful structure-only witness is not eligible for main
promotion.

Research source checker, negative SAT controls and full clause-category
audits were also packaged as the reproducible analysis ZIP attached to
this ChatGPT conversation. The current experiment holds the 10 exact
source bytes in the completed GitHub frozen source artifact above.
