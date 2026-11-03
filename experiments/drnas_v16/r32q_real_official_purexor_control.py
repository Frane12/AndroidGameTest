#!/usr/bin/env python3
"""R32q: previously examined SATComp2026 CNF, original Kissat vs existing R28 GF2.

This is a DIAGNOSTIC of a known exact-XOR official GBD instance, not blind
validation, not a new GF2 algorithm, no new competitive/world result.
One solver per attempt; same host, same original CNF, SHA-locked.
"""
from __future__ import annotations
import hashlib,json,os,random,re,statistics,subprocess,time
from pathlib import Path
import argparse
import r28_exact_gf2_benchmark as r28

TARGET="75429ff7acb5acb597abe01aa745c2a6"
TIME_CAP=60.
REPETITIONS=2
MODES=("clean_kissat","r28_exact_gf2")

def verify(v,msg):
    if not v:raise RuntimeError("R32Q_OFFICIAL_DIAGNOSTIC_FAILURE "+str(msg))
def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def perform(source,mode,clean,gf2,clauses,n):
    cmd=[str(clean),str(source)] if mode=="clean_kissat" else [
         str(gf2),str(source),str(clean)]
    start=time.monotonic()
    try:
        p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                encoding="utf-8",errors="replace",timeout=TIME_CAP)
        wall=time.monotonic()-start
        verify(p.returncode in (10,20),"Unexpected native solver exit")
        status="SAT" if p.returncode==10 else "UNSAT"
        verify(status=="SAT","Known official SHA status should be SAT")
        verify(r28.check_sat_model(p.stdout,n,clauses),
                "Original 2026 SAT CNF witness invalid")
        if mode=="r28_exact_gf2":
            found=re.findall(r"^c R28_ROUTE (\S+) rank=(\d+) equations=(\d+) clauses=(\d+) covered=(\d+)$",
                  p.stdout,re.MULTILINE)
            verify(len(found)==1 and found[0][0]=="certified_pure_xor_sat",
                   "Exact certified XOR route not taken")
            verify(int(found[0][2])==250 and int(found[0][4])==len(clauses),
                   "Native XOR algebra did not cover all original CNF clauses")
            route=found[0][0]
        else:route="plain_original"
        return dict(status=status,wall_s=round(wall,6),
                    par2_s=round(wall,6),original_source_model_checked=True,
                    route=route)
    except subprocess.TimeoutExpired:
        return dict(status="TIMEOUT",wall_s=round(time.monotonic()-start,6),
                    par2_s=120.,original_source_model_checked=False,
                    route="censored_at_60s")

def main():
    p=argparse.ArgumentParser()
    for name in ("frozen","clean","gf2","out"):p.add_argument("--"+name,required=True)
    a=p.parse_args()
    frozen=Path(a.frozen);manifest=json.loads((frozen/"manifest.json").read_text())
    verify(manifest["protocol"].startswith("DRNAS-R32P-REAL-SATCOMP2026"),
            "Only exact frozen R32p external original accepted")
    record=next(x for x in manifest["cases"] if x["gbd"]==TARGET)
    source=(frozen/record["name"]).resolve()
    verify(digest(source)==record["sha256"],"Official DIMACS identity mismatch")
    clean=Path(a.clean).resolve();gf2=Path(a.gf2).resolve()
    verify(clean.is_file() and gf2.is_file(),"Missing pinned solver binaries")
    n,clauses=r28.load_clauses(source)
    verify(n==250 and len(clauses)==1000,
           "Target source was changed from official 250-variable 1000-clause CNF")
    if hasattr(os,"sched_getaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    rows=[]
    for repeat in range(REPETITIONS):
        order=list(MODES);random.Random(32026250+repeat).shuffle(order)
        for mode in order:
            r=perform(source,mode,clean,gf2,clauses,n)
            rows.append(dict(mode=mode,repeat=repeat,**r))
            print("R32Q_TRIAL",mode,repeat,r,flush=True)
    verify(len(rows)==4,"Missing exact four matched trial attempts")
    results={}
    for mode in MODES:
        v=[r for r in rows if r["mode"]==mode]
        results[mode]=dict(median_wall_s=statistics.median(r["wall_s"] for r in v),
                           sum_PAR2_s=sum(r["par2_s"] for r in v),
                           solved=sum(r["status"]=="SAT" for r in v),
                           timeout=sum(r["status"]=="TIMEOUT" for r in v))
    verify(results["r28_exact_gf2"]["solved"]==2,"R28 must prove both real original SAT witnesses")
    report=dict(protocol="R32Q-PREVIOUSLY-SEEN-OFFICIAL-XOR-20261103",
        original_gbd=TARGET,original_sha256=record["sha256"],
        original_uri=record["source"],n=n,m=len(clauses),
        clean_binary_sha256=digest(clean),r28_binary_sha256=digest(gf2),
        rows=rows,summary=results,
        limitations=[
          "Previously examined real SATComp2026 exact-XOR original, not blind holdout",
          "R28 is a SEPARATE established GF2 preprocessing/fallback prototype, not R32n",
          "Each solver alone on identical runner with random order; no parallel SAT portfolio",
          "The original plain solver timeout is censored; do not claim precise wall speedup factor",
          "Only one specially selected original formula; not a representative competition benchmark",
          "Original SAT witness checked against all 1000 source CNF clauses",
          "R28 Gauss elimination on complete XOR CNF is known prior art",
          "Official competition hardware/cutoff not reproduced"])
    dest=Path(a.out);dest.mkdir(parents=True,exist_ok=True)
    (dest/"r32q-results.json").write_text(json.dumps(report,indent=2)+"\n")
    lines=["# R32q controlled exact-GF2 diagnosis on a known SATComp2026 original",
      "Previously examined source, NOT blind. One process per attempt, 60s cap, 2 repetitions.",
      "Exact GBD ID: "+TARGET,"SHA256 original: "+record["sha256"],
      "No P=NP novelty claim: algebraic XOR Gaussian elimination is established.",
      "",
      "| Mode | SAT solved | Median observed time s | PAR2 total s |",
      "|---|---:|---:|---:|"]
    for key in MODES:
        z=results[key]
        lines.append(f'| {key} | {z["solved"]}/2 | {z["median_wall_s"]:.6f} | {z["sum_PAR2_s"]:.6f} |')
    lines+=["","The original SAT witness is independently verified on all 1000 clauses.",
      "Plain Kissat timeouts reflect a 60s censoring threshold, not a measured time of 60 seconds."]
    (dest/"r32q-results.md").write_text("\n".join(lines)+"\n")
    print("R32Q_REAL_OFFICIAL_DIAGNOSTIC_AUDIT_PASS",json.dumps(results),flush=True)

if __name__=="__main__":main()
