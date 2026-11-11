#!/usr/bin/env python3
"""Prospective SHA disjoint native generalist test against all constituent arms."""
import argparse,hashlib,json,sys,pathlib
sys.path.insert(0,"research")
from drnas_atlas40_benchmark import run,BIN
from drnas_atlas_wide500 import SOURCES,source_corpus,canonical
from generalist.generalist3 import fingerprint,choose
p=argparse.ArgumentParser()
p.add_argument("--shard",type=int,choices=(0,1),required=True)
p.add_argument("--policy",type=pathlib.Path,default=pathlib.Path("generalist4_policy.json"))
a=p.parse_args()
policy=json.loads(a.policy.read_text())
assert policy["version"]==3 and policy["selection_frozen"] is True
trained=set(policy["training_sha"])
root=pathlib.Path("mre_generalist4");root.mkdir(exist_ok=True)
corpus=source_corpus(limit=16)
sources=[]
for family in SOURCES:
 for i in (14,15):
    n,cls,sha,entry=corpus[family][i]
    if i%2!=a.shard:continue
    raw=canonical(n,cls)
    assert hashlib.sha256(raw).hexdigest()==sha and sha not in trained
    path=root/(family+"_"+str(i)+".cnf");path.write_bytes(raw)
    sources.append({"sha256":sha,"family":family,"index":i,"cohort":"unseen",
                    "path":str(path),"archive_entry":entry})
assert len(sources)==5 and len({x["sha256"] for x in sources})==5
cap=60.0; rows=[]
print("GENERALIST4_MANIFEST "+json.dumps({"shard":a.shard,"cases":len(sources),
 "repetitions":2,"cap_s":cap,"one_cpu":True,"training_run_id":policy["training_run_id"],
 "sha_disjoint":True,"training_sha":len(trained),"arms":["A36_75","A39_PROTECT","A40_TREE","AUTO","KISSAT"]}),flush=True)
for src in sources:
 feat=fingerprint(src["path"])
 assert feat["sha256"]==src["sha256"]
 selected=choose(feat,policy["cells"])
 for rep in range(2):
    results={}
    for arm in ("A36_75","A39_PROTECT","A40_TREE","AUTO","KISSAT"):
        actual=selected if arm=="AUTO" else arm
        result=run(src,actual,rep,cap)
        result["arm"]=arm
        result["executed_arm"]=actual
        result["fingerprint_key"]=feat["key"]
        result["fallback"]=selected=="A36_75"
        assert result["sha256"]==src["sha256"]
        rows.append(result);results[arm]=result
        print("GENERALIST4_TRIAL "+json.dumps(result,sort_keys=True),flush=True)
    if any(x["status"]=="SAT_VERIFIED" for x in results.values()) and any(x["status"]=="UNSAT_UNVERIFIED" for x in results.values()):
        raise AssertionError("SAT/UNSAT disagreement "+src["sha256"])
    auto=results["AUTO"]["PAR2_verified_s"]
    candidate={x:results[x]["PAR2_verified_s"] for x in ("A36_75","A39_PROTECT","A40_TREE")}
    best=min(candidate,key=candidate.get)
    print("GENERALIST4_FEEDBACK "+json.dumps({"sha256":src["sha256"],"rep":rep,
        "selected":selected,"best_measured":best,
        "regret_s":round(auto-candidate[best],6),
        "fallback":selected=="A36_75","feature_key":feat["key"]},sort_keys=True),flush=True)
out=root/f"results_{a.shard}.json"
out.write_text(json.dumps({"sources":sources,"rows":rows,"training_sha":sorted(trained),
                            "cap_s":cap},indent=2,sort_keys=True)+"\n")
print("GENERALIST4_FINAL "+json.dumps({"shard":a.shard,"trials":len(rows),
 "auto_par2_verified_s":round(sum(r["PAR2_verified_s"] for r in rows if r["arm"]=="AUTO"),5),
 "auto_solves":sum(r["status"]=="SAT_VERIFIED" for r in rows if r["arm"]=="AUTO"),
 "nondefault_auto":sum(r["executed_arm"]!="A36_75" for r in rows if r["arm"]=="AUTO")},sort_keys=True),flush=True)
