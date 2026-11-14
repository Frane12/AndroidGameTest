#!/usr/bin/env python3
"""CDCL/COOP contract audit, and separately compiled lifecycle/hint repair.

Builds FROM immutable COOP5.2 cap24k generated C++; never modifies X5,
COOP4/COOP5 source files, other experimental branches, or main.

audit: observability + sampled speculative rollback checks; no policy changes.
repair: audit + discard bridge hints after trail mutation + synchronize
       COOP4 known signatures with ordinary CDCL learned-clause deletion.
"""
import hashlib
from pathlib import Path
import subprocess

R=Path(__file__).resolve().parents[2]
BUILD=R/"build"
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
def replace_once(s,needle,replacement):
    number=s.count(needle)
    if number!=1:
        raise RuntimeError(f"COOP53_CONTRACT_SOURCE_DRIFT count={number} pattern={needle[:100]!r}")
    return s.replace(needle,replacement)

subprocess.run(["python3",str(R/"research/drnas_coop52/build.py")],cwd=R,check=True)
FROZEN_SHA="4dc87df8c3dff7dee877563357117e9b21f3b9b4d9748bfdd569b005f9d8c8d5"
BASE_SHA="3a63a6696e06e3d6dbe089dde07c9c971e97a105043ca3ecd0aaea71e4e3d948"
assert sha(BUILD/"drnas-coop5-fixed")==FROZEN_SHA,"COOP5 baseline binary drift"
assert sha(BUILD/"drnas-coop52-cap24k")==BASE_SHA,"COOP52 cap24k baseline binary drift"

s=(BUILD/"drnas_coop52_cap24k.cpp").read_text()

# Small audit fields. No branch heuristic changed in audit-only mode.
old='    int coop_hint_=-1;'
extra=r'''    static constexpr bool coop53_repair_=COOP53_REPAIR!=0;
    int64_t coop53_probe_checks_=0,coop53_bridge_calls_=0;
    int64_t coop53_hints_invalidated_=0,coop53_hints_stale_observed_=0;
    int64_t coop53_lemmas_tracked_=0,coop53_known_forgets_=0;
    void reportCoop53() const {
        std::cerr<<"COOP53_CONTRACT {\"repair\":"<<(coop53_repair_?"true":"false")
                 <<",\"probe_rollback_checks\":"<<coop53_probe_checks_
                 <<",\"bridge_calls\":"<<coop53_bridge_calls_
                 <<",\"bridge_hints_stale_observed\":"<<coop53_hints_stale_observed_
                 <<",\"bridge_hints_invalidated\":"<<coop53_hints_invalidated_
                 <<",\"component_lemmas_tracked\":"<<coop53_lemmas_tracked_
                 <<",\"known_keys_forgotten_after_cdcl_deletion\":"<<coop53_known_forgets_
                 <<",\"active_component_id_count\":"<<coop4_ids_.size()
                 <<",\"qhead_at_fixpoint\":"<<(qhead_==static_cast<int>(trail_.size())?"true":"false")
                 <<"}\n";
    }
    int coop_hint_=-1;'''
s=replace_once(s,old,extra)
s=replace_once(s,'        coop_.report(); coop5Report();',
                 '        coop_.report(); coop5Report(); reportCoop53();')

# Probe contract: sample 24 probes; assignment stack, phase and BCP cursor
# must be restored. Watcher movement is explicitly allowed and revalidated by
# ordinary CDCL and original CNF proof checks, not byte-for-byte equality.
s=replace_once(s,
'''    Probe probe(int lit,int max_inspections=900) {
        const int original_level=decisionLevel();
        const int original_trail=static_cast<int>(trail_.size());
        probing_=true;''',
'''    Probe probe(int lit,int max_inspections=900) {
        const int original_level=decisionLevel();
        const int original_trail=static_cast<int>(trail_.size());
        const bool audit_this=coop53_probe_checks_<24;
        const std::vector<int> saved_trail=audit_this?trail_:std::vector<int>{};
        const std::vector<int8_t> saved_phase=audit_this?phase_:std::vector<int8_t>{};
        const int saved_qhead=qhead_;
        probing_=true;''')
