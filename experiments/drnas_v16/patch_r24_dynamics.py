#!/usr/bin/env python3
"""R24 shadow-only first-UIP counters; independent of all restart policies.

Counts revisited literals during conflict resolution, binary/long resolution
steps, distinct decision levels and repeated long-clause content. It does not
claim to record the full propagation graph or physical clause identities.
"""
import argparse
from pathlib import Path
import patch_r22_conflict_chain as prev


def one(s, old, new, label):
    if s.count(old) != 1:
        raise RuntimeError(f"R24 anchor {label}: {s.count(old)} matches")
    return s.replace(old, new, 1)


def deduce(source):
    s = prev.deduce(source)
    anchor = 'static inline bool analyze_literal (kissat *solver, assigned *all_assigned,'
    declarations = '''// R24 counters cover the 1-UIP traversal, not the full propagation graph.
static uint64_t r24_calls, r24_revisits, r24_crosslevel, r24_pivots;
static uint64_t r24_binary, r24_long, r24_reason_reused, r24_reason_overflow;
static uint64_t r24_seen_a[1u<<18], r24_seen_b[1u<<18];
static unsigned r24_mark = 256;
static inline void r24_trace (kissat *solver) {
  if (solver->statistics.conflicts < r24_mark || r24_mark > 1024) return;
  // Threshold is a lower bound: log actual conflict, never fabricate a snapshot.
  fprintf(stdout, "c R24_TRACE mark=%u conflict=%" PRIu64
    " calls=%" PRIu64 " revisits=%" PRIu64 " crosslevel=%" PRIu64
    " pivots=%" PRIu64 " binary=%" PRIu64 " long=%" PRIu64
    " reason_reused=%" PRIu64 " reason_overflow=%" PRIu64
    " mature_low=%" PRIu64 " antecedent=%" PRIu64 " birth_unknown=%" PRIu64 "\\n",
    r24_mark, solver->statistics.conflicts, r24_calls, r24_revisits,
    r24_crosslevel, r24_pivots, r24_binary, r24_long, r24_reason_reused,
    r24_reason_overflow, drnas_r21_counts[11], drnas_r21_counts[6], drnas_r21_counts[10]);
  fflush(stdout);
  r24_mark *= 2;
}
static inline void r24_reason (const clause *c) {
  uint64_t a,b; drnas_r21_clause_fingerprint(c,&a,&b);
  // Store a nonzero fingerprint to reserve zero for empty slots.
  a |= 1ULL;
  unsigned i=(unsigned)a & ((1u<<18)-1u);
  for (unsigned step=0; step<64; step++,i=(i+1u)&((1u<<18)-1u)) {
    if (!r24_seen_a[i]) {r24_seen_a[i]=a; r24_seen_b[i]=b; return;}
    if (r24_seen_a[i]==a && r24_seen_b[i]==b) {r24_reason_reused++; return;}
  }
  r24_reason_overflow++;
}

'''
    s = one(s, anchor, declarations + anchor, 'declarations')
    s = one(s, '  if (a->analyzed)\n    return false;',
            '  r24_calls++;\n  if (level != solver->level) r24_crosslevel++;\n'
            '  if (a->analyzed) { r24_revisits++; return false; }', 'revisit')
    s = one(s, '  START (deduce);', '  r24_trace (solver);\n  START (deduce);', 'checkpoint')
    s = one(s, '    resolved++;\n    if (a->binary) {',
            '    resolved++;\n    r24_pivots++;\n    if (a->binary) {\n      r24_binary++;', 'binary')
    s = one(s, '      clause *reason = kissat_dereference_clause (solver, ref);\n      for (all_literals_in_clause (lit, reason))',
            '      clause *reason = kissat_dereference_clause (solver, ref);\n'
            '      r24_long++; r24_reason(reason);\n'
            '      for (all_literals_in_clause (lit, reason))', 'reason')
    return s


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--kissat-root', required=True, type=Path)
    a = p.parse_args()
    prev.config()
    root = a.kissat_root / 'src'
    edits = {'clause.c': prev.prev.patch_clause_c, 'deduce.c': deduce,
             'assign.c': prev.prev.patch_assign, 'search.c': prev.search}
    changed = {root / name: fun((root / name).read_text()) for name, fun in edits.items()}
    for path, data in changed.items():
        path.write_text(data)
    print('R24_TRACE_PATCH_OK; R22 POLICY UNCHANGED', flush=True)


if __name__ == '__main__':
    main()
