#!/usr/bin/env python3
"""R197 surgical CaDiCaL 2.1 state-resume ablations.

Pin: arminbiere/cadical@31f9aae44947c673dc6190c9beb399acb9ffec6a.
Modify only the schedule reinitialization on incremental solve entry.
The unmodified behavior remains for DRNAS_R197_KEEP=none/unset.
No modification of learned clause contents, VSIDS scores or phase arrays.
"""
import pathlib,sys,hashlib
assert len(sys.argv)==2,"usage r197_patch_cadical.py /path/src/internal.cpp"
p=pathlib.Path(sys.argv[1])
s=p.read_text()
assert "void Internal::init_search_limits () {" in s
assert 'lim.rephase = stats.conflicts + opts.rephaseint;' in s
assert 'lim.restart = stats.conflicts + opts.restartint;' in s
assert 'reluctant.enable (opts.reluctant, opts.reluctantmax);' in s
assert "#include \"internal.hpp\"" in s
s=s.replace('#include "internal.hpp"',
'''#include "internal.hpp"
#include <cstdlib>
#include <cstring>
#include <cstdio>''',1)
head,tail=s.split("void Internal::init_search_limits () {",1)
assert tail.count('  const bool incremental = lim.initialized;')>=1
tail=tail.replace('  const bool incremental = lim.initialized;',
'''  const bool incremental = lim.initialized;
  const char *r197_keep = std::getenv ("DRNAS_R197_KEEP");
  if (!r197_keep) r197_keep = "none";
  const bool r197_all = incremental && !std::strcmp (r197_keep, "all");
  const bool r197_restart = r197_all ||
     (incremental && !std::strcmp (r197_keep, "restart"));
  const bool r197_rephase = r197_all ||
     (incremental && !std::strcmp (r197_keep, "rephase"));
  const bool r197_stabilize = r197_all ||
     (incremental && !std::strcmp (r197_keep, "stabilize"));
  if (incremental) {
    std::fprintf (stderr,
      "R197_STATE when=before keep=%s conflicts=%lld restarts=%lld "
      "restart_limit=%lld rephase_limit=%lld stabilize_limit=%lld "
      "stable=%d rephase_count0=%lld rephase_count1=%lld\\n",
      r197_keep,(long long)stats.conflicts,(long long)stats.restarts,
      (long long)lim.restart,(long long)lim.rephase,
      (long long)lim.stabilize,stable?1:0,
      (long long)lim.rephased[0],(long long)lim.rephased[1]);
  }''',1)
rephase='''  lim.rephase = stats.conflicts + opts.rephaseint;
  lim.rephased[0] = lim.rephased[1] = 0;'''
assert tail.count(rephase)==1
tail=tail.replace(rephase,'''  if (!r197_rephase) {
    lim.rephase = stats.conflicts + opts.rephaseint;
    lim.rephased[0] = lim.rephased[1] = 0;
  }''',1)
restart='''  lim.restart = stats.conflicts + opts.restartint;'''
assert tail.count(restart)==1
tail=tail.replace(restart,'''  if (!r197_restart)
    lim.restart = stats.conflicts + opts.restartint;''',1)
begin='''  if (!incremental) {
    stable = opts.stabilize && opts.stabilizeonly;'''
end='''  } else
    reluctant.disable ();

  /*----------------------------------------------------------------------*/

  // Conflict and decision limits.'''
assert tail.count(begin)==1 and tail.count(end)==1
tail=tail.replace(begin,'''  if (!r197_stabilize) {
  if (!incremental) {
    stable = opts.stabilize && opts.stabilizeonly;''',1)
tail=tail.replace(end,'''  } else
    reluctant.disable ();
  }

  if (incremental) {
    std::fprintf (stderr,
      "R197_STATE when=after keep=%s conflicts=%lld restarts=%lld "
      "restart_limit=%lld rephase_limit=%lld stabilize_limit=%lld "
      "stable=%d rephase_count0=%lld rephase_count1=%lld\\n",
      r197_keep,(long long)stats.conflicts,(long long)stats.restarts,
      (long long)lim.restart,(long long)lim.rephase,
      (long long)lim.stabilize,stable?1:0,
      (long long)lim.rephased[0],(long long)lim.rephased[1]);
  }

  /*----------------------------------------------------------------------*/

  // Conflict and decision limits.''',1)
s=head+"void Internal::init_search_limits () {"+tail
assert s.count('R197_STATE when=before')==1
assert s.count('R197_STATE when=after')==1
assert 'r197_rephase' in s and 'r197_restart' in s and 'r197_stabilize' in s
p.write_text(s)
print("R197_CADICAL_PATCH_PASS",hashlib.sha256(s.encode()).hexdigest(),flush=True)
