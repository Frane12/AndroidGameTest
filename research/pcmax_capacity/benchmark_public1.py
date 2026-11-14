#!/usr/bin/env python3
"""Unseen PUBLIC P||Cmax job inputs -> native DRNAS capacity guard.

Inputs and proven optimal makespans: immutable upstream Git commit, not SAT2024
original20 and not randomly generated tasks. Translating task data to CNF is
local (tested BDD scheduling encoding); resulting CNFs are not claimed to be
published original competition formulas.

For every source job vector, independently check feasibility at the published
optimum (SAT control), infeasibility at optimum-1 (UNSAT test), then time the
unchanged native capacity guard and independently check every structural proof.
Results are immutable artifacts, verified separately on each source CNF.
"""
import argparse
import hashlib
import json
from pathlib import Path
import os
import subprocess
import sys
import time
import urllib.request
from functools import lru_cache

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/"research/pcmax_capacity/tests"))
from make_fixtures import build_scheduling

UPSTREAM = "https://github.com/anon495351/pcmax"
UPSTREAM_COMMIT = "7ce7488b8f5cb5006448945ae56faec45c2c10fe"
SOURCE_FILE_LIST = [
    ("frangioni", "NU_1_0010_05_0.txt"),
    ("frangioni", "NU_1_0010_05_1.txt"),
    ("frangioni", "NU_1_0010_05_2.txt"),
    ("frangioni", "NU_1_0010_05_3.txt"),
    ("huebner", "p_cmax-n10-m3-jobsample-raxml-webserver-secs--m=3--10-2.txt"),
    ("huebner", "p_cmax-n10-m3-jobsample-raxml-webserver-secs--m=3--10-8.txt"),
    ("huebner", "p_cmax-n12-m3-jobsample-raxml-webserver-secs--m=3--12-1.txt"),
    ("huebner", "p_cmax-n12-m4-jobsample-raxml-webserver-secs--m=4--12-8.txt"),
    ("laupichler", "p_cmax-n10-m3-jobsample-Berlin-1pct_KaRRi-IND_0_0_0_0_w600_r0.csv-cleared--m=3--10-1.txt"),
    ("laupichler", "p_cmax-n10-m3-jobsample-Berlin-1pct_KaRRi-IND_0_0_0_0_w600_r0.csv-cleared--m=3--10-2.txt"),
    ("lehmann", "p_cmax-n10-m3-jobsample-rawtimes-sichash-100Mkeys-easy--m=3--10-1.txt"),
    ("lehmann", "p_cmax-n10-m3-jobsample-rawtimes-sichash-100Mkeys-hard--m=3--10-1.txt"),
    ("planted", "p_cmax-n10-m4-planted-exact-U100-perturb0.txt"),
    ("planted", "p_cmax-n10-m4-planted-exact-U300-perturb0.05.txt"),
]

def retrieve(path):
    url = ("https://raw.githubusercontent.com/anon495351/pcmax/"
           + UPSTREAM_COMMIT + "/" + path)
    error = None
    for k in range(3):
        try:
            req = urllib.request.Request(url,headers={"User-Agent":"DRNAS-PCMAX-Independent-Public-Audit/1.0"})
            with urllib.request.urlopen(req, timeout=35) as resp:
                content = resp.read(500000)
            assert len(content) < 500000, "oversize public source"
            return content,url
        except Exception as e:
            error=e
            time.sleep(k+1)
    raise RuntimeError(f"Cannot retrieve {path}: {error}")

def parse_source(source):
    lines=[l.strip() for l in source.decode("ascii").splitlines() if l.strip()]
    assert len(lines) == 2 and lines[0].startswith("p p_cmax "),lines[:2]
    header = lines[0].split()
    assert len(header)==4, header
    n,m=map(int, header[2:])
    nums=list(map(int,lines[1].split()))
    assert nums[-1]==0 and len(nums)==n+1
    assert 1<=n<=16 and 2<=m<=6
    assert all(x>0 for x in nums[:-1])
    return nums[:-1],m

def independent_schedule(jobs,m,bound):
    """Exact branch-and-bound with assignment witness, symmetric load memo."""
    ordered=sorted(enumerate(jobs),key=lambda z:-z[1])
    if max(jobs)>bound or sum(jobs)>m*bound:
        return None,0
    loads=[0]*m
    assign=[None]*len(jobs)
    failed=set()
    visits=0
    def dfs(idx):
        nonlocal visits
        visits+=1
        if idx==len(ordered): return True
        key=(idx,tuple(sorted(loads)))
        if key in failed: return False
        job_id,weight=ordered[idx]
        seen=set()
        for machine,old in enumerate(loads):
            if old in seen: continue
            seen.add(old)
            if old+weight>bound: continue
            loads[machine]+=weight
            assign[job_id]=machine
            if dfs(idx+1):return True
            loads[machine]=old
            assign[job_id]=None
        failed.add(key)
        return False
    feasible=dfs(0)
    if feasible:
        assert all(sum(jobs[i] for i,x in enumerate(assign) if x==j)<=bound for j in range(m))
    return (assign if feasible else None),visits

