#!/usr/bin/env python3
"""ATLAS-MAP2 short paired original-CNF and synthetic-mixed audit.

Public SATLIB sources selected solely by a frozen SHA rank. "mixed_augmented"
is NOT an untouched benchmark: it adds a small satisfiability-preserving
independent parity chain as a POSITIVE CONTROL, and is reported separately.
"""
import hashlib
import io
import json
import os
import pathlib
import re
import resource
import subprocess
import tarfile
import time
import urllib.request

OUT=pathlib.Path("mre_atlasmap2")
OUT.mkdir(exist_ok=True)
SHARD=int(os.environ.get("ATLASMAP2_SHARD","0"))
assert 0<=SHARD<4
FAMILIES=("uf100-430","uf150-645","uf200-860","uf250-1065")
SPECS=((100,430),(150,645),(200,860),(250,1065))
FAMILY=FAMILIES[SHARD]
VARS,NCLAUSES=SPECS[SHARD]
RANK=58
CAP=6
REPEATS=2
ARMS={
    "native_A":("drnas_atlasmap2","A"),
    "native_MAP1":("drnas_atlasmap2","MAP1"),
    "native_MAP2_SHADOW":("drnas_atlasmap2","MAP2_SHADOW"),
    "native_MAP2_LIVE":("drnas_atlasmap2","MAP2_LIVE"),
    "native_MAP2_COMBO":("drnas_atlasmap2","MAP2_COMBO"),
    "kissat":("kissat",None),
    "cadical":("cadical",None),
}

URL="https://www.cs.ubc.ca/~hoos/SATLIB/Benchmarks/SAT/RND3SAT/"+FAMILY+".tar.gz"
with urllib.request.urlopen(URL,timeout=90) as response:
    archive=response.read(25_000_000)
with tarfile.open(fileobj=io.BytesIO(archive),mode="r:gz") as tar:
    entries=sorted(
        (m for m in tar.getmembers() if m.isfile() and m.name.lower().endswith(".cnf")),
        key=lambda m:hashlib.sha256((FAMILY+"|"+pathlib.PurePosixPath(m.name).name).encode()).hexdigest()
    )
    assert len(entries)>RANK
    selected=entries[RANK]
    raw=tar.extractfile(selected).read()
header=None
clauses=[]
pending=[]
finished=False
for line in raw.decode("ascii").splitlines():
    line=line.strip()
    if not line or line.startswith("c"):
        continue
    if line.startswith("%"):
        finished=True
        continue
    if finished:
        if line=="0":continue
        raise ValueError("unexpected data after SATLIB trailer")
    if line.startswith("p "):
        fields=line.split()
        assert len(fields)==4 and fields[1]=="cnf" and header is None
        header=(int(fields[2]),int(fields[3]))
        continue
    assert header
    for token in line.split():
        lit=int(token)
        if lit:
            assert abs(lit)<=header[0]
            pending.append(lit)
        else:
            clauses.append(pending)
            pending=[]
assert header==(VARS,NCLAUSES) and not pending and len(clauses)==NCLAUSES

def dimacs(n,cs):
    return (f"p cnf {n} {len(cs)}\n" +
            "".join(" ".join(map(str,c))+" 0\n" for c in cs)).encode()

# The mixed control adds 6 new parity-linked variables disconnected from the
# SATLIB core. A unit fixes its first variable. It *preserves* SAT status but
# is an intentionally synthetic extension, not the original official CNF.
mixed=[list(c) for c in clauses]
new=[VARS+1+i for i in range(6)]
mixed.append([new[0]])
for i in range(len(new)-1):
    x,y=new[i:i+2]
    rhs=i%2
    if rhs==0:mixed.extend(([-x,y],[x,-y]))
    else:mixed.extend(([x,y],[-x,-y]))
COHORTS={
    "original":(VARS,clauses),
    "mixed_augmented":(VARS+6,mixed),
}
meta={
    "family":FAMILY,"rank":RANK,"shard":SHARD,
    "selection_rule":"SHA256(family|basename), ascending; rank 58",
    "original_source":"SATLIB public uf-series, source-locked before timing",
    "entry":selected.name,"archive_sha256":hashlib.sha256(archive).hexdigest(),
    "raw_sha256":hashlib.sha256(raw).hexdigest(),
    "cap_s":CAP,"repeats":REPEATS,"one_cpu":True,
    "mixed_kind":"synthetic independent 6-var certified parity chain + root unit; NOT original SATLIB",
}
paths={}
for cohort,(n,cs) in COHORTS.items():
    data=dimacs(n,cs)
    path=OUT/(cohort+".cnf")
    path.write_bytes(data)
    paths[cohort]=path
    meta[cohort]={"sha256":hashlib.sha256(data).hexdigest(),
                  "variables":n,"clauses":len(cs)}
