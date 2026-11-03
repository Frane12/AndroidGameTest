#!/usr/bin/env python3
"""R32 ORIGINAL SAT Competition 2026 GBD retrospective audit.

NOT an official SAT Competition result or a blind holdout. 14 original
SHA-verified instances from R28's frozen archive; compare pinned Kissat,
CaDiCaL 3.0.1, R29 shadow and R29 active on the same GitHub runner per case.
The R32 preview is READ ONLY: partial XOR patterns are never asserted as facts.
"""
import argparse,collections,hashlib,json,os,random,re,statistics,subprocess,time
from pathlib import Path
import r29_official_2026_gbd as original

CAP=60.0
REPS=2
SHARDS=4
MODES=("Kissat_pinned","CaDiCaL301","R29_shadow","R29_active")
MAX_PREVIEW_CLAUSES=15000
MAX_PREVIEW_GROUPS=25000
PROTOCOL="DRNAS-R32-ORIGINAL-2026-GBD-14-SHA60-RISK-AUDIT-V1"

def check(ok,msg):
    if not ok: raise RuntimeError("R32_OFFICIAL_AUDIT_FAIL: "+str(msg))

def sha(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda:f.read(1<<20),b""):h.update(chunk)
    return h.hexdigest()

def preview(path):
    """Bounded, incomplete DIMACS prefix scan, never a certification or solution."""
    groups=collections.defaultdict(set)
    widths=collections.Counter()
    header_n=header_m=None
    clauses=0
    seen_header=False
    pending=[]
    stopped=False
    started=time.monotonic()
    with Path(path).open("rt",encoding="ascii",errors="replace") as f:
        for raw in f:
            line=raw.strip()
            if not line or line.startswith("c") or line.startswith("%"):continue
            if line.startswith("p "):
                words=line.split()
                check(len(words)==4 and words[1]=="cnf","Invalid DIMACS header")
                header_n,header_m=map(int,words[2:])
                check(not seen_header,"Repeated DIMACS header")
                seen_header=True
                continue
            if not seen_header:raise ValueError("No DIMACS header before clauses")
            for token in line.split():
                literal=int(token)
                if literal:
                    pending.append(literal)
                    if len(pending)>200000:
                        stopped=True;break
                    continue
                cl=pending;pending=[]
                clauses+=1; k=len(cl);widths[k]+=1
                if 2<=k<=6 and len({abs(x) for x in cl})==k and len(groups)<=MAX_PREVIEW_GROUPS:
                    ordered=sorted(cl,key=lambda x:abs(x))
                    key=tuple(abs(x) for x in ordered)
                    mask=sum(1<<i for i,x in enumerate(ordered) if x<0)
                    groups[key].add(mask)
                if clauses>=MAX_PREVIEW_CLAUSES:
                    stopped=True;break
            if stopped:break
    complete=near=partial=0
    for key,seen in groups.items():
        k=len(key)
        even={m for m in range(1<<k) if m.bit_count()%2==0}
        odd={m for m in range(1<<k) if m.bit_count()%2==1}
        if even<=seen or odd<=seen:complete+=1
        elif max(len(even&seen),len(odd&seen))>=max(2,2**(k-1)-1):near+=1
        elif len(seen)>1:partial+=1
    return dict(variables=header_n,declared_clauses=header_m,
        scanned_clauses=clauses,prefix_only=stopped or clauses!=header_m,
        sample_limit_clauses=MAX_PREVIEW_CLAUSES,
        widths={str(k):v for k,v in widths.most_common(12)},
        candidate_groups=len(groups),complete_parity_groups_in_prefix=complete,
        near_complete_uncertified_groups=near,partial_uncertified_groups=partial,
        preview_seconds=round(time.monotonic()-started,6),
        note="Prefix XOR signals are diagnostics only; never insert unproven constraints.")

