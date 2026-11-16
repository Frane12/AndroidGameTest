#!/usr/bin/env python3
"""IPG6 source CG2 original-Petersen proof-gated benchmark.

Cut discovery/proof construction:
 - original source clauses alone give three rank1 triangle cuts;
 - these source cuts + original positive ALO/ternary covers give nine
   NEW rank2 graph mutex constraints, WITHOUT invoking CDCL or DPLL.
 - a SEPARATE historical bounded-DPLL-generated pure POL certificate is
   appended to make a COMPLETE UNSAT proof for the original source.
   These nine new cuts DO NOT by themselves prove UNSAT.

Every original-source CG lemma is independently rechecked by exact
integer PB arithmetic, then the full 112-line POL proof is accepted by
pinned EXTERNAL VeriPB 3.0.2 on the exact source. Corruptions rejected.
One CPU, serial, no SAT solver. Not a blind benchmark.
"""
import hashlib,json,os,pathlib,subprocess,sys,time

ROOT=pathlib.Path(__file__).resolve().parents[1]
OUT=ROOT/"results/ipg6_rank2"
NATIVE=ROOT/"build/drnas-ipg5b-jobbranch"
OLD_CONV=ROOT/"research/ipg5e_pure_pol_from_source_rup.py"
GEN=ROOT/"research/ipg6_rank2_source_cg.py"
INDEP=ROOT/"research/ipg6_independent_rank2_checker.py"
VERIPB=ROOT/"veripb-tool/bin/veripb"
DRAT=ROOT/"drat-trim/drat-trim"
SHA="c2fefeffc1f9644ffd6f85728106a21c82dfc01d0d021f32d4d73569cc2bfb70"
sys.path.insert(0,str(ROOT/"research"))
from ipg1_fixtures import petersen

def invoke(args,timeout=30):
    start=time.perf_counter()
    try:
        p=subprocess.run(list(map(str,args)),capture_output=True,text=True,timeout=timeout)
        return p.returncode,round(time.perf_counter()-start,6),p.stdout+"\n"+p.stderr
    except subprocess.TimeoutExpired:
        return 124,round(time.perf_counter()-start,6),"TIMEOUT"

def run(log,args,limit=30):
    rc,s,text=invoke(args,limit)
    log.write_text(text)
    return rc,s,text

def must(x,reason):
    if not x:raise AssertionError(reason)

