#!/usr/bin/env python3
"""XORABC3: native source-certified GF2/CaDiCaL IPASIR-UP true live trail.
R158X binary is pinned same across clean, shadow and direct modes.
No GF2 proof shortcut; SAT model checked on original CNF; no UNSAT LRAT.
Python orchestration/aggregation only. Bench formulas previously seen.
"""
import argparse, collections, hashlib, json, os, pathlib, random, re, subprocess, tempfile, time
import drnas_xorabc2_native_benchmark as abc2
import drnas_equiv9_prospective_seed_holdout as e9
import r158x_causal_benchmark as telemetry
ROOT=pathlib.Path("mre_xorabc3")
NATIVE=ROOT/"bin/xorabc3_trail"
EXPORT=ROOT/"bin/xorabc3_rows"
CAP=10.0;REPS=2;SHARDS=10;N=40
PROTO="DRNAS-XORABC3-40FROZEN-NATIVE-IPASIR-UP-REAL-TRAIL-6ARMS-1CPU-10S-v1"
ARMS=("cadical_clean","gf2_shadow","gf2_direct","gf2_nogate","kissat_plain","cms_plain")
MODES={"cadical_clean":"clean","gf2_shadow":"shadow_boundary",
       "gf2_direct":"direct_boundary","gf2_nogate":"direct_boundary_nogate"}
def need(ok,msg):
    if not ok:raise RuntimeError("XORABC3_FAIL_CLOSED "+str(msg))
def digest(path):return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(pathlib.Path(path).read_text())
def write(path,data):
    path=pathlib.Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,sort_keys=True,indent=2)+"\n")
def signature():
    return dict(script=digest(__file__),
        source_cpp=digest("research/drnas_xorabc3_source_rows.cpp"),
        extractor_base=digest("research/drnas_xorabc2_native.cpp"),
        original_bridge=digest("research/r158x_causal_cdcl_bridge.cpp"),
        bridge_base=digest("research/r133c_native_gf2_cdcl_bridge.cpp"),
        exporter=digest(EXPORT),bridge=digest(NATIVE),
        cadical_commit=(ROOT/"cadical-source-commit.txt").read_text().strip(),
        kissat=digest(e9.KISSAT),cms=digest(abc2.prev.CMS),
        abc2_frozen=digest(abc2.ROOT/"manifest.json"))
def freeze():
    abc2.verify()
    cases=abc2.prev.roster()
    need(len(cases)==40 and len(set(c["sha256"] for c in cases))==40,
         "40 frozen SHA original source cases required")
    for c in cases:abc2.prev.source(c)
    write(ROOT/"manifest.json",dict(protocol=PROTO,cases=cases,arms=list(ARMS),
      signatures=signature(),one_logical_CPU=True,cap_s=CAP,reps=REPS,
      shards=SHARDS,expected_trials=N*REPS*len(ARMS),
      original_sources_previously_seen_not_blind=True,
      true_CaDiCaL_IPASIR_UP_CDCL_trail=True,shadow_matched=True,
      original_CNF_immutable=True,no_GF2_UNSAT_shortcut=True,
      backend_UNSAT_no_independent_LRAT=True))
    verify()
    print("XORABC3_FROZEN "+json.dumps(dict(sources=N,attempts=480,
       arms=len(ARMS),cap_s=CAP,source_locked=True)),flush=True)
def verify():
    abc2.verify()
    m=read(ROOT/"manifest.json")
    need(m["protocol"]==PROTO and m["cases"]==abc2.prev.roster()
         and m["arms"]==list(ARMS) and m["signatures"]==signature()
         and m["expected_trials"]==480 and m["one_logical_CPU"],
         "source manifest or native binary signature drift")
    for c in m["cases"]:abc2.prev.source(c)
    return m
def export_native(src,where):
    t=time.perf_counter()
    p=subprocess.run([str(EXPORT.resolve()),"export",str(src.resolve()),
       str(where.resolve())],capture_output=True,text=True,timeout=3.0)
    need(p.returncode==0,"native original GF2 row verification: "+p.stderr[-1500:])
    matches=[line[len("XORABC3_EXPORT "):] for line in p.stdout.splitlines()
             if line.startswith("XORABC3_EXPORT ")]
    need(len(matches)==1,"native GF2 source certificate not returned")
    data=json.loads(matches[0])
    need(data["verified"] and data["rows"]<=32 and
         data["selector"]=="source_frequency_only",
         "source-only complete parity extractor failed")
    lines=where.read_text().splitlines()
    need(len(lines)==data["rows"] and
         all(2<=int(line.split()[0])<=4 and
             len(line.split())==int(line.split()[0])+2 for line in lines),
         "source XOR TSV malformed")
    return data,round(time.perf_counter()-t,6)
