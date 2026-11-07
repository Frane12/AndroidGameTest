#!/usr/bin/env python3
"""TA7 frozen source-only R28 host-lock after TA6 failed transfer.

The certified R28 preparation may be enabled on a Kissat host only if
frozen TA3 already chose Kissat; never change CMS to Kissat from XOR alone.
No formula ID, family label, historical speed or expected outcome is used.
"""
import json
import drnas_ta3_adaptive_selector as ta3
EXECUTORS = ("cms_plain","cms_r28","kissat_plain","kissat_r28")
def route(f,mode):
    if mode not in ("ta7_host_locked","ta7_shadow"): raise ValueError(mode)
    legacy,reason = ta3.decision(f,"ta2_portfolio")
    if legacy not in EXECUTORS: raise AssertionError("Invalid TA3 host")
    if mode=="ta7_shadow": return legacy,"TA7_shadow_same_TA3:"+reason
    size=int(f["declared_clauses"])
    cov=float(f["sample_fraction_clauses"])
    x=int(f["complete_xor3_templates_sample"])
    bi=float(f["binary_fraction"]); lg=float(f["long_clause_fraction"])
    ho=float(f["horn_clause_fraction"])
    sk=float(f["variable_occurrence_p90_over_median"])
    pure=size<=2500 and cov>=.95 and x>=6 and bi<.12 and lg<.16
    sparse=size>=2500 and x>=16 and cov<=.10 and bi<.40 and lg<.40 and ho<.95 and sk<12
    if legacy=="kissat_plain" and (pure or sparse):
        return "kissat_r28","TA7_source_only_R28_same_Kissat_host"
    return legacy,"TA7_no_cross_backend_TA3:"+reason
def selftest():
    b=dict(declared_clauses=150000,sample_fraction_clauses=512/150000,
        complete_xor3_templates_sample=0,binary_fraction=.01,
        horn_clause_fraction=.45,long_clause_fraction=.02,
        variable_occurrence_p90_over_median=2)
    fs=[b,dict(b,declared_clauses=1000,sample_fraction_clauses=1,
         complete_xor3_templates_sample=10),
        dict(b,complete_xor3_templates_sample=28,sample_fraction_clauses=.02),
        dict(b,binary_fraction=.8),dict(b,horn_clause_fraction=.99),
        dict(b,long_clause_fraction=.5),dict(b,variable_occurrence_p90_over_median=15)]
    for f in fs:
        old,_=ta3.decision(f,"ta2_portfolio")
        new,_=route(f,"ta7_host_locked")
        sh,_=route(f,"ta7_shadow")
        assert new in EXECUTORS and sh==old
        assert new.split("_")[0]==old.split("_")[0]
        if old.startswith("cms_"): assert new==old
    print("TA7_HOSTLOCK_SELFTEST_PASS",json.dumps({"profiles":len(fs),
        "cms_preserved":True,"source_only":True}),flush=True)
if __name__=="__main__": selftest()
