#!/usr/bin/env python3
"""DRNAS MRE3 P1: two frozen SAT2026 sources, early guard and lemma-wise CDCL ablation.

On large sources MRE3 reads only the DIMACS header before calling native CMS;
it does not parse the full formula or derive/replay unnecessary CRR lemmas.
On the responsive SAT case, import each of the two selected proof-certified
CRR clauses individually, plus the both/full/shadow controls, and compare
ACTUAL native CMS propagation, decision and conflict counters.

This is per-lemma CAUSAL PRESENCE ABLATION, not a watch/BCP reason event hook.
An independent CMS source-level hook would be needed to prove direct use.
"""
from __future__ import annotations
import argparse, collections, hashlib, json, os, pathlib, random, statistics
import subprocess, sys, tempfile, time

sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import mre1_cross_representation as mre1
import mre2_impact_gate as mre2
import mre2_cdcl_pilot as pilot
import r195_native_cms_benchmark as r195
import r164_pure_exact_gf2 as exact

PROTO="DRNAS-MRE3-TWO-SOURCE-EARLY-ABLAT-2SEEDS-2REPS-v1"
ROOT=pathlib.Path("mre3_p1")
REPS=2
REPEATS=2
CAP=22.0
MODES={
  0:("native","xor","shadow","crr_all","crr_gate","lemma_0","lemma_1"),
  1:("native","xor","legacy_gate","early_guard","early_guard_repeat")
}
MAX_GATE_CNF=mre2.MAX_GATE_CNF


def need(ok, why):
    if not ok:
        raise RuntimeError("MRE3_FAIL_CLOSED "+str(why))


def header_count(path):
    """Only read DIMACS header, avoiding expensive full parser on guard path."""
    with open(path,"r",encoding="utf8") as f:
        for line in f:
            line=line.strip()
            if line.startswith("c") or not line:
                continue
            bits=line.split()
            need(len(bits)>=4 and bits[:2]==["p","cnf"],"bad frozen DIMACS header")
            return int(bits[2]),int(bits[3])
    need(False,"missing DIMACS header")


def prepare(source,mode,case_no):
    """Returns rows, imported clauses, metadata; every candidate proof replayed."""
    n,num_clauses=header_count(source)
    meta=dict(guarded=False,cnf_clauses=num_clauses,derived=0,
              selected=0,lemma_sha256=None,source_rows=0,
              gate={"selected":0,"probed":0,"new_implications":0,
                    "new_conflicts":0,"abstain":"not_run"})
    if mode in ("native","early_guard","early_guard_repeat"):
        need(mode=="native" or case_no==1,
             "guard mode only allowed on designated large case")
        if mode!="native":
            need(num_clauses>MAX_GATE_CNF,"guard must be justified by CNF size")
            meta["guarded"]=True
        return n,[],[],meta
    n2,original=exact.parse_dimacs(source)
    need(n2==n and len(original)==num_clauses,"header/parse drift")
    if mode=="xor":
        rows=r195.certified_source_rows(original)[:mre1.MAX_SOURCE_ROWS]
        mre1.replay_source_xors(original,rows)
        meta["source_rows"]=len(rows)
        return n,rows,[],meta
    rows,proofs,derive_info=mre1.derive(original)
    need(derive_info["proof_replayed"],"certified CRR proof not replayed")
    meta["derived"]=len(proofs)
    meta["source_rows"]=len(rows)
    if case_no==0:
        selected,gate=mre2.gate(original,proofs)
        need(len(selected)==2,"responsive SAT formula changed: expected exactly 2 gated lemmas")
        meta["gate"]=gate
    else:
        selected=[]
        meta["gate"]={"selected":0,"probed":0,"new_implications":0,
                      "new_conflicts":0,"abstain":"legacy_gate_after_derive"}
        need(num_clauses>MAX_GATE_CNF,"large UNSAT cohort lost guard criterion")
    if mode=="crr_all":
        imported=proofs
    elif mode=="crr_gate":
        imported=selected
    elif mode.startswith("lemma_"):
        idx=int(mode.split("_")[1])
        need(idx<len(selected),"missing chosen lemma")
        imported=[selected[idx]]
        meta["lemma_sha256"]=hashlib.sha256(
            json.dumps(selected[idx]["clause"],separators=(",",":")).encode()
        ).hexdigest()
    else:
        imported=[]
    # The only imported clauses must be among full independently replayed proofs.
    originals={tuple(p["clause"]) for p in proofs}
    need(all(tuple(p["clause"]) in originals for p in imported),
         "unproven imported lemma")
    meta["selected"]=len(imported)
    return n,rows,imported,meta


