#!/usr/bin/env python3
"""R115 original-CNF same-run R28 vs CryptoMiniSat Gauss on/off; SAT witnesses audited."""
import csv, hashlib, json, os, pathlib, re, statistics, subprocess, sys, time
root = pathlib.Path("r115_cms_audit")
root.mkdir(exist_ok=True)
cnf = root/"r115.cnf"
SHA="243e5d0079606862166a4619691cbbb8ffc9c8c14eb16250138b16d724c6bc83"
assert hashlib.sha256(cnf.read_bytes()).hexdigest()==SHA, "Original CNF SHA mismatch"
tokens=[]
for line in cnf.read_text().splitlines():
    if line.strip().startswith(("c","p","%")): continue
    tokens.extend(map(int,line.split()))
clauses=[]; current=[]
for x in tokens:
    if x == 0: clauses.append(current);current=[]
    else: current.append(x)
assert not current and len(clauses)==1000
version = subprocess.run(["cryptominisat5","--version"],capture_output=True,text=True,timeout=10)
print("CMS_VERSION", (version.stdout+" "+version.stderr).strip()[:2000],flush=True)
print("CNF_SHA",SHA,flush=True)
def audit(output):
    status = "SAT" if re.search(r"^s\s+SATISFIABLE\b",output,re.M) else ("UNSAT" if re.search(r"^s\s+UNSATISFIABLE\b",output,re.M) else "UNKNOWN")
    model={}
    if status=="SAT":
        for line in output.splitlines():
            if line.startswith("v "):
                for k in map(int,line[2:].split()):
                    if k: model[abs(k)]=(k>0)
        if not model: return status,False,0,len(model)
        covered=sum(any(model.get(abs(l))==(l>0) for l in clause) for clause in clauses)
        return status,covered==len(clauses),covered,len(model)
    return status,status=="UNSAT",None,0
modes={
 "r28":["./r115_cms_audit/r28",str(cnf),"/bin/false"],
 "cms_gauss_on":["cryptominisat5","--threads=1","--autodisablegauss=0","--maxnummatrices=5","--verb=2",str(cnf)],
 "cms_gauss_off":["cryptominisat5","--threads=1","--maxnummatrices=0","--verb=2",str(cnf)],
}
rows=[]
for rep in range(3):
    order=list(modes)
    if rep%2:order.reverse()
    for mode in order:
        cmd=modes[mode]
        t=time.perf_counter()
        try:
            p=subprocess.run(cmd,capture_output=True,text=True,timeout=30)
            elapsed=time.perf_counter()-t
            output=p.stdout+"\n"+p.stderr
            st,verified,ncovered,nassigned=audit(output)
            if st=="UNKNOWN": st="ERROR"
            if st=="SAT" and not verified:st="INVALID_MODEL"
            rc=p.returncode
        except subprocess.TimeoutExpired as ex:
            elapsed=30.0
            output=(ex.stdout or b"").decode(errors="replace") if isinstance(ex.stdout,bytes) else (ex.stdout or "")
            output+="\nTIMEOUT"
            st="TIMEOUT";verified=False;ncovered=None;nassigned=0;rc=124
        (root/f"{mode}-rep{rep}.log").write_text(output)
        row=dict(rep=rep,mode=mode,status=st,elapsed_s=round(elapsed,6),
                 model_verified=verified,covered_clauses=ncovered,assigned_vars=nassigned,exit_code=rc)
        rows.append(row)
        print("R115_CMS_TRIAL",json.dumps(row,sort_keys=True),flush=True)
        if st=="INVALID_MODEL" or st=="ERROR":
            print("INVALID OR ERROR: "+mode+" "+str(rep),flush=True)
with (root/"trials.csv").open("w",newline="") as f:
    w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
summary={}
for name in modes:
    r=[x for x in rows if x["mode"]==name]
    solved=[x for x in r if x["status"]=="SAT" and x["model_verified"]]
    summary[name]=dict(sat_verified=len(solved),trials=len(r),
      median_s=round(statistics.median(x["elapsed_s"] for x in solved),6) if solved else None,
      timeouts=sum(x["status"]=="TIMEOUT" for x in r),other=[x["status"] for x in r if x["status"] not in ("SAT","TIMEOUT")])
(root/"summary.json").write_text(json.dumps(summary,indent=2))
print("R115_CMS_FINAL",json.dumps(summary,sort_keys=True),flush=True)
if any(x["status"] not in ("SAT","TIMEOUT") for x in rows):
    sys.exit(2)
