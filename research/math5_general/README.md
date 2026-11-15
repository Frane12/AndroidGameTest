# MATH5 GENERAL100

General evaluation of the latest frozen MATH5 build, using all 100 original SAT2024 CNFs from CF7 REAL100. No source is added, dropped, or replaced based on outcomes. These are previously exposed formulas, so this is a retrospective general test, not a new blind holdout. The 100 normalized filename groups are heuristic groups, not proof of 100 independent problem families. The earlier train/validation/holdout labels are not reused: all 100 formulas are evaluation cases, with no learning or promotion.

Six arms: MATH5, MATH4, the identical MATH5 executable with the mathematical module OFF, Kissat 4.0.4, CaDiCaL 3.0.1, and CryptoMiniSat 5.11.15. There are three timing repetitions per source and arm, 1,800 attempts total. Repetitions use the same solver settings and are not independent formulas or randomized solver seeds. The arms run sequentially on one pinned logical CPU per runner. Ten shards, at most five concurrent runners. Each attempt has 10 seconds total for the solver and independent checker; timeout, unverified answer, or resource failure costs 20 seconds. Time includes process startup, parsing and proof checking, and excludes artifact hashing/archival.

The MATH5/MATH4 binaries and structural checkers are unchanged from BLIND30, commit `517f5e3cacea46e6ab5efb4955fd354354d0bc89`; solver implementation commit `8614545baee7e9c6f2c0427406405be13c2ff712`. The MATH5 mathematical budget is 750 ms. No external solver is launched by MATH5. Full binary, shared-library, checker and original-input SHA-256 values are fixed before evaluation. `prespec.json` is authoritative. Main and all earlier frozen experiments remain unchanged.

Reports retain three explicit scoring columns:

* Primary verified E2E PAR2 accepts checked SAT models and checked DRAT, FRAT or structural UNSAT certificates.
* Standard MODEL/DRAT/FRAT PAR2 penalizes structural-only UNSAT; CryptoMiniSat FRAT is independently verified by pinned `frat-rs elab -v` within the same time cap.
* Exact legacy MODEL/DRAT-only PAR2 is retained for continuity and additionally excludes FRAT. It must not be used alone to rank CryptoMiniSat against DRAT-producing solvers.

Independent SAT checking scans every original clause. Known SAT/UNSAT controls exercise all six arms, and a known count instance checks the structural proof path plus rejection of an altered certificate. Critical answer/proof failures make the final job fail after retaining evidence. The report refuses incomplete or duplicated result matrices, preserves per-source wins/losses and CPU/RSS telemetry, and bootstraps sources rather than repetitions. The 10% improvement threshold is descriptive on this retrospective suite, not a prospective promotion gate or official competition ranking.

Frozen dependencies: MATH5 run `43664639093`, source run `43613581688`, CMS/FRAT run `43368689724`. All original CNFs, manifests, logs, emitted certificates and complete verified proofs are retained as Actions artifacts for 60 days. Incomplete proof scratch is removed only after recording status and size.
