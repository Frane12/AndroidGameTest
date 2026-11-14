#!/usr/bin/env python3
"""Proof-first paired benchmark of Worker-domain guard and PCMAX RUP preprocessing.

Three disjoint experimental panels on source-pinned SAT2024 CNFs:
- Worker #64: 25 repetitions, X5 guard ON/OFF, CF7, Kissat.
- PCMAX #44: 3 repetitions, seven arms, 8-s cap, plus a 20-s diagnostic.
- Eight non-target originals: 2 repetitions of guard ON/OFF (1-s cap).
Each subprocess runs serially under one pinned logical CPU; no parallel solver
portfolio. No promotion, learning, or modifications to the main solver.
"""
import argparse,collections,hashlib,json,os,pathlib,random,resource,signal
import statistics,subprocess,sys,tempfile,time
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"research"))
import drnas_focus_44_64 as F
import drnas_structure_44_64 as S
import drnas_clause_cf7_real100 as CF

OUT=ROOT/"domain_bench"
TARGETS={44:F.EXPECTED[44],64:F.EXPECTED[64]}
CONTROLS=(8,14,24,34,54,74,84,94)
WORKER_ARMS=("X5_OFF","X5_WORKER_GUARD","CF7","Kissat")
PCMAX_ARMS=("X5_OFF","X5_WORKER_GUARD","X5_RUP584","CF7","CF7_RUP584",
            "Kissat","Kissat_RUP584")
BINARIES={"X5_OFF":"build/drnas-worker-domain",
 "X5_WORKER_GUARD":"build/drnas-worker-domain",
 "X5_RUP584":"build/drnas-worker-domain",
 "CF7":"build/drnas-clause-cf6","CF7_RUP584":"build/drnas-clause-cf6",
 "Kissat":"build/kissat","Kissat_RUP584":"build/kissat"}
PROOF_CHECKER=str(ROOT/"build/drat-trim")
def emit(tag,value):print(tag+" "+json.dumps(value,sort_keys=True),flush=True)
def read_sources():
    manifest=json.loads((ROOT/"cf7/manifest.json").read_text())
    assert manifest["protocol"]=="CF7-FIVE-ARM-REAL100-V1"
    assert len(manifest["sources"])==100 and manifest["cap_s"]==8.0
    sources={s["id"]:s for s in manifest["sources"]}
    assert set(TARGETS).issubset(sources) and all(i in sources for i in CONTROLS)
    for i,hash_ in TARGETS.items():
        assert sources[i]["sha256"]==hash_,("PINNED_SOURCE",i)
    return sources

def append_rup584(source,output):
    """Compute one-step binary RUP resolvents of ORIGINAL CNF each time.

    Ternary (l1 OR l2 OR head), plus original (-head), yields (l1 OR l2).
    Every added clause is thus a single-resolution consequence and RUP.
    """
    original=ROOT/source["path"]
    nv,clauses,normalization=S.parse(original,source["sha256"])
    assert normalization["tautological_clauses_omitted"]==0
    groups=[c for c in clauses if len(c)>=5 and all(x>0 for x in c)]
    choices={v for c in groups for v in c}
    units={-c[0] for c in clauses if len(c)==1 and c[0]<0}
    existing=set(clauses)
    added=set();witnesses={}
    for clause in clauses:
        if len(clause)!=3:continue
        vars_choice=[x for x in clause if abs(x) in choices]
        other=[x for x in clause if abs(x) not in choices]
        if len(vars_choice)!=1 or len(other)!=2:continue
        heads=[x for x in other if x>0 and x in units]
        if len(heads)!=1:continue
        head=heads[0]
        short=tuple(x for x in clause if x!=head)
        if len(short)!=2:continue
        assert (-head,) in existing and clause in existing
        if short not in existing:
            added.add(short);witnesses[short]=(clause,(-head,))
    assert len(added)==584,("RUP_COUNT_DRIFT",len(added))
    assert len(witnesses)==len(added)
    with output.open("w") as f:
        f.write(f"p cnf {nv} {len(clauses)+len(added)}\n")
        for c in clauses:f.write(" ".join(map(str,c))+" 0\n")
        for c in sorted(added):f.write(" ".join(map(str,c))+" 0\n")
    return len(added),hashlib.sha256(output.read_bytes()).hexdigest()

