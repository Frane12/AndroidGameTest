#!/usr/bin/env python3
"""Strict V14.3 blind real SAT benchmark: 30 new SHA-disjoint 2024 Main CNFs.
Compares native local XOR+FastGate to unchanged V14.2, Kissat, and legacy.
All solvers get 8s full wall time, 3GiB, one CPU, shuffled paired order.
Only SHA-locked source CNFs and official label checks; decision never uses label.
For native XOR contradiction independently replay original 4-clause groups.
"""
import argparse, hashlib, json, os, random, resource, statistics, subprocess, time
from pathlib import Path
from collections import Counter,defaultdict
import v1311_local_xor as verifier
import v137_fastpath as fullverify
import official_shortlong_select as source
import official_2026_mini_sim as mini

PROTOCOL="DRNAS-V144-MIXED-XOR-NEW16-BLIND2024-CAP16-20261101-v1"
HOLDOUT_PROTOCOL="DRNAS-V144-MIXED-XOR-NEW16-SC2024-20261101-v1"
MODES=("V144_Mixed","V143_NativeLocal","Kissat404","DRNAS_Legacy")
REPS=2;SHARDS=8;CAP=16.0;MEM=3
mini.CAP=CAP;mini.MEMORY_GIB=MEM
source.RAW_CAP=96*1024**2;source.CNF_CAP=64*1024**2
source.VARIABLE_CAP=500000;source.CLAUSE_CAP=1000000

def assertok(x,message):
    if not x: raise RuntimeError(message)
def read(p):return json.loads(Path(p).read_text())
def write(p,z):
    path=Path(p);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(z,sort_keys=True,indent=2)+"\n")
def digest(p):
    h=hashlib.sha256()
    with Path(p).open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""):h.update(b)
    return h.hexdigest()
def limit():
    mem=MEM*1024**3;resource.setrlimit(resource.RLIMIT_AS,(mem,mem))

def freeze(a):
    meta=read(a.prior)
    assertok(meta["protocol"]=="DRNAS-V144-SC2024-NEW16-SHA-DISJOINT-20261101-v1" and
             meta["holdout_protocol"]==HOLDOUT_PROTOCOL and
             len(meta["cases"])==16,"Wrong 16 new CNFs")
    assertok(len({c["sha256"] for c in meta["cases"]})==16 and
             Counter(c["official_label"] for c in meta["cases"])=={"SAT":8,"UNSAT":8},
             "Wrong identities or label balance")
    assertok(len({c["id"] for c in meta["cases"]})==16,"Repeated official ID")
    write(a.out,{"protocol":PROTOCOL,"origin_manifest_sha256":digest(a.prior),
        "cases":meta["cases"],"modes":MODES,"reps":REPS,"cap_seconds":CAP,
        "cohorts":"new-2024-original-CNF-SHA-disjoint-from-V14.3-and-earlier",
        "limits":["All 30 formulas pre-selected using source family and official SAT/UNSAT labels, not solver timings.",
          "Genuine public 2024 SAT Main Track; this is a small, size-filtered sample, not official ranking.",
          "16 second cap, 3 GiB memory, CPU affinity to a single core, two reps per solver.",
          "A matched SAT/UNSAT published label is not a DRAT UNSAT proof. Native XOR UNSAT claims require independent GF2 replay.",
          "V14.4 algorithm was frozen before solver runs on these 16 CNFs.",
          "Only independently rechecked GF2-derived constraints can be appended; no proof-based result may bypass verification."]})
    print("V144_FREEZE_PASS sha-disjoint 30 SAT/UNSAT",digest(a.out),flush=True)

