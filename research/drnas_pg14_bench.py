#!/usr/bin/env python3
"""PG14: certified original-CNF, paired native congruence experiments.
Smoke tests verify SAT and UNSAT on tiny manually specified formulas.
Actual #12/#13/#82 source bytes come from frozen CF7 source artifact.
"""
import argparse,hashlib,json,os,pathlib,resource,signal,subprocess,tempfile,time
import drnas_clause_cf7_real100 as CF
R=pathlib.Path(__file__).resolve().parents[1]
OUT=pathlib.Path("pg14")
CHECKER="build/drat-trim"
def emit(mark,obj):print(mark+" "+json.dumps(obj,sort_keys=True),flush=True)
def one(path,arm,cap,source_id,expect=None):
    cnf=pathlib.Path(path)
    with tempfile.TemporaryDirectory() as tmp:
        proof=pathlib.Path(tmp)/"proof.drat"
        if arm=="PG14_CONGRUENCE":
            cmd=["build/drnas-pg14",str(cnf),"--mode","core","--time",str(cap),
                "--stats","--x5-no-minimize","--x5-no-retain",
                "--cf5-policy","B2L_32","--pg-congruence","--proof",str(proof)]
        elif arm=="PG14_OFF":
            cmd=["build/drnas-pg14",str(cnf),"--mode","core","--time",str(cap),
                "--stats","--x5-no-minimize","--x5-no-retain",
                "--cf5-policy","B2L_32","--proof",str(proof)]
        elif arm=="CF7_FROZEN":
            cmd=["build/drnas-clause-cf6",str(cnf),"--mode","core","--time",str(cap),
                "--stats","--x5-no-minimize","--x5-no-retain",
                "--cf5-policy","B2L_32","--proof",str(proof)]
        elif arm=="KISSAT":
            cmd=["build/kissat",str(cnf),str(proof)]
        elif arm=="CADICAL":
            cmd=["build/cadical","-q","--no-binary",str(cnf),str(proof)]
        else:raise ValueError(arm)
        begin=time.perf_counter()
        p=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                           text=True,start_new_session=True,
                           preexec_fn=lambda:resource.setrlimit(resource.RLIMIT_FSIZE,(512*1024*1024,512*1024*1024)))
        timed=False
        try:stdout,stderr=p.communicate(timeout=cap+0.25)
        except subprocess.TimeoutExpired:
            timed=True;os.killpg(p.pid,signal.SIGKILL);stdout,stderr=p.communicate()
        elapsed=time.perf_counter()-begin
        if not timed and p.returncode not in (0,10,20,153):
            raise RuntimeError(("SOLVER_PROCESS_ERROR",source_id,arm,p.returncode,stderr[-900:]))
        valid=False;verify_s=0;state="TIMEOUT" if timed else "UNKNOWN"
        if not timed and p.returncode==10:
            valid=CF.DATA.sat_witness_valid(cnf,CF.DATA.nvars(cnf),stdout)
            if not valid:raise RuntimeError(("WRONG_SAT",source_id,arm))
            state="SAT_VERIFIED"
        elif not timed and p.returncode==20:
            if not proof.is_file() or proof.stat().st_size==0:
                raise RuntimeError(("MISSING_UNSAT_PROOF",source_id,arm))
            t=time.perf_counter()
            check=subprocess.run([CHECKER,str(cnf),str(proof)],
                                 capture_output=True,text=True,timeout=90)
            verify_s=time.perf_counter()-t
            valid=check.returncode==0 and "s VERIFIED" in check.stdout
            if not valid:raise RuntimeError(("BAD_UNSAT_PROOF",source_id,arm,
                     check.stdout[-700:],check.stderr[-700:]))
            state="UNSAT_CERTIFIED"
        if expect is not None and state!=expect:
            raise RuntimeError(("SMOKE_EXPECTED",source_id,arm,expect,state))
        telemetry={}
        stats={}
        for line in stderr.splitlines():
            if line.startswith("PG14_PREPROCESS "):
                telemetry=json.loads(line.split(" ",1)[1])
            if line.startswith("X41_STATS "):
                stats=json.loads(line.split(" ",1)[1])
        if arm=="PG14_CONGRUENCE" and not telemetry:
            raise RuntimeError(("MISSING_PG14_METRICS",source_id))
        record={"id":source_id,"arm":arm,"cap_s":cap,
                "status":state,"accepted":bool(valid and elapsed<=cap),
                "wall_s":round(elapsed,6),
                "par2_verified_s":round(elapsed if valid and elapsed<=cap else 2*cap,6),
                "proof_bytes":proof.stat().st_size if proof.is_file() else 0,
                "verify_s":round(verify_s,6),
                "conflicts":stats.get("conflicts"),"decisions":stats.get("decisions"),
                "preprocess":telemetry}
        emit("PG14_TRIAL",record)
        return record