def diagnose(args):
    inp=Path(args.inputs)
    spec=json.loads((inp/"manifest.json").read_text())
    check(len(spec["cases"])==14,"Expected exactly 14 original competition files")
    rows=[]
    for case in spec["cases"]:
        path=inp/case["path"]
        check(sha(path)==case["raw_sha256"],"Official source SHA drift "+case["id"])
        size=path.stat().st_size
        item=dict(id=case["id"],sha256=case["raw_sha256"],source=case["source"],
                  role=case["source_role"],file_bytes=size,expected=case["expected"])
        try:
            p=preview(path)
            item.update(p)
            guard=[]
            if size>12*1024*1024:guard.append("file_gt_12MiB")
            if p["variables"] is not None and p["variables"]>3000:guard.append("vars_gt_3000")
            if p["declared_clauses"] is not None and p["declared_clauses"]>150000:guard.append("clauses_gt_150k")
            item["r29_static_guard"]=guard
            started=time.monotonic()
            try:
                proc=subprocess.run([str(Path(args.r29).resolve()),str(path.resolve()),
                                     str(Path(args.kissat).resolve()),"--classify-only"],
                                   capture_output=True,text=True,errors="replace",timeout=20)
                item["r29_exit"]=proc.returncode
                route=next((x[len("c R29_ROUTE "):] for x in proc.stdout.splitlines()
                            if x.startswith("c R29_ROUTE ")),"")
                item["r29_route"]=route
                check(proc.returncode==0 and bool(route),"R29 classify error "+case["id"])
                if guard:check(route.startswith("fallback reason=input_guard"),
                               "R29 static size gate not honored "+case["id"])
            except subprocess.TimeoutExpired:
                item["r29_route"]="classification_timeout"
                item["risk"]="preflight_analysis_hang"
            item["r29_probe_seconds"]=round(time.monotonic()-started,6)
            item["risk_flags"]=guard+(
                ["uncertified_partial_xor_do_not_infer"] if p["near_complete_uncertified_groups"]
                 or p["partial_uncertified_groups"] else [])+(
                ["prefix_only_not_full_structure"] if p["prefix_only"] else [])
        except Exception as exc:
            item["error"]=str(exc)
            item["risk_flags"]=["diagnostic_failed"]
        rows.append(item)
        print("R32_OFFICIAL_GATE",json.dumps(item,sort_keys=True),flush=True)
    Path(args.out).write_text(json.dumps(dict(protocol=PROTOCOL,read_only=True,
        limitations=["Previously seen retrospective official benchmark, not blind holdout",
                     "R29 native caps: 12MiB, 3000 variables, 150000 clauses",
                     "A prefix XOR pattern cannot certify an unseen full CNF",
                     "Native solver timing includes R29 probe/preprocessing overhead",
                     "No speedups inferred from classify-only"],rows=rows),indent=2)+"\n")
    print("R32_OFFICIAL_GATE_DONE",len(rows),flush=True)

def execute(path,mode,bins):
    if mode=="Kissat_pinned":cmd=[str(bins["kissat"]),str(path)]
    elif mode=="CaDiCaL301":cmd=[str(bins["cadical"]),str(path)]
    else:cmd=[str(bins["r29"]),str(path),str(bins["kissat"])]
    env=os.environ.copy()
    env["R29_MODE"]="active" if mode=="R29_active" else "shadow"
    start=time.monotonic()
    try:
        p=subprocess.run(cmd,env=env,capture_output=True,text=True,
                         errors="replace",timeout=CAP)
        elapsed=time.monotonic()-start
        check(p.returncode in (10,20),"Solver failure rc="+str(p.returncode)+
              " stderr="+p.stderr[-300:])
        status="SAT" if p.returncode==10 else "UNSAT"
        route=next((x[len("c R29_ROUTE "):] for x in p.stdout.splitlines()
                    if x.startswith("c R29_ROUTE ")),"")
        if mode.startswith("R29_"):check(bool(route),"Missing R29 route marker")
        reason=next((x.split("reason=",1)[1].split()[0] for x in
                     p.stdout.splitlines() if x.startswith("c R29_ROUTE fallback reason=")),"")
    except subprocess.TimeoutExpired:
        elapsed=time.monotonic()-start
        status="TIMEOUT";route="timeout";reason=""
    return dict(status=status,seconds=round(elapsed,6),
                PAR2=120.0 if status=="TIMEOUT" else round(elapsed,6),
                route=route,reason=reason)

