#!/usr/bin/env python3
"""ATLAS prospective V1: completely new source SHAs, frozen WIDE500 policy.
100 formulae / 20 families, 2 repeats, 6 matched one-core E2E arms.
Only SAT witnesses are independently checked. UNSAT without proof is reported
but NOT independently certified. CDCL decisions and outcomes stream to JSONL.
"""
import argparse,hashlib,json,os,pathlib,selectors,subprocess,time
import drnas_atlas_wide500 as W
import drnas_atlas_selective_gf2 as GF2

SHARD=int(os.environ.get("ATLAS_PROSPECT_SHARD","0"))
assert 0<=SHARD<5
ROOT=pathlib.Path("mre_map2_real47")
ROOT.mkdir(exist_ok=True)
MEMFILE=pathlib.Path("research/atlas_wide500_memory.json")
CAP=5.0
REPS=2
ARMS=("A","GF2_SELECTIVE","MAP2_LIVE","POLICY","KISSAT","CMS")
NATIVE=pathlib.Path("mre_atlasmap2/bin/drnas_atlasmap2").resolve()
KISSAT=pathlib.Path("mre_map2_real47/bin/kissat").resolve()
CMS=pathlib.Path("/usr/bin/cryptominisat5")

def manifest():
    raw=MEMFILE.read_bytes()
    memory=json.loads(raw)
    assert len(memory["train_samples"])==400 and len(memory["groups"])>=20
    training=set(memory["train_samples"])
    corpus=W.source_corpus(limit=30)
    rows=[]
    for cat in W.SOURCES+W.SYNTH:
        i=25+SHARD
        if cat in corpus:
            n,clauses,sha,entry=corpus[cat][i]
        else:
            n,clauses=W.synth_one(cat,i)
            sha=hashlib.sha256(W.canonical(n,clauses)).hexdigest()
            entry=f"generated:{cat}:{i}"
        screen=GF2.screen(clauses)
        key=W.group_key({"category":cat,"clauses":clauses},screen)
        policy=W.decide(memory["groups"].get(key,{}))
        rows.append(dict(category=cat,index=i,n=n,clauses=clauses,
                         sha256=sha,provenance=entry,policy_arm=policy,
                         gf2_gate=screen["gate"],group_key=key))
    assert len(rows)==20 and len({x["sha256"] for x in rows})==20
    assert all(x["sha256"] not in training for x in rows)
    return rows,hashlib.sha256(raw).hexdigest()

def parse_model(stdout,expected_n,clauses):
    model={}
    for line in stdout:
        if not line.startswith("v "):continue
        for t in line.split()[1:]:
            try:lit=int(t)
            except ValueError:continue
            if lit and abs(lit)<=expected_n:model[abs(lit)]=lit>0
    return bool(model) and all(any(model.get(abs(v))==(v>0) for v in c) for c in clauses)

def command(arm,policy,cnf):
    actual=policy if arm=="POLICY" else arm
    if actual in ("A","GF2_SELECTIVE","MAP2_LIVE"):
        return [str(NATIVE),str(cnf),"--mode",actual,"--time",str(CAP)]
    if actual=="KISSAT":return [str(KISSAT),str(cnf)]
    if actual=="CMS":return [str(CMS),"--threads=1","--verb=0",str(cnf)]
    raise AssertionError("invalid frozen arm: "+actual)

