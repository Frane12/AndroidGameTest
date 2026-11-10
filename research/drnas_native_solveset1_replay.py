#!/usr/bin/env python3
"""One-command replay of 4 permanently frozen original DRNAS-solvable SHA.
Own source-built R1, R2B, R3C-plain and R3C-GF2 only. No external solver.
"""
import hashlib, json, pathlib, random
import drnas_native_solveset1 as engine
ROOT=pathlib.Path("mre_drnas_native_solveset1")
FREEZE=pathlib.Path("experiments/drnas_native_solveset1/FROZEN_DEV4.json")
REPS=3
CAP=5.0
def fail(ok,msg):
    if not ok:raise RuntimeError("DRNAS_SOLVESET1_REPLAY_FAIL_CLOSED "+str(msg))
def sha(p):
    return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def main():
    ROOT.mkdir(parents=True,exist_ok=True)
    freeze=json.loads(FREEZE.read_text())
    fail(freeze["protocol"]=="DRNAS-NATIVE-SOLVESET1-FROZEN-DEV4-20261110",
         "not a known original SHA freeze")
    rows=freeze["selected"]
    fail(len(rows)==4 and len({r["sha256"] for r in rows})==4,
         "four unique SHA required")
    locations={}
    manifests={}
    for cohort,mfile,folder,key in (
        ("MIXAB4",pathlib.Path("mre_mixab4/manifest.json"),
         pathlib.Path("mre_mixab4/cases"),"original_cases"),
        ("EQUIV10M5",pathlib.Path("mre_equiv10m5/manifest.json"),
         pathlib.Path("mre_equiv9/cases"),"cases")):
        fail(mfile.is_file(),"missing original source manifest "+str(mfile))
        m=json.loads(mfile.read_text())
        manifests[cohort]=sha(mfile)
        for entry in m[key]:
            source=folder/entry["filename"]
            if entry["sha256"] in {r["sha256"] for r in rows}:
                fail(source.is_file() and sha(source)==entry["sha256"],
                     "original source SHA drift")
                fail(entry["sha256"] not in locations,"repeated source")
                locations[entry["sha256"]]=(cohort,source)
    fail(set(locations)=={r["sha256"] for r in rows},"missing frozen SHA source")
    binary_sha=engine.verify_prereq()
    print("DRNAS_SOLVESET1_REPLAY_FROZEN "+json.dumps(dict(
        sha=[x["sha256"] for x in rows],one_CPU=True,cap_s=CAP,reps=REPS,
        arms=list(engine.BINARIES),
        development_not_blind=True,model_verification=True,
        own_build_sha=binary_sha,source_manifests=manifests),sort_keys=True),flush=True)
    attempts=[]
    for case in rows:
        source=locations[case["sha256"]][1]
        fail(locations[case["sha256"]][0]==case["cohort"],"cohort mismatch")
        for rep in range(REPS):
            arms=list(engine.BINARIES)
            random.Random(case["sha256"]+str(rep)+"FROZEN_DEV4_REPLAY").shuffle(arms)
            for arm in arms:
                out=engine.run_original(source,arm,CAP)
                out.update(source_SHA=case["sha256"],cohort=case["cohort"],
                           rep=rep,cap_s=CAP,development_not_blind=True)
                attempts.append(out)
                engine.save(ROOT/"replay-trials.json",attempts)
                print("DRNAS_SOLVESET1_REPLAY_TRIAL "+json.dumps(out,sort_keys=True),flush=True)
    expected={(r["sha256"],arm,rep) for r in rows
             for arm in engine.BINARIES for rep in range(REPS)}
    actual=[(z["source_SHA"],z["arm"],z["rep"]) for z in attempts]
    fail(len(attempts)==len(expected) and set(actual)==expected,
         "paired original trials missing/duplicated")
    arms_out={}
    by_sha={}
    for arm in engine.BINARIES:
        z=[a for a in attempts if a["arm"]==arm]
        arms_out[arm]=dict(attempts=len(z),
            verified_SAT=sum(a["model_original_verified"] for a in z),
            raw_UNSAT_no_LRAT=sum(a["status"]=="UNSAT" for a in z),
            timeouts=sum(a["status"]=="UNKNOWN" for a in z),
            PAR2_s=round(sum(a["wall_E2E_s"] if a["model_original_verified"]
                 else 2*CAP for a in z),6),
            total_solver_s=round(sum(a["solver_s"] for a in z),6),
            total_E2E_s=round(sum(a["wall_E2E_s"] for a in z),6),
            GF2_derived_implications=sum(a["xor_derived_implications"] for a in z))
    for row in rows:
        by_sha[row["sha256"]]={}
        for arm in engine.BINARIES:
            z=sorted((a for a in attempts if a["source_SHA"]==row["sha256"]
                      and a["arm"]==arm),key=lambda x:x["rep"])
            by_sha[row["sha256"]][arm]=dict(status=[a["status"] for a in z],
                solver_s=[a["solver_s"] for a in z],
                e2e_s=[a["wall_E2E_s"] for a in z],
                verified_SAT=[a["model_original_verified"] for a in z])
    baseline=arms_out["r1"]["PAR2_s"]
    ratios={arm:round(baseline/z["PAR2_s"],5)
            if z["PAR2_s"]>0 else None for arm,z in arms_out.items()}
    report=dict(protocol="DRNAS-NATIVE-FROZEN-DEV4-REPLAY-THREE-REPS",
        original_SHA=[r["sha256"] for r in rows],
        selected_by_previous_R3C_plain_model_verified=True,
        nonblind_development_benchmark=True,
        one_logical_cpu=True,cap_s=CAP,reps=REPS,
        arms=arms_out,PAR2_speedup_vs_R1=ratios,per_SHA=by_sha,
        binary_sha256=binary_sha,source_manifest_sha256=manifests,
        independent_UNSAT_LRAT=False)
    engine.save(ROOT/"frozen-dev4-replay-report.json",report)
    print("DRNAS_SOLVESET1_REPLAY_FINAL "+json.dumps(
       {k:v for k,v in report.items() if k!="per_SHA"},
       sort_keys=True),flush=True)
if __name__=="__main__":main()
