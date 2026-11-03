#!/usr/bin/env python3
"""R32b frozen native GF2 shadow: compare pinned clean Kissat vs same native
instrumented binary with probe disabled vs probe enabled.

Original C++/Python solver strategy is untouched. A native C module captures
original DIMACS and computes the *proven* parity-vs-original-BCP gap at root
and optional conflict-free native trail projections. No inferred units are
ever added; no strategy decisions are changed. Includes 21 genuinely new
SHA-distinct synthetic sources and 30 prior R31 diagnostic controls.
"""
from __future__ import annotations
import argparse,collections,csv,hashlib,json,os,random,re,statistics,subprocess
import time
from pathlib import Path
import r30_passive_monitor as r30
import r31_consistent_gf2_test as r31

PROTO="DRNAS-R32B-NATIVE-READONLY-GF2-20261103-v1"
SOURCE_PROTO=r31.PROTO
REPS=2
SHARDS=4
CAP=4.0
MODES=("clean","native_off","R32B_native_shadow")
EXTRA=(10,11,12)

def check(value,message):
    if not value:raise RuntimeError("R32B_AUDIT_FAILURE "+str(message))
def sha(x):return hashlib.sha256(x.read_bytes() if isinstance(x,Path) else x).hexdigest()
def freeze(previous,dest):
    previous=Path(previous);out=Path(dest);out.mkdir(parents=True,exist_ok=True)
    source=json.loads((previous/"manifest.json").read_text())
    check(source["protocol"]==SOURCE_PROTO and len(source["cases"])==30,"Expected valid R31 original frozen corpus")
    cases=[]
    for old in source["cases"]:
        raw=(previous/old["file"]).read_bytes()
        check(sha(raw)==old["sha256"],"Prior R31 SHA mismatch")
        (out/old["file"]).write_bytes(raw)
        cases.append(dict(name=old["file"],family=old["family"],expected=old["expected"],
                          sha256=sha(raw),cohort="prior_R31_diagnostic",size=len(raw)))
    for family in r31.FAMILIES:
        for idx in EXTRA:
            n,clauses,expected,_truth=r31.make_case(family,idx)
            raw=r31.encode(n,clauses)
            name=f"r32b_new_{family}_{idx:02d}.cnf"
            (out/name).write_bytes(raw)
            cases.append(dict(name=name,family=family,expected=expected,
                              sha256=sha(raw),cohort="new_SHA_distinct",size=len(raw)))
    check(len(cases)==51 and len({x["sha256"] for x in cases})==51,
          "Expected 51 unique SHA-distinct CNFs")
    (out/"manifest.json").write_text(json.dumps(dict(
        protocol=PROTO,source_protocol=SOURCE_PROTO,
        previous_manifest_sha256=sha(previous/"manifest.json"),
        cap=CAP,repeats=REPS,shards=SHARDS,modes=MODES,
        cases=cases,warnings=[
          "R32b is purely passive C-in-process structural measurement",
          "30 R31 originals are known diagnostics, 21 new SHA-distinct synthetic formulas",
          "2 original SAT Competition GBD controls are previously seen and not a fresh blind test",
          "A naive original-CNF BCP closure conditioned on projected preprocessed trail is not an internal solver propagation trace",
          "Native shadow only reports complete parity patterns or sound single-variable-parent resolvents",
          "No active GF2 unit insertion, phase/restart change, or learned clause intervention",
          "Only complete external mapped native trails can support conditioned GF2 gap",
          "Time includes native static CNF capture and shadow elimination",
          "No universal SAT speedup or competition ranking claims"
        ]),indent=2)+"\n")
    (out/"cnf.sha256").write_text("".join(f'{x["sha256"]}  {x["name"]}\n' for x in cases))
    print("R32B_FROZEN",len(cases),sha(out/"manifest.json"),flush=True)

