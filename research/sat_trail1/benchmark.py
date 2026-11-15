#!/usr/bin/env python3
"""Source-pinned TRAIL-RECONSTRUCT1 original CNF ablation, no retrospective cherry-pick.
600 SATLIB standard originals + 24 historical SAT2024 originals (SHA-disjoint).
OFF / SHADOW / ACTIVE on identical native X59; pinned Kissat/CaDiCaL/CMS.
One logical CPU per process, independent SAT model and DRAT/FRAT checkers.
"""
import argparse
import collections
import hashlib
import json
import os
import platform
import random
import resource
import signal
import statistics
import subprocess
import tempfile
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
INPUT=ROOT/"sat_trail1_inputs"
OUT=ROOT/"sat_trail1_results"
ARMS=("OFF","TRAIL_SHADOW","TRAIL_ON","Kissat","CaDiCaL","CMS")
SHARDS=4
BINS={
    "OFF":"build/drnas-sat-trail-x59","TRAIL_SHADOW":"build/drnas-sat-trail-x59",
    "TRAIL_ON":"build/drnas-sat-trail-x59","Kissat":"build/kissat",
    "CaDiCaL":"build/cadical","CMS":"build/cms"
}
SOURCE600_SHA="69ecc2d2ac38157ca0175893dd164a659b0c042a5e6fc630f7af0260f85054a8"

def sha(data):
    return hashlib.sha256(data).hexdigest()
def file_sha(p):
    h=hashlib.sha256()
    with open(p,"rb") as f:
        for chunk in iter(lambda:f.read(1<<20),b""):
            h.update(chunk)
    return h.hexdigest()
def save(p,d):
    p=Path(p)
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(d,indent=2,sort_keys=True)+"\n")
def emit(k,v):
    print(k+" "+json.dumps(v,sort_keys=True),flush=True)

def read_cnf(path):
    """Read strict or SATLIB legacy %, preserving exact logical clauses."""
    n=m=None;out=[];current=[]
    with open(path,encoding="ascii") as f:
        for line in f:
            a=line.split()
            if not a:continue
            if a[0]=="%":break
            if a[0]=="c":continue
            if a[0]=="p":
                if n is not None or len(a)!=4 or a[1]!="cnf":
                    raise RuntimeError("bad DIMACS header")
                n,m=map(int,a[2:])
                continue
            if n is None:raise RuntimeError("missing DIMACS header")
            for tok in a:
                lit=int(tok)
                if abs(lit)>n:raise RuntimeError("bad literal")
                if not lit:
                    out.append(current)
                    current=[]
                else:current.append(lit)
    if n is None or current or len(out)!=m:
        raise RuntimeError("incomplete DIMACS")
    return n,out

def model_ok(path,log):
    values={}
    try:
        for row in log.splitlines():
            if not row.startswith("v "):continue
            for t in row[2:].split():
                lit=int(t)
                if not lit:continue
                v=abs(lit)
                if v in values and values[v]!=(lit>0):return False
                values[v]=lit>0
        n,clauses=read_cnf(path)
        return (len(values)==n and all(1<=v<=n for v in values)
            and all(any(values[abs(l)]==(l>0) for l in c) for c in clauses))
    except (ValueError,KeyError,RuntimeError,UnicodeError):
        return False

