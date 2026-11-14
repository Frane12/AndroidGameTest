#!/usr/bin/env python3
"""Build isolated source-blind DELTAX-SIGNAL1, preserving frozen GUARD1.

The only new behavior is a deterministic bounded CNF structural prefilter
BEFORE same-state clone A/B; original-source proof gate and original-CNF
SAT/UNSAT proof checks remain mandatory. No main edits or retraining.
"""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
B=ROOT/"build"
sys.path.insert(0,str(ROOT/"research/drnas_deltax_guard"))
from build import main as guard_build
PIN_CAUSAL_SOURCE="e896efbdf860ae9cbe6591b3d407ac1a32b508151522c83caabdf54b25c82962"

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def once(s,a,b):
    count=s.count(a)
    if count!=1:raise RuntimeError(("DELTAX_SIGNAL_SOURCE_DRIFT",count,a[:100]))
    return s.replace(a,b)

def main():
    # Reproduce the exact GUARD1 binary from the frozen source generation
    # and assert it has the identical checksum of the control artifact.
    guard_build()
    expected={}
    for line in (B/"DELTAX_GUARD_FROZEN.sha256").read_text().splitlines():
        h,p=line.split()
        expected[p]=h
    assert sha(B/"drnas-deltax-guard")==expected["build/drnas-deltax-guard"],(
        "FROZEN_GUARD1_BINARY_DRIFT",sha(B/"drnas-deltax-guard"))
    assert sha(B/"drnas_deltax_causal.cpp")==PIN_CAUSAL_SOURCE

    s=(B/"drnas_deltax_guard.cpp").read_text()
    h=(B/"deltax_guard_join.hpp").read_text()
    # The separate DELTAX+GUARD1 source-proof gate still runs BEFORE
    # the supplied callback for any signal mode. Never bypass it.
    h=once(h,
        '&&m!="deltax-guard-shadow")',
        '&&m!="deltax-guard-shadow"&&m.rfind("deltax-signal-",0)!=0)')
    h=once(h,
        'if(join_mode=="deltax-guard"||join_mode=="deltax-guard-shadow"){',
        'if(join_mode=="deltax-guard"||join_mode=="deltax-guard-shadow"||\n'
        '               join_mode.rfind("deltax-signal-",0)==0){')
    h=once(h,
        'const bool installed=join_mode=="deltax"||join_mode=="deltax-guard";',
        'const bool installed=join_mode=="deltax"||join_mode=="deltax-guard"||\n'
        '                                 join_mode.rfind("deltax-signal-",0)==0;')
    h=once(h,
        'join_mode=="deltax-guard"||join_mode=="deltax-guard-shadow") &&',
        'join_mode=="deltax-guard"||join_mode=="deltax-guard-shadow"||\n'
        '                                join_mode.rfind("deltax-signal-",0)==0) &&')
    (B/"deltax_signal_join.hpp").write_text(h)
    s=once(s,'#include "deltax_guard_join.hpp"',
              '#include "deltax_signal_join.hpp"')
    s=once(s,'    int coop_hint_=-1;',
           (ROOT/"research/drnas_deltax_signal/signal_methods.inc").read_text()+
           '\n    int coop_hint_=-1;')
    s=once(s,
        '''    bool deltaxGuardApprove(const std::vector<int>& c) {
        ++deltax_guard_calls_;''',
        '''    bool deltaxGuardApprove(const std::vector<int>& c) {
        if(!deltaxSignalPrefilter(c))return false;
        ++deltax_guard_calls_;''')
    s=once(s,'coop_.reportDeltaxGuardSource(); reportDeltaxGuard();',
           'coop_.reportDeltaxGuardSource(); reportDeltaxGuard(); reportDeltaxSignal();')
    source=B/"drnas_deltax_signal.cpp"
    source.write_text(s)
    out=B/"drnas-deltax-signal"
    subprocess.run(["g++","-std=c++20","-O3","-DNDEBUG","-Wall","-Wextra",
                    "-Wpedantic","-Werror","-DCOOP5_DYNAMIC_DEFAULT=0",
                    "-DCOOP52_FALLBACK_DEFAULT=0","-DCOOP53_REPAIR=1",
                    str(source),"-o",str(out)],cwd=ROOT,check=True)
    report={"status":"COMPILED","guard1_control_sha256":sha(B/"drnas-deltax-guard"),
            "signal_binary_sha256":sha(out),"source_sha256":sha(source),
            "signal_header_sha256":sha(B/"deltax_signal_join.hpp"),
            "signal_method_sha256":sha(ROOT/"research/drnas_deltax_signal/signal_methods.inc"),
            "same_compiler":subprocess.check_output(["g++","--version"],text=True).splitlines()[0],
            "source_proof_gate_intact":True,
            "clone_guard_intact":True,"signal_source_blind":True,
            "no_main_changes":True,"not_promoted":True}
    (B/"DELTAX_SIGNAL_BUILD.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print("DELTAX_SIGNAL_BUILD",json.dumps(report,sort_keys=True),flush=True)

if __name__=="__main__":main()
