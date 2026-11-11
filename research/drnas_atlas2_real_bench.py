#!/usr/bin/env python3
"""Independent REAL HWMCC 2024 miter CNFs (not generated ATLAS2 fixtures).
Source pins: public Tractables/cnfs, SHA-frozen July 31 2026 commit,
per-file exact Git blob SHA-1 verified before decompression.
UNSAT outcomes are NOT independently LRAT-certified: do not count as solved.
"""
import hashlib,json,lzma,os,pathlib,re,resource,subprocess,time,urllib.request
OUT=pathlib.Path("mre_atlas2_real");OUT.mkdir(exist_ok=True)
SHARD=int(os.environ.get("MICRO_SHARD","0"));assert 0<=SHARD<4
COMMIT="de4731f68e5a5bb6629269b3be1d19b44e812763"
FILES=(
 ("analog_estimation_convergence_unsafe.cnf.xz","e94f60e0434f7c7befca232135164daa7f4470a7"),
 ("93.c.cnf.xz","eecc8e9b396b5ee1f140ebfdb574ddd81c0492d2"),
 ("bin-suffix-5.cnf.xz","85fca82d7a45208e6b038db22199fdb213da8b80"),
 ("benchmark04_conjunctive.cnf.xz","7898baf5070b43806a0ce07ec498dab81a41af86"),
)
name,pinned_blob=FILES[SHARD]
url=f"https://raw.githubusercontent.com/Tractables/cnfs/{COMMIT}/hwmcc/{name}"
with urllib.request.urlopen(url,timeout=60) as request:
    comp=request.read(350_001)
assert len(comp)<=350000,("compressed source unexpectedly oversized",name)
blob=hashlib.sha1(b"blob "+str(len(comp)).encode()+b"\x00"+comp).hexdigest()
assert blob==pinned_blob,(name,blob,pinned_blob)
data=lzma.decompress(comp)
assert len(data)<=8_000_000,(name,len(data))
path=OUT/"original.cnf";path.write_bytes(data)
header=None;clauses=[];current=[]
for ln in data.decode("ascii").splitlines():
    ln=ln.strip()
    if not ln or ln.startswith("c"):continue
    if ln.startswith("%"):break
    if ln.startswith("p "):
        p=ln.split();assert len(p)==4 and p[1]=="cnf" and header is None,p
        header=(int(p[2]),int(p[3]));continue
    assert header is not None
    for tok in ln.split():
        lit=int(tok)
        if lit==0:
            clauses.append(current);current=[]
        else:
            assert abs(lit)<=header[0]
            current.append(lit)
assert header is not None and len(clauses)==header[1] and not current,(name,header,len(clauses))
VARS=header[0];CAP=15;REPS=2
src=dict(file=name,source_commit=COMMIT,git_blob_sha1=blob,
    decompressed_sha256=hashlib.sha256(data).hexdigest(),bytes=len(data),
    vars=VARS,clauses=len(clauses),cap_s=CAP,repeats=REPS,
    protocol="independent_real_HWMCC24_original_source_sha_UNSAT_unverified")
(OUT/"source.json").write_text(json.dumps(src,indent=2,sort_keys=True))
print("ATLAS2_REAL_SOURCE "+json.dumps(src,sort_keys=True),flush=True)
def verified_model(stdout):
    assigned={}
    for line in stdout.splitlines():
        if line.startswith("v "):
            for token in line.split()[1:]:
                lit=int(token)
                if lit==0:continue
                if abs(lit)>VARS:return False
                assigned[abs(lit)]=lit>0
    if len(assigned)!=VARS:return False
    return all(any(assigned[abs(lit)]==(lit>0) for lit in clause) for clause in clauses)

def run(arm,rep):
    binaries={"drnas":"drnas_atlas2","atlas1":"drnas_atlas1",
              "atlas2":"drnas_atlas2","kissat":"kissat","cadical":"cadical"}
    command=[str((OUT/"bin"/binaries[arm]).resolve()),str(path.resolve())]
    if arm in ("drnas","atlas1","atlas2"):
        command+=["--mode",{"drnas":"A","atlas1":"ATLAS1","atlas2":"ATLAS2"}[arm],"--time",str(CAP)]
    def limits():
        resource.setrlimit(resource.RLIMIT_CPU,(CAP,CAP+1))
        resource.setrlimit(resource.RLIMIT_AS,(4*1024**3,4*1024**3))
    begin=time.monotonic()
    try:
        p=subprocess.run(command,text=True,capture_output=True,timeout=CAP+2,preexec_fn=limits)
        code,stdout,stderr=p.returncode,p.stdout,p.stderr
    except subprocess.TimeoutExpired:
        code,stdout,stderr=124,"","timeout"
    elapsed=time.monotonic()-begin
    raw_status={10:"SAT",20:"UNSAT"}.get(code,"UNKNOWN")
    if raw_status=="SAT":
        assert verified_model(stdout),(name,arm,"invalid ORIGINAL SAT witness",stderr[-500:])
        status="SAT_VERIFIED"
    elif raw_status=="UNSAT":
        # Do not infer independent UNSAT correctness from two solvers agreeing.
        status="UNSAT_UNVERIFIED"
    elif code in (0,124,-9,-24):
        status="UNKNOWN"
    else:
        raise RuntimeError((name,arm,code,stderr[-1000:]))
    telemetry={}
    if arm in ("drnas","atlas1","atlas2"):
        marker="ATLAS1" if arm=="atlas1" else "ATLAS2"
        m=re.search(r"^"+marker+r"_TRIAL (.*)$",stdout,re.M)
        if m:telemetry=dict(x.split("=",1) for x in m.group(1).split() if "=" in x)
    if arm=="atlas2" and rep==0 and telemetry:
        print("ATLAS2_REAL_ROUTE "+json.dumps(dict(name=name,**telemetry),sort_keys=True),flush=True)
    return dict(arm=arm,rep=rep,raw_status=raw_status,status=status,
        E2E_s=round(elapsed,6),
        PAR2_s=round(elapsed if status=="SAT_VERIFIED" else 2*CAP,6),
        SAT_original_verified=(status=="SAT_VERIFIED"),
        UNSAT_independent_LRAT=False,telemetry=telemetry)

ARMS=("drnas","atlas1","atlas2","kissat","cadical")
rows=[]
for rep in range(REPS):
    for arm in ARMS[rep:]+ARMS[:rep]:
        row=run(arm,rep);rows.append(row)
        print("ATLAS2_REAL_TRIAL "+json.dumps(row,sort_keys=True),flush=True)
summary={arm:dict(
    sat_verified=sum(r["status"]=="SAT_VERIFIED" for r in rows if r["arm"]==arm),
    unsat_unverified=sum(r["status"]=="UNSAT_UNVERIFIED" for r in rows if r["arm"]==arm),
    unknown=sum(r["status"]=="UNKNOWN" for r in rows if r["arm"]==arm),
    PAR2_s=round(sum(r["PAR2_s"] for r in rows if r["arm"]==arm),6)
 ) for arm in ARMS}
(OUT/"audit.json").write_text(json.dumps(dict(source=src,rows=rows,summary=summary),indent=2,sort_keys=True))
print("ATLAS2_REAL_FINAL "+json.dumps(dict(file=name,summary=summary),sort_keys=True),flush=True)
