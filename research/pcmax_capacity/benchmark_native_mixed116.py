#!/usr/bin/env python3
"""Source-paired native opt-in math guard vs unchanged Hall2 on frozen 116 CNFs."""
import argparse,hashlib,json,os,random,subprocess,sys,time
from pathlib import Path
from random_unsat_probe import cases,SEED,write_cnf,satisfied,exact_sat
from check_clause_hall import check as hall_check
from check_mixed_unsat import verify as mixed_check

def run(binary,cnf,proof,mode,budget_ms=400):
    cmd=[str(binary.resolve()),str(cnf.resolve()),"--mode","core",
         "--time","2","--pcmax-only","--pcmax-budget-ms",str(budget_ms),
         "--pcmax-clause-guard" if mode=="HALL2" else "--math-mixed-guard",
         "--pcmax-certificate",str(proof.resolve())]
    t=time.perf_counter()
    try:p=subprocess.run(cmd,capture_output=True,text=True,timeout=4)
    except subprocess.TimeoutExpired as e:raise AssertionError((mode,cnf,"HARD_TIMEOUT")) from e
    elapsed=time.perf_counter()-t
    tel=[json.loads(l.split("c PCMAX_CAPACITY ",1)[1])
         for l in p.stdout.splitlines() if l.startswith("c PCMAX_CAPACITY ")]
    return p,elapsed,tel[-1] if tel else {}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--binary",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    a.out.mkdir(parents=True,exist_ok=False)
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    formulas=cases(random.Random(SEED))
    results=[]
    with (a.out/"trials.jsonl").open("w") as f:
        for i,c in enumerate(formulas):
            src=a.out/(c["name"]+".cnf")
            raw=write_cnf(src,c["clauses"],c["nvars"])
            if c["expected"]=="SAT":
                assert satisfied(c["clauses"],c["model"])
            if c["family"] in ("unsat_2sat","xor_parity_unsat","random_3sat_unsat"):
                assert exact_sat(c["clauses"],c["nvars"]) is None
            for arm in ("HALL2","MIXED_NATIVE"):
                cert=a.out/(c["name"]+"."+arm+".json")
                trial,e2e,tel=run(a.binary,src,cert,arm)
                if trial.returncode==20:
                    assert cert.is_file(),("UNSAT without cert",arm,c["name"])
                    data=json.loads(cert.read_text())
                    outcome=(hall_check(raw,data) if data.get("format")=="pcmax-clause-hall-v1"
                             else mixed_check(raw,data))
                    assert outcome["status"] in ("UNSAT_VERIFIED","UNSAT_CLAUSE_HALL_CERTIFICATE_VERIFIED")
                    assert c["expected"]=="UNSAT",("FALSE UNSAT",arm,c["name"])
                    status="UNSAT_VERIFIED"
                    method=data.get("method","hall2")
                elif trial.returncode==0 and "s UNKNOWN" in trial.stdout:
                    assert not cert.exists(),("unexpected certificate",arm,c["name"])
                    status="UNKNOWN";method=None
                else:
                    raise AssertionError(("solver error",arm,c["name"],trial.returncode,
                                          trial.stdout[-1000:],trial.stderr[-1000:]))
                row={"id":i,"name":c["name"],"family":c["family"],"expected":c["expected"],
                     "arm":arm,"status":status,"method":method,
                     "e2e_s":round(e2e,6),"reason":tel.get("reason","unknown"),
                     "source_sha256":hashlib.sha256(raw).hexdigest()}
                f.write(json.dumps(row,sort_keys=True)+"\n");f.flush()
                results.append(row)
                print("MIXED_NATIVE_TRIAL "+json.dumps(row,sort_keys=True),flush=True)
    summary={"seed":SEED,"source_count":len(formulas),"trial_count":len(results),
             "verified_by_arm":{arm:sum(r["status"]=="UNSAT_VERIFIED" for r in results if r["arm"]==arm)
                for arm in ("HALL2","MIXED_NATIVE")},
             "false_unsat":sum(r["expected"]=="SAT" and r["status"]=="UNSAT_VERIFIED" for r in results),
             "methods":{arm:sorted(set(r["method"] for r in results if r["arm"]==arm and r["method"]))
                for arm in ("HALL2","MIXED_NATIVE")},
             "binary_sha256":hashlib.sha256(a.binary.read_bytes()).hexdigest()}
    (a.out/"summary.json").write_text(json.dumps(summary,indent=2)+"\n")
    print("MIXED_NATIVE_SUMMARY "+json.dumps(summary,sort_keys=True),flush=True)
    assert summary["false_unsat"]==0
    assert summary["verified_by_arm"]["HALL2"]==54
    assert summary["verified_by_arm"]["MIXED_NATIVE"]==88

if __name__=="__main__":main()