def run_cmd(cmd,hard_limit):
    t=time.perf_counter()
    try:
        p=subprocess.run(cmd,capture_output=True,text=True,timeout=hard_limit,check=False)
        return dict(returncode=p.returncode,seconds=time.perf_counter()-t,
                    stdout=p.stdout,stderr=p.stderr,timeout=False)
    except subprocess.TimeoutExpired:
        return dict(returncode=None,seconds=time.perf_counter()-t,
                    stdout="",stderr="hard timeout",timeout=True)

def write_cnf(path,jobs,m,bound,public_sha):
    nv,clauses,groups,graphs=build_scheduling(jobs,m,bound)
    raw=(f"c public P||Cmax source SHA256 {public_sha}\n"+
         f"c local BDD scheduling reduction limit {bound}\n"+
         f"p cnf {nv} {len(clauses)}\n"+
         "".join(" ".join(map(str,c))+" 0\n" for c in clauses)).encode("ascii")
    assert len(raw)<80_000_000
    path.write_bytes(raw)
    return dict(sha256=hashlib.sha256(raw).hexdigest(),
                variables=nv,clauses=len(clauses),bytes=len(raw))

def load_inputs(base):
    original=base/"public-original"
    original.mkdir()
    opts={}
    for family,_ in SOURCE_FILE_LIST:
        if family not in opts:
            data,url=retrieve(f"benchmarks/opt-known-instances-{family}.txt")
            (original/f"{family}-published-optima.txt").write_bytes(data)
            opts[family]=dict(line.strip().split() for line in data.decode().splitlines() if line.strip())
    cases=[]
    for index,(family,filename) in enumerate(SOURCE_FILE_LIST):
        source_path=f"benchmarks/{family}/{filename}"
        raw,url=retrieve(source_path)
        original_file=original/f"source-{index:02d}.txt"
        original_file.write_bytes(raw)
        jobs,m=parse_source(raw)
        optimum=int(opts[family][filename])
        assert max(jobs)<=optimum<=sum(jobs), (source_path,optimum)
        # Independently verify both a feasible optimum and the lack of any
        # feasible schedule one unit below. No native module participates.
        t=time.perf_counter()
        witness,sat_visits=independent_schedule(jobs,m,optimum)
        _,unsat_visits=independent_schedule(jobs,m,optimum-1)
        unsat_witness,extra=independent_schedule(jobs,m,optimum-1)
        oracle_s=time.perf_counter()-t
        assert witness is not None, "published optimum must be feasible"
        assert unsat_witness is None,"published optimum is not actually optimal"
        src_sha=hashlib.sha256(raw).hexdigest()
        cases.append(dict(index=index,family=family,filename=filename,
                          upstream_source=source_path,upstream_raw_url=url,
                          upstream_sha256=src_sha,original_file=str(original_file),
                          source_jobs=jobs,job_count=len(jobs),machines=m,
                          published_optimum=optimum,independent_oracle_s=round(oracle_s,5),
                          sat_oracle_visits=sat_visits,unsat_oracle_visits=unsat_visits,
                          sat_witness_machine_indices=witness))
        print("PUBLIC_SOURCE_ORACLE "+json.dumps({k:cases[-1][k] for k in
              ("index","family","job_count","machines","published_optimum",
               "sat_oracle_visits","unsat_oracle_visits","independent_oracle_s")}),flush=True)
    return cases

