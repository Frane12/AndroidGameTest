#!/usr/bin/env python3
"""R40: one strictly scoped native intervention in frozen v9.4 CaDiCaL probe.

The only active change is to permit the OLD v9.1 checkpoint-quality test to
apply phase hints on the EARLY-RESUME branch at conflict 256. Learned clauses,
decision rules, and first 256 conflicts are unchanged. Forced fallback is
a matched positive-action control, not a deployable policy.

No known R37/R38 outcomes or formula IDs influence this policy.
"""
from pathlib import Path
import argparse,hashlib
p=argparse.ArgumentParser()
p.add_argument("--source",required=True)
p.add_argument("--dest",required=True)
a=p.parse_args()
s=Path(a.source).read_text()
def once(before,after,expected=1):
 global s
 count=s.count(before)
 if count!=expected:raise RuntimeError(f"Patch anchor count {count} != {expected}: {before[:120]}")
 s=s.replace(before,after)
 # For defensive reproducibility, detect unintended overlap.
 print("R40_PATCH_ANCHOR_OK",expected,before[:54],flush=True)

once('policy!="v91_gate" && policy!="v91_always" && policy!="v91_never")',
     'policy!="v91_gate" && policy!="v91_always" && policy!="v91_never" &&\n'
     '       policy!="v91_rescue" && policy!="v91_force_fallback")')
once('policy=="v91_always" || policy=="v91_never")',
     'policy=="v91_always" || policy=="v91_never" ||\n'
     '       policy=="v91_rescue" || policy=="v91_force_fallback")',expected=3)
once('const bool apply=policy=="v91_always" ||\n'
     '                    (policy=="v91_gate" && a.v91_gate_quality);',
     'const bool apply=policy=="v91_always" ||\n'
     '                    ((policy=="v91_gate" || policy=="v91_rescue" ||\n'
     '                      policy=="v91_force_fallback") && a.v91_gate_quality);')
once('''        if(after==0) {
            // In never/skip arms, unphase() would itself alter later
            // phase state, violating the matched no-hint continuation.
            const bool is_v91=(policy=="v91_gate" ||
                               policy=="v91_always" || policy=="v91_never");
            if(!is_v91 || a.v91_phase_applied)
                for(const int lit:h.literals)solver.unphase(lit);
            auto next=Clock::now();
            a.status=solver.solve();''',
'''        if(after==0) {
            // R40: Only on first-256 EARLY-RESUME (no v7.6 extension).
            // Keep EXACT old v9.1 quality threshold. No hints were
            // applied during the first 256 conflicts.
            if(!a.extended &&
               (policy=="v91_rescue" || policy=="v91_force_fallback")) {
                const bool choose=policy=="v91_force_fallback" ||
                                  a.v91_gate_quality;
                if(choose && !h.literals.empty()) {
                    for(const int lit:h.literals)solver.phase(lit);
                    a.v91_phase_applied=true;
                    a.gate_reason=policy=="v91_rescue"?
                        "r40_rescue_fallback":"r40_forced_fallback";
                } else {
                    a.gate_reason=choose?"r40_no_hint_candidates":
                        "r40_quality_reject_fallback";
                }
            }
            // Preserve existing v9.1 unphase semantics on EXTENDED arms.
            // Do not immediately undo a NEW early-resume phase action.
            const bool is_v91=(policy=="v91_gate" ||
                               policy=="v91_always" || policy=="v91_never" ||
                               policy=="v91_rescue" ||
                               policy=="v91_force_fallback");
            if(!is_v91 || (a.v91_phase_applied && a.extended))
                for(const int lit:h.literals)solver.unphase(lit);
            auto next=Clock::now();
            a.status=solver.solve();''')
once('''        } else if(mode=="v91_quality_gate") {
            a=ablation(f,"v91_gate",false,seed,true);
        } else if(mode=="v91_always_late") {''',
'''        } else if(mode=="v91_quality_gate") {
            a=ablation(f,"v91_gate",false,seed,true);
        } else if(mode=="v91_rescue") {
            a=ablation(f,"v91_rescue",false,seed,true);
        } else if(mode=="v91_force_fallback") {
            a=ablation(f,"v91_force_fallback",false,seed,true);
        } else if(mode=="v91_always_late") {''')
dest=Path(a.dest);dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(s)
print("R40_NATIVE_PATCH_PASS",hashlib.sha256(s.encode()).hexdigest(),flush=True)