def run_one(source,arm,rep,journal):
    cnf=ROOT/f"atlas_prospect_{SHARD}.cnf"
    cnf.write_bytes(W.canonical(source["n"],source["clauses"]))
    start=time.monotonic()
    cmd=command(arm,source["policy_arm"],cnf.resolve())
    proc=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,bufsize=0)
    selector=selectors.DefaultSelector()
    selector.register(proc.stdout,selectors.EVENT_READ)
    output=[];buffer=b"";events=0;counts={}
    deadline=start+CAP+1.25
    while time.monotonic()<deadline:
        waiting=selector.select(timeout=0.12)
        if waiting:
            chunk=os.read(proc.stdout.fileno(),65536)
            if not chunk:break
            buffer+=chunk
            while b"\n" in buffer:
                line,buffer=buffer.split(b"\n",1)
                line=line.decode("utf-8","replace")
                if line.startswith("DRNAS_CDCL_EVENT ") or line.startswith("DRNAS_CDCL_OUTCOME "):
                    kind="outcome" if line.startswith("DRNAS_CDCL_OUTCOME ") else "event"
                    fields=dict(k.split("=",1) for k in line.split()[1:] if "=" in k)
                    key=kind+":"+fields.get("kind","unknown")
                    counts[key]=counts.get(key,0)+1
                    journal.write(json.dumps({"phase":"prospective","sha256":source["sha256"],
                        "category":source["category"],"arm":arm,"repeat":rep,
                        "record_type":kind,"elapsed_s":round(time.monotonic()-start,6),
                        "telemetry":fields},sort_keys=True)+"\n")
                    journal.flush()
                    events+=1
                else:output.append(line)
        if proc.poll() is not None and not waiting:break
    if proc.poll() is None:proc.kill()
    proc.wait()
    selector.close()
    if buffer:output.append(buffer.decode("utf-8","replace"))
    seconds=round(time.monotonic()-start,6)
    exit_code=proc.returncode
    status={10:"SAT",20:"UNSAT_UNCERTIFIED"}.get(exit_code,"UNKNOWN")
    if status=="UNKNOWN" and any("ATLASMAP2_ERROR" in x for x in output):
        raise RuntimeError("native solver error "+source["sha256"]+":"+";".join(output[-4:]))
    sat_verified=status=="SAT" and parse_model(output,source["n"],source["clauses"])
    if status=="SAT" and not sat_verified:
        raise RuntimeError("Invalid or missing SAT witness "+source["sha256"]+" "+arm)
    metrics={}
    for line in output:
        if line.startswith("ATLASMAP2_TRIAL "):
            metrics=dict(k.split("=",1) for k in line.split()[1:] if "=" in k)
    return dict(arm=arm,actual=source["policy_arm"] if arm=="POLICY" else arm,
        rep=rep,sha256=source["sha256"],category=source["category"],
        group_key=source["group_key"],policy_arm=source["policy_arm"],
        provenance=source["provenance"],E2E_s=seconds,
        PAR2_verified_s=seconds if sat_verified else CAP*2,
        PAR2_reported_s=seconds if (sat_verified or status=="UNSAT_UNCERTIFIED") else CAP*2,
        SAT_original_verified=bool(sat_verified),
        UNSAT_independent_LRAT=False,
        status=status,CDCL_event_count=events,feedback_counts=counts,
        decisions=int(metrics.get("decisions",0)),
        conflicts=int(metrics.get("conflicts",0)),
        learned=int(metrics.get("learned",0)),
        gf2_gate=int(metrics.get("gf2_gate",0)),
        gf2_implications=int(metrics.get("gf2_implications",0)),
        gf2_reasons=int(metrics.get("gf2_reasons",0)))

def totals(rows):
    summary={}
    for arm in ARMS:
        r=[x for x in rows if x["arm"]==arm]
        summary[arm]={
            "trials":len(r),
            "SAT_verified":sum(x["SAT_original_verified"] for x in r),
            "UNSAT_reported_uncertified":sum(x["status"]=="UNSAT_UNCERTIFIED" for x in r),
            "UNKNOWN":sum(x["status"]=="UNKNOWN" for x in r),
            "PAR2_verified_s":round(sum(x["PAR2_verified_s"] for x in r),6),
            "PAR2_reported_s":round(sum(x["PAR2_reported_s"] for x in r),6),
            "decisions":sum(x["decisions"] for x in r),
            "conflicts":sum(x["conflicts"] for x in r),
            "gf2_implications":sum(x["gf2_implications"] for x in r),
            "CDCL_events":sum(x["CDCL_event_count"] for x in r),
            "CDCL_backjump_samples":sum(x["feedback_counts"].get("outcome:conflict_backjump",0) for x in r),
            "CDCL_restart_samples":sum(x["feedback_counts"].get("outcome:restart_abandoned",0) for x in r)}
    return summary