def one_trial(case_no,case,rep,repeat,mode,binary):
    src=r195.FROZEN/case["name"]
    began=time.perf_counter()
    need(r195.digest(src)==case["sha256"],"original SHA drift")
    n,rows,imported,meta=prepare(src,mode,case_no)
    prep_s=time.perf_counter()-began
    seed=int(hashlib.sha256((mre2.PROTO+case["sha256"]+str(rep))
                              .encode()).hexdigest()[:8],16)
    native_mode="cms_native" if mode in ("native","early_guard","early_guard_repeat") else "source_xor_no_gauss"
    status,model,stats="TIMEOUT",{},{}
    solver_s=None
    with tempfile.TemporaryDirectory(prefix="mre3-p1-") as tmp:
        tmp=pathlib.Path(tmp)
        cnf,xor,empty=tmp/"original-or-augmented.cnf",tmp/"rows.tsv",tmp/"empty.tsv"
        if imported:
            n2,original=exact.parse_dimacs(src)
            need(n2==n,"variable drift")
            mre1.write_cnf(cnf,n,original,imported)
        else:
            cnf=src
        mre1.write_xors(xor,rows)
        empty.write_text("")
        remain=CAP-(time.perf_counter()-began)
        if remain>0.1:
            t=time.perf_counter()
            try:
                p=subprocess.run(
                  [str(pathlib.Path(binary).resolve()),str(cnf),
                   str(xor),str(empty),native_mode,str(seed)],
                  text=True,capture_output=True,timeout=remain,check=False)
            except subprocess.TimeoutExpired:
                p=None
            solver_s=time.perf_counter()-t
            if p is not None:
                need(p.returncode==0,"CMS failed or invalid SAT witness: "+p.stderr[-900:])
                status,model,stats=r195.parsed_native(p.stdout)
                if status=="SAT":
                    r195.verify_model(src,model)
                if status in ("SAT","UNSAT"):
                    for k in ("propagations","conflicts","decisions"):
                        need(isinstance(stats.get(k),int),"missing actual CMS counter "+k)
    wall_s=time.perf_counter()-began
    if wall_s>=CAP:
        status="TIMEOUT"
    if status!="TIMEOUT":
        need(status==case["expected"],"incorrect solver verdict")
    return dict(protocol=PROTO,case=case["name"],source_sha256=case["sha256"],
                rep=rep,repeat=repeat,seed=seed,mode=mode,status=status,
                wall_s=round(wall_s,6),prep_s=round(prep_s,6),
                solver_s=round(solver_s,6) if solver_s is not None else None,
                par2_s=round(2*CAP if status=="TIMEOUT" else wall_s,6),
                native_cdcl_propagations=stats.get("propagations"),
                native_cdcl_conflicts=stats.get("conflicts"),
                native_cdcl_decisions=stats.get("decisions"),
                imported_lemmas=len(imported),source_xors=len(rows),
                meta=meta,otf_gauss=False,
                observation="causal_clause_presence_ablation_NOT_reason_watch_hook",
                proof=("ORIGINAL_CNF_SAT_MODEL_CHECKED" if status=="SAT"
                       else "UNSAT_NO_INDEPENDENT_LRAT" if status=="UNSAT"
                       else "CAP_TIMEOUT"),
                git_sha=os.environ.get("GITHUB_SHA","local"))


