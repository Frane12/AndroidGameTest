#!/usr/bin/env python3
"""ATLAS19 isolated C9 fixed 1/4 deletion, at 1500 or 3000 conflicts.

C6 and C7 controls are generated unmodified from the frozen ATLAS17 source.
Only delete scheduling/quota are changed in the new C9 modes, never SAT/UNSAT
inference or source CNF. Both use C6's watched-list compaction safeguards.
"""
from pathlib import Path
root=Path("mre_atlas19")
root.mkdir(exist_ok=True)
s=Path("mre_atlas17/drnas_native_core_c.hpp").read_text()

def one(a,b):
    global s
    n=s.count(a)
    assert n==1,("ATLAS19 patch source drift",a,n)
    s=s.replace(a,b,1)

one("    bool atlas17_adaptive_=false, atlas17_high_pressure_=false;",
"""    bool atlas17_adaptive_=false, atlas17_high_pressure_=false;
    int atlas19_fixed_q4_mode_=0;  // 0 frozen control, 1 every 1500, 2 every 3000""")
one("""                   ((atlas17_adaptive_ && stats_.conflicts%1500==0) ||
                    (!atlas17_adaptive_ && stats_.conflicts%10000==0)))""",
"""                   ((atlas17_adaptive_ && stats_.conflicts%1500==0) ||
                    (atlas19_fixed_q4_mode_==1 && stats_.conflicts%1500==0) ||
                    (atlas19_fixed_q4_mode_==2 && stats_.conflicts%3000==0) ||
                    (!atlas17_adaptive_ && !atlas19_fixed_q4_mode_
                     && stats_.conflicts%10000==0)))""")
one("""        const size_t divisor=atlas17_adaptive_?(atlas17_high_pressure_?4:16):8;""",
"""        const size_t divisor=atlas19_fixed_q4_mode_?4:
            (atlas17_adaptive_?(atlas17_high_pressure_?4:16):8);""")
one("""    uint64_t atlas17_low_cycles()const{return atlas17_low_cycles_;}""",
"""    uint64_t atlas17_low_cycles()const{return atlas17_low_cycles_;}
    void atlas19_enable_fixed_q4(int cadence_mode){
        require(atlas16_keep_ && !atlas17_adaptive_ &&
                !atlas19_fixed_q4_mode_,"C9 requires original C6 retention");
        require(cadence_mode==1 || cadence_mode==2,"invalid C9 cadence mode");
        atlas19_fixed_q4_mode_=cadence_mode;
    }
    int atlas19_fixed_q4_mode()const{return atlas19_fixed_q4_mode_;}""")
(root/"drnas_native_core_c.hpp").write_text(s)

src=Path("mre_atlas17/native.cpp").read_text()
enable='if(mode=="C7_ADAPT"||mode=="C7_ADAPT_GAUSS")solver.atlas17_enable_adaptive();'
assert src.count(enable)==1
src=src.replace(enable,"/*ATLAS19_ENABLE_ANCHOR*/",1)
assert src.count('mode=="C7_ADAPT"')>=2
assert src.count('mode=="C7_ADAPT_GAUSS"')>=2
src=src.replace('mode=="C7_ADAPT_GAUSS"',
    'mode=="C7_ADAPT_GAUSS"||mode=="C9_FIXED_Q4_GAUSS"||mode=="C9_SLOW_Q4_GAUSS"')
src=src.replace('mode=="C7_ADAPT"',
    'mode=="C7_ADAPT"||mode=="C9_FIXED_Q4"||mode=="C9_SLOW_Q4"')
src=src.replace("/*ATLAS19_ENABLE_ANCHOR*/",
"""if(mode=="C7_ADAPT"||mode=="C7_ADAPT_GAUSS")solver.atlas17_enable_adaptive();
    if(mode=="C9_FIXED_Q4"||mode=="C9_FIXED_Q4_GAUSS")
        solver.atlas19_enable_fixed_q4(1);
    if(mode=="C9_SLOW_Q4"||mode=="C9_SLOW_Q4_GAUSS")
        solver.atlas19_enable_fixed_q4(2);""",1)
anchor='           <<" SAT_original_verified="<<int(status==10)'
assert src.count(anchor)==1
src=src.replace(anchor,
'''           <<" atlas19_fixed_q4_mode="<<solver.atlas19_fixed_q4_mode()
''' +anchor,1)
(root/"native.cpp").write_text(src)
for mode in ["C9_FIXED_Q4","C9_FIXED_Q4_GAUSS","C9_SLOW_Q4","C9_SLOW_Q4_GAUSS"]:
    assert src.count('mode=="'+mode+'"')>=2
assert 'atlas19_fixed_q4_mode_' in s
print("ATLAS19_BUILD_PATCH_PASS c6_c7_frozen=true fixedQ4_1500=1 fixedQ4_3000=2")
