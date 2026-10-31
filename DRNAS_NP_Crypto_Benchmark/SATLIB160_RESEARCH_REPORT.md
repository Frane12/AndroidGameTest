# DRNAS NP Lab v0.3: independent SATLIB-160 and causal analysis

Date: 2026-10-31. Real GitHub Actions run: https://github.com/Frane12/AndroidGameTest/actions/runs/41185564328
Artifact: https://github.com/Frane12/AndroidGameTest/actions/runs/41185564328/artifacts/13036803425

## Independent evaluation

160 PREEXISTING SATLIB instances: 20 selected with a committed fixed seed from each of
uf20-91, uf50-218, uuf50-218, uf75-325, uuf75-325, uf100-430, uuf100-430, flat30-60.

Original benchmark page: https://www.cs.ubc.ca/~hoos/SATLIB/benchm.html

Each source tarball and original file is retained with SHA256 provenance.
For fair compatibility SATLIB's percent-sign EOF and trailing zero were
converted to standard canonical DIMACS; both programs received the exact
same canonical CNF bytes. This changes no logical constraints.
The tested algorithm did NOT receive source family information.

Environment: Ubuntu 24.04 GitHub Actions, Python 3.12.15, CryptoMiniSat 5.11.15.
One timed invocation per solver per instance; 1.5 seconds per invocation.
Wall-clock times below include separate process startup.
A second profile pass with 0.12s in-process budgets is DIAGNOSTIC ONLY,
not the comparative speed measurement.

| Family | DRNAS solved | CMS solved | DRNAS median ms | CMS median ms |
|---|---:|---:|---:|---:|
| uf20-91 | 20/20 | 20/20 | 48.870 | 2.622 |
| uf50-218 | 20/20 | 20/20 | 59.853 | 2.723 |
| uuf50-218 | 20/20 | 20/20 | 67.045 | 2.819 |
| uf75-325 | 20/20 | 20/20 | 98.107 | 3.003 |
| uuf75-325 | 20/20 | 20/20 | 157.240 | 3.308 |
| uf100-430 | 20/20 | 20/20 | 231.635 | 3.176 |
| uuf100-430 | 20/20 | 20/20 | 741.309 | 4.626 |
| flat30-60 | 20/20 | 20/20 | 50.873 | 2.619 |

**Result: CryptoMiniSat is faster on all 160 individual cases.**
Both solvers agree on 100 SAT and 60 UNSAT outcomes.
Neither timed out; no disagreement or runtime error.

The exact XOR-quartet detector finds **zero** in all 160 SATLIB
instances, and DRNAS selects **DPLL fallback** in all 160.
This is a limitation of this pattern recognizer, not proof no useful
algebraic structure exists in these instances. The fallback is a
reference Python DPLL, not modern conflict-driven clause learning (CDCL).
A significant part of short DRNAS case wall time is Python startup
(~40-50ms); for harder formulas the solver itself also scales worse.

## EXACT reason the earlier specially constructed XOR UNSAT set favored DRNAS

The generated factor graph contains XOR equations with each internal
variable occurring TWICE, but three terminal variables x1,x2,x3 once.
XORing all equations cancels all internal variables mod 2, yielding:

    x1 XOR x2 XOR x3 = 0

In the UNSAT version the residual unit clauses demand x1=x2=x3=1:

    1 XOR 1 XOR 1 = 1, contradiction with 0.

This is a short algebraic UNSAT proof. The SAT version instead fixes
x1=1, x2=1, x3=0, matching parity 0.

DRNAS recognizes each complete 4-clause encoding of an XOR triple
and solves through GF(2) elimination with a THREE-variable interface.
The masked variant uses the sound rewrite
(C OR z) AND (C OR NOT z) == C to recover XOR quartets.

Measured on 6 original UNSAT cases per family (in-process solver time):
- direct parity UNSAT: full algebra median 2.03ms, all 6 solved;
  disabling algebra: all 6 LIMIT at a 320ms budget.
- masked parity UNSAT: full algebra median 5.52ms, all 6 solved;
  disabling CNF pair cancellation: all 6 LIMIT.
- CMS 5.11.15 verbose trace on one 183-variable parity UNSAT:
  86,165 decisions and 56,001 conflicts; CMS did identify some XOR
  patterns during processing, so it would be misleading to claim CMS
  does not support XOR/Gauss in general.

This establishes **why the prototype won those synthetic cases**,
but NOT any generic advantage on NP-complete or SATLIB problems.

## Bugs caught by independent testing

1. The prototype DIMACS parser initially ignored SATLIB '%' EOF and
   interpreted its trailing '0' as an empty clause, falsely claiming UNSAT.
   Fixed parser to STOP on '%'; regression test added.
2. CryptoMiniSat 5.11.15 rejects '%' in SATLIB source with a PARSE ERROR.
   Both solvers now receive equivalent canonical DIMACS. Original files
   and checksums remain available for audit.

## Integrity and limitations

- Real external source selection, not cherry-picked after solver output.
- 1 repetition per case, one hardware runner; repeat >=3 times for
  statistically robust timing confidence.
- SAT models independently checked against input by benchmark parser.
  UNSAT is supported by SATLIB family labels and solver agreement; for
  formal independent certification, future proof traces should be used.
- Exact XOR detector only handles quartet-encoded arity-3 equations.
- No claim of solving P=NP or a novel generic complexity theorem.

## Research direction

1. Recognize larger and algebraically hidden parity constraints beyond
   exact triple quartets, verifying equisatisfiability.
2. Predict representation utility from low-cost exact features;
   **include the cost of discovering the structure** in timing.
3. Compare against CDCL and modern algebraic solvers on mixed
   parity-constraint, cryptographic and industrial benchmarks.
4. Run 3-10 repeated matched trials and publish per-instance dispersion,
   not only family-level median.
