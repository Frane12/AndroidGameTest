#!/usr/bin/env python3
"""R32o read-only lucky direction/probe trace for pinned Kissat.

Apply after existing R32n/R32l/R32m patches. This modifies no SAT decisions,
clauses, variable order, restarts or search policy. It records, per lucky call,
which direction was visited, how many leading probes encountered conflicts,
and the first attempted and conflicting internal literal.
"""
import argparse
import re
from pathlib import Path

HELPER = r'''// R32o: read-only lucky probe diagnostics, one native Kissat process.
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static int r32o_trace_flag=-1;
static unsigned r32o_call_number=0;
static unsigned r32o_probes=0,r32o_failures=0;
static int r32o_first_probe=0,r32o_first_conflict=0;
static const char *r32o_direction="none";
static int r32o_enabled(void) {
  if(r32o_trace_flag<0) {
    const char *s=getenv("R32O_TRACE");
    r32o_trace_flag=(s && !strcmp(s,"1")) ? 1 : 0;
  }
  return r32o_trace_flag;
}
static int r32o_signed_lit(unsigned lit) {
  const int v=(int)IDX(lit)+1;
  return NEGATED(lit) ? -v : v;
}
static void r32o_begin(const char *direction) {
  if(!r32o_enabled())return;
  r32o_direction=direction;
  r32o_probes=r32o_failures=0;
  r32o_first_probe=r32o_first_conflict=0;
}
static void r32o_probe(unsigned lit) {
  if(!r32o_enabled())return;
  if(!r32o_probes)r32o_first_probe=r32o_signed_lit(lit);
  ++r32o_probes;
}
static void r32o_failure(unsigned lit) {
  if(!r32o_enabled())return;
  if(!r32o_failures)r32o_first_conflict=r32o_signed_lit(lit);
  ++r32o_failures;
}
static void r32o_end(int result) {
  if(!r32o_enabled())return;
  printf("c R32O_DIR call=%u direction=%s result=%d probes=%u"
         " failures=%u first_probe=%d first_conflict=%d\n",
         r32o_call_number,r32o_direction,result,r32o_probes,
         r32o_failures,r32o_first_probe,r32o_first_conflict);
  fflush(stdout);
}
static void r32o_finish(int result,const char *shortcut) {
  if(!r32o_enabled())return;
  printf("c R32O_LUCKY call=%u result=%d shortcut=%s\n",
         r32o_call_number,result,shortcut);
  fflush(stdout);
}
'''

def once(text, old, new, name):
    n=text.count(old)
    if n!=1:
        raise RuntimeError("R32O_ANCHOR_%s count=%d"%(name,n))
    return text.replace(old,new,1)

def patch_direction(source, direction):
    marker="static int "+direction+"_satisfiable (struct kissat *solver) {"
    start=source.index(marker)
    future=source.find("\nstatic int ",start+len(marker))
    if future<0:
        future=source.index("\nint kissat_lucky ",start+len(marker))
    block=source[start:future]
    block=once(block,marker+"\n  assert (!solver->level);",
        marker+'\n  assert (!solver->level);\n  r32o_begin("'+direction+'");',
        direction+"_begin")
    signed="not_lit" if direction.endswith("false") else "lit"
    first="    kissat_internal_assume (solver, "+signed+");\n    clause *c = kissat_probing_propagate (solver, 0, true);"
    block=once(block,first,
        "    r32o_probe("+signed+");\n"+first,
        direction+"_probe")
    block=once(block,"    if (!c)\n      continue;",
        "    if (!c)\n      continue;\n    r32o_failure("+signed+");",
        direction+"_first_conflict")
    for result in ("0","10","20"):
        matches=list(re.finditer(r"\breturn "+result+r";",block))
        if len(matches)!=1:
            raise RuntimeError("R32O_RETURN_%s_%s count=%d"%(direction,result,len(matches)))
        block=block.replace("return "+result+";","r32o_end("+result+"); return "+result+";",1)
    return source[:start]+block+source[future:]

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--kissat-root",type=Path,required=True)
    a=p.parse_args()
    path=a.kissat_root/"src"/"lucky.c"
    source=path.read_text()
    source=once(source,"static int forward_false_satisfiable",HELPER+"\nstatic int forward_false_satisfiable","inject_helpers")
    for direction in ("forward_false","forward_true","backward_false","backward_true"):
        source=patch_direction(source,direction)
    source=once(source,"  START (lucky);",
        "  if(r32o_enabled())++r32o_call_number;\n  START (lucky);",
        "call_number")
    source=once(source,"  int res = 0;","  int res = 0;\n  const char *r32o_shortcut=\"none\";","shortcut_init")
    source=once(source,'    kissat_verbose (solver, "set all variables to true");',
        '    r32o_shortcut="all_true";\n    kissat_verbose (solver, "set all variables to true");',"shortcut_true")
    source=once(source,'    kissat_verbose (solver, "set all variables to false");',
        '    r32o_shortcut="all_false";\n    kissat_verbose (solver, "set all variables to false");',"shortcut_false")
    source=once(source,"  STOP (lucky);\n\n  return res;",
        "  STOP (lucky);\n  r32o_finish(res,r32o_shortcut);\n\n  return res;",
        "finish")
    path.write_text(source)
    print("R32O_LUCKY_READONLY_TRACE_PATCH_OK",flush=True)

if __name__=="__main__":
    main()
