# R28 native DIRECT medium benchmark

Frozen algorithm base: 630253acff48e9c78795f760d1fedda29625ff8e. No solver edits.

12 original SAT2024 CNFs from the frozen MATH14 real24 manifest (run 43161813420), sorted by compressed bytes and filename, positions 1,3,...,23 (zero-based). This complements the previous real12 cohort without selecting by outcomes. Previously used parent data: retrospective, not blind. Medium refers to study scope, not established runtime difficulty.

Five arms: R28_NATIVE_DIRECT, R153_EXACT, Kissat 4.0.4, CaDiCaL 3.0.1, and single-thread CryptoMiniSat. Two seeds (17,29), 60 seconds end-to-end per attempt: 120 attempts. Three independent runners, four formulas each. All arms for a formula run serially pinned to one logical CPU on the same runner. Order is reproducibly shuffled. No 180s followup. Maximum timed solver work is 40 minutes per shard, plus setup and verification.

DIRECT uses its existing online within-formula learner; no context-memory warm start or cross-formula training is introduced. R153_EXACT is exact GF2 only with abstention, not a complete general solver. Both UNKNOWN and timeout receive 120 seconds PAR2. SAT models are checked against the original CNF; source-based GF2/PHP certificates are independently checked. Generic UNSAT remains explicitly unverified. Both reported and verified PAR2, verified counts, unique solved sources, paired ratios, regressions, and per-shard totals are recorded. Verification cost is separate from timed solver launch/parse/search.

Original hashes, binary hashes, CMS version/hash, complete pair coverage, duplicates, and contradictory SAT/UNSAT claims are checked. Compact witnesses/certificates only, no large general proof files. No automatic promotion; at least 30% lower PAR2 against the best full reference on a subsequent unseen general holdout is required.
