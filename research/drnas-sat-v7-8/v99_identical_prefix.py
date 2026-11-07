#!/usr/bin/env python3
"""DRNAS V9.9: identical unphased first-256-conflict causal late-phase experiment.

Six preselected 2026 diagnostic CNFs + six archived 2025 external CNFs.
No novel/unseen holdout claim. Exactly three V99 arms share one prefix,
then compare never/always/early-quality phase intervention after conflict 256.
The V9.1 quality threshold is frozen before these V9.9 measurements.
"""
import argparse, hashlib, json, os, random, statistics, subprocess, time
from collections import defaultdict
from pathlib import Path
import official_shortlong_select as src

src.RAW_CAP = 96*1024*1024
src.CNF_CAP = 96*1024*1024
src.VARIABLE_CAP = 1_000_000
src.CLAUSE_CAP = 4_000_000
SALT = "DRNAS-V99-matched-unphased-prefix-256-v1"
ARMS = ("v99_late_plain_force", "v99_late_phase_force",
        "v99_late_gate_force", "v96_plain_force",
        "v96_phase_force", "ca_plain")
LATE = ARMS[:3]
EARLY_FIELDS = ("stage1", "v96_status64", "v96_status128",
                "v96_c64", "v96_c128", "v96_lbd2_64", "v96_lbd2_128",
                "v96_lbd4_64", "v96_lbd4_128", "v96_props64",
                "v96_props128", "v96_jump64", "v96_jump128",
                "v96_learn64", "v96_learn128",
                "v90_learned_256", "v90_lbd2_256", "v90_lbd4_256",
                "v90_lbd_sum_256", "v90_props_256", "v90_conflicts_256",
                "v90_jumpdepth_256", "v90_jumps_256",
                "learned_delta", "threshold", "active_pre",
                "active_256", "hints", "vars", "clauses")

def save(p, o):
    Path(p).write_text(json.dumps(o, indent=2, sort_keys=True)+"\n")

def unpack(line):
    parts = line.split("\t")
    return dict(kv.split("=", 1) for kv in parts[1:])

def quality(early):
    L = int(early["v90_learned_256"])
    C = int(early["v90_conflicts_256"])
    P = int(early["v90_props_256"])
    return L >= 20 and C > 0 and 100*int(early["v90_lbd2_256"]) >= 6*L and P >= 32*C

def freeze(args):
    old = json.loads(Path(args.v96).read_text())
    ext = json.loads(Path(args.v98).read_text())
    assert len(old["known_diagnostic"]) == len(ext["new"]) == 6
    cases = []
    for i in range(6):
        known = dict(old["known_diagnostic"][i])
        external = dict(ext["new"][i])
        assert known["official_label"] in ("SAT","UNSAT")
        assert external["official_label"] in ("SAT","UNSAT")
        known["group"] = "known_2026_diagnostic"
        external["group"] = "archived_2025_external"
        cases.extend([known,external])
    assert len(cases)==12 and len({x["id"] for x in cases})==12
    save(args.out,dict(protocol=SALT,cases=cases,arms=ARMS,
        repeats=2, cap_by_group={"known_2026_diagnostic":18.,
                                 "archived_2025_external":16.},
        hypotheses=[
            "Same unphased prefix, intervention only after conflict 256",
            "V9.1 prior-derived quality gate may improve late-phase selection",
            "No regression-free or causal-generalization claim"],
        limitations=[
            "Six known 2026 cases are deliberately selected, not blind",
            "Six 2025 cases reused from V9.8 and older V7.2.1 work",
            "Two randomized-order repetitions on shared runner class",
            "Timeouts censored; SAT/UNSAT relies on archived labels"]))
    print("V99_FROZEN 12 6 6",flush=True)

