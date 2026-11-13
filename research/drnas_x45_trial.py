#!/usr/bin/env python3
"""X4.5 blind prospective paired trial: native decision-level SHAM/FIXED/ONLINE.

Five arms per identical ORIGINAL input: independent X4.1 CORE, X3 ADAPTIVE,
X4.5 SHAM (probe/no intervention), FIXED, ONLINE (within-solve feedback).
All sources are GENERATED planted SAT; verify each native SAT witness. Future
outcomes are never read by decision policies. An observed BCP proxy reward
is NOT a causal estimate of remaining search time or SAT distance.
"""
from __future__ import annotations
import argparse
import collections
import hashlib
import json
import math
import pathlib
import random
import statistics
import subprocess
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import drnas_x42_1000 as G
import drnas_x43_two_cycle as X
import drnas_x44_ood as M

N_SHARDS=12
CAP=3.0
SEED_NAMESPACE="x45-prospective-1200-branch-feedback-20261113-v1"
ROOT=pathlib.Path("x45_generated")
BUILD={
    "CORE": ("build/drnas-x41", "core", "X41_STATS "),
    "ADAPTIVE": ("build/drnas-x3", "x3", "X3_STATS "),
    "SHAM": ("build/drnas-x45", "x45_sham", "X45_STATS "),
    "FIXED": ("build/drnas-x45", "x45_fixed", "X45_STATS "),
    "ONLINE": ("build/drnas-x45", "x45_online", "X45_STATS "),
}
GROUPS={
    "eval_known": ["planted_uniform", "planted_local40"],
    "eval_ood": ["novel_hub16", "novel_widthmix", "novel_xor_duplicate"],
}


def emit(tag, obj):
    print(tag+" "+json.dumps(obj,sort_keys=True,separators=(",", ":")),flush=True)


def sources():
    M.SEED_NAMESPACE=SEED_NAMESPACE
    result, manifest, sha=M.frozen_sources(ROOT)
    if len(result)!=1200 or len({r["sha256"] for r in result})!=1200:
        raise RuntimeError("Frozen source count or uniqueness invalid")
    return result,manifest,sha


def freeze(args):
    rows,data,sha=sources()
    # Prove that this experiment re-seeded every X4.4 generator family.
    M.SEED_NAMESPACE="x44-independent-family-prospective-20261113-v1"
    previous,_,previous_sha=M.frozen_sources(ROOT/"x44_previous_reference")
    newset={r["sha256"] for r in rows}
    if any(r["sha256"] in newset for r in previous):
        raise RuntimeError("Reused SHA from X4.4 experiment")
    output=pathlib.Path(args.freeze_dir)
    output.mkdir(parents=True,exist_ok=True)
    (output/"manifest.json").write_text(data)
    (output/"manifest_sha.txt").write_text(sha+"\n")
    emit("X45_FROZEN",{"sources":len(rows),"sha":sha,
        "distinct_from_x44":True,"previous_manifest_sha":previous_sha,
        "cap_s":CAP,"arms":list(BUILD),
        "by_family":dict(collections.Counter(r["family"] for r in rows))})


def one(src,key):
    binary,mode,prefix=BUILD[key]
    path=pathlib.Path(src["path"])
    if hashlib.sha256(path.read_bytes()).hexdigest()!=src["sha256"]:
        raise RuntimeError("Original SHA unexpectedly changed")
    cmd=[binary,str(path),"--mode",mode,"--time",str(CAP),"--stats"]
    started=time.perf_counter()
    try:
        p=subprocess.run(cmd,capture_output=True,text=True,timeout=CAP+1.5)
    except subprocess.TimeoutExpired:
        p=None
    elapsed=time.perf_counter()-started
    status="UNKNOWN"
    if p and p.returncode not in (0,10,20):
        raise RuntimeError(f"{key} native error: {src['formula_id']} {p.returncode} {p.stderr[-700:]}")
    if p and p.returncode==20:
        raise RuntimeError(f"UNSAT contradicts planted SAT: {src['formula_id']} {key}")
    if p and p.returncode==10:
        if not G.verify_sat(path,p.stdout,src["nvars"]):
            raise RuntimeError(f"SAT witness invalid: {src['formula_id']} {key}")
        if elapsed<=CAP:
            status="SAT_VERIFIED"
    stats={}
    if p:
        for line in p.stderr.splitlines():
            if line.startswith(prefix):
                stats=json.loads(line[len(prefix):])
    if p and not stats:
        raise RuntimeError(f"No expected native stats: {src['formula_id']} {key}")
    return {
        "status":status, "e2e_s":round(elapsed,6),
        "PAR2_s":round(elapsed if status=="SAT_VERIFIED" else 2*CAP,6),
        "decisions":stats.get("decisions"),"conflicts":stats.get("conflicts"),
        "probe_rounds":stats.get("x45_probe_rounds",0),
        "counterfactuals":stats.get("x45_counterfactuals",0),
        "interventions":stats.get("x45_interventions",0),
        "feedback":stats.get("x45_feedback",0),
        "updates":stats.get("x45_online_updates",0),
        "probe_seconds":stats.get("probe_seconds",0.0),
        "gain_weight_final":stats.get("x45_final_gain_weight"),
        "unit_weight_final":stats.get("x45_final_unit_weight"),
    }


