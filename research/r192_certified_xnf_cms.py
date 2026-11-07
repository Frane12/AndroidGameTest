#!/usr/bin/env python3
"""R192: independently certified complete source XOR patterns -> native CryptoMiniSat XNF.
One change: parity-preserving representation, not changed original CNF semantics.
Controls: original CMS default; original CMS forced Gauss; source-scan shadow
with original CMS forced Gauss; certified XNF forced Gauss; original R28 router.
Pinned 25 previously seen external originals + 13 synthetic controls: NOT BLIND.
All SAT witnesses checked on original SHA-frozen CNFs. Native UNSAT lacks LRAT.
"""
from __future__ import annotations
import argparse, collections, hashlib, itertools, json, pathlib, random, statistics, subprocess, time
import r188_feedback_benchmark as r188
import r191_selective_live_cms as r191

ROOT=pathlib.Path("r192")
SOURCE=pathlib.Path("r189/frozen")
PROTO="DRNAS-R192-SOURCE-CERTIFIED-NATIVE-XNF-5ARM-v1"
CAP=12.0
MAX_SCAN_S=0.75
REPS=2
SHARDS=12
MODES=("cms_default","cms_gauss_source","cms_scan_shadow","cms_certified_xnf","drnas_r28_router")

def need(ok,why):
    if not ok:raise RuntimeError("R192_FAIL_CLOSED "+str(why))
def sha(p):
    return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def save(p,obj):
    p=pathlib.Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(obj,indent=2,sort_keys=True)+"\n")
def sources():
    return r191.verify_sources()

def certify_xnf(n,clauses,rows):
    """Replace only complete, disjoint, independently truth-table-checked CNF parity blocks."""
    consumed=set(); selected=[]
    for vars_,rhs,parents in rows:
        vars_=tuple(vars_)
        k=len(vars_)
        if not (2<=k<=6) or rhs not in (0,1) or len(parents)!=(1<<(k-1)):
            continue
        ids=set(parents)
        if len(ids)!=len(parents) or ids&consumed:continue
        need(all(0<=i<len(clauses) for i in ids),"bad clause provenance")
        masks=set()
        for i in ids:
            clause=clauses[i]
            need(len(clause)==k and set(map(abs,clause))==set(vars_),
                 "source XOR parents do not match row")
            mask=sum(1<<j for j,v in enumerate(vars_) if -v in clause)
            masks.add(mask)
        need(len(masks)==1<<(k-1) and
             masks=={i for i in range(1<<k) if i.bit_count()%2==1-rhs},
             "source XOR truth-table parents incomplete")
        for bits in itertools.product((0,1),repeat=k):
            assignment=dict(zip(vars_,bits))
            block=all(any(bool(assignment[abs(l)])==(l>0) for l in clauses[i]) for i in ids)
            parity=(sum(bits)%2)==rhs
            need(block==parity,"source XOR truth-table violation")
        consumed.update(ids)
        selected.append((vars_,rhs))
    if not selected:return None,0,0
    lines=[f"p cnf {n} {len(clauses)-len(consumed)+len(selected)}"]
    for i,c in enumerate(clauses):
        if i not in consumed:lines.append(" ".join(map(str,c))+" 0")
    for vs,rhs in selected:
        lits=list(vs)
        if rhs==0:lits[0]=-lits[0]
        lines.append("x"+" ".join(map(str,lits))+" 0")
    return "\n".join(lines)+"\n",len(selected),len(consumed)

def extract(case,started):
    source=SOURCE/(case["id"]+".cnf")
    n,clauses=r188.gf.dimacs(source)
    if time.perf_counter()-started>MAX_SCAN_S:
        return None,0,0,"scan_budget_exhausted"
    rows,_=r188.ext.xor_source(clauses)
    if time.perf_counter()-started>MAX_SCAN_S:
        return None,0,0,"scan_budget_exhausted"
    body,count,covered=certify_xnf(n,clauses,rows)
    if time.perf_counter()-started>MAX_SCAN_S:
        return None,0,0,"cert_budget_exhausted"
    return body,count,covered,("certified" if body else "no_complete_xor")

def selftest():
    for k,rhs in ((3,0),(3,1),(4,0),(4,1)):
        vars_=list(range(1,k+1));clauses=[]
        for bits in itertools.product((0,1),repeat=k):
            if sum(bits)%2 != rhs:
                clauses.append([(-v if bits[v-1] else v) for v in vars_])
        rows,_=r188.ext.xor_source(clauses)
        xnf,nrows,nparents=certify_xnf(k,clauses,rows)
        need(nrows==1 and nparents==1<<(k-1),"synthetic parity cert failed")
        need("x" in xnf and len(xnf.splitlines())==2,"XNF encoding failed")
        for bits in itertools.product((0,1),repeat=k):
            original=all(any(bool(bits[abs(l)-1])==(l>0) for l in c) for c in clauses)
            need(original==(sum(bits)%2==rhs),"parity equivalence failed")
    print("R192_SELFTEST_PASS",flush=True)

