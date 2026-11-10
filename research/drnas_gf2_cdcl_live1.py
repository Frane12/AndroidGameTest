#!/usr/bin/env python3
"""DRNAS GF2CDCL-LIVE1: source-exact parity -> real CaDiCaL IPASIR-UP CDCL.
Compare plain (same CaDiCaL 2.1), monitor, R96 incremental, R96 readiness
gate, novel source-unit-suppression, plus Kissat. 17 seen original SHA,
2 reps, 10s single logical CPU per solver, full source SHA/prepass/proof/E2E.
All exported rows independently replayed on ORIGINAL CNF and source units.
UNSAT without LRAT is scored only on source-original CaDiCaL+Kissat agreement.
"""
from __future__ import annotations
import argparse,collections,hashlib,json,os,pathlib,random,resource,subprocess,tempfile,time
import drnas_equiv9_prospective_seed_holdout as e9
import drnas_gf2_proof_first_s1 as gf
import r157_source_certified_xor as exporter

ROOT=pathlib.Path("mre_gf2cdcl_live1")
DRIVER=ROOT/"bin/gf2cdcl"
SOURCE=ROOT/"source"
PROTO="DRNAS-GF2CDCL-LIVE1-17SHA-6ARM-2REP-10S-ONECPU-v1"
CADICAL_SOURCE_SHA="31f9aae44947c673dc6190c9beb399acb9ffec6a"
ARMS=("cadical_clean","cadical_monitor","cadical_incremental",
      "cadical_active","cadical_novel","kissat_orig")
CAP=10.0
REPS=2
SHARDS=6
COUNT=17
TRIALS=COUNT*REPS*len(ARMS)
MAX_ROWS=100

def need(cond,why):
    if not cond:raise RuntimeError("GF2CDCL_LIVE1_FAIL_CLOSED "+str(why))
def save(file,obj):
    p=pathlib.Path(file);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(obj,indent=2,sort_keys=True)+"\n")
def source_sha(path):return e9.digest(path)
def source_cases():
    cs=gf.cases()
    need(len(cs)==COUNT and len({x["sha256"] for x in cs})==COUNT,"source roster drift")
    for c in cs:
        need(source_sha(e9.SOURCE/c["filename"])==c["sha256"],"source SHA mismatch")
    return cs
def hashes():
    return dict(code=source_sha(__file__),
      cpp=source_sha("research/drnas_gf2_cdcl_live1.cpp"),
      exporter=source_sha("research/r157_source_certified_xor.py"),
      driver=source_sha(DRIVER),kissat=source_sha(e9.KISSAT),
      old_manifest=source_sha(gf.ROOT/"manifest.json"))
def freeze():
    gf.verify()
    cs=source_cases()
    need(DRIVER.is_file(),"native live-CDCL driver missing")
    m=dict(protocol=PROTO,source_count=COUNT,trial_count=TRIALS,
      previously_seen_not_blind=True,source_only_SAT2024_25=False,
      source_SHA_frozen=True,source_roster=cs,
      native_CaDiCaL_release="rel-2.1.0",native_CaDiCaL_commit=CADICAL_SOURCE_SHA,
      ARMS=list(ARMS),cap_s=CAP,reps=REPS,shards=SHARDS,
      selected_rows_limit=MAX_ROWS,one_logical_CPU=True,
      real_native_IPASIR_UP=True,nonparallel_child_solver=True,
      independent_original_source_complete_parity_replay=True,
      original_input_unmodified=True,original_SAT_witness_independently_verified=True,
      UNSAT_only_original_baseline_solver_agreement_no_LRAT=True,
      no_auto_promotion=True,
      novelty_scope="suppress XOR unit clause only when source CNF already unit on observed trail; does not inspect learned clauses",
      fingerprints=hashes())
    save(ROOT/"manifest.json",m)
    verify()
    print("GF2CDCL_LIVE1_FROZEN "+json.dumps(dict(sources=COUNT,trials=TRIALS,
      arms=ARMS,CaDiCaL_commit=CADICAL_SOURCE_SHA,one_cpu=True,
      no_LRAT=True,not_blind=True),sort_keys=True),flush=True)