def run(args):
    manifest=json.loads(Path(args.manifest).read_text())
    assert manifest["protocol"]==SALT and 0<=args.shard<6
    cases=manifest["cases"][args.shard*2:args.shard*2+2]
    assert len(cases)==2
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    core=min(os.sched_getaffinity(0))
    os.sched_setaffinity(0,{core})
    rows=[]
    for c in cases:
        path=out/(c["id"]+".cnf")
        downloaded=src.download_and_features(c["id"],path)
        assert downloaded["sha256"]==c["sha256"]
        assert downloaded["features"]==c["features"]
        cap=manifest["cap_by_group"][c["group"]]
        for rep in range(2):
            seed=(990013+991*rep+int(c["sha256"][:8],16))%(2**32)
            order=list(ARMS)
            random.Random(seed^199).shuffle(order)
            for mode in order:
                started=time.monotonic()
                error=""
                early={}
                answer={}
                try:
                    p=subprocess.run([str(Path(args.exe).resolve()),mode,str(path),
                                      str(seed)],capture_output=True,text=True,
                                      timeout=cap,check=False)
                    elapsed=time.monotonic()-started
                    if p.returncode:
                        raise RuntimeError("exit "+str(p.returncode)+" "+p.stderr[-400:])
                    traces=[x for x in p.stdout.splitlines()
                            if x.startswith("DRNAS_EARLY\t")]
                    finished=[x for x in p.stdout.splitlines()
                            if x.startswith("DRNAS_CAUSAL\t")]
                    if len(finished)!=1:
                        raise RuntimeError("Expected a single completed solver record")
                    early=unpack(traces[0]) if len(traces)==1 else {}
                    answer=unpack(finished[0])
                    if answer.get("mode")!=mode:
                        raise RuntimeError("Output mode mismatch")
                    status=answer.get("answer")
                    if status!=c["official_label"]:
                        raise RuntimeError("Wrong SAT/UNSAT or missing result")
                except subprocess.TimeoutExpired as e:
                    elapsed=cap
                    status="TIMEOUT"
                    body=e.stdout or b""
                    if isinstance(body,bytes):body=body.decode("utf-8","replace")
                    traces=[x for x in body.splitlines()
                            if x.startswith("DRNAS_EARLY\t")]
                    early=unpack(traces[-1]) if traces else {}
                except Exception as e:
                    status="ERROR"
                    elapsed=time.monotonic()-started
                    error=str(e)
                if mode.startswith("v99_") and not early:
                    raise RuntimeError("Missing V99 checkpoint trace: "+c["id"]+" "+mode)
                if status=="ERROR":
                    raise RuntimeError(c["id"]+" "+mode+" "+error)
                if early and early.get("mode")!=mode:
                    raise RuntimeError("Early trace mode mismatch")
                row=dict(id=c["id"], group=c["group"], sha256=c["sha256"],
                         rep=rep,seed=seed,mode=mode,status=status,
                         cap=cap,wall_s=round(elapsed,6),
                         early=early,final=answer,error=error)
                rows.append(row)
                print("V99_TRIAL",c["id"][:10],rep,mode,status,
                      round(elapsed,3),"LBD2",early.get("v90_lbd2_256","NA"),
                      flush=True)
        path.unlink(missing_ok=True)
    assert len(rows)==24
    save(out/"raw.json",rows)
    save(out/"meta.json",{"shard":args.shard,"cases":[x["id"] for x in cases],
                           "core":core,"trials":len(rows)})
    print("V99_SHARD_PASS",args.shard,len(rows),flush=True)

