#!/usr/bin/env python3
"""DRNAS T5 deterministic native/benchmark source generation.

Patches target immutable T2 reference files, fail closed on textual drift,
and create T5-only copies. No changes to frozen R1/R2/T2 sources.
"""
from pathlib import Path
R=Path("research")

def change(s,old,new,label):
    n=s.count(old)
    if n!=1:
        raise RuntimeError(f"T5_SOURCE_DRIFT {label}: {n} occurrences")
    return s.replace(old,new)

def build_native():
    s=(R/"ultimate_t2_native.cpp").read_text()
    s=change(s,
      '    const bool t2_units=(mode=="t2_derived_units");',
      '    const bool t2_units=(mode=="t2_derived_units");\n'
      '    const bool t5=(mode=="t5_novel_active"||mode=="t5_novel_shadow");',
      "detect")
    s=change(s,
      '''         mode=="td_lazy_source");
    const bool extend=''',
      '''         mode=="td_lazy_source"||t5);
    const bool extend=''',
      "t5-source")
    s=change(s,
      '(mode=="shadow_boundary"||mode=="t_shadow"||mode=="t2_derived_shadow")?',
      '(mode=="shadow_boundary"||mode=="t_shadow"||mode=="t2_derived_shadow"||\n'
      '           mode=="t5_novel_shadow")?',
      "shadow")
    s=change(s,
      '    bridge.incremental_enabled=(mode=="direct_incremental"||(t_source&&mode!="td_lazy_source"));',
      '    bridge.incremental_enabled=(mode=="direct_incremental"||\n'
      '                              (t_source&&mode!="td_lazy_source"&&!t5));',
      "incremental")
    s=change(s,
      '''                              mode=="td_lazy_source");''',
      '''                              mode=="td_lazy_source"||t5);''',
      "lazy-two-watch")
    s=change(s,
      '''mode!="td_lazy_source")
            throw runtime_error("R166X_BAD_MODE");''',
      '''mode!="td_lazy_source"&&
            mode!="t5_novel_active"&&mode!="t5_novel_shadow")
            throw runtime_error("R166X_BAD_MODE");''',
      "allowed")
    s=change(s,
      '''        cout<<"R166X_COMPONENT_GATE_SELFTEST_PASS"<<endl;
    }''',
      '''        cout<<"R166X_COMPONENT_GATE_SELFTEST_PASS"<<endl;
        // Independently source-replayed XOR(1,2,3)=0 and
        // XOR(1,2,4)=1 derive a NEW XOR(3,4)=1.
        // For current trail 3=true, 4=false must follow without ever
        // needing to assign eliminated variables 1 and 2.
        R162Bridge novel({{{3,4},1}},4,DIRECT);
        novel.watchlazy_enabled=true;
        novel.notify_new_decision_level();
        novel.notify_assignment({3});
        if(novel.cb_propagate()!=-4||novel.direct_proposals!=1)
            throw runtime_error("T5_DERIVED_NEW_TRAIL_REASON_NOT_DELIVERED");
        vector<int> t5_reason;
        while(true){
            int lit=novel.cb_add_reason_clause_lit(-4);
            if(!lit)break;
            t5_reason.push_back(lit);
        }
        if(t5_reason!=vector<int>({-4,-3})||
           novel.reason_clauses_completed!=1)
            throw runtime_error("T5_NEW_GF2_REASON_INVALID");
        novel.notify_assignment({-4});
        novel.notify_backtrack(0);
        if(novel.disabled||!novel.reasons.empty())
            throw runtime_error("T5_DERIVED_REASON_BACKTRACK_FAIL");
        R162Bridge shadow({{{3,4},1}},4,SHADOW);
        shadow.watchlazy_enabled=true;
        shadow.notify_new_decision_level();
        shadow.notify_assignment({3});
        if(shadow.cb_propagate()!=0||shadow.shadow_candidates!=1||
           shadow.direct_proposals!=0||!shadow.reasons.empty())
            throw runtime_error("T5_TRUE_DERIVED_SHADOW_FAIL");
        cout<<"T5_NOVEL_DERIVED_TRAIL_SELFTEST_PASS"<<endl;
    }''',
      "new-trail-selftest")
    (R/"ultimate_t5_native.cpp").write_text(s)