def verify():
    cs=source_cases()
    m=json.loads((ROOT/"manifest.json").read_text())
    need(m["protocol"]==PROTO and m["source_roster"]==cs and
         m["source_count"]==COUNT and m["trial_count"]==TRIALS and
         m["cap_s"]==CAP and m["reps"]==REPS and m["shards"]==SHARDS and
         m["ARMS"]==list(ARMS) and m["selected_rows_limit"]==MAX_ROWS and
         m["native_CaDiCaL_commit"]==CADICAL_SOURCE_SHA and
         m["fingerprints"]==hashes(),"source/code/backend drift")
    return m

def independently_check_rows(src,original,rows_path,proof_path):
    info=json.loads(pathlib.Path(proof_path).read_text())
    need(info["source_sha256"]==source_sha(src) and
         info["clauses"]==len(original),"original source parity proof SHA mismatch")
    unit={}
    signature=collections.defaultdict(set)
    for clause in original:
        if len(clause)==1:
            v=abs(clause[0]);bit=int(clause[0]>0)
            need(v not in unit or unit[v]==bit,"contradictory original units; abstain from live bridge")
            unit[v]=bit
        if not 2<=len(clause)<=6 or len({abs(l) for l in clause})!=len(clause):
            continue
        ordered=sorted(clause,key=abs)
        key=tuple(abs(x) for x in ordered)
        signature[key].add(sum(1<<i for i,x in enumerate(ordered) if x<0))
    cert=set()
    for vars_,maskset in signature.items():
        for forbidden_parity in (0,1):
            required={mask for mask in range(1<<len(vars_))
                      if mask.bit_count()%2==forbidden_parity}
            if required.issubset(maskset):
                cert.add((vars_,1-forbidden_parity))
    need(info["source_complete_parity_equations"]==len(cert),
         "independent complete source XOR scan disagrees")
    lines=[s.strip() for s in pathlib.Path(rows_path).read_text().splitlines() if s.strip()]
    selected=info["selected"]
    need(len(lines)==len(selected)==info["selected_rows"]<=MAX_ROWS,
         "row count wrong")
    unique=set()
    for line,rec in zip(lines,selected):
        parts=list(map(int,line.split()))
        k,rhs=parts[:2];vars_=tuple(parts[2:])
        need(2<=k<=6 and len(vars_)==k and
             tuple(sorted(set(vars_)))==vars_ and rhs in (0,1) and
             vars_==tuple(rec["vars"]) and rhs==rec["rhs"],
             "native input row differs from certified original evidence")
        original_vars=tuple(rec["source_vars"]);original_rhs=rec["source_rhs"]
        need((original_vars,original_rhs) in cert,
             "source XOR CNF pattern not complete")
        removed=tuple(rec["substituted_units"])
        need(removed==tuple(v for v in original_vars if v in unit) and
             vars_==tuple(v for v in original_vars if v not in unit),
             "unit substitutions do not match source literal units")
        expected_rhs=original_rhs
        for v in removed:expected_rhs^=unit[v]
        need(rhs==expected_rhs,"XOR parity after source units incorrect")
        need((vars_,rhs) not in unique,"duplicate derived row")
        unique.add((vars_,rhs))
    return dict(verified_rows=len(unique),source_exact_equations=len(cert),
                original_units=len(unit),original_SHA_verified=True,
                proof_type="original exact CNF XOR pattern and source-units independent replay")

def prepare(src,n,original,folder):
    row_path=pathlib.Path(folder)/"certified.tsv"
    proof_path=pathlib.Path(folder)/"source-proof.json"
    exporter.extract(src,row_path,proof_path,max_rows=MAX_ROWS)
    details=independently_check_rows(src,original,row_path,proof_path)
    need(details["verified_rows"]<=MAX_ROWS,"row budget exceeded")
    return row_path,details