def run_case(case,mode,rep,shard):
    src=SOURCE/(case["id"]+".cnf")
    need(sha(src)==case["sha256"],"original source drift")
    started=time.perf_counter()
    path=src;note="not_scanned";nrows=0;nparents=0;input_sha=case["sha256"]
    if mode in ("cms_scan_shadow","cms_certified_xnf"):
        body,nrows,nparents,note=extract(case,started)
        if body is not None and mode=="cms_certified_xnf":
            path=ROOT/"xnf"/f"shard-{shard}"/f"{case['id']}-r{rep}.xnf"
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(body)
            input_sha=sha(path)
    prep=time.perf_counter()-started
    if mode=="drnas_r28_router":
        cmd=[str(r191.BINARIES["r28_exact_router"].resolve()),str(src.resolve()),
             str(r191.BINARIES["kissat404"].resolve())]
    else:
        cmd=["cryptominisat5","--threads=1"]
        if mode!="cms_default":cmd+=["--maxnummatrices=5","--autodisablegauss=0"]
        cmd.append(str(path.resolve()))
    remaining=CAP-(time.perf_counter()-started)
    status="TIMEOUT";ok=False;proof="CAP_TIMEOUT";output="";return_code=None
    if remaining>0.08:
        try:
            p=subprocess.run(cmd,capture_output=True,text=True,errors="replace",
                             timeout=remaining,check=False)
            return_code=p.returncode
            output=p.stdout+"\n"+p.stderr
            status,model=r191.read_output(output,"ordinary",return_code)
            if status=="SAT":
                _,original=r188.gf.dimacs(src)
                r188.gf.sat_check(original,model)
                ok=True
                proof="SAT_WITNESS_ORIGINAL_CNF_VERIFIED"
            elif status=="UNSAT":
                proof="NO_INDEPENDENT_UNSAT_LRAT"
        except subprocess.TimeoutExpired:
            status="TIMEOUT"
    elapsed=time.perf_counter()-started
    if elapsed>=CAP:
        status="TIMEOUT";elapsed=CAP;proof="CAP_TIMEOUT"
    need(status in ("SAT","UNSAT","TIMEOUT"),"missing/invalid solver status")
    if case["expected"]!="UNKNOWN" and status!="TIMEOUT":
        need(status==case["expected"],"source truth disagreement")
    rec={"id":case["id"],"sha256":case["sha256"],"cohort":("external_original_25" if case["real"] else "synthetic_reference_13"),
         "family":case["family"],"rep":rep,"mode":mode,"status":status,
         "elapsed_s":round(elapsed,6),"par2_s":round(2*CAP if status=="TIMEOUT" else elapsed,6),
         "preprocessing_s":round(prep,6),"xnf_rows":nrows,"xnf_parent_clauses":nparents,
         "scan_outcome":note,"solver_input_sha256":input_sha,
         "used_native_xnf":bool(mode=="cms_certified_xnf" and path!=src),
         "witness_verified":ok,"proof":proof,"return_code":return_code}
    if output:
        log=ROOT/"raw"/f"shard-{shard}"/f"{case['id']}-{mode}-r{rep}.log"
        log.parent.mkdir(parents=True,exist_ok=True)
        log.write_text(output[-30000:])
    return rec

def shard(idx):
    cases=sources()
    need(0<=idx<SHARDS,"invalid shard")
    records=[]
    for c in cases[idx::SHARDS]:
        for rep in range(REPS):
            modes=list(MODES);random.Random(PROTO+c["sha256"]+str(rep)).shuffle(modes)
            for mode in modes:
                rec=run_case(c,mode,rep,idx)
                records.append(rec)
                save(ROOT/f"shard-{idx}.json",records)
                print("R192_TRIAL",json.dumps({k:rec[k] for k in
                  ("id","mode","rep","status","elapsed_s","xnf_rows","used_native_xnf",
                   "preprocessing_s","proof")},sort_keys=True),flush=True)
    need(len(records)==len(cases[idx::SHARDS])*REPS*len(MODES),"shard incomplete")
    print("R192_SHARD_PASS",idx,len(records),flush=True)

