#!/usr/bin/env python3
"""X7 semantic event audit: ignore order-dependent internal watch IDs.

Read frozen native event logs emitted by the successful X7 benchmark.
No rerun, no solver state change, no new claims of correctness or blind results.
WATCH_BIN.b is allocated clause ID; WATCH_LONG.b is allocator offset. Those
cannot be used as identity anchors when source clauses are permuted.
"""
import json
from pathlib import Path
from collections import Counter

ROOT=Path("mre_x7")
MODES=("front100","shift1","spread100","spread_reverse_copies","spread_shifted")
GROUPS={
 "watch_binary":("WATCH_BIN",),
 "watch_long":("WATCH_LONG",),
 "decisions":("DECIDE",),
 "implications":("IMPLY",),
 "learnt_lbd":("LEARN_LBD",),
 "trail_all":("ROOT","DECIDE","IMPLY"),
 "all_semantic":("ROOT","DECIDE","IMPLY","LEARN_LBD","WATCH_BIN","WATCH_LONG"),
}
def norm(e):
    kind=e["kind"]
    keys=("kind","conf","lev","lit","a") if kind in ("WATCH_BIN","WATCH_LONG") else ("kind","conf","lev","lit","a","b")
    return tuple(e[k] for k in keys)

def first_difference(a,b):
    n=min(len(a),len(b))
    index=next((i for i in range(n) if norm(a[i])!=norm(b[i])),None)
    if index is None and len(a)!=len(b): index=n
    return {
        "first_filtered_index":index,
        "reference":a[index] if index is not None and index<len(a) else None,
        "candidate":b[index] if index is not None and index<len(b) else None,
        "ref_events":len(a),"candidate_events":len(b),
        "identical_in_captured_window":index is None,
        "truncated_to_first_4000_raw_events":True
    }

def main():
    original=json.loads((ROOT/"x7-final.json").read_text())
    assert original["protocol"]=="DRNAS-MRE-X7-CMS51115-NATIVE-TRACE-6ARM-4SHA-4SEED-v1"
    assert original["real_E2E_trials"]==96 and original["bounded_not_PAR2"]==576
    rows=[]
    for i in range(4):
        data=json.loads((ROOT/f"trace-{i}.json").read_text())
        assert data["protocol"]==original["protocol"] and data["same_native_binary_on_off"] is True
        for mode in ("original",)+MODES:
            assert mode in data["modes"]
            assert data["modes"][mode]["plain_stats"] == data["modes"][mode]["traced_stats"]
            assert data["modes"][mode]["plain_status"] == data["modes"][mode]["traced_status"]
        a=data["modes"]["original"]["trace_events"]
        assert len(a)<=4000
        mode_results={}
        for mode in MODES:
            b=data["modes"][mode]["trace_events"]
            mode_results[mode]={}
            for group,types in GROUPS.items():
                aa=[e for e in a if e["kind"] in types]
                bb=[e for e in b if e["kind"] in types]
                mode_results[mode][group]=first_difference(aa,bb)
            old_raw=data["first_event_differences"][mode]["first_different_seq"]
            mode_results[mode]["raw_first_difference_including_internal_ids"]=old_raw
        row={"gbd":data["gbd"],"sha256":data["source_sha256"],
             "ref_event_counts":dict(Counter(e["kind"] for e in a)),
             "modes":mode_results}
        rows.append(row)
        print("MRE_X7B_SOURCE",json.dumps({"gbd":row["gbd"],"first":{
          mode:{g:r["first_filtered_index"] for g,r in d.items() if isinstance(r,dict)}
          for mode,d in mode_results.items()}},sort_keys=True),flush=True)
    output={"protocol":"DRNAS-MRE-X7B-INTERNAL-ID-NORMALIZED-TRACE-AUDIT-v1",
            "source_protocol":original["protocol"],"source_sha_run_id":42556906957,
            "source_count":4,"same_frozen_trace_no_rerun":True,
            "trace_limit_events":4000,
            "all_X7_on_off_parity_passed":True,
            "WATCH_BIN_ignore_order_dependent_clause_ID":True,
            "WATCH_LONG_ignore_order_dependent_allocator_offset":True,
            "first_difference_does_not_establish_causality":True,
            "no_independent_UNSAT_LRAT":True,
            "original_X7_PAR2_s":original["scores"]["original"]["PAR2_s"],
            "shifted_X7_PAR2_s":original["scores"]["spread_shifted"]["PAR2_s"],
            "shifted_X7_speedup":original["scores"]["spread_shifted"]["speedup_vs_original"],
            "per_source":rows}
    (ROOT/"semantic-causal-audit.json").write_text(json.dumps(output,indent=2,sort_keys=True)+"\n")
    print("MRE_X7B_FINAL",json.dumps({"protocol":output["protocol"],
          "source_count":4,"X7_original_PAR2":output["original_X7_PAR2_s"],
          "X7_shifted_PAR2":output["shifted_X7_PAR2_s"],
          "X7_shifted_speedup":output["shifted_X7_speedup"],
          "summary":[{"gbd":z["gbd"],"first":{
             m:{g:v["first_filtered_index"] for g,v in d.items() if isinstance(v,dict)}
             for m,d in z["modes"].items()}} for z in rows]},sort_keys=True),flush=True)

if __name__=="__main__":
    main()
