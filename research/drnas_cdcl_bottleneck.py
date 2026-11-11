#!/usr/bin/env python3
"""Diagnostic controlled CDCL ablation on difficult previously seen formulas.
NO training, no policy updates and no claims of independent UNSAT proof.
All binaries are native DRNAS built from same source, one CPU, matched 8s E2E.
"""
import hashlib,json,os,pathlib,subprocess,time
import drnas_atlas_wide500 as W

OUT=pathlib.Path("mre_cdcl_diag");OUT.mkdir(exist_ok=True)
SHARD=int(os.environ.get("CDCL_DIAG_SHARD","0"))
CAP=8.0;REPS=2
ARMS=("BASE","BLOCKER","FAST100","NEGPHASE","TRACE")
BIN={a:(OUT/"bin"/("drnas_"+a.lower())).resolve() for a in ARMS}
SELECTED=[
 ("uf250-1065",25),("uf250-1065",26),
 ("uuf250-1065",25),("uuf250-1065",26),
 ("pigeonhole_unsat",25),("pigeonhole_unsat",26),
 ("uf100-430",25),
]
SHARDS=[[0,2,6],[1,4],[3,5]]

def original_cases():
    real=W.source_corpus(limit=30)
    cases=[]
    for cat,i in SELECTED:
        if cat in real:n,clauses,sha,entry=real[cat][i]
        else:
            n,clauses=W.synth_one(cat,i)
            sha=hashlib.sha256(W.canonical(n,clauses)).hexdigest()
            entry=f"generated:{cat}:{i}"
        cases.append({"category":cat,"index":i,"n":n,"clauses":clauses,
                      "sha256":sha,"entry":entry})
    return cases

def tokens(line):
    return dict(x.split("=",1) for x in line.split()[1:] if "=" in x)

def invoke(src,arm,rep):
    cnf=OUT/f"diag_{src['category']}_{src['index']}.cnf"
    cnf.write_bytes(W.canonical(src["n"],src["clauses"]))
    start=time.monotonic()
    try:
        p=subprocess.run([str(BIN[arm]),str(cnf.resolve()),"--mode","A",
                     "--time",str(CAP)],capture_output=True,text=True,timeout=CAP+1.8)
        rc=p.returncode
        stdout=p.stdout
        stderr=p.stderr
    except subprocess.TimeoutExpired:
        rc=-9;stdout="";stderr="timeout_exceeded"
    elapsed=time.monotonic()-start
    metrics={}
    profile={}
    watch={}
    vals={}
    for line in stdout.splitlines():
        if line.startswith("ATLASMAP2_TRIAL "):metrics=tokens(line)
        elif line.startswith("DRNAS_PROFILE "):profile=tokens(line)
        elif line.startswith("DRNAS_WATCH1 "):watch=tokens(line)
        elif line.startswith("v "):
            for t in line.split()[1:]:
                lit=int(t)
                if lit:vals[abs(lit)]=lit>0
    if rc==2:raise RuntimeError("Native crash "+str((arm,src["sha256"],stderr[-500:],stdout[-500:])))
    status={10:"SAT",20:"UNSAT_UNCERTIFIED"}.get(rc,"UNKNOWN")
    verified=(status=="SAT" and len(vals)>=src["n"] and
              all(any(vals.get(abs(l))==(l>0) for l in c) for c in src["clauses"]))
    if status=="SAT" and not verified:raise AssertionError("Invalid SAT model "+src["sha256"]+" "+arm)
    f=lambda data,k:float(data.get(k,0))
    return {
      "arm":arm,"rep":rep,"category":src["category"],"index":src["index"],
      "sha256":src["sha256"],"status":status,"SAT_original_verified":verified,
      "UNSAT_independent_LRAT":False,"E2E_s":round(elapsed,6),
      "PAR2_reported_s":round(elapsed if status in ("SAT","UNSAT_UNCERTIFIED") else 2*CAP,6),
      "conflicts":int(f(metrics,"conflicts")),"decisions":int(f(metrics,"decisions")),
      "learned":int(f(metrics,"learned")),"restarts":int(f(metrics,"restarts")),
      "propagations":int(f(metrics,"propagations")),
      "watch_visits":int(f(metrics,"watch_visits")),
      "heap_bumps":int(f(metrics,"heap_bumps")),
      "bcp_s":round(f(profile,"bcp_s"),6),
      "analyze_s":round(f(profile,"analyze_s"),6),
      "select_s":round(f(profile,"select_s"),6),
      "update_s":round(f(profile,"update_s"),6),
      "watchlist_entries":int(f(watch,"watchlist_entries")),
      "watchlist_peak":int(f(watch,"watchlist_peak")),
      "visits_learned":int(f(watch,"visits_learned")),
      "visits_original":int(f(watch,"visits_original")),
      "candidate_probes":int(f(watch,"candidate_probes")),
      "watch_cache_hits":int(f(watch,"cache_hit")),
    }

def main():
    cases=original_cases()
    selected=[cases[k] for k in SHARDS[SHARD]]
    print("CDCL_DIAG_SOURCE "+json.dumps({"shard":SHARD,
          "selected":[{k:v for k,v in row.items() if k!="clauses"} for row in selected],
          "reps":REPS,"arms":ARMS,"cap_s":CAP,"oneCPU":True},sort_keys=True),flush=True)
    rows=[]
    for src in selected:
        for rep in range(REPS):
            for arm in ARMS:
                row=invoke(src,arm,rep)
                rows.append(row)
                print("CDCL_DIAG_TRIAL "+json.dumps(row,sort_keys=True),flush=True)
        for arm in ARMS:
            statuses={r["status"] for r in rows if r["sha256"]==src["sha256"] and r["arm"]==arm}
            # Conflicting SAT/UNSAT outcomes signal a genuine correctness issue.
            if "SAT" in statuses and "UNSAT_UNCERTIFIED" in statuses:
                raise AssertionError("Internal status mismatch "+src["sha256"])
    summary={}
    for arm in ARMS:
        rs=[r for r in rows if r["arm"]==arm]
        summary[arm]={k:sum(r[k] for r in rs) for k in [
            "E2E_s","PAR2_reported_s","conflicts","decisions","learned",
            "restarts","watch_visits","bcp_s","analyze_s","select_s","update_s",
            "candidate_probes","visits_learned","visits_original","watch_cache_hits"]}
        summary[arm]["trials"]=len(rs)
        summary[arm]["SAT_verified"]=sum(r["SAT_original_verified"] for r in rs)
        summary[arm]["UNSAT_uncertified"]=sum(r["status"]=="UNSAT_UNCERTIFIED" for r in rs)
        summary[arm]["UNKNOWN"]=sum(r["status"]=="UNKNOWN" for r in rs)
    (OUT/f"cdcl_diag_audit_{SHARD}.json").write_text(json.dumps({"rows":rows,"summary":summary},indent=2))
    print("CDCL_DIAG_FINAL "+json.dumps({"shard":SHARD,"summary":summary},sort_keys=True),flush=True)

if __name__=="__main__":
    main()