def parse_native(text):
    records=[]
    for line in text.splitlines():
        if line.startswith("c R32B_PROBE "):
            m=dict(re.findall(r"([A-Za-z_]+)=([A-Za-z_0-9.+-]+)",line))
            samples=line.split("samples=",1)[1].split()[0] if "samples=" in line else ""
            try:sample=[int(x) for x in samples.split(",") if x]
            except ValueError:sample=[]
            row={k:(float(v) if k.endswith("_us") else int(v)
                      if k in ("mark","vars","clauses","literals","equations","resolved",
                               "trail_assigned","bcp_assigned","rank","extra") else v)
                      for k,v in m.items() if k!="samples"}
            row["sample"]=sample;records.append(row)
    final=re.findall(r"c R32B_FINAL status=(\d+) conflicts=(\d+) decisions=(\d+) restarts=(\d+) propagations=(\d+) learned=(\d+)",text)
    check(len(final)<=1,"Duplicate native final metrics")
    keys=("status","conflicts","decisions","restarts","propagations","learned")
    metrics={k:int(v) for k,v in zip(keys,final[0])} if final else None
    for row in records:
        check(row["signal"] in ("GF2_UNSAT","ORIGINAL_BCP_CONFLICT","TRAIL_INVALID",
                  "ELIMINATION_CAP","CONSISTENT_GAP","CONSISTENT_NO_GAP","INPUT_GUARD","TRAIL_GUARD"),
              "Unknown native shadow taxonomy "+row["signal"])
        if row["signal"]=="GF2_UNSAT":
            check(row.get("extra",0)==0,"UNSAT must never be treated as units")
    return records,metrics

def get_root(probes):
    root=[p for p in probes if p.get("mark")==9999]
    check(len(root)==1,"R32b must capture exactly one original-CNF root probe")
    return root[0]

def compare_root(root,path):
    signal=root["signal"]
    parsed,meta=r30.parse_dimacs(path)
    if parsed is None:
        return dict(status="old_python_guard",why=meta["guard"],native_signal=signal)
    proof,context=r31.structure(path)
    expected=proof["signal"]
    mapping={
        "ROOT_GF2_UNSAT":"GF2_UNSAT",
        "CONSISTENT_EXTRA_UNITS":"CONSISTENT_GAP",
        "CONSISTENT_NO_UNITS":"CONSISTENT_NO_GAP",
        "ROOT_BCP_CONFLICT":"ORIGINAL_BCP_CONFLICT",
        "INPUT_GUARD":"INPUT_GUARD"
    }
    check(signal==mapping[expected],
          f"Native root {signal} != independently validated {expected} on {path.name}")
    if expected=="CONSISTENT_EXTRA_UNITS":
        check(root["extra"]==len(proof["units"]),
              f"Native unit count {root['extra']} not equal to certified {len(proof['units'])}")
        # Native printed samples are individually checked vs independently
        # proven signed literals, not treated as a model or UNSAT proof.
        expected_signed={x["literal"] for x in proof["units"]}
        check(set(root["sample"])<=expected_signed,"Native GF2 sample contains false consequence")
    if expected=="ROOT_GF2_UNSAT":
        check(root["extra"]==0,"Contradiction was wrongly counted as extra units")
    return dict(status="independent_proof_match",expected=expected,
                proven_units=len(proof["units"]),signal=signal,
                sampled_literals=root["sample"],certified=proof)

def sat_check(path,output):
    parsed,meta=r30.parse_dimacs(path)
    if parsed is None:return "large_input_no_model_audit"
    n,clauses=parsed
    check(r30.model_valid(output,clauses,n),"SAT witness failed original CNF validation")
    return "SAT_model_on_original_valid"

