#!/usr/bin/env python3
"""NOVEL2D: paired one-logical-CPU original-CNF benchmark on two source-
selected MIXAB3 XOR-reductive SHA with CMS reference. Previously seen sources,
not blind. UNSAT without independent original-CNF proof is NOT scored solved.
"""
import argparse, collections, hashlib, json, os, pathlib, random, re, subprocess, tempfile, time
import drnas_xorabc3_live_trail as abc3
import drnas_equiv9_prospective_seed_holdout as e9
import r158x_causal_benchmark as telemetry

ROOT=pathlib.Path("mre_gf_cdcl_novel2d")
BIN=ROOT/"bin/gf_cdcl_novel2d"
SCREEN=ROOT/"screen.json"
MIX3=pathlib.Path("mre_mixab3")
CAP=15.0
REPS=2
ARMS=("clean","direct","novel2b","novel2b_shadow","cms_plain")
MODES={"clean":"clean","direct":"direct_boundary",
       "novel2b":"novel2b","novel2b_shadow":"novel2b_shadow"}
PROTO="GFCDCL-NOVEL2D-MIX3-TWO-REDUCTIVE-SHA-5ARMS-2REPS-ONECPU-15S-v1"
def need(ok,msg):
    if not ok:raise RuntimeError("NOVEL2D_FAIL_CLOSED "+str(msg))
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def load(p):return json.loads(pathlib.Path(p).read_text())
def save(p,x):
    p=pathlib.Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(x,sort_keys=True,indent=2)+"\n")
def source(c):
    p=MIX3/"cases"/c["filename"]
    need(p.is_file() and sha(p)==c["sha256"],"original MIXAB3 source SHA mismatch")
    return p
def sorted_selection():
    # Only independent original-source XOR geometry; never solver outcomes.
    z=load(SCREEN)
    need(z["protocol"]=="GFCDCL-NOVEL2C-SOURCE-SCREEN-v1" and
         z["no_candidate_timing_used"] and z["original_sha_verified"],
         "source-only screen not frozen")
    hits=sorted((x for x in z["cases"] if
       x["cohort"]=="mixab3_source_only12" and x["short_reductions"]>0),
       key=lambda x:(-x["binary_reductions"],-x["short_reductions"],x["sha256"]))
    need(len(hits)==2,"exact two structural MIXAB3 cross-XOR SHA required")
    manifest=load(MIX3/"manifest.json")
    cases={x["sha256"]:x for x in manifest["original_cases"]}
    need(len(cases)==12,"MIXAB3 source roster not twelve")
    selected=[]
    for h in hits:
        need(h["sha256"] in cases,"screen candidate not in source roster")
        c=cases[h["sha256"]]
        source(c)
        selected.append(dict(**c,reductive_binary_rows=h["binary_reductions"],
                             reductive_rows=h["short_reductions"]))
    return selected
def signature():
    return dict(script=sha(__file__),source_cpp=sha("research/drnas_gf_cdcl_novel2b.cpp"),
                native=sha(BIN),row_exporter=sha(abc3.EXPORT),
                xorabc3_frozen=sha(abc3.ROOT/"manifest.json"),
                mixab3_frozen=sha(MIX3/"manifest.json"),
                structural_screen=sha(SCREEN),
                cadical_commit=(abc3.ROOT/"cadical-source-commit.txt").read_text().strip())
def freeze():
    abc3.verify()
    need(BIN.is_file() and abc3.EXPORT.is_file(),"native programs missing")
    cases=sorted_selection()
    save(ROOT/"manifest.json",dict(protocol=PROTO,cases=cases,
         arms=list(ARMS),reps=REPS,shards=2,cap_s=CAP,
         one_logical_cpu=True,source_only_selection=True,
         previously_seen_not_blind=True,strict_original_SAT_witness=True,
         backend_UNSAT_no_independent_LRAT=True,signatures=signature()))
    verify()
    print("NOVEL2D_FROZEN "+json.dumps(dict(cases=[c["sha256"] for c in cases],
         arms=ARMS,attempts=20,cap_s=CAP,one_cpu=True,previously_seen=True)),flush=True)