def run_child(command,original,limit,cpu):
    def affinity():os.sched_setaffinity(0,{cpu})
    started=time.perf_counter()
    p=subprocess.Popen([str(q) for q in command],
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,
        preexec_fn=affinity,start_new_session=True)
    try:
        out,err=p.communicate(timeout=max(.01,limit-.015))
    except subprocess.TimeoutExpired:
        p.kill();out,err=p.communicate();return "TIMEOUT",False,{},time.perf_counter()-started
    wall=time.perf_counter()-started
    if wall>=limit:return "TIMEOUT",False,{},wall
    need(p.returncode in (10,20),
         "native CDCL child did not return SAT/UNSAT rc="+str(p.returncode)+" "+err[-400:])
    status,model=e9.x22.solver_result("GF2CDCL-LIVE1",p.returncode,out,original,{})
    metrics={}
    lines=[x for x in out.splitlines() if x.startswith("GF2CDCL_RESULT ")]
    if lines:
        need(len(lines)==1,"ambiguous live-CDCL metrics")
        for kv in lines[0][len("GF2CDCL_RESULT "):].split():
            if "=" in kv:
                key,value=kv.split("=",1)
                try:metrics[key]=float(value) if "." in value else int(value)
                except ValueError:metrics[key]=value
        need(metrics.get("disabled")==0,"unsafe IPASIR-UP callback state, no result accepted")
    return status,model,metrics,wall

def trial(case,rep,arm,limit=CAP):
    need(arm in ARMS and 0<=rep<REPS,"unsupported arm/rep")
    src=e9.SOURCE/case["filename"]
    cpu=min(os.sched_getaffinity(0))
    os.sched_setaffinity(0,{cpu})
    begin=time.perf_counter();main_cpu_before=time.process_time()
    child_before=e9.x22.child_cpu()
    need(source_sha(src)==case["sha256"],"source sha mismatch")
    n,clauses=e9.x22.read_cnf(src)
    need(n>0 and clauses,"missing original")
    mode=arm.removeprefix("cadical_")
    source_rows={};prep=0.0;metrics={};result="TIMEOUT";verified=False
    with tempfile.TemporaryDirectory(dir=ROOT) as folder:
        rows=pathlib.Path(folder)/"empty.tsv";rows.write_text("")
        if arm!="kissat_orig" and mode!="clean":
            rows,source_rows=prepare(src,n,clauses,folder)
        prep=time.perf_counter()-begin
        remaining=limit-prep
        if remaining>.07:
            if arm=="kissat_orig":
                cmd=e9.command("kissat1",src,e9.seedpair(case["sha256"],rep)[0])
            else:
                cmd=[DRIVER,mode,src,rows]
            result,verified,metrics,solverwall=run_child(cmd,clauses,remaining,cpu)
    elapsed=time.perf_counter()-begin
    if elapsed>=limit:result="TIMEOUT";verified=False
    need(result!="SAT" or verified,"SAT witness not verified against ORIGINAL")
    need(source_sha(src)==case["sha256"],"source changed during solver")
    need(metrics.get("xor_rows",source_rows.get("verified_rows",0))==
         source_rows.get("verified_rows",0),"native did not receive exact verified XOR rows")
    return dict(protocol=PROTO,arm=arm,source_sha=case["sha256"],gbd=case["gbd"],
       rep=rep,cap_s=limit,original_SHA_verified=True,
       original_CNF_unchanged=True,pinned_logical_CPU=cpu,
       one_solver_child_max=True,UNSAT_independent_LRAT=False,
       SAT_original_witness_verified=verified if result=="SAT" else False,
       status=result,wall_E2E_s=round(elapsed,6),
       parent_CPU_s=round(time.process_time()-main_cpu_before,6),
       child_CPU_s=round(e9.x22.child_cpu()-child_before,6),
       prep_E2E_s=round(prep,6),
       original_source_verified_XOR=source_rows,
       native_live_metrics=metrics)