def one_trial(case,path,mode,bins):
    cmd=[str(bins["clean"] if mode=="clean" else bins["native"]),str(path)]
    env=os.environ.copy()
    env["R32B_MODE"]="shadow" if mode=="R32B_native_shadow" else "off"
    start=time.monotonic()
    try:
        p=subprocess.run(cmd,capture_output=True,text=True,errors="replace",timeout=CAP,env=env)
        elapsed=time.monotonic()-start
        check(p.returncode in (10,20),f"Bad Kissat exit {p.returncode} {p.stderr[-250:]}")
        status="SAT" if p.returncode==10 else "UNSAT"
        check(not case["expected"] or status==case["expected"].upper(),"Original truth-label mismatch")
        verification=sat_check(path,p.stdout) if status=="SAT" else "reference_label_only"
        stdout=p.stdout
    except subprocess.TimeoutExpired as e:
        elapsed=time.monotonic()-start
        status="TIMEOUT";verification="not_applicable"
        stdout=e.stdout or b""
        if isinstance(stdout,bytes):stdout=stdout.decode(errors="replace")
    probes,final=parse_native(stdout)
    if mode=="clean":check(not probes and not final,"Clean Kissat unexpectedly instrumented")
    if mode=="native_off":check(not probes,"Off mode ran a probe")
    proof=None;root=None
    if mode=="R32B_native_shadow":
        root=get_root(probes)
        proof=compare_root(root,path)
        check(proof["status"] in ("independent_proof_match","old_python_guard"),
              "Bad root proof validation status")
    if status!="TIMEOUT" and mode!="clean":
        check(final is not None,"Native final counters missing on finished solve")
        check(final["status"]==(10 if status=="SAT" else 20),"Native final status not correct")
    return dict(status=status,seconds=round(elapsed,6),
                par2=round(elapsed,6) if status!="TIMEOUT" else 2*CAP,
                verification=verification,root=root,root_proof=proof,
                probes=probes,final=final)

