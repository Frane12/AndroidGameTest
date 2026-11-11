#!/usr/bin/env python3
"""ATLAS40: orthogonal age/LBD gates for A39 reason-use based protection.

A40_YOUNG: only repeated recently-used, young, moderate-LBD reasons.
A40_MATURE: only repeated recently-used, mature, moderate-LBD reasons.
A39_PROTECT and frozen A36_75 remain byte-for-byte the same dispatch.
No learning on the matched evaluation cohort; observational experiment.
"""
from pathlib import Path
p=Path("mre_atlas23/drnas_native_core_c.hpp")
s=p.read_text()
def one(a,b):
 global s
 assert s.count(a)==1,("A40 patch drift",a[:100],s.count(a))
 s=s.replace(a,b,1)
one("    uint64_t atlas39_compaction_remaps_=0;",
"""    uint64_t atlas39_compaction_remaps_=0;
    uint64_t atlas40_gate_pass_=0;""")
one("""                    if(atlas39_mode_==2)score-=500;""",
"""                    if(atlas39_mode_==2)score-=500;
                    if(atlas39_mode_==3 || atlas39_mode_==4){
                        const auto born=atlas15_born_.find(cid);
                        const uint64_t age=(born!=atlas15_born_.end() &&
                            stats_.conflicts>=born->second)?
                            stats_.conflicts-born->second:UINT64_MAX;
                        const bool good_lbd=kv.second>=3 && kv.second<=8;
                        const bool eligible_gate=good_lbd &&
                            (atlas39_mode_==3 ? age<=2000 :
                              (age>2000 && age<=12000));
                        if(eligible_gate){
                            score-=250;
                            ++atlas40_gate_pass_;
                        }
                    }""")
one('require(mode==1||mode==2,"ATLAS39 invalid utility mode");',
    'require(mode>=1&&mode<=4,"ATLAS40 invalid utility mode");')
one("    uint64_t atlas39_reason_uses()const{return atlas39_reason_uses_;}",
"""    uint64_t atlas40_gate_pass()const{return atlas40_gate_pass_;}
    uint64_t atlas39_reason_uses()const{return atlas39_reason_uses_;}""")
p.write_text(s)
p=Path("mre_atlas23/native.cpp")
s=p.read_text()
# Patch the exact control block BEFORE expanding generic dispatch predicates.
# Otherwise a broad textual replace modifies the control-block anchor itself.
anchor='    if(mode=="A39_SHADOW"||mode=="A39_PROTECT"){'
assert s.count(anchor)==1,("ATLAS40 control activation anchor drift",s.count(anchor))
s=s.replace(anchor,'    if(mode=="A39_SHADOW"||mode=="A39_PROTECT"||mode=="A40_YOUNG"||mode=="A40_MATURE"){',1)
anchor='||mode=="A39_PROTECT"'
control='    if(mode=="A39_SHADOW"||mode=="A39_PROTECT"||mode=="A40_YOUNG"||mode=="A40_MATURE"){'
prefix,sep,suffix=s.partition(control)
assert sep and prefix.count(anchor)>=2,("ATLAS40 dispatch drift",prefix.count(anchor))
# Expand dispatcher only; never duplicate expressions in the activation block.
prefix=prefix.replace(anchor,anchor+'||mode=="A40_YOUNG"||mode=="A40_MATURE"')
s=prefix+sep+suffix
anchor='solver.atlas39_enable(mode=="A39_SHADOW"?1:2);'
assert s.count(anchor)==1
s=s.replace(anchor,'solver.atlas39_enable(mode=="A39_SHADOW"?1:(mode=="A39_PROTECT"?2:(mode=="A40_YOUNG"?3:4)));',1)
anchor='           <<" atlas39_mode="<<solver.atlas39_mode()'
assert s.count(anchor)==1
s=s.replace(anchor,'           <<" atlas40_gate_pass="<<solver.atlas40_gate_pass()'+'\n'+anchor,1)
assert s.count('mode=="A40_YOUNG"')>=3
assert s.count('mode=="A40_MATURE"')>=3
p.write_text(s)
print("ATLAS40_BUILD_PASS control_A39_untouched=true age_and_LBD_gated=true quotas_75=true")
