#!/usr/bin/env python3
"""DRNAS REAL-SPEED v1: auditable recurring *development* benchmark.

Blind/holdout CNFs are never copied into executable inputs, never evaluated
in the recurring workflow, and never used to fit or select a policy.
No promotion or solver changes are possible from this script.
"""
import argparse
import collections
import gzip
import hashlib
import json
import math
import os
import random
import resource
import shutil
import signal
import statistics
import subprocess
import tempfile
import time
from pathlib import Path

import drnas_x47_long_bench as witness

PROTOCOL = "DRNAS-REAL-SPEED-v1"
ARMS = ("CORE", "X5_NO_MIN", "X5", "X52_LBD", "Kissat", "CaDiCaL", "CMS")
NATIVE_BASELINES = ("CORE", "X5_NO_MIN", "X5")
EXPECTED_SHARDS = 8
DEFAULT_CAP = 5.0
DEFAULT_CHECK_CAP = 30.0
MAX_PROOF = 512 * 1024 * 1024

def digest(raw):
    return hashlib.sha256(raw).hexdigest()

def load(path):
    return json.loads(Path(path).read_text())

def save(path, obj):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=2, sort_keys=True)+"\n")

def emit(event, **values):
    print(event+" "+json.dumps(values, sort_keys=True, separators=(",", ":")), flush=True)

def merge_state(args):
    rows = {}
    role_by_family = {}
    for path in (args.real2_state, args.speed_state):
        if not path or not path.is_file():
            continue
        state = load(path)
        for item in state.get("sources", []):
            fam, role = item["family"], item["split"]
            if fam in role_by_family and role_by_family[fam] != role:
                raise RuntimeError("cross-catalog family/split collision: "+fam)
            role_by_family[fam] = role
            sha = item["sha256"]
            if sha in rows and rows[sha]["split"] != role:
                raise RuntimeError("cross-catalog SHA/split collision")
            rows[sha] = item
    save(args.out, {"protocol":"DRNAS-REAL-LEARN2-v1", "sources":list(rows.values())})
    emit("SPEED_MERGE_STATE", prior_unique_sources=len(rows), prior_families=len(role_by_family))

def stage(args):
    source_root = args.prepared/"real2_source"
    split_path = args.prepared/"real2_splits.json"
    full = load(split_path)
    entries = full["sources"]
    if len({r["sha256"] for r in entries}) != len(entries):
        raise RuntimeError("duplicate selected CNF")
    if set(r["split"] for r in entries) != {"train","validation","holdout"}:
        raise RuntimeError("split coverage incomplete")
    family_role = {}
    for r in entries:
        fam = r["family"]
        if fam in family_role and family_role[fam] != r["split"]:
            raise RuntimeError("cross-split family leak")
        family_role[fam] = r["split"]
    dev = [r for r in entries if r["split"] in ("train","validation")]
    blind = [r for r in entries if r["split"] == "holdout"]
    if len(dev) < 90 or len({r["family"] for r in dev}) < 20 or len(blind) < 10:
        raise RuntimeError("insufficient development or sealed-holdout material")
    out = args.out
    out.mkdir(parents=True, exist_ok=False)
    dest = out/"cnf"
    dest.mkdir()
    for s in dev:
        raw = (source_root/s["file"]).read_bytes()
        if digest(raw) != s["sha256"]:
            raise RuntimeError("source SHA mismatch")
        (dest/(s["sha256"]+".cnf")).write_bytes(raw)
    manifest = {
        "protocol": PROTOCOL, "stage":"development_only",
        "source_count":len(dev), "family_count":len({r["family"] for r in dev}),
        "train_count":sum(r["split"] == "train" for r in dev),
        "validation_count":sum(r["split"] == "validation" for r in dev),
        "sealed_holdout_count":len(blind),
        "sealed_holdout_families":len({r["family"] for r in blind}),
        "sources":sorted(dev,key=lambda s:s["sha256"]),
        "sealed_holdout_sha256":sorted(r["sha256"] for r in blind),
        "selection_hash":digest(split_path.read_bytes()),
        "holdout_never_benchmarked":True
    }
    save(out/"manifest.json", manifest)
    emit("SPEED_MATERIAL_LOCKED", dev_sources=len(dev),
         dev_families=manifest["family_count"], blind_reserved=len(blind),
         blind_families=manifest["sealed_holdout_families"],
         archive_count=full["source_count"])

