# DRNAS SAT R30 — algebraic structure versus CDCL dynamics: evidence and pre-registered hypotheses

Date: 2026-11-03
Status: **literature + existing benchmark audit + independently checkable toy CNF; NO new R30 benchmark has been run.**
Stable V15.3.1 unchanged. This is a research design on a separate branch, not a proven new heuristic.

## Core scientific distinction

The connection is not "number of XOR clauses => CDCL is slow". The connection is the **deductive gap** between conditional GF(2) linear-algebra consequences and consequences visible to the current CDCL Boolean-clause propagation under the *same* partial assignment, and whether the extra deductions are worth their cost.

Exact parity subset: A x = b (mod 2), where every recovered XOR constraint is backed by original or soundly derived clausal proof. Under an identical CDCL trail T, compare:

- BCP(F|T): Boolean unit-propagation fixed point on original clauses.
- GF2(A,b|T): newly implied unit assignments and zero-row contradictions from linear algebra of *certified* parity subset.
- **Gap**: G(T) = number of independently certified GF2-implied single-variable assignments not already in BCP(F|T). Record H(T)=1 if GF2 detects a contradiction not in the BCP snapshot. This is a testable **feature**, not an already proven runtime predictor.
- Algebraic rank: rank(A), rank([A|b]), rank deficiency (#rows - rank(A)), component size, row density and width; rank augmented greater than rank(A) is a valid contradiction. Rank by itself is **not** a CDCL runtime predictor.
- CDCL observations at conflict checkpoints: propagation count, decisions, conflicts, restart count, local/cross-community conflict antecedents, reason reuse, LBD distribution, learnt-clause age/re-use; cost in milliseconds and CPU cycles.
- Newly learned parity support: count **proof-verified** XOR/XNOR/ITE structures recoverable from learned clauses, not just original CNF. Learned clauses must retain original-CNF proof trace to establish consequence.

## Independently reproduced 4-variable example

Let original equations be (GF2):

  x XOR y XOR z = 0
  x XOR y XOR w = 1
  z = 0

Encoded in CNF: 4 clauses per width-3 XOR plus unit (-z): 9 clauses, 4 variables.
Plain Boolean unit propagation (BCP) assigns only z=0.
XORing the first two equations cancels x,y: z XOR w = 1, hence w=1.
Enumerated complete CNF models: (x,y,z,w) = (0,0,0,1) and (1,1,0,1).
Thus GF2 yields one additional valid unit **without any BCP unit consequence on w**.
This demonstrates deductive gap but not a performance speedup by itself.

## Existing DRNAS empirical findings — distinguish from hypothesis

- R26 paired original R24 random3 test_01, N=220 M=931: switching native restartint to 50 at conflict 2048 made median 0.057532s -> 0.176460s (3.07x slower), while 2048->25 gave 0.056505s. Pre-2048 **R6 recorded checkpoints** matched across arms. This proves a causal intervention effect on the tested problem, **not** an XOR cause: no recovered parity algebra was established for the example. Source: https://github.com/Frane12/AndroidGameTest/actions/runs/41606817712
- R28 240 fresh but XOR-rich synthetic formulas, 2 runs each: total PAR2 improved 62.704% vs same pinned clean Kissat, but non-XOR family overhead was negative. Source: https://github.com/Frane12/AndroidGameTest/actions/runs/41613064879
- R29 72 synthetic recovery-focused formulas, 2 runs × 4 arms: R29 active total PAR2 0.614259s versus Kissat 107.021376s. On incomplete XOR decoys and easy mixed unit-derivation formula families it was **~43% and ~46% worse** in aggregate; certified units are sound, but preprocessor/gating/solver overhead can exceed savings. Source: https://github.com/Frane12/AndroidGameTest/actions/runs/41617986064
- R29 on 14 **real original** SAT Competition 2026 GBD CNFs, 2 runs × 4 arms, 6-second cap: R29 safe 2/14 solved, sum per-case median PAR2 150.163s; pinned Kissat 2/14, 150.260s. For both solved cases R29 reported **input_guard + fallback**, not activated algebra; 12 cases timeout. It does not demonstrate generalization to real cases. Source: https://github.com/Frane12/AndroidGameTest/actions/runs/41620579411
- R24 telemetry is only **1-UIP traversal**, not a full implication graph. It cannot be treated as a complete source for graph-causal claims.

## Literature already covering related mechanisms (prior art)

1. Soos & Bryant, *Proof Generation for CDCL Solvers Using Gauss-Jordan Elimination* (2022): CDCL can fare poorly on parity constraints; algebraic GF2 proof integration helps. https://www.cs.cmu.edu/~bryant/pubdir/pos22.pdf
2. Ansótegui, Giráldez-Cru & Levy, *The Community Structure of SAT Formulas* (SAT 2012): industrial formulas show modular communities, much learned-clause activity is local. https://www.ugr.es/~jgiraldez/publications/2012_SAT_abstract.html
3. Ansótegui et al., *Community structure in industrial SAT instances* (JAIR 2019): learned clauses reshape modularity. https://upcommons.upc.edu/entities/publication/89953f92-fff7-447e-8755-9d27d4cd931f
4. Yang, Shaw, Baluta, Soos & Meel, *Explaining SAT Solving Using Causal Reasoning* (SAT 2023): observational and intervention causal study of clause utility/heuristics. https://drops.dagstuhl.de/entities/document/10.4230/LIPIcs.SAT.2023.28
5. Pollitt et al., *Factoring Learned Clauses* (SAT 2026): factor XOR and ITE gates **from learned clauses**, exploiting extended resolution; shows benefits on hard combinatorial problems. https://drops.dagstuhl.de/entities/document/10.4230/LIPIcs.SAT.2026.28
6. Soos (CryptoMiniSat FAQ): Gaussian elimination may require explicit build/runtime flags; benchmark parity-aware solver with verified Gauss configuration, never assume presence from version alone. https://www.msoos.org/cryptominisat-faq/

None of these concepts is novel merely by naming it. The possible DRNAS contribution is a rigorously evaluated, low-overhead **admission gate** that links certified algebraic deductions to real-time CDCL usefulness, including negative cases.

## Three explicit R30 hypotheses (NOT YET CONFIRMED)

**H1. Conditional propagation gap predicts intervention benefit.** Hold structural formula features fixed; at a frozen CDCL conflict checkpoint, compare GF2-only unit count and conflict detection against BCP at the same original trail. Test whether verified G(T)>0 or H(T)=1 predicts more avoided conflicts *net of probe cost*. Control with G=0 formulas. No action during first shadow-only collection.

**H2. Clause-learning makes hidden algebra more detectable.** On a bounded sample of new clauses at checkpoints 0, 256, 1024, 4096 conflicts, inspect the increase in *certified* parity blocks and ITE motifs after clause learning. Compare rank, proof size and time needed to construct reasons. This directly tests the gap between R29 static CNF patterns and dynamic CDCL clauses. Avoid assuming that syntactic XOR-looking patterns are logically valid.

**H3. Interface structure mediates useful vs harmful CDCL guidance.** Record graph modularity, XOR-to-non-XOR boundary fraction, key bridge-variable centrality, LBD and useful learned-clause repropagation. Fit on independent development corpus whether GF2 propagation on high-centrality bridge variables predicts useful CDCL progress better than raw XOR count or restart count. This is not yet an observed DRNAS correlation.

## Admission and cost model

An algebraic inference is *sound* if and only if it is independently provable from original/learned clauses. Soundness is separate from performance.

Require:
1. **Verified** recovered parity blocks or resolution-derived equations, bounded memory/time, no guessed XOR from incomplete sets.
2. Short shadow probe at fixed checkpoints, with full profiling, never applied to main search before randomization. Budget cap is a prospective parameter to tune on development only; fail closed on exceed.
3. Estimate net runtime: estimated saved CDCL conflicts × observed recent time per conflict, minus algebraic extraction/elimination/reason-generation costs. This is heuristic and must be validated by matched intervention/fallback A/B tests.
4. Safe fallback and no accepted slowdown outliers hidden by averages; report worst pairwise regressions, solved/unsolved, PAR2, SAT witness and independently checked UNSAT certification.
5. Do not infer speedups from a preprocessor performing only **Kissat fallback**; successful solver path and proof of intervention must be separately logged.

## Plan for next empirical run (not yet started)

**Phase A: diagnostic instrumentation**, not optimization:
- For each SHA-distinct original official SAT Competition formula, record explicit input guard reason: bytes, nvars, clauses, clause-width histogram and time spent per step; use a bounded streaming sampler for large CNFs, never silently remove the 12 MiB / 3000 var / 150k clause guard.
- Collect verified GF2 subset component/rank features, direct and learned support (with proof where relevant), BCP-vs-GF2 extra units on identical trails. Record 0/256/1024/4096-conflict R6 snapshots, and reason / LBD telemetry.
- Separately label official industrial, cryptographic/XOR, random, planted, and decoy categories. Include test-set cases where no parity is found.
- Build clean Kissat/CaDiCaL and truly XOR-enabled CryptoMiniSat reference. Record CPU, binary SHA and original-CNF SHA, same runner and matched randomized paired runs.

**Phase B: causal test** only after Phase A:
- Freeze a model on a development set, never re-use it as blind.
- On a new SHA-separated set, compare (A) no GF2, (B) shadow scan/no action, (C) verified GF2 consequences inserted with proof and bounded budget. Matched original CNFs, seeds and process CPU pinning; no uncontrolled restarts or phase edits.
- Prefer 30 and 120 second cutoffs rather than only 2–6 seconds; report per-family and cross-family with timeout PAR2. No universal or championship claim from one distribution.
- Keep stable V15.3.1 unchanged.

**Go/no-go:** No promotion without reproducible gains beyond shadow overhead across external official classes, no invalid SAT/UNSAT outputs, independently checked GF2 proofs and an acceptable worst-case regression profile.