def shard(args):
    if args.shard not in range(N_SHARDS):
        raise ValueError("Invalid shard")
    for binary,_,_ in BUILD.values():
        if not pathlib.Path(binary).is_file():
            raise RuntimeError(f"Missing native binary {binary}")
    src,data,sha=sources()
    freeze=pathlib.Path(args.freeze_dir)
    if hashlib.sha256((freeze/"manifest.json").read_bytes()).hexdigest()!=sha:
        raise RuntimeError("Frozen source SHA mismatch")
    if (freeze/"manifest_sha.txt").read_text().strip()!=sha:
        raise RuntimeError("Frozen manifest checksum mismatch")
    assigned=[s for s in src if s["global_id"] % N_SHARDS==args.shard]
    if len(assigned)!=100:
        raise RuntimeError("Unexpected shard size")
    stage=pathlib.Path(f"x45_stage/shard_{args.shard}")
    stage.mkdir(parents=True,exist_ok=True)
    counts=collections.Counter()
    with (stage/"trials.jsonl").open("w") as f:
        for i,s in enumerate(assigned,1):
            names=list(BUILD)
            rot=s["global_id"]%len(names)
            names=names[rot:]+names[:rot]
            out={}
            for key in names:
                out[key]=one(s,key)
            item={
                "global_id":s["global_id"],"sha256":s["sha256"],
                "family":s["family"],"split":s["split"],
                "arms":out,
            }
            f.write(json.dumps(item,sort_keys=True,separators=(",", ":"))+"\n")
            f.flush()
            counts["done"]+=1
            for key,r in out.items():
                counts[key+"_solved"]+=r["status"]=="SAT_VERIFIED"
                counts[key+"_PAR2_s"]+=r["PAR2_s"]
                counts[key+"_E2E_s"]+=r["e2e_s"]
            if i%25==0:
                emit("X45_PROGRESS",{"shard":args.shard,"total":len(assigned),**counts})
    report={"shard":args.shard,"sources":len(assigned),"manifest_sha256":sha,
            "counts":dict(counts),"cap_s":CAP}
    (stage/"report.json").write_text(json.dumps(report,indent=2)+"\n")
    emit("X45_SHARD_FINAL",report)


def exact_binomial_test(wins,losses):
    discordant=wins+losses
    if discordant==0:
        return 1.0
    k=min(wins,losses)
    # Exact two-sided binomial McNemar test, stable for n<=1200.
    prob=sum(math.comb(discordant,i) for i in range(k+1))/2**discordant
    return min(1.0,2.0*prob)


def bootstrap_difference(a,b,replications=1500):
    """Paired bootstrap, (arm a PAR2 minus arm b PAR2), lower is better."""
    if len(a)!=len(b) or not a:
        raise ValueError("Unpaired or empty samples")
    diffs=[x-y for x,y in zip(a,b)]
    rng=random.Random(4511+len(a))
    sampled=[]
    n=len(diffs)
    for _ in range(replications):
        sampled.append(sum(diffs[rng.randrange(n)] for _ in range(n)))
    sampled.sort()
    return {
        "observed_sum_s":round(sum(diffs),5),
        "bootstrap95_sum_s":[round(sampled[int(.025*replications)],5),
                            round(sampled[int(.975*replications)],5)]
    }


