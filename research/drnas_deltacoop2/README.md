# Delta COOP2: nonlinear information between local modules

This is a falsifiable discovery experiment, not a claim of new mathematics,
a proof about P versus NP, or a promoted solver.

## Question and exact comparison

At the same CDCL Boolean-propagation fixpoint alpha, form the exact feasible
tables T_A(alpha) and T_B(alpha) of two overlapping local blocks. Match their
assignments on the shared separator and remove tuples without a partner.
This is an exact two-relation semijoin. Each block has at most 8 variables;
the union has at most 12. No approximation is used for logical inference.

Look for a forced literal (or empty join) absent from the evaluated individual
tables. For each such event, search for a violating assignment in

    Aff_GF2(T_A(alpha)) JOIN Aff_GF2(T_B(alpha)).

A concrete countermodel is a certificate that **all linear GF(2) consequences
of these two conditional tables together** do not imply the proposed literal.
That certificate establishes a nonlinear information gap for this comparison.
It says nothing about the power of all other blocks, full-CNF Gaussian
reasoning, failed-literal probing, or stronger CSP/SAT algorithms.

An emitted DELTA2_WITNESS includes the actual block CNFs, variables,
assumptions, conclusion, and affine countermodel. Python independently
enumerates both tables, constructs their affine hulls without the C++
algorithm, and validates the exact join and countermodel. Logs retain up to
four conclusion witnesses per run. Event counters are not counts of distinct theorems.

A separate SECONDARY diagnostic samples removed left-table tuples even when
no literal is forced: a tuple is in T_A, has no partner in T_B, yet has a
partner in Aff(T_B). These are concrete nonlinear combination exclusions,
not CDCL assignments or evidence of speed. At most 16 tuple probes and four
saved tuple witnesses per run. Their fields are separate from conclusion
certificates and the primary structural success criterion below. This
diagnostic was added after a 0.25-second exploratory REAL36 smoke saw tuple
removals but no new pair-forced literals; the cohort remains retrospective.

Only conclusions with a bounded resolution/RUP derivation from ORIGINAL
clauses are inserted into CDCL. The preflight checks every proof addition
with an independent forward RUP checker, all SAT models against originals,
and all UNSAT results with drat-trim. The original frozen drat-trim's SAT
forward mode can abort on repeated intermediate additions, so it is not the
checker used for partial SAT proofs. Full UNSAT checks still use drat-trim.

## Controlled positive example

Use a three-bit separator (x1,x2,x3). One six-variable block permits separator
patterns {0,1,2,4}; the other permits {1,3,5,6}. Each separator relation has a
full three-dimensional affine hull and neither fixes a separator bit. Their
intersection is {1}: the exact nonlinear relations fix all three bits.
The blocks have disjoint sets of three additional free variables, making a
nine-variable union. The DIMACS CNF alone is passed to the solver.

The preflight uses 12 polarity/variable/order variants, SAT and UNSAT cases,
and downstream implication chains, plus existing exhaustive and random
small-CNF cases. These planted examples validate the mechanism; they are NOT
evidence of industrial speed or scientific novelty.

## Arms and immutable references

* OFF: no collection or mathematical propagation.
* LOCAL: exact individual tables, same gate and source as JOIN.
* SHADOW: tables and joins observed without injecting clauses or branching hints.
* JOIN: same local inference plus proof-certified pair consequences.
* DELTA1: immutable previous binary from run 43582788399.
* KISSAT and CADICAL: same frozen binaries and original sources as Delta1.

OFF/LOCAL/SHADOW/JOIN use one executable. Heuristic hints and COOP5 probes are
disabled in all new arms. A source-pinned generator replays only historical
text transforms, preserving source-drift assertions and omitting old compiler
invocations and their compiler-specific binary assertions. It compiles only
the new binary. Frozen Delta1 and competitor executables are not rebuilt.
The new build manifest records all inherited source hashes, new header hash,
generated source hash, compiler identity and resulting binary hash.

Eligibility is checked before entering the CDCL bridge. Analysis waits for
64 conflicts in benchmark mode, uses backoff, and skips unchanged pair states.
Maximum 64 blocks, 96 pairs, 24 passes, 8 lemmas per pass, 256 total lemmas,
8192 proof steps. The 2.5 ms pass and 30 ms cumulative limits are checked
between bounded operations; they are soft latency budgets, not hard-real-time
guarantees. Inherited 4096-variable and 24000-clause collection limits remain.

## Evidence and decision rules

REAL36 is the previously used retrospective official SAT2024 cohort: 36
original CNFs, seven families, two repeats, seven arms, 504 trials, 5-second
solve E2E cap, one logical CPU per solver. Trial order is deterministically
shuffled. SAT witnesses and independent original-CNF UNSAT proofs are needed
for credited PAR2; checker time is reported separately. Missing/late/unverified
answers receive 2*cap. Timeouts are never evidence of mathematical failure.

Report separately:

1. Structural indication: independent nonlinear countermodels and certified
   join conclusions on distinct originals, with source family counts.
2. Causal integration: direct CDCL assignments, conflicts and cascades.
3. Search and cost: decisions/conflicts, math time, verified solved and PAR2;
   JOIN versus LOCAL isolates adding pair reasoning, while OFF and frozen
   DELTA1 show the total implementation cost.
4. Uncertainty: bootstrap intervals resample families, not individual repeats.
   Seven families give limited resolution; a tiny global PAR2 change is not
   a speed discovery.

A worthwhile discovery candidate should recur on at least three distinct
originals from at least two families. Any speed claim requires a separately
frozen, source-disjoint holdout, zero invalid answers and >=10% verified PAR2
gain versus the best reference, with a positive uncertainty bound. REAL36
does not satisfy that holdout requirement. This workflow never promotes main.
If there are no real nonlinear certificates, the result is negative for this
bounded selector/budget, even when the crafted positive control passes.

## Prior art and novelty boundary

Exact joins and relational consistency are established methods, and XOR/CDCL
cooperation is established too. Potential novelty would have to concern the
specific selection/gating/measurement method and survive a broader prior-art
review; this experiment does not establish it.

* Dechter and Pearl, Tree Clustering for Constraint Networks (1989):
  https://doi.org/10.1016/0004-3702(89)90037-4
* Dechter and van Beek, Local and Global Relational Consistency (1997):
  https://doi.org/10.1016/S0304-3975(97)86737-0
* Laitinen, Junttila and Niemela, Extending Clause Learning SAT Solvers with
  Complete Parity Reasoning (2012): https://arxiv.org/abs/1207.0988

## Reproduce

Restore delta-coop1-preflight from run 43582788399 and extract delta_frozen.tgz.
Run from repository root:

    python3 research/drnas_deltacoop2/build.py
    python3 tests/test_drnas_deltacoop2.py
    python3 research/drnas_deltacoop2/paired.py shard --shard 0

Use shards 0 through 5; the workflow downloads them into the expected folder
structure and runs paired.py aggregate. The smoke stage runs only JOIN on
all 36 sources at 0.25 s, for operational coverage, never a speed comparison.
