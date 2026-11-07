# DRNAS New Horizon SAT R5 — real SAT2026 native-speed first contact

## Primary question

Is any speed gain visible in **native CDCL search** on official SAT
Competition 2026 original CNFs, beyond millisecond-class Python
preprocessing on synthetics?

R4b/R4d proved repeatable gains on easy source-exact XOR and small
2SAT generator families, but 12 previously reused hard real originals
all timed out. This is *not* a broad SAT solver advantage.

## New six-arm study, fixed before timing

- All arms receive the **identical original GBD main_2026 CNF** byte-for-byte.
- Same CaDiCaL 2.1 C++ binary SHA from prior New Horizon builds.
- Six exact SAT methods:
  1. native default CaDiCaL;
  2. native CaDiCaL "sat" configuration;
  3. native CaDiCaL "unsat" configuration;
  4. cheap source-only header+first96-clause profile router;
  5. frozen proof-gated R4b;
  6. frozen proof-gated R4d.
- Router's source-only score affects **profile choice only**, never a SAT
  or UNSAT answer. Conservative abstention defaults to native CaDiCaL.
- True solver wall time includes profile selection, process launch,
  source verification, and SAT model check.
- All SAT assignments are checked against the **unchanged original CNF**.
- Native UNSAT results currently lack an independently replayed LRAT/FRAT
  proof; this limitation is not covered up.

## New, but not globally certified "blind"

Source collection is fixed *before* any R5 timing. GBD 2026 metadata
and original CNF are downloaded fresh. We exclude prior IDs and original
SHA-256 hashes from enumerated ledgers:
- R152 known source IDs, including R115/R32p IDs.
- R106 original SHA manifest.
- Pinned R183 twelve-source external SAT CNF frozen manifest.
This is not all conceivable previously tested instances, so we call
this "prospective / first contact relative to enumerated ledgers",
not globally unseen.

No solver score, known SAT status, or filename influences eligibility.
Selection depends on GBD track, source family, size bounds and original
SHA. All catalog failures, skipped sources and original hashes are
published as artifacts. Source count is 12–16; if fewer than 12 new
external originals pass filters, **the test aborts**, not padded with
previously seen or generated examples.

## Budget and audit

- 12–16 new GBD SAT Competition 2026 original CNFs.
- Original byte cap 2.5 MB; declared n<=20k, clauses<=170k.
- Six arms × two repeats × eight shards, 8-second per-attempt cap,
  **144–192 paired runs**.
- Original sources and identical CaDiCaL C++ executable SHA-pinned
  before any timed run.
- Pre-committed shuffled arm order within source/repeat.
- Audit refuses missing arms, mismatched SHA, incomplete trials, or
  contradictory successful SAT/UNSAT answers on the same source.
- PAR2 = 2×cap for timeout.
- At 8-second caps many real 2026 tasks may time out identically;
  that demonstrates no speed gain and is not interpreted otherwise.

## Hardware and scientific limitations

- Runner timings can be noisy even with paired order.
- A native profile win on 12–16 family-conditioned originals does not
  imply superiority across the official SAT 2026 main benchmark.
- Source family selection is conditional and not representative.
- Three profiles are existing CaDiCaL configurations. Any gains from
  them are configuration/selection effects, NOT proof of a fundamentally
  new CDCL algorithm.
- This is a research experiment in an isolated branch and draft PR,
  not a release or production upgrade.

## Files

- research/new_horizon_r5_real_native.py
- .github/workflows/drnas-new-horizon-r5-real-native.yml

Prior pinned native binary SHA:
d3e17f52ee77be0df090da28710a10ba9543576e8ca12e9b2555288a02a077ed.
Reference original R4d audit GitHub run 42328083835.