def summarize(rows):
    out={"sources":len(rows)}
    for key in BUILD:
        rec=[r["arms"][key] for r in rows]
        out[key]={
            "SAT_verified":sum(x["status"]=="SAT_VERIFIED" for x in rec),
            "UNKNOWN":sum(x["status"]!="SAT_VERIFIED" for x in rec),
            "PAR2_s":round(sum(x["PAR2_s"] for x in rec),5),
            "total_E2E_s":round(sum(x["e2e_s"] for x in rec),5),
            "decisions":sum(x["decisions"] or 0 for x in rec),
            "conflicts":sum(x["conflicts"] or 0 for x in rec),
            "probe_rounds":sum(x["probe_rounds"] for x in rec),
            "counterfactuals":sum(x["counterfactuals"] for x in rec),
            "interventions":sum(x["interventions"] for x in rec),
            "online_updates":sum(x["updates"] for x in rec),
            "probe_seconds":round(sum(x["probe_seconds"] for x in rec),6),
        }
    for challenger,baseline in (("FIXED","SHAM"),("ONLINE","FIXED"),
                                ("ONLINE","SHAM"),("ONLINE","ADAPTIVE"),
                                ("ONLINE","CORE")):
        better=worse=tied=0
        sat_wins=sat_losses=0
        for r in rows:
            a=r["arms"][challenger]
            b=r["arms"][baseline]
            if a["PAR2_s"] < b["PAR2_s"]-.002:
                better+=1
            elif a["PAR2_s"]>b["PAR2_s"]+.002:
                worse+=1
            else:
                tied+=1
            sat_wins+=a["status"]=="SAT_VERIFIED" and b["status"]!="SAT_VERIFIED"
            sat_losses+=a["status"]!="SAT_VERIFIED" and b["status"]=="SAT_VERIFIED"
        out[challenger+"_vs_"+baseline]={
            "faster_pairs":better,"slower_pairs":worse,"ties":tied,
            "SAT_only_challenger":sat_wins,"SAT_only_baseline":sat_losses,
            "mcnemar_p_two_sided":round(exact_binomial_test(sat_wins,sat_losses),6),
            "paired_PAR2_delta":bootstrap_difference(
                [r["arms"][challenger]["PAR2_s"] for r in rows],
                [r["arms"][baseline]["PAR2_s"] for r in rows]),
        }
    return out


def finish(args):
    freeze=pathlib.Path(args.freeze_dir)
    original=json.loads((freeze/"manifest.json").read_text())
    sha=hashlib.sha256((freeze/"manifest.json").read_bytes()).hexdigest()
    if sha!=(freeze/"manifest_sha.txt").read_text().strip():
        raise RuntimeError("Frozen manifest hash invalid")
    allrows=[]
    for i in range(N_SHARDS):
        folder=pathlib.Path(args.shards_dir)/f"x45-eval-{i}"
        report=json.loads((folder/"report.json").read_text())
        rows=[json.loads(line) for line in (folder/"trials.jsonl").read_text().splitlines()]
        if report["manifest_sha256"]!=sha or len(rows)!=100:
            raise RuntimeError("Missing or incompatible shard")
        allrows.extend(rows)
    if len(allrows)!=1200 or len({r["sha256"] for r in allrows})!=1200:
        raise RuntimeError("Duplicated or missing cases in trials")
    original_by_sha={s["sha256"]:s for s in original}
    if {r["sha256"] for r in allrows}!=set(original_by_sha):
        raise RuntimeError("Frozen source set differs from results")
    for r in allrows:
        orig=original_by_sha[r["sha256"]]
        if orig["family"]!=r["family"] or orig["split"]!=r["split"] or orig["global_id"]!=r["global_id"]:
            raise RuntimeError("Metadata changed after freeze")
        if set(r["arms"])!=set(BUILD):
            raise RuntimeError("Missing paired arm")
    allrows.sort(key=lambda r:r["global_id"])
    report={
        "status":"COMPLETE", "benchmark":"DRNAS_X45",
        "generated_planted_SAT_only":True, "sources":len(allrows),
        "manifest_sha256":sha,"cap_s":CAP,
        "policy":("SHAM=identical speculative budget no changed decision; "
                 "FIXED=static bounded-BCP proxy; ONLINE=within-formula updates "
                 "from immediate REAL branch feedback; all three share same probe code"),
        "overall":summarize(allrows),
        "splits":{k:summarize([r for r in allrows if r["split"]==k])
                  for k in GROUPS},
        "families":{family:summarize([r for r in allrows
                                    if r["family"]=="GENERATED:"+family])
                    for fs in GROUPS.values() for family in fs},
        "limits":("Generated SAT only; within-CNF online feedback is not transfer learning; "
                  "counterfactual temporary BCP is local to equal-prefix propagation, NOT "
                  "the causal effect on eventual SAT runtime. No UNSAT proof certification "
                  "or original competition CNF tested. Prospective SHA and arms frozen "
                  "before solving. PAR2 includes native overhead and UNKNOWN=6s."),
    }
    dest=pathlib.Path(args.out_dir)
    dest.mkdir(parents=True,exist_ok=True)
    (dest/"report.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    with (dest/"paired_trials.jsonl").open("w") as f:
        for r in allrows:
            f.write(json.dumps(r,sort_keys=True,separators=(",", ":"))+"\n")
    emit("X45_FINAL",report)


def main():
    p=argparse.ArgumentParser()
    p.add_argument("command",choices=("freeze","shard","finish"))
    p.add_argument("--shard",type=int,default=0)
    p.add_argument("--freeze-dir",default="x45_frozen")
    p.add_argument("--shards-dir",default="x45_eval_downloads")
    p.add_argument("--out-dir",default="x45_final")
    args=p.parse_args()
    if args.command=="freeze":
        freeze(args)
    elif args.command=="shard":
        shard(args)
    else:
        finish(args)


if __name__=="__main__":
    main()