def measure(a):
    root=Path(a.inputs);spec=json.loads((root/"manifest.json").read_text())
    check(spec["protocol"]==PROTO and spec["modes"]==list(MODES),"Protocol changed")
    check(0<=a.shard<SHARDS,"Bad shard")
    if hasattr(os,"sched_getaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    bins={key:Path(getattr(a,key)).resolve() for key in ("clean","native")}
    check(all(p.is_file() for p in bins.values()),"Missing binary")
    out=Path(a.outdir);out.mkdir(parents=True,exist_ok=True)
    (out/"metadata.json").write_text(json.dumps(dict(
        shard=a.shard,manifest_sha256=sha(root/"manifest.json"),
        binary_sha256={key:sha(value) for key,value in bins.items()}),indent=2))
    rows=[]
    for case in spec["cases"][a.shard::SHARDS]:
        path=root/case["name"]
        check(sha(path)==case["sha256"],"Unfrozen input")
        for rep in range(REPS):
            modes=list(MODES)
            random.Random(int(sha((case["sha256"]+":"+str(rep)+":shuffle").encode()),16)).shuffle(modes)
            for mode in modes:
                result=one_trial(case,path,mode,bins)
                rows.append(dict(case=case["name"],family=case["family"],
                                 cohort=case["cohort"],repeat=rep,mode=mode,**result))
                (out/"rows.json").write_text(json.dumps(rows,indent=1)+"\n")
                print("R32B_TRIAL",a.shard,case["name"],rep,mode,result["status"],
                      result["seconds"],"conflicts",
                      result["final"]["conflicts"] if result["final"] else "censored",
                      "signal",result["root"]["signal"] if result["root"] else "-",
                      "probes",len(result["probes"]),flush=True)
        labels={z["status"] for z in rows if z["case"]==case["name"]}-{"TIMEOUT"}
        check(len(labels)<=1,"Contradictory SAT results")
    print("R32B_SHARD_COMPLETE",a.shard,len(rows),flush=True)

def aggregate(a):
    folder=Path(a.inputs);spec=json.loads((folder/"manifest.json").read_text())
    rows=[];binary=set()
    for shard in range(SHARDS):
        out=Path(a.combined)/f"r32b-shard-{shard}"/"results"
        meta=json.loads((out/"metadata.json").read_text())
        check(meta["shard"]==shard and meta["manifest_sha256"]==sha(folder/"manifest.json"),
              "Manifest drift")
        binary.add(json.dumps(meta["binary_sha256"],sort_keys=True))
        part=json.loads((out/"rows.json").read_text())
        check(len(part)==len(spec["cases"][shard::SHARDS])*REPS*len(MODES),
              "Incomplete paired shard")
        rows+=part
    check(len(rows)==51*REPS*len(MODES) and len(binary)==1,
          "Expected 306 identical-binary attempts")
    bycase={x["name"]:[z for z in rows if z["case"]==x["name"]] for x in spec["cases"]}
    conflicts_mismatch=[]
    for case,data in bycase.items():
        for rep in range(REPS):
            off=next(z for z in data if z["repeat"]==rep and z["mode"]=="native_off")
            on=next(z for z in data if z["repeat"]==rep and z["mode"]=="R32B_native_shadow")
            if off["final"] and on["final"]:
                if any(off["final"][k]!=on["final"][k]
                       for k in ("status","conflicts","decisions","restarts","propagations","learned")):
                    conflicts_mismatch.append(dict(case=case,repeat=rep,
                                                   off=off["final"],on=on["final"]))
    # Any native policy drift is a hard failure and must not be hidden in
    # a summary or called a passive monitor.
    check(not conflicts_mismatch,"READ_ONLY_NATIVE_COUNTER_DRIFT "+json.dumps(conflicts_mismatch[:3]))
    families=["ALL","prior_R31_diagnostic","new_SHA_distinct"]+list(r31.FAMILIES)+["official_gbd_2026"]
    summaries={}
    for family in families:
        if family in ("prior_R31_diagnostic","new_SHA_distinct"):
            selected=[x for x in spec["cases"] if x["cohort"]==family]
        elif family=="ALL":selected=spec["cases"]
        else:selected=[x for x in spec["cases"] if x["family"]==family]
        subset=[x["name"] for x in selected]
        d={}
        for mode in MODES:
            arows=[r for r in rows if r["mode"]==mode and r["case"] in subset]
            check(len(arows)==len(selected)*REPS,"Category missing trials")
            d[mode]=dict(sum_PAR2=round(sum(x["par2"] for x in arows),6),
                         solved=sum(all(z["status"]!="TIMEOUT" for z in bycase[c] if z["mode"]==mode)
                                    for c in subset),
                         timeouts=sum(x["status"]=="TIMEOUT" for x in arows))
        on=[r for r in rows if r["mode"]=="R32B_native_shadow" and r["case"] in subset]
        rootSignals=collections.Counter(x["root"]["signal"] for x in on)
        gap=[p for r in on for p in r["probes"] if p.get("mark")!=9999]
        d["root_signals"]=dict(rootSignals)
        d["native_root_extra_unit_sum"]=sum(x["root"].get("extra",0) for x in on)
        d["native_dynamic_snapshots"]=len(gap)
        d["dynamic_consistent_gap_snapshots"]=sum(x["signal"]=="CONSISTENT_GAP" for x in gap)
        d["dynamic_GF2_UNSAT_snapshots"]=sum(x["signal"]=="GF2_UNSAT" for x in gap)
        d["root_probe_us_median"]=round(statistics.median(x["root"].get("probe_us",
                      x["root"].get("elapsed_us",0)) for x in on),1) if on else 0
        b=d["native_off"]["sum_PAR2"];c=d["R32B_native_shadow"]["sum_PAR2"]
        d["shadow_vs_native_off_pct"]=round(100*(c-b)/max(1e-9,b),3)
        summaries[family]=d
        print("R32B_SUMMARY",family,json.dumps(d,sort_keys=True),flush=True)
    per=[]
    for case in spec["cases"]:
        rr=bycase[case["name"]]
        times={m:round(statistics.median(x["par2"] for x in rr if x["mode"]==m),6)
               for m in MODES}
        on=next(x for x in rr if x["mode"]=="R32B_native_shadow")
        per.append(dict(name=case["name"],family=case["family"],cohort=case["cohort"],
                        root=on["root"],validated_proof=on["root_proof"]["status"],
                        checkpoints=[x for x in on["probes"] if x.get("mark")!=9999],
                        times=times))
    final=dict(protocol=PROTO,manifest_sha256=sha(folder/"manifest.json"),
               binaries=json.loads(next(iter(binary))),summary=summaries,
               per_case=per,rows=rows,
               caution=["This is a passive natively compiled GF(2) observer, not an active adaptive SAT solver",
                        "Proven full-clause XORs and bounded single-variable resolvents only",
                        "BCP on original CNF under exported Kissat trail projection does not include learned clauses",
                        "Baseline/outcome comparison is diagnostic, not a randomized blinded external industrial competition",
                        "Two previously seen official formulas are out-of-scope guards not positive examples"])
    Path(a.output).write_text(json.dumps(final,indent=2)+"\n")
    md=["# DRNAS R32b: native in-process certified GF(2) shadow / BCP gap",
        "51 SHA-distinct formulas x 2 repeats x 3 arms = 306 attempts.",
        "Pinned clean Kissat, compiled Kissat + observer OFF, identical compiled Kissat with observer ON.",
        "No added clauses or search interventions. Native final counters must match OFF vs ON.",
        "Timed in-process scan/BCP/GF2 cost is included in process wall time.",
        "**The 30 old R31 cases are diagnostic; 21 new instances have SHA-distinct seeds.**",
        "", "| Category | Clean PAR-2 s | Native OFF PAR-2 s | R32b Shadow PAR-2 s | Shadow cost vs OFF | Root GF2 extras | Dynamic snapshots |",
        "|---|---:|---:|---:|---:|---:|---:|"]
    for fam,d in summaries.items():
        md.append("| "+fam+" | "+" | ".join(f"{d[m]['sum_PAR2']:.4f}" for m in MODES)+
                  f" | {d['shadow_vs_native_off_pct']:+.2f}% | {d['native_root_extra_unit_sum']} | {d['native_dynamic_snapshots']} |")
    md+=["","## Formula-level proof status and native root classification",
         "| Formula | Root signal | Verified? | New units | Clean PAR-2 | R32b PAR-2 |",
         "|---|---|---|---:|---:|---:|"]
    for x in per:
        md.append(f"| {x['name']} | {x['root']['signal']} | {x['validated_proof']} | {x['root'].get('extra',0)} | "
                  f"{x['times']['clean']:.5f} | {x['times']['R32B_native_shadow']:.5f} |")
    Path(a.report).write_text("\n".join(md)+"\n")
    with Path(a.csv).open("w",newline="") as f:
        w=csv.writer(f)
        w.writerow(["file","family","cohort","root_signal","root_extra",
                    "clean_PAR2","native_off_PAR2","native_shadow_PAR2",
                    "native_probe_us","dynamic_snapshots"])
        for x in per:
            z=x["times"];root=x["root"]
            w.writerow([x["name"],x["family"],x["cohort"],root["signal"],root.get("extra",0),
                        z["clean"],z["native_off"],z["R32B_native_shadow"],
                        root.get("probe_us",root.get("elapsed_us",0)),len(x["checkpoints"])])
    print("R32B_AUDIT_PASS",len(rows),"attempts",len(per),"cases",flush=True)
def main():
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest="command",required=True)
    a=sub.add_parser("freeze");a.add_argument("--previous",required=True);a.add_argument("--dest",required=True)
    a=sub.add_parser("measure")
    for s in ("inputs","clean","native","outdir"):a.add_argument("--"+s,required=True)
    a.add_argument("--shard",type=int,required=True)
    a=sub.add_parser("aggregate")
    for s in ("inputs","combined","output","report","csv"):a.add_argument("--"+s,required=True)
    arg=p.parse_args()
    if arg.command=="freeze":freeze(arg.previous,arg.dest)
    elif arg.command=="measure":measure(arg)
    else:aggregate(arg)
if __name__=="__main__":main()
