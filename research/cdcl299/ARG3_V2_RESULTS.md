# DRNAS ARG3-V2 — permutation-invariant original-CNF SAT construction

Research date: 2026-11-15. Experimental native C++ solver branch; main untouched.
Source GBD: b9ed6fd14f4fc969ec966a4b54c36872.
Original DIMACS SHA256:
c46261a9a52b8080ddc040f6b58e7a48eb651993ff6f67ae78830848b8e14fb2

## Original formula and reconstructed semantics

960 Boolean variables representing 320 argument groups, each with
three disjoint states: IN, OUT, UNDEC. Exactly-one 3-CNF group,
binary source implications and 640 wide graph-relation clauses encode
30,406 directed attacks. The remaining 17 wide positive constraints
exclude the empty extension and 16 previously found stable extensions.
SAT can be witnessed by a new conflict-free, out-dominating set.

Source clauses: 61,772 binary, 320 ternary, 657 long.
Native algorithm:
- Detect source-backed complete three-label graph schema.
- Reconstruct directed attackers, graph exclusion and blocked extensions.
- Bounded randomized search for an independent out-dominating set.
- Turn candidate into a full source Boolean model.
- Verify *every original CNF clause* independently.
- If no model is found, return UNKNOWN and let standard X59 CDCL continue.
No separate solver process, portfolio, or proof-free UNSAT verdict is used.
Formal argumentation/stable-extension reasoning and greedy randomized search
are known prior art; this is an experimental implementation of these ideas.

## Results on the already-known original (not blind)

13-arm development diagnostic:
https://github.com/Frane12/AndroidGameTest/actions/runs/43712045656

Original X59 base: 0/2 solved at 8s cap.
X59 with minimization disabled and dynamic restarts: 2/2 SAT verified,
median 5.567s. CaDiCaL median 0.257s.

ARG3 original model and native budget ablation:
https://github.com/Frane12/AndroidGameTest/actions/runs/43713171125

Native ARG3 50ms, same-process X59: 2/2 verified SAT,
median E2E 0.065662s; CaDiCaL 2/2, 0.248566s.
The ratio to CaDiCaL on this one developed source is ~3.79x.
All 62,749 original clauses were validated.
The native source recognizer found the graph with 320 groups,
30,406 directed edges and 17 blocker clauses. It rejected two
already-blocked stable models and returned a third, full SAT witness
after 2,282 candidate iterations. Observed structural work was
roughly 9.4-10.1ms in the first native run.

Frozen 19 original SAT2025 source regression (same X59 executable,
OFF vs ARG3 50ms, two repetitions per source, strict DRAT validation):
https://github.com/Frane12/AndroidGameTest/actions/runs/43713338667

| Arm | Solved / 38 | SAT | UNSAT | Sum certified E2E PAR2 s |
|---|---:|---:|---:|---:|
| X59 OFF | 8 | 4 | 4 | 480.461658 |
| X59 + ARG3 | 10 | 6 | 4 | 448.689014 |

The PAR2 difference is 31.772644s, or ~6.61% relative reduction.
Paired per source: 3 tiny/wide wins, one tiny loss, 15 ties; nearly
all substantive benefit is from the exact known source #299.
This is a negative generalization signal outside the new class,
NOT a blind improvement claim.

## Additional invariant-source validation

The initial constructor required contiguous IN/OUT/UNDEC variable groups.
V2 (this branch) reconstructs the groups from original positive
exactly-one triple clauses and infers label roles from mixed-binary
literal signs, then internally canonicalizes variable labels.
It never uses the original filename, SHA, variable numbers or known
SAT assignment to choose a candidate.

Five independently permuted CNFs from the same original, with
different SHA256 values, were tested:
- 3 arbitrary variable renumberings while retaining clause order;
- 2 arbitrary variable renumberings plus randomized clause/literal order.
V2 returned a *fully verified SAT model* on all five (5/5), with
no false SAT results. Native role recovery and search lasted
roughly 17-37ms across these permutation controls.
Run: https://github.com/Frane12/AndroidGameTest/actions/runs/43714089214

These five permutations are not five independent SAT families or
previously unseen competition problems. They certify representation
robustness on the *same logical formula*, not broad generalization.

## Safety and future science

Default ARG3 is OFF; --arg3-ms N opt-in, with source-size guard,
monotonic budget, full original model verification and CDCL fallback.
UNSAT proof generation is left to the existing CDCL core and
independently certified DRAT/LRAT benchmark pipeline.

Do not promote from the post-discovery source or its renamings.
To verify genuine transfer, preregister and freeze new original
competition CNFs with disjoint source SHA *before* solver outcomes,
compare with Kissat, CaDiCaL and CryptoMiniSat and include
negative controls and a paired source-level PAR2 confidence interval.