def run(args):
    spec=json.loads((Path(args.inputs)/"manifest.json").read_text())
    check(len(spec["cases"])==14,"Official case count mismatch")
    check(0<=args.shard<SHARDS,"Invalid shard")
    bins={name:Path(getattr(args,name)).resolve() for name in ("r29","kissat","cadical")}
    check(all(p.is_file() for p in bins.values()),"Missing binaries")
    if hasattr(os,"sched_getaffinity"):
        a=os.sched_getaffinity(0)
        if a:os.sched_setaffinity(0,{min(a)})
    output=Path(args.outdir);output.mkdir(parents=True,exist_ok=True)
    meta=dict(protocol=PROTOCOL,shard=args.shard,
        manifest_sha256=sha(Path(args.inputs)/"manifest.json"),
        binaries={k:sha(v) for k,v in bins.items()},
        cpu=next((x for x in Path("/proc/cpuinfo").read_text().splitlines()
                  if x.startswith("model name")),"unknown"),cap=CAP,repeats=REPS)
    (output/"metadata.json").write_text(json.dumps(meta,indent=2)+"\n")
    rows=[]
    for case in spec["cases"][args.shard::SHARDS]:
        path=(Path(args.inputs)/case["path"]).resolve()
        check(sha(path)==case["raw_sha256"],"Source hash mismatch "+case["id"])
        for rep in range(REPS):
            modes=list(MODES)
            random.Random(int(hashlib.sha256((case["raw_sha256"]+"/r32/"+str(rep)).encode()).hexdigest(),16)).shuffle(modes)
            for mode in modes:
                result=execute(path,mode,bins)
                check(result["status"] in ("TIMEOUT",case["expected"].upper()),
                      "WRONG SAT ANSWER "+case["id"]+" "+mode+" "+str(result))
                row=dict(id=case["id"],role=case["source_role"],sha256=case["raw_sha256"],
                         rep=rep,mode=mode,**result)
                rows.append(row)
                (output/"rows.json").write_text(json.dumps(rows,indent=2)+"\n")
                print("R32_OFFICIAL_TRIAL",json.dumps(row,sort_keys=True),flush=True)
        observed={x["status"] for x in rows if x["id"]==case["id"]} - {"TIMEOUT"}
        check(len(observed)<=1,"Conflicting SAT/UNSAT answers "+case["id"])
    print("R32_OFFICIAL_SHARD_DONE",args.shard,len(rows),flush=True)