def selftest():
    ROOT.mkdir(parents=True,exist_ok=True)
    need(DRIVER.exists(),"native driver missing")
    src=ROOT/"toy.cnf"
    # Two separately complete 3-XOR encodings, plus residual CNF.
    clauses=[]
    for vars_ in ((1,2,3),(1,2,4)):
        for mask in (1,2,4,7):
            clauses.append(tuple(-v if mask & (1<<i) else v
                                 for i,v in enumerate(vars_)))
    clauses.extend([(3,4),(1,4)])
    src.write_text("p cnf 4 %d\n"%len(clauses)+
                   "".join(" ".join(map(str,c))+" 0\n" for c in clauses))
    n,original=e9.x22.read_cnf(src)
    with tempfile.TemporaryDirectory(dir=ROOT) as folder:
        rows,proof=prepare(src,n,original,folder)
        need(proof["verified_rows"]>=1,"toy live parity source extraction absent")
        cpu=min(os.sched_getaffinity(0))
        answers={}
        for mode in ("clean","monitor","incremental","active","novel"):
            cmd=[DRIVER,mode,src,rows]
            status,checked,tele,wall=run_child(cmd,original,3,cpu)
            need(status=="SAT" and checked and tele.get("disabled")==0,
                 "toy original SAT model or callback state "+mode)
            answers[mode]=dict(SAT_model_verified=checked,
               emitted=tele.get("clauses_emitted"),suppressed=tele.get("source_unit_suppressed"))
    src.unlink()
    print("GF2CDCL_LIVE1_SELFTEST_PASS "+json.dumps(dict(
      independently_certified_rows=proof["verified_rows"],
      all_five_native_live_modes_original_SAT_verified=True,
      telemetry=answers),sort_keys=True),flush=True)

def shard(i):
    need(0<=i<SHARDS,"invalid shard")
    m=verify()
    cs=[x for k,x in enumerate(m["source_roster"]) if k%SHARDS==i]
    rows=[]
    for c in cs:
        for rep in range(REPS):
            order=list(ARMS)
            random.Random(c["sha256"]+"|"+str(rep)+"|"+PROTO).shuffle(order)
            for arm in order:
                q=trial(c,rep,arm);q["shard"]=i
                rows.append(q)
                save(ROOT/f"shard-{i}.json",rows)
                print("GF2CDCL_LIVE1_TRIAL "+json.dumps(q,sort_keys=True),flush=True)
    need(len(rows)==len(cs)*REPS*len(ARMS),"shard incomplete")
    print("GF2CDCL_LIVE1_SHARD_PASS "+json.dumps(dict(shard=i,trials=len(rows)),sort_keys=True),flush=True)

