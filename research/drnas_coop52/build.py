#!/usr/bin/env python3
"""Build isolated COOP5.2 A/B variants without changing frozen source/main.

A: same COOP5 fixed 25ms gate, algebra collector raised 12k -> 24k clauses.
B: A plus second-best VSIDS fallback when Walsh supplies no valid hint.
Both preserve original BCP, CDCL learning, and RUP/DRAT mechanics.
"""
import hashlib
from pathlib import Path
import subprocess

R=Path(__file__).resolve().parents[2]
BUILD=R/"build"
def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()
def rep(s, old, new):
    if s.count(old)!=1:
        raise RuntimeError("COOP52 source drift: %r count=%d"%(old[:85],s.count(old)))
    return s.replace(old,new)

subprocess.run(["python3",str(R/"research/drnas_coop5/build.py")],check=True,cwd=R)
expected="4dc87df8c3dff7dee877563357117e9b21f3b9b4d9748bfdd569b005f9d8c8d5"
assert sha(BUILD/"drnas-coop5-fixed")==expected,"frozen COOP5 fixed baseline drift"
orig_h=(R/"research/drnas_coop4/coop.hpp").read_text()
new_h=rep(orig_h,"originals.size()>=12000","originals.size()>=24000")
(BUILD/"coop52_big.hpp").write_text(new_h)
source=(BUILD/"drnas_coop5.cpp").read_text()
source=rep(source,'#include "../research/drnas_coop4/coop.hpp"','#include "coop52_big.hpp"')
# The A/B candidates share identical expanded mathematical collector.
new_marker=(
    '    std::string coop5_mode_="off";'
)
source=rep(source,new_marker,
    '    int64_t coop52_fallback_candidates_=0;\n'
    '    int64_t coop52_fallback_pairs_=0;\n'
    '    static constexpr bool coop52_fallback_=COOP52_FALLBACK_DEFAULT!=0;\n'
    +new_marker)
source=rep(source,
    '    void reportCoop() const { coop_.report(); coop5Report(); }',
    '''    void reportCoop() const {
        coop_.report(); coop5Report();
        std::cerr<<"COOP52_GATE {\\\\\\"fallback_policy\\\\\\":"
                 <<(coop52_fallback_?"true":"false")
                 <<",\\\\\\"algebra_disabled\\\\\\":"<<(coop_.disabled?"true":"false")
                 <<",\\\\\\"originals_retained\\\\\\":"<<coop_.originals.size()
                 <<",\\\\\\"fallback_candidates\\\\\\":"<<coop52_fallback_candidates_
                 <<",\\\\\\"fallback_pairs\\\\\\":"<<coop52_fallback_pairs_
                 <<"}\\\\n";
    }'''.replace('\\\\\\"','\\"').replace('\\\\n','\\n'))
# The fallback variant gets to request an alternate even if the algebra
# returned no candidate or disabled collection for large CNFs.
old='''            if(coop_.mode=="on" && coop_hint_>=0 &&
               values_[coop_hint_]==0 && v>=0) {
                if(coop5_mode_=="off") {
                    if(v!=coop_hint_){offer(v);v=coop_hint_;++coop_.applied_hints;}
                } else {
                    v=coop5Choose(v);
                }
            }'''
new='''            if(coop_.mode=="on" && v>=0 &&
               (coop_hint_>=0 || coop52_fallback_)) {
                if(coop5_mode_=="off") {
                    if(coop_hint_>=0 && values_[coop_hint_]==0 &&
                       v!=coop_hint_) {
                        offer(v);v=coop_hint_;++coop_.applied_hints;
                    }
                } else {
                    v=coop5Choose(v);
                }
            }'''
source=rep(source,old,new)
old='''        if(coop5_mode_=="off" || coop_hint_<0 || baseline<0)
            return baseline;
        ++coop5_hints_;
        const int hint=coop_hint_;
        if(hint==baseline || values_[static_cast<size_t>(hint)]!=0)return baseline;
        ++coop5_candidates_;'''
new='''        if(coop5_mode_=="off" || baseline<0)return baseline;
        ++coop5_hints_;
        int hint=coop_hint_;
        bool fallback=false;
        if(hint<0 || hint==baseline ||
           values_[static_cast<size_t>(hint)]!=0) {
            if(!coop52_fallback_)return baseline;
            // Cheap deterministic eligibility gate BEFORE touching the heap.
            if(stats_.conflicts<64 ||
               stats_.decisions<coop5_next_decision_ || timedOut() ||
               (timeout_s_>0 && elapsed()>timeout_s_*0.90) ||
               coop5_spent_ms_>=coop5_budget_ms_)
                return baseline;
            const auto alternatives=topCandidates(2);
            if(alternatives.size()!=2 || alternatives[0]!=baseline)
                return baseline;
            hint=alternatives[1];
            fallback=true;
            ++coop52_fallback_candidates_;
        }
        ++coop5_candidates_;'''
source=rep(source,old,new)
source=rep(source,
    '        ++coop5_attempts_;\n        coop5_total_inspected_',
    '        ++coop5_attempts_;\n'
    '        if(fallback)++coop52_fallback_pairs_;\n'
    '        coop5_total_inspected_')
for variant,flag in (("cap24k","0"),("fallback","1")):
    f=BUILD/("drnas_coop52_"+variant+".cpp")
    f.write_text(source)
    out=BUILD/("drnas-coop52-"+variant)
    subprocess.run([
        "g++","-std=c++20","-O3","-DNDEBUG","-Wall","-Wextra",
        "-Wpedantic","-Werror","-DCOOP5_DYNAMIC_DEFAULT=0",
        "-DCOOP52_FALLBACK_DEFAULT="+flag,str(f),"-o",str(out)
    ],check=True,cwd=R)
    print("COOP52_BUILD",variant,sha(out),flush=True)
print("COOP52_FROZEN_REFERENCE",expected,flush=True)
