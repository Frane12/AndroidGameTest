#!/usr/bin/env python3
"""R17 strict 16-shard raw native SAT and in-process abstention audit.
New formula bootstrap is by whole formula, stratified by n, never by attempts.
"""
import csv,hashlib,json,math,random,statistics,sys
from pathlib import Path
from collections import defaultdict,Counter
sys.path.insert(0,"experiments/drnas_v16")
import r17_abstain_benchmark as b

FOLDS=("random3_development","random3_test","community3_development","community3_test")
OUT=b.OUT/"aggregate"
def need(x,why):
    if not x:raise RuntimeError("R17_AGGREGATION_REFUSED "+str(why))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def quantile(vals,p):
    vals=sorted(vals);t=(len(vals)-1)*p;k=int(t)
    return vals[k]*(1-(t-k))+vals[min(k+1,len(vals)-1)]*(t-k)
def bootstrap(rows,mode):
    groups=defaultdict(list)
    for row in rows:groups[row["n"]].append(row)
    rng=random.Random(170005+sum(ord(c) for c in mode)+len(rows))
    samples=[]
    for _ in range(3500):
        chosen=[rng.choice(group) for group in groups.values() for j in range(len(group))]
        monitor=sum(x["monitor"] for x in chosen)
        test=sum(x[mode] for x in chosen)
        samples.append(100*(monitor-test)/monitor if monitor else 0)
    return [round(quantile(samples,.025),6),round(quantile(samples,.975),6)]
def csvwrite(path,rows):
    if not rows:return
    with path.open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]))
        w.writeheader();w.writerows(rows)
