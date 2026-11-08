#!/usr/bin/env python3
"""Patch SHA-frozen CMS 5.11.15 for MRE4 P2 in-CDCL imported-clause reason events.

Only observe native watched-clause propagation/conflict. Original clauses stay
unchanged. A small C ABI marks the *exact* pre-certified clauses imported by
the adapter while add_clause() executes. Their internal clause IDs are retained
by CMS. The propagation hot path counts native watched reason events by ID.
No new implication is injected during CDCL; this is causal telemetry stage.
"""
import argparse,hashlib,json,pathlib
UPSTREAM="3b709118fd08eb1d15f25e0e239dbc596f967b60"
MARKER="DRNAS_MRE4_P2_CMS_51115_WATCH_TRACE_V1"

def edit(path,old,new,count=1):
    text=path.read_text()
    actual=text.count(old)
    if actual!=count:
        raise RuntimeError(f"{path}: anchor occurrences {actual} != {count}: {old[:100]}")
    path.write_text(text.replace(old,new,count))

def main(source):
    source=pathlib.Path(source)
    head=(source/".git").exists()
    if head:
        import subprocess
        commit=subprocess.check_output(
            ["git","-C",str(source),"rev-parse","HEAD"],text=True).strip()
        if commit!=UPSTREAM:raise RuntimeError("CMS upstream commit SHA changed: "+commit)
    solver=source/"src/solver.cpp"
    prop=source/"src/propengine.cpp"
    if MARKER in solver.read_text():
        raise RuntimeError("patch already applied")
    api=r'''
// DRNAS_MRE4_P2_CMS_51115_WATCH_TRACE_V1
#include <unordered_set>
#include <cstdint>
#include <cstdio>
namespace {
bool drnas_importing=false, drnas_solving=false;
std::unordered_set<int32_t> drnas_clause_ids;
uint64_t drnas_tagged_clauses=0;
uint64_t drnas_binary_units=0, drnas_binary_conflicts=0;
uint64_t drnas_long_units=0, drnas_long_conflicts=0;
uint64_t drnas_nonroot_units=0, drnas_nonroot_conflicts=0;
uint64_t drnas_traced_events=0;
}
extern "C" __attribute__((visibility("default"))) void drnas_mre4_trace_import(int x) {
    drnas_importing=(x!=0);
}
extern "C" __attribute__((visibility("default"))) void drnas_mre4_trace_solve(int x) {
    drnas_solving=(x!=0);
}
extern "C" __attribute__((visibility("default"))) void drnas_mre4_trace_note_clause(int32_t id, uint32_t width) {
    if(drnas_importing && width>=2 && drnas_clause_ids.insert(id).second)
        ++drnas_tagged_clauses;
}
extern "C" __attribute__((visibility("default"))) void drnas_mre4_trace_event(
    int32_t id, int conflict, int binary, uint32_t level
) {
    if(!drnas_solving || drnas_clause_ids.find(id)==drnas_clause_ids.end())return;
    ++drnas_traced_events;
    if(binary){ if(conflict)++drnas_binary_conflicts; else ++drnas_binary_units; }
    else { if(conflict)++drnas_long_conflicts; else ++drnas_long_units; }
    if(level>0){ if(conflict)++drnas_nonroot_conflicts; else ++drnas_nonroot_units; }
}
extern "C" __attribute__((visibility("default"))) void drnas_mre4_trace_dump() {
    std::printf(
        "MRE4_NATIVE_TRACE tagged=%llu bin_units=%llu bin_conflicts=%llu"
        " long_units=%llu long_conflicts=%llu nonroot_units=%llu"
        " nonroot_conflicts=%llu events=%llu\n",
        (unsigned long long)drnas_tagged_clauses,
        (unsigned long long)drnas_binary_units,
        (unsigned long long)drnas_binary_conflicts,
        (unsigned long long)drnas_long_units,
        (unsigned long long)drnas_long_conflicts,
        (unsigned long long)drnas_nonroot_units,
        (unsigned long long)drnas_nonroot_conflicts,
        (unsigned long long)drnas_traced_events
    );
    std::fflush(stdout);
}
'''
    edit(solver,'#include "solver.h"','#include "solver.h"\n'+api)
    edit(solver,'    //Handle special cases\n    switch (ps.size()) {',
         '    // Tag only clauses actually admitted at the native CMS input boundary.\n'
         '    drnas_mre4_trace_note_clause(ID, (uint32_t)ps.size());\n'
         '    //Handle special cases\n    switch (ps.size()) {')
    defcall='extern "C" void drnas_mre4_trace_event(int32_t, int, int, uint32_t);\n'
    edit(prop,'#include "propengine.h"','#include "propengine.h"\n'+defcall)
    edit(prop,
        '        enqueue<inprocess>(i->lit2(), currLevel, PropBy(~p, i->red(), i->get_ID()));',
        '        drnas_mre4_trace_event(i->get_ID(),0,1,currLevel);\n'
        '        enqueue<inprocess>(i->lit2(), currLevel, PropBy(~p, i->red(), i->get_ID()));')
    edit(prop,
        '        confl = PropBy(~p, i->red(), i->get_ID());',
        '        drnas_mre4_trace_event(i->get_ID(),1,1,currLevel);\n'
        '        confl = PropBy(~p, i->red(), i->get_ID());')
    edit(prop,
        '        handle_normal_prop_fail<inprocess>(c, offset, confl);',
        '        drnas_mre4_trace_event(c.stats.ID,1,0,currLevel);\n'
        '        handle_normal_prop_fail<inprocess>(c, offset, confl);')
    edit(prop,
        '    // Did not find watch -- clause is unit under assignment:\n    *j++ = *i;',
        '    // Did not find watch -- clause is unit under assignment:\n    *j++ = *i;')
    edit(prop,
        '        if (currLevel == decisionLevel()) {\n            enqueue<inprocess>(c[0], currLevel, PropBy(offset));',
        '        drnas_mre4_trace_event(c.stats.ID,0,0,currLevel);\n'
        '        if (currLevel == decisionLevel()) {\n            enqueue<inprocess>(c[0], currLevel, PropBy(offset));')
    assert MARKER in solver.read_text()
    report={"upstream":UPSTREAM,"marker":MARKER,
        "solver_sha256":hashlib.sha256(solver.read_bytes()).hexdigest(),
        "propengine_sha256":hashlib.sha256(prop.read_bytes()).hexdigest(),
        "limitations":["ID-level BCP reason events only, not all search influence",
         "one-thread single solver process only",
         "original CNF SAT model checked after solving",
         "on-the-fly Gauss explicitly disabled",
         "UNSAT lacks external LRAT proof"]}
    dest=source/"drnas-mre4-p2-patch.json"
    dest.write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
    print("MRE4_P2_PATCH_PASS",json.dumps(report,sort_keys=True),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("source")
    a=p.parse_args();main(a.source)