def verify():
    abc3.verify()
    m=load(ROOT/"manifest.json")
    need(m["protocol"]==PROTO and m["cases"]==sorted_selection() and
         m["arms"]==list(ARMS) and m["reps"]==REPS and m["shards"]==2 and
         m["cap_s"]==CAP and m["one_logical_cpu"] and m["signatures"]==signature(),
         "freeze or binary signature drift")
    for c in m["cases"]:source(c)
    return m
def trial(c,rep,arm):
    need(arm in ARMS and rep in (0,1),"invalid trial")
    cpu=min(os.sched_getaffinity(0));os.sched_setaffinity(0,{cpu})
    begin=time.perf_counter();parent_cpu=time.process_time()
    p=source(c)
    n,cnf=e9.x22.read_cnf(p)
    need(n>0 and sha(p)==c["sha256"],"original source modified")
    backend="TIMEOUT";status="TIMEOUT";satverified=False;stats={}
    with tempfile.TemporaryDirectory(dir=ROOT) as td:
        tsv=pathlib.Path(td)/"source-certified.tsv"
        info=None
        if arm!="clean" and arm!="cms_plain":
            info,_=abc3.export_native(p,tsv)
        left=CAP-(time.perf_counter()-begin)
        need(left>0.8,"source prepass budget exceeded")
        mode=MODES.get(arm)
        command=([str(BIN.resolve()),mode,str(p.resolve()),
                  str(tsv.resolve()),str(max(1.0,left-0.5))]
                 if mode else
                 [str(abc3.abc2.prev.CMS.resolve()),"--verb","0","-t","1",str(p.resolve())])
        env=os.environ.copy()
        env["LD_LIBRARY_PATH"]=str(pathlib.Path("mre_equiv12/lib").resolve())+":"+str(pathlib.Path("mre5/lib").resolve())+":"+env.get("LD_LIBRARY_PATH","")
        try:
            run=subprocess.run(command,capture_output=True,text=True,env=env,
                              timeout=max(.05,left-.02),check=False)
        except subprocess.TimeoutExpired:run=None
        if run is not None:
            need(run.returncode in (0,10,20),
                 "solver failed "+str(run.returncode)+": "+run.stderr[-800:])
            if mode is not None:
                output,tele,s,nsource,nderived=telemetry.parse_native(run.stdout.encode(),mode)
                backend=tele["status"]
                if backend=="SAT":
                    model=abc3.get_model(output)
                    need(model and e9.x22.holds(cnf,model),"native SAT model not original")
                    satverified=True
                if info is not None:
                    need(info["verified"] and nsource==info["rows"],
                         "native independently checked source rows drifted")
                m=re.search(r"^R158X_RESULT .*?$",run.stdout,re.M)
                need(m is not None,"missing true-CDCL native telemetry")
                kv={}
                for field in m.group().split():
                    if "=" in field:
                        k,v=field.split("=",1);kv[k]=v
                stats={k:int(kv[k]) for k in
                  ("derived_direct_proposals","source_direct_proposals",
                   "derived_shadow_candidates","source_rows_skipped","derived_rows_examined",
                   "direct_proposals","reason_clauses_completed",
                   "source_rows","conflict_candidates","conflicts_delivered")
                   if k in kv}
                stats.update({k:s.get(k) for k in
                    ("conflicts","decisions","propagations","learned")})
                stats["derived_rows"]=nderived
            else:
                backend,satverified=e9.x22.solver_result("cms",run.returncode,
                    run.stdout+"\n"+run.stderr,cnf,{})
                if backend=="SAT":
                    need(satverified,"CMS SAT model not verified on original")
            status=("SAT" if backend=="SAT" else
                    "UNSAT_UNVERIFIED" if backend=="UNSAT" else "TIMEOUT")
    elapsed=time.perf_counter()-begin
    if elapsed>=CAP:status="TIMEOUT";satverified=False
    need(status!="SAT" or satverified,"unverified SAT")
    need(sha(p)==c["sha256"],"original SHA mutated after trial")
    return dict(sha256=c["sha256"],cohort="mixab3_source_only12",
                arm=arm,rep=rep,cap_s=CAP,
                status=status,backend_status=backend,
                SAT_original_witness_verified=satverified,
                UNSAT_independent_original_LRAT=False,
                one_logical_CPU=cpu,source_SHA_verified=True,
                wall_E2E_s=round(elapsed,6),
                parent_CPU_s=round(time.process_time()-parent_cpu,6),metrics=stats)
