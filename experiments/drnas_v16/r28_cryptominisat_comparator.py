#!/usr/bin/env python3
"""R28 vs CryptoMiniSat 5.11 + clean pinned Kissat on SAME existing R28 cohort.

This is a **post-hoc comparator**, not a fresh holdout. 72 evenly selected
cases (12 per family, six families). Keep equal 2 s cap, two paired repeats,
one runner, process-start wall clock, model / parity-certificate validation.
"""
import argparse,csv,hashlib,json,os,random,statistics,subprocess,time
from pathlib import Path
import r28_exact_gf2_benchmark as prior

PROTO="DRNAS-R28-CRYPTOMINISAT-72-MATCHED-20261103"
INDICES=(0,1,4,5,8,9,12,13,16,17,20,21)
MODES=("Kissat_pin","R28_exact_gf2","CryptoMiniSat_5_11")
REPS=2
CAP=2.0
def digest(v):return prior.digest(v)
def run(a):
    root=Path(a.inputs)
    j=json.loads((root/"manifest.json").read_text())
    prior.check(j["protocol"]==prior.PROTO,"Wrong R28 input protocol")
    chosen=[c for c in j["cases"] if c["idx"] in INDICES]
    prior.check(len(chosen)==72,"Expected 72 selected cases")
    out=Path(a.output);out.mkdir(parents=True,exist_ok=True)
    prior.cpu_affinity()
    binary=Path(a.binary).resolve()
    kissat=Path(a.kissat).resolve()
    cms=Path(a.cms).resolve()
    prior.check(binary.is_file() and kissat.is_file() and cms.is_file(),"Missing executable")
    (out/"metadata.json").write_text(json.dumps({
        "protocol":PROTO,"R28_manifest_sha":digest(root/"manifest.json"),
        "r28_binary_sha":digest(binary),"kissat_binary_sha":digest(kissat),
        "cms_binary_sha":digest(cms),"cms_version":subprocess.run(
            [str(cms),"--version"],capture_output=True,text=True,timeout=3).stdout[:500],
        "expected":72*REPS*len(MODES),
        "cpu":next((v for v in Path("/proc/cpuinfo").read_text().splitlines()
            if v.startswith("model name")),"unknown")},indent=2)+"\n")
    rows=[]
    for c in chosen:
        path=(root/c["name"]).resolve()
        prior.check(digest(path)==c["sha256"],"Input SHA identity")
        n,clauses=prior.load_clauses(path)
        for rep in range(REPS):
            modes=list(MODES)
            random.Random(int(digest(f"r28/cms/{c['sha256']}/{rep}".encode()),16)).shuffle(modes)
            for mode in modes:
                if mode=="CryptoMiniSat_5_11":
                    cmd=[str(cms),str(path)]
                elif mode=="Kissat_pin":
                    cmd=[str(kissat),str(path)]
                else:
                    cmd=[str(binary),str(path),str(kissat)]
                started=time.monotonic()
                route="upstream" if mode=="Kissat_pin" else ("CMS" if mode=="CryptoMiniSat_5_11" else "unknown")
                verified="unknown"
                try:
                    p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                                     text=True,errors="replace",timeout=CAP)
                    secs=time.monotonic()-started
                    if p.returncode==10 or "s SATISFIABLE" in p.stdout:
                        status="SAT"
                    elif p.returncode==20 or "s UNSATISFIABLE" in p.stdout:
                        status="UNSAT"
                    else:
                        raise RuntimeError(f"Bad solver exit {mode} {p.returncode}: {p.stderr[-250:]}")
                    if c["expected"]:prior.check(status==c["expected"],"Known GF2 truth mismatch")
                    if mode=="R28_exact_gf2":
                        route=next((l.split()[2] for l in p.stdout.splitlines()
                                    if l.startswith("c R28_ROUTE ")),"MISSING")
                        prior.check(route!="MISSING","Missing R28 route")
                    if status=="SAT":
                        has_model=any(l.startswith("v ") for l in p.stdout.splitlines())
                        if has_model:
                            prior.check(prior.check_sat_model(p.stdout,n,clauses),"Wrong SAT model")
                            verified="SAT_model_checked"
                        elif mode=="CryptoMiniSat_5_11":
                            verified="CMS_no_model_available"
                        else:
                            raise RuntimeError("SAT assignment missing")
                    elif route=="certified_xor_contradiction":
                        prior.check(prior.check_gf2_unsat_proof(p.stdout,clauses),"Invalid UNSAT parity cert")
                        verified="GF2_cert_checked"
                    else:
                        verified="UNSAT_solver_only"
                except subprocess.TimeoutExpired:
                    secs=time.monotonic()-started
                    status="TIMEOUT";route="timeout";verified="not_applicable"
                row={"formula":c["name"],"family":c["family"],"rep":rep,
                     "mode":mode,"status":status,"seconds":round(secs,6),
                     "PAR2":4.0 if status=="TIMEOUT" else round(secs,6),
                     "route":route,"verified":verified}
                rows.append(row)
                (out/"trials.json").write_text(json.dumps(rows,indent=1)+"\n")
                print("R28_CMS_TRIAL",c["name"],rep,mode,status,round(secs,6),
                      route,verified,flush=True)
        labels={r["status"] for r in rows if r["formula"]==c["name"]} - {"TIMEOUT"}
        prior.check(len(labels)<=1,"Solver truth disagreement")
    report={}
    for family in ("ALL",)+prior.FAMILIES:
        g=([x for x in rows if family=="ALL" or x["family"]==family])
        stats={}
        for mode in MODES:
            trials=[x for x in g if x["mode"]==mode]
            stats[mode]={"PAR2_sum":round(sum(x["PAR2"] for x in trials),6),
                         "timeouts":sum(x["status"]=="TIMEOUT" for x in trials),
                         "solved_attempts":sum(x["status"]!="TIMEOUT" for x in trials),
                         "GF2_cert_verified":sum(x["verified"]=="GF2_cert_checked" for x in trials),
                         "CMS_SAT_without_model":sum(x["verified"]=="CMS_no_model_available" for x in trials)}
        report[family]=stats
        print("R28_CMS_SUMMARY",family,json.dumps(stats,sort_keys=True),flush=True)
    final={"protocol":PROTO,"cases":len(chosen),"attempts":len(rows),
           "R28_manifest_sha":digest(root/"manifest.json"),"stats":report,
           "trials":rows,"limitations":["Post-hoc subset of already-measured R28 inputs",
                        "CryptoMiniSat Ubuntu packaged version; verify upstream version before world-class claims",
                        "No official competition industrial inputs in this selected benchmark"]}
    prior.check(len(rows)==432,"Incomplete comparator")
    (out/"comparison.json").write_text(json.dumps(final,indent=2)+"\n")
    md=["# DRNAS R28 — 72-case post-hoc CryptoMiniSat control",
        "12 cases per R28 synthetic family, two repeats, 2s cap, PAR-2 timeout penalty 4s.",
        "Same GitHub runner and CPU affinity, binaries SHA-verified; **not a new blind holdout**.",
        "",
        "| Family | Pinned Kissat PAR2 | R28 GF2 PAR2 | CryptoMiniSat PAR2 |",
        "|---|---:|---:|---:|"]
    for fam,stats in report.items():
        md.append("| "+fam+" | "+" | ".join(f"{stats[m]['PAR2_sum']:.4f}" for m in MODES)+" |")
    (out/"report.md").write_text("\n".join(md)+"\n")
    with (out/"trials.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]))
        w.writeheader();w.writerows(rows)
    print("R28_CMS_AUDIT_PASS",len(rows),len(chosen),flush=True)

def main():
    p=argparse.ArgumentParser()
    for a in ("inputs","output","binary","kissat","cms"):p.add_argument("--"+a,required=True)
    run(p.parse_args())

if __name__=="__main__":main()
