# MATH5: exact-one to parity bridge (experimental)

Implemented and tested locally on 2026-11-15. Parent MATH4 commit:
`b8829b29183bb5e38756ff18cc99b2b97f09bacb`.
No changes to main, frozen references, or any existing solver source. No new
GitHub Actions benchmark was started for this experiment.

## Result: one additional original source refuted

The unchanged original24 inputs from run **43646454422**, artifact **14133712771**,
were screened with MATH4 and MATH5 guards, one logical CPU, one repetition,
750 ms guard budget. These are retrospective/development inputs, NOT a blind holdout.

- MATH4: certified originals **1, 7, 18, 19**.
- MATH5: certified originals **1, 7, 18, 19, 21**.
- No previously certified source was lost in this screen.
- Screen total wall times are not a general solver speed/PAR2 result.

New source: **count, ID 21**, GBD ID `727ebce936c010888c7f71f00885e643`.
It has 300 variables and 6,925 clauses. Exact raw-CNF SHA-256:
`23702be6f54e7c6722880ea44f26ce4c7ca01791631cdfc8bce47c18615477c6`.
Source ZIP SHA-256:
`44ecbad24dded4352bb07c9f13752e43bc62b70f9b81187f8bf9b280aa809d36`.

## What the proof actually says

The source contains 25 positive at-least-one clauses, each of width 24.
All 6,900 pairwise exclusion clauses needed for these groups are present.
Therefore each group contains **exactly one** true variable.
Every one of the 300 variables occurs in exactly two selected groups.
Summing the 25 equations gives:

`2 * (x_1 + ... + x_300) = 25`.

The left side is even and the right side is odd: UNSAT.
The 2,408-byte certificate uses **25 exact-one rows, zero pre-existing XOR rows,
and zero units**. This is the exact-one-to-GF(2) path, not an explicit XOR-plus-Hall
input. Overlapping groups are legitimate here; disjointness is not assumed.

The mathematical parity principle is established. The result is a new proof
path in DRNAS, NOT a claim of a new theorem or worldwide algorithmic priority.

## Focused full-solver comparison after discovery

One logical CPU; same unchanged count21 CNF; 5 seconds per trial; two repetitions;
reference binaries from the pinned original24 artifact; proof logging enabled.
MATH4 and MATH5 were compiled with the same compiler and flags.

| Arm | Trial 1 | Trial 2 | Verified |
|---|---:|---:|---:|
| MATH5, solver + fresh checker process | 0.965797 s | 0.893204 s | 2/2 |
| MATH4 | TIMEOUT at 5 s | TIMEOUT at 5 s | 0/2 |
| Kissat 4.0.4 | TIMEOUT at 5 s | TIMEOUT at 5 s | 0/2 |
| CaDiCaL | TIMEOUT at 5 s | TIMEOUT at 5 s | 0/2 |

MATH5 solver alone took 0.047061 s and 0.023217 s. The table deliberately includes
the fresh Python checker process startup and checking time. Do not present the
solver-only numbers as full certified end-to-end times.

This is a targeted, post-discovery comparison, not a blind general benchmark.
Custom structural certificates are **not DRAT/LRAT**. Under the strict DRAT-only
score MATH5 receives the unsolved penalty, just as documented in the earlier protocol.

## Controls

288 designed/fuzz formulas: 181 SAT controls and 107 UNSAT cases.
MATH4 guard certified 7; MATH5 guard certified 73. The 64 deliberately constructed
mixed exact-one/XOR UNSAT cases were all certified by MATH5 and none by MATH4's
guard. No false UNSAT on the 181 SAT controls; 205 malformed proof/source variants
were rejected. The general small random CNFs were exhaustively checked.

On original count21: 16 signed variable/clauses permutations also certified.
A separate certificate-free counting audit reproduced the even/odd contradiction.
Removing a critical mutex or an ALO clause gives two explicitly checked SAT
assignments; MATH5 guard correctly returns UNKNOWN for both changed inputs.
Three additional corrupted-original/proof checks reject.

## Build and reproduce

Requires C++20, OpenSSL development headers and Python standard library.

```sh
python3 research/math5/build.py
python3 research/math5/test_bridge.py --binary build/drnas-math5 --baseline build/drnas-math4-local --out results/math5-fixtures-new
```

`build.py` checks the exact MATH4 source hashes, generates the experimental
header and full solver under `build/math5-src/`, and builds the same-process
native solver. It does not edit original sources. `--math5` is opt-in;
unsupported input or exhausted budget falls through to existing HALL3/CF7.
The source algebra stage keeps MATH4's bounded budget and size gates.

For any generated MATH5 certificate:

```sh
build/drnas-math5 ORIGINAL.cnf --mode core --time 5 --math5 --pcmax-budget-ms 750 --pcmax-certificate proof.json
python3 research/math5/check_math5.py ORIGINAL.cnf proof.json
```

Extract `math4-frozen.tgz` from artifact 14133712771 into a directory called
`frozen`. Original24 screening and the focused test scripts accept that directory.
Read their `--help` flags. Every result includes hashes and explicit proof type.

## Limits

This is not a complete SAT algorithm or a new general Hall-plus-XOR theory.
Only source-supported exact-one constraints, complete source XOR blocks, and
independently re-derived root units are accepted. There is no inference from an
AMO constraint alone. Broad held-out performance and standard proof export remain
untested. No automatic promotion is justified by these local tests.

Related prior work: Reeves, Heule, Bryant, *From Clauses to Klauses*, CAV 2024,
DOI `10.1007/978-3-031-65627-9_6`; native cardinality extraction is not claimed new.
