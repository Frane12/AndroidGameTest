#!/usr/bin/env python3
"""PRE-GUARD13: isolated read-only instrumentation against frozen CF7 and Kissat."""
import hashlib,json,os,pathlib,resource,signal,subprocess,tempfile,time
import drnas_clause_cf7_real100 as CF
def emit(t,r):print(t+" "+json.dumps(r,sort_keys=True),flush=True)
def run(src,arm,cap):
    cnf=pathlib.Path(src["path"]);assert CF.sha(cnf.read_bytes())==src["sha256"]
    with tempfile.TemporaryDirectory() as tmp:
        proof=pathlib.Path(tmp)/"proof.drat"
        if arm=="SHADOW":
            cmd=["build/drnas-preguard-shadow13",str(cnf),"--mode","core","--time",str(cap),
                 "--stats","--x5-no-minimize","--x5-no-retain","--proof",str(proof),"--cf5-policy","B2L_32"]
        elif arm=="FROZEN":
            cmd=["build/drnas-clause-cf6",str(cnf),"--mode","core","--time",str(cap),
                 "--stats","--x5-no-minimize","--x5-no-retain","--proof",str(proof),"--cf5-policy","B2L_32"]
        else:
            cmd=["build/kissat",str(cnf),str(proof)]
            if arm=="KISSAT_NO_PREPROCESS":cmd.insert(1,"--no-preprocess")
        t=time.perf_counter()
        p=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True,
                           preexec_fn=lambda:resource.setrlimit(resource.RLIMIT_FSIZE,(512*1024*1024,512*1024*1024)))
        timed=False
        try:stdout,stderr=p.communicate(timeout=cap+0.25)
        except subprocess.TimeoutExpired:
            timed=True;os.killpg(p.pid,signal.SIGKILL);stdout,stderr=p.communicate()
        wall=time.perf_counter()-t
        if not timed and p.returncode not in (0,10,20,153):raise RuntimeError(("SOLVER_FAILED",arm,p.returncode,stderr[-900:]))
        valid=False;status="TIMEOUT" if timed else "UNKNOWN"
        if not timed and p.returncode==10:
            valid=CF.DATA.sat_witness_valid(cnf,CF.DATA.nvars(cnf),stdout)
            if not valid:raise RuntimeError(("WRONG_SAT",arm))
            status="SAT_VERIFIED"
        if not timed and p.returncode==20:
            status="UNSAT_UNVERIFIED"
            if proof.exists() and proof.stat().st_size:
                c=subprocess.run(["build/drat-trim",str(cnf),str(proof)],capture_output=True,text=True,timeout=90)
                valid=c.returncode==0 and "s VERIFIED" in c.stdout
                if valid:status="UNSAT_CERTIFIED"
        root={}
        stats={}
        for line in stderr.splitlines():
            if line.startswith("PREGUARD_ROOT "):root=json.loads(line.split(" ",1)[1])
            if line.startswith("X41_STATS "):stats=json.loads(line.split(" ",1)[1])
        return {"arm":arm,"cap_s":cap,"status":status,"wall_s":round(wall,6),
                "PAR2_verified":round(wall if valid and wall<=cap else 2*cap,6),
                "verified":valid,"root":root,
                "conflicts":stats.get("conflicts"),"decisions":stats.get("decisions"),
                "proof_size":proof.stat().st_size if proof.exists() else 0,
                "kissat_log_tail":(stdout+stderr)[-1600:] if arm.startswith("KISSAT") else ""}
def main():
    CF.cpu_pin()
    m=CF.checked_manifest();src=next(s for s in m["sources"] if s["id"]==13)
    results=[]
    for cap in (8.0,20.0):
        for arm in ("SHADOW","FROZEN","KISSAT","KISSAT_NO_PREPROCESS"):
            result=run(src,arm,cap);results.append(result)
            emit("PREGUARD_TRIAL",result)
    assert results[0]["root"]["decisions"]==0
    assert results[0]["root"]["conflicts"]==0
    assert results[0]["root"]==results[4]["root"]
    dest=pathlib.Path("preguard13");dest.mkdir(exist_ok=True)
    (dest/"trials.json").write_text(json.dumps(results,indent=2)+"\n")
    emit("PREGUARD_PASS",{"formula_id":13,"trials":len(results),"source_sha":src["sha256"],"read_only":True,"no_promotion":True})
if __name__=="__main__":main()