(OUT/"source.json").write_text(json.dumps(meta,indent=2,sort_keys=True))
print("ATLASMAP2_SOURCE "+json.dumps(meta,sort_keys=True),flush=True)

def verify_model(stdout,n,cs):
    model={}
    for line in stdout.splitlines():
        if line.startswith("v "):
            for token in line.split()[1:]:
                value=int(token)
                if value:model[abs(value)]=value>0
    return len(model)==n and all(
        any(model[abs(lit)]==(lit>0) for lit in clause)
        for clause in cs)

def trial(cohort,arm,rep):
    n,cs=COHORTS[cohort]
    binary,mode=ARMS[arm]
    cmd=[str((OUT/"bin"/binary).resolve()),str(paths[cohort].resolve())]
    if mode is not None:cmd.extend(("--mode",mode,"--time",str(CAP)))
    def limits():
        resource.setrlimit(resource.RLIMIT_CPU,(CAP,CAP+1))
        resource.setrlimit(resource.RLIMIT_AS,(4*1024**3,4*1024**3))
    t=time.monotonic()
    try:
        proc=subprocess.run(cmd,capture_output=True,text=True,
                            timeout=CAP+2,preexec_fn=limits)
        rc,stdout,stderr=proc.returncode,proc.stdout,proc.stderr
    except subprocess.TimeoutExpired:
        rc,stdout,stderr=124,"","external_wall_timeout"
    wall=time.monotonic()-t
    status={10:"SAT",20:"UNSAT"}.get(rc,"UNKNOWN")
    if status=="SAT" and not verify_model(stdout,n,cs):
        raise RuntimeError("invalid ORIGINAL-COHORT SAT witness: "+str((cohort,arm,rep)))
    if status=="UNSAT":
        raise RuntimeError("UNSAT on known-SAT original/extension: "+str((cohort,arm,rep)))
    if status=="UNKNOWN" and rc not in (0,124,-9,-24):
        raise RuntimeError(f"solver error {cohort} {arm} rc={rc}: {stderr[-400:]}")
    details={}
    match=re.search(r"^ATLASMAP2_TRIAL (.*)$",stdout,re.M)
    if mode is not None and match:
        details=dict(field.split("=",1) for field in match.group(1).split() if "=" in field)
        if details.get("SAT_original_verified")!="1" and status=="SAT":
            raise RuntimeError("native original witness flag missing")
    if mode is not None and status=="SAT" and not match:
        raise RuntimeError("missing native telemetry on solved attempt")
    if arm=="native_MAP2_LIVE" and cohort=="mixed_augmented" and status=="SAT":
        if int(details.get("map2_groups",0))<1 or int(details.get("map2_implications",0))<5:
            raise RuntimeError("positive mixed source group produced no native reasons: "+repr(details))
    return {
        "cohort":cohort,"arm":arm,"repeat":rep,"status":status,
        "E2E_s":round(wall,6),
        "PAR2_s":round(wall if status=="SAT" else 2*CAP,6),
        "SAT_original_model_verified":status=="SAT",
        "UNSAT_independent_LRAT":False,
        "native":details,
        "returncode":rc,"stderr_tail":stderr[-300:],
    }
rows=[]
for cohort in ("original","mixed_augmented"):
    for rep in range(REPEATS):
        for arm in ARMS:
            result=trial(cohort,arm,rep)
            rows.append(result)
            print("ATLASMAP2_TRIAL "+json.dumps(result,sort_keys=True),flush=True)
summary={}
for cohort in COHORTS:
    summary[cohort]={}
    for arm in ARMS:
        these=[r for r in rows if r["cohort"]==cohort and r["arm"]==arm]
        summary[cohort][arm]={
            "solved":sum(r["status"]=="SAT" for r in these),
            "trials":len(these),
            "PAR2_s":round(sum(r["PAR2_s"] for r in these),6),
            "E2E_wall_s":round(sum(r["E2E_s"] for r in these),6),
            "live_implications":sum(int(r["native"].get("map2_implications",0))
                                    for r in these),
            "shadow_opportunities":sum(int(r["native"].get("map2_shadow_opportunities",0))
                                       for r in these),
        }
audit={"protocol":"MAP2-SATLIB-RANK58-4F-2REPS-6S-ONECPU-ORIG+SYNTH",
       "source":meta,"rows":rows,"summary":summary}
(OUT/"audit.json").write_text(json.dumps(audit,indent=2,sort_keys=True))
print("ATLASMAP2_FINAL "+json.dumps({"family":FAMILY,"summary":summary},sort_keys=True),flush=True)
