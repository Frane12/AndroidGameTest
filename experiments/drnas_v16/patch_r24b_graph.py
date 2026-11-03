#!/usr/bin/env python3
"""R24b: depth and labelled-community crossings in the traversed 1-UIP DAG.

Experimental observation only; no heuristic or SAT decisions are changed.
Community labels must be supplied externally as 'external_var group' lines.
They must move with variables under any permutation; 0 means unknown.
"""
import argparse
from pathlib import Path
import patch_r24_dynamics as base
import patch_r22_conflict_chain as prev

def deduce(source):
    s=base.deduce(source)
    s=base.one(s, '#include "deduce.h"', '#include <string.h>\n#include "deduce.h"', 'string header')
    code='''// R24b: max reverse path depth on reason edges actually visited by 1-UIP.
// This is a subgraph, not the full implication graph. Unlabelled edges are unknown.
#define R24B_LABEL_CAP (1u<<20)
static unsigned *r24b_depth, *r24b_stamp, *r24b_labels;
static unsigned r24b_capacity, r24b_epoch, r24b_current, r24b_parent_group;
static unsigned r24b_conflict_max, r24b_loaded, r24b_enabled = 1;
static uint64_t r24b_depth_sum, r24b_conflicts, r24b_max_depth;
static uint64_t r24b_edges, r24b_cross, r24b_unknown, r24b_fail;
static void r24b_load (void) {
  if (r24b_loaded++) return;
  const char *path=getenv("DRNAS_R24_COMMUNITIES");
  if (!path || !*path) return;
  FILE *f=fopen(path,"r");
  if (!f) {r24b_fail++; return;}
  r24b_labels=calloc(R24B_LABEL_CAP,sizeof(unsigned));
  if (!r24b_labels) {fclose(f); r24b_fail++; return;}
  unsigned variable,group;
  while (fscanf(f,"%u %u",&variable,&group)==2) {
    if (variable < R24B_LABEL_CAP) r24b_labels[variable]=group;
    else r24b_fail++;
  }
  fclose(f);
}
static unsigned r24b_group (kissat *solver, unsigned lit) {
  if (!r24b_labels) return 0;
  int ext=kissat_export_literal(solver,lit);
  unsigned v=ext<0 ? (unsigned)(-ext) : (unsigned)ext;
  return v<R24B_LABEL_CAP ? r24b_labels[v] : 0;
}
static void r24b_begin (kissat *solver) {
  r24b_load();
  if (!r24b_enabled) return;
  if (VARS > r24b_capacity) {
    free(r24b_depth); free(r24b_stamp);
    r24b_capacity=VARS;
    r24b_depth=calloc(r24b_capacity,sizeof(unsigned));
    r24b_stamp=calloc(r24b_capacity,sizeof(unsigned));
    if (!r24b_depth || !r24b_stamp) {r24b_enabled=0; r24b_fail++; return;}
    r24b_epoch=0;
  }
  if (++r24b_epoch==0) {memset(r24b_stamp,0,r24b_capacity*sizeof(unsigned)); r24b_epoch=1;}
  r24b_current=0; r24b_parent_group=0; r24b_conflict_max=0;
}
static inline void r24b_touch (kissat *solver, unsigned lit) {
  if (!r24b_enabled) return;
  unsigned idx=IDX(lit), d=r24b_current+1;
  if (idx>=r24b_capacity) {r24b_fail++; return;}
  if (r24b_stamp[idx]!=r24b_epoch) {r24b_stamp[idx]=r24b_epoch; r24b_depth[idx]=d;}
  else if (r24b_depth[idx]<d) r24b_depth[idx]=d;
  if (r24b_depth[idx]>r24b_conflict_max) r24b_conflict_max=r24b_depth[idx];
  if (r24b_current) {
    unsigned group=r24b_group(solver,lit);
    r24b_edges++;
    if (!r24b_parent_group || !group) r24b_unknown++;
    else if (r24b_parent_group != group) r24b_cross++;
  }
}
static inline void r24b_pivot (kissat *solver, unsigned lit) {
  unsigned idx=IDX(lit);
  if (!r24b_enabled || idx>=r24b_capacity || r24b_stamp[idx]!=r24b_epoch) {
    r24b_current=0; r24b_parent_group=0; r24b_fail++; return;
  }
  r24b_current=r24b_depth[idx];
  r24b_parent_group=r24b_group(solver,lit);
}
static inline void r24b_finish (void) {
  if (!r24b_enabled) return;
  r24b_conflicts++; r24b_depth_sum+=r24b_conflict_max;
  if (r24b_conflict_max>r24b_max_depth) r24b_max_depth=r24b_conflict_max;
}

'''
    s=base.one(s,'static inline void r24_trace (kissat *solver) {',code+'static inline void r24_trace (kissat *solver) {','b declarations')
    s=base.one(s,'  fflush(stdout);\n  r24_mark *= 2;',
      '''  fprintf(stdout,"c R24B_TRACE mark=%u conflict=%" PRIu64
    " chains=%" PRIu64 " depth_sum=%" PRIu64 " max_depth=%" PRIu64
    " edges=%" PRIu64 " cross=%" PRIu64 " unknown=%" PRIu64 " errors=%" PRIu64 "\\n",
    r24_mark, solver->statistics.conflicts, r24b_conflicts, r24b_depth_sum,
    r24b_max_depth, r24b_edges, r24b_cross, r24b_unknown, r24b_fail);
  fflush(stdout);
  r24_mark *= 2;''','b trace')
    s=base.one(s,'  r24_trace (solver);\n  START (deduce);','  r24_trace (solver);\n  r24b_begin(solver);\n  START (deduce);','b begin')
    s=base.one(s,'  r24_calls++;','  r24b_touch(solver,lit);\n  r24_calls++;','b touch')
    s=base.one(s,'    r24_pivots++;','    r24b_pivot(solver,uip);\n    r24_pivots++;','b pivot')
    s=base.one(s,'      STOP (deduce);\n      return res;','      r24b_finish();\n      STOP (deduce);\n      return res;','b finish otfs')
    s=base.one(s,'  STOP (deduce);\n  return 0;','  r24b_finish();\n  STOP (deduce);\n  return 0;','b finish normal')
    return s

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--kissat-root',required=True,type=Path);a=parser.parse_args()
    prev.config();root=a.kissat_root/'src'
    edits={'clause.c':prev.prev.patch_clause_c,'deduce.c':deduce,
           'assign.c':prev.prev.patch_assign,'search.c':prev.search}
    changed={root/name:fn((root/name).read_text()) for name,fn in edits.items()}
    for path,data in changed.items():path.write_text(data)
    print('R24B_GRAPH_TRACE_PATCH_OK',flush=True)
if __name__=='__main__':main()