def main():
    if hasattr(os,"sched_setaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    OUT.mkdir(parents=True,exist_ok=True)
    source=OUT/"original_weighted_petersen_45v300c.cnf"
    source.write_bytes(petersen().encode("ascii"))
    must(hashlib.sha256(source.read_bytes()).hexdigest()==SHA,"source SHA changed")
    rup=OUT/"upstream_bounded_DPLL_100.rup"
    rc,search_s,out=run(OUT/"upstream_cpp.log",[
        NATIVE,source,"--output",rup],10)
    must(rc==0 and rup.exists(),"historical C++ no-CDCL source RUP missing")
    rc,check_s,out=run(OUT/"upstream_drat_trim.log",[
        DRAT,source,rup],20)
    must(rc==0 and "s VERIFIED" in out,"RUP suffix itself not source verified")
    old=OUT/"old_100_pol_only.pbp"
    meta=OUT/"old_100_pol_meta.json"
    rc,old_s,out=run(OUT/"historical_pol_convert.log",[
        sys.executable,OLD_CONV,
        "--cnf",source,"--source-rup",rup,"--pb-proof",old,
        "--meta",meta,"--expected-sha256",SHA],30)
    must(rc==0 and old.exists(),"historical pure POL suffix missing")
    d=json.loads(meta.read_text())
    must(d["veripb_rup_lines"]==0 and d["veripb_pol_lines"]==100,
         "historical suffix proof unexpectedly changed")
    rc,old_v_s,out=run(OUT/"historical_veripb.log",[
        VERIPB,"--cnf",source,old],30)
    must(rc==0 and "s VERIFIED UNSATISFIABLE" in out,
         "historical source suffix not externally VeriPB verified")
    candidate=OUT/"IPG6_RANK2_12SOURCECUTS_plus_100POL.pbp"
    report=OUT/"source_rank2_certificate.json"
    rc,gen_s,out=run(OUT/"rank2_generator.log",[
        sys.executable,GEN,"--cnf",source,
        "--old-pol",old,"--proof",candidate,"--meta",report],20)
    must(rc==0 and candidate.exists(),"original-source rank2 cut generator failed")
    info=json.loads(report.read_text())
    must(info["source_rank2_new_petersen_mutexes"]==9 and
         info["source_rank1_triangle_cuts"]==3 and
         info["total_POL_lines"]==112 and info["total_RUP_lines"]==0,
         "unexpected original-source cut coverage")
    rc,ic_s,out=run(OUT/"independent_source_integer_algebra.log",[
        sys.executable,INDEP,"--cnf",source,
        "--meta",report,"--proof",candidate],25)
    must(rc==0 and "IPG6_SOURCE_CG_ACCEPT " in out,
         "second independent exact source integer-PB checker failed")
    rc,vs,out=run(OUT/"independent_veripb3.0.2.log",[
        VERIPB,"--cnf",source,candidate],40)
    must(rc==0 and "s VERIFIED UNSATISFIABLE" in out,
         "VeriPB rejected 3 rank1 + 9 rank2 source cuts plus existing POL suffix")
    # Store a CUT-ONLY transcript; this is a NON-FINAL proof of intermediate
    # source lemmas. The actual complete externally verified proof is above.
    cut_excerpt=OUT/"SOURCE_CG_ONLY_12_pol_steps.txt"
    cut_excerpt.write_text("\n".join(candidate.read_text().splitlines()[2:14])+"\n")
    # Recheck robustness: metadata forgery, exact source SHA change, and
    # perturbing one proof parent ID must be rejected.
    forged=json.loads(report.read_text())
    forged["cut_records"][0]["source_CNF_clause_ids"][0]=1
    corrupt=OUT/"forged_cut_certificate.json"
    corrupt.write_text(json.dumps(forged)+"\n")
    rc,_,_=run(OUT/"tamper_cut_support.log",[
        sys.executable,INDEP,"--cnf",source,
        "--meta",corrupt,"--proof",candidate],15)
    must(rc!=0,"forged source CP support accepted")
    modified=OUT/"changed_source.cnf"
    modified.write_bytes(source.read_bytes()+b"c tampered SHA source\n")
    bad=OUT/"invalid_changed_source.pbp"
    rc,_,_=run(OUT/"tamper_source.log",[
        sys.executable,GEN,"--cnf",modified,"--old-pol",old,
        "--proof",bad,"--meta",OUT/"bad_source_meta.json"],15)
    must(rc!=0 and not bad.exists(),"modified original source got a new proof")
    lines=candidate.read_text().splitlines()
    modified_line=lines[:]
    modified_line[2]=modified_line[2].replace("139","1",1)
    forgedproof=OUT/"forged_proof_parent.pbp"
    forgedproof.write_text("\n".join(modified_line)+"\n")
    rc,_,_=run(OUT/"tamper_proof_parent.log",[
        sys.executable,INDEP,"--cnf",source,
        "--meta",report,"--proof",forgedproof],15)
    must(rc!=0,"forged PB proof parent source id accepted")
    result={
        "status":"PASS",
        "source_sha256":SHA,"source_original_variables":45,"source_original_clauses":300,
        "original_rank1_PB_cuts":3,
        "new_rank2_original_PB_graph_mutexes":9,
        "new_PB_source_only_lines":12,
        "source_original_independent_integer_arithmetic":True,
        "complete_POL_lines":112,
        "complete_RUP_lines":0,
        "old_DPLL_PB_suffix":100,
        "new_PB_cuts_alone_prove_UNSAT":False,
        "historical_source_DPLL_used_for_final_suffix":True,
        "source_cuts_verified_by_external_VerIPB":True,
        "tampered_source_metadata_and_CP_ids_rejected":True,
        "source_rank2_generator_s":gen_s,
        "new_full_proof_bytes":candidate.stat().st_size,
        "external_veripb_s":vs,
        "original_source_pol_suffix_baseline_bytes":old.stat().st_size,
        "errors":[],
        "scope":"Nine previously absent graph mutexes are derived directly from original source PB clauses via round2 CG, no DPLL for their derivation. Global UNSAT still uses frozen 100-POL DPLL-discovered suffix. No full search-free original proof, no general polynomial SAT or blind PAR2.",
    }
    (OUT/"summary.json").write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print("IPG6_RANK2_TOTAL "+json.dumps(result,sort_keys=True),flush=True)
    return 0

if __name__=="__main__":
    try:sys.exit(main())
    except (AssertionError,ValueError,OSError,KeyError,TypeError) as err:
        OUT.mkdir(parents=True,exist_ok=True)
        (OUT/"failure.json").write_text(json.dumps({
            "status":"FAIL","reason":str(err)})+"\n")
        print("IPG6_RANK2_FAILED "+str(err),flush=True)
        sys.exit(1)