def binary_map():
    return {
        "CORE": Path("build/frozen-proof"),
        "X5_NO_MIN": Path("build/drnas-x5"),
        "X5": Path("build/drnas-x5"),
        "X52_LBD": Path("build/drnas-x52"),
        "Kissat": Path("build/kissat"),
        "CaDiCaL": Path("build/cadical"),
        "CMS": Path("build/cms"),
        "drat-trim":Path("build/drat-trim"),
        "frat-rs":Path("build/frat-rs"),
    }

def freeze(args):
    files = {name: digest(path.read_bytes()) for name,path in binary_map().items()}
    files["src/drnas_x52.cpp"] = digest(Path("src/drnas_x52.cpp").read_bytes())
    files["src/drnas_x5.cpp"] = digest(Path("src/drnas_x5.cpp").read_bytes())
    save(args.out, {"protocol":PROTOCOL, "binary_sha256":files,
        "cap_s":args.cap,"verify_cap_s":args.verify_cap,
        "repeats":args.repeats,"shards":EXPECTED_SHARDS,
        "arms":list(ARMS), "verified_solver_PAR2":True,
        "experimental_only":True, "promoted":False})
    emit("SPEED_FROZEN", binaries=len(files), cap_s=args.cap,
         verify_cap_s=args.verify_cap, repeats=args.repeats)

def check_freeze(frozen, cap, verify_cap, repeats):
    if (frozen["protocol"] != PROTOCOL or frozen["cap_s"] != cap or
        frozen["verify_cap_s"] != verify_cap or frozen["repeats"] != repeats or
        tuple(frozen["arms"]) != ARMS or frozen["shards"] != EXPECTED_SHARDS):
        raise RuntimeError("freeze/protocol mismatch")
    for name, sha in frozen["binary_sha256"].items():
        path = binary_map().get(name, Path(name))
        if digest(path.read_bytes()) != sha:
            raise RuntimeError("binary/source drift: "+name)

def run_one(arm, cnf, source, cap, verify_cap, tmp):
    bins = binary_map()
    solver = bins[arm].resolve()
    proof = tmp/("proof_"+arm+".out")
    proof.unlink(missing_ok=True)
    rss = tmp/("rss_"+arm+".txt")
    rss.unlink(missing_ok=True)
    if arm in ("Kissat","CaDiCaL"):
        cmd = [str(solver),str(cnf),str(proof)]
    elif arm == "CMS":
        cmd = [str(solver),"--threads=1","--verb=0","--frat="+str(proof),str(cnf)]
    else:
        cmd = [str(solver),str(cnf),"--mode","core","--stats","--time",
               str(cap),"--proof",str(proof)]
        if arm == "X5_NO_MIN":
            cmd.append("--x5-no-minimize")
        if arm == "X52_LBD":
            cmd += ["--x52-policy","lbd"]
    timed = Path("build/timed").resolve()
    wrapped = [str(timed),str(rss),*cmd] if timed.exists() else cmd
    cpu0 = resource.getrusage(resource.RUSAGE_CHILDREN)
    t0 = time.monotonic()
    status, ret, sout, serr = "TIMEOUT", None, "", ""
    try:
        p = subprocess.Popen(wrapped,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                             text=True,start_new_session=True)
        try:
            sout,serr = p.communicate(timeout=cap)
            ret = p.returncode
            status = {0:"UNKNOWN",10:"SAT",20:"UNSAT"}.get(ret,"CRASH")
        except subprocess.TimeoutExpired:
            os.killpg(p.pid,signal.SIGKILL)
            sout,serr = p.communicate()
            status = "TIMEOUT"
    except OSError as exc:
        status = "CRASH"
        serr = str(exc)
    solve_s = time.monotonic()-t0
    cpu1 = resource.getrusage(resource.RUSAGE_CHILDREN)
    cpu_s = (cpu1.ru_utime+cpu1.ru_stime)-(cpu0.ru_utime+cpu0.ru_stime)
    checked = False
    check_s = 0.0
    reason = ""
    if status == "SAT":
        c0 = time.monotonic()
        checked = bool(witness.verify_model_on_original_text(source,sout))
        check_s = time.monotonic()-c0
        if not checked:
            raise RuntimeError("WRONG_SAT_WITNESS "+source["sha256"]+" "+arm)
    elif status == "UNSAT":
        c0 = time.monotonic()
        if not proof.exists() or proof.stat().st_size>MAX_PROOF:
            reason="missing_or_oversize_proof"
        else:
            if arm == "CMS":
                command=[str(bins["frat-rs"].resolve()),"elab",str(proof),str(cnf),"-v"]
            else:
                command=[str(bins["drat-trim"].resolve()),str(cnf),str(proof)]
            try:
                q=subprocess.run(command,capture_output=True,text=True,timeout=verify_cap)
                if arm == "CMS":
                    checked=q.returncode==0 and "VERIFIED" in q.stdout.splitlines()
                else:
                    checked=("s VERIFIED" in q.stdout and
                             (q.returncode==0 or "c trivial UNSAT" in q.stdout))
                if not checked: reason="UNSAT_proof_not_verified"
            except subprocess.TimeoutExpired:
                reason="UNSAT_verification_timeout"
        check_s = time.monotonic()-c0
    accepted = bool(checked and solve_s<=cap and status in ("SAT","UNSAT"))
    if not accepted and not reason:
        reason = status.lower() if status not in ("SAT","UNSAT") else "not_verified"
    rss_kib = None
    if rss.is_file():
        try:
            rss_kib=int(rss.read_text().splitlines()[-1])
        except (ValueError, IndexError):
            pass
    return {
        "arm":arm,"status":status, "returncode":ret,"verified":checked,
        "accepted":accepted,"reason":reason,"solve_s":solve_s,"check_s":check_s,
        "verified_e2e_s":solve_s+check_s if checked else None,
        "PAR2_s":solve_s if accepted else 2*cap,
        "cap_s":cap,"verify_cap_s":verify_cap,"cpu_s":max(0.,cpu_s),
        "maxrss_kib":rss_kib,
        "proof_bytes":proof.stat().st_size if proof.is_file() else 0,
        "stderr_tail":serr[-600:] if status=="CRASH" else ""
    }

