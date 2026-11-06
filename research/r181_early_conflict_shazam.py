#!/usr/bin/env python3
"""R181 SAT Shazam: real 64/128/256 conflict probe + held-out offline replay.

All measured 5-arm target timings come from frozen R179. No held-out timings
are used in model fitting. Three probes are independent and add their actual
measured wall cost to the selected arm (the probe cannot be resumed).
All reported improvement figures are retrospective replay, NOT live solver speedup.
"""
from __future__ import annotations
import argparse, collections, hashlib, json, math, pathlib, re, statistics, subprocess, time
import r180_sat_shazam as r180

ROOT=pathlib.Path("r181")
CUTOFFS=(64,128,256)
MODES=r180.MODES

def need(ok,msg):
    if not ok:raise RuntimeError(msg)

def probe(src,binary,cutoff,timeout):
    started=time.perf_counter()
    try:
        p=subprocess.run([str(binary.resolve()),str(src.resolve()),str(cutoff)],
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout,check=False)
        elapsed=time.perf_counter()-started
    except subprocess.TimeoutExpired:
        elapsed=time.perf_counter()-started
        return {"status":"TIMEOUT","wall_s":elapsed,
                "conflicts":-1,"decisions":-1,"learned":-1,"propagations":-1}
    txt=p.stdout.decode(errors="replace")
    need(p.returncode==0,"probe failed "+p.stderr.decode(errors="replace")[-1500:])
    head=re.search(r"^R181_PROBE cutoff=(\d+) status=(SAT|UNSAT|UNKNOWN) vars=(\d+) elapsed=([0-9.eE+-]+)$",txt,re.M)
    b=txt.find("R181_STATS_BEGIN");e=txt.find("R181_STATS_END")
    need(head and int(head[1])==cutoff and b>=0 and e>b,"probe telemetry incomplete")
    block=txt[b:e]
    stats={}
    for key in ("conflicts","decisions","learned","propagations"):
        vals=re.findall(r"(?:^|\n)\s*(?:c\s+)?"+key+r":\s+(\d+)\b",block,re.M)
        stats[key]=int(vals[-1]) if vals else -1
    # At least two real internal CDCL counters required. Never substitute
    # intended conflict cutoff for actual conflicts reached.
    # CaDiCaL may finish with the "lucky" preprocessing/decision path
    # before it has CDCL conflict or decision counters to print at all.
    # Missing counters remain -1 (unavailable), not fabricated zeros.
    if head[2]=="UNKNOWN":
        need(stats["conflicts"]>=0 and stats["decisions"]>=0,
             "UNKNOWN probe statistics not captured: "+block[-2000:])
    return {"status":head[2],"wall_s":elapsed,**stats}

def features(static,obs):
    a=list(static)
    status=obs["status"]
    a.extend([math.log1p(obs[k]) if obs[k]>=0 else 0.0 for k in (
      "conflicts","decisions","learned","propagations")])
    c=max(1,obs["conflicts"]);d=max(1,obs["decisions"])
    a.extend([obs["conflicts"]/d if obs["conflicts"]>=0 else 0.0,
          obs["propagations"]/c if obs["propagations"]>=0 else 0.0,
          math.log1p(obs["wall_s"]),float(status=="UNKNOWN"),
          float(status=="SAT"),float(status=="UNSAT"),
          float(status=="TIMEOUT")])
    return tuple(a)

def metric(dataset,cutoff):
    train=[z for z in dataset if z["split"]=="train"]
    test=[z for z in dataset if z["split"]=="holdout"]
    training=[(features(z["struct"],z["probes"][cutoff]),z["times"]) for z in train]
    dimension=len(training[0][0])
    scales=[max(0.1,statistics.pstdev(z[0][i] for z in training))
            for i in range(dimension)]
    results=[]
    for z in test:
        v=features(z["struct"],z["probes"][cutoff])
        started=time.perf_counter()
        mode,pred=r180.route(v,training,scales)
        classifier_s=time.perf_counter()-started
        cost=z["static_s"]+z["probes"][cutoff]["wall_s"]+classifier_s
        clean=z["times"]["clean"]
        # conservative: independent clean probing is thrown away; chosen solve
        # starts afresh, plus fingerprint and decision overhead.
        chosen=z["times"][mode]+cost
        oracle=min(z["times"].values())
        results.append({
            "id":z["id"],"origin":z["origin"],"route":mode,
            "probe_status":z["probes"][cutoff]["status"],
            "probe_conflicts":z["probes"][cutoff]["conflicts"],
            "probe_decisions":z["probes"][cutoff]["decisions"],
            "probe_wall_s":round(z["probes"][cutoff]["wall_s"],7),
            "charged_cost_s":round(cost,7),
            "clean_par2_s":clean,"routed_replay_par2_s":chosen,
            "oracle_par2_s":oracle,"best_mode":min(MODES,key=z["times"].get),
            "predicted_score":pred.get(mode)
        })
    total=lambda key:sum(x[key] for x in results)
    cm=collections.Counter(x["route"] for x in results)
    sm=collections.Counter(x["probe_status"] for x in results)
    clean=total("clean_par2_s"); routed=total("routed_replay_par2_s")
    summary={"cutoff":cutoff,"train":len(train),"holdout":len(test),
        "real_holdout":sum(x["origin"]=="real_frozen" for x in results),
        "chosen_modes":dict(cm),"probe_statuses":dict(sm),
        "clean_par2_total_s":round(clean,6),
        "replay_par2_total_s":round(routed,6),
        "oracle_par2_total_s":round(total("oracle_par2_s"),6),
        "clean_to_routed_ratio":round(clean/routed,6) if routed>0 else None,
        "probe_wall_total_s":round(total("probe_wall_s"),6),
        "improved_cases":sum(x["routed_replay_par2_s"]<x["clean_par2_s"] for x in results),
        "chosen_oracle_mode":sum(x["route"]==x["best_mode"] for x in results)}
    return summary,results

