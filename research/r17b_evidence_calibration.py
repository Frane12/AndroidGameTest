#!/usr/bin/env python3
"""R17b evidence-calibration only. Development-only, no live solver patch."""
import argparse, csv, hashlib, json, math, random
from collections import Counter, defaultdict
from pathlib import Path

RUN=42094261835
ARTIFACT=13447042971
COMMIT="dc1a94520e90c75bb121203a273215a3c7b55308"
SHA={
 "results.json":"5d026d6117d5c1de4483263245f28bddfd6b929ad2fdc4b137fd6ab5d11ec771",
 "formula_features.csv":"497580181e1c5823a6f01f895fbe915ddc1f83fff1cd961752618d606715a967",
 "paired.csv":"5e25636be2251e83639e3fa776f5695ef3df27d63e258c529bccc82e858d6de9",
 "native_decisions.csv":"b3f746c25df4861f0cd637e10e84c273ffbd01386f7b46f7f763bfffdcafaaba",
}
FOLDS={"random3_development":60,"community3_development":20,
       "random3_test":60,"community3_test":20}
ARMS=("r17_agree50","r17_guarded50")
BOOTSTRAP=3000
MIN_EXPOSURE=10

def need(ok,why):
    if not ok:raise RuntimeError("R17B_FAIL_CLOSED "+why)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def readcsv(p):
    with open(p,newline="") as f:return list(csv.DictReader(f))
def numeric(s):
    x=float(s)
    need(math.isfinite(x) and x>=0,"invalid PAR2")
    return x
def q(v,p):
    v.sort();idx=(len(v)-1)*p;i=int(idx)
    return v[i]+(v[min(i+1,len(v)-1)]-v[i])*(idx-i)
def bootstrap(rs,arm,seed):
    rng=random.Random(seed);s=[]
    for _ in range(BOOTSTRAP):
        sampled=[rng.choice(rs) for _ in rs]
        b=sum(numeric(x["monitor"]) for x in sampled)
        a=sum(numeric(x[arm]) for x in sampled)
        s.append(100*(b-a)/b if b else 0.0)
    return [round(q(s[:],.025),6),round(q(s[:],.975),6)]

def verify(folder):
    for name,digest in SHA.items():
        path=folder/name
        need(path.is_file() and sha(path)==digest,"missing or changed "+name)
    report=json.loads((folder/"results.json").read_text())
    need(report["protocol"]=="R17-live-confidence-abstention-frozen-20261105-v1",
         "protocol mismatch")
    need(report["formulas"]==160 and report["attempts"]==4800,"incomplete audit")
    need(report["sha_disjoint_from_R7_R16"] and report["paired_native_cores_verified"],
         "provenance/native parity not verified")
    need(report["preintervention_mismatches"]==0,"preintervention mismatch")
    need(report["independent_unsat_certificate"] is False,"UNSAT source state changed")
    need(len(report["source_shards"])==16,"incomplete provenance")
    for entry in report["source_shards"]:
        need(entry["source_commit"]==COMMIT and entry["runner"] and
             entry["measurements_sha256"] and entry["source_sha256"],
             "source commit/runner/SHA mismatch")
    rows=readcsv(folder/"formula_features.csv")
    decisions=readcsv(folder/"native_decisions.csv")
    paired=readcsv(folder/"paired.csv")
    need(len(rows)==160 and len(decisions)==960 and len(paired)==1440,
         "aggregate row mismatch")
    need(Counter(r["fold"] for r in rows)==Counter(FOLDS),
         "development/test fold changed")
    need(len(set(r["sha256"] for r in rows))==160,"duplicate formula SHA")
    decision=defaultdict(list)
    for r in decisions:
        need(r["mode"] in ARMS and r["fold"] in FOLDS and r["repeat"] in ("0","1","2"),
             "decision provenance mismatch")
        if r["actual_switch"]:need(r["selected"]=="1","unselected native switch")
        decision[(r["sha256"],r["mode"])].append(r)
    need(len(decision)==320,"missing decision arm")
    pairedmap={(r["sha256"],r["mode"]):r for r in paired}
    need(len(pairedmap)==1440,"duplicate paired arm")
    for r in rows:
        for arm in ARMS:
            dd=decision[(r["sha256"],arm)]
            need(len(dd)==3 and all(d["fold"]==r["fold"] for d in dd),
                 "decision fold/parity mismatch")
            need(sum(d["selected"]=="1" for d in dd)==int(r[arm+"_selected"]),
                 "selected mismatch")
            need(sum(bool(d["actual_switch"]) for d in dd)==int(r[arm+"_switched"]),
                 "switched mismatch")
            p=pairedmap[(r["sha256"],arm)]
            need(p["fold"]==r["fold"] and
                 abs(numeric(p["monitor_PAR2_s"])-numeric(r["monitor"]))<1e-6 and
                 abs(numeric(p["treatment_PAR2_s"])-numeric(r[arm]))<1e-6,
                 "paired performance mismatch")
    return report,rows

