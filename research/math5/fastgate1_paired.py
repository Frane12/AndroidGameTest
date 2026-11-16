#!/usr/bin/env python3
"""Proof-gated C++ BDD signature A/B against frozen unchanged C++ BDD3.

No training/holdout claims: 6 old original CNFs and 8 deterministic
generated BDD PCMAX fixtures. Same exact source, order alternated per
pair, 8-second E2E cap including proof verification; one logical CPU.
"""
import hashlib,json,os,pathlib,random,sys
ROOT=pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"research"/"unified_evidence"))
import benchmark as original
sys.path.insert(0,str(ROOT/"research"))
from ipg_bdd_fixtures import cases
from ipg1_fixtures import petersen

OUT=ROOT/"results/fastgate1_paired"
original.BIN["CXX_FAST"]="build/drnas-pcmax-mg7-ipg1-bdd3-fastgate1"
ARMS=("CXX_BDD3","CXX_FAST","CXX_BASE")
SELECTED_ORIGINAL_IDS=(0,3,7,12,25,31)

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def original_entries():
    manifest=json.loads((ROOT/"unified_realblind100_inputs/manifest.json").read_text())
    source={s["id"]:s for s in manifest["sources"]}
    result=[]
    for i in SELECTED_ORIGINAL_IDS:
        row=source[i]
        path=ROOT/row["path"]
        if sha(path)!=row["sha256"]:raise ValueError("original bytes changed")
        result.append(row)
    return result

def synthetic_entries():
    path=OUT/"bdd_source_controls"
    samples=cases(path)[:8]
    records=[]
    for i,c in enumerate(samples):
        f=path/c["name"]
        if sha(f)!=c["sha256"]:raise ValueError("fixture not frozen")
        records.append({"id":100+i,"path":str(f.relative_to(ROOT)),
                        "sha256":c["sha256"],"file_id":c["name"],
                        "family":"GENERATED_BDD_ORACLE",
                        "catalog_label":c["expected"].lower(),
                        "expected_oracle":c["expected"]})
    return records

def main():
    if hasattr(os,"sched_setaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    OUT.mkdir(parents=True,exist_ok=True)
    for arm in ARMS:
        binary=ROOT/original.BIN[arm]
        if not binary.is_file():raise FileNotFoundError(binary)
    sources=original_entries()+synthetic_entries()
    # IPG1 needs no BDD source encoding. Retain its Petersen proof route.
    petersen_raw=petersen().encode("ascii")
    petersen_sha=hashlib.sha256(petersen_raw).hexdigest()
    assert petersen_sha=="c2fefeffc1f9644ffd6f85728106a21c82dfc01d0d021f32d4d73569cc2bfb70"
    petersen_file=OUT/"petersen-original45v300c.cnf"
    petersen_file.write_bytes(petersen_raw)
    sources.append({"id":109,"path":str(petersen_file.relative_to(ROOT)),
        "sha256":petersen_sha,"file_id":petersen_file.name,
        "family":"RETROSPECTIVE_ORIGINAL_PETERSEN_IPG1",
        "catalog_label":"unsat"})
    trials=[]
    for src in sources:
        order=list(ARMS)
        random.Random(int(src["sha256"][:12],16)).shuffle(order)
        for arm in order:
            row=original.trial(src,arm,0)
            row["source_kind"]=("ORIGINAL_PETERSEN_IPG1" if src["id"]==109 else
               ("GENERATED_BDD_ORACLE" if src["id"]>=100 else "RETROSPECTIVE_ORIGINAL_2026"))
            if row["critical"] or row["status"].startswith(("INVALID","SOLVER_ERROR")):
                raise ValueError("invalid proof/model "+str(row))
            if src.get("expected_oracle")=="SAT" and row["accepted"] and row["status"]=="UNSAT_VERIFIED":
                raise ValueError("false UNSAT on SAT oracle")
            trials.append(row)
            print("FASTGATE1_TRIAL "+json.dumps({k:row.get(k) for k in (
              "id","arm","status","certificate_kind","accepted","strict_accepted",
              "e2e_s","PAR2_s","PAR2_strict_s")},sort_keys=True),flush=True)
    summary={"status":"PASS","retrospective_originals":len(SELECTED_ORIGINAL_IDS),
             "generated_bdd_fixtures":len(sources)-len(SELECTED_ORIGINAL_IDS)-1,
             "original_petersen_ipg1_fixture":1,
             "trials":len(trials),"per_arm":{},"cap_s":original.CAP,
             "one_cpu":True,"no_unchecked_results":True,
             "not_blind":True}
    for arm in ARMS:
        rows=[r for r in trials if r["arm"]==arm]
        summary["per_arm"][arm]={
            "verified":sum(r["accepted"] for r in rows),
            "strict_verified":sum(r["strict_accepted"] for r in rows),
            "structural_PAR2_s":round(sum(r["PAR2_s"] for r in rows),6),
            "strict_PAR2_s":round(sum(r["PAR2_strict_s"] for r in rows),6),
            "solved_e2e_s":[{"id":r["id"],"seconds":r["e2e_s"]}
                            for r in rows if r["accepted"]]}
    per_id={(r["id"],r["arm"]):r for r in trials}
    proof_regressions=[]
    for src in sources:
        earlier=per_id[(src["id"],"CXX_BDD3")]
        new=per_id[(src["id"],"CXX_FAST")]
        if earlier["accepted"] and not new["accepted"]:
            proof_regressions.append(src["id"])
    summary["solved_to_unsolved_regressions"]=proof_regressions
    if proof_regressions:
        summary["status"]="REGRESSION"
    (OUT/"trials.json").write_text(json.dumps(trials,indent=2,sort_keys=True)+"\n")
    (OUT/"summary.json").write_text(json.dumps(summary,indent=2,sort_keys=True)+"\n")
    print("FASTGATE1_FINAL "+json.dumps(summary,sort_keys=True),flush=True)
    if proof_regressions:raise SystemExit(1)

if __name__=="__main__":main()
