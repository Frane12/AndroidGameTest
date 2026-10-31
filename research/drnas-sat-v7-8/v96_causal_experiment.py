#!/usr/bin/env python3
"""V9.6 controlled factorial: initial phase hints x 256-conflict continuation.
Six instrumented interventions; frozen V7.6 and CaDiCaL as references.
Known diagnostic examples NEVER count as independent validation.
"""
import argparse,csv,hashlib,json,os,random,statistics,subprocess,time
from collections import defaultdict,Counter
from pathlib import Path
import official_shortlong_select as source
from official_shortlong_select import REV,SCORES_GIT_BLOB
source.RAW_CAP=96*1024*1024
source.CNF_CAP=96*1024*1024
source.VARIABLE_CAP=1000000
source.CLAUSE_CAP=4000000
SALT="DRNAS-SAT-v96-factorial-prospective-20261031-v1"
KNOWN_PREFIX=("8117a2ac08","f52a349677","75429ff7ac","91860f79f0",
              "8d0d8518a4","ee44c3f4")
ARMS=("ca_plain","orig_v76","v96_phase_durable","v96_plain_durable",
      "v96_phase_force","v96_plain_force","v96_phase_stop","v96_plain_stop")
TRACE=("stage1","stage2","v96_status64","v96_status128",
       "v96_c64","v96_c128","v96_lbd2_64","v96_lbd2_128",
       "v96_lbd4_64","v96_lbd4_128","v96_props64","v96_props128",
       "v96_jump64","v96_jump128","v96_learn64","v96_learn128",
       "v90_learned_256","v90_lbd2_256","v90_lbd4_256",
       "v90_lbd_sum_256","v90_props_256","v90_conflicts_256",
       "v90_jumpdepth_256","v90_jumps_256",
       "learned_delta","threshold","active_pre","active_256",
       "gate_reason","hints","extended")
