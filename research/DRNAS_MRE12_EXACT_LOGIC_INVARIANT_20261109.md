# DRNAS MRE12 — exact Boolean meaning invariant

**Status: experimental, source-preserving, no automatic production promotion.**

## Mathematical contract

Let F be the original Boolean CNF. Every source binary clause
(a OR b) certifies the implications ((NOT a) -> b) and ((NOT b) -> a).
For every proposed signed substitution v := L, the independent proof
replayer must verify an original-binary-clause path v -> L and a second
path L -> v. Thus F entails (v iff L), without assuming a guessed XOR
pattern, statistical correlation, or a solver's output.

Define Q(F) by substituting only these replayed signed equalities
throughout every clause, dropping tautologies and duplicate clauses.
The original source file, original-variable SHA and witness domain
remain untouched.

The correct equivalence is **through projection and reconstruction**,
not a claim that arbitrary assignments to removed variables still match:

- Every model of F obeys all certified equalities, so projecting it
  onto representative variables satisfies Q(F).
- Every model of Q(F) can be expanded by v := value(L) for every
  removed alias to obtain a model of the unchanged F.
- These maps are inverse on satisfying original assignments. No original
  logical solutions are lost, and no spurious source models are accepted.

SAT results from the transformed formula are verified twice:
first on transformed clauses, then on the unchanged original CNF
after fully reconstructing original variables.

## Four-arm causal pilot

1. baseline: untouched source plus pinned CaDiCaL.
2. shadow: pay for full detection/replay, then solve untouched source.
3. quotient: solve certified quotient only if proof-replayed aliases exist,
   otherwise solve untouched source.
4. selective_no_vivify: retain untouched source, disable vivification
   only if >=2 certified equivalences were found. This is an
   **unvalidated structural selection hypothesis**, not a proven
   prediction of vivification benefit or a universal disabling rule.

Bounds: <=6,000 variables, <=70,000 clauses, <=48 aliases, <=12 graph
edges per proof direction, 0.6 seconds search budget. On insufficient
or contradictory evidence, the transformation abstains.

Source provenance: 12 frozen originals reused from completed
C15D run 42541912605, six development and six *previously evaluated*
official originals. These are NOT globally blind. Four arms times two
repeats per source = 96 source-matched attempts, cap 8s, timeout
PAR2 = 16s; preparation and SAT check overheads charged E2E.
The external solver seeds are not independently changed.

## Validation

The implementation selftest checks 506 small CNFs and 6,232
truth-value assignments, with positive/negative equalities, contradictory
SCC, empty clauses, and rejection of deliberately tampered
implication-path certificates. This finite test is a regression audit;
the soundness theorem comes from replayed original implications and
explicit inverse model reconstruction.

All SAT witnesses must satisfy original F. For UNSAT, published
reference agreement is NOT an independent LRAT/FRAT proof. An auditor
must reject unpaired modes, source hash drift, unexpected solver
verdicts, missing original witness, and incomplete PAR2.

No promotion on proof counts or isolated development time savings.
A source-disjoint new holdout with independent SAT/UNSAT certification
is required to claim generalization.