def bench(args):
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    frozen = load(args.freeze)
    check_freeze(frozen,args.cap,args.verify_cap,args.repeats)
    manifest = load(args.input/"manifest.json")
    if manifest["protocol"] != PROTOCOL or manifest["stage"] != "development_only":
        raise RuntimeError("refuse non-development material")
    if manifest["holdout_never_benchmarked"] is not True:
        raise RuntimeError("holdout not sealed")
    sources = sorted(manifest["sources"],key=lambda x:x["sha256"])
    chosen = [r for i,r in enumerate(sources) if i%args.shards==args.shard]
    args.out.mkdir(parents=True,exist_ok=False)
    freeze_hash = digest(args.freeze.read_bytes())
    metadata = {
        "protocol":PROTOCOL,"shard":args.shard,"shards":args.shards,
        "stage":"development_only","source_sha256":[r["sha256"] for r in chosen],
        "source_split":{r["sha256"]:r["split"] for r in chosen},
        "repeats":args.repeats,"arms":list(ARMS),"cap_s":args.cap,
        "freeze_sha256":freeze_hash,"material_sha256":digest((args.input/"manifest.json").read_bytes()),
        "logical_cpu_count":len(os.sched_getaffinity(0))}
    if metadata["logical_cpu_count"] != 1:
        raise RuntimeError("not pinned to one logical CPU")
    save(args.out/"manifest.json",metadata)
    with tempfile.TemporaryDirectory() as d,(args.out/"trials.jsonl").open("w") as log:
        tmp=Path(d)
        for index,item in enumerate(chosen):
            path=args.input/"cnf"/(item["sha256"]+".cnf")
            raw=path.read_bytes()
            if digest(raw) != item["sha256"]:
                raise RuntimeError("material identity drift")
            source={"sha256":item["sha256"],"nvars":item["nvars"],
                    "nclauses":item["nclauses"],"content":raw.decode("ascii")}
            for rep in range(args.repeats):
                order=list(ARMS)
                random.Random(5412026 ^ int(item["sha256"][:12],16) ^ rep).shuffle(order)
                for arm in order:
                    row=run_one(arm,path,source,args.cap,args.verify_cap,tmp)
                    row.update({"sha256":item["sha256"],"family":item["family"],
                                "source_split":item["split"],"rep":rep,"shard":args.shard})
                    log.write(json.dumps(row,sort_keys=True)+"\n")
                    log.flush()
            if (index+1)%5 == 0 or index+1==len(chosen):
                emit("SPEED_SHARD_PROGRESS", shard=args.shard, completed=index+1,
                     total=len(chosen), cap_s=args.cap)
    emit("SPEED_SHARD_DONE",shard=args.shard, sources=len(chosen),
         trials=len(chosen)*len(ARMS)*args.repeats)

def bootstrap_family(rows,candidate,reference,draws=5000):
    grouped=collections.defaultdict(lambda:collections.defaultdict(float))
    for r in rows:
        grouped[r["family"]][r["arm"]]+=r["PAR2_s"]
    families=sorted(grouped)
    if len(families)<20:
        raise RuntimeError("too few independent family units")
    rng=random.Random(130047)
    def reduction(sample):
        base=sum(grouped[f][reference] for f in sample)
        other=sum(grouped[f][candidate] for f in sample)
        return (base-other)/base if base else 0.0
    values=sorted(reduction([rng.choice(families) for _ in families]) for _ in range(draws))
    return {"reduction":reduction(families), "lower95":values[int(.025*(draws-1))],
            "upper95":values[int(.975*(draws-1))], "family_units":len(families)}