def evaluate(source,binary,probe_timeout):
    manifest=json.loads((source/"frozen"/"manifest.json").read_text())
    need(manifest["protocol"]=="DRNAS-R179-FROZEN-100-MIXED-SPECTRUM-v1",
         "wrong dataset")
    rows=[]
    for i in range(10): rows.extend(json.loads((source/f"shard-{i}.json").read_text()))
    need(len(rows)==1000,"missing original 1000 paired R179 measurements")
    cases=r180.cases_from_data(manifest,rows)
    dataset=[]; counts=collections.Counter()
    ROOT.mkdir(parents=True,exist_ok=True)
    checkpoint=ROOT/"probe-checkpoint.json"
    persisted=json.loads(checkpoint.read_text()) if checkpoint.exists() else {}
    for c,times in cases:
        src=source/"frozen"/(c["id"]+".cnf")
        need(hashlib.sha256(src.read_bytes()).hexdigest()==c["sha256"],
             "original source SHA mismatch")
        struct,static_s,info=r180.fingerprint(src)
        group=r180.split(c["id"],c["sha256"],c["origin"])
        current=persisted.setdefault(c["sha256"],{})
        for k in CUTOFFS:
            if str(k) not in current:
                current[str(k)]=probe(src,binary,k,probe_timeout)
                checkpoint.write_text(json.dumps(persisted))
                print("R181_EARLY",json.dumps({"id":c["id"],"cutoff":k,
                    "split":group,**current[str(k)]}),flush=True)
        dataset.append({"id":c["id"],"origin":c["origin"],"sha256":c["sha256"],
                 "split":group,"struct":struct,"static_s":static_s,
                 "details":info,"times":times,
                 "probes":{k:current[str(k)] for k in CUTOFFS}})
        counts[group]+=1
    need(counts["train"]>=50 and counts["holdout"]>=10,"bad SHA split")
    need(sum(z["origin"]=="real_frozen" for z in dataset if z["split"]=="train")==0,
         "real source leakage")
    summaries={}
    for k in CUTOFFS:
        summary,results=metric(dataset,k)
        summaries[str(k)]=summary
        (ROOT/f"holdout-{k}.json").write_text(json.dumps(results,indent=2))
    baseline_replay={"R180_clean_only_holdout":True}
    audit={"protocol":"DRNAS-R181-EARLY-CONFLICTS-v1",
         "dataset":"R179 4 known real + 96 synthetic SAT; not blind",
         "methods":"kNN source-structure + clean CDCL early statistics, independent probes",
         "scoring":"R179 capped PAR2 from same frozen SHA originals; probe time charged",
         "not_live_speedup":True,"no_heldout_label_leakage":True,
         "all_real_formulas_heldout":True,
         "no_continuation_from_probe":True,
         "runs":summaries}
    (ROOT/"report.json").write_text(json.dumps(audit,indent=2,sort_keys=True))
    (ROOT/"summary.md").write_text(
      "# R181 SAT Shazam true early CDCL probe, retrospective holdout replay\n\n"
      "CaDiCaL rel-2.1.0, 64/128/256 separate conflict-capped runs. "
      "All 4 real known CNFs held out. 96 synthetic SAT; not blind. "
      "Replay includes independent probe overhead and cannot claim live speedup.\n\n"
      "| cutoff | clean PAR2 s | routed replay PAR2 s | ratio | routed modes |\n"
      "|---:|---:|---:|---:|---|\n"+
      "".join(f'| {k} | {v["clean_par2_total_s"]} | {v["replay_par2_total_s"]} | {v["clean_to_routed_ratio"]} | {v["chosen_modes"]} |\n'
              for k,v in summaries.items()))
    print("R181_EARLY_FINAL",json.dumps(summaries,sort_keys=True),flush=True)

def selftest():
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        t=pathlib.Path(td)
        f=t/"small.cnf"
        f.write_text("p cnf 3 2\n1 2 0\n-1 3 0\n")
        v,_,_=r180.fingerprint(f)
        fake={"status":"UNKNOWN","wall_s":0.01,"conflicts":64,"decisions":70,
              "learned":12,"propagations":210}
        need(len(features(v,fake))==len(v)+11,"bad feature dimension")
        need(r180.split("unused","a"*64,"real_frozen")=="holdout","bad provenance")
    print("R181_SELFTEST_PASS")
if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("action",choices=("selftest","evaluate"))
    ap.add_argument("--source",default="r179")
    ap.add_argument("--probe",default="r181/r181-probe")
    ap.add_argument("--timeout",type=float,default=20.0)
    args=ap.parse_args()
    if args.action=="selftest":selftest()
    else:evaluate(pathlib.Path(args.source),pathlib.Path(args.probe),args.timeout)