def get_model(txt):
    model={}
    for l in txt.splitlines():
        if l.startswith("v "):
            for val in map(int,l[2:].split()):
                if val:
                    need(abs(val) not in model or model[abs(val)]==(val>0),
                         "inconsistent native SAT model")
                    model[abs(val)]=(val>0)
    return model
def trial(case,rep,arm,cap=CAP,pilot=False):
    need(arm in ARMS and rep in (0,1),"invalid trial arm")
    cpu=min(os.sched_getaffinity(0));os.sched_setaffinity(0,{cpu})
    t=time.perf_counter();pc=time.process_time()
    src=abc2.prev.source(case)
    n,original=e9.x22.read_cnf(src)
    need(n>0 and digest(src)==case["sha256"],"original source SHA drift")
    status="TIMEOUT";checked=False;raw_status="TIMEOUT";native={}
    proof=dict(rows=0,equations=0,verified=False,source_row_sha=None,prep_s=0.0)
    with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
        if arm in ("gf2_shadow","gf2_direct","gf2_nogate"):
            tsv=pathlib.Path(tmp)/"original-source-certified.tsv"
            metrics,seconds=export_native(src,tsv)
            proof=dict(rows=metrics["rows"],equations=metrics["equations"],
                 verified=True,source_row_sha=digest(tsv),prep_s=seconds)
        else:tsv=pathlib.Path(tmp)/"unused.tsv"
        left=cap-(time.perf_counter()-t)
        if left>1.05 or (arm not in MODES and left>.08):
            if arm in MODES:
                mode=MODES[arm]
                # Native terminator must have room to return statistics.
                # The outer E2E cap still includes all process overhead.
                command=[str(NATIVE.resolve()),mode,str(src.resolve()),
                    str(tsv.resolve()),str(max(1.0,min(cap,left-1.0)))]
            else:
                mode="kissat" if arm=="kissat_plain" else "cms"
                command=([str(e9.KISSAT.resolve()),str(src.resolve())] if
                    mode=="kissat" else [str(abc2.prev.CMS.resolve()),"--verb","0",
                                      "-t","1",str(src.resolve())])
            env=os.environ.copy()
            env["LD_LIBRARY_PATH"]=str(pathlib.Path("mre_equiv12/lib").resolve())+":"+str(pathlib.Path("mre5/lib").resolve())+":"+env.get("LD_LIBRARY_PATH","")
            try:
                p=subprocess.run(command,capture_output=True,text=True,
                     env=env,timeout=max(.05,left-.01),check=False)
            except subprocess.TimeoutExpired:p=None
            if p is not None:
                if arm in MODES:
                    need(p.returncode in (0,10,20),
                         "native CaDiCaL failed: "+p.stderr[-1200:])
                    txt,tele,stats,source_rows,derived=telemetry.parse_native(p.stdout.encode(),mode)
                    raw_status=tele["status"]
                    if raw_status=="SAT":
                        model=get_model(txt)
                        need(model and e9.x22.holds(original,model),
                             "native CDCL model fails original SHA CNF")
                        checked=True
                    status="TIMEOUT" if raw_status=="UNKNOWN" else raw_status
                    need(stats["conflicts"] is not None and
                         stats["decisions"] is not None and
                         stats["propagations"] is not None,
                         "native solver lacks genuine conflict/decision/propagation counters")
                    native=dict(conflicts=stats["conflicts"],decisions=stats["decisions"],
                       search_propagations=stats["propagations"],learned=stats["learned"],
                       bridge_assignments=int(tele["assignments"]),
                       bridge_backtracks=int(tele["backtracks"]),
                       GF2_proposals=int(tele["direct_proposals"]),
                       GF2_completed_reasons=int(tele["reason_clauses_completed"]),
                       GF2_shadow_candidates=int(tele["shadow_candidates"]),
                       GF2_adaptive_gate=int(tele["adaptive_gate_events"]),
                       source_rows=source_rows,derived_rows=derived)
                    need(mode=="clean" or proof["rows"]==source_rows,
                         "source native extractor versus IPASIR-UP row mismatch")
                else:
                    need(p.returncode in (0,10,20),
                         "reference solver execution failure "+p.stderr[-1200:])
                    raw_status,checked=e9.x22.solver_result(mode,p.returncode,
                       p.stdout+"\n"+p.stderr,original,{})
                    status=raw_status
        elapsed=time.perf_counter()-t
    if elapsed>=cap:
        status="TIMEOUT";checked=False
    need(status!="SAT" or checked,"SAT witness not checked on original CNF")
    need(digest(src)==case["sha256"],"source mutated after benchmark")
    return dict(protocol=PROTO,sha256=case["sha256"],gbd=case["gbd"],
        shard=-1,arm=arm,rep=rep,one_cpu=cpu,
        source_SHA_checked=True,cap_s=cap,status=status,
        backend_status=raw_status,SAT_original_witness_verified=checked if status=="SAT" else False,
        UNSAT_independent_LRAT=False,
        native_source_GF2_certificate_checked=proof["verified"],
        source_XOR_equations=proof["equations"],source_rows=proof["rows"],
        source_rows_sha256=proof["source_row_sha"],
        prepass_s=proof["prep_s"],metrics=native,wall_E2E_s=round(elapsed,6),
        parent_CPU_s=round(time.process_time()-pc,6))