def run_case(case_no,binary):
    case=pilot.select_case(case_no)
    ROOT.mkdir(parents=True,exist_ok=True)
    rows=[]
    for rep in range(REPS):
        for repeat in range(REPEATS):
            modes=list(MODES[case_no])
            random.Random(PROTO+case["sha256"]+str(rep)+":"+str(repeat)).shuffle(modes)
            for mode in modes:
                row=one_trial(case_no,case,rep,repeat,mode,binary)
                rows.append(row)
                (ROOT/("case-%d.json"%case_no)).write_text(
                    json.dumps(rows,sort_keys=True)+"\n")
                print("MRE3_TRIAL",json.dumps(row,sort_keys=True),flush=True)
    need(len(rows)==REPS*REPEATS*len(MODES[case_no]),"incomplete case")
    print("MRE3_CASE_PASS",case_no,len(rows),flush=True)


def audit():
    bycase={}
    all_rows=[]
    for case_no in (0,1):
        cases=pilot.select_case(case_no)
        rows=json.loads((ROOT/("case-%d.json"%case_no)).read_text())
        need(len(rows)==REPS*REPEATS*len(MODES[case_no]),"missing case results")
        paired=collections.defaultdict(dict)
        for row in rows:
            need(row["protocol"]==PROTO and row["otf_gauss"] is False,
                 "protocol/OTF drift")
            need(row["source_sha256"]==cases["sha256"],"SHA drift")
            need(row["mode"] not in paired[(row["rep"],row["repeat"])],"duplicate")
            paired[(row["rep"],row["repeat"])][row["mode"]]=row
            if row["status"]=="SAT":
                need(row["proof"]=="ORIGINAL_CNF_SAT_MODEL_CHECKED","unverified SAT")
        for p in paired.values():
            need(set(p)==set(MODES[case_no]),"missing paired modes")
            need(len({x["status"] for x in p.values()
                      if x["status"]!="TIMEOUT"})<=1,
                 "verdict disagreement")
        grouped=collections.defaultdict(list)
        for row in rows:
            grouped[row["mode"]].append(row)
        bycase[cases["name"]]={}
        for mode in MODES[case_no]:
            a=grouped[mode]
            complete=[r for r in a if r["status"]!="TIMEOUT"]
            bycase[cases["name"]][mode]=dict(
                count=len(a),solved=len(complete),
                par2_s=round(sum(x["par2_s"] for x in a),6),
                median_wall_s=round(statistics.median(x["wall_s"] for x in a),6),
                prep_total_s=round(sum(x["prep_s"] for x in a),6),
                imported_lemmas=sum(x["imported_lemmas"] for x in a),
                mean_native_propagations=round(statistics.mean(
                    r["native_cdcl_propagations"] for r in complete),2) if complete else None,
                mean_native_decisions=round(statistics.mean(
                    r["native_cdcl_decisions"] for r in complete),2) if complete else None,
                mean_native_conflicts=round(statistics.mean(
                    r["native_cdcl_conflicts"] for r in complete),2) if complete else None)
        all_rows+=rows
    report=dict(protocol=PROTO,measurements=len(all_rows),total_expected=48,
                cases=bycase,OTF_GAUSS=False,original_SAT_model_verified=True,
                independent_UNSAT_LRAT=False,
                attribution="PER_LEMMA_CAUSAL_ABLATION_NOT_IN_CDCL_REASON_EVENT",
                sources_previously_used_development_NOT_blind=True)
    need(len(all_rows)==48,"expected 48 total paired measurements")
    (ROOT/"report.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print("MRE3_FINAL",json.dumps(report,sort_keys=True),flush=True)


def selftest():
    need(sum(REPS*REPEATS*len(v) for v in MODES.values())==48,"protocol")
    need(MODES[0][-2:]==("lemma_0","lemma_1"),"missing isolated arms")
    print("MRE3_SELFTEST_PASS",PROTO,flush=True)


if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("action",choices=("selftest","case","audit"))
    ap.add_argument("--case-no",type=int,default=0)
    ap.add_argument("--binary",default="mre3_p1/native")
    a=ap.parse_args()
    if a.action=="selftest":selftest()
    elif a.action=="case":run_case(a.case_no,a.binary)
    else:audit()