def run():
    manifest_rows,memory_sha=manifest()
    source_manifest=[{k:v for k,v in s.items() if k!="clauses"} for s in manifest_rows]
    (ROOT/f"atlas_prospect_manifest_{SHARD}.json").write_text(
        json.dumps({"memory_sha256":memory_sha,"sources":source_manifest},indent=2))
    print("ATLAS_PROSPECT_FROZEN "+json.dumps({"shard":SHARD,"memory_sha256":memory_sha,
        "sources":len(manifest_rows),"arms":list(ARMS),"reps":REPS,
        "one_cpu":True,"cap_s":CAP},sort_keys=True),flush=True)
    rows=[]
    journal_path=ROOT/f"atlas_prospect_feedback_{SHARD}.jsonl"
    with journal_path.open("w",buffering=1) as journal:
        for s in manifest_rows:
            for rep in range(REPS):
                for arm in ARMS:
                    outcome=run_one(s,arm,rep,journal)
                    rows.append(outcome)
                    print("ATLAS_PROSPECT_TRIAL "+json.dumps(outcome,sort_keys=True),flush=True)
    summary=totals(rows)
    report={"shard":SHARD,"memory_sha256":memory_sha,"sources":source_manifest,
            "rows":rows,"summary":summary,"cap_s":CAP,
            "UNSAT_independent_LRAT":False,
            "training_memory_updated":False}
    (ROOT/f"atlas_prospect_audit_{SHARD}.json").write_text(json.dumps(report,indent=2))
    print("ATLAS_PROSPECT_FINAL "+json.dumps({"shard":SHARD,"summary":summary,
          "memory_sha256":memory_sha},sort_keys=True),flush=True)

def merge(directory):
    reports=[json.loads((directory/f"atlas_prospect_audit_{i}.json").read_text()) for i in range(5)]
    sha={r["memory_sha256"] for r in reports}
    if len(sha)!=1:raise AssertionError("memory SHA differs across shards")
    rows=sum((r["rows"] for r in reports),[])
    sources=sum((r["sources"] for r in reports),[])
    ids={s["sha256"] for s in sources}
    if len(ids)!=100 or len(sources)!=100:
        raise AssertionError("prospective sources overlap or missing")
    fams={s["category"] for s in sources}
    if len(fams)!=20 or any(sum(s["category"]==fam for s in sources)!=5 for fam in fams):
        raise AssertionError("not 20 balanced families")
    original=json.loads(MEMFILE.read_text())
    if ids.intersection(original["train_samples"]):
        raise AssertionError("train leakage")
    expected=len(sources)*REPS*len(ARMS)
    if len(rows)!=expected:raise AssertionError(f"trials mismatch {len(rows)} != {expected}")
    output={"sources":len(sources),"categories":len(fams),"attempts":len(rows),
        "cap_s":CAP,"memory_sha256":next(iter(sha)),"memory_updated":False,
        "summary":totals(rows),"source_sha":[s["sha256"] for s in sources],
        "UNSAT_independent_LRAT":False}
    pathlib.Path("research/atlas_prospective_v1_summary.json").write_text(json.dumps(output,indent=2))
    print("ATLAS_PROSPECT_MERGED "+json.dumps(output,sort_keys=True),flush=True)

def smoke():
    a=({"category":"pigeonhole_unsat","index":25})
    n,clauses=W.synth_one(a["category"],a["index"])
    src={**a,"n":n,"clauses":clauses,
         "sha256":hashlib.sha256(W.canonical(n,clauses)).hexdigest(),
         "policy_arm":"A","group_key":"smoke","provenance":"generated-smoke"}
    with (ROOT/"atlas_prospect_smoke_feedback.jsonl").open("w") as journal:
        r=run_one(src,"A",0,journal)
    assert r["status"] in ("SAT","UNSAT_UNCERTIFIED","UNKNOWN")
    assert r["CDCL_event_count"]>0,"missing compiled live CDCL events"
    print("ATLAS_FEEDBACK2_SMOKE_PASS "+json.dumps(r,sort_keys=True),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--merge-dir")
    p.add_argument("--smoke",action="store_true")
    args=p.parse_args()
    if args.smoke:smoke()
    elif args.merge_dir:merge(pathlib.Path(args.merge_dir))
    else:run()
