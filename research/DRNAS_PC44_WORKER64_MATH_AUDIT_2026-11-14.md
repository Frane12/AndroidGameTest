# DRNAS SAT — PCMAX #44 / Worker #64 structural audit
**2026-11-14 · exploratory, exact original SAT2024 CNFs · no promotion**

## Provenance
- Source parent: GitHub Actions [CF7 REAL100 run 43613581688](https://github.com/Frane12/AndroidGameTest/actions/runs/43613581688)
- PCMAX #44: `pcmax-scheduling-m11-1517-6802-UNSAT.sanitized.cnf.xz`, SHA-256 `c55ab8fe2c9e10f0579f806802bc32d04913f12cd6ce28e6662b8d59d114c174`
- Worker #64: `worker_20_40_20_0.95.cnf.xz`, SHA-256 `fc529dff1a6f763c97b0ed1dd33199e0d9dd26c50d210f9032e4fdaab5534c16`
- These are prior-exposed retrospective formulas, not an unseen holdout.

## PCMAX: exact factorization
The 6,802 clauses have the following exhaustive syntax:
- 21 all-positive long clauses: 20 length-11 and one length-5. All 225 choice variables are distinct.
- 1,527 all-negative binary clauses: **1,110** provide all intra-group pairwise mutexes, making each of the 21 positive groups an **exactly-one** constraint; **220** exclude choice pairs in different groups; **197** exclude choice/auxiliary pairs.
- 2,500 mixed-sign ternary clauses, matched without leftovers into **1,250 pairs** under one state `a` and choice `x`: `(x ∨ ¬a ∨ b)`, `(¬x ∨ ¬a ∨ c)`. Thus `a∧¬x⇒b` and `a∧x⇒c`; these are implications, not claimed equivalences.
- 2,702 all-negative ternary clauses of the form `¬a_i∨¬a_j∨¬x`, each involving two state variables from different networks plus one choice.
- 52 unit clauses (41 positive, 11 negative).

The transition graph has **11 distinct weak components** of sizes 51, 51, 56, 56, 72, 72, 88, 89, 89, 324, 324. All 2,500 transition edges increase the state index (acyclic). All **1,850 edges** that lead to another transition state advance **exactly one choice-group layer**. The remaining 650 edges lead to terminal states. The 2,702 negative ternaries connect **all 55 possible pairs** of the 11 networks (complete `K11` coupling graph). This is a collection of ordered branching/decision networks jointly coupled by resource-like incompatibilities, not eleven independent easy Horn problems.

Root unit propagation forces 62 variables and leaves 6,625 live clauses. Pure-literal elimination plus unit propagation assigns 104 variables in total and leaves **6,436 clauses**. The formula is **not** globally Horn-renamable; the binary-and-unit-only subformula does **not** establish UNSAT. Horn-only forward closure forces 41 true variables without a contradiction.

A family-based greedy **strong Horn backdoor upper bound** has 225 variables. The 21 disjoint positive clauses give a **rigorous 204-variable lower bound** for deletion-to-Horn on the *original variable polarities* (20·10+4), so the interval is 204–225. This should not be confused with a minimum renamable-Horn backdoor.

## Verified logical preprocessing
The 11 negative unit state terminals produce **584 new binary resolvents** of the form `¬a∨x` or `¬a∨¬x`. None already appears as an original clause. Every resolvent has a one-step RUP witness: negate the proposed binary clause, use the corresponding original ternary transition to force a forbidden terminal, then contradict its original negative unit. These are safe to add as redundant clauses without changing satisfiability.

Exploratory local, same-CPU 8-second comparison of original and 584-augmented PCMAX:
- CF7 original: UNKNOWN, 211,954 conflicts.
- CF7 augmented: UNKNOWN, 226,829 conflicts.
- Kissat original and augmented: both timeout.

The conflict counts indicate different throughput/search behavior, **not** improved verified PAR2. Neither variant was solved in this small test. The augmented variant must not be promoted without repeated, source-paired benchmarking and independently validated SAT/UNSAT answers.

## Worker: a different combinatorial problem
The source consists of **17 disjoint all-positive groups** (553 total candidate variables, 30–39 per group), **11,917 all-negative binary exclusion clauses**, and 103 other pure-negative variables. There are no other clause types. Only 262 of 8,750 possible within-group pairs are explicitly prohibited; the groups are not syntactically exactly-one.

However, any satisfying assignment can be modified to choose **exactly one true variable per positive group**, while setting all other variables false, because deleting true literals cannot violate a negative binary clause. Thus SAT reduces exactly to finding an **independent transversal** of 17 groups in a binary incompatibility graph.

A small Python DFS with minimum-remaining-values and least-impact ordering found a **full original-CNF-verified SAT model** after 18 search nodes and zero backtracks. Selected true variables:
`[200, 94, 614, 48, 279, 119, 351, 6, 158, 233, 313, 390, 428, 470, 510, 551, 573]`.
All other variables may be assigned false. This is a sound SAT witness, **not** a representative runtime speedup benchmark. The prototype's inner search clock excluded CNF loading.

Worker is also not globally Horn-renamable. Its syntactic strong Horn-backdoor minimum is **536** variables, exactly: each of the 17 disjoint all-positive groups must lose all but one, and removing those 536 suffices because all other clauses are all-negative. Backdoor size alone therefore does not predict practical difficulty: Worker is easy despite a larger deletion-to-Horn backdoor than PCMAX.

## Proposed proof-first paths
1. **Worker-domain guard:** detect the exact two-clause-type pattern, all-positive disjoint choice groups and all-negative binary mutexes. Run a strict bounded independent-transversal search *inside one solver and CPU*. Accept a SAT answer only after validating the complete original CNF witness. On timeout/failure, return to unmodified CDCL. Do not claim UNSAT without a certificate.
2. **PCMAX automaton guard:** detect group exactly-one constraints plus ordered state transitions and cross-machine negative ternaries. Test cheap backward reachability and redundant RUP binary inferences under a fixed time budget. No speculative branch skipping and no automatic promotion.
3. **Comparison protocol:** frozen, hash-checked original CNFs, serialized one-CPU arms, equal wall/CPU accounting, 3+ repetitions, accepted SAT model / independent UNSAT proof, source-disjoint validation then blind holdout, verified PAR2 and memory/proof-size penalties.

This is a structural diagnostic and potentially useful algorithmic idea, **not** a new complexity-class theorem or evidence that P=NP.
