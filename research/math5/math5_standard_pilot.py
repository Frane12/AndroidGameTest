#!/usr/bin/env python3
"""Reproducible E2E original-count source test of MATH5 -> VeriPB 3.0.

The original CNF, X59+MATH5 executable and official VeriPB binary are
restored from frozen GRAND-UNIFIED run 43853390060. No solver-produced
answer is accepted without source-checker + external VeriPB.
One logical CPU. 8s E2E cap includes solver, emission and verification.
"""
import hashlib,itertools,json,os,pathlib,resource,subprocess,sys,tempfile,time

ROOT=pathlib.Path(__file__).resolve().parents[2]
OUT=ROOT/"results/math5_standard1"
EXPECTED="8020990ff906e9b2f7ec72652da7db736d90db4170e104a888454dffa583aa88"
SOURCE=ROOT/"unified_realblind100_inputs/cnf/31-b0142b06940fb02e2b4ddb7a2101a3d6.cnf"
SOLVER=ROOT/"build/drnas-x59-xor-math5-unified1"
CHECKER=ROOT/"research/math5/check_math5.py"
EMIT=ROOT/"research/math5/emit_veripb_eo_multiplicity.py"
VERIPB=ROOT/"veripb-tool/bin/veripb"
KISSAT=ROOT/"build/kissat"
DRAT=ROOT/"build/drat-trim"
CAP=8.0

def execute(cmd,remaining):
    start=time.perf_counter()
    try:
        p=subprocess.run(list(map(str,cmd)),capture_output=True,text=True,
                         timeout=max(.001,remaining),
                         env=dict(os.environ,OMP_NUM_THREADS="1",OPENBLAS_NUM_THREADS="1",
                                  MKL_NUM_THREADS="1"))
        return {"rc":p.returncode,"seconds":time.perf_counter()-start,
                "expired":False,"stdout":p.stdout,"stderr":p.stderr}
    except subprocess.TimeoutExpired:
        return {"rc":124,"seconds":time.perf_counter()-start,
                "expired":True,"stdout":"","stderr":"TIMEOUT"}

def require(condition,message):
    if not condition:raise RuntimeError(message)

def one(rep):
    with tempfile.TemporaryDirectory(prefix="math5-standard-") as td:
        temp=pathlib.Path(td)
        cert=temp/"structural.json";pbp=temp/"proof.pbp";meta=temp/"emission.json"
        started=time.perf_counter()
        solve=execute([SOLVER,SOURCE,"--mode","core","--time",str(CAP),
                       "--sat-construct-ms","25","--math5-ms","100",
                       "--math5-certificate",cert,"--stats"],CAP)
        require(not solve["expired"] and solve["rc"]==20 and
                "s UNSATISFIABLE" in solve["stdout"] and cert.exists(),
                "original count MATH5 native source proof not produced")
        remaining=CAP-(time.perf_counter()-started)
        chk=execute([sys.executable,CHECKER,SOURCE,cert],remaining)
        require(chk["rc"]==0 and "UNSAT_MATH5_CERTIFICATE_VERIFIED" in chk["stdout"],
                "original source checker refused structural witness")
        remaining=CAP-(time.perf_counter()-started)
        emitted=execute([sys.executable,EMIT,"--cnf",SOURCE,"--certificate",cert,
                         "--output",pbp,"--meta",meta],remaining)
        require(emitted["rc"]==0 and pbp.exists(),"cutting-planes source proof emitter rejected")
        remaining=CAP-(time.perf_counter()-started)
        verified=execute([VERIPB,"--cnf",SOURCE,pbp],remaining)
        require(verified["rc"]==0 and "s VERIFIED UNSATISFIABLE" in
                verified["stdout"]+verified["stderr"],"external standard VeriPB rejected")
        elapsed=time.perf_counter()-started
        require(elapsed<=CAP,"source solver/emitter/verifier exceeded E2E cap")
        proof=json.loads(meta.read_text())
        require(proof["source_sha256"]==EXPECTED,"wrong source bound")
        return {"rep":rep,"status":"UNSAT_VERIPB_VERIFIED","e2e_s":round(elapsed,6),
                "solver_s":round(solve["seconds"],6),
                "project_checker_s":round(chk["seconds"],6),
                "pb_emission_s":round(emitted["seconds"],6),
                "veripb_checker_s":round(verified["seconds"],6),
                "proof_bytes":pbp.stat().st_size,
                "proof_sha256":hashlib.sha256(pbp.read_bytes()).hexdigest(),
                "source_sha256":EXPECTED,"par2_s":round(elapsed,6)}

