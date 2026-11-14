#!/usr/bin/env python3
"""DRNAS ΔCOOP1: exact local algebra -> CDCL marginal implication audit.

Generated from frozen COOP54B source; source X5/COOP modules/main are untouched.
One executable, three CLI modes: --coop4 off / observe / gate.
"observe" enumerates sound local consequences without proof/injection;
"gate" injects only already proof-certified clauses into CDCL.
"""
from pathlib import Path
import hashlib
import subprocess

ROOT=Path(__file__).resolve().parents[2]
B=ROOT/"build"

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def replace_once(src,old,new):
    number=src.count(old)
    if number!=1:
        raise RuntimeError(f"DELTA_SOURCE_DRIFT {number} expected=1, text={old[:120]!r}")
    return src.replace(old,new)

subprocess.run(["python3",str(ROOT/"research/drnas_coop54/build.py")],
               check=True,cwd=ROOT)
EXPECTED_COOP54B="5bb08736a569daa5b566767e4fe1a8338c6a40816e8e64a34c6bd23f75b35652"
assert sha(B/"drnas-coop54-gate")==EXPECTED_COOP54B,"FROZEN_COOP54B_SHA_MISMATCH"

h=(B/"coop52_big.hpp").read_text()
h=replace_once(h,"    int64_t gate_next_conflict=64;",
               "    int64_t gate_next_conflict=0; // ΔCOOP1: permit certified root inferences")
h=replace_once(
    h,
    "    int64_t gate_candidate_checks=0,gate_inactive_candidates=0;",
    """    int64_t delta_candidate_units=0,delta_candidate_conflicts=0;
    int64_t delta_candidate_inactive=0;
    int64_t gate_candidate_checks=0,gate_inactive_candidates=0;""")
h=replace_once(
    h,
    '''                auto key=canonical(clause);if(known.count(key)||out.clauses.size()>=8)return;
                if(mode=="observe")return;''',
    '''                auto key=canonical(clause);if(known.count(key)||out.clauses.size()>=8)return;
                // At a CDCL BCP fixpoint, a locally entailed non-satisfied
                // unit/conflict is a potential marginal inference. Count it
                // BEFORE the observe-mode return. This is NOT proof certification.
                bool delta_satisfied=false;
                int delta_unassigned=0;
                for(int lit:clause){
                    const int8_t v=values[static_cast<size_t>(std::abs(lit)-1)];
                    if(v==0)++delta_unassigned;
                    else if((v>0)==(lit>0)){delta_satisfied=true;break;}
                }
                if(!delta_satisfied){
                    if(delta_unassigned==0)++delta_candidate_conflicts;
                    else if(delta_unassigned==1)++delta_candidate_units;
                    else ++delta_candidate_inactive;
                }
                if(mode=="observe")return;''')
(B/"delta_coop1.hpp").write_text(h)

s=(B/"drnas_coop54_gate.cpp").read_text()
s=replace_once(s,'#include "coop52_big.hpp"','#include "delta_coop1.hpp"')
s=replace_once(s,
    '    int coop_hint_=-1;',
    r'''    int64_t delta_bridge_calls_=0,delta_direct_forces_=0;
    int64_t delta_cascade_forces_=0,delta_net_forces_=0;
    int64_t delta_conflict_lemmas_=0,delta_bridge_backtracks_=0;
    void reportDelta() const {
        std::cerr<<"DELTA_COOP1 {\"mode\":\""<<coop_.mode
                 <<"\",\"candidate_unit_events\":"<<coop_.delta_candidate_units
                 <<",\"candidate_conflict_events\":"<<coop_.delta_candidate_conflicts
                 <<",\"candidate_inactive_events\":"<<coop_.delta_candidate_inactive
                 <<",\"bridge_calls\":"<<delta_bridge_calls_
                 <<",\"certified_lemmas\":"<<coop_.lemmas
                 <<",\"direct_forces\":"<<delta_direct_forces_
                 <<",\"cascade_forces\":"<<delta_cascade_forces_
                 <<",\"same_level_new_assignments\":"<<delta_net_forces_
                 <<",\"live_bridge_conflicts\":"<<delta_conflict_lemmas_
                 <<",\"bridge_backtracks\":"<<delta_bridge_backtracks_
                 <<",\"mathematical_analysis_ms\":"<<coop_.ms
                 <<"}\n";
    }
    int coop_hint_=-1;''')
s=replace_once(s,
    '        coop_.report(); coop5Report(); reportCoop53();',
    '        coop_.report(); coop5Report(); reportCoop53(); reportDelta();')
s=replace_once(s,
    '''        const int bridge_level=decisionLevel();
        const size_t bridge_trail=trail_.size();
        bool bridge_mutated=false;''',
    '''        const int bridge_level=decisionLevel();
        const size_t bridge_trail=trail_.size();
        const int64_t direct_before=delta_direct_forces_;
        ++delta_bridge_calls_;
        bool bridge_mutated=false;''')
s=replace_once(s,
    '''                cancelUntil(maxlevel);++coop_.conflicts;
                return Prop{PropResult::CONFLICT,cid,0};''',
    '''                cancelUntil(maxlevel);++coop_.conflicts;
                ++delta_conflict_lemmas_;
                return Prop{PropResult::CONFLICT,cid,0};''')
s=replace_once(s,
    '''                bridge_mutated=true;
                // Assert at the highest antecedent level; root units survive restarts.''',
    '''                bridge_mutated=true;
                ++delta_direct_forces_;
                // Assert at the highest antecedent level; root units survive restarts.''')
s=replace_once(s,
    '''        const Prop completed=propagate(-1);
        const bool changed=bridge_mutated || bridge_trail!=trail_.size() ||''',
    '''        const Prop completed=propagate(-1);
        if(decisionLevel()!=bridge_level)++delta_bridge_backtracks_;
        if(completed.result==PropResult::OK &&
           decisionLevel()==bridge_level && trail_.size()>=bridge_trail){
            const auto gained=static_cast<int64_t>(trail_.size()-bridge_trail);
            const auto directly=delta_direct_forces_-direct_before;
            delta_net_forces_+=gained;
            delta_cascade_forces_+=std::max<int64_t>(0,gained-directly);
        }
        const bool changed=bridge_mutated || bridge_trail!=trail_.size() ||''')
src=B/"drnas_deltacoop1.cpp"
src.write_text(s)
out=B/"drnas-deltacoop1"
subprocess.run(["g++","-std=c++20","-O3","-DNDEBUG","-Wall","-Wextra",
                "-Wpedantic","-Werror","-DCOOP5_DYNAMIC_DEFAULT=0",
                "-DCOOP52_FALLBACK_DEFAULT=0","-DCOOP53_REPAIR=1",
                str(src),"-o",str(out)],check=True,cwd=ROOT)
print("DELTA_COOP1_BUILD",sha(out),flush=True)
print("DELTA_COOP1_PINNED_COOP54B",EXPECTED_COOP54B,flush=True)
