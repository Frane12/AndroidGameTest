# DRNAS SCALE9 — native SAC and source-bound proof validation

**Status: experimental, on a branch.** `main` and the reference CDCL engine are not modified.

This component converts the SCALE8 source-only singleton arc consistency prototype into native C++17 and emits **an untrusted DRAT candidate**. An UNSAT result is accepted **only** when an independently pinned DRAT or VeriPB checker accepts its trace against the unchanged DIMACS source.

## What works

- Parses original DIMACS CNF, discovers disjoint positive demand domains and binary negative incompatibilities. No job-shop metadata or answer label is used by this structural engine.
- Implements directed arc consistency, singleton probing, and source-derived deletion-free RUP proof traces.
- Reuses a reversible *last-support cache* across different singleton trials, accepting a cached witness only when it is still active.
- Counts pairs with nested source-support sets (a possible temporal ordering signal; **not** an inferred machine identity or a sound energy inequality on its own).
- Optional `--temporal-priority` chooses high nested-support-degree domains first when current domain sizes tie.
- `--no-cache` and the default algorithm remain available for matched ablations.
- Leaves unsupported, satisfiable, or inconclusive cases `UNKNOWN`, **not** CDCL fallback.

## Compile and replay

```sh
g++ -std=c++17 -O3 -DNDEBUG -o drnas-sac9 research/sac9/sac9.cpp
./drnas-sac9 --cnf frozen-original.cnf --seconds 10 --cap 6000 \
  --drat candidate.drat --report native.json --temporal-priority

# REQUIRED: independent source-bound verification
drat-trim frozen-original.cnf candidate.drat -U

# Optional second standard checker, independent VeriPB 3.0.2:
python3 research/sac9/emit_veripb3.py \
  --cnf frozen-original.cnf --drat candidate.drat --out candidate.pbp
veripb --cnf frozen-original.cnf candidate.pbp
```

The native program prints `EMITTED_UNCHECKED` rather than claiming a verified UNSAT. Only external `s VERIFIED` (DRAT) or `s VERIFIED UNSATISFIABLE` (VeriPB 3.0.2) counts as proof acceptance. This does **not** prove a general O(n) complexity bound or universal SAT performance.

## Audited results

### FT06 original source

Frozen FT06 time-indexed source IDs:

- horizon 54 UNSAT: SHA256 `99910f35ed2401b2315618aa7ac23605ba876cfea79c3edadd1e468ef1c674ee`
- horizon 55 SAT: SHA256 `ec8a9bbb98f7742cedddf4c7430ce1185da7256427505b1b051bff1cbbb4dc20`

CI: https://github.com/Frane12/AndroidGameTest/actions/runs/45351259243

FT06 on its first C++-vs-Python CI test (3 repetitions, one CPU):

| FT06 | Native C++ | Python baseline | External DRAT |
|---|---:|---:|---:|
| 54 UNSAT | 0.019448 s | 0.159420 s | 0.091765 s |
| 55 UNKNOWN | 0.035335 s | 0.493471 s | not applicable |

**Safety and matched CDCL audit**: 9/9 mutated UNSAT CNFs accepted by independent DRAT and 9/9 SAT controls returned UNKNOWN, with independent VeriPB 3.0.2 also accepting the original native RUP proof. One-CPU, same-run median CDCL time 0.026553 s for 54 and 0.023242 s for 55. The structural producer is faster than CDCL for UNSAT 54, but **producer + external proof checking is slower**.

https://github.com/Frane12/AndroidGameTest/actions/runs/45352021557

**Temporal-priority ablation** (5 interleaved repetitions on the same CI runner):

| FT06 | Default native | Temporal priority | Proof bytes default → priority |
|---|---:|---:|---:|
| 54 UNSAT | 0.012537 s | 0.011984 s | 103520 → 79413 |
| 55 UNKNOWN | 0.023949 s | 0.023770 s | no UNSAT proofs |

Every candidate UNSAT proof was externally accepted. Native last-support caching by itself did not show a reliable runtime benefit on the first three-run test, despite reducing repeated scans.

https://github.com/Frane12/AndroidGameTest/actions/runs/45352185820

### New external-source-derived cases

Public Lawrence instances LA01/LA02 are fetched from `tamy0612/JSPLIB` and their exact upstream Git blob hashes are pinned. **These are four-job derived subproblems**, retaining all five operations of each selected job, and are **not** the complete published ten-job Lawrence benchmarks. They are development tests, not an untouched blind industrial holdout.

| Derived source | Deadline | CNF vars | CNF clauses | SAC9 | Native status | CP-SAT structured |
|---|---:|---:|---:|---:|---|---:|
| LA01 ×4 | 383 | 5140 | 308019 | 0.084623 s | externally checked UNSAT | 0.001813 s UNSAT |
| LA01 ×4 | 443 | 7540 | 604490 | 0.194941 s | UNKNOWN | 0.002939 s SAT |
| LA02 ×4 | 426 | 6210 | 417427 | 0.150337 s | externally checked UNSAT | 0.002259 s UNSAT |
| LA02 ×4 | 493 | 8890 | 810637 | 0.851875 s | UNKNOWN | 0.003079 s SAT |

Independent DRAT checking adds 0.125753 s for the LA01 UNSAT case and 0.181111 s for LA02 UNSAT. Large CP-SAT raw-CNF models exceeding the predeclared 400,000-clause construction gate were **skipped**, not counted as timeouts.

https://github.com/Frane12/AndroidGameTest/actions/runs/45351698314

## Mathematical and implementation limits

Finding a consistent support for every domain value across multiple constraints is a CSP consistency technique, not a novel NP-complete solution or new linear-time SAT algorithm. Exact general time complexity depends on domain size, number of directed arcs, singleton attempts, and support recovery. In particular, the present implementation has nested graph extraction and can require numerous complete AC propagation passes.

Nested support signatures alone do not prove operation duration, precedence, machine identity, or an energetic/cumulative inequality. Extending to recognized source-derived time intervals and independently certified energy cuts remains **open SCALE10 work**. The current module does not discover arbitrary raw-CNF scheduling encodings, and does not construct SAT solutions.

Record all `UNKNOWN` outcomes as structural research gaps. CDCL results are **separate comparison runs**, never success attributable to this strucural approach.

## GitHub evidence

- Native proof: https://github.com/Frane12/AndroidGameTest/actions/runs/45351259243
- Metamorphic DRAT + VeriPB + CDCL: https://github.com/Frane12/AndroidGameTest/actions/runs/45352021557
- Temporal ablation: https://github.com/Frane12/AndroidGameTest/actions/runs/45352185820
- Lawrence derived benchmark: https://github.com/Frane12/AndroidGameTest/actions/runs/45351698314
