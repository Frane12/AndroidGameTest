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

PROTOCOL="DRNAS-V146-STREAMING-PARITY-30-BLIND2024-CAP8-20261101-v1"
HOLDOUT_PROTOCOL="DRNAS-V146-BLIND30-SC2024-STREAMING-PARITY-20261101-v1"
MODES=("V146_StreamPrefix","V145_Propagated","V144_HiddenParity","Kissat404")
REPS=2;SHARDS=10;CAP=8.0;MEM=3
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
    assertok(meta["protocol"]=="DRNAS-V1313-SC2024-THIRTY-SHA-DISJOINT-20261101-v1" and
             meta["holdout_protocol"]==HOLDOUT_PROTOCOL and
             len(meta["cases"])==30,"Wrong 30 unseen new CNFs")
    assertok(len({c["sha256"] for c in meta["cases"]})==30 and
             Counter(c["official_label"] for c in meta["cases"])=={"SAT":15,"UNSAT":15},
             "Wrong identities or label balance")
    assertok(len({c["id"] for c in meta["cases"]})==30,"Repeated official ID")
    write(a.out,{"protocol":PROTOCOL,"origin_manifest_sha256":digest(a.prior),
        "cases":meta["cases"],"modes":MODES,"reps":REPS,"cap_seconds":CAP,
        "cohorts":"new-2024-original-CNF-SHA-disjoint-from-V14.5-and-earlier",
        "limits":["All 30 formulas pre-selected using source family and official SAT/UNSAT labels, not solver timings.",
          "Genuine public 2024 SAT Main Track; this is a small, size-filtered sample, not official ranking.",
          "8 second cap, 3 GiB memory, CPU affinity to a single core, two reps per solver.",
          "A matched SAT/UNSAT published label is not a DRAT UNSAT proof. Native XOR UNSAT claims require independent GF2 replay.",
          "V14.6 code and gate precommitted before these 30 formulas were timed.",
          "The gate may not catch all useful XOR blocks; false negatives are acceptable, false UNSAT is not."]})
    print("V146_FREEZE_PASS sha-disjoint 30 SAT/UNSAT",digest(a.out),flush=True)

def verify_hidden_parity(cnf,proof):
    """Independent soundness audit: source clauses exactly encode each 1/2/3 XOR
    equation (all 2^k valuations), then XOR all claimed equations to 0=1.
    Unknown/malformed witnesses fail closed."""
    clauses=[record[1] for record in verifier.clauses(cnf) if record[0]=="clause"]
    if not isinstance(proof,list) or not proof or len(proof)>512:
        return False
    support=set();rhs=0
    for e in proof:
        vs=e.get("variables");bit=e.get("rhs");ids=e.get("clause_indices")
        if (not isinstance(vs,list) or not 1<=len(vs)<=3 or
            not all(isinstance(x,int) and x>0 for x in vs) or
            len(set(vs))!=len(vs) or vs!=sorted(vs) or bit not in (0,1) or
            not isinstance(ids,list) or len(ids)!=(1<<(len(vs)-1)) or
            len(set(ids))!=len(ids) or not all(isinstance(i,int) and 0<=i<len(clauses) for i in ids)):
            return False
        pos={v:j for j,v in enumerate(vs)}
        if any(any(abs(l) not in pos for l in clauses[i]) for i in ids):
            return False
        for mask in range(1<<len(vs)):
            sat=all(any(bool((mask>>pos[abs(l)])&1)==(l>0) for l in clauses[i]) for i in ids)
            parity=(mask.bit_count()&1)==bit
            if sat!=parity:return False
        for v in vs:
            if v in support:support.remove(v)
            else:support.add(v)
        rhs^=bit
    return not support and rhs==1

def verify_propagated_parity(cnf,proof,steps):
    """Proof checking independent of C++: replay every unit-propagation step on
    ORIGINAL clauses, then each claimed 1/2/3 parity implication by truth
    table or replayed unit. XOR verified rows must sum to 0 = 1."""
    clauses=[rec[1] for rec in verifier.clauses(cnf) if rec[0]=="clause"]
    if not isinstance(steps,list) or not isinstance(proof,list) or not proof or \
       len(steps)>4096 or len(proof)>512:
        return False
    values={}
    for step in steps:
        if not isinstance(step,dict):return False
        lit=step.get("lit");reason=step.get("reason_clause")
        if not isinstance(lit,int) or lit==0 or abs(lit) in values or \
           not isinstance(reason,int) or reason<0 or reason>=len(clauses):
            return False
        unknown=0
        for x in clauses[reason]:
            v=values.get(abs(x))
            if v is None:
                if x!=lit:return False
                unknown+=1
            elif v==(x>0):
                return False
        if unknown!=1:return False
        values[abs(lit)]=(lit>0)
    support=set();xor_bit=0
    for e in proof:
        if not isinstance(e,dict):return False
        vs=e.get("variables");rhs=e.get("rhs");ids=e.get("clause_indices")
        if not isinstance(vs,list) or not 1<=len(vs)<=3 or \
           not all(isinstance(x,int) and x>0 for x in vs) or \
           vs!=sorted(set(vs)) or rhs not in (0,1):
            return False
        if "unit_step" in e:
            j=e["unit_step"]
            if not isinstance(j,int) or j<0 or j>=len(steps) or \
               len(vs)!=1 or ids!=[] or vs[0]!=abs(steps[j]["lit"]) or \
               rhs!=int(steps[j]["lit"]>0):return False
        else:
            if not isinstance(ids,list) or len(ids)!=(1<<(len(vs)-1)) or \
               len(set(ids))!=len(ids) or \
               not all(isinstance(i,int) and 0<=i<len(clauses) for i in ids):
                return False
            pos={v:j for j,v in enumerate(vs)}
            if any(any(abs(lit) not in pos for lit in clauses[i]) for i in ids):return False
            for mask in range(1<<len(vs)):
                sat=all(any(bool((mask>>pos[abs(lit)])&1)==(lit>0)
                            for lit in clauses[i]) for i in ids)
                if sat!=((mask.bit_count()&1)==rhs):return False
        for v in vs:
            if v in support:support.remove(v)
            else:support.add(v)
        xor_bit^=rhs
    return not support and xor_bit==1

