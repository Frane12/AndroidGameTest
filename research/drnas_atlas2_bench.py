#!/usr/bin/env python3
"""DRNAS ATLAS2 independently checked E2E test on deterministic constructed
structured SAT (NOT external competition CNFs). Frozen 8 SHA inputs:
4 gate/cardinality families x minimal vs logically redundant encodings.
3 repeats, 20s cap, one logical CPU, original-model verification, PAR2.
"""
import hashlib,json,os,pathlib,re,resource,subprocess,time
from drnas_atlas2_generate_structured import FAMILIES,COHORTS,build
OUT=pathlib.Path("mre_atlas2")
OUT.mkdir(exist_ok=True)
SHARD=int(os.environ.get("MICRO_SHARD","0"))
assert 0<=SHARD<8
FAMILY=FAMILIES[SHARD//2]
COHORT=COHORTS[SHARD%2]
CAP=20
REPEATS=3
ARMS=("drnas","atlas1","atlas2","kissat","cadical")
source=build(FAMILY,COHORT)
data=source["raw"]
assert hashlib.sha256(data).hexdigest()==source["source_sha256"]
clauses=[]
for line in data.decode().splitlines()[1:]:
    c=list(map(int,line.split()))
    assert c.pop()==0
    clauses.append(c)
N=source["variables"]
assert len(clauses)==source["clauses"]
assert all(any(source["witness"][abs(l)]==(l>0) for l in c) for c in clauses)
path=OUT/"original.cnf";path.write_bytes(data)
manifest={k:v for k,v in source.items() if k not in ("raw","witness")}
manifest.update(shard=SHARD,cap_s=CAP,repeats=REPEATS,
    protocol="controlled_generated_structured_not_external_unseen")
(OUT/"source.json").write_text(json.dumps(manifest,sort_keys=True,indent=2))
print("ATLAS2_SOURCE "+json.dumps(manifest,sort_keys=True),flush=True)

def verify_model(stdout):
    assigned={}
    for line in stdout.splitlines():
        if not line.startswith("v "):continue
        for x in line.split()[1:]:
            l=int(x)
            if l==0:continue
            assert 1<=abs(l)<=N
            assert abs(l) not in assigned or assigned[abs(l)]==(l>0)
            assigned[abs(l)]=(l>0)
    if len(assigned)!=N:return False
    return all(any(assigned[abs(l)]==(l>0) for l in clause) for clause in clauses)

def run(arm,rep):
    programs={"drnas":"drnas_atlas2","atlas1":"drnas_atlas1",
              "atlas2":"drnas_atlas2","kissat":"kissat","cadical":"cadical"}
    command=[str((OUT/"bin"/programs[arm]).resolve()),str(path.resolve())]
    if arm in ("drnas","atlas1","atlas2"):
        mode={"drnas":"A","atlas1":"ATLAS1","atlas2":"ATLAS2"}[arm]
        command+=["--mode",mode,"--time",str(CAP)]
    def limits():
        resource.setrlimit(resource.RLIMIT_CPU,(CAP,CAP+1))
        resource.setrlimit(resource.RLIMIT_AS,(4*1024**3,4*1024**3))
    started=time.monotonic()
    try:
        p=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
          text=True,timeout=CAP+2,preexec_fn=limits)
        rc=p.returncode;stdout=p.stdout;stderr=p.stderr
    except subprocess.TimeoutExpired:
        rc=124;stdout="";stderr="timeout"
    elapsed=time.monotonic()-started
    status={10:"SAT",20:"UNSAT"}.get(rc,"UNKNOWN")
    if status=="SAT":
        assert verify_model(stdout),("Original SAT witness INVALID",arm,stderr[-600:])
    elif status=="UNSAT":
        raise AssertionError(("Constructed SAT benchmark unexpectedly UNSAT",arm))
    elif rc not in (0,124,-9,-24):
        raise RuntimeError(("Unexpected solver error",arm,rc,stderr[-900:]))
    telemetry={}
    marker={"drnas":"ATLAS2","atlas1":"ATLAS1","atlas2":"ATLAS2"}.get(arm)
    if marker:
        m=re.search(r"^"+marker+r"_TRIAL (.*)$",stdout,re.M)
        if status!="UNKNOWN":assert m,("Missing telemetry",arm,status)
        if m:telemetry=dict(x.split("=",1) for x in m.group(1).split() if "=" in x)
    if arm=="atlas2" and telemetry:
        d=telemetry
        assert d["decision"] in ("commit","sleep","fallback"),d
        assert int(d["modules"])<=32,d
        assert int(d["removed"])<=32*24,d
        assert int(d["final_clauses"])==int(d["original_clauses"])-int(d["removed"])+int(d["added"]),d
        if d["decision"]=="commit":
            assert int(d["modules"])>0 and int(d["saved_literals"])>0,d
        if rep==0:
            print("ATLAS2_ROUTE "+json.dumps(dict(family=FAMILY,cohort=COHORT,**d),sort_keys=True),flush=True)
            (OUT/"route_decision.json").write_text(json.dumps(d,sort_keys=True,indent=2))
    return dict(arm=arm,rep=rep,status=status,
        E2E_s=round(elapsed,6),PAR2_s=round(elapsed if status!="UNKNOWN" else 2*CAP,6),
        SAT_original_verified=(status=="SAT"),UNSAT_independent_LRAT=False,
        telemetry=telemetry)

rows=[]
for rep in range(REPEATS):
    # Rotate execution order to reduce ordering noise.
    order=ARMS[rep:]+ARMS[:rep]
    for arm in order:
        row=run(arm,rep)
        rows.append(row)
        print("ATLAS2_TRIAL "+json.dumps(row,sort_keys=True),flush=True)
summary={arm:dict(
    solved=sum(r["status"]=="SAT" for r in rows if r["arm"]==arm),
    PAR2_s=round(sum(r["PAR2_s"] for r in rows if r["arm"]==arm),6),
    trials=REPEATS) for arm in ARMS}
audit=dict(protocol=manifest["protocol"],source=manifest,
    oneCPU=True,rows=rows,summary=summary)
(OUT/"audit.json").write_text(json.dumps(audit,indent=2,sort_keys=True))
print("ATLAS2_FINAL "+json.dumps(dict(family=FAMILY,cohort=COHORT,
    sha256=manifest["source_sha256"],summary=summary),sort_keys=True),flush=True)