def native(mode,cnf,seed,label,a):
    exe=a.v144 if mode=="V144_Mixed" else a.v143
    command=[str(Path(exe).resolve()),str(Path(cnf).resolve()),
             str(Path(a.kissat).resolve()),str(seed)]
    start=time.monotonic()
    try:
        p=subprocess.run(command,capture_output=True,text=True,errors="replace",
                         timeout=CAP,preexec_fn=limit,check=False)
        seconds=time.monotonic()-start
        lines=p.stdout.splitlines()
        local=[line for line in lines if line.startswith("DRNAS_V143_RESULT\t")]
        whole=[line for line in lines if line.startswith("DRNAS_HYBRID_RESULT\t")]
        if len(local)==1:
            assertok(mode in ("V143_NativeLocal","V144_Mixed") and p.returncode==0,
                     "Local XOR proof from wrong program")
            data=json.loads(local[0].split("\t",1)[1])
            assertok(data["status"]=="UNSAT" and data["verified"] and
                     data["path"]=="local_xor_verified","Invalid local certificate metadata")
            _,_,equations,diag=verifier.extract(cnf)
            assertok(diag["extraction_complete"] and
                     len(equations)==data["xor_blocks"] and
                     verifier.proof_valid(equations,data["proof_equation_indices"],(),1),
                     "Independent replay rejected native local XOR contradiction")
            path="certified_local_xor";status="UNSAT"
        elif len(whole)==1:
            assertok(p.returncode==0,"Native exact solver failed")
            data=json.loads(whole[0].split("\t",1)[1])
            n,clauses=fullverify.read_dimacs(cnf.read_bytes())
            assertok(data["status"] in ("SAT","UNSAT") and data["verified"] and
                     fullverify.verify(n,clauses,data),
                     "Original exact GF2/PHP certificate verification failed")
            path=data["path"];status=data["status"]
        else:
            assertok(p.returncode in (10,20),
                     "Native fallback did not launch Kissat "+str(p.returncode)+" "+p.stderr[-220:])
            status="SAT" if p.returncode==10 else "UNSAT"
            assertok("s SATISFIABLE" in p.stdout if status=="SAT" else
                     "s UNSATISFIABLE" in p.stdout,
                     "Kissat answer output missing")
            assertok(any(line.startswith("DRNAS_V142_ROUTE\tkissat_direct") for line in lines) or
                     (mode=="V144_Mixed" and any(line.startswith("DRNAS_V144_ROUTE\tmixed_xor_augmented") for line in lines)),
                     "FastGate Kissat route output missing")
            path="mixed_xor_augmented" if (mode=="V144_Mixed" and any(line.startswith("DRNAS_V144_ROUTE\tmixed_xor_augmented") for line in lines)) else "kissat_fallback"
        assertok(status==label,"Native verdict differs from published label")
        assertok(seconds<=CAP,"Late result")
        return {"status":status,"seconds":round(seconds,6),"path":path,"error":""}
    except subprocess.TimeoutExpired:
        return {"status":"TIMEOUT","seconds":CAP,"path":"timeout","error":""}
    except Exception as exc:
        return {"status":"ERROR","seconds":round(min(CAP,time.monotonic()-start),6),
                "path":"error","error":str(exc)[:450]}

def trial(mode,path,seed,label,a):
    if mode in ("V143_NativeLocal","V144_Mixed"):
        return native(mode,path,seed,label,a)
    z=mini.trial(mode,path,seed,a.legacy,a.kissat,label)
    return {"status":z["status"],"seconds":z["seconds"],
            "path":mode,"error":z["error"]}

def run(a):
    m=read(a.manifest)
    assertok(m["protocol"]==PROTOCOL and 0<=a.shard<SHARDS,"Manifest/shard mismatch")
    cases=m["cases"][a.shard::SHARDS]
    assertok(len(cases)==2,"Expected two formulas per shard")
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    cpu=next((x.split(":",1)[1].strip() for x in Path("/proc/cpuinfo").read_text().splitlines()
              if x.startswith("model name")),"unknown")
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    signatures={name:digest(getattr(a,name)) for name in ("v144","v143","kissat","legacy")}
    write(out/"meta.json",{"protocol":PROTOCOL,"shard":a.shard,"cpu":cpu,
                           "manifest_sha":digest(a.manifest),"binaries":signatures,
                           "ids":[c["id"] for c in cases]})
    rows=[]
    for c in cases:
        target=out/(c["id"]+".cnf")
        actual=source.download_and_features(c["id"],target)
        assertok(actual["sha256"]==c["sha256"] and
                 actual["features"]==c["features"] and
                 digest(target)==c["sha256"],"Official original CNF SHA mismatch")
        repeats=[]
        for rep in range(REPS):
            seed=(1442026+int(c["sha256"][:8],16)+1009*rep)%(2**32)
            order=list(MODES);random.Random(seed^144).shuffle(order)
            for mode in order:
                z=trial(mode,target,seed,c["official_label"],a)
                assertok(z["status"] in ("SAT","UNSAT","TIMEOUT") and not z["error"],
                         "Bad solver "+mode+" "+c["id"]+" "+z["error"])
                assertok(z["status"]=="TIMEOUT" or z["status"]==c["official_label"],
                         "Wrong SAT/UNSAT label "+mode)
                repeats.append({"mode":mode,"rep":rep,**z})
                print("V144_TRIAL",c["id"],mode,rep,z["status"],z["seconds"],z["path"],flush=True)
        rows.append({"id":c["id"],"sha256":c["sha256"],"family":c["family"],
                     "label":c["official_label"],"trials":repeats})
        write(out/"rows.json",rows)
        target.unlink()
    print("V144_SHARD_PASS",a.shard,len(rows),flush=True)

