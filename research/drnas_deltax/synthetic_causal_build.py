#!/usr/bin/env python3
"""DELTAX synthetic causality diagnostic with immutable reference executable.

The only new binary is build/drnas-deltax-causal, derived from the frozen
DELTAX native solver. All logical operations are identical; additional
instrumentation records each CDCL assignment whose actual reason is a
DELTAX-origin clause. No synthetic labels change inference heuristics.
"""
import hashlib
from pathlib import Path
import subprocess

R=Path(__file__).resolve().parents[2]
B=R/"build"

def once(src,old,new):
    n=src.count(old)
    if n!=1:raise RuntimeError(("DELTAX_SYNTH_SOURCE_DRIFT",n,old[:120]))
    return src.replace(old,new)

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    subprocess.run(["python3",str(R/"research/drnas_deltax/build.py")],
                   cwd=R,check=True)
    s=(B/"drnas_deltax.cpp").read_text()
    s=once(s,
        "    int coop_hint_=-1;",
        "    int64_t deltax_causal_propagations_=0,deltax_causal_events_logged_=0;\n"+
        "    int coop_hint_=-1;")
    s=once(s,
        "        coop_.reportJoin(); coop_.reportDeltax(values_);",
        r'''        coop_.reportJoin(); coop_.reportDeltax(values_);
        std::cerr<<"DELTAX_CAUSAL_STATS {\"real_enqueues_with_deltax_reason\":"
                 <<deltax_causal_propagations_
                 <<",\"logged_events\":"<<deltax_causal_events_logged_
                 <<"}\n";''')
    s=once(s,
        '''        trail_.push_back(lit);
        if(!probing_ && !x46_clone_)
            coop_.deltaxOnTrailChange(lit,values_);''',
        r'''        trail_.push_back(lit);
        if(!probing_ && !x46_clone_ && reason>=0 &&
           clauses_[static_cast<size_t>(reason)].deltax_origin) {
            // Causal provenance at CDCL enqueue, not merely a clause count.
            // Every other literal of the actual reason must currently
            // evaluate to FALSE; otherwise this is not legitimate UP.
            for(int other:clauses_[static_cast<size_t>(reason)].lits)
                if(other!=lit && value(other)!=-1)
                    throw std::runtime_error("DELTAX_NOT_ACTUALLY_UNIT_REASON");
            ++deltax_causal_propagations_;
            if(deltax_causal_events_logged_<8) {
                ++deltax_causal_events_logged_;
                std::cerr<<"DELTAX_CAUSAL_PROPAGATION {\"literal\":"<<lit
                         <<",\"decision_level\":"<<decisionLevel()
                         <<",\"reason_clause\":[";
                const auto& c=clauses_[static_cast<size_t>(reason)].lits;
                for(size_t i=0;i<c.size();++i){
                    if(i)std::cerr<<",";
                    std::cerr<<c[i];
                }
                std::cerr<<"]}\n";
            }
        }
        if(!probing_ && !x46_clone_)
            coop_.deltaxOnTrailChange(lit,values_);''')
    out=B/"drnas_deltax_causal.cpp"
    out.write_text(s)
    binary=B/"drnas-deltax-causal"
    subprocess.run(["g++","-std=c++20","-O3","-DNDEBUG","-Wall","-Wextra",
                   "-Wpedantic","-Werror","-DCOOP5_DYNAMIC_DEFAULT=0",
                   "-DCOOP52_FALLBACK_DEFAULT=0","-DCOOP53_REPAIR=1",
                   str(out),"-o",str(binary)],cwd=R,check=True)
    print("DELTAX_CAUSAL_BUILD",{
        "frozen_reference_sha256":sha(B/"drnas-deltax"),
        "instrumented_sha256":sha(binary),
        "causal_source_sha256":sha(out),
        "only_event_telemetry_added":True},flush=True)

if __name__=="__main__":main()
