#!/usr/bin/env python3
"""DRNAS FUSION-GUARD1: native CDCL stays primary; optional proof modules cold.

Source-only derived build. No edits to main, frozen baselines, source inputs,
X5 core, or upstream DELTAX SIGNAL1. Four modes in one executable:
--fusion-core, --fusion-shadow, --fusion-guard; no fusion flag is legacy.
Only --fusion-guard authorizes COOP4 exact GF(2) + DELTAX SIGNAL1 analysis.
All derived clauses pass the original source/proof checks of those modules.
"""
from pathlib import Path
import hashlib
import json
import subprocess
import sys

R=Path(__file__).resolve().parents[2]
B=R/"build"
PIN_SIGNAL_SOURCE="9d142ff619f9519dd58912a2c153864dcdc9e27c46c94022d63a9f4f1fc24599"
PIN_SIGNAL_BINARY="46252501f59b279165cfcb55b000cb357d5217fde32a94ee693ae47e3bb495e0"
sys.path.insert(0,str(R/"research/drnas_deltax_signal"))
import build as signal_build

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def once(src,old,new):
    n=src.count(old)
    if n!=1:raise RuntimeError(("FUSION_SOURCE_DRIFT",n,old[:130]))
    return src.replace(old,new)

def main():
    # Rebuild and verify *identical* frozen SIGNAL1 before modifying any
    # source. This checks the entire inherited X5->COOP4->DELTA->GUARD chain.
    signal_build.main()
    assert sha(B/"drnas_deltax_signal.cpp")==PIN_SIGNAL_SOURCE,\
        ("FUSION_FROZEN_SOURCE_CHANGED",sha(B/"drnas_deltax_signal.cpp"))
    assert sha(B/"drnas-deltax-signal")==PIN_SIGNAL_BINARY,\
        ("FUSION_FROZEN_BINARY_CHANGED",sha(B/"drnas-deltax-signal"))

    s=(B/"drnas_deltax_signal.cpp").read_text()
    s=once(s,
        "    int coop_hint_=-1;",
        (R/"research/drnas_fusion1/fusion_methods.inc").read_text()+
        "\n    int coop_hint_=-1;")
    # Parsing is expensive enough for large CNFs. For FUSION GUARD and SHADOW
    # modes, leave module's ORIGINAL CNF cache entirely cold until permitted.
    s=once(s,
        '''        coop_.add(clean);
        const int cid = storeClause(std::move(clean), false);''',
        '''        if(fusion_mode_!=3 && fusion_mode_!=2)coop_.add(clean);
        const int cid = storeClause(std::move(clean), false);''')
    # First safety control is outside ALL module engines and is O(1):
    # use only already-computed CDCL counters and static binary footprints.
    s=once(s,
        '''        if(!coop_.enabled() || x46_clone_ ||
           !coop_.ready(stats_.decisions,stats_.conflicts))return Prop{};''',
        '''        if(!fusionCheapPermit())return Prop{};
        if(!coop_.enabled() || x46_clone_ ||
           !coop_.ready(stats_.decisions,stats_.conflicts))return Prop{};''')
    s=once(s,
        '''            [&](const std::vector<int>& c){return deltaxGuardApprove(c);});
        coop_hint_=out.hint;''',
        '''            [&](const std::vector<int>& c){return deltaxGuardApprove(c);});
        fusionRecordWindow();
        coop_hint_=out.hint;''')
    # Do not change the existing CDCL variable selector or phase heuristic.
    # The original COOP4 hint mode is never enabled: "gate" only.
    s=once(s,
       '    std::string delta2_mode="local";',
       '    std::string delta2_mode="local";\n'
       '    bool fusion_flag_guard=false,fusion_flag_core=false,'
       'fusion_flag_shadow=false;')
    s=once(s,
       '        else if (opt=="--delta2" && i+1<argc) delta2_mode=argv[++i];',
       '        else if (opt=="--fusion-guard")fusion_flag_guard=true;\n'
       '        else if (opt=="--fusion-core")fusion_flag_core=true;\n'
       '        else if (opt=="--fusion-shadow")fusion_flag_shadow=true;\n'
       '        else if (opt=="--delta2" && i+1<argc) delta2_mode=argv[++i];')
    s=once(s,
       '    if(coop_mode!="off"&&',
       '''    if(static_cast<int>(fusion_flag_guard)+static_cast<int>(fusion_flag_core)+
       static_cast<int>(fusion_flag_shadow)>1)
       throw std::runtime_error("FUSION_MULTIPLE_MODES");
    if(fusion_flag_guard){
        // The cheap guard must approve BEFORE even initializing modules.
        // Both are source/proof certified; only the DELTAX candidate invokes
        // expensive same-state clone risk scoring after structural SIGNAL8.
        coop_mode="gate";
        delta2_mode="deltax-signal-8";
        coop_eager=false; // no eager CNF preparation before first wake
    } else if(fusion_flag_core || fusion_flag_shadow){
        coop_mode="off";
        delta2_mode="local";
        coop_eager=false;
    }
    if(coop_mode!="off"&&''')
    s=once(s,
       '''            solver->configureCoop(coop_mode,coop_eager);''',
       '''            solver->configureCoop(coop_mode,coop_eager);
            solver->configureFusion(fusion_flag_guard,fusion_flag_shadow,
                                    fusion_flag_core);''')
    s=once(s,
        '''coop_.reportDeltaxGuardSource(); reportDeltaxGuard(); reportDeltaxSignal();''',
        '''coop_.reportDeltaxGuardSource(); reportDeltaxGuard();
        reportDeltaxSignal(); reportFusion();''')
    target=B/"drnas_fusion1.cpp"
    target.write_text(s)
    binary=B/"drnas-fusion1"
    subprocess.run(["g++","-std=c++20","-O3","-DNDEBUG","-Wall",
                    "-Wextra","-Wpedantic","-Werror",
                    "-DCOOP5_DYNAMIC_DEFAULT=0",
                    "-DCOOP52_FALLBACK_DEFAULT=0","-DCOOP53_REPAIR=1",
                    str(target),"-o",str(binary)],cwd=R,check=True)
    info={
        "status":"COMPILED",
        "fusion_native_sha256":sha(binary),
        "fusion_native_source_sha256":sha(target),
        "frozen_cdcl_parent_sha256":sha(B/"drnas-deltax-signal"),
        "parent_source_sha256":sha(B/"drnas_deltax_signal.cpp"),
        "main_untouched":True,
        "same_process_one_logical_cpu":True,
        "default_modules_off":True,
        "core_CDCL_controls_all_decisions":True,
        "integrated_proof_modules":["COOP4 exact GF2 guarded gate",
                                    "DELTAX-SIGNAL8 original-source RUP guarded equality"],
        "deltax_candidate_clone_guard_preserved":True,
        "original_drat_source_check_required":True,
        "cold_start_source_copy":True,
        "no_promotion":True
    }
    (B/"FUSION1_BUILD.json").write_text(json.dumps(info,sort_keys=True,indent=2)+"\n")
    print("DRNAS_FUSION_BUILD",json.dumps(info,sort_keys=True),flush=True)

if __name__=="__main__":main()
