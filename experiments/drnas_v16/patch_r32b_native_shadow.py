#!/usr/bin/env python3
"""R32b: instrumentation-only source patch for exact pinned Kissat.

Capture original DIMACS external literals in parse.c; at the beginning of
kissat_search record unconditional/root GF2 gap; at conflict-free propagation
checkpoints 0/256/1024/4096 capture full exported trail and only if all vars
are mapped, pass that *projection* to native, bounded GF2-vs-original-BCP.
NEVER modify learned/original clauses, solver policy, assignments or phases.
"""
from pathlib import Path
import argparse,hashlib

PIN="8af8e56f174b778aef3aa45af9f739b2a5f492c2"

def once(s,old,new,what):
    if s.count(old)!=1:
        raise RuntimeError(f"R32B_KISSAT_ANCHOR_MISMATCH {what} count={s.count(old)}")
    return s.replace(old,new,1)

def patch_parse(s):
    s=once(s,'#define size_buffer (1u << 20)',
           '#include "r32b_shadow_core.h"\n\n#define size_buffer (1u << 20)',
           'include_native_core')
    s=once(s,'      kissat_add (solver, lit);',
           '      r32b_capture_original_literal (lit);\n      kissat_add (solver, lit);',
           'external_dimacs_capture')
    return s

def patch_search(s):
    decl=r'''// DRNAS R32b passive native original-CNF algebra observer only.
extern void r32b_shadow_native_probe (const int *, unsigned, unsigned);
static unsigned r32b_next=0;
static int r32b_enabled=-1;
static void r32b_native_snapshot (kissat *solver) {
  if(r32b_enabled<0) {
    const char *mode=getenv("R32B_MODE");
    r32b_enabled=mode && !strcmp(mode,"shadow");
  }
  if(!r32b_enabled || r32b_next>=4)return;
  static const uint64_t marks[4]={0,256,1024,4096};
  const uint64_t conflicts=solver->statistics.conflicts;
  if(conflicts<marks[r32b_next])return;
  const unsigned mark=(unsigned)marks[r32b_next++];
  const size_t total=SIZE_ARRAY(solver->trail);
  if(total>1024) {
    printf("c R32B_TRAIL mark=%u signal=TRAIL_GUARD reason=trail_cap"
           " conflicts=%" PRIu64 " trail=%zu\n",mark,conflicts,total);
    fflush(stdout);return;
  }
  int exported[1024];
  const unsigned *trail=BEGIN_ARRAY(solver->trail);
  unsigned mapped=0;
  for(size_t i=0;i<total;i++){
    int ext=kissat_export_literal(solver,trail[i]);
    if(!ext)break;
    exported[mapped++]=ext;
  }
  if(mapped!=total) {
    printf("c R32B_TRAIL mark=%u signal=TRAIL_GUARD reason=unmapped"
           " conflicts=%" PRIu64 " trail=%zu mapped=%u\n",
           mark,conflicts,total,mapped);
    fflush(stdout);return;
  }
  printf("c R32B_TRACE mark=%u conflict=%" PRIu64
         " decisions=%" PRIu64 " restarts=%" PRIu64
         " propagations=%" PRIu64 " learned=%" PRIu64
         " trail=%u complete=1\n",
         mark,conflicts,solver->statistics.decisions,
         solver->statistics.restarts,solver->statistics.propagations,
         solver->statistics.clauses_learned,mapped);
  r32b_shadow_native_probe(exported,mapped,mark);
}

'''
    s=once(s,'int kissat_search (kissat *solver) {',
           decl+'int kissat_search (kissat *solver) {',
           'passive_monitor_function')
    s=once(s,'int kissat_search (kissat *solver) {\n  REPORT (0, \'*\');',
           'int kissat_search (kissat *solver) {\n'
           '  // Even easy CNFs solved by preprocessing receive a root-only audit.\n'
           '  r32b_shadow_native_probe(NULL,0,9999);\n'
           '  REPORT (0, \'*\');',
           'root_even_before_preprocessing')
    s=once(s,
           '      clause *conflict = kissat_search_propagate (solver);\n      if (conflict)',
           '      clause *conflict = kissat_search_propagate (solver);\n'
           '      if (!conflict) r32b_native_snapshot (solver);\n'
           '      if (conflict)',
           'conflict_free_native_probe')
    s=once(s,'  report_search_result (solver, res);\n  return res;',
           '''  report_search_result (solver, res);
  printf("c R32B_FINAL status=%d conflicts=%" PRIu64
         " decisions=%" PRIu64 " restarts=%" PRIu64
         " propagations=%" PRIu64 " learned=%" PRIu64 "\\n",
         res,solver->statistics.conflicts,solver->statistics.decisions,
         solver->statistics.restarts,solver->statistics.propagations,
         solver->statistics.clauses_learned);
  fflush(stdout);
  return res;''',
           'read_only_final_stats')
    return s

def main():
    p=argparse.ArgumentParser();p.add_argument("--kissat-root",type=Path,required=True)
    p.add_argument("--native-header",type=Path,default=Path("experiments/drnas_v16/r32b_shadow_core.h"))
    a=p.parse_args()
    root=a.kissat_root/"src"
    parse=root/"parse.c";search=root/"search.c"
    header=(root/"r32b_shadow_core.h")
    if header.exists():raise RuntimeError("Source already patched")
    content=a.native_header.read_bytes()
    changed_parse=patch_parse(parse.read_text())
    changed_search=patch_search(search.read_text())
    header.write_bytes(content)
    parse.write_text(changed_parse)
    search.write_text(changed_search)
    print("R32B_NATIVE_SHADOW_PATCH_OK",PIN,
          "header_sha256="+hashlib.sha256(content).hexdigest(),
          "parse_sha256="+hashlib.sha256(changed_parse.encode()).hexdigest(),
          "search_sha256="+hashlib.sha256(changed_search.encode()).hexdigest(),flush=True)

if __name__=="__main__":main()
