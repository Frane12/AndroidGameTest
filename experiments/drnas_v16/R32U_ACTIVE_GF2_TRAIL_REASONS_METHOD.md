# R32u: certified live XOR implication with native CNF reasons

**Started:** 2026-11-03  
**Implemented in pinned upstream Kissat:** `8af8e56f174b778aef3aa45af9f739b2a5f492c2`  
**Source patch:** `patch_r32u_live_xor_reasons.py`  
**Local deterministic model test:** `r32u_random_original_model_test.py`  
**Real-source benchmark:** `r32u_native_active_xor_benchmark.py`  
**Validated pinned-build preflight:** https://github.com/Frane12/AndroidGameTest/actions/runs/41681988821  
**Live five-official-paired benchmark:** https://github.com/Frane12/AndroidGameTest/actions/runs/41683024261

## Scientific goal

Prior R32t achieved **103 certified additional XOR relations and 932
entailed source clauses**, but no proven solve-time improvement on 17
official 2026 mixed SAT/XOR formulas (15/17 120s timeouts with either
native baseline or source-CNF augmentation). R32u tests a more
demand-sensitive intervention: **conditional XOR implications only when
almost all variables of an entailed parity relation are assigned on
the actual native CDCL trail**.

For an original-CNF-entailed parity row

`x1 xor x2 xor ... xor xk = rhs`

with exactly one unassigned variable `xj`, the required value is

`xj = rhs xor (xor of all previously assigned xi)`.

The native engine attaches a reason clause

`(opposite(x1) OR ... OR opposite(xk, except xj) OR required(xj))`.

That clause **is entailed by the full parity equation regardless of the
branch**, not merely by the temporary assignments. The normal Kissat
assignment APIs reference this clause. Therefore future CDCL conflict
analysis and backtracking retain a concrete valid reason instead of
receiving an unexplained forced literal.

## Strict provenance of XOR equations

1. Capture the original DIMACS through R32b *before* any learned clause
   is available; identify only complete parity block encodings from
   original clauses.
2. R32u's first iteration **refuses hidden/resolvent-reconstructed XOR**
   groups to simplify independent original proof checking.
3. Compute bounded RREF over those sound equations, retaining only
   derived parity relations of width 2 through 5, not present as
   original complete equations.
4. Freeze up to 64 rows per original source, deterministic ordering.
   Independently reproduce RREF and verify every listed row from the
   original complete parity clauses. For the three source diagnostics:
   `12535b326...`: **64/64 matched**,
   `7db30d12...`: **31/31 matched**,
   `b76b9699...`: **8/8 matched**.
5. At the native CDCL search loop, after ordinary watched-literal
   propagation, run one bounded row scan at most every 16th new
   decision. Skip any row with more than one unassigned variable,
   eliminated or unmapped source variables, or unsafe source guards.
6. If exactly one variable is missing and active mode is enabled,
   allocate a **native CNF clause as reason** and assign via Kissat's
   `kissat_assign_binary` or `kissat_assign_reference`.
   Resume native watched-literal Boolean propagation before a new
   decision. No independent SAT subprocess or search watchdog.
7. Budget: at most 256 newly attached reason clauses per attempt.
   Include read-only per-source statistics and periodic logs.

## Reproducible observations

The compile and pinned real-CNF proof preflight succeeded:
https://github.com/Frane12/AndroidGameTest/actions/runs/41681988821

Original 2026 formula `7db30d12cb06f0dc2f30abff80d96d6a`:
- Original source: 1023 vars, 4088 clauses; 857 complete parity
  equations, rank 857, 166 free XOR variables.
- **31 source-entailed new short parity relations** checked independently.
- Live reason attachment began at native decision count 16,
  before the first recorded CDCL conflict.
- No solved-result performance conclusion from its early timeout probe.

A deterministic synthetic 60-case test has passed on the same pinned
Kissat source/hardware: **45 SAT and 15 UNSAT**; both the unmodified
clean Kissat and native passive/active produced identical statuses;
all 45 SAT source models satisfied every original clause; three
nontrivial native XOR-reason assignments occurred.

## Hard limits and open questions

- This is **active XOR implication** in native CDCL, **not** full
  Gaussian propagation at every trail step; XOR-explained conflicts
  and clause learning from a violating fully-assigned row are NOT
  implemented in this first prototype.
- RREF computation is one-time source extraction; the engine scans
  up to 64 static sound rows against the *current* CDCL trail.
- There is a fixed 16-decision sampling interval, not continuous
  per-assignment parity propagation.
- Dynamic reason clauses have a source-side mathematical parity
  certificate but **not yet a complete external DRAT/LRAT proof
  replay for UNSAT**. Independently checked original-CNF SAT witness
  remains mandatory. Avoid officially certified UNSAT claims.
- Changes to reasons may increase CPU overhead or worsen native
  decision heuristic dynamics. Widespread performance improvement
  and any world-record claim remain unproven.
- The initial five-real-source benchmark reuses previously seen
  2026 competition CNFs; it is *mechanistic development*, not blind.
- For a scientific comparison with existing strong parity-aware SAT
  solvers, use fresh prospective original formulas and same-host
  hardware/limits after method and policy are frozen.

No runtime restarts/process portfolios/watchdogs are introduced by
R32u. Every test attempt runs precisely **one** native Kissat.
