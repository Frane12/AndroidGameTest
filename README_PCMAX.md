# Optional native PCMAX capacity guard

`drnas-pcmax` adds bounded structural capacity discovery before the existing X5
CDCL search. It runs in the same process and does not invoke another solver,
Python, or a subprocess. The guard is off unless `--pcmax-capacity` or
`--pcmax-only` is supplied. Unsupported structure, an exhausted discovery
budget, or failure to find a certificate falls back to CDCL.

The module only reports structural UNSAT after its exact checks succeed and a
complete certificate has been written and flushed durably. This certificate
is a separate mathematical proof format, not a DRAT proof. Supplying `--proof`
disables the guard and retains the original CDCL proof writer.
`--pcmax-only --proof ...` is an error, before either output is opened.

## Build

A C++20 compiler, CMake 3.16+, and OpenSSL Crypto development files are required
for `drnas-pcmax`. Existing targets and `drnas-pcmax-base` do not require OpenSSL.

```sh
cmake -S . -B build
cmake --build build --target drnas-pcmax drnas-pcmax-base -j2
```

The base target compiles the same `src/drnas_x5.cpp` without
`DRNAS_PCMAX_MODULE`. Existing target definitions and the CDCL algorithm are
unchanged. If OpenSSL is unavailable, CMake skips the optional module target.

Equivalent direct builds on Linux:

```sh
g++ -std=c++20 -O3 -DNDEBUG src/drnas_x5.cpp -o drnas-pcmax-base
g++ -std=c++20 -O3 -DNDEBUG -DDRNAS_PCMAX_MODULE src/drnas_x5.cpp -lcrypto -o drnas-pcmax
```

## Run and verify

Use core mode for timing comparisons. Each certificate path must be new:
existing files, hardlinks, and symlinks are never overwritten. Parent directory
components must not be symlinks. The parent directory must already exist.

```sh
./build/drnas-pcmax instance.cnf --mode core --time 5 \
  --pcmax-capacity --pcmax-budget-ms 250 \
  --pcmax-certificate instance.capacity.json
python3 research/pcmax_capacity/check_capacity.py \
  instance.cnf instance.capacity.json
```

`--pcmax-only` enables discovery and returns `s UNKNOWN` instead of invoking
CDCL when discovery cannot produce a saved, verified certificate. It is useful
for evaluating the guard by itself. Without `--pcmax-certificate`, a discovered
witness is reported as `certificate_path_required` and cannot produce
structural UNSAT. Certificate write failures return error code 1 and cannot
produce `s UNSATISFIABLE`.

`c PCMAX_CAPACITY {...}` records the reason, discovery budget, elapsed time,
group and machine counts, demand and capacity, the input SHA256, and the saved
certificate path on success. Exit codes remain 10 for SAT, 20 for UNSAT,
0 for UNKNOWN, and 1 for errors. A structural hit returns before CDCL statistics
or transition output; use this telemetry for its cost.

The default discovery budget is 250 ms. `--pcmax-budget-ms 0` skips discovery.
Valid budget values range from 0 through 86,400,000 ms (one day).
The total `--time` deadline starts before reading the source, includes source
hashing and preprocessing, and clamps the module budget to the time remaining.
As in the base solver, `--time 0` means no overall deadline. Filesystem calls
and other individual operations cannot be preempted by this cooperative limit.

The original 1-based DIMACS clauses are retained only when the guard is active
and the header declares at most 200,000 variables and 1,000,000 clauses. Copying
stops and the copy is released if the source exceeds 10,000,000 literals.
These limits skip the module while preserving normal CDCL fallback. SHA256 is
computed from exact source bytes during parsing, including comments, CRLF,
and the presence or absence of a final newline.
Discovery also rejects any original clause wider than 1,024 literals before
copying or sorting it internally, and skips unsupported BDD structures.
The certificate checker accepts ASCII DIMACS with full-line `c` comments.
Other comment syntax supported by the CDCL parser, including `%` and inline
comments, or non-ASCII bytes, disables the module and retains CDCL fallback.
In discovery-only mode, an oversized valid header returns `UNKNOWN` before
allocating CDCL variable arrays; exceeding the literal limit also returns
immediately. These early results omit the source hash because reading stopped.

The independent checker uses Python's standard library and verifies the
certificate against the original CNF. It does not import the native discovery
implementation. Passing a finite regression suite is evidence for that suite;
the capacity test is incomplete and is not a general scheduling solver.

Run the portable integration checks against the CMake targets:

```sh
python3 research/pcmax_capacity/integration_tests.py \
  --binary build/drnas-pcmax --base-binary build/drnas-pcmax-base \
  --report build/pcmax-integration-results.json
```

The tests create their own scheduling fixtures and temporary directory. They
cover independent certificate checks, exact source hashes, CDCL fallback,
DRAT gating, path aliases and symlinks, write failures, and resource budgets.
`--work-dir` keeps test files in a chosen directory; `--cpu` selects an available
CPU instead of the first CPU allowed to the test process.

The floating-point simplex proposal routine follows the Stanford Notebook
implementation. Its MIT license, attribution, pinned source copies, and
provenance are in [third_party/stanford-simplex](third_party/stanford-simplex).
The exact certificate checks do not trust floating-point LP results.

## Capacity rule and discovery scope

For disjoint job groups, choose nonnegative integer weights `w[j]`. Each
positive-weight group must have all its assignment literals covered by the
extracted machines. For each machine, compute the largest accepted assignment
weight by exact dynamic programming through its ordered BDD, including skipped
levels. If `sum(w) > sum(machine_maximum_weight)`, the original CNF is UNSAT.
Every transition and required unit is checked against original clauses.

Groups with an uncovered assignment literal are forced to weight zero. This
lets a fully covered subset prove a contradiction without assuming anything
about the uncovered groups. The m14 instance uses this extension: weighted
demand 31 exceeds capacity 30, using 20 positive-weight job groups. These are
weights, not 31 distinct jobs. Extraction is conservative and does not support
arbitrary PCMAX encodings or all UNSAT instances.

## Reproduce the original20 experiment

The [frozen local report](research/pcmax_capacity/results/README.md) records
11 independently certified UNSAT formulas in all three repetitions and nine
SAT-labeled controls returning UNKNOWN. It includes complete timing JSON,
source hashes, integration checks and mathematical oracle checks.

`sources20.json` pins original CNF bytes by SHA256 and records download URLs.
Expected labels are read only by the benchmark harness; the native module
receives the original CNF. The m14 entry has catalog status `unknown` and a
filename/author claim of UNSAT, so it is recorded as expected `UNKNOWN` rather
than pretending it already had an independently confirmed catalog result.

```sh
python3 research/pcmax_capacity/benchmark.py \
  --binary build/drnas-pcmax --inputs original-cnfs \
  --output results/original20 --budget-ms 5000 --repetitions 3 --download
```

Use a fresh output directory for each experiment. The harness pins itself and
each child to one logical CPU and runs cases serially. Every positive result
is checked in a separate fresh Python process. It reports native wall time,
checker wall time, their sum, process CPU time, and peak RSS. Native wall time
includes process startup, CNF reading/hashing, discovery, native verification,
durable certificate writing, and teardown. Inputs are not cache-flushed.

The 5-second discovery budget is an experimental setting, not the default
250 ms integration setting. Unknown results may consume this budget. Results
from this targeted family test are not a general SAT speed comparison and
must not be entered as DRAT/LRAT-verified PAR2 scores.
