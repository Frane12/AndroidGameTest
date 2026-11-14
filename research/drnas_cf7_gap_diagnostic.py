#!/usr/bin/env python3
"""Focused retrospective gap diagnosis: #12 XOR, #13 miter, #82 FRB.
Equal input, one CPU, one process at a time, E2E wall and proof checks.
No solver source alterations, no holdout claims or promotion.
"""
import collections, hashlib, json, os, pathlib, random, resource, signal, subprocess, tempfile, time
import drnas_clause_cf7_real100 as CF
IDS=(12,13,82)
ARMS=CF.ARMS
CAPS=(8.0,20.0)
OUT=pathlib.Path("cf7_gap")
def emit(key,item):print(key+" "+json.dumps(item,sort_keys=True),flush=True)
def run(source,arm,cap,rep):
    cnf=pathlib.Path(source["path"]);assert CF.sha(cnf.read_bytes())==source["sha256"]
    with tempfile.TemporaryDirectory() as d:
        proof=pathlib.Path(d)/"proof.drat"
        cmd=CF.command(arm,cnf,proof)
        if arm.startswith("CF"):
            ix=cmd.index("--time");cmd[ix+1]=str(cap)
            cmd.append("--stats")
        before=resource.getrusage(resource.RUSAGE_CHILDREN)
        t=time.perf_counter()
        p=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                           text=True,start_new_session=True,
                           preexec_fn=lambda:resource.setrlimit(resource.RLIMIT_FSIZE,(512*1024*1024,512*1024*1024)))
        killed=False
        try:stdout,stderr=p.communicate(timeout=cap+0.25)
        except subprocess.TimeoutExpired:
            killed=True;os.killpg(p.pid,signal.SIGKILL);stdout,stderr=p.communicate()
        wall=time.perf_counter()-t
        after=resource.getrusage(resource.RUSAGE_CHILDREN)
        cpu=after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime
        status="TIMEOUT" if killed else "UNKNOWN"
        valid=False;verify_s=0
        if not killed and p.returncode==10:
            valid=CF.DATA.sat_witness_valid(cnf,CF.DATA.nvars(cnf),stdout)
            if not valid:raise RuntimeError(("WRONG_SAT",source["id"],arm))
            status="SAT_VERIFIED"
        if not killed and p.returncode==20:
            status="UNSAT_UNVERIFIED"
            if proof.is_file() and proof.stat().st_size:
                c0=time.perf_counter()
                try:
                    check=subprocess.run([CF.CHECKER,str(cnf),str(proof)],capture_output=True,text=True,timeout=90)
                    valid=check.returncode==0 and "s VERIFIED" in check.stdout
                except subprocess.TimeoutExpired:pass
                verify_s=time.perf_counter()-c0
                if valid:status="UNSAT_CERTIFIED"
        if not killed and p.returncode not in (0,10,20,153):
            raise RuntimeError(("PROCESS_FAILURE",source["id"],arm,p.returncode,stderr[-500:]))
        stats={}
        for line in stderr.splitlines():
            for prefix in ("X41_STATS ","CLCF5_STATS ","CLCF6_STATS "):
                if line.startswith(prefix):
                    try:stats[prefix.strip()]=json.loads(line[len(prefix):])
                    except ValueError:pass
        row=dict(id=source["id"],arm=arm,cap_s=cap,rep=rep,
                 status=status,valid=valid,e2e_s=round(wall,6),cpu_s=round(cpu,6),
                 par2_verified_s=round(wall if valid and wall<=cap else 2*cap,6),
                 proof_size=proof.stat().st_size if proof.is_file() else 0,
                 verify_s=round(verify_s,6),
                 conflicts=stats.get("X41_STATS",{}).get("conflicts"),
                 decisions=stats.get("X41_STATS",{}).get("decisions"),
                 first_reduction=stats.get("CLCF5_STATS",{}),
                 swap=stats.get("CLCF6_STATS",{}))
        emit("GAP_TRIAL",row)
        return row
def main():
    CF.cpu_pin()
    manifest=CF.checked_manifest()
    sources=[s for s in manifest["sources"] if s["id"] in IDS]
    assert len(sources)==3
    OUT.mkdir(exist_ok=True)
    rows=[]
    for source in sources:
        data=source["path"];raw=pathlib.Path(data).read_bytes()
        parts=raw.splitlines()
        header=next(x.decode() for x in parts if x.startswith(b"p cnf "))
        emit("GAP_SOURCE",{"id":source["id"],"family":source["normalized_name_family"],
                           "sha256":source["sha256"],"bytes":len(raw),"header":header})
        for cap in CAPS:
            order=list(ARMS)
            random.Random(9081+source["id"]+int(cap)).shuffle(order)
            batch=[run(source,arm,cap,0) for arm in order]
            certified={r["status"] for r in batch if r["valid"]}
            assert len(certified)<=1
            rows.extend(batch)
    with (OUT/"trials.jsonl").open("w") as f:
        for r in rows:f.write(json.dumps(r,sort_keys=True)+"\n")
    result={"status":"COMPLETE","sources":list(IDS),"arms":list(ARMS),"caps":list(CAPS),
            "trials":len(rows),"blind_holdout":False,
            "proof_checked":True,"one_cpu":True,
            "focus":"First reduction vs branching/propagation gap, not a proof of cause"}
    (OUT/"summary.json").write_text(json.dumps(result,indent=2)+"\n")
    emit("GAP_FINAL",result)
if __name__=="__main__":main()
