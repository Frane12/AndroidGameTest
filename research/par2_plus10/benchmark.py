#!/usr/bin/env python3
"""Two-era source-paired STRICT E2E diagnostic: frozen SAT2025/26 originals.
Retrospective validation ONLY. Does not satisfy a new prospective blind holdout.
No main promotion; original source bytes + executable SHA256 pinned before trials.
"""
import argparse, collections, hashlib, json, os, random, statistics, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"research/unified_evidence"))
import benchmark as base
import importlib.util
spec=importlib.util.spec_from_file_location("math5_strict_runner",ROOT/"research/math5_standard_real67/benchmark.py")
m5=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m5)

OUT=ROOT/"results/par2_plus10"
MANIFEST25=ROOT/"sat_real2025_inputs/manifest.json"
MANIFEST25_SHA="47cc882a3893b2ecaf543341040d41c417eb13d8eb940198d37143715f65db4e"
CAP=12.0
REPS=2
SHARDS=10
ARMS=("X59_MATH5_VERIPB","X59_OFF","CXX_UNION","Kissat","CaDiCaL","CryptoMiniSat")
REFERENCES=("Kissat","CaDiCaL","CryptoMiniSat")
# Independent conventional model / proof check; project-only structural checks
# NEVER count as strict verified.
STRICT={"MODEL","DRAT","FRAT","VERIPB_CAPACITY","VERIPB_MATH5"}
# The frozen 2026 runner supports a different cap via these process-local globals.
# Base prespec/corpus is unchanged and cryptographically validated.
base.CAP=CAP
m5.CAP=CAP

def digest(p):
    return base.sha(p)
def put(p,x):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(x,sort_keys=True,indent=2)+"\n")

def sources():
    historical=base.frozen_sources()
    assert historical["selected"]==67
    assert digest(MANIFEST25)==MANIFEST25_SHA,"SAT2025 frozen manifest changed"
    manifest25=json.loads(MANIFEST25.read_text())
    assert manifest25["protocol"]=="DRNAS-REAL2025-FROZEN-ORIGINAL-V1"
    assert manifest25["ready_count"]==len(manifest25["ready_sources"])==19
    result={}
    a=[]
    for src in historical["sources"]:
        assert digest(ROOT/src["path"])==src["sha256"]
        a.append(dict(src,era="SAT2026",old_id=src["id"]))
    result["SAT2026"]=a
    b=[]
    for idx,src in enumerate(manifest25["ready_sources"]):
        assert src["status"]=="READY"
        assert digest(ROOT/src["path"])==src["sha256"]
        b.append(dict(id=idx,old_id=src["index"],era="SAT2025",
                      path=src["path"],sha256=src["sha256"],file_id=str(src["gbd"]),
                      family="SAT2025_ORIGINALS",catalog_label="unknown"))
    assert len({x["sha256"] for x in b})==19
    result["SAT2025"]=b
    # Guard against cross-era duplicates.
    assert len({x["sha256"] for seq in result.values() for x in seq})==86
    return result

def preflight():
    base.affinity()
    data=sources()
    binary_sha=base.pinned()
    controls=m5.proof_preflight()
    proto=dict(
        protocol="DRNAS-PAR2-PLUS10-TWO-ERA-RETROSPECTIVE-V1",
        status="PRECOMMITTED_DIAGNOSTIC_NOT_BLIND",
        git_sha=os.environ.get("GITHUB_SHA"),
        frozen_2026_sha=digest(base.DATA/"manifest.json"),
        frozen_2025_sha=digest(MANIFEST25),
        frozen_binaries=binary_sha,
        script_sha=digest(Path(__file__)),
        cap_s=CAP,repetitions=REPS,shards=SHARDS,arms=ARMS,
        counts={k:len(v) for k,v in data.items()},
        expected_trials=sum(map(len,data.values()))*REPS*len(ARMS),
        strict_proofs=sorted(STRICT),
        source_families="2026 labels; 2025 conservative single cluster",
        one_logical_cpu_per_solver=True,serial_paired=True,
        no_portfolio=True,no_main_promotion=True,
        retrospective_used_sources=True,prospective_goal_not_claimed=True,
        selftests=controls)
    put(OUT/"protocol.json",proto)
    print("PLUS10_READY "+json.dumps({
        "sources":sum(map(len,data.values())),
        "trials":proto["expected_trials"],"cap_s":CAP,
        "sha25":proto["frozen_2025_sha"],"sha26":proto["frozen_2026_sha"]
    },sort_keys=True),flush=True)