def pilot():
    m=verify()
    # Outcome-independent sampling: one XOR-bearing and one XOR-absent source
    selected={}
    with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
        for c in m["cases"]:
            tsv=pathlib.Path(tmp)/"pilot.tsv"
            info,_=export_native(abc2.prev.source(c),tsv)
            label="xor" if info["rows"] else "control"
            if label not in selected:selected[label]=c
            if len(selected)==2:break
    need(len(selected)==2,"pilot requires XOR and no-XOR original sources")
    for label,c in sorted(selected.items()):
        for arm in ("cadical_clean","gf2_shadow","gf2_direct"):
            x=trial(c,0,arm,cap=8.0,pilot=True)
            print("XORABC3_PILOT "+json.dumps(dict(type=label,sha=c["sha256"][:12],
               arm=arm,status=x["status"],stats=x["metrics"],
               prepass_s=x["prepass_s"],wall_E2E_s=x["wall_E2E_s"])),flush=True)
            need(x["metrics"].get("conflicts") is not None,
                 "pilot missing true in-solver CaDiCaL metrics: "
                 +json.dumps(dict(type=label,arm=arm,status=x["status"],
                                  wall=x["wall_E2E_s"],source=c["sha256"][:12])))
    print("XORABC3_PILOT_PASS two_original_SHA_x_three_live_arms",flush=True)
def shard(index):
    m=verify();need(0<=index<SHARDS,"bad shard")
    cases=[c for i,c in enumerate(m["cases"]) if i%SHARDS==index]
    records=[]
    for c in cases:
        for rep in range(REPS):
            order=list(ARMS)
            random.Random(c["sha256"]+str(rep)+"xorabc3").shuffle(order)
            for arm in order:
                r=trial(c,rep,arm);r["shard"]=index
                need(r["wall_E2E_s"]<=CAP+.2,"runtime exceeds CAP")
                records.append(r)
                write(ROOT/f"shard-{index}.json",records)
                print("XORABC3_TRIAL "+json.dumps(r,sort_keys=True),flush=True)
    need(len(records)==48,"missing shard paired trials")
    print(f"XORABC3_SHARD_PASS {index} 48",flush=True)