def audit(a):
    m=read(a.manifest);assertok(m["protocol"]==PROTOCOL,"Wrong audit manifest")
    rows=[];unique_bin=set();cpu=set();cases={c["id"]:c for c in m["cases"]}
    for shard in range(SHARDS):
        d=Path(a.combined)/f"v144-shard-{shard}"
        meta=read(d/"meta.json");part=read(d/"rows.json")
        expected=m["cases"][shard::SHARDS]
        assertok(meta["protocol"]==PROTOCOL and meta["shard"]==shard and
                 meta["manifest_sha"]==digest(a.manifest) and
                 meta["ids"]==[c["id"] for c in expected] and
                 [r["id"] for r in part]==meta["ids"],"Wrong shard or identities")
        unique_bin.add(json.dumps(meta["binaries"],sort_keys=True))
        cpu.add(meta["cpu"]);rows+=part
    assertok(len(rows)==16 and len({r["sha256"] for r in rows})==16,
             "Missing formulas")
    assertok(len(unique_bin)==1,"Binary hash drift between shards")
    totals=Counter();times=defaultdict(list);paths=Counter()
    per_case=[]
    for item in rows:
        c=cases[item["id"]]
        assertok(item["sha256"]==c["sha256"] and
                 item["label"]==c["official_label"],"Case identity changed")
        observed={(v["mode"],v["rep"]):v for v in item["trials"]}
        assertok(len(observed)==REPS*len(MODES),"Incomplete per-case trials")
        row={"id":item["id"],"family":item["family"],"label":item["label"],"modes":{}}
        for mode in MODES:
            attempts=[]
            for rep in range(REPS):
                z=observed[mode,rep]
                assertok(z["status"] in ("SAT","UNSAT","TIMEOUT") and not z["error"],
                         "Invalid solver status")
                assertok(z["status"]=="TIMEOUT" or z["status"]==item["label"],
                         "Incorrect answer")
                times[mode].append(2*CAP if z["status"]=="TIMEOUT" else z["seconds"])
                totals[mode]+=int(z["status"]!="TIMEOUT")
                paths[mode+":"+z["path"]]+=1
                attempts.append(z["seconds"] if z["status"]!="TIMEOUT" else None)
            row["modes"][mode]=attempts
        per_case.append(row)
    summary={mode:{"solved":totals[mode],"total":16*REPS,
                   "par2_s":round(statistics.mean(times[mode]),6)} for mode in MODES}
    report={"protocol":PROTOCOL,"manifest_sha":digest(a.manifest),
            "cases":per_case,"summary":summary,"paths":dict(paths),
            "CPUs":sorted(cpu),"binary_sha256s":json.loads(next(iter(unique_bin))),
            "limitations":m["limits"],"attempts":16*REPS*len(MODES)}
    write(a.out,report)
    md=["# V14.4 Mixed-CNF certified XOR preprocessing: NEW blind 2024 Main Track CNFs",
        "","16 precommitted SHA-disjoint original CNFs, 2 repeats, 16 seconds per solver, one core, 3GiB.",
        "","| Solver | Solved / 32 | PAR2 seconds (lower better) |",
        "|---|---:|---:|"]
    for mode,z in summary.items():
        md.append(f"| {mode} | {z['solved']}/{z['total']} | {z['par2_s']:.6f} |")
    md+=["","## Solver paths",json.dumps(dict(paths),sort_keys=True),"",
         "## Cases with a native certified local contradiction or verified mixed-XOR augmented solver"]
    for row in per_case:
        if any(x["mode"]=="V144_Mixed" and x["path"] in ("certified_local_xor","mixed_xor_augmented")
               for x in next(y for y in rows if y["id"]==row["id"])["trials"]):
            md.append("- "+row["id"]+" ("+row["family"]+")")
    md+=["","## Limitations"]+["- "+x for x in m["limits"]]
    Path(a.md).write_text("\n".join(md)+"\n")
    print("V144_AUDIT_PASS",json.dumps(summary),flush=True)
def main():
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest="cmd",required=True)
    z=sub.add_parser("freeze")
    for x in ("prior","out"):z.add_argument("--"+x,required=True)
    z=sub.add_parser("run")
    for x in ("manifest","v144","v143","kissat","legacy","out"):
        z.add_argument("--"+x,required=True)
    z.add_argument("--shard",type=int,required=True)
    z=sub.add_parser("audit")
    for x in ("manifest","combined","out","md"):z.add_argument("--"+x,required=True)
    a=p.parse_args()
    if a.cmd=="freeze":freeze(a)
    elif a.cmd=="run":run(a)
    else:audit(a)
if __name__=="__main__":main()