def check():
    base.affinity()
    data=sources()
    p=json.loads((OUT/"protocol.json").read_text())
    assert p["protocol"]=="DRNAS-PAR2-PLUS10-TWO-ERA-RETROSPECTIVE-V1"
    assert p["git_sha"]==os.environ.get("GITHUB_SHA")
    assert p["script_sha"]==digest(Path(__file__))
    assert p["frozen_binaries"]==base.pinned()
    assert p["frozen_2026_sha"]==digest(base.DATA/"manifest.json")
    assert p["frozen_2025_sha"]==digest(MANIFEST25)
    assert p["cap_s"]==CAP and p["repetitions"]==REPS
    assert p["arms"]==list(ARMS) and p["shards"]==SHARDS
    return data,p

def test_one(src,arm,rep):
    if arm=="X59_MATH5_VERIPB":
        row=m5.standard_trial(src,rep)
    else:
        row=base.trial(src,arm,rep)
    row["era"]=src["era"]
    assert row["source_sha256"]==src["sha256"]
    assert row["id"]==src["id"] and row["arm"]==arm
    assert row["rep"]==rep and row["PAR2_strict_s"]>=0
    # Protect against accidentally crediting a nonstandard custom certificate.
    if row["strict_accepted"]:
        assert row["accepted"] and row["certificate_kind"] in STRICT
        assert row["e2e_s"]<=CAP
    return row

def shard(n):
    assert 0<=n<SHARDS
    data,_=check()
    directory=OUT/f"shard-{n}"
    directory.mkdir(parents=True,exist_ok=False)
    rows=0
    with (directory/"trials.jsonl").open("w") as out:
        for era in ("SAT2025","SAT2026"):
            for src in data[era]:
                if src["id"]%SHARDS!=n:continue
                for rep in range(REPS):
                    order=list(ARMS)
                    random.Random(f"{era}:{src['sha256']}:{rep}:20261116").shuffle(order)
                    state={}
                    for arm in order:
                        r=test_one(src,arm,rep)
                        out.write(json.dumps(r,sort_keys=True)+"\n")
                        out.flush()
                        rows+=1
                        state[arm]=[r["status"],round(r["PAR2_strict_s"],3)]
                    print("PLUS10_SOURCE "+json.dumps(dict(era=era,id=src["id"],
                        rep=rep,results=state),sort_keys=True),flush=True)
    expected=sum(sum(x["id"]%SHARDS==n for x in data[era]) for era in data)*REPS*len(ARMS)
    assert rows==expected
    print("PLUS10_SHARD "+json.dumps(dict(shard=n,trials=rows),sort_keys=True),flush=True)

def totals(rows):
    d={}
    for arm in ARMS:
        r=[x for x in rows if x["arm"]==arm]
        d[arm]=dict(
            attempts=len(r),
            strict_verified=sum(bool(x["strict_accepted"]) for x in r),
            strict_PAR2_s=round(sum(x["PAR2_strict_s"] for x in r),6),
            sat=sum(x["strict_accepted"] and x["status"]=="SAT_VERIFIED" for x in r),
            unsat=sum(x["strict_accepted"] and x["status"]=="UNSAT_VERIFIED" for x in r),
            status=dict(collections.Counter(x["status"] for x in r)))
    return d

def confidence(rows,srcs,reference):
    # Source-cluster bootstrap; 2025 corpus is a single conservative cluster.
    lookup={(x["era"],x["id"],x["rep"],x["arm"]):x["PAR2_strict_s"] for x in rows}
    clusters=collections.defaultdict(list)
    for era,group in srcs.items():
        for src in group:
            clusters[(era,src["family"])].append(src)
    chunks=[]
    for members in clusters.values():
        a=b=0.0
        for s in members:
            for rep in range(REPS):
                a+=lookup[s["era"],s["id"],rep,"X59_MATH5_VERIPB"]
                b+=lookup[s["era"],s["id"],rep,reference]
        chunks.append((a,b))
    rng=random.Random(20261116)
    estimates=[]
    for _ in range(3000):
        sample=[chunks[rng.randrange(len(chunks))] for i in chunks]
        dra=sum(x for x,y in sample)
        ref=sum(y for x,y in sample)
        estimates.append(100*(1-dra/ref) if ref else 0)
    estimates.sort()
    return dict(family_clusters=len(chunks),
                gain_percent_95pct_bootstrap=[
                    round(estimates[75],4),round(estimates[2924],4)])