def audit(args):
    m=json.loads(Path(args.manifest).read_text())
    assert m["protocol"]==SALT
    rows=[]
    for shard in range(6):
        base=Path(args.combined)/("v99-shard-"+str(shard))/"results"
        meta=json.loads((base/"meta.json").read_text())
        assert meta["shard"]==shard and meta["trials"]==24
        assert meta["cases"]==[x["id"] for x in m["cases"][shard*2:shard*2+2]]
        rows.extend(json.loads((base/"raw.json").read_text()))
    assert len(rows)==144,len(rows)
    ids={x["id"]:x for x in m["cases"]}
    seen=set()
    per=defaultdict(dict)
    gate_selected=0
    same_prefix=0
    for r in rows:
        key=(r["id"],r["rep"],r["mode"])
        assert key not in seen
        seen.add(key)
        case=ids[r["id"]]
        assert case["sha256"]==r["sha256"]
        assert r["status"] in ("SAT","UNSAT","TIMEOUT") and not r["error"]
        assert r["cap"]==m["cap_by_group"][r["group"]]
        if r["status"]!="TIMEOUT":
            assert r["status"]==case["official_label"]
        per[(r["id"],r["rep"])][r["mode"]]=r
    for c in m["cases"]:
        for rep in range(2):
            d=per[(c["id"],rep)]
            assert set(d)==set(ARMS)
            traces=[d[mode]["early"] for mode in LATE]
            assert all(t and all(k in t for k in EARLY_FIELDS) for t in traces)
            a=traces[0]
            for b in traces[1:]:
                assert all(a[k]==b[k] for k in EARLY_FIELDS),\
                    ("V99 shared-first-256 violated",c["id"],rep)
                same_prefix+=1
            gate=quality(a)
            gate_selected+=gate
            # Checking the gate requires no post-256 knowledge.
            if d["v99_late_gate_force"]["status"]!="TIMEOUT":
                final=d["v99_late_gate_force"]["final"]
                assert int(final["v91_quality_signal"])==int(gate)
                assert int(final["v91_phase_applied"])==int(gate and int(a["stage1"])==0)
    summary={}
    details=[]
    for group in ("known_2026_diagnostic","archived_2025_external"):
        rr=[r for r in rows if r["group"]==group]
        ss={}
        for mode in ARMS:
            select=[r for r in rr if r["mode"]==mode]
            scores=[2*r["cap"] if r["status"]=="TIMEOUT" else r["wall_s"]
                    for r in select]
            ss[mode]={"solved":sum(r["status"]!="TIMEOUT" for r in select),
                      "n":len(select),"mean_PAR2_s":statistics.mean(scores)}
        summary[group]=ss
    for c in m["cases"]:
        rr=[r for r in rows if r["id"]==c["id"]]
        stats={}
        for mode in ARMS:
            subset=[x for x in rr if x["mode"]==mode]
            stats[mode]=statistics.mean(
                2*x["cap"] if x["status"]=="TIMEOUT" else x["wall_s"] for x in subset)
        ref=stats["v99_late_plain_force"]
        details.append({"id":c["id"],"group":c["group"],"PAR2":stats,
            "late_phase_minus_plain_s":stats["v99_late_phase_force"]-ref,
            "late_gate_minus_plain_s":stats["v99_late_gate_force"]-ref})
    report={"protocol":SALT,"count":len(rows),"verified_prefix_pairs":same_prefix,
            "gate_activated_runs":gate_selected,"summary":summary,
            "cases":details,"limitations":m["limitations"]}
    save(args.out,report)
    lines=["# DRNAS V9.9 — Identical-Prefix Causal Phase Experiment","",
        "144 paired measurements, six known 2026 diagnostic and six archived 2025 CNFs.",
        "Same first 256 conflicts checked with all telemetry fields on each matched V99 trio.",
        "The V9.1 quality threshold was specified BEFORE the V9.9 experiment.",
        "Known cases and reused external cases do not independently validate a selector.",
        "","Verified identical-prefix comparisons: "+str(same_prefix),
        "Quality gate activated on "+str(gate_selected)+" of 24 case/seed pairs.",""]
    for name,data in summary.items():
        lines.extend(["## "+name,"","| Strategy | Solved | Mean PAR2 seconds |",
                     "|---|---:|---:|"])
        for arm,v in data.items():
            lines.append("| "+arm+" | "+str(v["solved"])+"/"+str(v["n"])+
                         " | "+format(v["mean_PAR2_s"],".4f")+" |")
        lines.append("")
    lines.extend(["## Per-CNF comparisons","",
                  "Positive late-phase minus plain PAR2 = late phase is worse."])
    for item in details:
        lines.append("- "+item["id"][:12]+" ("+item["group"]+"): late phase minus plain "+
                     format(item["late_phase_minus_plain_s"],"+.3f")+
                     " s; adaptive minus plain "+format(item["late_gate_minus_plain_s"],"+.3f")+" s")
    lines.extend(["","No new world-record claim, no unseen benchmark success claim.",
                  "SAT/UNSAT references use published labels; UNSAT proof not independently checked."])
    Path(args.md).write_text("\n".join(lines)+"\n")
    print("\n".join(lines),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    cmd=p.add_subparsers(dest="cmd",required=True)
    for op,names in (("freeze",("v96","v98","out")),
                     ("run",("manifest","exe","out")),
                     ("audit",("manifest","combined","out","md"))):
        parser=cmd.add_parser(op)
        for name in names:parser.add_argument("--"+name,required=True)
        if op=="run":parser.add_argument("--shard",type=int,required=True)
    args=p.parse_args()
    {"freeze":freeze,"run":run,"audit":audit}[args.cmd](args)
