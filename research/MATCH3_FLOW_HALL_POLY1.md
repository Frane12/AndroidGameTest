# DRNAS MATCH3-FLOW-HALL: polynomial min-cut certificate on source-CNF (2026-11-16)

**Experimental branch only:** experiment/drnas-match3-flow-hall-poly1-20261116.
No production C++ solver, main, APK, or frozen baseline modified.

## Mathematical theorem (restricted source-CNF family)

Suppose an arbitrary input CNF F *literally contains* disjoint positive
clauses G_j = (OR_{v in V_j} v) for jobs j=1,...,n. The chosen V_j must be
pairwise disjoint. Map every chosen selector variable into exactly one
resource R_i (resource sets form a partition of the selected variables).
An original negative unit (-v) makes that selector unavailable.

For every resource i, certify an upper bound c_i on how many DISTINCT
jobs can choose selectors from that resource in a satisfying assignment:
if c_i is below the number of eligible jobs, then for every set of
(c_i+1) active selectors from different jobs in R_i, the negative
source clause (-v_1 OR ... OR -v_(c_i+1)) must *literally appear* in F.
No source hints or comments are trusted. If a smaller cap is not
certified, use the trivial cap equal to the number of eligible jobs.

Build a bipartite graph with one vertex per job, one per resource,
job-resource edges for non-unit-excluded source selectors, source->job
capacity 1, job->resource capacity 1 and resource->sink capacity c_i.
For a subset of jobs S, N(S) is the set of resources adjacent to S.

**Theorem.** If the max flow is less than n, an integer minimum cut
provides a nonempty set S with:

    |S| > sum_{i in N(S)} c_i.

Therefore F is UNSAT.

**Proof.** Any assignment satisfying each source ALO must select at
least one available selector per job. Choose one such true selector
per job. By the literally checked negative source clauses, no
resource has >c_i distinct jobs with chosen selectors. These choices
would define a feasible integral unit-flow of value n, contradicting
the max-flow/min-cut witness. Constraints of F that were ignored can
only reduce the set of satisfying assignments. QED.

The max-flow part is polynomial: this implementation uses Dinic.
Checking source capacity premises is polynomial when c_i <= 3 is
fixed, with bounded O(R * L^4) tuple enumeration, where L is the
number of source selectors. This is a *sufficient UNSAT detector*,
not complete for general SAT, and not a P=NP result. The mathematics
of capacitated Hall matching and max-flow/min-cut is established prior
art; the experiment tests source-CNF recovery plus verifiable routing.

## How this differs from MATCH2 and MATCH2-BDD-MASK1

* MATCH2 exhaustively enumerated all job subsets and refuses n>18.
  MATCH3 replaces the 2^n subset scan with flow and recovers an
  independently checked polynomial-size Hall witness.
* MATCH2-BDD-MASK1 reasons about exact machine job-set masks and can
  prove the original 45-variable, 300-clause weighted Petersen PCMAX,
  but its 3^n worst-case mask convolution is exponential. MATCH3
  deliberately does **not** claim to reproduce that exact-mask proof
  or decode arbitrary source BDD, PB and weighted PCMAX constraints.
* For source clauses not giving direct capacities the method falls back
  to an uninformative capacity or UNKNOWN. For correct UNSAT claims it
  *never* relies on candidate inference being correct without checking.

## Scope, safeguards and validation

* <=200 disjoint ALO jobs, <=2400 selectors, <=100,000 source clauses,
  <=1,000 inferred resources, caps certified by negative tuples of
  size 2, 3 or 4, bounded at 150,000 producer tuple checks.
* Producer: research/match3_flow_hall.py.
* Separate checker: research/match3_flow_hall_checker.py. It does
  NOT import the producer, recomputes all original source premises,
  job/resource partition and Hall arithmetic, and rejects changed
  source hashes or incomplete/forged capacity witnesses.
* The source certificate is project-specific, **NOT a DRAT/LRAT/VeriPB
  certificate**. No result is labeled standard-proof-verified.
* Deterministic bench: research/match3_flow_hall_bench.py.
  Retrospective constructed original CNFs: pigeonhole, sparse subset
  Hall, capacity-two triples, SAT counterexamples, renumberings,
  source mutation/forgeries, small independent exact DPLL controls,
  and earlier original weighted Petersen as an honest unsupported case.
* One logical core per process; minimal logs; frozen CNF bytes, SHA,
  certificate JSON, per-case results as CI artifact.
* **No official source-disjoint blind real SAT benchmark yet.**
  No comparison against Kissat/CaDiCaL/CMS PAR2, no claim that this
  algorithm is newly discovered and no main merge.

## Reproduce

    python3 -m py_compile research/match3_flow_hall*.py
    python3 -u research/match3_flow_hall_bench.py
    python3 research/match3_flow_hall.py sample.cnf --certificate sample.json
    python3 research/match3_flow_hall_checker.py sample.cnf sample.json

A source-checker acceptance means UNSAT has been proved within the
narrow source-bound capacity/Hall theorem, not that a standardized
general-purpose competition certificate has been checked.

## Next scientific experiment

Extract capacities from bounded *source-verifiable BDD/PB* implications,
not just literal forbidden tuples, so that the weighted Petersen
45/300 source can be bridged without exponential job-mask enumeration.
Require independently accepted standard proof certificates and a
prospective, source-disjoint mixed original-CNF holdout with identical
core/cap and verification-inclusive E2E PAR2 before performance claims.
