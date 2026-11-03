# R32g — certified inter-solver root-unit communication audit

Date: 2026-11-03. **All six GitHub Actions jobs passed.**

- [Run 41642371038](https://github.com/Frane12/AndroidGameTest/actions/runs/41642371038)
- [FINAL-540, source-SHA-locked artifact](https://github.com/Frane12/AndroidGameTest/actions/runs/41642371038/artifacts/13232774472)
- Experimental source: `r32g_cooperative_relay_benchmark.py`.

## Protocol and interpretation

36 new SHA-distinct synthetic original CNFs (18 baseline + 18 coupled
stress), 3 matched repeats, five modes (clean Kissat, native OFF,
R32e active, independent two-core race, cooperative relay): **540 trials**,
no timeouts, final audit PASS. All SAT results are independently checked
against the original DIMACS; UNSAT labels rely on generator source, not LRAT.
Same frozen clean/native binary SHAs as R32e. Two fixed CPU cores.

**Real communication was tested, but it is limited**: the R32e worker
emits independently certified original-source signed GF(2) root literals.
A Python coordinator verifies them and, after a fixed 20 ms guard, may
kill and *restart* the native-OFF worker with the original CNF plus those
logically entailed literals. At most one restart per attempt. This does
not import learnt clauses in-process or preserve the OFF worker's CDCL
history. Solver terminal timestamp excludes subsequent offline scientific
proof audit; measured times include process startup, polling, relay
and restart. Child CPU includes both workers, but not Python-parent CPU.

## Final measured totals

| Mode | Total PAR2/solver wall (s) | Change against Native OFF | Child CPU (s) | CPU overhead against Native OFF |
|---|---:|---:|---:|---:|
| Clean Kissat | 3.111271 | -0.27% | 2.258195 | +0.29% |
| Native OFF | **3.119655** | baseline | **2.251707** | baseline |
| R32e active solo | 3.184172 | +2.07% | 2.244007 | -0.34% |
| Independent two-core race | **3.031123** | **-2.8379%** | 5.640890 | **+150.5162%** |
| Cooperative proof relay | 3.205275 | **+2.7445%** | 5.888480 | **+161.5118%** |

This small synthetic study suggests that naive destructive root-unit
relay actually reduces wall-time performance relative to the independent
race, even though certified source knowledge is being communicated.

**Actual relay executions:** 63 of 108 relay trials; root unit messages
observed in 73/108 trials. On the 18 coupled-stress CNFs, relay triggered
in 54/54 paired trials and R32e won all 54 after the original OFF worker
was destroyed. The independent race on those same cases chose OFF in
54/54 trials, making the causal failure mode transparent: the 20ms
coordinator restarts the worker that would otherwise finish first.

| Cohort | Native OFF (s) | Independent race (s) | Cooperative relay (s) | Relay change vs OFF |
|---|---:|---:|---:|---:|
| 18 baseline CNFs | 1.143386 | 0.978767 | 1.000542 | -12.4931% |
| 18 coupled stress CNFs | 1.976269 | 2.052356 | 2.204733 | **+11.5604%** |

The bootstrap 95% interval of the cooperative-vs-native-OFF paired
case-median delta is **[-8.499%, +10.785%]**; it spans zero and is
not evidence of a general speedup. Some per-case medians differ sharply,
which may include native preparation, startup and VM/runner noise.

## Research conclusion and next controlled experiment

1. Verified root-unit inter-task communication can be carried out safely
   via a bounded coordinator relay without invalidating a SAT model.
2. **Killing a solver to insert source-proven units destroys useful search
   progress**, even when the clauses themselves are fully valid. This
   distinguishes logical safety from *computational* utility.
3. The next mechanism must import independently certified clauses only
   at an actual safe in-process CDCL root/restart checkpoint, preserving
   assignments and learned-clause state; or hand off to a separate *third*
   worker without killing the OFF worker. Both require new controlled
   benchmarks that include communication, memory and CPU cost.
4. On the present easy synthetic suite, running two solver tasks already
   uses about 2.5x child CPU for little or no reliable general wall-time
   gain. Target genuinely hard externally sourced formulas before
   inferring a practical multicore benefit.

This test does NOT demonstrate acceleration on SAT Competition 2026,
general NP solving, or P versus NP.