def negative_tests():
    # Test a satisfiable four-vertex perfect-matching exact-one system:
    # K4 edges are selectors, and each vertex requires exactly one edge.
    groups=[[1,2,3],[1,4,5],[2,4,6],[3,5,6]]
    src=[list(g) for g in groups]
    for group in groups:
        src.extend([[-a,-b] for a,b in itertools.combinations(group,2)])
    model={v:(v in (1,6)) for v in range(1,7)}
    require(all(any(model[abs(l)]==(l>0) for l in c) for c in src),"SAT control incorrect")
    with tempfile.TemporaryDirectory() as td:
        t=pathlib.Path(td)
        cnf=t/"sat.cnf";proof=t/"false_math5.json";output=t/"bad.pbp"
        cnf.write_text("p cnf 6 "+str(len(src))+"\n"+
          "".join(" ".join(map(str,c))+" 0\n" for c in src))
        cert={"format":"drnas-math5-eo-xor-unit-v1",
              "source_sha256":hashlib.sha256(cnf.read_bytes()).hexdigest(),
              "exact_one_groups":groups,"xor_rows":[],"root_units":[]}
        proof.write_text(json.dumps(cert))
        r=execute([sys.executable,EMIT,"--cnf",cnf,"--certificate",proof,
                   "--output",output],5)
        require(r["rc"]!=0 and not output.exists(),
                "standard proof emitter accepted known SAT control")
        forged=t/"corrupt.cnf"
        forged.write_bytes(cnf.read_bytes()+b"c changed source\n")
        r=execute([sys.executable,EMIT,"--cnf",forged,
                   "--certificate",proof,"--output",output],5)
        require(r["rc"]!=0 and not output.exists(),
                "emitter ignored changed source SHA")
    return {"sat_control_rejected":True,"changed_source_rejected":True}

def main():
    if hasattr(os,"sched_setaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    OUT.mkdir(parents=True,exist_ok=True)
    for binary in (SOLVER,VERIPB,KISSAT,DRAT):
        require(binary.is_file(),"missing frozen binary "+str(binary))
    require(hashlib.sha256(SOURCE.read_bytes()).hexdigest()==EXPECTED,
            "source SHA not frozen original")
    controls=negative_tests()
    trials=[]
    for rep in (0,1):
        row=one(rep);trials.append(row)
        print("MATH5_STANDARD_TRIAL "+json.dumps(row,sort_keys=True),flush=True)
    summary={"status":"PASS","source_sha256":EXPECTED,
             "original_count_cnf":True,"source_variables":210,"source_clauses":4011,
             "attempts":len(trials),"veripb_standard_verified":len(trials),
             "e2e_par2_s":round(sum(t["par2_s"] for t in trials),6),
             "times_s":[t["e2e_s"] for t in trials],
             "proof_bytes":[t["proof_bytes"] for t in trials],
             "controls":controls,
             "note":"Source-frozen post-discovery test; fixed identical original count source, no blind claim. External VeriPB 3.0.2 independently validates each cutting-planes refutation. No general mixed-XOR standard proof supported."}
    (OUT/"trials.json").write_text(json.dumps(trials,sort_keys=True,indent=2)+"\n")
    (OUT/"summary.json").write_text(json.dumps(summary,sort_keys=True,indent=2)+"\n")
    print("MATH5_STANDARD_FINAL "+json.dumps(summary,sort_keys=True),flush=True)

if __name__=="__main__":main()