def build_bench():
    s=(R/"ultimate_t2_benchmark.py").read_text()
    s=change(s, 'ROOT = pathlib.Path("ultimate_t2")',
             'ROOT = pathlib.Path("ultimate_t5")',"root")
    s=change(s,
      '''MODES = ("r153","t_clean","t_shadow","t_source","t_adaptive","t_derived",
         "t2_derived_rows","t2_derived_units","t2_derived_incremental","t2_derived_shadow",
         "td_lazy_source")''',
      '''MODES = ("r153","t_clean","t_shadow","td_lazy_source",
         "t2_derived_shadow","t2_derived_rows",
         "t5_novel_shadow","t5_novel_active")''',
      "modes")
    s=change(s,
      'PROTO = "DRNAS-TD-20261107-LAZY-WATCH-11-ARM-SOURCE-ABLATION"',
      'PROTO = "DRNAS-T5-20261108-CERTIFIED-NOVEL-GF2-8ARM-PAIRED-v1"',
      "proto")
    s=change(s,
      'FALLBACK = pathlib.Path("research/ultimate_t2_fallback.py")',
      'FALLBACK = pathlib.Path("research/ultimate_t5_fallback.py")',
      "fallback")
    s=change(s,
      'need(len(MODES)==11 and len(cases())==20,"eleven-arm TD protocol")',
      'need(len(MODES)==8 and len(cases())==20,"eight-arm T5 original protocol")',
      "selftest")
    s=change(s,
      'need(len(rows)==len(cs)*REPS*len(MODES)==440,"trial count incorrect")',
      'need(len(rows)==len(cs)*REPS*len(MODES)==320,"trial count incorrect")',
      "count")
    s=change(s,
      '''"t2_derived_incremental","t2_derived_shadow","td_lazy_source")''',
      '''"t2_derived_incremental","t2_derived_shadow","td_lazy_source",
                                         "t5_novel_shadow","t5_novel_active")''',
      "started counter")
    # Purely descriptive; NEVER claim new blind cohort or native LRAT.
    s=change(s,
      'status="ULTIMATE_TD_LAZY_SOURCE_AUDIT_PASS_NONBLIND"',
      'status="ULTIMATE_T5_DERIVED_NOVEL_AUDIT_PASS_NONBLIND"',
      "status")
    s=change(s,
      'original_r2_run=42346485260,',
      'original_r2_run=42346485260,original_t4_run=42477975655,\n'
      '        t5_derived_only=True,t5_source_certificate_replay=True,',
      "source pin")
    s=change(s,
      '''20 previously used original CNFs; eleven arms, two reps = 440 attempts. Not blind. Native UNSAT lacks LRAT. Causal factorial isolation.''',
      '''20 previously used original CNFs; eight arms, two reps = 320 attempts. Not blind. Novel derived GF2 short rows independently replayed; native UNSAT lacks LRAT. Exact SHA frozen Clean/Shadow/derived causal ablation.''',
      "limitations")
    s=change(s,
      '''# Ultimate TD — lazy exact two-watch vs eager source XOR incremental frontier''',
      '''# DRNAS T5 — independently certified new GF2 cancellation on CDCL trail''',
      "report title")
    begin=s.index('    for ref,cand in ((')
    end=s.index(':\n        deltas=',begin)
    s=s[:begin]+'''    for ref,cand in (("t_clean","t_shadow"),
                     ("t_clean","td_lazy_source"),
                     ("t_clean","t2_derived_shadow"),
                     ("t_clean","t2_derived_rows"),
                     ("t_clean","t5_novel_shadow"),
                     ("t_clean","t5_novel_active"),
                     ("t_shadow","t5_novel_shadow"),
                     ("t5_novel_shadow","t5_novel_active"),
                     ("t2_derived_rows","t5_novel_active"),
                     ("r153","t5_novel_active"))'''+s[end:]
    (R/"ultimate_t5_benchmark.py").write_text(s)

def main():
    build_native()
    build_bench()
    print("T5_DETERMINISTIC_GENERATED_SOURCES_PASS",flush=True)

if __name__=="__main__":
    main()
