#!/usr/bin/env python3
"""Patch exact upstream CaDiCaL rel-1.7.3 (commit 38e073b...) for C8c.

Only logs and one SAT-preserving intervention: optionally DO NOT attempt BVE on
specified variable IDs at the elimination schedule pop. All learned/added
clauses remain standard CaDiCaL, no unsound transform added.
Logging is disabled unless DRNAS_C8C_TRACE=1.
This intentionally does not call a skipped pivot an eliminated variable.
"""
from __future__ import annotations
import argparse,pathlib
TAG_SHA="38e073b389a877b0a0d3c91136d2443ab95fdeba"
def replace_once(s,a,b):
    assert s.count(a)==1,("C8C exact 1.7.3 source anchor drift",a[:140],s.count(a))
    return s.replace(a,b)
def main(path):
    e=path/"src/elim.cpp"
    v=path/"src/vivify.cpp"
    s=e.read_text()
    s=replace_once(s,
'''#include "internal.hpp"

namespace CaDiCaL {
''',
'''#include "internal.hpp"
#include <cstdio>
#include <cstdlib>
#include <cstring>

namespace CaDiCaL {

// C8c diagnostic-only independent instrumentation, source SHA pinned.
static bool c8c_trace_enabled () {
  const char *s = std::getenv ("DRNAS_C8C_TRACE");
  return s && !std::strcmp (s, "1");
}
static bool c8c_block_candidate (int idx) {
  const char *s = std::getenv ("DRNAS_C8C_SKIP_VARS");
  if (!s || !*s) return false;
  while (*s) {
    char *end = 0;
    long value = std::strtol (s, &end, 10);
    if (end == s) return false;
    if (value == idx) return true;
    if (!*end) break;
    if (*end != ',') return false;
    s = end + 1;
  }
  return false;
}
''')
    s=replace_once(s,
'''  for (auto &c : ps) {
    if (unsat)
      break;''',
'''  long long c8c_added = 0, c8c_added_literals = 0;
  for (auto &c : ps) {
    if (unsat)
      break;''')
    s=replace_once(s,
'''      Clause *r = new_resolved_irredundant_clause ();
      elim_update_added_clause (eliminator, r);''',
'''      Clause *r = new_resolved_irredundant_clause ();
      c8c_added++;
      c8c_added_literals += r->size;
      elim_update_added_clause (eliminator, r);''')
    s=replace_once(s,
'''  LOG ("added %" PRId64 " resolvents to eliminate %d", resolvents, pivot);
}''',
'''  if (c8c_trace_enabled ())
    std::fprintf (stderr,
      "C8C_INSERT pivot=%d conflicts=%lld added=%lld added_lits=%lld\\n",
      pivot, (long long) stats.conflicts, c8c_added, c8c_added_literals);
  LOG ("added %" PRId64 " resolvents to eliminate %d", resolvents, pivot);
}''')
    s=replace_once(s,
'''  if (pos && neg > opts.elimocclim) {
    LOG ("too many occurrences thus not eliminated %d", pivot);''',
'''  if (pos && neg > opts.elimocclim) {
    if (c8c_trace_enabled ())
      std::fprintf (stderr,
         "C8C_REJECT idx=%d conflicts=%lld reason=occ_limit pos=%lld neg=%lld\\n",
         pivot, (long long)stats.conflicts,(long long)pos,(long long)neg);
    LOG ("too many occurrences thus not eliminated %d", pivot);''')
    s=replace_once(s,
'''        if (size > opts.elimclslim) {
          LOG ("resolvent size %d too big after %" PRId64''',
'''        if (size > opts.elimclslim) {
          if (c8c_trace_enabled ())
            std::fprintf (stderr,
              "C8C_REJECT idx=%d conflicts=%lld reason=resolvent_size size=%d limit=%d\\n",
              pivot, (long long)stats.conflicts, size, opts.elimclslim);
          LOG ("resolvent size %d too big after %" PRId64''')
    s=replace_once(s,
'''        if (resolvents > bound) {
          LOG ("too many non-tautological resolvents on %d", pivot);''',
'''        if (resolvents > bound) {
          if (c8c_trace_enabled ())
            std::fprintf (stderr,
             "C8C_REJECT idx=%d conflicts=%lld reason=resolvent_bound count=%lld bound=%lld\\n",
             pivot, (long long)stats.conflicts, (long long)resolvents,(long long)bound);
          LOG ("too many non-tautological resolvents on %d", pivot);''')
    s=replace_once(s,
'''  // Main loops tries to eliminate variables according to the schedule. The
  // schedule is updated dynamically and variables are potentially
  // rescheduled to be tried again if they occur in a removed clause.
  //
#ifndef QUIET
  int64_t tried = 0;
#endif
  while (!unsat && !terminated_asynchronously () &&
         stats.elimres <= resolution_limit && !schedule.empty ()) {
    int idx = schedule.front ();
    schedule.pop_front ();
    flags (idx).elim = false;
    try_to_eliminate_variable (eliminator, idx);''',
'''  // Main loops tries to eliminate variables according to the schedule. The
  // schedule is updated dynamically and variables are potentially
  // rescheduled to be tried again if they occur in a removed clause.
  //
#ifndef QUIET
  int64_t tried = 0;
#endif
  long long c8c_candidate_sequence = 0;
  if (c8c_trace_enabled ())
    std::fprintf (stderr,
        "C8C_ROUND_START conflicts=%lld round=%lld candidates=%lld\\n",
        (long long)stats.conflicts, (long long)stats.elimrounds,
        (long long)schedule.size ());
  while (!unsat && !terminated_asynchronously () &&
         stats.elimres <= resolution_limit && !schedule.empty ()) {
    int idx = schedule.front ();
    schedule.pop_front ();
    flags (idx).elim = false;
    const long long c8c_pre_res = (long long) stats.elimres;
    const long long c8c_pre_checks = (long long) stats.elimrestried;
    const long long c8c_pre_tried = (long long) stats.elimtried;
    const long long c8c_pre_eliminated = (long long) stats.all.eliminated;
    const long long c8c_pre_fixed = (long long) stats.all.fixed;
    const long long c8c_conflicts = (long long) stats.conflicts;
    const bool c8c_skip = c8c_block_candidate (idx);
    if (!c8c_skip) try_to_eliminate_variable (eliminator, idx);
    ++c8c_candidate_sequence;
    if (c8c_trace_enabled ())
      std::fprintf (stderr,
        "C8C_CANDIDATE seq=%lld idx=%d conflicts=%lld round=%lld skip=%d accepted=%d tried_delta=%lld resolutions=%lld checks=%lld fixed=%lld\\n",
        c8c_candidate_sequence, idx, c8c_conflicts,
        (long long)stats.elimrounds,(int)c8c_skip,
        (int)(stats.all.eliminated > c8c_pre_eliminated),
        (long long)stats.elimtried - c8c_pre_tried,
        (long long)stats.elimres - c8c_pre_res,
        (long long)stats.elimrestried - c8c_pre_checks,
        (long long)stats.all.fixed - c8c_pre_fixed);''')
    e.write_text(s)
    t=v.read_text()
    t=replace_once(t,
'''#include "internal.hpp"

namespace CaDiCaL {
''',
'''#include "internal.hpp"
#include <cstdio>
#include <cstdlib>
#include <cstring>

namespace CaDiCaL {
static bool c8c_vivify_trace () {
  const char *s = std::getenv ("DRNAS_C8C_TRACE");
  return s && !std::strcmp (s, "1");
}
''')
    t=replace_once(t,
'''  START_SIMPLIFIER (vivify, VIVIFY);
  stats.vivifications++;

  int64_t limit = stats.propagations.search;''',
'''  START_SIMPLIFIER (vivify, VIVIFY);
  stats.vivifications++;
  const long long c8c_before_checks = (long long)stats.vivifychecks;
  const long long c8c_before_sub = (long long)stats.vivifysubs;
  const long long c8c_before_str = (long long)stats.vivifystrs;
  const long long c8c_before_units = (long long)stats.vivifyunits;
  if (c8c_vivify_trace ())
    std::fprintf (stderr,
        "C8C_VIVIFY_START conflicts=%lld phase=%lld\\n",
        (long long)stats.conflicts,(long long)stats.vivifications);

  int64_t limit = stats.propagations.search;''')
    t=replace_once(t,
'''  vivify_round (true, limit); // Vivify all clauses.

  STOP_SIMPLIFIER (vivify, VIVIFY);''',
'''  vivify_round (true, limit); // Vivify all clauses.
  if (c8c_vivify_trace ())
    std::fprintf (stderr,
      "C8C_VIVIFY_END conflicts=%lld phase=%lld checks=%lld subsumed=%lld strengthened=%lld units=%lld\\n",
      (long long)stats.conflicts,(long long)stats.vivifications,
      (long long)stats.vivifychecks-c8c_before_checks,
      (long long)stats.vivifysubs-c8c_before_sub,
      (long long)stats.vivifystrs-c8c_before_str,
      (long long)stats.vivifyunits-c8c_before_units);

  STOP_SIMPLIFIER (vivify, VIVIFY);''')
    v.write_text(t)
    print("C8C_EXACT_173_SOURCE_PATCH_OK",e,v,flush=True)
if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("upstream_dir",type=pathlib.Path)
    args=ap.parse_args()
    main(args.upstream_dir)
