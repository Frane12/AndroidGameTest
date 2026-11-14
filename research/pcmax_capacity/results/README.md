# Local native PCMAX module validation, 2026-11-14

Frozen final CMake Release build; AMD EPYC 9V74, GCC 14.2.0, one logical CPU per process. Twenty original CNFs, three serial repetitions, 5-second cooperative discovery budget. Separate fresh-process independent checker for every native UNSAT. Caches were not flushed.

All 60 trials completed: **11 distinct UNSAT formulas independently certified in all three repetitions (33/33 positive trials)**. The nine catalog SAT controls returned UNKNOWN in all 27 trials. Ten positive formulas had expected UNSAT labels; m14 had catalog status unknown and a filename/author UNSAT claim. Its independently checked weighted capacity contradiction is 31 > 30.

This is a family-targeted developmental regression corpus, not a blind holdout: m14 coverage and two LP-degenerate cases informed implementation fixes. These results establish reproducibility on these inputs, not general SAT speedup. Structural certificates are pcmax-capacity-v1, not DRAT/LRAT.

Native time includes startup, input read/hash, discovery, native exact verification, durable certificate write and teardown. Total is native process wall time plus independent checker process wall time. Harness preparation, input hash prechecks and log parsing are excluded. Table values are medians of three repetitions.

| Original formula | Result | Integer demand > capacity | Native (s) | Checker (s) | Total (s) |
|---|---|---:|---:|---:|---:|
| m11-1517-6802-UNSAT | UNSAT checked 3/3 | 16 > 15 | 0.011158 | 0.041769 | 0.053343 |
| m12-8049-55035-SAT | UNKNOWN 3/3 | — | 3.737808 | — | 3.737808 |
| m13-1655-9604-UNSAT | UNSAT checked 3/3 | 105 > 104 | 0.136890 | 0.044910 | 0.181056 |
| m13-2011-12813-UNSAT | UNSAT checked 3/3 | 10000 > 9945 | 0.247673 | 0.052873 | 0.305497 |
| m13-2826-11437-UNSAT | UNSAT checked 3/3 | 10000 > 9971 | 0.058243 | 0.054957 | 0.113266 |
| m14-3640-14524-UNSAT | UNSAT checked 3/3 | 31 > 30 | 0.063589 | 0.061867 | 0.125456 |
| m15-2352-13561-SAT | UNKNOWN 3/3 | — | 0.316797 | — | 0.316797 |
| m19-10199-62102-UNSAT | UNSAT checked 3/3 | 1002 > 997 | 0.409415 | 0.152661 | 0.547046 |
| m19-2974-16501-UNSAT | UNSAT checked 3/3 | 9996 > 9895 | 0.086779 | 0.058600 | 0.145379 |
| m20-3726-23254-UNSAT | UNSAT checked 3/3 | 1002 > 988 | 0.229835 | 0.070435 | 0.300270 |
| m20-4135-27005-UNSAT | UNSAT checked 3/3 | 42 > 41 | 0.157238 | 0.072817 | 0.229997 |
| m23-6057-43824-SAT | UNKNOWN 3/3 | — | 0.705692 | — | 0.705692 |
| m24-17855-226744-SAT | UNKNOWN 3/3 | — | 5.146244 | — | 5.146244 |
| m24-24102-255206-SAT | UNKNOWN 3/3 | — | 5.160473 | — | 5.160473 |
| m26-6398-62377-UNSAT | UNSAT checked 3/3 | 10001 > 9927 | 0.510077 | 0.139679 | 0.649756 |
| m30-14113-167638-UNSAT | UNSAT checked 3/3 | 998 > 990 | 1.308988 | 0.396696 | 1.720180 |
| m35-32274-371389-SAT | UNKNOWN 3/3 | — | 5.252550 | — | 5.252550 |
| m37-28831-324346-SAT | UNKNOWN 3/3 | — | 5.208199 | — | 5.208199 |
| m40-26287-324155-SAT | UNKNOWN 3/3 | — | 5.207628 | — | 5.207628 |
| m43-38782-385402-SAT | UNKNOWN 3/3 | — | 5.283935 | — | 5.283935 |

Validation: 28/28 integration checks; 30 small CNFs (23 exhaustively SAT, 7 exhaustively UNSAT); 858 exact maximum/pattern comparisons; 30 canonical CLI checks; 12 independently checked synthetic certificates. One deliberately constructed fractional-gap UNSAT has no capacity certificate and correctly remains UNKNOWN.

Frozen identities:

```text
native binary SHA256 d798625390434d5e29abec450feea43408f5cb58f152651b83a72caa806be19b
checker SHA256       08ee88608f173b0a08bb053f88f40a120b10b675e019d9205296aed007701b0f
header SHA256        1a319350ca982b2344d1a7f3a1e7773d7380cd0fd85ac354cc9fd64f9d969a99
CDCL source SHA256   68ddb1371dc5eea634b0ba8d472abd5debea76229eb3997b92b9acf561aee474
```

Full timings and source hashes: [original20 JSON](original20-local-20261114.json). Integration and math records are in the adjacent JSON files. Replay instructions are in the repository root README_PCMAX.md. GitHub Actions regenerates certificates and stores them with the binaries and original inputs in its run artifact.