def native(mode,cnf,seed,label,a):
    exe=a.v146 if mode=="V146_StreamPrefix" else a.v145 if mode=="V145_Propagated" else a.v144
    command=[str(Path(exe).resolve()),str(Path(cnf).resolve()),
             str(Path(a.kissat).resolve()),str(seed)]
    start=time.monotonic()
    try:
        p=subprocess.run(command,capture_output=True,text=True,errors="replace",
                         timeout=CAP,preexec_fn=limit,check=False)
        seconds=time.monotonic()-start
        lines=p.stdout.splitlines()
        streamed=[line for line in lines if line.startswith("DRNAS_V146_RESULT\t")]
        propagated=[line for line in lines if line.startswith("DRNAS_V145_RESULT\t")]
        hidden=[line for line in lines if line.startswith("DRNAS_V144_RESULT\t")]
        local=[line for line in lines if line.startswith("DRNAS_V143_RESULT\t")]
        whole=[line for line in lines if line.startswith("DRNAS_HYBRID_RESULT\t")]
        if len(streamed)==1:
            assertok(mode=="V146_StreamPrefix" and p.returncode==0,"Wrong streaming proof route")
            data=json.loads(streamed[0].split("\t",1)[1])
            assertok(data["status"]=="UNSAT" and data["verified"] and
                     data["path"]=="streaming_bounded_parity" and
                     96*1024 < cnf.stat().st_size and data["scanned_bytes"]<=2*1024*1024+100000 and
                     data["scanned_clauses"]<=30000 and
                     verify_hidden_parity(cnf,data["proof"]),
                     "Original-CNF clause replay rejected partial streaming UNSAT")
            path="certified_streaming_xor";status="UNSAT"
        elif len(propagated)==1:
            assertok(mode in ("V146_StreamPrefix","V145_Propagated") and p.returncode==0,"Wrong native path")
            data=json.loads(propagated[0].split("\t",1)[1])
            assertok(data["status"]=="UNSAT" and data["verified"] and
                     data["path"]=="propagated_hidden_parity" and
                     verify_propagated_parity(cnf,data["proof"],data["unit_steps"]),
                     "Failed independent CNF propagation and GF2 proof replay")
            path="certified_propagated_parity";status="UNSAT"
        elif len(hidden)==1:
            assertok(mode in ("V146_StreamPrefix","V145_Propagated","V144_HiddenParity") and p.returncode==0,
                     "Unexpected hidden-parity proof")
            data=json.loads(hidden[0].split("\t",1)[1])
            assertok(data["status"]=="UNSAT" and data["verified"] and
                     data["path"]=="hidden_parity_gf2", "Bad hidden proof metadata")
            assertok(verify_hidden_parity(cnf,data["proof"]),
                     "Independent original-clause truth-table XOR proof failed")
            path="certified_hidden_parity";status="UNSAT"
        elif len(local)==1:
            assertok(mode in ("V145_Propagated","V144_HiddenParity") and p.returncode==0,
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
            assertok(any(line.startswith("DRNAS_V142_ROUTE\tkissat_direct") for line in lines),
                     "FastGate Kissat route output missing")
            path="kissat_fallback"
        assertok(status==label,"Native verdict differs from published label")
        assertok(seconds<=CAP,"Late result")
        return {"status":status,"seconds":round(seconds,6),"path":path,"error":""}
    except subprocess.TimeoutExpired:
        return {"status":"TIMEOUT","seconds":CAP,"path":"timeout","error":""}
    except Exception as exc:
        return {"status":"ERROR","seconds":round(min(CAP,time.monotonic()-start),6),
                "path":"error","error":str(exc)[:450]}

def trial(mode,path,seed,label,a):
    if mode in ("V146_StreamPrefix","V145_Propagated","V144_HiddenParity"):
        return native(mode,path,seed,label,a)
    z=mini.trial(mode,path,seed,a.kissat,a.kissat,label)
    return {"status":z["status"],"seconds":z["seconds"],
            "path":mode,"error":z["error"]}

def run(a):
    m=read(a.manifest)
    assertok(m["protocol"]==PROTOCOL and 0<=a.shard<SHARDS,"Manifest/shard mismatch")
    cases=m["cases"][a.shard::SHARDS]
    assertok(len(cases)==3,"Expected three formulas per shard")
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    cpu=next((x.split(":",1)[1].strip() for x in Path("/proc/cpuinfo").read_text().splitlines()
              if x.startswith("model name")),"unknown")
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    signatures={name:digest(getattr(a,name)) for name in ("v146","v145","v144","kissat")}
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
            seed=(1462026+int(c["sha256"][:8],16)+1009*rep)%(2**32)
            order=list(MODES);random.Random(seed^146).shuffle(order)
            for mode in order:
                z=trial(mode,target,seed,c["official_label"],a)
                assertok(z["status"] in ("SAT","UNSAT","TIMEOUT") and not z["error"],
                         "Bad solver "+mode+" "+c["id"]+" "+z["error"])
                assertok(z["status"]=="TIMEOUT" or z["status"]==c["official_label"],
                         "Wrong SAT/UNSAT label "+mode)
                repeats.append({"mode":mode,"rep":rep,**z})
                print("V146_TRIAL",c["id"],mode,rep,z["status"],z["seconds"],z["path"],flush=True)
        rows.append({"id":c["id"],"sha256":c["sha256"],"family":c["family"],
                     "label":c["official_label"],"trials":repeats})
        write(out/"rows.json",rows)
        target.unlink()
    print("V146_SHARD_PASS",a.shard,len(rows),flush=True)

def audit(a):
    m=read(a.manifest);assertok(m["protocol"]==PROTOCOL,"Wrong audit manifest")
    rows=[];unique_bin=set();cpu=set();cases={c["id"]:c for c in m["cases"]}
    for shard in range(SHARDS):
        d=Path(a.combined)/f"v146-shard-{shard}"
        meta=read(d/"meta.json");part=read(d/"rows.json")
        expected=m["cases"][shard::SHARDS]
        assertok(meta["protocol"]==PROTOCOL and meta["shard"]==shard and
                 meta["manifest_sha"]==digest(a.manifest) and
                 meta["ids"]==[c["id"] for c in expected] and
                 [r["id"] for r in part]==meta["ids"],"Wrong shard or identities")
        unique_bin.add(json.dumps(meta["binaries"],sort_keys=True))
        cpu.add(meta["cpu"]);rows+=part
    assertok(len(rows)==30 and len({r["sha256"] for r in rows})==30,
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
    summary={mode:{"solved":totals[mode],"total":30*REPS,
                   "par2_s":round(statistics.mean(times[mode]),6)} for mode in MODES}
    report={"protocol":PROTOCOL,"manifest_sha":digest(a.manifest),
            "cases":per_case,"summary":summary,"paths":dict(paths),
            "CPUs":sorted(cpu),"binary_sha256s":json.loads(next(iter(unique_bin))),
            "limitations":m["limits"],"attempts":30*REPS*len(MODES)}
    write(a.out,report)
    md=["# V14.6 Bounded Prefix Streaming XOR: NEW blind 2024 SAT Main Track CNFs",
        "","30 precommitted SHA-disjoint original CNFs, 2 repeats, 8 seconds per solver, one core, 3GiB.",
        "","| Solver | Solved / 60 | PAR2 seconds (lower better) |",
        "|---|---:|---:|"]
    for mode,z in summary.items():
        md.append(f"| {mode} | {z['solved']}/{z['total']} | {z['par2_s']:.6f} |")
    md+=["","## Solver paths",json.dumps(dict(paths),sort_keys=True),"",
         "## Formulas with a verified new streaming XOR proof"]
    for row in per_case:
        if any(x["mode"]=="V146_StreamPrefix" and x["path"]=="certified_streaming_xor"
               for x in next(y for y in rows if y["id"]==row["id"])["trials"]):
            md.append("- "+row["id"]+" ("+row["family"]+")")
    md+=["","## Limitations"]+["- "+x for x in m["limits"]]
    Path(a.md).write_text("\n".join(md)+"\n")
    print("V146_AUDIT_PASS",json.dumps(summary),flush=True)
def main():
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest="cmd",required=True)
    z=sub.add_parser("freeze")
    for x in ("prior","out"):z.add_argument("--"+x,required=True)
    z=sub.add_parser("run")
    for x in ("manifest","v146","v145","v144","kissat","out"):
        z.add_argument("--"+x,required=True)
    z.add_argument("--shard",type=int,required=True)
    z=sub.add_parser("audit")
    for x in ("manifest","combined","out","md"):z.add_argument("--"+x,required=True)
    a=p.parse_args()
    if a.cmd=="freeze":freeze(a)
    elif a.cmd=="run":run(a)
    else:audit(a)
if __name__=="__main__":main()