def audit():
    m=verify();allrows=[]
    for i in range(SHARDS):
        rows=read(ROOT/f"shard-{i}.json")
        need(len(rows)==48,"missing or invalid shard")
        allrows+=rows
    keys={(r["sha256"],r["rep"],r["arm"]) for r in allrows}
    expected={(c["sha256"],rep,arm) for c in m["cases"]
              for rep in range(REPS) for arm in ARMS}
    need(len(allrows)==len(keys)==480 and keys==expected,
         "duplicate/missing matched original SHA trials")
    bysha=collections.defaultdict(list)
    for r in allrows:
        need(r["protocol"]==PROTO and r["source_SHA_checked"] and
             r["status"] in ("SAT","UNSAT","TIMEOUT") and r["wall_E2E_s"]<=CAP+.2
             and (r["status"]!="SAT" or r["SAT_original_witness_verified"]),
             "incorrect or unverifiable original solver claim")
        if r["arm"] in ("gf2_shadow","gf2_direct","gf2_nogate"):
            need(r["native_source_GF2_certificate_checked"],"uncertified GF2")
        bysha[r["sha256"]].append(r)
    agree={s for s,rs in bysha.items()
           if any(r["arm"]=="kissat_plain" and r["status"]=="UNSAT" for r in rs)
           and any(r["arm"]=="cms_plain" and r["status"]=="UNSAT" for r in rs)}
    for s,rr in bysha.items():
        need(len({r["status"] for r in rr if r["status"]!="TIMEOUT"})<=1,
             "SAT/UNSAT cross-solver contradiction")
    def valid(r):
        return (r["status"]=="SAT" and r["SAT_original_witness_verified"]) or (
            r["status"]=="UNSAT" and r["sha256"] in agree)
    def par(r):return r["wall_E2E_s"] if valid(r) else 2*CAP
    def score(rr):
        metrics=[r["metrics"] for r in rr if "conflicts" in r["metrics"]]
        return dict(attempts=len(rr),solved=sum(valid(r) for r in rr),
           verified_SAT=sum(valid(r) and r["status"]=="SAT" for r in rr),
           reference_consensus_UNSAT_no_LRAT=sum(valid(r) and r["status"]=="UNSAT" for r in rr),
           UNSAT_unverified=sum(r["status"]=="UNSAT" and not valid(r) for r in rr),
           PAR2_s=round(sum(par(r) for r in rr),6),
           actual_wall_s=round(sum(r["wall_E2E_s"] for r in rr),6),
           source_GF2_rows=sum(r["source_rows"] for r in rr),
           source_prepass_s=round(sum(r["prepass_s"] for r in rr),6),
           native_stat_attempts=len(metrics),
           CDCL_conflicts=sum(x["conflicts"] for x in metrics),
           CDCL_decisions=sum(x["decisions"] for x in metrics),
           CDCL_search_propagations=sum(x["search_propagations"] for x in metrics),
           GF2_proposals=sum(x["GF2_proposals"] for x in metrics),
           GF2_accepted_reasons=sum(x["GF2_completed_reasons"] for x in metrics),
           GF2_shadow_candidates=sum(x["GF2_shadow_candidates"] for x in metrics))
    scores={arm:score([r for r in allrows if r["arm"]==arm]) for arm in ARMS}
    def paired(a,b):
        vals=[]
        for rs in bysha.values():
            for rep in range(REPS):
                x=next(r for r in rs if r["arm"]==a and r["rep"]==rep)
                y=next(r for r in rs if r["arm"]==b and r["rep"]==rep)
                vals.append(par(x)-par(y))
        return dict(gain_PAR2_s=round(-sum(vals),6),
           wins=sum(x<-.02 for x in vals),losses=sum(x>.02 for x in vals),
           ties=sum(abs(x)<=.02 for x in vals))
    comparisons=dict(direct_vs_shadow=paired("gf2_direct","gf2_shadow"),
      direct_vs_clean=paired("gf2_direct","cadical_clean"),
      direct_vs_nogate=paired("gf2_direct","gf2_nogate"),
      shadow_vs_clean=paired("gf2_shadow","cadical_clean"),
      direct_vs_kissat=paired("gf2_direct","kissat_plain"))
    for arm in ARMS:scores[arm]["PAR2_speedup_vs_cadical_clean_x"]=round(
      scores["cadical_clean"]["PAR2_s"]/scores[arm]["PAR2_s"],6)
    report=dict(protocol=PROTO,trials=480,sources=40,one_CPU=True,
       original_sources_previously_seen_not_blind=True,
       true_live_CDCL_trail_native_C_plus_plus=True,not_static_CNFs=True,
       independent_original_GF2_source_replay=True,
       no_independent_UNSAT_LRAT=True,
       benchmark_consensus_UNSAT_SHA=sorted(agree),
       scores=scores,comparisons=comparisons,
       per_shard={str(i):{arm:score([r for r in allrows if r["shard"]==i and
            r["arm"]==arm]) for arm in ARMS} for i in range(SHARDS)})
    write(ROOT/"report.json",report)
    print("XORABC3_FINAL "+json.dumps(report,sort_keys=True),flush=True)
def main():
    p=argparse.ArgumentParser();p.add_argument("cmd",choices=["freeze","verify","pilot","shard","audit"]);p.add_argument("--shard",type=int,default=-1);arg=p.parse_args()
    if arg.cmd=="freeze":freeze()
    if arg.cmd=="verify":verify();print("XORABC3_VERIFY_PASS",flush=True)
    if arg.cmd=="pilot":pilot()
    if arg.cmd=="shard":shard(arg.shard)
    if arg.cmd=="audit":audit()
if __name__=="__main__":main()
