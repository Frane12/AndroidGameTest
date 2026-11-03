#!/usr/bin/env python3
"""DRNAS R32f: trustworthy multicore SAT portfolio benchmark.
A race between native OFF and previously proof-audited R32e active. Both
attempt the *same original formula*; only the first independently validated
answer can win. Immediately kill and reap the loser. Measure *end-to-end*
wall time, child CPU cost, and winner identity, with pinned separate cores.
Compare to standalone clean, native OFF and R32e on SHA-new synthetic cases.
A portfolio is not a statistical classifier and uses more CPU.
"""
from __future__ import annotations
import argparse,collections,hashlib,json,os,random,re,resource,statistics
import subprocess,tempfile,time
from pathlib import Path
import r31_consistent_gf2_test as r31
import r32b_native_shadow_benchmark as b

PROTO="DRNAS-R32F-SAFE-MULTICORE-PORTFOLIO-20261103-v1"
CAP=8.0
MODES=("clean","native_off","r32e_active","portfolio")
FAMILIES=tuple(r31.FAMILIES)
BASE_INDICES=range(60,66)
STRESS_INDICES=range(70,76)
REPS_BASE=5
REPS_STRESS=4
SHARDS=4

def check(condition,reason):
    if not condition:raise RuntimeError("R32F_AUDIT_FAILURE "+str(reason))
