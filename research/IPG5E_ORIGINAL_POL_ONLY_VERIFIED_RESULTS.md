# DRNAS IPG5-E — original weighted Petersen pure-POL VeriPB proof

## Verified result (2026-11-16)

GitHub Actions SUCCESS:
https://github.com/Frane12/AndroidGameTest/actions/runs/43872950102

One original SHA-256-fixed Petersen PCMAX CNF:
`c2fefeffc1f9644ffd6f85728106a21c82dfc01d0d021f32d4d73569cc2bfb70`,
45 variables, 300 original clauses.

**Independently accepted VeriPB 3.0.2 proof:**
- 100 `pol` proof lines, **0 `rup` or `pbc` proof lines**
- 1,398 PB additions, 1,398 PB coefficient-saturation operations
- 0 literal-axiom weakening additions on this original
- 11,681 proof bytes
- Independent external VeriPB checker returned 0 and printed
  `s VERIFIED UNSATISFIABLE` on the original unchanged CNF.

Additional accepted pure-POL original-source UNSAT proofs:
- Source-permuted Petersen: 169 pol, 1,767 saturations,
  24 literal-axiom weakening additions (proof 15,643 bytes).
- 7-job cardinality packing: 163 pol, 813 saturations
  (proof 7,524 bytes).
- 3-coloring odd wheel W5: 10 pol, 84 saturations
  (proof 770 bytes).
- SAT 6-job packing and unsupported 9-var CNF controls:
  both UNKNOWN; no false UNSAT.

Source tampering and missing terminal RUP contradiction were
rejected. Independent DRAT-trim first accepted every bounded
native source trace; external VeriPB independently accepted
the POL-only translation. No modification to main or frozen
solver references.

## What was actually proved (and what was NOT)

The new `research/ipg5e_pure_pol_from_source_rup.py` walks a
previously generated RUP proof and reconstructs its unit
propagation antecedents from exact input clauses and earlier
lemmas. For a source RUP clause C, assume all literals of C
are false; then source unit propagation reaches contradiction.

By resolving the final conflicting source clause against
unit reason clauses in reverse chronological order, the
generator derives C using source-supported *ordinary resolution*.
Each binary resolution is simulated by the cutting-plane rule

    pol <left-ID> <right-ID> + s ;

where `+` combines two source-supported PB clauses and `s`
saturates any duplicate literal coefficient. The eliminated
pivot contributes x+~x=1. If an implied clause is a
strict subset of C, literal axioms add the extra allowed
literals. A separate integer PB normalizer checks each
intermediate resolvent before writing a POL command.

Thus the FINAL proof really consists ONLY of VeriPB
cutting-plane arithmetic, and VeriPB externally accepts it.

**However the upstream source trace was DISCOVERED by bounded,
worst-case exponential, NON-CDCL DPLL job-level case branching.**
A proof FORMAT consisting only of `pol` instructions is NOT a
proof discovery algorithm restricted to cutting planes, and
does NOT establish polynomial-time SAT or general PCMAX.

No improvement over the frozen DRNAS CDCL is claimed:
the old CDCL/MG7 proof of this original source had 92 RUP
clauses and about 3,746 PB bytes; the IPG5-E pure-POL
proof has 100 `pol` lines and 11,681 bytes. This pilot
targets certificate semantics, not best runtime or compression.

## Why original rank-one source odd-cycle cuts alone cannot suffice

Consider the fractional assignment x_i=1/3 to all 45
original assignment variables. EVERY original CNF clause,
when translated to a linear PB constraint, is satisfied:

- Exactly-one job ALO triple gives 3*(1/3)=1.
- Every original all-negative clause has length at least 2,
  giving at least 2*(2/3)>=1.

Moreover ANY odd cycle of length L>=3 in the original
binary-conflict graph produces the rank-one cut

  sum_(i in cycle) ~x_i >= ceil(L/2).

At x_i=1/3, the left-hand side is 2L/3 and
2L/3 >= (L+1)/2 for all L>=3. Thus ALL such
individual odd-cycle cuts retain this fractional witness.

Consequently original source clauses PLUS these particular
rank-one odd-cycle cuts cannot directly give a contradiction.
One needs higher-rank cuts, other structural constraints, or
case analysis. This does NOT say all rank-one CG cuts fail;
only the specific binary odd-cycle family was analyzed.

## Next important mathematical experiment

Find a DPLL-FREE *proof discovery* procedure using direct
original-source PB inequalities, potentially:
- multi-round integer cutting planes and disjunctive hulls,
- graph odd-set/parity inequalities source-grounded via a
  polynomial certificate of source-to-graph reduction,
- machine-state dynamic programming with a VeriPB derivation
  of the required integer-rounding lemmas.

Proofs must be generated from exact source and independently
checked; do not claim a new algorithm based solely on
post-processing a DPLL-produced trail.

Reproduce:

    cargo install veripb --version 3.0.2 --locked --root ./veripb-tool
    make -C drat-trim drat-trim
    cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
    cmake --build build --target drnas-ipg5b-jobbranch drnas-ipg5c-onehot -j2
    python3 -u research/ipg5e_pol_benchmark.py

All results are exploratory known-source retrospective experiments,
not source-disjoint blind PAR2. The branch is
`experiment/drnas-ipg5e-original-pure-pol-20261116`.