def audit():
    cases=sources();bysha={c["sha256"]:c for c in cases}
    records=[];keys=set()
    for idx in range(SHARDS):
        path=ROOT/f"shard-{idx}.json"
        need(path.is_file(),"missing shard "+str(idx))
        items=json.loads(path.read_text())
        need(len(items)==len(cases[idx::SHARDS])*REPS*len(MODES),"shard count mismatch")
        for r in items:
            key=(r["sha256"],r["rep"],r["mode"])
            need(key not in keys,"duplicate paired record")
            keys.add(key)
            need(r["sha256"] in bysha and r["mode"] in MODES and r["rep"] in range(REPS),"unfrozen case")
            need(r["par2_s"]==round(2*CAP if r["status"]=="TIMEOUT" else r["elapsed_s"],6),
                 "PAR-2 mismatch")
            if r["status"]=="SAT":need(r["witness_verified"] and r["proof"]=="SAT_WITNESS_ORIGINAL_CNF_VERIFIED",
                                       "unverified SAT model")
            if r["status"]=="UNSAT":need(r["proof"]=="NO_INDEPENDENT_UNSAT_LRAT","UNSAT provenance incorrect")
            if r["used_native_xnf"]:need(r["xnf_rows"]>0 and r["xnf_parent_clauses"]>0 and
                 r["solver_input_sha256"]!=r["sha256"],"native XNF provenance invalid")
        records.extend(items)
    need(len(records)==38*REPS*len(MODES)==380,"expected exactly 380 original-source attempts")
    for c in cases:
        for rep in range(REPS):
            need({r["mode"] for r in records if r["sha256"]==c["sha256"] and r["rep"]==rep}
                 ==set(MODES),"paired modes incomplete")
    report={"protocol":PROTO,"status":"R192_AUDIT_PASS","frozen_source_manifest_sha":r191.SOURCE_SHA,
            "source_sha_verified":True,"not_blind":True,"originals":25,"synthetic_controls":13,
            "attempts":len(records),"cap_s":CAP,"reps":REPS,"source_truth_checked":True,
            "independent_unsat_lrat":False,"hypothesis":"source-certified XNF input vs same-scan shadow CMS",
            "cohorts":{}}
    for label,subset in (("all",records),("external_original_25",[r for r in records if r["cohort"]=="external_original_25"]),
                         ("synthetic_reference_13",[r for r in records if r["cohort"]=="synthetic_reference_13"])):
        scores={}
        for mode in MODES:
            a=[r for r in subset if r["mode"]==mode]
            scores[mode]={"attempts":len(a),"solved":sum(r["status"]!="TIMEOUT" for r in a),
                         "sat":sum(r["status"]=="SAT" for r in a),
                         "unsat":sum(r["status"]=="UNSAT" for r in a),
                         "timeouts":sum(r["status"]=="TIMEOUT" for r in a),
                         "par2_s":round(sum(r["par2_s"] for r in a),6),
                         "preprocessing_s":round(sum(r["preprocessing_s"] for r in a),6),
                         "native_xnf_activations":sum(bool(r["used_native_xnf"]) for r in a),
                         "certified_xnf_rows":sum(r["xnf_rows"] for r in a if r["used_native_xnf"])}
        report["cohorts"][label]=scores
    for name in ("cms_gauss_source","cms_scan_shadow","cms_default"):
        original={(r["sha256"],r["rep"]):r for r in records if r["mode"]==name}
        transformed={(r["sha256"],r["rep"]):r for r in records if r["mode"]=="cms_certified_xnf"}
        gain=sum(original[k]["par2_s"]-v["par2_s"] for k,v in transformed.items())
        report["cohorts"]["all"][f"paired_xnf_vs_{name}"]={
            "par2_gain_s":round(gain,6),
            "wins":sum(v["par2_s"]<original[k]["par2_s"]-0.000001 for k,v in transformed.items()),
            "losses":sum(v["par2_s"]>original[k]["par2_s"]+0.000001 for k,v in transformed.items()),
            "ties":sum(abs(v["par2_s"]-original[k]["par2_s"])<=0.000001 for k,v in transformed.items())}
    save(ROOT/"report.json",report);save(ROOT/"all-trials.json",records)
    summary=["# R192 — certified native XOR/XNF vs CryptoMiniSat","",
             "Same 38 frozen sources as R191, NOT BLIND. All SAT models checked on original CNF.",
             "Native UNSAT lacks independent LRAT. PAR2 includes certification and preprocessing.",""]
    for label,sc in report["cohorts"].items():
        summary += ["## "+label,"","| Mode | Solved | SAT | UNSAT | PAR2 s | Prep s | XNF activations |",
                    "|---|---:|---:|---:|---:|---:|---:|"]
        for mode in MODES:
            v=sc[mode]
            summary.append(f"| {mode} | {v['solved']}/{v['attempts']} | {v['sat']} | {v['unsat']} | {v['par2_s']} | {v['preprocessing_s']} | {v['native_xnf_activations']} |")
    (ROOT/"summary.md").write_text("\n".join(summary)+"\n")
    print("R192_FINAL",json.dumps({"status":report["status"],"manifest":report["frozen_source_manifest_sha"],
          "attempts":len(records),"cohorts":report["cohorts"]},sort_keys=True),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("action",choices=["selftest","shard","audit"])
    p.add_argument("--shard",type=int,default=0)
    args=p.parse_args()
    if args.action=="selftest":selftest()
    elif args.action=="shard":shard(args.shard)
    else:audit()
