#!/usr/bin/env python3
"""FACTOR6: 4 pinned SATLIB family picks; original clause-preserving DIMACS
normalization, one CPU, matched A/C/D/Kissat/CMS end-to-end comparison.
Not SAT Competition 2024. UNSAT solver claims are not independently certified.
"""
import argparse
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

from drnas_factor6_dimacs import canonical_dimacs,witness_ok

OUT=pathlib.Path("mre_factor6")
OUT.mkdir(exist_ok=True)
MANIFEST="research/drnas-sat-v7-4/frozen_real_medium.json"
FAMILIES=("uf250-1065","uuf250-1065","flat200-479","planning-logistics")
ARMS=("drnas_plain","drnas_factor4","drnas_gateD","kissat","cms")
CAP=int(os.environ.get("FACTOR6_CAP", "10"))
BIN=OUT/"bin"

def selftest():
    example=b"  c introductory comment\n c p edge misleading comment\np cnf 3 2\n1 -2 0\n 3 0\n%\n0\n"
    canon,header,clauses=canonical_dimacs(example)
    assert header==(3,2) and canon==b"p cnf 3 2\n1 -2 0\n3 0\n"
    assert witness_ok(clauses,"s SATISFIABLE\nv 1 -2 3 0\n")
    for bad in (b"p cnf 2 2\n1 0\n",b"p cnf 2 1\n3 0\n",
                b"p cnf 2 1\n1 0\nBAD",b"p cnf 2 1\n1 0\n-1 0\n"):
        try:canonical_dimacs(bad)
        except ValueError:pass
        else:raise AssertionError("invalid CNF accepted: "+repr(bad))
    # Prove we can enter exact structure mode D on an elementary 1-cut.
    clauses=["1 "+str(v)+" 0" for v in range(2,13)]+["-1 -"+str(v)+" 0" for v in range(2,13)]
    sample=OUT/"selftest_structural.cnf"
    sample.write_text("p cnf 12 22\n"+"\n".join(clauses)+"\n")
    if (BIN/"drnas_factor4").exists():
        result=run(sample,[tuple(int(w) for w in line.split()[:-1]) for line in clauses],"drnas_gateD",2)
        assert result["status"]=="SAT" and result["SAT_original_witness_verified"],result
        assert int(result["telemetry"].get("probes",0))>0,result
    print("FACTOR6_SELFTEST_PASS",flush=True)

def sources():
    manifest=json.loads(pathlib.Path(MANIFEST).read_text())
    result=[]
    for i,family in enumerate(FAMILIES):
        entry=next(x for x in manifest["archives"] if x["set"]==family)
        with urllib.request.urlopen(entry["url"],timeout=60) as response:
            raw_archive=response.read(12_000_001)
        if len(raw_archive)>12_000_000:raise RuntimeError("archive exceeds precommitted size cap")
        if hashlib.sha256(raw_archive).hexdigest()!=entry["archive_sha256"]:
            raise RuntimeError("pinned archive SHA mismatch: "+family)
        with tarfile.open(fileobj=io.BytesIO(raw_archive),mode="r:gz") as tf:
            items=sorted((x for x in tf.getmembers() if x.isfile() and x.name.lower().endswith(".cnf")),
                key=lambda x:hashlib.sha256((family+"|"+pathlib.PurePosixPath(x.name).name).encode()).hexdigest())
            if not items:raise RuntimeError("no CNF files in "+family)
            member=items[2 if len(items)>2 else 0]
            original=tf.extractfile(member).read()
        normalized,header,clauses=canonical_dimacs(original)
        path=OUT/f"source_{i}.cnf"
        path.write_bytes(normalized)
        result.append(dict(id=i,family=family,entry=member.name,
            archive_url=entry["url"],archive_sha256=entry["archive_sha256"],
            original_sha256=hashlib.sha256(original).hexdigest(),
            normalized_sha256=hashlib.sha256(normalized).hexdigest(),
            normalization="discard comments/whitespace/legacy percent terminator only; strict clause/header validation",
            vars=header[0],clauses=header[1],original_bytes=len(original),
            normalized_bytes=len(normalized),_parsed_clauses=clauses))
    return result