def report(args):
    inp=load(args.input/"manifest.json")
    if inp["protocol"] != PROTOCOL or inp["stage"] != "development_only":
        raise RuntimeError("report is not on development")
    rows,metas=[],[]
    for p in sorted(args.results.rglob("manifest.json")):
        m=load(p)
        metas.append(m)
        for line in (p.parent/"trials.jsonl").read_text().splitlines():
            if line.strip(): rows.append(json.loads(line))
    if len(metas)!=EXPECTED_SHARDS or {m["shard"] for m in metas}!=set(range(EXPECTED_SHARDS)):
        raise RuntimeError("missing benchmark shard")
    for field in ("cap_s","freeze_sha256","material_sha256","repeats","arms","logical_cpu_count"):
        if len({json.dumps(m[field],sort_keys=True) for m in metas})!=1:
            raise RuntimeError("inconsistent shard "+field)
    if metas[0]["logical_cpu_count"] != 1 or tuple(metas[0]["arms"]) != ARMS:
        raise RuntimeError("wrong CPU/arms")
    if metas[0]["material_sha256"] != digest((args.input/"manifest.json").read_bytes()):
        raise RuntimeError("material SHA changed")
    expected={(s["sha256"],rep,arm) for s in inp["sources"]
              for rep in range(metas[0]["repeats"]) for arm in ARMS}
    got=[(r["sha256"],r["rep"],r["arm"]) for r in rows]
    if set(got)!=expected or len(got)!=len(expected):
        raise RuntimeError("missing, duplicated, or extra trials")
    mapping={s["sha256"]:s for s in inp["sources"]}
    for r in rows:
        if r["source_split"] not in ("train","validation") or r["family"]!=mapping[r["sha256"]]["family"]:
            raise RuntimeError("holdout leak or family mismatch")
        if r["accepted"] and not r["verified"]:
            raise RuntimeError("invalid solved credit")
        cost=r["solve_s"] if r["accepted"] else 2*r["cap_s"]
        if abs(r["PAR2_s"]-cost)>1e-6:
            raise RuntimeError("PAR2 mismatch")
    verdicts=collections.defaultdict(set)
    for r in rows:
        if r["verified"]:
            verdicts[r["sha256"]].add(r["status"])
    if any(len(v)>1 for v in verdicts.values()):
        raise RuntimeError("contradictory verified SAT/UNSAT answers")
    overall={}
    for arm in ARMS:
        trials=[r for r in rows if r["arm"]==arm]
        overall[arm]={
            "attempts":len(trials),"distinct_verified":len({r["sha256"] for r in trials if r["accepted"]}),
            "verified":sum(bool(r["accepted"]) for r in trials),
            "SAT":sum(r["accepted"] and r["status"]=="SAT" for r in trials),
            "UNSAT":sum(r["accepted"] and r["status"]=="UNSAT" for r in trials),
            "timeouts":sum(r["status"]=="TIMEOUT" for r in trials),
            "unverified":sum(not r["accepted"] and r["status"] in ("SAT","UNSAT") for r in trials),
            "crashes":sum(r["status"]=="CRASH" for r in trials),
            "PAR2_s":sum(r["PAR2_s"] for r in trials),
            "proof_check_s":sum(r["check_s"] for r in trials),
            "rss_missing":sum(r["maxrss_kib"] is None for r in trials)
        }
    best_native=min(NATIVE_BASELINES,key=lambda arm:(overall[arm]["PAR2_s"],arm))
    candidate="X52_LBD"
    comparisons={a:bootstrap_family(rows,candidate,a) for a in ARMS if a!=candidate}
    c=comparisons[best_native]
    no_loss=overall[candidate]["distinct_verified"]>=overall[best_native]["distinct_verified"]
    # A development screening flag, NEVER a blind gate or production promotion.
    screen=bool(c["reduction"]>=.05 and c["lower95"]>0 and no_loss and overall[candidate]["crashes"]==0)
    output={
        "protocol":PROTOCOL,"status":"COMPLETE","stage":"development_only",
        "candidate":candidate,"best_native_in_dev":best_native,
        "source_count":inp["source_count"],"family_count":inp["family_count"],
        "train_count":inp["train_count"],"validation_count":inp["validation_count"],
        "sealed_holdout_count":inp["sealed_holdout_count"],
        "sealed_holdout_never_executed":True,
        "cap_s":metas[0]["cap_s"],"repeats":metas[0]["repeats"],
        "freeze_sha256":metas[0]["freeze_sha256"],
        "totals":overall,"family_bootstrap95":comparisons,
        "development_screen_positive":screen,
        "blind_gate_passed":False, "promoted":False,
        "note":"Development data only. No unbiased holdout claim. Repeat runs do not create independent formulas."
    }
    save(args.out,output)
    emit("SPEED_REPORT_COMPLETE", best_native=best_native, candidate=candidate,
         candidate_PAR2=round(overall[candidate]["PAR2_s"],3),
         baseline_PAR2=round(overall[best_native]["PAR2_s"],3),
         gain=round(c["reduction"],5), lower95=round(c["lower95"],5),
         informative_sources=len(verdicts), screen_positive=screen,
         blind_executed=False)