FIELDS=("id","group","sha256","rep","cap","mode","status","wall_s","error")+TRACE
def hash_file(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def dump(p,x):Path(p).write_text(json.dumps(x,indent=2,sort_keys=True)+"\n")
def order(s):return hashlib.sha256((SALT+"/"+s).encode()).hexdigest()
def freeze(args):
    manifests=[json.loads(Path(p).read_text()) for p in
               (args.old18,args.old12,args.old24)]
    prior={c["id"]:c for m in manifests for c in m["cases"]}
    assert len(prior)==54, len(prior)
    known=[]
    for prefix in KNOWN_PREFIX:
        found=[v for k,v in prior.items() if k.startswith(prefix)]
        assert len(found)==1,prefix
        known.append({**found[0],"group":"known_diagnostic"})
    with Path(args.scores).open(newline="",encoding="utf8") as f:raw=list(csv.DictReader(f))
    rows=[x for x in raw if x["solverid"]=="biere_cadical3[main]"]
    assert len(rows)==400
    candidates=defaultdict(list)
    for r in rows:
        if r["instanceid"] in prior:continue
        if r["status"] not in ("sat-verified","unsat-verified"):continue
        sec=float(r["runtime"])
        if not (.5<=sec<=180):continue
        label="SAT" if r["status"]=="sat-verified" else "UNSAT"
        grade="fast" if sec<5 else ("mid" if sec<30 else "slow")
        candidates[label+"_"+grade].append({
           "id":r["instanceid"],"official_label":label,"stratum":label+"_"+grade,
           "official_baseline_s":sec})
    chosen=[];attempts=[];used=set()
    for label in ("SAT","UNSAT"):
        for grade in ("fast","mid","slow"):
            bucket=sorted(candidates[label+"_"+grade],key=lambda r:order(r["id"]))
            need=2
            for candidate in bucket:
                if need==0:break
                used.add(candidate["id"])
                try:info=source.download_and_features(candidate["id"])
                except Exception as exc:
                    attempts.append({"id":candidate["id"],"ok":False,"reason":str(exc)})
                    print("V96_REJECT",candidate["id"],str(exc),flush=True)
                    continue
                chosen.append({**candidate,**info,"group":"new_prospective"})
                attempts.append({"id":candidate["id"],"ok":True})
                print("V96_NEW_ACCEPT",candidate["id"],label,grade,flush=True)
                need-=1
            if need:print("V96_QUOTA_SHORT",label,grade,need,flush=True)
    for label in ("SAT","UNSAT"):
        while sum(c["official_label"]==label for c in chosen)<6:
            bucket=sorted([c for k,v in candidates.items() if k.startswith(label+"_")
                           for c in v if c["id"] not in used],
                           key=lambda c:order("spill/"+c["id"]))
            assert bucket,"No eligible candidate for "+label
            appended=False
            for c in bucket:
                used.add(c["id"])
                try:info=source.download_and_features(c["id"])
                except Exception as exc:
                    attempts.append({"id":c["id"],"ok":False,"reason":str(exc)})
                    print("V96_SPILL_REJECT",c["id"],str(exc),flush=True)
                    continue
                chosen.append({**c,**info,"group":"new_prospective"})
                attempts.append({"id":c["id"],"ok":True})
                print("V96_SPILL_ACCEPT",c["id"],label,flush=True)
                appended=True;break
            if not appended:raise RuntimeError("No more downloadable CNFs for "+label)
    assert len(chosen)==12 and len(set(x["id"] for x in chosen))==12
    assert not(set(x["id"] for x in chosen)&set(prior))
    chosen.sort(key=lambda c:order("schedule/"+c["id"]))
    dump(args.out,{"protocol":SALT,"prior_54_excluded":sorted(prior),
        "old_manifests_sha256":{str(i):hash_file(p) for i,p in enumerate(
               (args.old18,args.old12,args.old24))},
        "known_diagnostic":known,"new_prospective":chosen,
        "all_cases":known+chosen,"rejected_or_accepted":attempts,
        "score_git_blob":SCORES_GIT_BLOB,"official_commit":REV,
        "caution":["Known six selected from observed wins - only mechanistic diagnosis",
                   "Prospective twelve selected without new DRNAS timings",
                   "Size caps and public baseline difficulty limit generality",
                   "15s PAR2 comparisons are not the official 2026 ranking"]})
    print("V96_FROZEN",len(known),len(chosen),hash_file(args.out),flush=True)
def runner(args):
    m=json.loads(Path(args.manifest).read_text())
    assert m["protocol"]==SALT and 0<=args.shard<6
    group="known_diagnostic" if args.shard<2 else "new_prospective"
    cases=(m["known_diagnostic"][args.shard*3:(args.shard+1)*3]
           if args.shard<2 else m["new_prospective"][(args.shard-2)*3:(args.shard-1)*3])
    assert len(cases)==3
    root=Path(args.out);root.mkdir(parents=True,exist_ok=True)
    core=min(os.sched_getaffinity(0));os.sched_setaffinity(0,{core})
    dump(root/"meta.json",{"group":group,"shard":args.shard,"core":core,
         "manifest_sha256":hash_file(args.manifest),"cases":[c["id"] for c in cases]})
    problems=[];rows=[]
    with (root/"raw.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader()
        for c in cases:
            ident=c["id"];dest=root/(ident+".cnf")
            chk=source.download_and_features(ident,dest)
            assert chk["sha256"]==c["sha256"],"CNF input hash mismatch"
            assert chk["features"]==c["features"],"CNF input feature mismatch"
            print("V96_VERIFIED",group,ident,chk["sha256"],flush=True)
            configs=[(15.,0),(15.,1)]+([(60.,2)] if group=="known_diagnostic" else [])
            for cap,rep in configs:
                modes=list(ARMS)
                seed=(720031+rep*911+int(c["sha256"][:8],16))%(2**32)
                random.Random(96123+int(c["id"][:8],16)+rep*1009).shuffle(modes)
                for mode in modes:
                    begin=time.monotonic();status="";error="";data={}
                    try:
                        proc=subprocess.run([str(Path(args.exe).resolve()),mode,
                             str(dest),str(seed)],capture_output=True,text=True,
                             timeout=cap,check=False)
                        sec=time.monotonic()-begin
                        if proc.returncode:raise RuntimeError("exit="+str(proc.returncode)+
                                                         " "+proc.stderr[-250:])
                        lines=[x for x in proc.stdout.splitlines()
                                 if x.startswith("DRNAS_CAUSAL\t")]
                        if len(lines)!=1:raise RuntimeError("Missing result record")
                        data=dict(x.split("=",1) for x in lines[0].split("\t")[1:])
                        if data["mode"]!=mode:raise RuntimeError("Mode mismatch")
                        status=data["answer"]
                        if status!=c["official_label"]:
                            raise RuntimeError("SAT/UNSAT contradicts official verified label")
                    except subprocess.TimeoutExpired:status="TIMEOUT";sec=cap
                    except Exception as exc:
                        status="ERROR";sec=time.monotonic()-begin;error=str(exc)
                        problems.append(ident+" "+mode+" "+error)
                    rec={"id":ident,"group":group,"sha256":c["sha256"],"rep":rep,
                         "cap":cap,"mode":mode,"status":status,
                         "wall_s":round(sec,6),"error":error}
                    rec.update({k:data.get(k,"") for k in TRACE})
                    w.writerow(rec);f.flush();rows.append(rec)
                    print("V96_TRIAL",ident[:10],group,"rep",rep,"cap",cap,mode,
                          status,rec["wall_s"],flush=True)
            dest.unlink(missing_ok=True)
    assert len(rows)==3*len(ARMS)*(3 if group=="known_diagnostic" else 2)
    # Exact causal-invariant pre-256 trajectory within a phase/no-phase trio.
    equal_fields=[x for x in TRACE if x not in ("stage2","gate_reason","extended")]
    for c in cases:
        for cap,rep in ([(15.,0),(15.,1),(60.,2)] if group=="known_diagnostic"
                        else [(15.,0),(15.,1)]):
            for start in ("v96_phase_","v96_plain_"):
                tri=[r for r in rows if r["id"]==c["id"] and r["cap"]==cap
                     and r["rep"]==rep and r["mode"].startswith(start)]
                assert len(tri)==3
                # Timeouts lose stdout; compare only observed complete recordings.
                recorded=[x for x in tri if x["status"]!="TIMEOUT"]
                for f in equal_fields:
                    if len({r[f] for r in recorded})>1:
                        problems.append("INVARIANT_ERROR "+c["id"]+" "+start+" "+f)
    dump(root/"summary.json",{"group":group,"shard":args.shard,
        "trials":len(rows),"issues":problems})
    if problems:raise RuntimeError("Invalid trial: "+str(problems[:6]))
    print("V96_SHARD_PASS",args.shard,len(rows),flush=True)
def audit(args):
    m=json.loads(Path(args.manifest).read_text())
    assert m["protocol"]==SALT
    cases={x["id"]:x for x in m["all_cases"]}
    rows=[]
    for shard in range(6):
        f=Path(args.combined)/f"v96-shard-{shard}"/"results"/"raw.csv"
        with f.open(newline="") as stream:rows+=list(csv.DictReader(stream))
    assert len(rows)==336,len(rows)
    by=defaultdict(list);seen=set()
    for r in rows:
        id=r["id"];mode=r["mode"];rep=int(r["rep"]);cap=float(r["cap"])
        k=(id,mode,rep,cap)
        assert k not in seen;seen.add(k)
        assert id in cases and mode in ARMS and r["sha256"]==cases[id]["sha256"]
        assert not r["error"] and r["status"] in ("SAT","UNSAT","TIMEOUT")
        if r["status"]!="TIMEOUT":assert r["status"]==cases[id]["official_label"]
        assert (cap,rep) in ([(15.,0),(15.,1),(60.,2)] if r["group"]=="known_diagnostic"
               else [(15.,0),(15.,1)])
        by[(id,cap,mode)].append(2*cap if r["status"]=="TIMEOUT" else float(r["wall_s"]))
    for c in cases.values():
        for cap in ([15.,60.] if c["group"]=="known_diagnostic" else [15.]):
            for mode in ARMS:
                assert len(by[(c["id"],cap,mode)])==(2 if cap==15 else 1)
    report={"protocol":SALT,"count_unique":18,"count_prospective":12,
            "total_trials":len(rows),"groups":{},"case_details":[]}
    for grp in ("known_diagnostic","new_prospective"):
        ids=[x["id"] for x in cases.values() if x["group"]==grp]
        cost={id:{mode:statistics.mean(by[(id,15.,mode)]) for mode in ARMS} for id in ids}
        means={mode:statistics.mean(cost[id][mode] for id in ids) for mode in ARMS}
        solved={mode:sum(cost[id][mode]<30 for id in ids) for mode in ARMS}
        report["groups"][grp]={"n":len(ids),"meanPAR2_15s":means,
             "solved_unique_15s":solved}
        if grp=="known_diagnostic":
            report["groups"][grp]["meanPAR2_60s"]={
                mode:statistics.mean(by[(id,60.,mode)][0] for id in ids)
                for mode in ARMS}
        for id in ids:
            # Mechanistic factorial contrast; descriptive, NOT prospective law.
            c=cost[id]
            phase=c["v96_plain_durable"]-c["v96_phase_durable"]
            gate=(c["v96_phase_stop"]-c["v96_phase_durable"])
            inter=(c["v96_plain_stop"]-c["v96_plain_durable"])-gate
            report["case_details"].append({"id":id,"group":grp,
                 "status":cases[id]["official_label"],
                 "features":cases[id]["features"],
                 "PAR2":c,"phase_advantage_positive_s":phase,
                 "durable_advantage_over_force_stop_s":gate,
                 "phase_x_gate_interaction_s":inter})
    # Pairwise result at CNF level: no treating repeated trials as independent.
    fresh=[c for c in report["case_details"] if c["group"]=="new_prospective"]
    pairs=[c["PAR2"]["ca_plain"]-c["PAR2"]["v96_phase_durable"] for c in fresh]
    rnd=random.Random(960031)
    boots=sorted(statistics.mean(rnd.choices(pairs,k=len(pairs))) for _ in range(5000))
    report["prospective_Ca_minus_phase_durable"]=statistics.mean(pairs)
    report["prospective_CI_bootstrap_95"]=[boots[125],boots[4874]]
    report["limitations"]=[
        "12 independent prospective samples - insufficient for universal law",
        "Known six chosen after observing prior outcomes, only diagnostic",
        "Pre-256 trace from completed runs only: timeouts may censor telemetry",
        "All six phase/checkpoint arms instrumented identically at 64,128,256",
        "Separate frozen CaDiCaL reference does not have matched trace hooks",
        "UNSAT has no independent DRAT/LRAT proof; checked against published label",
        "60-second cap only on diagnostic cases; cannot pool with 15s results",
        "CaDiCaL patched telemetry, identical build across all arms",
        "Runner noise and small samples; no world-record claim"]
    dump(args.out,report)
    lines=["# DRNAS V9.6 causal phase x checkpoint test","",
        "336 completed attempts; six matched interventions and two frozen controls.",
        "Pre-256 64/128/256 conflicts; only first phase hints differ before 256.",
        ""]
    for group in ("known_diagnostic","new_prospective"):
        g=report["groups"][group]
        lines+=[f"## {group} ({g['n']} distinct CNFs)","",
           "| Mode | solved unique @15s | mean PAR2 15s |","|---|---:|---:|"]
        for mode in ARMS:
            lines.append(f"| {mode} | {g['solved_unique_15s'][mode]}/{g['n']} | {g['meanPAR2_15s'][mode]:.4f} |")
        lines.append("")
    lines+=["Prospective CaDiCaL minus V96 phase/durable PAR2: "+
          f"{report['prospective_Ca_minus_phase_durable']:.5f} s;",
        "Bootstrap 95% interval: "+str(report["prospective_CI_bootstrap_95"]),
        "","## Matched per-CNF effects @15s","",
        "| CNF | Group | Phase advantage, durable | Gate durable vs stop (phase on) | Interaction |",
        "|---|---|---:|---:|---:|"]
    for x in report["case_details"]:
        lines.append(f"| {x['id'][:10]} | {x['group']} | "+
             f"{x['phase_advantage_positive_s']:.3f} | "+
             f"{x['durable_advantage_over_force_stop_s']:.3f} | "+
             f"{x['phase_x_gate_interaction_s']:.3f} |")
    lines+=["","These are experimental interventions, not a learned rule.",
       "Warning: 15s cap, hard file-size screening, prior competition published labels.",
       "No official competition placing, no general complexity-class claim."]
    Path(args.md).write_text("\n".join(lines)+"\n")
    print("\n".join(lines),flush=True)
def main():
    ap=argparse.ArgumentParser();sub=ap.add_subparsers(dest="action",required=True)
    f=sub.add_parser("freeze")
    for p in ("old18","old12","old24","scores","out"):f.add_argument("--"+p,required=True)
    r=sub.add_parser("run")
    for p in ("manifest","exe","out"):r.add_argument("--"+p,required=True)
    r.add_argument("--shard",type=int,required=True)
    a=sub.add_parser("audit")
    for p in ("manifest","combined","out","md"):a.add_argument("--"+p,required=True)
    x=ap.parse_args()
    {"freeze":freeze,"run":runner,"audit":audit}[x.action](x)
if __name__=="__main__":main()