def sha(value):return b.sha(value)
def freeze(dest):
    out=Path(dest);out.mkdir(parents=True,exist_ok=True)
    cases=[]
    for family in FAMILIES:
        for idx in BASE_INDICES:
            n,clauses,expected,truth=r31.make_case(family,idx)
            raw=r31.encode(n,clauses)
            name=f"r32f_base_{family}_{idx:02d}.cnf"
            (out/name).write_bytes(raw)
            cases.append(dict(name=name,family=family,expected=expected,
                              sha256=sha(raw),cohort="new_baseline",
                              repeats=REPS_BASE))
    for family in ("consistent_visible","consistent_hidden","consistent_mixed"):
        for idx in STRESS_INDICES:
            n,clauses,expected,truth=r31.make_case(family,idx)
            rng=random.Random(int(sha((PROTO+"/"+family+"/"+str(idx)).encode()),16))
            additional=260+60*(idx%2)
            background=list(range(n+1,n+additional+1))
            for v in background:truth[v]=rng.getrandbits(1)
            n+=additional
            for _ in range(int(additional*4.24)):
                clauses.append(r31.planted_clause(rng,background,truth))
            copies=8+4*(idx%2)
            for j in range(260):
                bridge=4*(j%copies+1)
                others=rng.sample(background,2)
                clause=[-bridge]+[v if rng.getrandbits(1) else -v for v in others]
                if not any((x>0)==bool(truth[abs(x)]) for x in clause):
                    clause[1]*=-1
                clauses.append(clause)
            rng.shuffle(clauses)
            check(all(any((l>0)==bool(truth[abs(l)]) for l in cl)
                      for cl in clauses),"Invalid planted SAT witness")
            raw=r31.encode(n,clauses)
            name=f"r32f_stress_{family}_{idx:02d}.cnf"
            (out/name).write_bytes(raw)
            cases.append(dict(name=name,family=family,expected=expected,
                              sha256=sha(raw),cohort="new_coupled_stress",
                              repeats=REPS_STRESS))
    trials=sum(c["repeats"]*len(MODES) for c in cases)
    check(len(cases)==60 and trials==1128 and
          len({x["sha256"] for x in cases})==60,
          "Need 60 unique formulas, 1,128 paired trials")
    manifest=dict(protocol=PROTO,cases=cases,arms=MODES,cap_seconds=CAP,
        shards=SHARDS,total_trials=trials,
        binary_origin_run=41638482746,baseline_repeats=REPS_BASE,
        stress_repeats=REPS_STRESS,
        warnings=[
          "All formulas synthetic, not independently sourced official SAT Competition",
          "The synthetic coupled-stress candidates are not necessarily hard",
          "R32f portfolio requires at least two pinned CPU cores per trial",
          "Portfolio uses up to twice a single solver's CPU, and no hard wall guarantee",
          "Race first independently valid terminal status; opposite process killed",
          "SAT model checked on original DIMACS; UNSAT relies on generator label, not LRAT",
          "Race spawning, validation and polling included in elapsed wall time",
          "Child CPU excludes parent Python bookkeeping and proof-checking",
          "8-second cap per portfolio; PAR-2=16 seconds",
          "Performance cannot be inferred for external SAT, P vs NP or world records"])
    (out/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
    (out/"cnf.sha256").write_text("".join(
       f'{x["sha256"]}  {x["name"]}\n' for x in cases))
    print("R32F_SHA_FROZEN",len(cases),"cases",trials,"trials",
          "manifest",sha(out/"manifest.json"),flush=True)

def cpu_usage():
    u=resource.getrusage(resource.RUSAGE_CHILDREN)
    return u.ru_utime+u.ru_stime
def verify(case,path,output,returncode,mode):
    check(returncode in (10,20),"Solver exited without SAT/UNSAT verdict")
    status="SAT" if returncode==10 else "UNSAT"
    check(status==case["expected"],"Original known-truth label drift")
    witness=b.sat_check(path,output) if status=="SAT" else "generator_label_only"
    probes,final=b.parse_native(output)
    if mode=="clean":
        check(not probes and final is None,"Unexpected clean Kissat instrumentation")
    else:
        check(final is not None and final["status"]==returncode,
              "Native final status missing or incorrect")
        if mode=="native_off":
            check(not probes,"Native OFF unexpectedly probed")
        else:
            root=b.get_root(probes)
            proof=b.compare_root(root,path)
            check(proof["status"]=="independent_proof_match",
                  "Native R32e GF2 proof mismatch")
            expected=int(root.get("extra",0)) if root["signal"]=="CONSISTENT_GAP" else 0
            matches=re.findall(
              r"^c R32E_SELECT policy=hidden_resolvent_v1 equations=(\d+) resolved=(\d+) extra=(\d+) selected=(\d+)$",
              output,re.MULTILINE)
            check(len(matches)==1,"Missing frozen R32e gate decision")
            eq,resolved,extra,selected=map(int,matches[0])
            admissible=0<expected<=12
            approved=expected if admissible and 16<=eq<=96 and extra>=8 and (
                     resolved==0 or resolved>=2*extra) else 0
            check(eq==root["equations"] and resolved==root["resolved"] and
                  extra==expected and selected==int(approved>0),
                  "R32e selection drift")
            active=re.findall(
              r"^c R32C_ACTIVE signal=([A-Z_]+) injected=(\d+) certified=(\d+)$",
              output,re.MULTILINE)
            check(len(active)==1 and int(active[0][1])==approved
                  and int(active[0][2])>=approved,
                  "Actual injection differs from certified source decision")
            literal_hits=re.findall(
              r"^c R32C_INJECTED_LITS count=(\d+) lits=([0-9,-]+)$",
              output,re.MULTILINE)
            if approved:
                check(len(literal_hits)==1 and active[0][0]=="APPLIED",
                      "Missing sound injection record")
                length,literals=literal_hits[0]
                signed=[int(x) for x in literals.split(",")]
                check(int(length)==len(signed)==approved and
                      sorted(signed)==sorted(root["sample"]),
                      "R32e injected literal is not independently proven")
            else:
                check(active[0][0]!="APPLIED" and not literal_hits,
                      "R32e intervened without independent proof")
    return status,witness,final

def process(path,binary,mode,core):
    env=os.environ.copy()
    env["R32B_MODE"]="r32e" if mode=="r32e_active" else "off"
    output=tempfile.TemporaryFile(mode="w+t")
    # Pin before the subprocess exec: fair, non-migrating CPU assignment.
    def pin():
        os.sched_setaffinity(0,{core})
    proc=subprocess.Popen([str(binary),str(path)],
              stdout=output,stderr=subprocess.PIPE,text=True,
              env=env,preexec_fn=pin)
    return proc,output
def stop_and_reap(p):
    if p.poll() is None:p.kill()
    p.communicate()
def read_output(file):
    file.flush();file.seek(0)
    return file.read()
def run_trial(case,path,mode,bins,cores):
    startcpu=cpu_usage()
    begin=time.monotonic()
    work=[]
    try:
        if mode!="portfolio":
            which="clean" if mode=="clean" else "native"
            p,out=process(path,bins[which],mode,cores[0]);work.append((p,out,mode))
            try:p.wait(timeout=CAP)
            except subprocess.TimeoutExpired:
                stop_and_reap(p)
                return dict(status="TIMEOUT",wall_s=round(time.monotonic()-begin,6),
                            par2=2*CAP,cpu_s=round(cpu_usage()-startcpu,6),
                            winner=None,conflicts=None)
            output=read_output(out)
            status,witness,final=verify(case,path,output,p.returncode,mode)
            return dict(status=status,wall_s=round(time.monotonic()-begin,6),
                        par2=round(time.monotonic()-begin,6),
                        cpu_s=round(cpu_usage()-startcpu,6),winner=mode,
                        conflicts=final["conflicts"] if final else None)
        # Portfolio: the same native binary, OFF versus certified R32e.
        # Each runs on its own fixed core; randomized launch order across reps.
        order=[("native_off",cores[0]),("r32e_active",cores[1])]
        if int(sha((case["sha256"]+":"+str(time.monotonic_ns()%17)).encode()),16)%2:
            order.reverse()
        for candidate,core in order:
            p,out=process(path,bins["native"],candidate,core)
            work.append((p,out,candidate))
        while time.monotonic()-begin < CAP:
            for p,out,candidate in work:
                if p.poll() is None:continue
                output=read_output(out)
                status,witness,final=verify(case,path,output,p.returncode,candidate)
                wall=round(time.monotonic()-begin,6)
                for other,_,_ in work:
                    if other is not p:stop_and_reap(other)
                return dict(status=status,wall_s=wall,par2=wall,
                            cpu_s=round(cpu_usage()-startcpu,6),
                            winner=candidate,
                            conflicts=final["conflicts"] if final else None)
            time.sleep(0.0001)
        for p,_,_ in work:stop_and_reap(p)
        return dict(status="TIMEOUT",wall_s=round(time.monotonic()-begin,6),
                    par2=2*CAP,cpu_s=round(cpu_usage()-startcpu,6),
                    winner=None,conflicts=None)
    finally:
        for p,out,_ in work:
            if p.poll() is None:stop_and_reap(p)
            else:p.wait()
            out.close()

def measure(a):
    frozen=Path(a.inputs);data=json.loads((frozen/"manifest.json").read_text())
    check(data["protocol"]==PROTO and len(data["cases"])==60,"Changed manifest")
    check(0<=a.shard<SHARDS,"Shard range")
    cores=sorted(os.sched_getaffinity(0))
    check(len(cores)>=2,"Two pinned CPU cores required to test a fair race")
    cores=cores[:2]
    bins={key:Path(getattr(a,key)).resolve() for key in ("clean","native")}
    check(all(path.is_file() for path in bins.values()),"Missing pinned Kissat binaries")
    out=Path(a.outdir);out.mkdir(parents=True,exist_ok=True)
    (out/"meta.json").write_text(json.dumps(dict(shard=a.shard,
         manifest_sha256=sha(frozen/"manifest.json"),
         binaries={k:sha(v) for k,v in bins.items()},
         cores=cores),indent=2))
    rows=[]
    for case in data["cases"][a.shard::SHARDS]:
        source=frozen/case["name"]
        check(sha(source)==case["sha256"],"SHA mismatch for original CNF")
        for rep in range(case["repeats"]):
            order=list(MODES)
            random.Random(int(sha((case["sha256"]+str(rep)+"R32F").encode()),16)).shuffle(order)
            for mode in order:
                measured=run_trial(case,source,mode,bins,cores)
                rows.append(dict(case=case["name"],cohort=case["cohort"],
                      family=case["family"],repeat=rep,mode=mode,**measured))
                print("R32F_TRIAL",a.shard,case["name"],rep,mode,
                      measured["status"],measured["wall_s"],
                      "winner",measured["winner"],"CPU",measured["cpu_s"],flush=True)
        (out/"rows.json").write_text(json.dumps(rows)+"\n")
    print("R32F_SHARD_DONE",a.shard,len(rows),flush=True)

def aggregate(a):
    frozen=Path(a.inputs);manifest=json.loads((frozen/"manifest.json").read_text())
    check(manifest["protocol"]==PROTO,"Wrong manifest")
    rows=[];binaries=set()
    for shard in range(SHARDS):
        root=Path(a.combined)/f"r32f-shard-{shard}"/"results"
        meta=json.loads((root/"meta.json").read_text())
        check(meta["shard"]==shard and
              meta["manifest_sha256"]==sha(frozen/"manifest.json"),
              "One shard has a different source manifest")
        binaries.add(json.dumps(meta["binaries"],sort_keys=True))
        part=json.loads((root/"rows.json").read_text())
        check(len(part)==sum(c["repeats"]*len(MODES)
             for c in manifest["cases"][shard::SHARDS]),"Incomplete shard results")
        rows.extend(part)
    check(len(binaries)==1 and len(rows)==manifest["total_trials"]==1128,
          "Expected 1128 complete paired trials and one pinned binary pair")
    bycase={c["name"]:[r for r in rows if r["case"]==c["name"]]
            for c in manifest["cases"]}
    for c in manifest["cases"]:
        group=bycase[c["name"]]
        for rep in range(c["repeats"]):
            t={r["mode"]:r for r in group if r["repeat"]==rep}
            check(len(t)==len(MODES),"Missing/duplicate paired arm")
            statuses={r["status"] for r in t.values()}-{"TIMEOUT"}
            check(len(statuses)<=1,"Contradictory truth on matched CNF")
            if t["portfolio"]["winner"] is not None:
                check(t["portfolio"]["winner"] in ("native_off","r32e_active"),
                      "Portfolio winner outside audited candidate list")
    groups={"ALL":manifest["cases"]}
    groups.update({name:[c for c in manifest["cases"] if c["cohort"]==name]
                  for name in ("new_baseline","new_coupled_stress")})
    groups.update({family:[c for c in manifest["cases"] if c["family"]==family]
                  for family in FAMILIES})
    summary={}
    for name,cases in groups.items():
        selected={c["name"] for c in cases}
        report={}
        for mode in MODES:
            subset=[r for r in rows if r["case"] in selected and r["mode"]==mode]
            report[mode]=dict(PAR2_sum=round(sum(r["par2"] for r in subset),6),
              CPU_sum=round(sum(r["cpu_s"] for r in subset),6),
              timeouts=sum(r["status"]=="TIMEOUT" for r in subset),
              trials=len(subset))
        report["portfolio"]["winners"]=dict(collections.Counter(
            r["winner"] for r in rows if r["case"] in selected and r["mode"]=="portfolio"))
        for ref in ("native_off","clean"):
            base=report[ref]["PAR2_sum"]
            report["portfolio"][f"delta_vs_{ref}_pct"]=round(
                  100*(report["portfolio"]["PAR2_sum"]-base)/base,4)
            cpu=report[ref]["CPU_sum"]
            report["portfolio"][f"CPU_vs_{ref}_pct"]=round(
                  100*(report["portfolio"]["CPU_sum"]-cpu)/max(1e-9,cpu),4)
        summary[name]=report
        print("R32F_SUMMARY",name,json.dumps(report,sort_keys=True),flush=True)
    percase=[]
    for case in manifest["cases"]:
        trials=bycase[case["name"]]
        med={mode:statistics.median(r["par2"] for r in trials if r["mode"]==mode)
             for mode in MODES}
        wins=dict(collections.Counter(r["winner"] for r in trials if r["mode"]=="portfolio"))
        conf={mode:statistics.median([r["conflicts"] for r in trials
                  if r["mode"]==mode and r["conflicts"] is not None])
                  if any(r["mode"]==mode and r["conflicts"] is not None
                         for r in trials) else None for mode in ("native_off","r32e_active","portfolio")}
        percase.append(dict(name=case["name"],cohort=case["cohort"],
            family=case["family"],medians=med,winners=wins,median_conflicts=conf))
    rng=random.Random(32111)
    def boot(group):
        arr=[]
        for i in range(2500):
            sample=[rng.choice(group) for _ in group]
            base=sum(c["medians"]["native_off"] for c in sample)
            test=sum(c["medians"]["portfolio"] for c in sample)
            arr.append(100*(test-base)/base)
        arr.sort()
        return [round(arr[62],3),round(arr[2437],3)]
    summary["ALL"]["bootstrap_case_median_95pct"]=boot(percase)
    summary["ALL"]["faster_case_medians"]=sum(
         c["medians"]["portfolio"]<c["medians"]["native_off"] for c in percase)
    for name in ("new_baseline","new_coupled_stress"):
        summary[name]["bootstrap_case_median_95pct"]=boot(
             [c for c in percase if c["cohort"]==name])
    data=dict(protocol=PROTO,source_sha256=sha(frozen/"manifest.json"),
        summary=summary,per_case=percase,rows=rows,warnings=manifest["warnings"])
    Path(a.output).write_text(json.dumps(data,indent=2)+"\n")
    report=["# DRNAS R32f safe two-core SAT portfolio",
        "60 previously unseen synthetic CNFs, 1,128 matched trials, four arms.",
        "Pinned clean vs pinned native OFF vs proof-certified R32e vs two-core race.",
        "Portfolio returns only independently validated answer; other child killed.",
        "CPU ratio excludes Python parent; wall time includes process startup and SAT validation.",
        "All formulas synthetic; this is not a world competition result.",
        f'95% bootstrap case-median delta interval: {summary["ALL"]["bootstrap_case_median_95pct"]}%.',
        f'Cases faster: {summary["ALL"]["faster_case_medians"]}/60.',
        "","| Group | Clean s | Native OFF s | R32e s | Portfolio s | Portfolio vs OFF | Portfolio CPU vs OFF | R32e winners |",
        "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for group,vals in summary.items():
        v=vals["portfolio"]
        report.append(f'| {group} | {vals["clean"]["PAR2_sum"]:.4f} | {vals["native_off"]["PAR2_sum"]:.4f} | {vals["r32e_active"]["PAR2_sum"]:.4f} | {v["PAR2_sum"]:.4f} | {v["delta_vs_native_off_pct"]:+.3f}% | {v["CPU_vs_native_off_pct"]:+.2f}% | {v["winners"].get("r32e_active",0)}/{v["trials"]} |')
    report+=["","| Formula | Cohort | Native OFF median s | R32e median s | Portfolio median s | Portfolio winners |",
             "|---|---|---:|---:|---:|---|"]
    for c in percase:
        m=c["medians"]
        report.append(f'| {c["name"]} | {c["cohort"]} | {m["native_off"]:.6f} | {m["r32e_active"]:.6f} | {m["portfolio"]:.6f} | {c["winners"]} |')
    Path(a.report).write_text("\n".join(report)+"\n")
    print("R32F_AUDIT_PASS",len(rows),"trials",len(percase),"originals",flush=True)

def main():
    parser=argparse.ArgumentParser()
    sub=parser.add_subparsers(dest="mode",required=True)
    p=sub.add_parser("freeze");p.add_argument("--dest",required=True)
    p=sub.add_parser("measure")
    for name in ("inputs","clean","native","outdir"):p.add_argument("--"+name,required=True)
    p.add_argument("--shard",type=int,required=True)
    p=sub.add_parser("aggregate")
    for name in ("inputs","combined","output","report"):p.add_argument("--"+name,required=True)
    args=parser.parse_args()
    if args.mode=="freeze":freeze(args.dest)
    elif args.mode=="measure":measure(args)
    else:aggregate(args)

if __name__=="__main__":main()
