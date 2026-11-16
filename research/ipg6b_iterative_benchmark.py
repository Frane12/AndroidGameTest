#!/usr/bin/env python3
"""IPG6B: source-algebra rank4 iterative CP closure on original Petersen.

Runs previous IPG6 original-source proof audit as frozen tested input;
then discovers triangle-to-pair-to-triangle-to-pair PB derivations
without calling DPLL, CDCL or LP DURING THE NEW CUT SEARCH.
The baseline 100-POL suffix is still based on structural DPLL
and is included solely to produce an externally checkable UNSAT proof.

Strict independent source-integer PB replay and pinned external VeriPB
on unchanged original 300-clause CNF; tampered support and changed exact
source bytes must be rejected. No blind competition PAR2 claim.
"""
import hashlib,json,os,pathlib,subprocess,sys,time

ROOT=pathlib.Path(__file__).resolve().parents[1]
OUT=ROOT/"results/ipg6b_rank4"
BASE=ROOT/"results/ipg6_rank2"
GEN=ROOT/"research/ipg6b_iterative_source_cg.py"
CHECK=ROOT/"research/ipg6b_independent_source_pb_checker.py"
VP=ROOT/"veripb-tool/bin/veripb"
SHA="c2fefeffc1f9644ffd6f85728106a21c82dfc01d0d021f32d4d73569cc2bfb70"

def cmd(args,limit=45):
    begin=time.perf_counter()
    try:
        r=subprocess.run([str(x) for x in args],capture_output=True,text=True,timeout=limit)
        return r.returncode,round(time.perf_counter()-begin,6),r.stdout+"\n"+r.stderr
    except subprocess.TimeoutExpired:
        return 124,round(time.perf_counter()-begin,6),"TIMEOUT"
def logged(name,args,limit=45):
    rc,s,out=cmd(args,limit)
    (OUT/(name+".log")).write_text(out)
    return rc,s,out
def require(cond,msg):
    if not cond:raise AssertionError(msg)
def main():
    if hasattr(os,"sched_setaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    OUT.mkdir(parents=True,exist_ok=True)
    cnf=BASE/"original_weighted_petersen_45v300c.cnf"
    old=BASE/"old_100_pol_only.pbp"
    require(cnf.exists() and old.exists(),"frozen IPG6 baseline outputs missing")
    require(hashlib.sha256(cnf.read_bytes()).hexdigest()==SHA,
            "source bytes are not original Petersen CNF")
    pb=OUT/"IPG6B_21_SOURCE_CG_PLUS_100_POL.pbp"
    meta=OUT/"rank4_source_certificate.json"
    rc,gensec,log=logged("generator",[
        sys.executable,GEN,"--cnf",cnf,"--old-pol",old,
        "--proof",pb,"--meta",meta],25)
    require(rc==0 and pb.is_file(),"iterative rank4 PB source generator failed")
    data=json.loads(meta.read_text())
    require(data["new_source_mutexes"]==15 and
            data["new_source_only_pol_lines"]==21 and
            data["full_POL_lines"]==121 and
            data["full_RUP_lines"]==0,
            "bad rank4 output arity or provenance")
    rc,checksec,log=logged("independent_integer_source_checker",[
        sys.executable,CHECK,"--cnf",cnf,"--meta",meta,
        "--proof",pb],25)
    require(rc==0 and "IPG6B_SOURCE_CG_ACCEPT " in log,
            "independent source-only arithmetic audit rejected")
    rc,externalsec,log=logged("external_VerIPB3",[
        VP,"--cnf",cnf,pb],40)
    require(rc==0 and "s VERIFIED UNSATISFIABLE" in log,
            "external VeriPB3.0.2 rejected source rank4 121-POL proof")
    first=pb.read_text().splitlines()[2:23]
    (OUT/"source_only_rank4_21_pol.txt").write_text("\n".join(first)+"\n")
    tampered=OUT/"tampered_original.cnf"
    tampered.write_bytes(cnf.read_bytes()+b"c changed original source hash\n")
    invalid=OUT/"invalid_source.pbp"
    rc,_,_=logged("tamper_source",[
        sys.executable,GEN,"--cnf",tampered,"--old-pol",old,
        "--proof",invalid,"--meta",OUT/"invalid.json"],25)
    require(rc!=0 and not invalid.exists(),"source-tampered rank4 proof was accepted")
    fake=json.loads(meta.read_text())
    fake["new_source_mutexes"]=14
    fpath=OUT/"forged_meta.json"
    fpath.write_text(json.dumps(fake)+"\n")
    rc,_,_=logged("tamper_count",[
        sys.executable,CHECK,"--cnf",cnf,"--meta",fpath,
        "--proof",pb],25)
    require(rc!=0,"forged source-rank4 metadata accepted")
    result={
        "status":"PASS","source_sha256":SHA,
        "original_source_vars":45,"original_source_clauses":300,
        "original_source_rank1_triangle_bounds":3,
        "source_rank2_new_graph_mutexes":9,
        "derived_source_rank3_triangle_bounds":3,
        "new_source_rank4_graph_mutexes":6,
        "non_source_graph_mutexes_now_derived":15,
        "source_only_POL_lines":21,
        "full_original_source_POL_lines":121,
        "full_RUP_lines":0,
        "old_DPLL_discovered_suffix_POL_lines":100,
        "new_cuts_discovered_without_DPLL":True,
        "original_full_UNSAT_without_DPLL":False,
        "new_CG_only_does_not_complete_UNSAT":True,
        "independent_source_integer_PB_check":True,
        "external_veripb_UNSAT_verified":True,
        "source_SHA_tamper_rejected":True,
        "forged_metadata_rejected":True,
        "pure_source_cut_generator_s":gensec,
        "source_integer_checker_s":checksec,
        "external_VerIPB_s":externalsec,
        "final_proof_bytes":pb.stat().st_size,
        "discovered_triangle_groups":data["automatically_discovered_triangle_capacity_groups"],
        "CG_closure_rounds":data["source_CG_closure_rounds"],
        "scope":"Fifteen non-source Petersen graph mutexes from source-supported rank1..rank4 PB cutting planes. Global UNSAT still uses older 100 POL suffix discovered by DPLL. Not a standalone pure cutting-planes original PCMAX proof and not P=NP.",
    }
    (OUT/"summary.json").write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print("IPG6B_SOURCE_CG_TOTAL "+json.dumps(result,sort_keys=True),flush=True)
    return 0
if __name__=="__main__":
    try:sys.exit(main())
    except (AssertionError,ValueError,KeyError,OSError,TypeError) as err:
        OUT.mkdir(parents=True,exist_ok=True)
        (OUT/"failure.json").write_text(json.dumps({"status":"FAIL","reason":str(err)})+"\n")
        print("IPG6B_FAILED "+str(err),flush=True)
        sys.exit(1)
