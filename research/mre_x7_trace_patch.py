#!/usr/bin/env python3
"""Patch only CryptoMiniSat 5.11.15 diagnostic event sites (no search-policy edits).

Trace is OFF by default. With DRNAS_X7_TRACE=1, a single-thread solver emits
the earliest watched-clause examinations, trail assignments, and learnt LBDs.
The C++ code intentionally logs source-level observations, not inferred causes.
"""
import argparse
from pathlib import Path

HEADER = r'''#pragma once
#include <atomic>
#include <cstdlib>
#include <iostream>
namespace CMSat {
inline std::atomic<unsigned long long> drnas_x7_seq{0};
inline void drnas_x7_event(const char* kind,
                          unsigned long long conflicts, unsigned level,
                          int lit, unsigned long long a, unsigned long long b) {
    static const bool enabled = std::getenv("DRNAS_X7_TRACE") != nullptr;
    if (!enabled) return;
    auto n = drnas_x7_seq.fetch_add(1, std::memory_order_relaxed);
    if (n >= 4000) return;
    std::cerr << "DRNAS_X7_EVENT seq=" << n
              << " kind=" << kind << " conf=" << conflicts
              << " level=" << level << " lit=" << lit
              << " a=" << a << " b=" << b << "\n";
}
}
'''

def replace_once(text, old, new, label):
    n = text.count(old)
    if n != 1:
        raise RuntimeError(f"X7_PATCH_FAIL_CLOSED {label} anchors={n}")
    return text.replace(old, new, 1)

def patch(root):
    root = Path(root)
    file = root / "src" / "drnas_x7_trace.h"
    if file.exists():
        raise RuntimeError("X7_PATCH_FAIL_CLOSED preexisting header")
    file.write_text(HEADER)

    p = root / "src" / "propengine.h"
    t = p.read_text()
    t = replace_once(t, "#pragma once", '#pragma once\n#include "drnas_x7_trace.h"', "prop header")
    # Log the reason type; reason NULL identifies a decision while root enqueue is separate.
    old = "    trail.push_back(Trail(p, level));"
    new = '''    CMSat::drnas_x7_event(from.isNULL() ? (level ? "DECIDE" : "ROOT")
                                : "IMPLY",
                           sumConflicts, level, int(p.toInt()),
                           static_cast<unsigned long long>(from.getType()),
                           static_cast<unsigned long long>(trail.size()));
''' + old
    t = replace_once(t, old, new, "trail enqueue")
    p.write_text(t)

    p = root / "src" / "propengine.cpp"
    t = p.read_text()
    t = replace_once(t, '#include "propengine.h"',
                     '#include "propengine.h"\n#include "drnas_x7_trace.h"', "prop include")
    old = """    const lbool val = value(i->lit2());
    if (val == l_Undef) {"""
    new = '''    CMSat::drnas_x7_event("WATCH_BIN", sumConflicts, currLevel,
                           int(p.toInt()), static_cast<unsigned long long>(i->lit2().toInt()),
                           static_cast<unsigned long long>(i->get_ID()));
''' + old
    t = replace_once(t, old, new, "binary watched clause")
    old = """    //Blocked literal is satisfied, so clause is satisfied
    if (value(i->getBlockedLit()) == l_True) {"""
    new = '''    CMSat::drnas_x7_event("WATCH_LONG", sumConflicts, currLevel,
                           int(p.toInt()),
                           static_cast<unsigned long long>(i->getBlockedLit().toInt()),
                           static_cast<unsigned long long>(i->get_offset()));
''' + old
    t = replace_once(t, old, new, "long watched clause")
    p.write_text(t)

    p = root / "src" / "searcher.cpp"
    t = p.read_text()
    t = replace_once(t, '#include "searcher.h"',
                     '#include "searcher.h"\n#include "drnas_x7_trace.h"', "search include")
    old = """    print_learnt_clause();

    update_history_stats(backtrack_level, glue, connects_num_communities);"""
    new = '''    print_learnt_clause();
    CMSat::drnas_x7_event("LEARN_LBD", sumConflicts, decisionLevel(),
                           learnt_clause.empty() ? -1 : int(learnt_clause[0].toInt()),
                           static_cast<unsigned long long>(glue),
                           static_cast<unsigned long long>(learnt_clause.size()));

    update_history_stats(backtrack_level, glue, connects_num_communities);'''
    t = replace_once(t, old, new, "learnt LBD")
    p.write_text(t)
    print("MRE_X7_SOURCE_TRACE_PATCH_PASS watch_bin watch_long trail learn_lbd")

if __name__ == "__main__":
    a = argparse.ArgumentParser()
    a.add_argument("source_dir")
    patch(a.parse_args().source_dir)