def freeze():
    if INPUT.exists():raise RuntimeError("freeze directory exists")
    mpath=ROOT/"sat_construct_600_inputs/manifest.json"
    if file_sha(mpath)!=SOURCE600_SHA:
        raise RuntimeError("SATLIB REAL600 manifest does not match pinned source")
    satlib=json.loads(mpath.read_text())
    if len(satlib["sources"])!=600:raise RuntimeError("SATLIB count drift")
    realpath=ROOT/"cf7/manifest.json"
    real=json.loads(realpath.read_text())
    assert real["count"]==100 and len(real["sources"])==100
    sources=[]
    for x in satlib["sources"]:
        orig=ROOT/"sat_construct_600_inputs"/x["original_path"]
        canonical=ROOT/"sat_construct_600_inputs"/x["path"]
        if file_sha(orig)!=x["original_sha256"] or file_sha(canonical)!=x["sha256"]:
            raise RuntimeError("SATLIB hash drift")
        if read_cnf(orig)!=read_cnf(canonical):
            raise RuntimeError("SATLIB canonical clauses changed")
        sources.append(dict(id=len(sources),dataset="SATLIB600",family=x["family"],
           path=str(canonical.relative_to(ROOT)), original_path=str(orig.relative_to(ROOT)),
           sha256=x["sha256"],source_sha256=x["original_sha256"],
           catalog_label=x["catalog_label"],cap_s=2.0,repetitions=1))
    # 24 deterministic official SAT2024 originals, IDs chosen before any
    # TRAIL1 outcome: every fourth ID 0..92, never selected by solver results.
    chosen=[s for s in real["sources"] if s["id"] in set(range(0,96,4))]
    assert len(chosen)==24 and len({s["sha256"] for s in chosen})==24
    for s in sorted(chosen,key=lambda q:q["id"]):
        path=ROOT/s["path"]
        if file_sha(path)!=s["sha256"]:raise RuntimeError("REAL24 source drift")
        sources.append(dict(id=len(sources),dataset="REAL24",
             source_id=s["id"],family=s["normalized_name_family"],
             path=s["path"],original_path=s["path"],
             sha256=s["sha256"],source_sha256=s["sha256"],
             catalog_label="UNKNOWN",cap_s=3.0,repetitions=2))
    if len({s["source_sha256"] for s in sources})!=len(sources):
        raise RuntimeError("across-source-set overlap: abort")
    INPUT.mkdir()
    prespec=dict(protocol="drnas-trail-reconstruct1-v1",sources=sources,
                 source600_manifest_sha=SOURCE600_SHA,
                 real100_manifest_sha=file_sha(realpath),
                 real_source_ids=list(range(0,96,4)),
                 source_provenance="previously exposed SATLIB and SAT2024, not blind",
                 arms=list(ARMS),shards=SHARDS,
                 expected_trials=sum(s["repetitions"] for s in sources)*len(ARMS),
                 one_logical_cpu_per_solver=True,
                 primary="verified E2E PAR2",no_automatic_promotion=True)
    save(INPUT/"manifest.json",prespec)
    emit("TRAIL1_FROZEN",dict(sources=len(sources),satlib=600,real=24,
         trials=prespec["expected_trials"],manifest_sha256=file_sha(INPUT/"manifest.json")))

def validate():
    m=json.loads((INPUT/"manifest.json").read_text())
    assert len(m["sources"])==624 and m["expected_trials"]==3888
    for s in m["sources"]:
        if file_sha(ROOT/s["path"])!=s["sha256"] or file_sha(ROOT/s["original_path"])!=s["source_sha256"]:
            raise RuntimeError("CNF SHA changed")
        if s["dataset"]=="SATLIB600" and read_cnf(ROOT/s["path"])!=read_cnf(ROOT/s["original_path"]):
            raise RuntimeError("original and canonical logical clauses differ")
    return m

def pin():
    cpu=min(os.sched_getaffinity(0))
    os.sched_setaffinity(0,{cpu})
    assert len(os.sched_getaffinity(0))==1
    return cpu

def command(arm,cnf,proof,cap):
    if arm in ("OFF","TRAIL_SHADOW","TRAIL_ON"):
        cmd=[str(ROOT/BINS[arm]),str(cnf),"--mode","core",
             "--time",str(cap),"--stats","--proof",str(proof)]
        if arm in ("TRAIL_SHADOW","TRAIL_ON"):
            cmd+=["--sat-trail-ms","12"]
            if arm=="TRAIL_SHADOW":cmd+=["--sat-trail-shadow"]
        return cmd
    if arm=="Kissat":
        return [str(ROOT/BINS[arm]),str(cnf),str(proof)]
    if arm=="CaDiCaL":
        return [str(ROOT/BINS[arm]),"-q","--no-binary",str(cnf),str(proof)]
    if arm=="CMS":
        return [str(ROOT/BINS[arm]),"--threads=1","--verb=0",
                "--frat="+str(proof),str(cnf)]
    raise KeyError(arm)

