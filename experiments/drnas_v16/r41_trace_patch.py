#!/usr/bin/env python3
"""R41 strictly observational stderr flush at 256 conflicts and before resume.

First apply the frozen R40 patch, then this tracer. R41 does not alter any
decision or propagate/learn logic. stderr lines flush BEFORE a possible hang.
"""
import argparse,hashlib
from pathlib import Path
p=argparse.ArgumentParser()
p.add_argument("--source",required=True);p.add_argument("--dest",required=True)
a=p.parse_args()
s=Path(a.source).read_text()
def once(old,new):
 global s
 count=s.count(old)
 if count!=1:raise RuntimeError("R41 anchor missing or ambiguous count="+str(count)+" "+old[:100])
 s=s.replace(old,new,1)
 print("R41_TRACE_PATCH_ANCHOR_PASS",old[:65],flush=True)
once('''        int after=a.stage1;
        if(a.extended) {''',
'''        // R41 immediate checkpoint record. Before ANY delayed phase action.
        // Only integer counters are used for prefix equality.
        std::cerr << "R41_CHECKPOINT"
                  << "\\tpolicy=" << policy
                  << "\\tstage1=" << a.stage1
                  << "\\textended=" << int(a.extended)
                  << "\\tquality=" << int(a.v91_gate_quality)
                  << "\\tlearned=" << a.v90_learned_256
                  << "\\tlbd2=" << a.v90_lbd2_256
                  << "\\tlbd4=" << a.v90_lbd4_256
                  << "\\tprops=" << a.v90_props_256
                  << "\\tconflicts=" << a.v90_conflicts_256
                  << "\\tbacktracks=" << a.v90_backtracks_256
                  << "\\thints=" << a.hints
                  << "\\tlearned_delta=" << a.learned_delta
                  << "\\tthreshold=" << a.threshold
                  << std::endl;
        int after=a.stage1;
        if(a.extended) {''')
once('''            auto next=Clock::now();
            a.status=solver.solve();''',
'''            // R41 flush before potentially long, unbounded continuation.
            std::cerr << "R41_RESUME"
                      << "\\tpolicy=" << policy
                      << "\\tstage1=" << a.stage1
                      << "\\textended=" << int(a.extended)
                      << "\\tquality=" << int(a.v91_gate_quality)
                      << "\\tphase_applied=" << int(a.v91_phase_applied)
                      << "\\treason=" << a.gate_reason
                      << "\\thints=" << a.hints
                      << std::endl;
            auto next=Clock::now();
            a.status=solver.solve();''')
out=Path(a.dest);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(s)
print("R41_TRACE_PATCH_PASS",hashlib.sha256(s.encode()).hexdigest(),flush=True)