def persist(args):
    dev=load(args.input/"manifest.json")
    report_data=load(args.report)
    material=load(args.catalog_delta)
    if (report_data["status"]!="COMPLETE" or report_data["stage"]!="development_only"
        or not report_data["sealed_holdout_never_executed"] or report_data["promoted"]):
        raise RuntimeError("refusing invalid research persistence")
    root=args.root
    base=root/"runs"/args.run_id
    if base.exists():
        raise RuntimeError("run already persisted: "+args.run_id)
    base.mkdir(parents=True,exist_ok=False)
    save(base/"report.json",report_data)
    save(base/"dev_manifest.json",dev)
    save(base/"catalog_delta.json",material)
    save(base/"material.json",load(args.material))
    save(base/"splits.json",load(args.splits))
    for p in sorted(args.results.rglob("trials.jsonl")):
        idx=p.parent.name
        (base/(idx+".jsonl.gz")).write_bytes(
            gzip.compress(p.read_bytes(), compresslevel=9,mtime=0))
    catalog_path=root/"catalog.json"
    catalog=load(catalog_path) if catalog_path.exists() else {"protocol":PROTOCOL,"sources":[]}
    if catalog.get("protocol")!=PROTOCOL:
        raise RuntimeError("wrong catalog protocol")
    old={s["sha256"] for s in catalog["sources"]}
    new=material["sources"]
    if len({s["sha256"] for s in new})!=len(new) or any(s["sha256"] in old for s in new):
        raise RuntimeError("new-source duplicate in persistent catalog")
    catalog["sources"] += new
    save(catalog_path,catalog)
    save(root/"latest.json",{
        "protocol":PROTOCOL,"last_run":args.run_id,
        "cumulative_unique_formulas":len(catalog["sources"]),
        "candidate":report_data["candidate"],
        "screen_positive":report_data["development_screen_positive"],
        "holdout_never_reused":True,"promoted":False
    })
    emit("SPEED_DURABLE_STORED",run_id=args.run_id,
         total_catalog=len(catalog["sources"]),
         development=dev["source_count"],blind_reserved=dev["sealed_holdout_count"])

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("command",choices=("merge-state","stage","freeze","bench","report","persist"))
    ap.add_argument("--real2-state",type=Path)
    ap.add_argument("--speed-state",type=Path)
    ap.add_argument("--prepared",type=Path)
    ap.add_argument("--input",type=Path)
    ap.add_argument("--results",type=Path)
    ap.add_argument("--freeze",type=Path)
    ap.add_argument("--out",type=Path)
    ap.add_argument("--cap",type=float,default=DEFAULT_CAP)
    ap.add_argument("--verify-cap",type=float,default=DEFAULT_CHECK_CAP)
    ap.add_argument("--repeats",type=int,default=2)
    ap.add_argument("--shard",type=int,default=0)
    ap.add_argument("--shards",type=int,default=EXPECTED_SHARDS)
    ap.add_argument("--root",type=Path)
    ap.add_argument("--catalog-delta",type=Path)
    ap.add_argument("--report",type=Path)
    ap.add_argument("--material",type=Path)
    ap.add_argument("--splits",type=Path)
    ap.add_argument("--run-id")
    a=ap.parse_args()
    if a.command=="merge-state":merge_state(a)
    elif a.command=="stage":stage(a)
    elif a.command=="freeze":freeze(a)
    elif a.command=="bench":
        if a.shards != EXPECTED_SHARDS or not 0<=a.shard<a.shards:
            ap.error("require exactly eight shards")
        bench(a)
    elif a.command=="report":report(a)
    else:persist(a)

if __name__=="__main__":main()