def audit():
    m=verify();rows=[]
    for i in range(SHARDS):
        a=json.loads((ROOT/f"shard-{i}.json").read_text())
        need(len(a)==len([c for k,c in enumerate(m["source_roster"]) if k%SHARDS==i])*REPS*len(ARMS),
             "missing shard "+str(i))
        rows.extend(a)
    expect={(c["sha256"],rep,arm) for c in m["source_roster"]
            for rep in range(REPS) for arm in ARMS}
    seen={(r["source_sha"],r["rep"],r["arm"]) for r in rows}
    need(len(rows)==len(expect)==len(seen)==TRIALS and seen==expect,
         "missing or duplicate E2E trial")
    bysha=collections.defaultdict(list)
    for x in rows:
        need(x["protocol"]==PROTO and x["original_SHA_verified"] and
             x["original_CNF_unchanged"] and x["one_solver_child_max"] and
             x["cap_s"]==CAP and x["wall_E2E_s"]<=CAP+.15 and
             (x["status"]!="SAT" or x["SAT_original_witness_verified"]),
             "unverified original proof or E2E cap")
        bysha[x["source_sha"]].append(x)
    agreed=set()
    for sha,rr in bysha.items():
        need(len({x["status"] for x in rr if x["status"]!="TIMEOUT"})<=1,
             "SAT and UNSAT original SHA disagreement")
        if (any(x["arm"]=="kissat_orig" and x["status"]=="UNSAT" for x in rr)
                and any(x["arm"]=="cadical_clean" and x["status"]=="UNSAT" for x in rr)):
            agreed.add(sha)
    def accepted(x):
        return x["status"]=="SAT" or (x["status"]=="UNSAT" and x["source_sha"] in agreed)
    def par2(x):return x["wall_E2E_s"] if accepted(x) else 2*CAP
    def score(rs):
        return dict(trials=len(rs),solved=sum(accepted(x) for x in rs),
            SAT_original_verified=sum(x["status"]=="SAT" for x in rs),
            UNSAT_original_crosssolver_agreement_no_LRAT=sum(
                x["status"]=="UNSAT" and x["source_sha"] in agreed for x in rs),
            UNSAT_unverified=sum(x["status"]=="UNSAT" and x["source_sha"] not in agreed for x in rs),
            timeouts=sum(x["status"]=="TIMEOUT" for x in rs),
            PAR2_s=round(sum(par2(x) for x in rs),6),
            wall_E2E_s=round(sum(x["wall_E2E_s"] for x in rs),6),
            total_CPU_s=round(sum(x["child_CPU_s"]+x["parent_CPU_s"] for x in rs),6),
            prep_s=round(sum(x["prep_E2E_s"] for x in rs),6),
            certified_rows_scanned=sum(x["original_source_verified_XOR"].get("verified_rows",0) for x in rs),
            live_signals=sum(x["native_live_metrics"].get("live_signals",0) for x in rs),
            live_clauses_emitted=sum(x["native_live_metrics"].get("clauses_emitted",0) for x in rs),
            source_unit_suppressed=sum(x["native_live_metrics"].get("source_unit_suppressed",0) for x in rs),
            overhead_gate_tripped=sum(x["native_live_metrics"].get("budget_off",0) for x in rs))
    scores={a:score([x for x in rows if x["arm"]==a]) for a in ARMS}
    ref=scores["cadical_clean"]["PAR2_s"]
    for v in scores.values():
        v["PAR2_speedup_vs_CaDiCaL_clean_x"]=round(ref/v["PAR2_s"],6)
    bypair={}
    look={(x["source_sha"],x["rep"],x["arm"]):x for x in rows}
    for mode in ARMS:
        if mode=="cadical_clean":continue
        diff=[]
        for c in m["source_roster"]:
            for rep in range(REPS):
                a=look[(c["sha256"],rep,mode)]
                b=look[(c["sha256"],rep,"cadical_clean")]
                diff.append(par2(a)-par2(b))
        bypair[mode]=dict(wins=sum(x<-.02 for x in diff),
            losses=sum(x>.02 for x in diff),ties=sum(abs(x)<=.02 for x in diff),
            PAR2_gain_s=round(-sum(diff),6),
            worst_regression_s=round(max(diff),6),
            best_gain_s=round(min(diff),6))
    report=dict(protocol=PROTO,sources=COUNT,trials=TRIALS,
        one_cpu=True,no_parallel_solvers=True,
        source_SHA_original_unchanged=True,not_blind=True,
        CaDiCaL_2_1_pinned_commit=CADICAL_SOURCE_SHA,
        independent_source_exact_XOR_proof=True,
        independent_original_SAT_model_verification=True,
        UNSAT_original_Kissat_CaDiCaL_agreement_SHA=sorted(agreed),
        independent_LRAT=False,no_auto_promotion=True,
        scores=scores,paired=bypair,
        per_shard={str(i):{a:score([x for x in rows if x["shard"]==i and x["arm"]==a])
                    for a in ARMS} for i in range(SHARDS)},
        per_SHA={sha:{a:[dict(rep=x["rep"],status=x["status"],E2E_s=x["wall_E2E_s"],
            emitted=x["native_live_metrics"].get("clauses_emitted",0),
            suppressed=x["native_live_metrics"].get("source_unit_suppressed",0),
            certified_rows=x["original_source_verified_XOR"].get("verified_rows",0))
            for x in rr if x["arm"]==a] for a in ARMS} for sha,rr in bysha.items()})
    save(ROOT/"report.json",report)
    print("GF2CDCL_LIVE1_FINAL "+json.dumps(report,sort_keys=True),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("freeze","verify","selftest","shard","audit"))
    p.add_argument("--shard",type=int,default=0)
    a=p.parse_args()
    if a.action=="shard":shard(a.shard)
    elif a.action=="selftest":selftest()
    else:
        globals()[a.action]()
        if a.action=="verify":print("GF2CDCL_LIVE1_VERIFY_PASS",flush=True)
