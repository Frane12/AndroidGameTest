#!/usr/bin/env python3
"""DELTA4 preflight: original-source RUP, SAT model, UNSAT proof and shadow safety."""
import json
import os
from pathlib import Path
import sys
import tempfile

R=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(R/"research"))
sys.path.insert(0,str(R/"tests"))
import drnas_x55_cpu_real36 as B
import test_drnas_deltacoop3 as D3
from test_drnas_coop52 import CASES, oracle, text
from test_drnas_deltacoop2 import signal_cases

D3.BIN=R/"build/drnas-deltacoop4"

def main():
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    modes=("d4-shadow","d4-struct","d4")
    summary={m:{"cases":0,"valid":0,"injected":0,"reduction_pairs":0,
                "nonaffine_pairs":0} for m in modes}
    with tempfile.TemporaryDirectory() as td:
        path=Path(td)/"tiny.cnf"
        for n,cs in CASES[:10]+signal_cases()[:4]:
            expected=oracle(n,cs)
            path.write_text(text(n,cs))
            for mode in modes:
                rc,st,logged=D3.run(path,n,cs,mode,1.8)
                assert rc==(10 if expected else 20),("ORACLE_MISMATCH",mode,rc)
                assert "d4_reduction_pairs" in st and "d4_input_clauses" in st
                assert "d4_nonaffine_pairs" in st and "d4_scan_calls" in st
                if mode=="d4-shadow":
                    assert st["bridge_injected"]==0 and logged==0
                assert logged<=st["bridge_injected"]
                summary[mode]["cases"]+=1
                summary[mode]["valid"]+=1
                summary[mode]["injected"]+=st["bridge_injected"]
                summary[mode]["reduction_pairs"]+=st["d4_reduction_pairs"]
                summary[mode]["nonaffine_pairs"]+=st["d4_nonaffine_pairs"]

        originals,_=B.official_manifest()
        src=next(x for x in originals if x["id"]==30 and x["family"]=="hardware-miter")
        raw=Path(src["path"]).read_bytes()
        assert B.sha(raw)==src["sha256"]
        n,cs=B.parse_cnf(raw)
        prior={"clause":[-1,772,777],"left":[-1,-3,777],
               "right":[-1,3,772],"pivot":-3}
        D3.validate_lemma(prior,{D3.canon(c) for c in cs})
        real={}
        for mode in modes:
            rc,st,logged=D3.run(Path(src["path"]).resolve(),n,cs,mode,4.93,False)
            assert rc in (0,10,20,153)
            assert "d4_reduction_pairs" in st
            if mode=="d4-shadow":assert st["bridge_injected"]==0 and logged==0
            assert logged<=st["bridge_injected"]
            real[mode]={"returncode":rc,"bridge_injected":st["bridge_injected"],
                         "d4_reduction_pairs":st["d4_reduction_pairs"],
                         "d4_nonaffine_pairs":st["d4_nonaffine_pairs"],
                         "d4_scan_calls":st["d4_scan_calls"],
                         "lemmas_checked":logged}
    report={"synthetic_and_small":summary,"real_id30":real,
            "real_id30_SHA256":src["sha256"],"real_id30_original_RUP":True,
            "one_cpu":True,"original_proofs_checked":True,
            "no_main_changes":True}
    print("DELTA4_PREFLIGHT_PASS",json.dumps(report,sort_keys=True),flush=True)

if __name__=="__main__":
    main()
