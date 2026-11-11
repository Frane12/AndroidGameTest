#!/usr/bin/env python3
"""ATLAS23: isolated conservative learned-clause deletion from ATLAS19.
C10: 1/32 each 6000 conflicts. C11: 1/64 each 10000 conflicts.
Frozen A/C7 controls unchanged. Existing low-LBD and locked-clause protections inherited.
"""
from pathlib import Path
root=Path("mre_atlas23");root.mkdir(exist_ok=True)
s=Path("mre_atlas19/drnas_native_core_c.hpp").read_text()
def one(a,b):
 global s
 assert s.count(a)==1,(a,s.count(a))
 s=s.replace(a,b,1)
one("    int atlas19_fixed_q4_mode_=0;", "    int atlas23_conservative_mode_=0; // 1=1/32@6000, 2=1/64@10000\n    int atlas19_fixed_q4_mode_=0;")
one("                    (atlas19_fixed_q4_mode_==1 && stats_.conflicts%1500==0) ||",
"""                    (atlas23_conservative_mode_==1 && stats_.conflicts%6000==0) ||
                    (atlas23_conservative_mode_==2 && stats_.conflicts%10000==0) ||
                    (atlas19_fixed_q4_mode_==1 && stats_.conflicts%1500==0) ||""")
one("                    (!atlas17_adaptive_ && !atlas19_fixed_q4_mode_",
"                    (!atlas17_adaptive_ && !atlas19_fixed_q4_mode_ && !atlas23_conservative_mode_")
one("        const size_t divisor=atlas19_fixed_q4_mode_?4:",
"        const size_t divisor=atlas23_conservative_mode_?(atlas23_conservative_mode_==1?32:64):atlas19_fixed_q4_mode_?4:")
one("    int atlas19_fixed_q4_mode()const{return atlas19_fixed_q4_mode_;}",
"""    int atlas19_fixed_q4_mode()const{return atlas19_fixed_q4_mode_;}
    void atlas23_enable_conservative(int mode){
        require(atlas16_keep_ && !atlas17_adaptive_ &&
                !atlas19_fixed_q4_mode_ && !atlas23_conservative_mode_,
                "ATLAS23 conservative requires C6 retention");
        require(mode==1 || mode==2,"invalid conservative mode");
        atlas23_conservative_mode_=mode;
    }
    int atlas23_conservative_mode()const{return atlas23_conservative_mode_;}""")
(root/"drnas_native_core_c.hpp").write_text(s)
src=Path("mre_atlas19/native.cpp").read_text()
for original,replacement in (
 ('mode=="C9_SLOW_Q4_GAUSS"','mode=="C9_SLOW_Q4_GAUSS"||mode=="C10_KEEP32_GAUSS"||mode=="C11_KEEP64_GAUSS"'),
 ('mode=="C9_SLOW_Q4"','mode=="C9_SLOW_Q4"||mode=="C10_KEEP32"||mode=="C11_KEEP64"')):
 assert src.count(original)>=2,(original,src.count(original))
 src=src.replace(original,replacement)
expanded='    if(mode=="C9_SLOW_Q4"||mode=="C10_KEEP32"||mode=="C11_KEEP64"||mode=="C9_SLOW_Q4_GAUSS"||mode=="C10_KEEP32_GAUSS"||mode=="C11_KEEP64_GAUSS")'
assert src.count(expanded)==1
src=src.replace(expanded,'if(mode=="C9_SLOW_Q4"||mode=="C9_SLOW_Q4_GAUSS")',1)
# Existing C9 condition may have been expanded by replacements; add independent mode enable before stats output.
anchor='    if(mode=="C9_FIXED_Q4"||mode=="C9_FIXED_Q4_GAUSS")'
assert src.count(anchor)==1
src=src.replace(anchor,
'''    if(mode=="C10_KEEP32"||mode=="C10_KEEP32_GAUSS")
        solver.atlas23_enable_conservative(1);
    if(mode=="C11_KEEP64"||mode=="C11_KEEP64_GAUSS")
        solver.atlas23_enable_conservative(2);
'''+anchor,1)
anchor='           <<" atlas19_fixed_q4_mode="'
assert src.count(anchor)==1
src=src.replace(anchor,'           <<" atlas23_conservative_mode="<<solver.atlas23_conservative_mode()\n'+anchor,1)
(root/"native.cpp").write_text(src)
for mode in ("C10_KEEP32","C11_KEEP64"):
 assert src.count('mode=="'+mode+'"')>=2
print("ATLAS23_BUILD_PATCH_PASS frozen_controls=true keep32=6000 keep64=10000")