def main():
    a=argparse.ArgumentParser()
    a.add_argument("--binary",type=Path,required=True)
    a.add_argument("--output",type=Path,required=True)
    a.add_argument("--budget-ms",type=int,default=3000)
    a.add_argument("--repetitions",type=int,default=2)
    args=a.parse_args()
    assert 200<=args.budget_ms<=10000 and args.repetitions in (1,2,3)
    cpu=min(os.sched_getaffinity(0))
    os.sched_setaffinity(0,{cpu})
    args.output.mkdir(parents=True,exist_ok=False)
    cases=load_inputs(args.output)
    cnfs=args.output/"cnfs"
    cnfs.mkdir()
    checker=ROOT/"research/pcmax_capacity/check_capacity.py"
    assert checker.is_file()
    for case in cases:
        case["formulas"]={}
        for expected,limit in (("UNSAT",case["published_optimum"]-1),
                               ("SAT",case["published_optimum"])):
            name=f"public-{case['index']:02d}-{case['family']}-{expected.lower()}-C{limit}.cnf"
            info=write_cnf(cnfs/name,case["source_jobs"],case["machines"],limit,
                           case["upstream_sha256"])
            case["formulas"][expected]=dict(name=name,bound=limit,**info)
    # This manifest is frozen before invoking the native module.
    (args.output/"frozen_manifest.json").write_text(json.dumps(dict(
        upstream_repo=UPSTREAM,upstream_commit=UPSTREAM_COMMIT,
        public_job_inputs=len(cases),source_count=len(cases)*2,
        solver_binary_sha256=hashlib.sha256(args.binary.read_bytes()).hexdigest(),
        independent_checker_sha256=hashlib.sha256(checker.read_bytes()).hexdigest(),
        trials_per_case=args.repetitions, cases=cases),indent=2)+"\n")
    rows=[]
    with (args.output/"trials.jsonl").open("w") as log:
        for rep in range(args.repetitions):
            sequence=list(cases if rep%2==0 else reversed(cases))
            for case in sequence:
                for expected in ("UNSAT","SAT"):
                    f=case["formulas"][expected]
                    path=cnfs/f["name"]
                    assert hashlib.sha256(path.read_bytes()).hexdigest()==f["sha256"]
                    cert=args.output/f"cert-{case['index']:02d}-{expected}-r{rep}.json"
                    native=run_cmd([str(args.binary.resolve()),str(path.resolve()),
                      "--mode","core","--time",str(args.budget_ms/1000+2),
                      "--pcmax-only","--pcmax-budget-ms",str(args.budget_ms),
                      "--pcmax-certificate",str(cert.resolve())],
                      hard_limit=args.budget_ms/1000+8)
                    records=[json.loads(x[len("c PCMAX_CAPACITY "):])
                             for x in native["stdout"].splitlines()
                             if x.startswith("c PCMAX_CAPACITY ")]
                    row=dict(index=case["index"],family=case["family"],
                             source_sha256=case["upstream_sha256"],
                             cnf_sha256=f["sha256"],expected=expected,
                             optimum=case["published_optimum"],bound=f["bound"],
                             rep=rep, status="UNKNOWN",verified=False,
                             native_s=round(native["seconds"],6),
                             native_rc=native["returncode"],
                             telemetry=records[-1] if records else None)
                    if native["returncode"]==20 and "s UNSATISFIABLE" in native["stdout"]:
                        assert cert.is_file()
                        checked=run_cmd([sys.executable,str(checker.resolve()),
                                         str(path.resolve()),str(cert.resolve())],hard_limit=45)
                        assert checked["returncode"]==0,(row,checked)
                        verdict=json.loads(checked["stdout"])
                        assert verdict["status"]=="UNSAT_STRUCTURAL_CERTIFICATE_VERIFIED"
                        assert expected=="UNSAT","false positive for publicly optimal SAT bound"
                        row.update(status="UNSAT_VERIFIED",verified=True,
                                   demand=verdict["required"],capacity_sum=verdict["capacity_sum"],
                                   checker_s=round(checked["seconds"],6),
                                   total_s=round(native["seconds"]+checked["seconds"],6))
                    else:
                        assert native["returncode"]==0 and "s UNKNOWN" in native["stdout"],(row,native)
                        assert not cert.exists()
                        row["total_s"]=row["native_s"]
                    rows.append(row)
                    log.write(json.dumps(row,sort_keys=True)+"\n")
                    log.flush()
                    print("PCMAX_PUBLIC_TRIAL "+json.dumps({k:row[k] for k in
                          ("index","family","expected","bound","rep","status","native_s","total_s")}),flush=True)
    summary=dict(kind="PUBLIC_SOURCE_TASKS_LOCAL_BDD_CNF",upstream=UPSTREAM,
       upstream_commit=UPSTREAM_COMMIT,unique_original_public_job_inputs=len(cases),
       generated_cnf_formulas=len(cases)*2,unsat_formulas=len(cases),
       sat_control_formulas=len(cases),logical_cpu=cpu,
       solver_binary_sha256=hashlib.sha256(args.binary.read_bytes()).hexdigest(),
       checker_sha256=hashlib.sha256(checker.read_bytes()).hexdigest(),
       repetitions=args.repetitions,capacity_budget_ms=args.budget_ms,
       independently_verified_unsat_trials=sum(r["verified"] for r in rows),
       false_unsat_on_sat_controls=sum(r["expected"]=="SAT" and r["verified"] for r in rows),
       rows=rows)
    (args.output/"summary.json").write_text(json.dumps(summary,indent=2)+"\n")
    print("PCMAX_PUBLIC_SUMMARY "+json.dumps({k:summary[k] for k in
          ("unique_original_public_job_inputs","generated_cnf_formulas",
           "independently_verified_unsat_trials","false_unsat_on_sat_controls",
           "repetitions")}),flush=True)

if __name__=="__main__":
    main()