def main():
    cfg=b.load_protocol()
    hist=b.history_shas()
    raw=[];traces={};manifests=[];source=[]
    seen=set()
    for shard in b.SHARDS:
        folder=Path("r17-download")/("r17-"+shard)
        f=folder/"measurements.csv";m=folder/"manifest.json";t=folder/"traces.jsonl"
        need(all(p.is_file() for p in (f,m,t)),"missing shard "+shard)
        rows=list(csv.DictReader(f.open()))
        trace_rows=[json.loads(line) for line in t.read_text().splitlines()]
        manifest=json.loads(m.read_text())
        need(len(rows)==300 and len(trace_rows)==300,"incomplete 300 attempts "+shard)
        need(manifest["protocol"]==b.PROTOCOL and manifest["category"]==shard,
             "manifest drift "+shard)
        need(manifest["modes"]==list(b.MODES) and manifest["repeats"]==b.REPS,
             "missing or changed modes "+shard)
        need(manifest["kissat_pin"]==b.PIN and manifest["stable_blob"]==b.r16.STABLE_PIN,
             "binary/source pin drift "+shard)
        need(manifest["r17_protocol_sha256"]==sha(b.RULE)
             and manifest["frozen_r15_model_sha256"]==sha(b.MODEL)
             and manifest["r16_history_sha256"]==sha(b.HISTORY),
             "protocol/model/provenance drift "+shard)
        need(len(manifest["cases"])==10,"incomplete formula manifest")
        for c in manifest["cases"]:
            sid=c["formula_sha256"]
            need(sid not in seen and sid not in hist,"reused / duplicate formula SHA")
            seen.add(sid)
            fp=folder/c["formula"]
            need(fp.is_file() and sha(fp)==sid,"source CNF file hash missing "+c["formula"])
        for r in rows:
            need(r["category"]==shard and r["runner"]==manifest["runner"]
                 and r["r17_protocol_sha256"]==sha(b.RULE),"trial/shard mismatch")
            need(r["status"] in ("SAT","UNSAT","TIMEOUT"),"bad SAT status")
            need(not r["error"] and not r["r17_error"],"native/C-Python error")
            need(abs(float(r["par2_s"])-(24.0 if r["status"]=="TIMEOUT" else float(r["wall_s"])))<1e-4,
                 "PAR2 mismatch")
            if r["status"]=="SAT":need(r["sat_model_checked"]=="True","SAT witness not checked")
            if r["mode"] in b.NEW_MODES and r["switch_at"]:
                need(r["r17_selected"]=="1" and int(r["switch_at"])>=2048
                     and int(r["restart_after"])==50
                     and r["learned_before"]==r["learned_after"],"R17 illegal native restart")
            if r["mode"]=="monitor":need(not r["switch_at"],"monitor altered")
        for trace in trace_rows:
            key=(trace["category"],trace["formula"],str(trace["repeat"]),trace["mode"])
            need(key not in traces,"duplicate native trace")
            traces[key]=trace
        raw.extend(rows);manifests.append(manifest)
        source.append(dict(shard=shard,runner=manifest["runner"],cpu_affinity=manifest["cpu_affinity"],
                           source_commit=manifest["source_commit"],source_sha256=sha(m),
                           measurements_sha256=sha(f),traces_sha256=sha(t),
                           executables=manifest["executables"]))
    need(len(raw)==4800 and len(traces)==4800 and len(seen)==160,
         "expected 16x300 attempts 160 unique new formulas")
    matched=defaultdict(dict)
    for r in raw:
        k=(r["category"],r["formula"],r["repeat"])
        need(r["mode"] in b.MODES and r["mode"] not in matched[k],"duplicate paired mode")
        matched[k][r["mode"]]=r
    need(len(matched)==480,"expected 480 formula-repetition groups")
    parity=[]
    for key,pair in matched.items():
        need(set(pair)==set(b.MODES),"paired arm missing "+str(key))
        need(len({r["formula_sha256"] for r in pair.values()})==1,"unpaired SHA")
        need(len({r["runner"] for r in pair.values()})==1,"unpaired CPU")
        need(len({r["status"] for r in pair.values() if r["status"] in ("SAT","UNSAT")})<=1,
             "SAT/UNSAT contradiction")
        base={int(x["conflict"]):x for x in traces[(*key,"monitor")]["points"] if int(x["conflict"])<=1024}
        for mode in b.MODES:
            if mode in ("monitor","original_kissat","stable_v1531"):continue
            target={int(x["conflict"]):x for x in traces[(*key,mode)]["points"] if int(x["conflict"])<=1024}
            need(set(base)==set(target),"checkpoint identity mismatched "+mode+" "+str(key))
            for cp in base:
                need(all(base[cp].get(f)==target[cp].get(f)
                  for f in ("restarts","decisions","propagations","learned","glue","stable")),
                  "PREINTERVENTION TELEMETRY DRIFT "+mode+" "+str(key))
    byformula=defaultdict(lambda:defaultdict(list))
    for r in raw:byformula[(r["category"],r["formula"])][r["mode"]].append(r)
    features=[];paired=[];actions=[]
    for (category,formula),by in sorted(byformula.items()):
        need(set(by)==set(b.MODES),"missing formula modes")
        need(all(len(v)==3 for v in by.values()),"missing repeats")
        anyrow=next(iter(by.values()))[0]
        vals={m:sum(float(r["par2_s"]) for r in by[m]) for m in b.MODES}
        fold=b.r16.previous.r14.fold_from_category(category)
        fam=b.r16.previous.r14.family_from_category(category)
        frow=dict(category=category,formula=formula,
             sha256=anyrow["formula_sha256"],seed=int(anyrow["seed"]),
             n=b.r16.previous.r14.size_from_category(category),
             fold=fold,family=fam,**vals)
        for mode in b.NEW_MODES:
            frow[mode+"_selected"]=sum(r["r17_selected"]=="1" for r in by[mode])
            frow[mode+"_switched"]=sum(bool(r["switch_at"]) for r in by[mode])
        features.append(frow)
        for mode in b.MODES:
            if mode=="monitor":continue
            paired.append(dict(fold=fold,sha256=frow["sha256"],formula=formula,mode=mode,
                monitor_PAR2_s=vals["monitor"],treatment_PAR2_s=vals[mode],
                gain_percent=100*(vals["monitor"]-vals[mode])/vals["monitor"],
                regression_gt2x=(vals[mode]>2*vals["monitor"]),
                win_gt2x=(vals["monitor"]>2*vals[mode])))
        for mode in b.NEW_MODES:
            for row in by[mode]:
                actions.append(dict(fold=fold,formula=formula,sha256=frow["sha256"],
                     repeat=row["repeat"],mode=mode,
                     native_trajectory=row["r17_traj_score"],native_snapshot=row["r17_snap_score"],
                     novelty=row["r17_novelty"],risk_pass=row["r17_risk_pass"],
                     selected=row["r17_selected"],actual_switch=row["switch_at"]))
    need(len(features)==160 and len(paired)==1440 and len(actions)==960,
         "incomplete formula/decision stats")
    summaries={}
    for fold in FOLDS:
        subset=[r for r in features if r["fold"]==fold]
        need(len(subset)==(60 if fold.startswith("random3") else 20),"fold count wrong")
        monitor=sum(r["monitor"] for r in subset)
        arms={}
        for mode in b.MODES:
            score=sum(r[mode] for r in subset)
            arms[mode]=dict(PAR2_s=round(score,6),gain_percent=round(100*(monitor-score)/monitor,6),
                 formula_bootstrap95_gain_pct=bootstrap(subset,mode) if mode!="monitor" else [0,0],
                 regression_gt2x_formulas=sum(r[mode]>2*r["monitor"] for r in subset),
                 win_gt2x_formulas=sum(r["monitor"]>2*r[mode] for r in subset),
                 selected_attempts=sum(r[mode+"_selected"] for r in subset) if mode in b.NEW_MODES else None,
                 real_switch_attempts=sum(r[mode+"_switched"] for r in subset) if mode in b.NEW_MODES else None)
        summaries[fold]=dict(formulas=len(subset),arms=arms)
    OUT.mkdir(parents=True,exist_ok=True)
    csvwrite(OUT/"formula_features.csv",features)
    csvwrite(OUT/"paired.csv",paired)
    csvwrite(OUT/"native_decisions.csv",actions)
    report=dict(protocol=b.PROTOCOL,source="new synthetic random3/community3 not official",
         attempts=4800,formulas=160,sha_disjoint_from_R7_R16=True,
         frozen_r15_model_sha256=sha(b.MODEL),r17_protocol_sha256=sha(b.RULE),
         history_registry_sha256=sha(b.REGISTRY),r16_results_sha256=sha(b.HISTORY),
         preintervention_mismatches=0,paired_native_cores_verified=True,
         independent_unsat_certificate=False,solver_code_modified="R17 experimental only",
         primary="r17_agree50 versus monitor on random3_test; 60 formula, 3 repeats",
         folds=summaries,source_shards=source,
         verdict="RESEARCH_ONLY_NO_PROMOTION_UNTIL_INDEPENDENT_EXTERNAL_PROOF")
    dump=OUT/"results.json"
    dump.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print("R17_FINAL",json.dumps({k:v for k,v in report.items() if k!="source_shards"},sort_keys=True),flush=True)
if __name__=="__main__":main()
