#!/usr/bin/env python3
"""Cross-shard R149 strict source-identity/paired PAR2 audit. Not a blind holdout."""
import argparse,csv,hashlib,json,math
from pathlib import Path
from collections import Counter,defaultdict

MODES=("clean","cryptominisat","clause","direct","lazy","screen")
COHORTS=("official","external_application","external_xor","external_nonxor")

def fail(message):raise RuntimeError("R149_CROSS_SHARD_AUDIT_FAIL "+message)

def source_sha(path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda:f.read(1<<20),b""):h.update(b)
    return h.hexdigest()

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    a.out.mkdir(parents=True,exist_ok=True)
    folders=sorted(x for x in a.root.glob("r149-real-shard-*") if x.is_dir())
    if len(folders)!=4:fail("required exactly four shard artifacts")
    sources={};records=[];seen=set();manifests=set()
    for folder in folders:
        ledger_path=folder/"sources.json"
        csv_path=folder/"paired.csv"
        report_path=folder/"report.json"
        if not ledger_path.is_file() or not csv_path.is_file() or not report_path.is_file():
            fail("missing artifact data "+str(folder))
        ledger=json.loads(ledger_path.read_text())
        report=json.loads(report_path.read_text())
        if report["dataset"]!="real" or report["formulas"]!=len(ledger) or report["cap_s"]!=10:
            fail("shard report mismatch")
        if len(ledger)!=6:fail("expected six formulas per shard")
        for item in ledger:
            sha=item["sha256"]
            if sha in sources:fail("duplicated source SHA "+sha)
            sources[sha]=item
            manifests.add(item["source_manifest_sha256"])
        with csv_path.open(newline="") as f:
            for row in csv.DictReader(f):
                key=(row["source"],int(row["rep"]),row["mode"])
                if key in seen:fail("duplicate paired key "+repr(key))
                seen.add(key)
                if row["source"] not in sources and not any(row["source"]==x["sha256"] for x in ledger):
                    fail("row source not in local shard ledger")
                if row["mode"] not in MODES:fail("unexpected mode")
                if row["status"] not in ("SAT","UNSAT","TIMEOUT"):fail("bad status")
                val=float(row["par2_s"])
                secs=float(row["total_s"])
                if not math.isfinite(val) or not 0<=secs<=10.00001:
                    fail("invalid timing")
                if row["status"]=="TIMEOUT":
                    if abs(val-20)>1e-6:fail("invalid timeout PAR2")
                elif abs(val-secs)>1e-5:fail("non-timeout PAR2 mismatch")
                records.append(row)
    if len(manifests)!=1:fail("source manifest drift")
    if len(sources)!=24 or len(records)!=24*2*len(MODES):
        fail("wrong corpus size or missing paired trials")
    counts=Counter(x["category"] for x in sources.values())
    if any(counts[c]!=6 for c in COHORTS):fail("unbalanced cohort")
    for sha in sources:
        for rep in (0,1):
            statuses=set()
            for mode in MODES:
                if (sha,rep,mode) not in seen:fail("missing mode pair")
                row=next(x for x in records if
                    x["source"]==sha and int(x["rep"])==rep and x["mode"]==mode)
                if row["status"]!="TIMEOUT":statuses.add(row["status"])
            if len(statuses)>1:fail("SAT/UNSAT disagreement")
    modes={}
    for m in MODES:
        selected=[x for x in records if x["mode"]==m]
        modes[m]=dict(trials=len(selected),
                      solved=sum(x["status"]!="TIMEOUT" for x in selected),
                      par2_s=round(sum(float(x["par2_s"]) for x in selected),6),
                      direct_proposals=sum(int(x["direct_proposals"]) for x in selected),
                      online_rows=sum(int(x["online_rows"]) for x in selected))
    c=modes["clean"]["par2_s"]
    deltas={m:round(100*(c-modes[m]["par2_s"])/c,5) for m in MODES if m!="clean"}
    out=dict(protocol="DRNAS-R149-STRICT-24-REUSED-REAL-CNF-AUDIT-v1",
             blinded=False,
             original_manifest_sha256=next(iter(manifests)),
             data_scope="24 pre-existing R135 formulas, deterministic SHA choice, not new blind",
             formulas=24,measurements=len(records),
             source_category_counts=dict(counts),caps_s=10,reps=2,
             all_pairs_complete=True,all_source_SHA_linked=True,
             cross_solver_SAT_UNSAT_disagreement=False,
             independent_UNSAT_proof=False,
             modes=modes,gain_vs_clean_pct=deltas,
             verdict="DEVELOPMENT_ONLY_NO_PROMOTION")
    (a.out/"strict_report.json").write_text(json.dumps(out,indent=2,sort_keys=True)+"\n")
    print("R149_STRICT_FINAL",json.dumps(out,sort_keys=True),flush=True)

if __name__=="__main__":main()
