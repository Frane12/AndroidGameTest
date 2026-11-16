# IPG-BDD3 → VeriPB: bounded class-scalar proof bridge

## What the experiment tries (and does NOT prove)

Starting with an independently source-verified IPG-BDD3 count certificate
and its original source-bound BDD graph, search for a nonnegative
**three-class scalar separator**. If such a separator exists, use
the existing DRNAS weighted BDD proof generator to derive a STANDARD
pseudo-Boolean proof (VeriPB 3.0), then demand external acceptance
from pinned VeriPB 3.0.2 against the ORIGINAL unmodified DIMACS source.

Crucial distinction: this is NOT a compiler for all three-dimensional
count-DP proofs. A target integer count triple may be unreachable
without admitting any separating nonnegative linear functional.
Such a gap is fundamentally integer/disjunctive. Therefore the
bounded scalar search may correctly return UNKNOWN even when the
independent BDD3 source proof is valid.

## Mathematical condition

Let P_i be the source-proved set of accepted BDD count vectors
(a,b,c) for machine i and let d=(|A|,|B|,|C|).

For an integer vector w=(alpha,beta,gamma) >= 0, compute

  K_i(w) = max_{p in P_i} <w,p>.

If the bounded search finds

  <w,d> > sum_i K_i(w),

then the ORIGINAL CNF is UNSAT. This is the familiar weighted
capacity inequality induced by the 3D count classes, rather
than the full integer proof of unreachable d. All bound
calculations account for skipped BDD levels and source-unit roots.

Each positive result is rechecked by the frozen independent
`check_capacity.py` and converted to source-inductive VeriPB 3.0
using the pinned existing `emit_veripb_capacity_weighted2.py`.
That proof must be checked by EXTERNAL VeriPB 3.0.2; the
converter never self-certifies a PB proof.

If 3D proof succeeds but no suitable w is found within the
explicit bounded search alpha,beta,gamma <= 12, output
NO_NONNEGATIVE_SCALAR_SEPARATOR (within that bound only).
Do not infer mathematical impossibility of all scalar cuts
from this bounded negative search.

## Scope and reproducibility

Native one-logical-CPU DRNAS BDD3 runs are executed serially
against 5 source-frozen original SAT Competition PCMAX formulas
and 3 exact-seeded previously held-out synthetic examples.
Known SAT controls remain UNKNOWN unless a full SAT model is
independently checked. All source SHA-256s are retained.

Separately, the established older native BDD capacity+VeriPB
proof for official PCMAX m20-4135 is rechecked as an explicit
historical baseline, never mislabelled as a NEW BDD3 conversion.

Primary hypotheses:
1. Some BDD3 certificates admit a low-coefficient scalar cut
   and thus a standard VeriPB proof against the original source.
2. Others may require genuine three-dimensional disjunctions/
   integer parity beyond ordinary positive weighted capacity.
3. Proof output and external checker time must be measured
   separately; this is NOT prospective blind PAR2.

## Reproduce

    cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
    cmake --build build --target drnas-pcmax-mg7-ipg1-bdd3 drnas-pcmax -j2
    cargo install veripb --version 3.0.2 --locked --root ./veripb-tool
    python3 -u research/ipg_bdd3_veripb_benchmark.py

Every emitted `*.pbp` is authoritative ONLY if

    ./veripb-tool/bin/veripb --cnf unchanged_source.cnf proof.pbp

returns 0 AND prints `s VERIFIED UNSATISFIABLE`.

## Limitations

- Does not produce direct PB steps for the 3D integer count DP.
- Can fall back to an already-known BDD weighted capacity argument.
- Search alpha,beta,gamma is bounded and incomplete.
- BDD size may be exponentially large in the original scheduling input.
- No general polynomial PCMAX/P=NP claim and no new competitor speed
  result until independently verified prospective original holdout.
- Main and frozen references remain unchanged.