def smoke():
    CF.cpu_pin()
    with tempfile.TemporaryDirectory() as d:
        td=pathlib.Path(d)
        cases={
          # Same AND function encoded twice, followed by assertion that
          # outputs differ: impossible, but has no input unit clauses.
          "and_miter_unsat":("p cnf 4 8\n-3 1 0\n-3 2 0\n3 -1 -2 0\n"
                   "-4 1 0\n-4 2 0\n4 -1 -2 0\n3 4 0\n-3 -4 0\n","UNSAT_CERTIFIED"),
          "and_pair_sat":("p cnf 4 6\n-3 1 0\n-3 2 0\n3 -1 -2 0\n"
                          "-4 1 0\n-4 2 0\n4 -1 -2 0\n","SAT_VERIFIED"),
          "binary_scc_unsat":("p cnf 2 4\n1 2 0\n-1 2 0\n1 -2 0\n-1 -2 0\n",
                               "UNSAT_CERTIFIED"),
          "xor_sat":("p cnf 3 4\n1 2 3 0\n1 -2 -3 0\n-1 2 -3 0\n-1 -2 3 0\n",
                     "SAT_VERIFIED")
        }
        for name,(cnf,expected) in cases.items():
            path=td/(name+".cnf");path.write_text(cnf)
            out=one(path,"PG14_CONGRUENCE",2.5,name,expect=expected)
            if name=="and_miter_unsat":
                assert out["preprocess"]["gate_equalities"]>0,("NO_CONGRUENCE",out)
            if name=="binary_scc_unsat":
                assert out["preprocess"]["state"]=="binary_unsat",out
    emit("PG14_SMOKE_PASS",{"cases":4,"proof_certified":True,
                            "independent_original_cnf_checks":True})
def case(id):
    CF.cpu_pin()
    m=CF.checked_manifest()
    src=next(x for x in m["sources"] if x["id"]==id)
    cnf=pathlib.Path(src["path"])
    assert CF.sha(cnf.read_bytes())==src["sha256"]
    cases=[]
    for cap in (8.0,20.0):
        for arm in ("PG14_CONGRUENCE","PG14_OFF","CF7_FROZEN","KISSAT","CADICAL"):
            cases.append(one(cnf,arm,cap,id))
        outcome={x["status"] for x in cases[-5:] if x["status"] in ("SAT_VERIFIED","UNSAT_CERTIFIED")}
        assert len(outcome)<=1,("VERIFIED_DISAGREEMENT",id,cap)
    dest=OUT/str(id);dest.mkdir(parents=True,exist_ok=True)
    (dest/"trials.json").write_text(json.dumps(cases,indent=2,sort_keys=True)+"\n")
    emit("PG14_CASE_PASS",{"id":id,"sha256":src["sha256"],"attempts":len(cases)})
def final():
    all_rows=[]
    for id in (12,13,82):
        r=json.loads((OUT/"downloads"/("pg14-case-"+str(id))/"trials.json").read_text())
        assert len(r)==10
        all_rows.extend(r)
    assert len(all_rows)==30
    score={}
    for cap in (8.0,20.0):
        a=[x for x in all_rows if x["cap_s"]==cap]
        score[str(cap)]={}
        for arm in ("PG14_CONGRUENCE","PG14_OFF","CF7_FROZEN","KISSAT","CADICAL"):
            r=[x for x in a if x["arm"]==arm]
            assert len(r)==3
            score[str(cap)][arm]={"verified":sum(x["accepted"] for x in r),
                "par2_verified_s":round(sum(x["par2_verified_s"] for x in r),6)}
    dest=OUT/"final";dest.mkdir(parents=True,exist_ok=True)
    report={"status":"COMPLETE","cases":[12,13,82],"attempts":len(all_rows),
            "source":"SAT2024 original frozen CF7 retrospective",
            "no_blind_claim":True,"one_logical_cpu":True,
            "single_process_per_solver":True,"no_main_modification":True,
            "no_promotion":True,"scores":score}
    (dest/"report.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    emit("PG14_FINAL",report)
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("action",choices=("smoke","case","final"))
    p.add_argument("--id",type=int);args=p.parse_args()
    if args.action=="smoke":smoke()
    elif args.action=="case":case(args.id)
    else:final()
