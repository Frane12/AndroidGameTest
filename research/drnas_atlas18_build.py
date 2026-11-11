#!/usr/bin/env python3
"""ATLAS18: pre-registered learned-clause deletion cadence x quota factorial.

Generated strictly from frozen ATLAS17, with C6/C7 behavior untouched.
Mode 0 = unchanged C5/C6/C7; C8 modes:
  1: every 1500 conflicts, delete 1/8 of eligible clauses
  2: every 1500 conflicts, delete 1/16
  3: pressure-gated (1500 high/3000 low), delete 1/8
  4: pressure-gated (1500 high/3000 low), delete 1/16
Each run records BCP watch/propagation deltas; no change to SAT/UNSAT rules.
"""
from pathlib import Path

root=Path("mre_atlas18")
root.mkdir(exist_ok=True)
s=Path("mre_atlas17/drnas_native_core_c.hpp").read_text()

def one(old,new):
    global s
    assert s.count(old)==1,("ATLAS18 patch anchor",old,s.count(old))
    s=s.replace(old,new,1)

one("    bool atlas17_adaptive_=false, atlas17_high_pressure_=false;",
"""    bool atlas17_adaptive_=false, atlas17_high_pressure_=false;
    int atlas18_mode_=0;""")
one("""                   ((atlas17_adaptive_ && stats_.conflicts%1500==0) ||
                    (!atlas17_adaptive_ && stats_.conflicts%10000==0)))""",
"""                   (((atlas17_adaptive_ || atlas18_mode_>0) && stats_.conflicts%1500==0) ||
                    ((!atlas17_adaptive_ && atlas18_mode_==0) && stats_.conflicts%10000==0)))""")
one("""        if(atlas17_adaptive_){
            const uint64_t dw=stats_.watch_visits-atlas17_last_watch_;""",
"""        if(atlas17_adaptive_ || atlas18_mode_>0){
            const uint64_t dw=stats_.watch_visits-atlas17_last_watch_;""")
one("""            if(!atlas17_high_pressure_ && stats_.conflicts%3000!=0)return;""",
"""            if((atlas17_adaptive_ || atlas18_mode_>=3) &&
               !atlas17_high_pressure_ && stats_.conflicts%3000!=0)return;""")
one("""        const size_t divisor=atlas17_adaptive_?(atlas17_high_pressure_?4:16):8;""",
"""        // Factorial controls: keep cadence and quota independent.
        // mode 1/3 => 1/8; mode 2/4 => 1/16; legacy mode 0 unchanged.
        const size_t divisor=atlas18_mode_>0
            ? ((atlas18_mode_==1 || atlas18_mode_==3)?8:16)
            : (atlas17_adaptive_?(atlas17_high_pressure_?4:16):8);""")
one("""    uint64_t atlas17_low_cycles()const{return atlas17_low_cycles_;}""",
"""    uint64_t atlas17_low_cycles()const{return atlas17_low_cycles_;}
    void atlas18_enable_fixed(int mode){
        require(atlas16_keep_ && !atlas17_adaptive_ && atlas18_mode_==0,
                "factorial mode requires unchanged C6 retention");
        require(mode>=1 && mode<=4,"ATLAS18 invalid factorial mode");
        atlas18_mode_=mode;
    }
    int atlas18_mode()const{return atlas18_mode_;}""")
(root/"drnas_native_core_c.hpp").write_text(s)

src=Path("mre_atlas17/native.cpp").read_text()
enable='if(mode=="C7_ADAPT"||mode=="C7_ADAPT_GAUSS")solver.atlas17_enable_adaptive();'
assert src.count(enable)==1
src=src.replace(enable,"/*ATLAS18_C7_ENABLE_ANCHOR*/",1)
arms=("C8_FAST_Q8","C8_FAST_Q16","C8_GATE_Q8","C8_GATE_Q16")
assert src.count('mode=="C7_ADAPT"')>=2
src=src.replace('mode=="C7_ADAPT"',
    'mode=="C7_ADAPT"'+''.join('||mode=="'+a+'"' for a in arms))
insert=enable+"\n"+'\n'.join(
    '    if(mode=="'+arm+'")solver.atlas18_enable_fixed('+str(i)+');'
    for i,arm in enumerate(arms,1))
assert src.count("/*ATLAS18_C7_ENABLE_ANCHOR*/")==1
src=src.replace("/*ATLAS18_C7_ENABLE_ANCHOR*/",insert,1)
anchor='           <<" SAT_original_verified="<<int(status==10)'
assert src.count(anchor)==1
src=src.replace(anchor,
'''           <<" atlas18_mode="<<solver.atlas18_mode()
'''+anchor,1)
(root/"native.cpp").write_text(src)
for mode in arms:
    assert 'mode=="'+mode+'"' in src
assert 'atlas18_mode_' in s and "atlas18_enable_fixed" in src
print("ATLAS18_BUILD_PASS controls_c6_c7_unchanged=true factorial_modes=4")