def subrun(cmd,folder,limit):
    folder.mkdir(exist_ok=False)
    out,err=folder/"out.txt",folder/"err.txt"
    def limits():
        resource.setrlimit(resource.RLIMIT_FSIZE,(64<<20,64<<20))
        resource.setrlimit(resource.RLIMIT_AS,(3<<30,3<<30))
    env=dict(os.environ,OMP_NUM_THREADS="1",OPENBLAS_NUM_THREADS="1",
             MKL_NUM_THREADS="1")
    env["LD_LIBRARY_PATH"]=str(ROOT/"build/cms-libs/usr/lib/x86_64-linux-gnu")
    start=time.perf_counter()
    with out.open("w") as sout,err.open("w") as serr:
        proc=subprocess.Popen(cmd,stdout=sout,stderr=serr,
                              start_new_session=True,preexec_fn=limits,env=env)
        expired=False
        while True:
            pid,status,usage=os.wait4(proc.pid,os.WNOHANG)
            if pid:break
            if time.perf_counter()-start>=limit:
                expired=True
                try:os.killpg(proc.pid,signal.SIGKILL)
                except ProcessLookupError:pass
                _,status,usage=os.wait4(proc.pid,0)
                break
            time.sleep(.002)
    return dict(rc=os.waitstatus_to_exitcode(status),
       expired=expired,wall=time.perf_counter()-start,
       cpu=usage.ru_utime+usage.ru_stime,rss=usage.ru_maxrss,
       out=out.read_text(errors="replace"),err=err.read_text(errors="replace"))

def trial(s,arm,rep,root):
    folder=root/f'{s["id"]:03d}-{arm}-r{rep}'
    folder.mkdir()
    cnf=ROOT/s["path"]
    original=ROOT/s["original_path"]
    if file_sha(cnf)!=s["sha256"]:raise RuntimeError("CNF changed")
    proof=folder/("proof.frat" if arm=="CMS" else "proof.drat")
    start=time.perf_counter()
    cap=s["cap_s"]
    p=subrun(command(arm,cnf,proof,cap),folder/"solver",cap)
    status="TIMEOUT" if p["expired"] else "UNKNOWN"
    kind=None; checker_s=0.0
    if not p["expired"] and p["rc"]==10:
        if "s SATISFIABLE" not in p["out"].splitlines():
            status="INVALID_STATUS"
        elif not model_ok(original,p["out"]):
            status="INVALID_SAT_MODEL"
        else:
            status="SAT_VERIFIED";kind="MODEL"
    elif not p["expired"] and p["rc"]==20:
        if "s UNSATISFIABLE" not in p["out"].splitlines():
            status="INVALID_STATUS"
        elif not proof.exists() or proof.stat().st_size==0:
            status="UNSAT_UNVERIFIED"
        else:
            proof_type="FRAT" if arm=="CMS" else "DRAT"
            if proof_type=="FRAT":
                cmd=[str(ROOT/"build/frat-rs"),"elab",str(proof),str(cnf),"-v"]
            else:
                cmd=[str(ROOT/"build/drat-trim"),str(cnf),str(proof)]
            remaining=cap-(time.perf_counter()-start)
            if remaining<=0.002:
                status="CHECK_BUDGET_EXHAUSTED"
            else:
                check=subrun(cmd,folder/"checker",remaining)
                checker_s=check["wall"]
                if not check["expired"] and check["rc"]==0 and "VERIFIED" in check["out"]:
                    status="UNSAT_VERIFIED";kind=proof_type
                else:
                    status="CHECK_TIMEOUT" if check["expired"] else "UNSAT_UNVERIFIED"
    elif not p["expired"] and p["rc"] not in (0,153):
        status="RESOURCE_LIMIT" if p["rc"] in (-9,-25,137) else "SOLVER_ERROR"
    e2e=time.perf_counter()-start
    accepted=status in ("SAT_VERIFIED","UNSAT_VERIFIED") and e2e<=cap
    if not accepted and status in ("SAT_VERIFIED","UNSAT_VERIFIED"):
        status="CHECK_BUDGET_EXHAUSTED";kind=None
    critical=status.startswith("INVALID") or status=="SOLVER_ERROR"
    if accepted and s["catalog_label"] in ("SAT","UNSAT") and (
         ("SAT" if status=="SAT_VERIFIED" else "UNSAT")!=s["catalog_label"]):
        critical=True
    local=None
    for line in p["err"].splitlines():
        if line.startswith("SAT_TRAIL_STATS "):
            try:local=json.loads(line.split(" ",1)[1])
            except ValueError:pass
    return dict(source_id=s["id"],source_sha256=s["source_sha256"],
       dataset=s["dataset"],family=s["family"],arm=arm,rep=rep,
       status=status,accepted=accepted,kind=kind,critical=critical,
       method_trail=local,cap_s=cap,
       e2e_s=round(e2e,6),PAR2_s=round(e2e if accepted else 2*cap,6),
       solver_cpu_s=round(p["cpu"],6),maxrss_kib=p["rss"],
       solver_wall_s=round(p["wall"],6),checker_s=round(checker_s,6),
       error_tail=p["err"][-350:] if critical else None)