def aggregate(args):
    root=Path(args.inputs)
    spec=json.loads((root/"manifest.json").read_text())
    gates=json.loads((root/"r32-official-gates.json").read_text())
    check(gates["protocol"]==PROTOCOL and len(gates["rows"])==14,"Missing diagnostic cohort")
    allrows=[];binaries=set();cpus=set()
    for shard in range(SHARDS):
        loc=Path(args.combined)/("r32-official-shard-"+str(shard))/"results"
        md=json.loads((loc/"metadata.json").read_text())
        check(md["protocol"]==PROTOCOL and md["shard"]==shard and
              md["manifest_sha256"]==sha(root/"manifest.json"),"Shard manifest/protocol mismatch")
        binaries.add(json.dumps(md["binaries"],sort_keys=True))
        cpus.add(md["cpu"])
        piece=json.loads((loc/"rows.json").read_text())
        check(len(piece)==len(spec["cases"][shard::SHARDS])*REPS*len(MODES),
              "Missing paired attempts shard "+str(shard))
        allrows.extend(piece)
    check(len(binaries)==1 and len(allrows)==14*REPS*len(MODES),"Non-reproducible comparison")
    bycase=[];summary={}
    for case in spec["cases"]:
        rows=[r for r in allrows if r["id"]==case["id"]]
        t={};routes={}
        for mode in MODES:
            v=[r for r in rows if r["mode"]==mode]
            check(len(v)==REPS,"Missing repeats "+case["id"]+mode)
            t[mode]=round(statistics.median(r["PAR2"] for r in v),6)
            if mode.startswith("R29_"):routes[mode]=v[0]["route"]
        bycase.append(dict(id=case["id"],role=case["source_role"],
            expected=case["expected"],sha256=case["raw_sha256"],times=t,routes=routes))
    for mode in MODES:
        subset=[r for r in allrows if r["mode"]==mode]
        summary[mode]=dict(solved_both_repeats=sum(all(r["status"]!="TIMEOUT" for r in subset if r["id"]==c["id"])
                               for c in spec["cases"]),cases=14,
            timeout_attempts=sum(r["status"]=="TIMEOUT" for r in subset),
            sum_case_median_PAR2=round(sum(c["times"][mode] for c in bycase),6),
            regressions_2x_vs_Kissat=sum(c["times"][mode]>2*c["times"]["Kissat_pinned"]
                                        for c in bycase),
            routes=dict(collections.Counter(r["route"].split()[0] if r["route"] else "baseline" for r in subset)),
            fallback_reasons=dict(collections.Counter(r["reason"] for r in subset if r["reason"])))
    base=summary["Kissat_pinned"]["sum_case_median_PAR2"]
    for mode in MODES:
        score=summary[mode]["sum_case_median_PAR2"]
        summary[mode]["gain_vs_Kissat_pct"]=round(100*(base-score)/base,4) if base else None
    cautions=["Retrospective 14 original SAT Competition 2026 Main-track GBD inputs, NOT blind or full competition",
             "R32 currently contains read-only XOR gate analysis; no new R32 active solver was evaluated",
             "Original 2026 official ranking uses different hardware, timeout and full test set",
             "Main Track requires independently checkable UNSAT proofs, not demonstrated by this run",
             "SAT/UNSAT checked against frozen source labels, not independent new proof validation",
             "Large input R29 input_guard is honest unchanged-Kissat fallback, not XOR acceleration",
             "Times include R29 wrapper overhead; two paired repeats per formula; 60s cap, PAR2=120s",
             "GitHub Actions CPU model may differ between shards; per-formula arms use the same shard."]
    data=dict(protocol=PROTOCOL,summary=summary,per_case=bycase,diagnostics=gates,
       rows=allrows,binary_sha256=json.loads(next(iter(binaries))),cpus=sorted(cpus),
       warnings=cautions)
    Path(args.out_json).write_text(json.dumps(data,indent=2)+"\n")
    md=["# DRNAS SAT R32 official-2026 input diagnostic and R29 paired comparison",
        "**Retrospective subset only, NOT an official competition rank**",
        "14 SHA-frozen original SAT Competition 2026 Main GBD inputs, 4 arms × 2 paired repeats, 60s cap.",
        "R32 XOR scanning is read-only, not a modified R32 active solver.","",
        "| Solver | Solved / 14 | Sum median PAR-2 (s) | Timeouts / 28 | >2x regressions vs Kissat | Gain vs Kissat |",
        "|---|---:|---:|---:|---:|---:|"]
    for mode,s in summary.items():
        md.append(f"| {mode} | {s['solved_both_repeats']}/14 | {s['sum_case_median_PAR2']:.4f} | {s['timeout_attempts']} | {s['regressions_2x_vs_Kissat']} | {s['gain_vs_Kissat_pct']:+.2f}% |")
    md+=["","## Per formula (median PAR-2 seconds)", "| Formula | Kissat | CaDiCaL | R29 shadow | R29 active | R29 route |",
         "|---|---:|---:|---:|---:|---|"]
    for c in bycase:
        v=c["times"]
        md.append(f"| {c['id']} | {v['Kissat_pinned']:.3f} | {v['CaDiCaL301']:.3f} | {v['R29_shadow']:.3f} | {v['R29_active']:.3f} | {c['routes']['R29_shadow'][:95]} |")
    md+=["","## R29 input-gate diagnostics","| Formula | KiB | Vars | Clauses | Native guard | R29 classification | XOR in prefix |",
        "|---|---:|---:|---:|---|---|---:|"]
    for g in gates["rows"]:
        md.append(f"| {g['id']} | {g['file_bytes']/1024:.0f} | {g.get('variables','?')} | {g.get('declared_clauses','?')} | {','.join(g.get('r29_static_guard',[])) or 'none'} | {g.get('r29_route','?')[:75]} | {g.get('complete_parity_groups_in_prefix',0)} |")
    md+=["","## Risks / next implementation constraints"]+[f"- {x}" for x in cautions]
    md+=["","## Diagnostic exceptions / warning counts"]
    risk=collections.Counter(z for g in gates["rows"] for z in g.get("risk_flags",[]))
    for k,v in sorted(risk.items()):md.append(f"- {k}: {v}")
    Path(args.out_md).write_text("\n".join(md)+"\n")
    print("R32_OFFICIAL_AUDIT_PASS",len(allrows),json.dumps(summary,sort_keys=True),flush=True)

def main():
    p=argparse.ArgumentParser()
    subs=p.add_subparsers(dest="action",required=True)
    q=subs.add_parser("diagnose")
    for k in ("inputs","r29","kissat","out"):q.add_argument("--"+k,required=True)
    q=subs.add_parser("run")
    for k in ("inputs","r29","kissat","cadical","outdir"):q.add_argument("--"+k,required=True)
    q.add_argument("--shard",type=int,required=True)
    q=subs.add_parser("aggregate")
    for k in ("inputs","combined","out-json","out-md"):q.add_argument("--"+k,required=True)
    a=p.parse_args()
    if a.action=="diagnose":diagnose(a)
    elif a.action=="run":run(a)
    else:aggregate(a)
if __name__=="__main__":main()