def run_trial(source,arm,cap,rep,panel):
    src=ROOT/source["path"]
    t=time.perf_counter()
    assert F.sha(src)==source["sha256"],("ORIGINAL_CNFSHA_CHANGED",source["id"])
    dest=ROOT/BINARIES[arm]
    assert dest.is_file() and pathlib.Path(PROOF_CHECKER).is_file()
    rup=arm.endswith("_RUP584")
    with tempfile.TemporaryDirectory(prefix="drnas-domain-paired-") as td:
        td=pathlib.Path(td)
        proof=td/"proof.drat";input_cnf=src
        added=0;aug_hash=None
        if rup:
            assert source["id"]==44,"RUP subset only tested on original PCMAX44"
            input_cnf=td/"augmented.cnf"
            added,aug_hash=append_rup584(source,input_cnf)
        elapsed_prepare=time.perf_counter()-t
        remaining=cap-elapsed_prepare
        if remaining <= .2:
            return {"id":source["id"],"family":source["normalized_name_family"],
                "sha256":source["sha256"],"arm":arm,"panel":panel,"rep":rep,
                "cap_s":cap,"status":"PREPROCESS_BUDGET_EXHAUSTED","accepted":False,
                "elapsed_e2e_s":round(elapsed_prepare,6),"PAR2_verified_s":2*cap,
                "prepare_s":round(elapsed_prepare,6),"rup_added":added,
                "guard":None,"proof_bytes":0}
        if arm.startswith("X5_"):
            cmd=[str(dest),str(input_cnf),"--mode","core",
                 "--time",str(max(.1,remaining-.15)),"--x5-no-minimize",
                 "--proof",str(proof)]
            if arm=="X5_WORKER_GUARD":cmd+=["--domain-guard","--domain-budget-ms","2.0"]
        elif arm.startswith("CF7"):
            cmd=[str(dest),str(input_cnf),"--mode","core",
                 "--time",str(max(.1,remaining-.15)),"--x5-no-minimize",
                 "--x5-no-retain","--cf5-policy","B2L_32","--proof",str(proof)]
        else:cmd=[str(dest),str(input_cnf),str(proof)]
        def limit():
            resource.setrlimit(resource.RLIMIT_FSIZE,(512*1024*1024,512*1024*1024))
        process=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
             text=True,start_new_session=True,preexec_fn=limit)
        timed=False
        try:stdout,stderr=process.communicate(timeout=remaining+.25)
        except subprocess.TimeoutExpired:
            timed=True
            os.killpg(process.pid,signal.SIGKILL)
            stdout,stderr=process.communicate()
        elapsed=time.perf_counter()-t
        guard=None
        for line in stderr.splitlines():
            if line.startswith("DOMAIN_GUARD "):
                guard=json.loads(line[len("DOMAIN_GUARD "):])
        status="UNKNOWN";cert=False
        if not timed and process.returncode==10:
            cert=CF.DATA.sat_witness_valid(src,CF.DATA.nvars(src),stdout)
            if not cert:raise RuntimeError(("INVALID_SAT_MODEL",source["id"],arm,rep))
            status="SAT_VERIFIED"
        elif not timed and process.returncode==20:
            status="UNSAT_UNVERIFIED"
            if proof.exists() and proof.stat().st_size:
                try:
                    checked=subprocess.run([PROOF_CHECKER,str(input_cnf),str(proof)],
                        stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                        text=True,timeout=120)
                    cert=checked.returncode==0 and "s VERIFIED" in checked.stdout
                except subprocess.TimeoutExpired:cert=False
            if cert:
                status="UNSAT_RUP_CHAIN_CERTIFIED" if rup else "UNSAT_CERTIFIED"
        elif timed:status="TIMEOUT"
        elif process.returncode==153:status="PROOF_LIMIT"
        elif process.returncode not in (0,124):
            raise RuntimeError(("SOLVER_ERROR",source["id"],arm,process.returncode,stderr[-800:]))
        # The original-NF RUP+augmented-DRAT chain is independently checkable
        # because each added binary is one-step resolution against original
        # clauses and a negative unit, and the DRAT checker sees augmented CNF.
        if rup and cert and status.startswith("UNSAT_"):
            assert added==584 and aug_hash is not None
        accepted=cert and elapsed<=cap
        row={"id":source["id"],"family":source["normalized_name_family"],
          "sha256":source["sha256"],"arm":arm,"panel":panel,"rep":rep,
          "cap_s":cap,"status":status,"accepted":accepted,
          "elapsed_e2e_s":round(elapsed,6),
          "PAR2_verified_s":round(elapsed if accepted else 2*cap,6),
          "prepare_s":round(elapsed_prepare,6),"rup_added":added,
          "augmented_sha256":aug_hash,
          "guard":guard,"proof_bytes":proof.stat().st_size if proof.is_file() else 0}
        emit("DOMAIN_TRIAL",row)
        return row

