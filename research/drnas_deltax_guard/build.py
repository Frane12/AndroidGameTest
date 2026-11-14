#!/usr/bin/env python3
"""DELTAX-GUARD1: exact-source proof gate + bounded same-state CDCL clones.

Builds a new solver only; main, X5/DELTA references and frozen CNFs never
change. The cloned runs are heuristic forecasts and cannot certify SAT/UNSAT.
"""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[2]
B=ROOT/"build"
PIN_CAUSAL_SOURCE="e896efbdf860ae9cbe6591b3d407ac1a32b508151522c83caabdf54b25c82962"

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def once(s,old,new):
    number=s.count(old)
    if number!=1:
        raise RuntimeError(f"DELTAX_GUARD_SOURCE_DRIFT count={number}, pattern={old[:120]!r}")
    return s.replace(old,new)

def main():
    subprocess.run(["python3",str(ROOT/"research/drnas_deltax/synthetic_causal_build.py")],
                   cwd=ROOT,check=True)
    source=B/"drnas_deltax_causal.cpp"
    assert sha(source)==PIN_CAUSAL_SOURCE,(
        "FROZEN_CAUSAL_SOURCE_CHANGED",sha(source))

    s=source.read_text()
    h=(B/"deltax_join.hpp").read_text()

    # A cached EXACT original-CNF fingerprint allows a fail-closed
    # independent parent/pivot/resolvent check before proof emission.
    h=once(h,
      "    std::set<std::vector<int>> deltax_binary_originals_;",
      """    std::set<std::vector<int>> deltax_binary_originals_;
    std::set<std::vector<int>> deltax_source_keys_;
    int64_t deltax_guard_bad_derivation_=0;
    int64_t deltax_guard_probes_=0,deltax_guard_rejected_=0;
    int64_t deltax_guard_selected_=0,deltax_guard_shadow_selected_=0;""")
    h=once(h,
      """        for(const auto& c:originals)
            if(c.size()==2 && std::abs(c[0])!=std::abs(c[1]))
                deltax_binary_originals_.insert(canonical(c));""",
      """        for(const auto& c:originals) {
            deltax_source_keys_.insert(canonical(c));
            if(c.size()==2 && std::abs(c[0])!=std::abs(c[1]))
                deltax_binary_originals_.insert(canonical(c));
        }""")
    h=once(h,
      """    void resolveDeltax(const Block& left,const Block& right,
                       const std::vector<int8_t>& values,
                       Output& out,Tick::time_point deadline) {""",
      """    void resolveDeltax(const Block& left,const Block& right,
                       const std::vector<int8_t>& values,
                       Output& out,Tick::time_point deadline,
                       const std::function<bool(const std::vector<int>&)>& approve) {""")
    h=once(h,
      """            if(known.count(c.clause))continue;
            ++submitted;++deltax_candidates_;
            const bool installed=join_mode=="deltax";""",
      """            if(known.count(c.clause))continue;
            // Strict original-source proof. Never submit a candidate
            // without BOTH source parents and the exact resolution pivot.
            std::vector<int> derived;
            for(int lit:c.parent_a)if(lit!=c.pivot)derived.push_back(lit);
            for(int lit:c.parent_b)if(lit!=-c.pivot)derived.push_back(lit);
            derived=canonical(std::move(derived));
            const bool valid=
                deltax_source_keys_.count(canonical(c.parent_a))!=0 &&
                deltax_source_keys_.count(canonical(c.parent_b))!=0 &&
                deltax_source_keys_.count(c.reverse)!=0 &&
                std::find(c.parent_a.begin(),c.parent_a.end(),c.pivot)!=c.parent_a.end() &&
                std::find(c.parent_b.begin(),c.parent_b.end(),-c.pivot)!=c.parent_b.end() &&
                derived==c.clause;
            if(!valid){++deltax_guard_bad_derivation_;continue;}
            ++submitted;++deltax_candidates_;
            bool trial_accepted=true;
            if(join_mode=="deltax-guard"||join_mode=="deltax-guard-shadow"){
                ++deltax_guard_probes_;
                trial_accepted=approve(c.clause);
                if(!trial_accepted) {
                    ++deltax_guard_rejected_;
                    continue; // MAIN CDCL is untouched: no proof/alias/clauses
                }
                if(join_mode=="deltax-guard-shadow")
                    ++deltax_guard_shadow_selected_;
                else ++deltax_guard_selected_;
            }
            const bool installed=join_mode=="deltax"||join_mode=="deltax-guard";""")
    h=once(h,
      '&&m!="deltax-shadow")',
      '&&m!="deltax-shadow"&&m!="deltax-guard"&&m!="deltax-guard-shadow")')
    h=once(h,
      '''if((join_mode=="deltax"||join_mode=="deltax-shadow") &&
                               deltax_witnesses_<4 && Tick::now()<deadline){
                                resolveDeltax(a,b,values,out,deadline);''',
      '''if((join_mode=="deltax"||join_mode=="deltax-shadow"||
                                join_mode=="deltax-guard"||join_mode=="deltax-guard-shadow") &&
                               deltax_witnesses_<4 && Tick::now()<deadline){
                                resolveDeltax(a,b,values,out,deadline,approve);''')
    h=once(h,
      '''    Output step(const std::vector<int8_t>& values,int64_t decisions,int64_t cdcl_conflicts,
                const std::function<void(const std::vector<int>&)>& emit){''',
      '''    Output step(const std::vector<int8_t>& values,int64_t decisions,int64_t cdcl_conflicts,
                const std::function<void(const std::vector<int>&)>& emit,
                const std::function<bool(const std::vector<int>&)>& approve){''')
    h=once(h,
      '''    void reportDeltax(const std::vector<int8_t>& values) const {''',
      '''    void reportDeltaxGuardSource()const {
        std::cerr<<"DELTAX_GUARD_SOURCE {\\\"source_clause_keys\\\":"
                 <<deltax_source_keys_.size()
                 <<",\\\"invalid_derivations_rejected\\\":"<<deltax_guard_bad_derivation_
                 <<",\\\"guard_probes\\\":"<<deltax_guard_probes_
                 <<",\\\"guard_rejected\\\":"<<deltax_guard_rejected_
                 <<",\\\"guard_selected\\\":"<<deltax_guard_selected_
                 <<",\\\"guard_shadow_selected\\\":"<<deltax_guard_shadow_selected_
                 <<"}\\n";
    }
    void reportDeltax(const std::vector<int8_t>& values) const {''')
    (B/"deltax_guard_join.hpp").write_text(h)

    s=once(s,'#include "deltax_join.hpp"','#include "deltax_guard_join.hpp"')
    s=once(s,"    int coop_hint_=-1;",
           (ROOT/"research/drnas_deltax_guard/guard_methods.inc").read_text()+
           "\n    int coop_hint_=-1;")
    s=once(s,
      '''        coop_.reportJoin(); coop_.reportDeltax(values_);''',
      '''        coop_.reportJoin(); coop_.reportDeltax(values_);
        coop_.reportDeltaxGuardSource(); reportDeltaxGuard();''')
    s=once(s,
      '''        auto out=coop_.step(values_,stats_.decisions,stats_.conflicts,
            [&](const std::vector<int>& c){writeProofClause(c);});''',
      '''        auto out=coop_.step(values_,stats_.decisions,stats_.conflicts,
            [&](const std::vector<int>& c){writeProofClause(c);},
            [&](const std::vector<int>& c){return deltaxGuardApprove(c);});''')
    src=B/"drnas_deltax_guard.cpp"
    src.write_text(s)
    out=B/"drnas-deltax-guard"
    subprocess.run(["g++","-std=c++20","-O3","-DNDEBUG","-Wall","-Wextra",
                    "-Wpedantic","-Werror","-DCOOP5_DYNAMIC_DEFAULT=0",
                    "-DCOOP52_FALLBACK_DEFAULT=0","-DCOOP53_REPAIR=1",
                    str(src),"-o",str(out)],check=True,cwd=ROOT)
    report={
        "binary_sha256":sha(out),
        "source_sha256":sha(src),
        "header_sha256":sha(B/"deltax_guard_join.hpp"),
        "source_only_originals":True,
        "copy_same_main_CDCL_before_probe":True,
        "clone_proofs_never_written":True,
        "clone_sat_unsat_never_credited":True,
        "failed_or_inconclusive_probe_rejects_before_main_insertion":True,
        "main_promoted":False,
        "compiler":subprocess.check_output(["g++","--version"],text=True).splitlines()[0]
    }
    (B/"DELTAX_GUARD_BUILD.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print("DELTAX_GUARD_BUILD",json.dumps(report,sort_keys=True),flush=True)

if __name__=="__main__":main()
