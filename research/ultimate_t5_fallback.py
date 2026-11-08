#!/usr/bin/env python3
"""T5 source-proof-gated novel GF2 rows on original mixed CNF.

The R153 exact router runs first; this script runs only on genuine fallback.
All arms share the original immutable CNF and a single wall-clock cap.
T5 Active and T5 Shadow receive *identical* independently certified,
new 2..6-variable consequences, NO globally injected Gaussian units.
"""
import json
import os
import pathlib
import sys
import tempfile
import time

sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import ultimate_t2_fallback as t2
import ultimate_r2_fallback as r2
import ultimate_t2_probe as detector
import r157_source_certified_xor as cert
import r166x_certified_gauss as gf
import ultimate_t5_novel as novel

ROOT=pathlib.Path("ultimate_t5")
t2.ROOT=ROOT
t2.NATIVE=ROOT/"t-native"
t2.EMPTY=ROOT/"empty.tsv"
t2.NATIVE_MODES["t5_novel_shadow"]="t5_novel_shadow"
t2.NATIVE_MODES["t5_novel_active"]="t5_novel_active"

def main():
    mode=os.environ.get("ULTIMATE_T_MODE","clean")
    if mode not in ("t5_novel_shadow","t5_novel_active"):
        # Reuses *unchanged* reference fallback for Clean, Source Shadow and
        # all-source+derived controls, changing only the pinned native path.
        return t2.main()
    t2.need(len(sys.argv)==2,"T5 requires one original CNF")
    src=pathlib.Path(sys.argv[1]).resolve()
    t2.need(src.is_file() and t2.NATIVE.is_file() and t2.EMPTY.is_file(),
            "source/native/empty control missing")
    deadline=int(os.environ["ULTIMATE_R2_DEADLINE_NS"])
    source_sha=t2.sha256(src)
    begin=time.monotonic()
    selected=derived=0
    rows=t2.EMPTY
    reason="no_certified_derived_rows"
    eligible=False
    budget=min(1.2,(deadline-time.monotonic_ns())/1e9-1.5)
    if budget<=0:
        return t2.run_native(src,source_sha,mode,"insufficient_time",0,0,0,
                             False,time.monotonic()-begin,t2.EMPTY,None,deadline)
    with tempfile.TemporaryDirectory(prefix="t5-novel-proof-") as temp:
        d=pathlib.Path(temp)
        probe={}
        try:
            with r2.preparation_budget(budget):
                hinted,reason,probe=detector.cheap_probe(src)
                if hinted:
                    ev=cert.extract(src,d/"source.tsv",d/"source-proof.json",
                                    max_rows=64)
                    t2.need(ev["source_sha256"]==source_sha,
                            "T5 source SHA changed")
                    selected=ev["selected_rows"]
                    if selected and ev["usable_residual_linked_equations"]:
                        t2.need(t2.source_replay(src,ev,d/"source.tsv")==selected,
                                "T5 original XOR proof replay failed")
                        report,novel_tsv=novel.derive(src,ev,d/"novel",
                                                       max_rows=24)
                        derived=report["novel_rows"]
                        t2.need(report["source_sha256"]==source_sha,
                                "T5 derived provenance changed")
                        if derived:
                            rows=novel_tsv
                            reason="novel_derived_GF2_rows_source_replayed"
                        else:
                            reason="no_residual_linked_novel_short_rows"
                    else:
                        reason="insufficient_source_parity_overlap"
                if derived and (deadline-time.monotonic_ns())>1_500_000_000:
                    eligible=True
                elif derived:
                    reason="remaining_time_veto"
        except r2.PreparationBudgetExceeded:
            reason="certification_budget_preempted"
            eligible=False
            rows=t2.EMPTY
            derived=0
        elapsed=time.monotonic()-begin
        # No injected Gauss unit; ALL propagated units must be generated
        # by CURRENT CDCL trail from proof-replayed novel short rows.
        return t2.run_native(src,source_sha,mode,reason,selected,derived,0,
                             eligible,elapsed,rows,None,deadline,probe)

if __name__=="__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print("ULTIMATE_T_FATAL "+str(exc),file=sys.stderr,flush=True)
        sys.exit(78)
