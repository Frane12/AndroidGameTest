# DRNAS ARG3-SAT1: constructive 3-label directed graph SAT

**Experimental and post-discovery on original SAT Competition 2025 source.**
This is a sound SAT witness construction method, not a polynomial general SAT
algorithm and not evidence of an unseen official-source win.

## Grounded original

GBD: b9ed6fd14f4fc969ec966a4b54c36872
Original decompressed DIMACS SHA256:
c46261a9a52b8080ddc040f6b58e7a48eb651993ff6f67ae78830848b8e14fb2
960 variables; 62,749 clauses:
61,772 binary; 320 exactly-one ternary; 657 long.
There are 320 three-label argument groups, 30,406 directed attacks,
and 17 extra positive clauses. Of these 17, one rules out the empty
selected set, and 16 exclude particular complete/stable extensions.

For argument i there are three labels (IN, OUT, UNDEC).
The original source clauses strictly encode:
- Exactly one label per argument, via one positive triple and 3 mutexes.
- For each attack j -> i: IN(j) implies OUT(i), IN(i) implies OUT(j).
- OUT(i) implies some attacker is IN.
- All attackers OUT implies i IN.
The detector matches these source signatures including attacker-set
equality; unsupported/extra sources are rejected without any claim.

A *stable extension* S is conflict-free and attacks every argument
outside S. A candidate full assignment is then IN for S, OUT for
vertices attacked by S, and UNDEC for the remainder (zero for stable).
The full candidate is accepted as SAT ONLY if an independent complete
scan satisfies every clause of the untouched original CNF.

ARG3-SAT1 searches for stable extensions using randomized greedy
independent out-dominating sets (fixed RNG seed 17, bounded samples and
a monotonic wall-time budget). Blocked extensions are skipped. The
graph search is heuristic; failure means UNKNOWN, never UNSAT.
The X59 native CDCL engine is the same-process exact fallback.
This type of Dung argumentation labeling is established prior art.

## Compiling and running

In experimental branch:
  g++ -O3 -std=c++20 -DNDEBUG src/drnas_x59.cpp -o build/drnas-sat-native-x59
  build/drnas-sat-native-x59 ORIGINAL.cnf --mode core --time 8 --arg3-ms 50 --stats

Default ARG3 is OFF. The option --arg3-ms 15, 50 or 100 requests
the entire source-copy, graph recognition and model-construction wall
budget in milliseconds. No second solver process or CPU core.

## Results

Diagnostic ablation (13 modes, 2 repeats):
https://github.com/Frane12/AndroidGameTest/actions/runs/43712045656

X59 BASE did not finish within 8 seconds (0/2).
X59 without clause minimization plus dynamic restarts returned verified
SAT in 5.5663 and 5.5679 seconds. Pinned CaDiCaL returned verified
SAT in 0.2547 and 0.2591 seconds.

ARG3 native same-process result and controls:
https://github.com/Frane12/AndroidGameTest/actions/runs/43713171125

ARG3_15, ARG3_50, ARG3_100, ARG3_PLUS_MATH all returned verified SAT
2/2 on this original. Median E2E (including solver startup and
independent original CNF witness scanning) for ARG3_50 was 0.065662s,
versus CaDiCaL 0.248566s and X59 MIN_OFF_RESTART 4.805803s.
The speed ratio to CaDiCaL on this one known source is about 3.8x.
Do NOT treat a timeout-censored ratio against base X59 as a precise
equal-completion speedup.

In three independent original-source control calls, the graph guard
found one complete 11-IN / 309-OUT / 0-UNDEC witness after exactly 2,282
candidate iterations, including two blocked stable candidates.
Graph recognizer+search+candidate check cost about 9.4-10.1 ms within
each control invocation. All 62,749 original clauses passed.
12 generated graph controls, 10 unrelated negative-source guard cases,
and 3 original-source controls were checked; no incorrect SAT verdict.

## Scientific limits and promotion gate

The source was inspected BEFORE development and is a development test;
the semantics were reconstructed from its CNF structure. No worldwide
novelty or out-of-sample performance is established by this result.
Retain the complete original SHA, first-match rule, full source witness
and source-level paired end-to-end timings. Bench against all other
frozen originals and new SHA-disjoint true unseen originals of the
same and heterogeneous families. Check SAT models independently and
UNSAT with DRAT/LRAT. Gate activation by cheap source recognition and
empirically bounded overhead, not a filename, source hash or oracle.
