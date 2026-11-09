#!/usr/bin/env python3
"""X8 native causal instrumentation for CryptoMiniSat 5.11.15.

Apply AFTER the frozen X7 source patch. X8 uses semantic, sorted literal
hashes rather than allocator offsets or source-order-dependent clause IDs.
Trace-only branch (DRNAS_X8_TRACE=1) never changes solver choices. No trace
events are interpreted as independent proof of causality.
"""
from pathlib import Path
import argparse

HEADER = r'''#pragma once
#include <algorithm>
#include <atomic>
#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <vector>

namespace CMSat {
inline bool drnas_x8_enabled() {
    static const bool on = std::getenv("DRNAS_X8_TRACE") != nullptr;
    return on;
}
inline uint64_t drnas_x8_hash_data(std::vector<uint32_t> values) {
    std::sort(values.begin(), values.end());
    uint64_t h = 14695981039346656037ULL;
    for (auto v : values) {
        // Semantic hash over fixed-width little-endian literal integers.
        for (unsigned byte=0; byte<4; ++byte) {
            h ^= ((v >> (byte*8)) & 255U);
            h *= 1099511628211ULL;
        }
    }
    h ^= uint64_t(values.size());
    h *= 1099511628211ULL;
    return h;
}
inline uint64_t drnas_x8_hash_pair(uint32_t p, uint32_t q) {
    return drnas_x8_hash_data({p,q});
}
template<class ClauseLike>
inline uint64_t drnas_x8_hash_clause(const ClauseLike& c) {
    std::vector<uint32_t> vals;
    vals.reserve(c.size());
    for (const auto lit : c) vals.push_back(lit.toInt());
    return drnas_x8_hash_data(std::move(vals));
}
inline void drnas_x8_event(const char* kind,
    uint64_t conflicts, uint32_t level, int lit, uint64_t hash,
    uint32_t a, uint32_t b)
{
    static std::atomic<uint64_t> seq{0};
    if (!drnas_x8_enabled()) return;
    const auto n = seq.fetch_add(1, std::memory_order_relaxed);
    if (n >= 80000) return;
    std::cerr << "DRNAS_X8_EVENT seq=" << n << " kind=" << kind
              << " conf=" << conflicts << " level=" << level
              << " lit=" << lit << " hash=" << hash
              << " a=" << a << " b=" << b << '\n';
}
}
'''

def replace_exact(s,old,new,what):
    n=s.count(old)
    if n!=1:
        raise RuntimeError(f"X8_PATCH_FAIL_CLOSED {what} anchors={n}")
    return s.replace(old,new,1)

def patch(root):
    root=Path(root)
    header=root/"src"/"drnas_x8_trace.h"
    if header.exists():raise RuntimeError("X8_PATCH_FAIL_CLOSED already patched")
    header.write_text(HEADER)
    p=root/"src"/"propengine.h"
    s=p.read_text()
    s=replace_exact(s,'#include "drnas_x7_trace.h"',
                    '#include "drnas_x7_trace.h"\n#include "drnas_x8_trace.h"',
                    "propengine header include")
    old="    trail.push_back(Trail(p, level));"
    new=r'''    if (CMSat::drnas_x8_enabled()) {
        uint64_t clause_hash=0;
        if (!from.isNULL()) {
            if (from.getType() == PropByType::binary_t)
                clause_hash=CMSat::drnas_x8_hash_pair(p.toInt(), from.lit2().toInt());
            else if (from.getType() == PropByType::clause_t)
                clause_hash=CMSat::drnas_x8_hash_clause(*cl_alloc.ptr(from.get_offset()));
        }
        CMSat::drnas_x8_event(from.isNULL() ? (level ? "DECIDE" : "ROOT") : "IMPLY",
            sumConflicts, level, int(p.toInt()), clause_hash,
            static_cast<uint32_t>(from.getType()),
            static_cast<uint32_t>(trail.size()));
    }
''' + old
    s=replace_exact(s,old,new,"enqueue semantics")
    p.write_text(s)

    p=root/"src"/"propengine.cpp"
    s=p.read_text()
    s=replace_exact(s,'#include "drnas_x7_trace.h"',
                    '#include "drnas_x7_trace.h"\n#include "drnas_x8_trace.h"',
                    "propengine cpp include")
    old="    const lbool val = value(i->lit2());"
    new=r'''    if (CMSat::drnas_x8_enabled())
        CMSat::drnas_x8_event("WATCH_BIN", sumConflicts, currLevel,
            int(p.toInt()),
            CMSat::drnas_x8_hash_pair((~p).toInt(), i->lit2().toInt()),
            static_cast<uint32_t>(i->lit2().toInt()), 0);
''' + old
    s=replace_exact(s,old,new,"binary watch semantic clause")
    ptn="    //Blocked literal is satisfied, so clause is satisfied\n"
    extra=r'''    if (CMSat::drnas_x8_enabled()) {
        const Clause& watched = *cl_alloc.ptr(i->get_offset());
        CMSat::drnas_x8_event("WATCH_LONG", sumConflicts, currLevel,
            int(p.toInt()), CMSat::drnas_x8_hash_clause(watched),
            static_cast<uint32_t>(i->getBlockedLit().toInt()),
            static_cast<uint32_t>(watched.size()));
    }
'''
    s=replace_exact(s,ptn,extra+ptn,"long watch semantic clause")
    p.write_text(s)

    p=root/"src"/"searcher.cpp"
    s=p.read_text()
    s=replace_exact(s,'#include "drnas_x7_trace.h"',
                    '#include "drnas_x7_trace.h"\n#include "drnas_x8_trace.h"',
                    "searcher cpp include")
    old="    update_history_stats(backtrack_level, glue, connects_num_communities);"
    new=r'''    if (CMSat::drnas_x8_enabled())
        CMSat::drnas_x8_event("LEARN", sumConflicts, decisionLevel(),
            learnt_clause.empty() ? -1 : int(learnt_clause[0].toInt()),
            CMSat::drnas_x8_hash_clause(learnt_clause),
            glue, static_cast<uint32_t>(learnt_clause.size()));
''' + old
    s=replace_exact(s,old,new,"learnt canonical content/LBD")
    p.write_text(s)
    print("MRE_X8_PATCH_PASS watched_bin watched_long trail_reasons canonical_learn LBD",flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("source_dir")
    args=p.parse_args()
    patch(args.source_dir)