def shard_run(ix):
    assert 0<=ix<SHARDS
    cpu=pin()
    m=validate()
    out=OUT/f"shard-{ix}"
    out.mkdir(parents=True,exist_ok=False)
    save(out/"environment.json",dict(cpu=cpu,platform=platform.platform(),
       file_sha256={str(p):file_sha(ROOT/p) for p in
       set(BINS.values())|{"build/drat-trim","build/frat-rs"}},
       manifest_sha256=file_sha(INPUT/"manifest.json")))
    counts=collections.Counter()
    sources=[s for s in m["sources"] if s["id"]%SHARDS==ix]
    with (out/"trials.jsonl").open("w") as f, tempfile.TemporaryDirectory() as td:
        tmp=Path(td)
        for i,s in enumerate(sources):
            order=list(ARMS)
            random.Random(20261115+s["id"]).shuffle(order)
            for rep in range(s["repetitions"]):
                arms=order[rep%len(order):]+order[:rep%len(order)]
                for arm in arms:
                    row=trial(s,arm,rep,tmp)
                    f.write(json.dumps(row,sort_keys=True)+"\n")
                    f.flush()
                    counts[(arm,row["status"])]+=1
                    if row["critical"]:
                        emit("TRAIL1_CRITICAL",dict(source_id=s["id"],arm=arm,
                              status=row["status"],error=row["error_tail"]))
                    import shutil
                    shutil.rmtree(tmp/f'{s["id"]:03d}-{arm}-r{rep}')
            if (i+1)%25==0:
                emit("TRAIL1_PROGRESS",dict(shard=ix,sources_done=i+1,
                     total_sources=len(sources)))
    emit("TRAIL1_SHARD_COMPLETE",dict(shard=ix,sources=len(sources),
         trials=sum(counts.values()),statuses={
             f"{a}:{status}":n for (a,status),n in sorted(counts.items())}))

