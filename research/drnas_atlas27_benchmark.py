#!/usr/bin/env python3
"""ATLAS27 matched 1CPU evaluation: frozen C7/C26 vs conditional usage gate.

A27 changes only the new arms' deletion-score priority. All SAT witnesses
checked on original CNF. Independent GF2 proof checked only on dedicated
untouched C26_GF2 and C7_GF2 controls. No uncertified UNSAT earns verified PAR2.
"""
import argparse,hashlib,json,os,pathlib,sys
sys.path.insert(0,"research")
import drnas_atlas26_benchmark as A26
import drnas_atlas23_benchmark as Old
import drnas_atlas_wide500 as W

ROOT=pathlib.Path("mre_atlas27")
BIN=ROOT/"bin"
ARMS=("A","C7_ADAPT","C7_ADAPT_GAUSS","C26_REUSE3K",
      "C26_REUSE6K","C26_REUSE6K_GF2","C27_GATE3K",
      "C27_GATE6K","KISSAT","CMS")
CAP={"smoke":3,"regression":10,"extension":12,"hard":12,"fresh":8}
REPS=2
A26.ROOT=ROOT
A26.BIN=BIN
A26.ARMS=ARMS
A26.FIELDS=A26.FIELDS+(
 "atlas27_windows","atlas27_pressure_windows",
 "atlas27_gate_on","atlas27_gate_off","atlas27_active",
 "atlas27_score_eligible","atlas27_bypassed")
FIELDS=A26.FIELDS

def sources(cohort,shard,shards):
    if cohort=="smoke":
        assert shard==0 and shards==1
        cases=A26.sources("smoke",0,1)
        return cases
    if cohort in ("regression","extension"):
        assert shard==0 and shards==1
        return A26.sources(cohort,0,1)
    if cohort=="fresh":
        assert shards==4 and 0<=shard<shards
        cases=[]
        for family in W.SYNTH:
            for index in (180,181):
                n,clauses=W.synth_one(family,index)
                raw=W.canonical(n,clauses)
                sha=hashlib.sha256(raw).hexdigest()
                path=ROOT/"fresh"/f"{family}_{index}.cnf"
                path.parent.mkdir(parents=True,exist_ok=True)
                path.write_bytes(raw)
                cases.append(dict(id=len(cases),family=family,index=index,
                    sha256=sha,source_kind="DETERMINISTIC_GENERATED",
                    path=str(path),archive_entry=f"wide500:{family}:{index}",
                    bytes=len(raw),cohort=cohort))
        assert len(cases)==30 and len({s["sha256"] for s in cases})==30
        return [s for s in cases if s["id"]%shards==shard]
    assert cohort=="hard" and shard==0 and shards==1
    corpus=W.source_corpus(limit=14)
    cases=[]
    for family in W.SOURCES:
        for index in (12,13):
            n,clauses,sha,entry=corpus[family][index]
            raw=W.canonical(n,clauses)
            assert hashlib.sha256(raw).hexdigest()==sha
            path=ROOT/"hard"/f"{family}_{index}.cnf"
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes(raw)
            cases.append(dict(id=len(cases),family=family,index=index,
                sha256=sha,source_kind="SATLIB_ARCHIVE_SHA_PINNED",
                archive_entry=entry,path=str(path),bytes=len(raw),cohort=cohort))
    assert len(cases)==10 and len({s["sha256"] for s in cases})==10
    return cases

def run(source,arm,rep,cap):
    x=A26.run(source,arm,rep,cap)
    if arm.startswith("C27_") and x["status"]!="UNKNOWN":
        t=x["telemetry"]
        expected=3 if arm=="C27_GATE3K" else 4
        if t.get("atlas26_mode")!=expected:
            raise AssertionError("ATLAS27 native mode activation missing")
        for name in ("atlas27_windows","atlas27_pressure_windows",
                     "atlas27_gate_on","atlas27_gate_off",
                     "atlas27_score_eligible","atlas27_bypassed"):
            if t.get(name) is None:raise AssertionError("missing "+name)
    return x

def summarize(rows):
    base=A26.summary(rows)
    for arm in ARMS:
        rr=[r for r in rows if r["arm"]==arm]
        t=lambda name:sum((r["telemetry"].get(name) or 0) for r in rr)
        base[arm].update(gate_windows=t("atlas27_windows"),
          pressure_windows=t("atlas27_pressure_windows"),
          gate_on=t("atlas27_gate_on"),gate_off=t("atlas27_gate_off"),
          gate_eligible=t("atlas27_score_eligible"),
          bypassed=t("atlas27_bypassed"))
    return base

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--cohort",choices=CAP.keys(),required=True)
    ap.add_argument("--shard",type=int,default=0)
    ap.add_argument("--shards",type=int,default=1)
    a=ap.parse_args()
    assert 0<=a.shard<a.shards
    cases=sources(a.cohort,a.shard,a.shards)
    assert cases and len({s["sha256"] for s in cases})==len(cases)
    cap=CAP[a.cohort]
    manifest=dict(cohort=a.cohort,shard=a.shard,shards=a.shards,
         source_shas=[s["sha256"] for s in cases],arms=list(ARMS),
         cap_s=cap,reps=1 if a.cohort=="smoke" else REPS,
         one_cpu=len(os.sched_getaffinity(0))==1,
         original_SHA_checked=True,global_blind_claim=False,
         source_prospective_relative_to_atlas26=a.cohort in ("fresh","hard"),
         code_frozen_before_evaluation=True)
    assert manifest["one_cpu"]
    sha=hashlib.sha256(json.dumps(manifest,sort_keys=True).encode()).hexdigest()
    print("ATLAS27_MANIFEST "+json.dumps(dict(manifest,manifest_sha256=sha),sort_keys=True),flush=True)
    results=[]
    for case in cases:
        for rep in range(manifest["reps"]):
            verdicts=set()
            for arm in ARMS:
                r=run(case,arm,rep,cap)
                results.append(r)
                print("ATLAS27_TRIAL "+json.dumps(r,sort_keys=True),flush=True)
                if r["status"]=="SAT_VERIFIED":verdicts.add("SAT")
                elif r["status"] in ("UNSAT_UNVERIFIED","GF2_UNSAT_VERIFIED"):
                    verdicts.add("UNSAT")
            if len(verdicts)>1:
                raise AssertionError("cross-solver SAT/UNSAT original SHA contradiction")
    assert len(results)==len(cases)*manifest["reps"]*len(ARMS)
    info=dict(manifest=manifest,manifest_sha256=sha,sources=cases,
        rows=results,summary=summarize(results))
    dest=ROOT/a.cohort/f"shard_{a.shard}"
    dest.mkdir(parents=True,exist_ok=True)
    (dest/"results.json").write_text(json.dumps(info,sort_keys=True,indent=2)+"\n")
    print("ATLAS27_FINAL "+json.dumps(dict(cohort=a.cohort,shard=a.shard,
        sources=len(cases),trials=len(results),summary=info["summary"]),
        sort_keys=True),flush=True)

if __name__=="__main__":main()
