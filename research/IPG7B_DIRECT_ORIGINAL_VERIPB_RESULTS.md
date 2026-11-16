# DRNAS IPG7-B — configuration-indexed ORIGINAL-CNF VeriPB proof

**Completed 2026-11-16. Experimental branch only; main untouched.**

## The exact research question

IPG7 had a 7-line, pure cutting-plane proof on a DERIVED
two-machine configuration master, coupled to an independent
original-source reconstruction checker. It was NOT a standard
VeriPB proof against the original 300-clause weighted Petersen CNF.

IPG7-B generates ONE standard VeriPB certificate directly against
the ORIGINAL source, while retaining exact configuration masks
as the semantic guide for proof construction. External VeriPB3.0.2
checks the actual original DIMACS source, not its projection.

**Proof-search limitation:** the new bridge's source lemma
derivations and final source refutation use bounded DPLL case
splits and original-source unit propagation. Thus this is a
configuration-GUIDED standard original proof, NOT a search-free
mathematical import of IPG7's seven master POL steps.

## Original-source theorem and source clauses

For n jobs of positive weights p_j and 3 identical machines each
with capacity T, assume sum_j p_j = 3T. Every feasible schedule
must make every machine's load equal T.

Let F = {S subseteq [n] | sum_{j in S} p_j = T}. The original
source is validated as the EXACT one-hot + all
inclusion-minimal-overweight encoding, both by the producer
and a separately implemented independent source checker.

If ALL pairs A,B in F intersect, the original source is UNSAT.
A SAT solution would necessarily induce two disjoint full-T
configurations for the first and second machine.

For the original weighted Petersen:

- Original source SHA-256:
  `c2fefeffc1f9644ffd6f85728106a21c82dfc01d0d021f32d4d73569cc2bfb70`
- 45 variables, 300 source clauses, 15 jobs, T=29,524.
- Exactly 6 subsets of jobs have total weight T.
- Every pair of these six exact-T subsets intersects.

## A single original-CNF standard VeriPB certificate

For every one of the six exact-T masks S, IPG7-B produces a
separate ORIGINAL-source RUP derivation of the clause

  OR_{j in S} ~x_(j, machine0) >= 1.

This statement says that the exact-T configuration S
cannot occur on machine 0 in a satisfying 3-machine schedule.
For each S, complete bounded source-unit-propagation DPLL
case splits show that assuming all x_(j,0) in S true forces
a contradiction. Each leaf and branch-closure clause is
independently replayable as RUP on original source clauses.

After all six source no-goods are derived, the remaining
source contradiction is established by additional bounded
three-way job-assignment case splitting.

Every source-RUP step is locally replayed from the original
CNF. An independent research checker verifies every original
source clause, exact-T masks, source SHA, the six individual
configuration no-goods and RUP trace including the empty clause.

The whole source trace is also validated by independent
`drat-trim`. Then the frozen `research/ipg5e_pure_pol_from_source_rup.py`
translates the actual source RUP proof into a SINGLE STANDARD
VeriPB3.0 document using explicit source-resolution reasons,
integer PB additions and coefficient saturations.

**The external VeriPB command is**

  veripb-tool/bin/veripb --cnf ORIGINAL_SOURCE.cnf DIRECT_ORIGINAL_WEIGHTED_VerIPB.pbp

External pinned VeriPB 3.0.2 returned successful verification
of UNSAT on that exact ORIGINAL source.

## Successfully completed benchmark

GitHub Actions successful run:
https://github.com/Frane12/AndroidGameTest/actions/runs/43890563613

| Source | Configurations | Source case-block proof | Closing proof | Direct ORIGINAL VeriPB POL |
|---|---:|---:|---:|---:|
| Original Petersen 45v/300c | 6 | 50 RUP-derived steps | 100 steps | 150 POL |
| Permuted Petersen (same mathematical problem) | 6 | 50 | 100 | 150 POL |
| New independent weighted 5-job PCMAX UNSAT | 2 | 6 | 10 | 16 POL |

The single original Petersen standard proof is 16,663 bytes.
The exact 7-line derived-master pure-PB proof remains
SEPARATELY independently verified and is NOT the same
as the 150-line original source proof.

Two satisfiable controls, K4 cubic packing and six equal jobs,
produced independently verified COMPLETE SAT models against
each original CNF clause; both were correctly refused by
the UNSAT configuration bridge. One unsupported input with
zero exact-T configurations returned UNKNOWN.

Deliberate SHA input changes, a missing configuration block
and a truncated source-RUP proof were all rejected by
the independent source checker.

**Total: 6 test cases, 3 original-source VeriPB-accepted UNSAT,
2 independently checked SAT models, 1 UNKNOWN, and 0 errors.**

## What improved, and what did not

**Improvement:** This closes the important *proof-target gap*.
VeriPB now checks a complete proof against the ORIGINAL
300-clause source. It includes source-grounded lemmas for
each of the six configuration options known from IPG7,
rather than only a pure proof of a derived master CNF.

**Not an improvement in proof length:** The previous generic
source-only IPG5B already yielded an independently accepted
original source proof in 100 RUP/POL lines; the new
configuration-indexed bridge uses 150 lines and is larger.

**Not a pure mathematical or polynomial-time original source
proof discovery:** Source configuration exclusion and
final closure use bounded, worst-case exponential DPLL
search. Merely converting its discovered RUP clauses into
VeriPB `pol` instructions does not change that complexity.

**Not a general blind performance result:** these are
small source-frozen known problems and one independent
5-job packing case, not prospective source-disjoint SAT
Competition formulas with verification-inclusive PAR2.

## Files and reproduction

Code:

- `research/ipg7b_original_config_bridge.py` — bounded
  source config no-good construction and final source RUP.
- `research/ipg7b_independent_source_checker.py` — independent
  exact source reconstruction and full RUP replay.
- `research/ipg7b_source_veripb_benchmark.py` — serial one-core
  verification including DRAT-trim, original VeriPB and controls.

Reproduce on a runner with pinned VeriPB 3.0.2 and DRAT-trim:

  python3 -u research/ipg7b_source_veripb_benchmark.py

The exact original CNFs, derived master proofs, original-source
VeriPB proofs, SHA-bound configuration block metadata, logs and
full SAT models are in the successful Actions artifact.

## Next research gate

Replace the bounded DPLL proof of each configuration exclusion
by SOURCE-VERIPB integer cuts or certified knapsack/BDD bounds;
and replace the final 100-line DPLL closure by a direct
configuration-exhaustiveness PB theorem, ideally with
correctly checked redundancy/reification extension steps.

Only after that is there a credible basis to claim a fully
search-free, source-embedded seven-configuration mathematical
proof method. Native C++ integration and independent blind
performance work remain future engineering tasks.
