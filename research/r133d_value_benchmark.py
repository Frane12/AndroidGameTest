#!/usr/bin/env python3
"""R133d paired CaDiCaL CDCL+GF2 value experiment on reused SATLIB PARITY.
Ablation: clean vs R133c live XOR, R133c full pairwise GF2, R133d short rows.
Same CaDiCaL 2.1.0 source/runner; 10s cap and PAR2, prep charged to GF2 modes.
Development only, NOT blinded, no independent UNSAT proof and not Kissat.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import random
import subprocess
import sys
import time
import r133c_native_gf2_benchmark as base

MODES=("clean","active","gf2","short")
REPS=2
CAP=base.CAP

def select_rows(cnf, rows, proof, out, stem):
    filtered=out/(stem+"-short.tsv")
    audit=out/(stem+"-selector.json")
    start=time.perf_counter()
    subprocess.run([sys.executable,"research/r133d_short_signal_selector.py",
                    "export","--cnf",str(cnf),"--rows",str(rows),
                    "--proof",str(proof),"--out",str(filtered),
                    "--audit",str(audit)],check=True,timeout=30,capture_output=True,text=True)
    elapsed=time.perf_counter()-start
    return filtered,json.loads(audit.read_text()),elapsed

def measure(binary,source,out,stem):
    original,proof,source_info,prep=base.verified_rows(source,out,stem)
    selected,selection,selection_s=select_rows(source,original,proof,out,stem)
    return dict(original=original,proof=proof,source_info=source_info,
                short=selected,selection=selection,prep=prep,
                selection_s=selection_s)

def run_mode(binary,mode,source,inventory):
    native_mode="active" if mode=="short" else mode
    row_file=inventory["short"] if mode=="short" else inventory["original"]
    prep=0 if mode=="clean" else inventory["prep"] + (
        inventory["selection_s"] if mode=="short" else 0)
    record=base.native_run(binary,native_mode,source,row_file,prep)
    record["selected_source_rows"]=inventory["selection"]["source_kept"] if mode=="short" else inventory["source_info"]["exported"]
    record["selected_derived_rows"]=inventory["selection"]["derived_kept"] if mode=="short" else record["derived_rows"]
    record["selector_s"]=round(inventory["selection_s"] if mode=="short" else 0,6)
    record["source_export_s"]=round(inventory["prep"] if mode!="clean" else 0,6)
    record["messages_per_1000_scans"]=round(1000*record["emitted"]/record["rows_scanned"],5) if record["rows_scanned"] else 0
    return record

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--binary",type=Path,required=True)
    ap.add_argument("--satlib",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    a=ap.parse_args()
    a.out.mkdir(parents=True,exist_ok=True)
    fixture=base.fixture(a.out)
    inv=measure(a.binary,fixture,a.out,"fixture")
    assert inv["selection"]["derived_kept"]>=1,inv["selection"]
    fresults={mode:run_mode(a.binary,mode,fixture,inv) for mode in MODES}
    if any(row["status"]!="SAT" for row in fresults.values()):
        raise RuntimeError("R133D_FIXTURE_MISMATCH "+str(fresults))
    if fresults["short"]["selected_derived_rows"]<1:
        raise RuntimeError("R133D_FIXTURE_SHORT_BRIDGE_UNUSED")
    (a.out/"fixture-results.json").write_text(json.dumps(fresults,indent=2,sort_keys=True)+"\n")
    print("R133D_FIXTURE_PASS",json.dumps(fresults,sort_keys=True),flush=True)

    controls=base.select_controls(a.satlib)
    manifest=[dict(file=p.name,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in controls]
    (a.out/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
    records=[]
    for source in controls:
        digest=hashlib.sha256(source.read_bytes()).hexdigest()
        inv=measure(a.binary,source,a.out,digest[:12])
        for rep in range(REPS):
            order=list(MODES)
            random.Random(digest+str(rep)).shuffle(order)
            for mode in order:
                data=run_mode(a.binary,mode,source,inv)
                data.update(formula=source.name,sha256=digest,rep=rep,mode=mode,
                            certified_source_rows=inv["source_info"]["exported"])
                records.append(data)
        print("R133D_CASE",source.name,
              "source_xor",inv["source_info"]["exported"],
              "short_source",inv["selection"]["source_kept"],
              "short_derived",inv["selection"]["derived_kept"],
              "prep_s",round(inv["prep"]+inv["selection_s"],6),flush=True)
    assert len(records)==len(controls)*REPS*len(MODES)==48
    for source in controls:
        for rep in range(REPS):
            distinct={r["status"] for r in records
                if r["formula"]==source.name and r["rep"]==rep and r["status"]!="TIMEOUT"}
            if len(distinct)>1:
                raise RuntimeError("R133D_SOLVER_DISAGREEMENT "+repr((source.name,rep,distinct)))
    with (a.out/"paired.csv").open("w",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=list(records[0]))
        writer.writeheader();writer.writerows(records)
    totals={}
    for mode in MODES:
        rows=[r for r in records if r["mode"]==mode]
        totals[mode]=dict(
            trials=len(rows),solved=sum(x["status"]!="TIMEOUT" for x in rows),
            par2_s=round(sum(x["par2_s"] for x in rows),6),
            emitted=sum(x["emitted"] for x in rows),
            scans=sum(x["rows_scanned"] for x in rows),
            assignments=sum(x["assignments"] for x in rows),
            backtracks=sum(x["backtracks"] for x in rows),
            short_derived_rows=sum(x["selected_derived_rows"] for x in rows),
            mean_messages_per_1000_scans=round(
              1000*sum(x["emitted"] for x in rows)/max(1,sum(x["rows_scanned"] for x in rows)),5))
    clean=totals["clean"]["par2_s"]
    baseline=totals["gf2"]["par2_s"]
    short=totals["short"]["par2_s"]
    audit=dict(
        protocol="DRNAS-R133D-NATIVE-CDCL-SHORT-GF2-SIGNAL-CONTROL-20261105-v1",
        scope="6 previously used SATLIB PARITY formulas x2, 4 modes; development, NOT blind",
        trials=len(records),formulas=len(controls),cap_s=CAP,
        solver="CaDiCaL rel-2.1.0 with unchanged R133c native IPASIR-UP",
        certified_source_rows=True,derived_ancestry_replayed=True,
        sat_witnesses_checked=True,independent_unsat_proofs=False,
        preprocessing_cost_charged=True,modes=totals,
        r133d_vs_clean_pct=round(100*(clean-short)/clean,5),
        r133d_vs_r133c_gf2_pct=round(100*(baseline-short)/baseline,5))
    (a.out/"audit.json").write_text(json.dumps(audit,indent=2,sort_keys=True)+"\n")
    print("R133D_FINAL_AUDIT",json.dumps(audit,sort_keys=True),flush=True)

if __name__=="__main__":
    main()