def run(path,clauses,arm,cap):
    if arm=="drnas_plain":args=[str(BIN/"drnas_factor4"),str(path),"--mode","A","--time",str(cap)]
    elif arm=="drnas_factor4":args=[str(BIN/"drnas_factor4"),str(path),"--mode","C","--time",str(cap)]
    elif arm=="drnas_gateD":args=[str(BIN/"drnas_factor4"),str(path),"--mode","D","--time",str(cap)]
    elif arm=="kissat":args=[str(BIN/"kissat"),str(path)]
    elif arm=="cms":args=[str(BIN/"cryptominisat5"),"--verb","0",str(path)]
    else:raise ValueError(arm)
    def limit():
        resource.setrlimit(resource.RLIMIT_CPU,(cap,cap+1))
        resource.setrlimit(resource.RLIMIT_AS,(4*1024**3,4*1024**3))
    start=time.monotonic()
    try:
        p=subprocess.run(args,capture_output=True,text=True,timeout=cap+3,preexec_fn=limit)
        stdout,stderr,code=p.stdout,p.stderr,p.returncode
    except subprocess.TimeoutExpired as exc:
        stdout=exc.stdout.decode("utf-8","replace") if isinstance(exc.stdout,bytes) else (exc.stdout or "")
        stderr=exc.stderr.decode("utf-8","replace") if isinstance(exc.stderr,bytes) else (exc.stderr or "")
        code=124
    elapsed=time.monotonic()-start
    # Reject parse errors, missing binaries and crashes rather than scoring as timeouts.
    if code not in (0,10,20,124,-24,-9):
        raise RuntimeError(f"{arm} abnormal exit {code}: {stderr[-600:]}")
    if code==-9 and elapsed < cap*0.75:
        raise RuntimeError(f"{arm} killed early: {stderr[-600:]}")
    status={10:"SAT",20:"UNSAT"}.get(code,"UNKNOWN")
    verified=None
    if status=="SAT":
        verified=witness_ok(clauses,stdout)
        if not verified:raise RuntimeError(f"unverified SAT {arm} {path}")
    telemetry={}
    match=re.search(r"^FACTOR2_TRIAL (.*)$",stdout,re.M)
    if match:
        telemetry=dict(x.split("=",1) for x in match.group(1).split() if "=" in x)
    return dict(arm=arm,status=status,E2E_s=round(elapsed,6),
        PAR2_s=round(elapsed if status!="UNKNOWN" else cap*2,6),
        SAT_original_witness_verified=verified,UNSAT_independent_LRAT=False,
        returncode=code,telemetry=telemetry,stderr_tail=stderr[-250:])

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--selftest-only",action="store_true")
    args=parser.parse_args()
    selftest()
    if args.selftest_only:return
    data=sources()
    public=[{k:v for k,v in s.items() if not k.startswith("_")} for s in data]
    (OUT/"sources.json").write_text(json.dumps(public,indent=2))
    print("FACTOR6_SOURCES "+json.dumps(public,sort_keys=True),flush=True)
    rows=[]
    for s in data:
        for arm in ARMS:
            row=dict(source_id=s["id"],sha256=s["normalized_sha256"],
                **run(OUT/f"source_{s['id']}.cnf",s["_parsed_clauses"],arm,CAP))
            rows.append(row)
            print("FACTOR6_TRIAL "+json.dumps(row,sort_keys=True),flush=True)
        outcomes={r["status"] for r in rows if r["source_id"]==s["id"] and r["status"]!="UNKNOWN"}
        if len(outcomes)>1:raise RuntimeError("SAT/UNSAT disagreement source "+str(s["id"]))
    summary={arm:dict(solved=sum(r["status"]!="UNKNOWN" for r in rows if r["arm"]==arm),
        PAR2_s=round(sum(r["PAR2_s"] for r in rows if r["arm"]==arm),6),
        E2E_s=round(sum(r["E2E_s"] for r in rows if r["arm"]==arm),6))
        for arm in ARMS}
    audit=dict(protocol="FACTOR6-4-PINNED-SATLIB-5-ARMS-ONECPU",
        cap_cpu_s=CAP,PAR2_timeout_penalty_s=2*CAP,repeat_count=1,
        not_SAT_competition=True,UNSAT_independent_LRAT=False,
        source=public,summary=summary,rows=rows)
    (OUT/"audit.json").write_text(json.dumps(audit,indent=2,sort_keys=True))
    print("FACTOR6_FINAL "+json.dumps({k:v for k,v in audit.items() if k not in ("rows","source")},sort_keys=True),flush=True)

if __name__=="__main__":main()
