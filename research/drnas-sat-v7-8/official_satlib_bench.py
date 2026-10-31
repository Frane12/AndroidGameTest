#!/usr/bin/env python3
"""Frozen SATLIB 225/250 benchmark: screen ONLY by bare CaDiCaL, then paired ablation."""
import csv,hashlib,io,json,os,random,statistics,subprocess,tarfile,time,urllib.request
from pathlib import Path

SHARD=int(os.getenv("SHARD","0"))
GROUPS=(
 ("uf225-960","SAT"),
 ("uuf225-960","UNSAT"),
 ("uf250-1065","SAT"),
 ("uuf250-1065","UNSAT"))
assert 0<=SHARD<4
GROUP,TRUTH=GROUPS[SHARD]
ROOT=Path("satlib-official-results")/("shard-"+str(SHARD))
ROOT.mkdir(parents=True,exist_ok=True)
CAP=4.0
SCREEN_CAP=3.0
MIDDLE_LOW=0.08
MIDDLE_HIGH=2.70
SCREEN_COUNT=20
FINAL_COUNT=6
REPEATS=3
MODES=("ca_plain","orig_v76","orig_v76_plain","v92_sparse","v92_structural")
VERSION="drnas-official-satlib-225-250-20261031-frozen-preselect-v1"
ORIGIN="https://www.cs.ubc.ca/~hoos/SATLIB/Benchmarks/SAT/RND3SAT/"
archive_url=ORIGIN+GROUP+".tar.gz"
archive=ROOT/(GROUP+".tar.gz")
if not archive.exists():
    # Pinned official SATLIB archive, with a 25MB hard transport bound and a timeout.
    with urllib.request.urlopen(urllib.request.Request(
            archive_url,headers={"User-Agent":"DRNAS SAT official benchmark research"}),
            timeout=25) as response,archive.open("wb") as dst:
        while True:
            chunk=response.read(1024*1024)
            if not chunk:break
            if dst.tell()+len(chunk)>25_000_000:
                raise RuntimeError("Official SATLIB archive exceeds transport cap")
            dst.write(chunk)
archive_sha=hashlib.sha256(archive.read_bytes()).hexdigest()
print("OFFICIAL_SOURCE",archive_url,"archive_sha256",archive_sha,flush=True)
members=[]
with tarfile.open(archive,"r:gz") as tg:
    for member in tg:
        if member.isfile() and member.name.lower().endswith(".cnf") and member.size<300_000:
            raw=tg.extractfile(member).read()
            if b"p cnf " in raw:
                members.append((member.name,raw))
print("FOUND_ORIGINAL_CNFS",GROUP,len(members),flush=True)
if len(members)<SCREEN_COUNT:raise RuntimeError("Insufficient official SATLIB CNFs in "+GROUP)
# Deterministic screening sample; no future method or label influences selection.
members=sorted(members,key=lambda x:hashlib.sha256(
    (VERSION+"|"+GROUP+"|"+x[0]).encode()).hexdigest())[:SCREEN_COUNT]

def original_to_dimacs(raw):
    # SATLIB files sometimes append a '%' end marker. Strip only that marker,
    # preserve every non-marker CNF line and SHA256 of original as provenance.
    out=[]
    for b in raw.splitlines():
        if b.strip().startswith(b"%"):break
        if b.strip().startswith(b"0") and len(b.strip())>1 and b"%" in b:
            b=b.split(b"%",1)[0]
        out.append(b)
    return b"\n".join(out)+b"\n"

cases=[]
for index,(name,raw) in enumerate(members):
    data=original_to_dimacs(raw)
    p=ROOT/(GROUP+"-src-"+str(index).zfill(2)+".cnf")
    p.write_bytes(data)
    cases.append(dict(name=GROUP+"-"+str(index).zfill(2),family=GROUP,
                      source_member=name,origin=archive_url,truth=TRUTH,
                      archive_sha256=archive_sha,original_sha256=hashlib.sha256(raw).hexdigest(),
                      sha256=hashlib.sha256(data).hexdigest(),cnf=str(p)))