def shard(idx):
    m=verify()
    need(idx in (0,1),"bad shard")
    case=m["cases"][idx];records=[]
    for rep in range(REPS):
        order=list(ARMS)
        random.Random(case["sha256"]+"|N2D|"+str(rep)).shuffle(order)
        for arm in order:
            x=trial(case,rep,arm)
            need(x["wall_E2E_s"]<=CAP+.1,"cap violated")
            records.append(x)
            save(ROOT/f"shard-{idx}.json",records)
            print("NOVEL2D_TRIAL "+json.dumps(x,sort_keys=True),flush=True)
    need(len(records)==10,"missing SHA paired trials")
    print(f"NOVEL2D_SHARD_PASS {idx} 10",flush=True)
def audit():
    m=verify();rr=[]
    for i in range(2):
        x=load(ROOT/f"shard-{i}.json")
        need(len(x)==10,"incomplete shard")
        rr+=x
    expected={(c["sha256"],rep,arm) for c in m["cases"] for
             rep in range(REPS) for arm in ARMS}
    actual=[(r["sha256"],r["rep"],r["arm"]) for r in rr]
    need(set(actual)==expected and len(actual)==len(expected),
         "duplicate, missing or unexpected paired records")
    report={}
    for arm in ARMS:
        z=[r for r in rr if r["arm"]==arm]
        solved=[r for r in z if r["status"]=="SAT" and r["SAT_original_witness_verified"]]
        report[arm]=dict(attempts=4,verified_SAT=len(solved),
             raw_UNSAT_without_LRAT=sum(r["backend_status"]=="UNSAT" for r in z),
             timeouts=sum(r["status"]=="TIMEOUT" for r in z),
             solved_strict=len(solved),
             PAR2_strict_s=round(sum(r["wall_E2E_s"] if r in solved else 2*CAP for r in z),6),
             actual_wall_s=round(sum(r["wall_E2E_s"] for r in z),6),
             derived_proposals=sum(r["metrics"].get("derived_direct_proposals",0) for r in z),
             completed_reasons=sum(r["metrics"].get("reason_clauses_completed",0) for r in z),
             real_CDCL_decisions=sum(r["metrics"].get("decisions") or 0 for r in z))
    summary=dict(protocol=PROTO,cases=[c["sha256"] for c in m["cases"]],trials=20,
                 source_selection_source_only=True,previously_seen_not_blind=True,
                 UNSAT_independent_LRAT=False,one_logical_cpu=True,per_arm=report)
    save(ROOT/"report.json",summary)
    print("NOVEL2D_FINAL "+json.dumps(summary,sort_keys=True),flush=True)
def main():
    a=argparse.ArgumentParser();a.add_argument("task",choices=("freeze","verify","shard","audit"))
    a.add_argument("--shard",type=int)
    q=a.parse_args()
    if q.task=="freeze":freeze()
    elif q.task=="verify":verify();print("NOVEL2D_VERIFY_PASS",flush=True)
    elif q.task=="shard":shard(q.shard)
    else:audit()
if __name__=="__main__":main()