def calibrate(report,rows):
    dev=[x for x in rows if x["fold"].endswith("_development")]
    need(len(dev)==80,"training/test crossover")
    cohorts=[("all_development",dev)]
    for fold in ("random3_development","community3_development"):
        rs=[r for r in dev if r["fold"]==fold]
        cohorts.append((fold,rs))
        for n in (200,220,240):
            sub=[r for r in rs if int(r["n"])==n]
            if sub:cohorts.append((fold+"_n"+str(n),sub))
    model={
     "model_id":"R17b-evidence-calibration-20261105-v1",
     "deployment_status":"OFFLINE_ONLY_ABSTAIN_NO_SOLVER_CHANGE",
     "source":{"run_id":RUN,"artifact_id":ARTIFACT,"commit":COMMIT,
               "file_sha256":SHA,
               "frozen_r15_model_sha256":report["frozen_r15_model_sha256"]},
     "training":{"development_formulas":80,"test_formulas_excluded":80,
                 "formula_bootstrap_repetitions":BOOTSTRAP,
                 "min_intervened_distinct_development_formulas":MIN_EXPOSURE,
                 "test_labels_used":False},
     "frozen_existing_gates":{
       "r17_agree50":{"trajectory":.25,"snapshot":.05,"novelty_max":2.5},
       "r17_guarded50":{"trajectory":.40,"snapshot":.10,"novelty_max":2.0}},
     "risk_by_cohort":{},"safety":{
       "default":"MONITOR_ABSTAIN","v1531_modified":False,
       "unsat_independent_proof_verified":False,
       "requires_new_SHA_disjoint_external_prospective_validation":True,
       "not_a_live_speedup":True}}
    tab=[]
    for cohort,rs in cohorts:
        records={};eligible=[]
        for i,arm in enumerate(ARMS):
            b=sum(numeric(r["monitor"]) for r in rs)
            t=sum(numeric(r[arm]) for r in rs)
            exposed={r["sha256"] for r in rs if int(r[arm+"_switched"])>0}
            ci=bootstrap(rs,arm,170017+sum(map(ord,cohort))*17+i)
            harmful=sum(numeric(r[arm])>2*numeric(r["monitor"]) for r in rs)
            qualifies=len(exposed)>=MIN_EXPOSURE and ci[0]>0 and harmful==0
            rec={"formula_count":len(rs),"intervened_formula_count":len(exposed),
                 "switched_attempts":sum(int(r[arm+"_switched"]) for r in rs),
                 "selected_attempts":sum(int(r[arm+"_selected"]) for r in rs),
                 "monitor_PAR2_s":round(b,6),"treatment_PAR2_s":round(t,6),
                 "gain_percent":round(100*(b-t)/b,6) if b else 0,
                 "formula_bootstrap95_gain_pct":ci,"twofold_regression_formulas":harmful,
                 "eligible_for_future_candidate":qualifies}
            records[arm]=rec
            tab.append({"cohort":cohort,"policy":arm,**rec})
            if qualifies:eligible.append(arm)
        choice=max(eligible,key=lambda a:records[a]["formula_bootstrap95_gain_pct"][0]) if eligible else "MONITOR_ABSTAIN"
        model["risk_by_cohort"][cohort]={"replay_only_candidate":choice,"arms":records}
    model["hypotheses"]=[
      "Novelty and two-model agreement may reduce harmful restart switches.",
      "Few independent intervened formulas: use confidence proxies as uncalibrated.",
      "Validate on a newly acquired SHA-disjoint external prospective cohort before any live policy promotion."
    ]
    return model,tab

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--source",required=True,type=Path)
    p.add_argument("--out",required=True,type=Path)
    a=p.parse_args()
    report,rows=verify(a.source)
    model,tab=calibrate(report,rows)
    # Metamorphic leakage test: change all TEST treatment and baseline
    # performance labels; the development-only model MUST remain byte-equal.
    tampered=[dict(x) for x in rows]
    for r in tampered:
        if r["fold"].endswith("_test"):
            for k in ("monitor",)+ARMS:r[k]="99999.0"
    second,_=calibrate(report,tampered)
    need(model==second,"test fold leaked into training")
    a.out.mkdir(parents=True,exist_ok=True)
    result=a.out/"r17b_evidence_model.json"
    result.write_text(json.dumps(model,sort_keys=True,indent=2)+"\n")
    with (a.out/"r17b_development_calibration.csv").open("w",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=list(tab[0]))
        writer.writeheader();writer.writerows(tab)
    audit={"verified_parent_run":RUN,"source_artifact":ARTIFACT,
           "source_commit":COMMIT,"model_sha256":sha(result),
           "source_sha256":SHA,"development_formulas":80,
           "excluded_test_formulas":80,"test_leakage_metamorphic_check":"PASS",
           "new_SAT_solves":0,"V1531_changed":False,
           "final_live_speedup_claimed":False}
    (a.out/"audit.json").write_text(json.dumps(audit,sort_keys=True,indent=2)+"\n")
    print("R17B_CALIBRATION_PASS "+json.dumps({
      "model_sha256":sha(result),"development":80,"excluded_test":80,
      "selected":model["risk_by_cohort"]["all_development"]["replay_only_candidate"]},
      sort_keys=True))
if __name__=="__main__":main()
