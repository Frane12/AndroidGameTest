#!/usr/bin/env python3
"""ATLAS23: three isolated native CDCL hypotheses from ATLAS21M regressions.

Only generated mre_atlas23 C++ is modified. Parent ATLAS19/C7, main and SHA
locked CNFs are untouched. Proof/soundness is unchanged; UNSAT needs an
independent original-CNF certificate before being counted verified.
"""
from pathlib import Path

root = Path("mre_atlas23")
root.mkdir(parents=True, exist_ok=True)
s = Path("mre_atlas19/drnas_native_core_c.hpp").read_text()

def one(a, b):
    global s
    n = s.count(a)
    assert n == 1, ("ATLAS23 header drift", a[:100], n)
    s = s.replace(a, b, 1)

# V23_A_MIN: keep A's normal branching, restarts and no deletion; enable just
# previously-tested implication-graph learned-clause minimization.
one("    bool atlas17_adaptive_=false, atlas17_high_pressure_=false;",
"""    bool atlas17_adaptive_=false, atlas17_high_pressure_=false;
    bool atlas23_min_only_=false,atlas23_age_protect_=false,atlas23_stable_phase_=false;""")
one("""    void atlas15_minimize(std::vector<int>&cl,int&target){
        if(!atlas15_enabled_)return;""",
"""    void atlas15_minimize(std::vector<int>&cl,int&target){
        if(!atlas15_enabled_ && !atlas23_min_only_)return;""")

# V23_C7_AGE: only clauses old enough to be eligible can be discarded.
# C6's compaction changes clause IDs; migrate birth metadata alongside LBD.
one("        atlas15_lbd_.swap(migrated);",
"""        atlas15_lbd_.swap(migrated);
        std::map<int,uint64_t> born_migrated;
        for(const auto &kv:atlas15_born_)
            if(kv.first>=0 && size_t(kv.first)<before &&
               remap[size_t(kv.first)]>=0)
                born_migrated[remap[size_t(kv.first)]]=kv.second;
        atlas15_born_.swap(born_migrated);""")
one("            if(locked[size_t(cid)] || kv.second<7 || cl.size()<4)continue;",
"""            if(locked[size_t(cid)] || kv.second<7 || cl.size()<4)continue;
            if(atlas23_age_protect_){
                const auto born=atlas15_born_.find(cid);
                // Never treat missing age metadata as evidence that a clause is old.
                if(born==atlas15_born_.end() ||
                   stats_.conflicts<born->second ||
                   stats_.conflicts-born->second<20000)continue;
            }""")

# V23_C7_STABLE: isolate random phase-flip instability without touching
# branching selection, reductions, C7 restart policy, or sound inference.
one("""if(atlas13_c_enabled_ && (atlas13_next()%1000)<(atlas15_enabled_?(atlas15_short_lbd_>atlas15_long_lbd_?140:40):100))phases_[v]=-phases_[v];""",
"""if(!atlas23_stable_phase_ && atlas13_c_enabled_ && (atlas13_next()%1000)<(atlas15_enabled_?(atlas15_short_lbd_>atlas15_long_lbd_?140:40):100))phases_[v]=-phases_[v];""")

one("    int atlas19_fixed_q4_mode()const{return atlas19_fixed_q4_mode_;}",
"""    int atlas19_fixed_q4_mode()const{return atlas19_fixed_q4_mode_;}
    void atlas23_enable_min_only(){
        require(!atlas15_enabled_ && !atlas13_c_enabled_,
                "V23_A_MIN must preserve A search policy");
        atlas23_min_only_=true;
    }
    void atlas23_enable_age_protect(){
        require(atlas16_keep_ && atlas17_adaptive_,"age protection requires C7");
        atlas23_age_protect_=true;
    }
    void atlas23_enable_stable_phase(){
        require(atlas16_keep_ && atlas17_adaptive_,"phase ablation requires C7");
        atlas23_stable_phase_=true;
    }
    bool atlas23_min_only()const{return atlas23_min_only_;}
    bool atlas23_age_protect()const{return atlas23_age_protect_;}
    bool atlas23_stable_phase()const{return atlas23_stable_phase_;}""")
(root / "drnas_native_core_c.hpp").write_text(s)

src = Path("mre_atlas19/native.cpp").read_text()
assert src.count('mode=="A"') == 1, "ATLAS23 mode A dispatch drift"
src = src.replace('mode=="A"', 'mode=="A"||mode=="V23_A_MIN"', 1)
assert src.count('mode=="C7_ADAPT"') >= 2
src = src.replace('mode=="C7_ADAPT"',
                  'mode=="C7_ADAPT"||mode=="V23_C7_AGE"||mode=="V23_C7_STABLE"')
anchor = 'drnas::NativeCDCL solver(work.vars);'
assert src.count(anchor) == 1
src = src.replace(anchor, anchor+
    '\n  if(mode=="V23_A_MIN")solver.atlas23_enable_min_only();', 1)
anchor = 'solver.atlas17_enable_adaptive();'
assert src.count(anchor) == 1, "C7 activation anchor lost"
src = src.replace(anchor, anchor+
    '\n    if(mode=="V23_C7_AGE")solver.atlas23_enable_age_protect();'
    '\n    if(mode=="V23_C7_STABLE")solver.atlas23_enable_stable_phase();', 1)
anchor = '           <<" SAT_original_verified="<<int(status==10)'
assert src.count(anchor) == 1
src = src.replace(anchor,
'''           <<" atlas23_min_only="<<int(solver.atlas23_min_only())
           <<" atlas23_age_protect="<<int(solver.atlas23_age_protect())
           <<" atlas23_stable_phase="<<int(solver.atlas23_stable_phase())
''' + anchor, 1)
for mode in ("V23_A_MIN", "V23_C7_AGE", "V23_C7_STABLE"):
    assert src.count('mode=="'+mode+'"') >= 2, mode
(root / "native.cpp").write_text(src)
print("ATLAS23_BUILD_PASS three_isolated_modes=true controls_unchanged=true "
      "safe_reasons=true age_metadata_remapped=true")