def report():
    m=validate()
    rows=[]
    for i in range(SHARDS):
        path=OUT/f"shard-{i}/trials.jsonl"
        rows.extend(json.loads(line) for line in path.read_text().splitlines())
    wanted={(s["id"],a,rep) for s in m["sources"] for a in ARMS
            for rep in range(s["repetitions"])}
    actual=[(r["source_id"],r["arm"],r["rep"]) for r in rows]
    if len(actual)!=len(set(actual)) or set(actual)!=wanted:
        raise RuntimeError("incomplete or duplicate benchmark trial matrix")
    for r in rows:
        if r["source_sha256"]!=m["sources"][r["source_id"]]["source_sha256"]:
            raise RuntimeError("source SHA drift in trials")
    criticals=[r for r in rows if r["critical"]]
    for s in m["sources"]:
        verdicts={r["status"] for r in rows if r["source_id"]==s["id"]
                 and r["accepted"]}
        if "SAT_VERIFIED" in verdicts and "UNSAT_VERIFIED" in verdicts:
            criticals.append(dict(source_id=s["id"],reason="verified contradictory answers"))
    totals={}
    for ds in ("SATLIB600","REAL24"):
        totals[ds]={}
        for arm in ARMS:
            subset=[r for r in rows if r["dataset"]==ds and r["arm"]==arm]
            locals_=[r["method_trail"] for r in subset if r["method_trail"] is not None]
            totals[ds][arm]=dict(
               trials=len(subset),
               sat=sum(r["status"]=="SAT_VERIFIED" and r["accepted"] for r in subset),
               unsat=sum(r["status"]=="UNSAT_VERIFIED" and r["accepted"] for r in subset),
               accepted=sum(r["accepted"] for r in subset),
               PAR2_s=round(sum(r["PAR2_s"] for r in subset),6),
               median_solver_cpu_s=round(statistics.median(r["solver_cpu_s"] for r in subset),6),
               maxrss_kib=max(r["maxrss_kib"] for r in subset),
               full_models=sum(bool(x.get("full")) for x in locals_),
               full_candidates=sum(x.get("full_candidates",0) for x in locals_),
               attempts=sum(x.get("attempts",0) for x in locals_),
               phase_uses=sum(x.get("phase_uses",0) for x in locals_),
               found_local_xor=sum(x.get("xor_patterns",0)>0 for x in locals_),
               hints=sum(x.get("hints",0) for x in locals_),
               rup_units=0,
               statuses=dict(collections.Counter(r["status"] for r in subset)))
    comparisons={}
    for ds in totals:
        ref=totals[ds]["OFF"]["PAR2_s"]
        comparisons[ds]={a:round(1-totals[ds][a]["PAR2_s"]/ref,6) for a in ARMS}
    result=dict(status="COMPLETE" if not criticals else "CRITICAL",
                total_trials=len(rows),sources=624,critical_count=len(criticals),
                criticals=criticals,totals=totals,
                comparisons_vs_off=comparisons,
                manifest_sha256=file_sha(INPUT/"manifest.json"),
                no_automatic_promotion=True,
                repetitions_not_independent=True,
                source_blind=False)
    save(OUT/"summary.json",result)
    lines=["# DRNAS TRAIL-RECONSTRUCT1: 600 public SATLIB + 24 original SAT2024",
        "",
        "624 source-distinct formulas, six solvers, 3888 total trials. One pinned CPU.",
        "SATLIB E2E 2s cap and REAL24 3s cap, including checker.",
        "Only original-CNF verified SAT / DRAT or FRAT checked UNSAT is accepted.",
        "SATLIB is an easy retrospective comparison; REAL24 are older known original sources.",
        "There is no source-blind or independent replication claim.",
        ""]
    for ds in ("SATLIB600","REAL24"):
        lines.extend([f"## {ds}","","| Arm | SAT verified | UNSAT verified | Total PAR2 (s) | Trail full model | Full candidates | Trail attempts | Phase uses |",
                      "|---|---:|---:|---:|---:|---:|---:|"])
        for a,t in totals[ds].items():
            lines.append(f"| {a} | {t['sat']} | {t['unsat']} | {t['PAR2_s']:.6f} | {t['full_models']} | {t['full_candidates']} | {t['attempts']} | {t['phase_uses']} |")
        lines.extend(["",f"Relative verified PAR2 change vs OFF: {comparisons[ds]}.",""])
    lines.extend([f"Critical trial count: {len(criticals)}",
                  "Full per-trial records and source manifests stored as artifacts.",
                  "No edits to main, references, or APK. No solver promotion."])
    (OUT/"README.md").write_text("\n".join(lines)+"\n")
    emit("TRAIL1_FINAL",dict(status=result["status"],critical=len(criticals),
         trials=len(rows),totals=totals,comparisons_vs_off=comparisons))
    if criticals:raise RuntimeError("critical solver/proof failures: see summary")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("action",choices=("freeze","shard","report"))
    ap.add_argument("--index",type=int)
    a=ap.parse_args()
    if a.action=="freeze":freeze()
    if a.action=="shard":shard_run(a.index)
    if a.action=="report":report()

if __name__=="__main__":main()