def plan(panel,sources):
    if panel=="worker":
        for rep in range(25):
            order=list(WORKER_ARMS);random.Random(64025+rep).shuffle(order)
            for arm in order:yield sources[64],arm,2.,rep
    elif panel=="pcmax":
        for rep in range(3):
            order=list(PCMAX_ARMS);random.Random(44003+rep).shuffle(order)
            for arm in order:yield sources[44],arm,8.,rep
        for arm in ("X5_OFF","X5_WORKER_GUARD","CF7","CF7_RUP584"):
            yield sources[44],arm,20.,3
    elif panel=="controls":
        for ident in CONTROLS:
            for rep in range(2):
                arms=["X5_OFF","X5_WORKER_GUARD"]
                random.Random(74000+ident*7+rep).shuffle(arms)
                for arm in arms:yield sources[ident],arm,1.,rep
    else:raise ValueError(panel)

def evaluate(panel):
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    assert len(os.sched_getaffinity(0))==1
    sources=read_sources();dst=OUT/panel;dst.mkdir(parents=True,exist_ok=True)
    rows=[]
    with (dst/"trials.jsonl").open("w") as f:
        for source,arm,cap,rep in plan(panel,sources):
            row=run_trial(source,arm,cap,rep,panel)
            rows.append(row);f.write(json.dumps(row,sort_keys=True)+"\n");f.flush()
    expected={"worker":100,"pcmax":25,"controls":32}[panel]
    assert len(rows)==expected,("INCOMPLETE_PANEL",panel,len(rows),expected)
    by=collections.defaultdict(set)
    for r in rows:
        if r["accepted"]:
            by[(r["id"],r["rep"],r["cap_s"])].add("SAT" if r["status"]=="SAT_VERIFIED" else "UNSAT")
    assert all(len(x)<=1 for x in by.values()),"CONTRADICTORY_CERTIFIED_ANSWERS"
    (dst/"meta.json").write_text(json.dumps({
        "panel":panel,"trial_count":len(rows),"single_logical_cpu":True,
        "fixed_original_sha":TARGETS,"no_promotion":True},indent=2)+"\n")
    emit("DOMAIN_PANEL_PASS",{"panel":panel,"trials":len(rows),
         "verified":sum(x["accepted"] for x in rows)})

def report():
    results={}
    allrows=[]
    for panel,count in (("worker",100),("pcmax",25),("controls",32)):
        location=ROOT/"bench_downloads"/("bench-"+panel)
        meta=json.loads((location/"meta.json").read_text())
        assert meta["panel"]==panel and meta["trial_count"]==count
        rows=[json.loads(s) for s in (location/"trials.jsonl").read_text().splitlines()]
        assert len(rows)==count
        results[panel]=rows;allrows+=rows
    assert len(allrows)==157
    grouped=collections.defaultdict(list)
    for row in allrows:
        grouped[(row["panel"],row["cap_s"],row["arm"])].append(row)
    summaries=[]
    for (panel,cap,arm),rr in sorted(grouped.items()):
        good=[r["elapsed_e2e_s"] for r in rr if r["accepted"]]
        summaries.append({"panel":panel,"cap_s":cap,"arm":arm,"trials":len(rr),
           "accepted":len(good),"PAR2_verified_s":round(sum(r["PAR2_verified_s"] for r in rr),6),
           "median_verified_s":round(statistics.median(good),6) if good else None,
           "guard_eligible":sum(bool((r.get("guard") or {}).get("eligible")) for r in rr),
           "guard_solved":sum(bool((r.get("guard") or {}).get("solved")) for r in rr)})
    assert all(len({r["sha256"] for r in rows if r["id"]==44})<=1 for rows in results.values())
    obj={"protocol":"DOMAIN-GUARD-REAL-ORIGINAL-SAT2024-BENCH1",
         "trials":157,"single_logical_cpu_per_runner":True,"blind_holdout":False,
         "no_promotion":True,"source_run":43613581688,"summary":summaries,
         "raw":allrows}
    dst=ROOT/"bench_final";dst.mkdir(exist_ok=True)
    (dst/"report.json").write_text(json.dumps(obj,indent=2,sort_keys=True)+"\n")
    emit("DOMAIN_BENCH_FINAL",{"status":"COMPLETE","trial_count":157,"summary":summaries})

def main():
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("worker","pcmax","controls","report"))
    a=p.parse_args()
    report() if a.action=="report" else evaluate(a.action)
if __name__=="__main__":main()
