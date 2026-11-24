# DRNAS PCMAX SCALE4 native Hall guard — experimental

Optional structural UNSAT detector for disjoint positive assignment clauses and
source-proven pairwise mutex cliques, with Hall witnesses via Hopcroft–Karp.
This is a known mathematical method adapted to the existing DRNAS CNF core;
**not** a new complexity class or proof of general O(n) SAT.

## Usage (build on Linux)

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --target drnas-pcmax -j2
./build/drnas-pcmax path/to/instance.cnf --mode core --time 5 \
  --pcmax-hall-only --pcmax-hall-budget-ms 1500 \
  --pcmax-certificate path/to/new-certificate.json
python3 research/pcmax_hall/verify_hall.py path/to/instance.cnf path/to/new-certificate.json
python3 research/pcmax_hall/smoke_test.py --binary build/drnas-pcmax
```

The certificate target **must not already exist**. `--pcmax-hall-only` reports
`UNKNOWN` without any CDCL search on failure or unsupported structure.
`--pcmax-hall` enables the source-bound structural guard and otherwise permits
the original solver search. Research protocol treats fallback as a diagnostic
failure to address, never as proof that the structural method succeeded.
The original `--pcmax-capacity` rule remains separately available.

The guard is OFF by default; `--proof` disables ordinary Hall discovery and
`--pcmax-hall-only --proof` is an error. No changes to frozen CDCL logic.

## Proof and limitations

A certificate lists source clause indices requiring at least one true literal,
and source-proven disjoint mutex cliques covering their selectors, such that
**number of selected clauses > number of slot cliques**. The independent
checker re-reads the exact source CNF and checks source SHA-256, distinct
assignment groups, every pairwise mutex clause and the deficit. There is no
assumption about a source filename's expected SAT label.

- The certificate is **not a standard VeriPB, DRAT or LRAT proof**. Export to
  independently standardized proof formats remains an open task.
- Conservative limits include 200,000 CNF variables, 1,000,000 CNF clauses,
  10 million literals, 10,000 job groups, 40,000 selectors and 2 million
  checked clique pairs. Unsupported instances return UNKNOWN.
- Matching is polynomial on the recognized bipartite structure, but this is
  **not** an O(n) theorem for arbitrary raw CNF or integrated scheduling.
- Development, fresh-seeded synthetic and metamorphic tests are not a genuine
  external blind industrial holdout.
- Compare E2E solver wall time on the same CPU and treat time limits as
  censored observations, not measured time-to-solution.
