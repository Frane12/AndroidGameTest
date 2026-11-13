#!/usr/bin/env python3
"""GATE-R2 changes scheduling only, on the pinned X4.6/X4.5 probe/scorer.
No watch-order rollback claim: inherited probes restore assignments, not full state.
Original solver sources and the X4.6 builder are never edited.
"""
from pathlib import Path
import hashlib
import runpy

EXPECTED='9a25e1b0acc65261183bb6a7f1e8398a5c604984'
p=Path('research/build_x46_gate30.py')
b=p.read_bytes()
if hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()!=EXPECTED:
    raise RuntimeError('X4.6 builder not pinned')
runpy.run_path(str(p))
s=Path('build/drnas_x46_gate30.cpp').read_text()

def change(a,b,n=1):
    global s
    if s.count(a)!=n:raise RuntimeError('Patch anchor mismatch: '+a[:100])
    s=s.replace(a,b)

change('#include <algorithm>','#include "../src/drnas_gate_r2.hpp"\n#include <algorithm>')
change('    bool isX46() const {\n        return mode_=="x46_gate" || mode_=="x46_sparse";\n    }', '''    drnas::GateR2 gate_r2_;
    bool isGateR2() const {
        return mode_=="gate_r2" || mode_=="gate_r2_fixed";
    }
    bool isX46() const {
        return mode_=="x46_gate" || mode_=="x46_sparse" || isGateR2();
    }''')
change('    bool x46Permit() {\n        ++x46_calls_;', '''    bool x46Permit() {
        if (isGateR2()) {
            const bool adaptive=mode_=="gate_r2";
            if (!gate_r2_.due(stats_.decisions,stats_.conflicts,adaptive)) return false;
            return gate_r2_.affordable(stats_.decisions,stats_.conflicts,
                                      elapsed(),timeout_s_,probing_seconds_,adaptive);
        }
        ++x46_calls_;''')
change('        if (useful) ++x46_good_; else ++x46_bad_;', '''        if (isGateR2()) {
            gate_r2_.feedback(useful,stats_.decisions);
            return;
        }
        if (useful) ++x46_good_; else ++x46_bad_;''')
change('        probing_seconds_+=std::chrono::duration<double>(Clock::now()-start).count();', '''        const double gate_round_seconds=std::chrono::duration<double>(Clock::now()-start).count();
        probing_seconds_+=gate_round_seconds;
        if (isGateR2()) gate_r2_.cost(gate_round_seconds,elapsed(),probing_seconds_);''')
change('    void writeGateStats() const {\n        if (!isX46()) return;', '''    void writeGateStats() const {
        if (isGateR2()) { gate_r2_.write(std::cerr); return; }
        if (!isX46()) return;''')
change('&& mode!="x46_sparse" && mode!="x46_gate")',
       '&& mode!="x46_sparse" && mode!="x46_gate" && mode!="gate_r2" && mode!="gate_r2_fixed")')
change('(mode.rfind("x46_",0)==0?"X46_STATS ":(mode.rfind("x45_",0)==0?"X45_STATS ":"X41_STATS "))',
       '(mode.rfind("gate_r2",0)==0?"GATER2_STATS ":(mode.rfind("x46_",0)==0?"X46_STATS ":(mode.rfind("x45_",0)==0?"X45_STATS ":"X41_STATS ")))')
change('Usage: drnas-x45 <file.cnf> [--mode core|trace|x45_sham|x45_fixed|x45_online]',
       'Usage: drnas-gate-r2 <file.cnf> [--mode core|trace|x45_sham|x45_fixed|x45_online|x46_sparse|x46_gate|gate_r2|gate_r2_fixed]')
Path('build/drnas_gate_r2.cpp').write_text(s)
print('GATER2_PATCH_PASS',len(s.encode()),hashlib.sha256(s.encode()).hexdigest())