def solve(case,mode,rep,timeout):
    path=Path(case["cnf"])
    if hashlib.sha256(path.read_bytes()).hexdigest()!=case["sha256"]:
        raise ValueError("CNF changed after hashing")
    seed=(20312+rep*7919+int(case["sha256"][:8],16))%(2**32)
    t=time.perf_counter()
    try:
        p=subprocess.run(["./v92_early_structural",mode,str(path),str(seed)],
               capture_output=True,text=True,timeout=timeout)
    except subprocess.TimeoutExpired:
        return dict(status="TIMEOUT",wall_s=timeout,seed=seed)
    wall=time.perf_counter()-t
    out=[line for line in p.stdout.splitlines() if line.startswith("DRNAS_CAUSAL\t")]
    if p.returncode!=0 or len(out)!=1:
        return dict(status="ERROR",wall_s=wall,seed=seed,error=(
          "RC="+str(p.returncode)+" STDERR="+p.stderr[-250:]+" OUTPUT="+p.stdout[-80:]))
    vals=dict(x.split("=",1) for x in out[0].split("\t")[1:])
    return dict(status=vals["answer"],wall_s=wall,seed=seed,
                **{k:vals.get(k,"") for k in ("hints","extended","second_budget",
                 "gate_reason","v92_choice","v92_static_us","learned_delta","threshold","active_256",
                 "first_budget","stage1","stage2","stage3")})
 
screen=[]
for case in cases:
    result=solve(case,"ca_plain",0,SCREEN_CAP)
    sec=result["wall_s"]
    valid=(result["status"]==TRUTH and MIDDLE_LOW<=sec<=MIDDLE_HIGH)
    screen.append(dict(**case,screen_time_s=sec,screen_status=result["status"],
                       screen_eligible=valid))
    print("SCREEN",case["name"],case["source_member"],result["status"],round(sec,4),
          "ELIGIBLE" if valid else "INELIGIBLE",flush=True)
(ROOT/"screen.json").write_text(json.dumps(screen,indent=2))
# Choose moderate cases ONLY if baseline (unhinted CaDiCaL) is in the
# predeclared time range. If fewer than FINAL_COUNT, use ALL eligible,
# rather than adding easy/hard cases that violate the user's requirement.
selected=sorted((x for x in screen if x["screen_eligible"]),
                key=lambda x:abs(x["screen_time_s"]-.6))[:FINAL_COUNT]
manifest=dict(version=VERSION,source=ORIGIN,archive=archive_url,
              archive_sha256=archive_sha,cap_s=CAP,screen_cap_s=SCREEN_CAP,
              middle_low_s=MIDDLE_LOW,middle_high_s=MIDDLE_HIGH,
              screen_count=SCREEN_COUNT,final_count=FINAL_COUNT,
              repeats=REPEATS,modes=MODES,group=GROUP,truth=TRUTH,cases=selected)
(ROOT/"manifest.json").write_text(json.dumps(manifest,indent=2))
if not selected:
    print("NO_MEDIUM_INSTANCES",GROUP,"No final solves on this group.",flush=True)
    exit(0)
fields=("case","family","status","truth","mode","repeat","wall_s","sha256",
        "seed","error","hints","extended","second_budget","gate_reason",
        "v92_choice","v92_static_us","learned_delta","threshold","active_256",
        "first_budget","stage1","stage2","stage3")
rows=[]
with (ROOT/"raw.csv").open("w",newline="") as file:
    writer=csv.DictWriter(file,fieldnames=fields)
    writer.writeheader()
    for case in selected:
        for rep in range(REPEATS):
            order=list(MODES)
            random.Random(int(case["sha256"][:12],16)+rep).shuffle(order)
            for mode in order:
                r=solve(case,mode,rep,CAP)
                rec=dict(case=case["name"],family=GROUP,truth=TRUTH,
                         mode=mode,repeat=rep,sha256=case["sha256"],**r)
                rows.append(rec);writer.writerow(rec);file.flush()
                print("SATLIB",GROUP,case["name"],rep,mode,r["status"],
                      "%.5f"%r["wall_s"],flush=True)
    if len(rows)!=len(selected)*REPEATS*len(MODES):
        raise RuntimeError("Missing benchmark row")
for case in selected:
    subset=[x for x in rows if x["case"]==case["name"]]
    outcomes={x["status"] for x in subset if x["status"] in ("SAT","UNSAT")}
    if outcomes!={TRUTH}:
        raise RuntimeError("Official SATLIB answer contradiction "+case["name"]+" "+str(outcomes))
    if any(x["status"]=="ERROR" for x in subset):
        raise RuntimeError("Solver error on "+case["name"])
print("FINAL_SELECTED",GROUP,len(selected),"RUNS",len(rows),flush=True)
