# DRNAS LOCAL-HYBRID1 — source-verified local SAT construction in a single CDCL

**Status:** experimental. Both `main` and all frozen references are untouched.

## What is actually implemented

1. Source clause connectivity partitions a CNF into **independent connected components**. Four existing native construct methods (Horn, 2SAT, resource-matching, GF(2) parity) attempt models for each component. Models are combined only if every component is solved, and the **complete original CNF** is verified before SAT.
2. In any connected or disconnected mixed CNF, complete signed XOR patterns of width 2–4 are extracted from the original clauses. A bounded native constructor finds a satisfying assignment to this *XOR subset*. It is **only a reversible phase hint** to native CDCL; such a model is not presumed valid for the full CNF.
3. Up to six phase-hinted variables may be checked at the **root** by a bounded BCP failed-literal test. Only if the **opposite polarity leads to an actual BCP conflict** is the hinted unit learned. The clause is RUP by construction, appended to the original-CNF DRAT proof, and propagated by normal CDCL. A nonconflicting or budget-incomplete probe does nothing.
4. Otherwise plain CDCL continues. There is **no new UNSAT oracle**, no parallel solver or hidden assumption. Unknown source structures are never claimed SAT.
5. `--sat-local-ms 15` enables it. `--sat-local-shadow` discovers structures without applying hints or using constructed models. Default OFF. `SAT_LOCAL_STATS` includes source components, solved components, XOR patterns, hints, root RUP units and time.

This experiment does not prove a new complexity bound or general superiority over existing SAT methods. Exact connected-component splitting, XOR/Gaussian elimination and RUP are established techniques. Our combination is the engineering hypothesis to test.

## What passed

Run [LOCAL1 soundness](https://github.com/Frane12/AndroidGameTest/actions/runs/43733080357):
56 deterministic cases (24 closed mixed SAT, 24 connected XOR-plus-mixed SAT, 8 contradictory UNSAT); 168 OFF/SHADOW/ACTIVE runs with zero observed wrong SAT/UNSAT responses. The older standalone global constructor found SAT on 4/48 mixed SAT cases and returned UNKNOWN on 44/48. This **does not** establish speedups.

## Pinned E2E experiment

* **600 public SATLIB originals**, six families from [SAT-CONSTRUCT REAL600](https://github.com/Frane12/AndroidGameTest/actions/runs/43731136744), source manifest SHA-256 `69ecc2d2ac38157ca0175893dd164a659b0c042a5e6fc630f7af0260f85054a8`. Original SATLIB bytes and exact-clause-normalized DIMACS are both retained; model check uses original SATLIB clauses.
* **24 SAT2024 originals** from frozen CF7 REAL100, IDs 0,4,...,92. Fixed selection before LOCAL1 solver results; two repetitions (48 trial rows per arm).
* Six arms: `OFF`, `SHADOW`, `ACTIVE` **same new X59 executable**; pinned Kissat, CaDiCaL, CryptoMiniSat.
* Total **3,888 trials**, four shards, each sequential on one pinned logical CPU. SATLIB 2 s E2E cap; REAL24 3 s E2E cap; model/proof checker included. Timeout / UNKNOWN / unverified scores `2×cap` PAR2.
* Independent **full original-CNF SAT model** checker and **DRAT/FRAT UNSAT** checker. Verify RUP root-unit traces in the full original proof; never credit raw solver exit codes.
* Trial JSONL logs store exact source SHA, method telemetry, process CPU, peak RSS, certificate type, accepted verdict, E2E and PAR2. Workflow logs print bounded progress and summary rather than noisy per-trial records.
* Report both subsets separately, source-level wins/losses, changed solver behavior, worst regressions and per-family outcomes. This remains **retrospective**, not blind holdout; no automatic promotion.