def report():
    srcs,p=check()
    rows=[]
    for n in range(SHARDS):
        path=OUT/f"shard-{n}"/"trials.jsonl"
        assert path.is_file(),("missing shard",n)
        rows += [json.loads(v) for v in path.read_text().splitlines()]
    observed={(x["era"],x["id"],x["rep"],x["arm"]) for x in rows}
    expected={(era,s["id"],rep,arm) for era,all_src in srcs.items()
              for s in all_src for rep in range(REPS) for arm in ARMS}
    assert observed==expected and len(rows)==len(expected)==p["expected_trials"],"incomplete matrix"
    srcmap={(e,s["id"]):s for e,ss in srcs.items() for s in ss}
    problems=[]
    for r in rows:
        src=srcmap[r["era"],r["id"]]
        if r["source_sha256"]!=src["sha256"] or r["family"]!=src["family"]:
            problems.append(("hash or family",r["era"],r["id"]))
        if r["critical"]:problems.append(("critical",r["era"],r["id"],r["arm"],r["status"]))
        if r["strict_accepted"] and (
            not r["accepted"] or r["certificate_kind"] not in STRICT or r["e2e_s"]>CAP):
            problems.append(("invalid strict",r["era"],r["id"],r["arm"]))
    for era,all_src in srcs.items():
        for s in all_src:
            verdicts={r["status"].split("_")[0] for r in rows
                      if r["era"]==era and r["id"]==s["id"] and r["strict_accepted"]}
            if len(verdicts)>1:problems.append(("contradictory",era,s["id"],sorted(verdicts)))
    results={}
    for era in ("SAT2025","SAT2026","COMBINED"):
        rr=rows if era=="COMBINED" else [r for r in rows if r["era"]==era]
        sums=totals(rr)
        best=min(REFERENCES,key=lambda arm:sums[arm]["strict_PAR2_s"])
        candidate="X59_MATH5_VERIPB"
        a=sums[candidate]["strict_PAR2_s"];b=sums[best]["strict_PAR2_s"]
        gain=100*(1-a/b)
        results[era]=dict(
            sources=len(rr)//(len(ARMS)*REPS),
            best_reference=best,
            gain_percent=round(gain,4),
            passes_numeric_plus10=gain>=10,
            strict_totals=sums)
    combined=confidence(rows,srcs,results["COMBINED"]["best_reference"])
    out=dict(status="FAILED" if problems else "COMPLETE",
             diagnostic_only=True,holdout_target_achieved=False,
             protocol=p,results=results,confidence=combined,
             critical=problems,
             limitations=[
               "Retrospective 2025+2026 original CNF samples previously used elsewhere in this repository.",
               "No new blind holdout or family-disjoint prospective generalization claim.",
               "The MATH5 and CXX_UNION arms are separate ablations, not a newly integrated IPG7 build.",
               "12-second strict E2E cap is a new diagnostic, not a competition leaderboard score."
             ])
    put(OUT/"final.json",out)
    print("PLUS10_FINAL "+json.dumps(dict(
        status=out["status"],sources=86,trials=len(rows),
        eras={e:dict(gain_percent=x["gain_percent"],
                     best_reference=x["best_reference"],
                     strict_totals={k:dict(par2=v["strict_PAR2_s"],
                       verified=v["strict_verified"])
                       for k,v in x["strict_totals"].items()})
              for e,x in results.items()},
        confidence=combined,critical_count=len(problems),
        diagnostic_only=True),sort_keys=True),flush=True)
    if problems:raise SystemExit(1)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("prepare","shard","report"))
    p.add_argument("--index",type=int)
    args=p.parse_args()
    if args.action=="prepare":preflight()
    elif args.action=="shard":shard(args.index)
    else:report()