s=replace_once(s,
'''        cancelUntil(original_level);
        probing_=false;
        return r;
    }
    int selectVariable()''',
'''        cancelUntil(original_level);
        probing_=false;
        if(audit_this){
            if(decisionLevel()!=original_level || trail_!=saved_trail ||
               phase_!=saved_phase || qhead_!=saved_qhead)
                throw std::runtime_error("COOP53_SPECULATIVE_PROBE_STATE_LEAK");
            ++coop53_probe_checks_;
        }
        return r;
    }
    int selectVariable()''')

# Measure the bridge boundary, including case where learned, proved clauses
# cause backtracking or propagation and make an earlier hint stale.
s=replace_once(s,
'''        if(!coop_.enabled() || x46_clone_)return Prop{};
        auto out=coop_.step(values_,stats_.decisions,stats_.conflicts,''',
'''        if(!coop_.enabled() || x46_clone_)return Prop{};
        ++coop53_bridge_calls_;
        const int bridge_level=decisionLevel();
        const size_t bridge_trail=trail_.size();
        bool bridge_mutated=false;
        auto out=coop_.step(values_,stats_.decisions,stats_.conflicts,''')
s=replace_once(s,
'''            if(sat)continue;
            if(free==0){''',
'''            if(sat)continue;
            if(free==0){
                if(coop53_repair_ && coop_hint_>=0){
                    ++coop53_hints_invalidated_;coop_hint_=-1;
                }''')
s=replace_once(s,
'''            if(free==1){
                // Assert at the highest antecedent level; root units survive restarts.''',
'''            if(free==1){
                bridge_mutated=true;
                // Assert at the highest antecedent level; root units survive restarts.''')
s=replace_once(s,
'''        return propagate(-1);
    }
    void configureX5(''',
'''        const Prop completed=propagate(-1);
        const bool changed=bridge_mutated || bridge_trail!=trail_.size() ||
                           bridge_level!=decisionLevel() ||
                           completed.result!=PropResult::OK;
        if(changed && coop_hint_>=0){
            ++coop53_hints_stale_observed_;
            if(coop53_repair_){
                ++coop53_hints_invalidated_;
                coop_hint_=-1;
            }
        }
        if(completed.result==PropResult::OK &&
           qhead_!=static_cast<int>(trail_.size()))
            throw std::runtime_error("COOP53_BRIDGE_NONFIXPOINT_RETURN");
        return completed;
    }
    void configureX5(''')

# CDCL owns clause lifecycle. In repair build, track ALL non-original
# certified COOP4 lemmas, not only "retain" policy. Their IDs already
# participate in the existing remap on CDCL garbage collection.
s=replace_once(s,
'''            clauses_[cid].glue=computeGlue(clauses_[cid].lits);
            if(coop_.mode=="retain") {''',
'''            clauses_[cid].glue=computeGlue(clauses_[cid].lits);
            if(coop53_repair_ && coop_.mode!="retain"){
                clauses_[cid].coop4_origin=true;
                coop4_ids_.push_back(cid);
                ++coop53_lemmas_tracked_;
            }
            if(coop_.mode=="retain") {''')
# Ordinary learned-clause reduction may delete certified COOP4 clauses.
# Drop only that clause's signature, allowing its independent re-certification.
# Original CNF signatures were never inserted as new COOP lemmas.
s=replace_once(s,
'''                clauses_[candidates[k]].deleted=true;
                ++stats_.reduce_removed;''',
'''                const int cid=candidates[k];
                if(coop53_repair_ && clauses_[cid].coop4_origin &&
                   coop_.known.erase(drnas_coop4::canonical(clauses_[cid].lits))!=0)
                    ++coop53_known_forgets_;
                clauses_[cid].deleted=true;
                ++stats_.reduce_removed;''')

for variant,flag in (("audit","0"),("repair","1")):
    src=BUILD/("drnas_coop53_"+variant+".cpp")
    src.write_text(s)
    out=BUILD/("drnas-coop53-"+variant)
    subprocess.run([
        "g++","-std=c++20","-O3","-DNDEBUG",
        "-Wall","-Wextra","-Wpedantic","-Werror",
        "-DCOOP5_DYNAMIC_DEFAULT=0","-DCOOP52_FALLBACK_DEFAULT=0",
        "-DCOOP53_REPAIR="+flag,str(src),"-o",str(out)
    ],cwd=R,check=True)
    print("COOP53_BUILD",variant,sha(out),flush=True)
print("COOP53_BASELINE_COOP52_SHA",BASE_SHA,flush=True)
print("COOP53_SOURCE_CONTRACT_PATCHED",flush=True)
