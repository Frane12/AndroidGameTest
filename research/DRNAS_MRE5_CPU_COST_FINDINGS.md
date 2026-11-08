# DRNAS MRE5 — Native CMS CPU and BCP watcher workload: final audit

Date: 2026-11-08. Experimental branch:
experiment/drnas-mre5-cpu-watch-cost-20261108.
Successful source-paired GitHub run:
https://github.com/Frane12/AndroidGameTest/actions/runs/42490090624

All stages successful; 32/32 SHA-pinned SAT trials, independently checked
original CNF SAT witnesses, two native seeds × two timing repeats × eight arms.
All arms used the SAME source-pinned CryptoMiniSat 5.11.15 library with OTF
Gauss OFF. Exact upstream source commit:
3b709118fd08eb1d15f25e0e239dbc596f967b60.

Source: reused SAT2026 official-28dcc4119e1bbb5fbd3fdd8f4140f28d.cnf
SHA256 b2c2008e5d24a7aa82499d1486af2550a53a7167e46836c4b9977846204ad483.

Certified clauses:
A=(-12,224); B=(12,-224), jointly imply x12=x224.
Source XORs frozen across arms. All mathematical CRR proofs replayed once
OUTSIDE the native timed trials; results therefore isolate native solve CPU,
not full extraction+proof+deployment overhead.

## Real native CMS solver CPU, trace OFF

CPU measured directly via clock_gettime(CLOCK_PROCESS_CPUTIME_ID), checked
against getrusage(RUSAGE_SELF) user+system seconds, entirely around cms.solve().

| Arm | sum process CPU seconds, 4 trials | delta vs XOR-only |
|---|---:|---:|
| XOR-only | 31.343673 | reference |
| A-only | 32.049424 | +2.252% |
| B-only | 33.325243 | +6.322% |
| A+B | 31.294509 | -0.157% |

B-only adds 1.981570 CPU seconds despite reducing native mean CDCL decisions
from 72,344.5 to 71,203 (about -1.58%). The CPU regression is positive on
both distinct seeds: +0.7622s on seed 0 and +1.2194s on seed 1.
A+B is fast on one seed (-0.95645s CPU for two repetitions) but slow on
the other (+0.90729s). Averaging these cancels; it is NOT robust acceleration.

## Actual non-inprocessing binary watcher workload, trace ON

Counters are live from PropEngine::prop_bin_cl, with each visited binary
watch ID classified by the second literal as already satisfied (no new unit),
undefined (new unit), or false (binary conflict). No per-event syscalls.

The following figures are MEANS PER RUN across four timed executions:

| Arm | all binary watch visits | all watched units | already satisfied | tagged watch visits | tagged units |
|---|---:|---:|---:|---:|---:|
| XOR-only | 5,872,939 | 2,800,084 | 3,067,037 | 0 | 0 |
| A-only | 6,168,662 | 2,954,069 | 3,209,478 | 7,809 | 3,681 |
| B-only | 6,215,287 | 2,983,041 | 3,226,970 | 9,664 | 4,138 |
| A+B | 6,788,121 | 3,217,886 | 3,565,156 | 20,717 | 9,700 |

B-only adds approximately 342,348 watched-binary visits (+5.83%), plus
182,957 new unit-enqueue events and ~159,934 satisfied scans per run,
while reducing decision count; its process CPU rises +6.32%.
A+B increases binary visits approximately 915,183 (+15.58%)
and total native CMS propagations ~35.98%; different seeds lead to
opposite timing outcomes.

The tagged watch IDs account for only a SMALL portion of the change in
global watcher traffic; the extra clauses alter native CDCL search/trail,
so downstream propagations and redundant scans dominate the effect. This
is a supported mechanistic inference, not a proof that each additional scan
is causally due to exactly one input clause.

## Instrumentation overhead (paired on versus off of SAME input)

The patched native binary is identical in all arms, but its hot loop calls
the trace helper. Turning recording ON versus OFF gives:
- XOR-only: 31.477830 minus 31.343673 = +0.134157 CPU s across four trials
  (+0.43%).
- A-only: 32.019885 minus 32.049424 = -0.029539 s (timing noise).
- B-only: 33.458488 minus 33.325243 = +0.133245 s (+0.40%).
- A+B: 31.600681 minus 31.294509 = +0.306172 s (+0.98%).

These are observed paired differences, NOT a constant overhead calibration.
Do not compare a fully instrumented MRE5 build directly against a prior
Ubuntu-packaged CMS library to claim a solver speedup.

## Strongest conclusion

A smaller number of mathematically valid clauses does not guarantee lower
CPU cost: clause B demonstrably causes direct native watched-unit events,
but also perturbs propagation/cascades and raises global binary watcher
visits by ~5.8%. Mean native decisions decrease by ~1.6%, while CPU time
still increases by ~6.3% on the one controlled source across both seeds.

This supports testing a **watch-work-aware gate**, not a gate based on
numbers of new clauses, apparent UP novelty, or raw reduced decision count.

## Caveats

- Single reused formula, 2 independent seeds; no blind holdout.
- Native CPU around cms.solve() only; no per-clause CPU cycle attribution.
- 2 repeats each seed: timing repeat is not independent formula data.
- Tagged CDCL watch events are direct, but their downstream CPU consequences
  cannot be separately assigned to one watcher.
- CPU time can drift due to runner host variability; use larger replicated
  holdout before claiming practical speedup.
- This SAT-only experiment independently verified original SAT witnesses.
  Independent UNSAT LRAT is not part of this experiment.

## Proposed very next small experiment

On this same SAT source, use a fixed 2-seed mini-sweep to test a cheap
watch-work penalty / implication-vs-satisfied-scans gate. Probe with shadow
measurement first, then selectively accept A/B only when observed marginal
native CPU savings exceed threshold after overhead and preprocessing.
This cannot select a winner post hoc on an unseen run; any gating rule
must be frozen and validated on previously untouched source-disjoint CNFs.
