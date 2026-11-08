#!/usr/bin/env python3
"""DRNAS MRE4 P1: proof-first, cost-gated and ablated CMS mathematical reduction.

Research build -- not an in-CDCL DRNAS reason callback. CMS 5.11.15's ACTUAL
propagation/conflict/decision counters are read after each solve. A paired
active-vs-shadow comparison tests causal impact of certified imported clauses.
Per-lemma reason consumption needs a subsequent source-instrumented CMS build.

KEEP: R164/R28 exact fast-path (SAT with original model check; UNSAT abstains),
MRE3 header early guard, MRE1 independently replayed CNF/GF(2) short proofs,
MRE2 bounded impact probe, T6A subsecond cost cap, R195 original SAT witness
audit, frozen SHA & native matched configuration.
DISABLE: risky CMS OTF Gauss; uncertified XOR, unconstrained bulk import,
unbounded full-CNF preprocessing, YalSAT on original-holdout, guessed parity,
any active lemma lacking independent proof and useful measured UP effect.
"""
from __future__ import annotations
import argparse, collections, hashlib, json, os, pathlib, random, subprocess
import sys, tempfile, time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import r195_native_cms_benchmark as r195
import r164_pure_exact_gf2 as exact
import mre1_cross_representation as mre1
import mre2_impact_gate as mre2

PROTO="DRNAS-MRE4-SAFE-CAUSAL-P1-32SHA-5ARM-2REPS-30S-v1"
ROOT=pathlib.Path("mre4_p1")
MODES=("cms_native","r28_safe","xor_no_otf","crr_shadow","crr_active")
SHARDS=8
REPS=2
CAP=30.0
MAX_CNF_FOR_WORK=35000
MAX_CNF_FOR_CRR=10000
MAX_BYTES_FOR_WORK=20_000_000
MIN_CNF_FOR_WORK=500
MAX_SOURCE_ROWS=32
MAX_ADDED_LEMMAS=2
MAX_DERIVE_BUDGET=.08
MAX_BCP_BUDGET=.035
MAX_TOTAL_PREP=.27
MAX_R28_CNF=20000
MIN_R28_CNF=2500
PREFIX_CLAUSES=640
PREFIX_BYTES=170000

def need(ok,why):
    if not ok: raise RuntimeError("MRE4_FAIL_CLOSED: "+str(why))

def save(p,obj):
    p=pathlib.Path(p)
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(obj,indent=2,sort_keys=True)+"\n")

def sha(s):return hashlib.sha256(s.encode()).hexdigest()

def header(path):
    with pathlib.Path(path).open("rt",encoding="utf-8",errors="strict") as f:
        for line in f:
            s=line.strip()
            if not s or s.startswith("c"):continue
            parts=s.split()
            need(parts[:2]==["p","cnf"] and len(parts)==4,"invalid original DIMACS header")
            n,m=int(parts[2]),int(parts[3])
            need(n>0 and m>0,"invalid header values")
            return n,m
    need(False,"missing DIMACS header")

def prefix_signal(path):
    """Bounded header + prefix only; conservative false negatives are allowed."""
    n,m=header(path)
    st=pathlib.Path(path).stat()
    sig=dict(vars=n,clauses=m,bytes=st.st_size,seen=0,found_xor_rows=0,
             reason=None)
    if st.st_size>MAX_BYTES_FOR_WORK or m>MAX_CNF_FOR_WORK or m<MIN_CNF_FOR_WORK:
        sig["reason"]="cheap_size_abstain"
        return sig
    prefix=[]
    current=[]
    total_bytes=0
    with pathlib.Path(path).open("rt",encoding="utf-8") as f:
        for line in f:
            total_bytes+=len(line)
            if total_bytes>PREFIX_BYTES or len(prefix)>=PREFIX_CLAUSES:break
            s=line.strip()
            if not s or s.startswith(("c","p","%")):continue
            for w in s.split():
                v=int(w)
                if v==0:
                    prefix.append(tuple(current)); current=[]
                    if len(prefix)>=PREFIX_CLAUSES:break
                else:current.append(v)
    sig["seen"]=len(prefix)
    sig["found_xor_rows"]=len(r195.certified_source_rows(prefix))
    sig["reason"]="xor_prefix_present" if sig["found_xor_rows"] else "no_prefix_xor"
    return sig

def prepare(source,mode):
    begun=time.perf_counter()
    sig=prefix_signal(source)
    meta=dict(signal=sig,route="cms_fallback",source_rows=0,
        derived_lemmas=0,approved_lemmas=0,approx_root_units=0,
        root_probe_implications=0,root_probe_conflicts=0,
        proof_replayed=False,source_proof_replayed=False,
        prep_abstain=None,preparation_s=0.0,
        unsafe_otf_gauss=False,actual_reason_callback=False,
        direct_cms_event_count=None)
    source_rows=[];imported=[];pure_status=None;pure_proof=None
    m=sig["clauses"]
    if mode=="cms_native":
        meta["route"]="cms_native"
        return source_rows,imported,meta,pure_status,pure_proof
    if sig["reason"]!="xor_prefix_present":
        meta["prep_abstain"]="no_cheap_eligibility"
        return source_rows,imported,meta,pure_status,pure_proof
    # R28 fast-path on medium/large exact-XOR SAT sources ONLY.
    # Pure UNSAT is replayed but sent to native CMS because no LRAT certificate.
    if mode=="r28_safe":
        if not MIN_R28_CNF<=m<=MAX_R28_CNF:
            meta["prep_abstain"]="r28_size_gate"
            return source_rows,imported,meta,pure_status,pure_proof
        answer=exact.solve(source)
        need(answer["source_sha256"]==r195.digest(source),"R28 source proof SHA mismatch")
        if answer["pure_exact"] and answer["status"]=="SAT":
            need(answer["proof"]=="EXACT_CNFEQUIV_GAUSS_SAT_MODEL_CHECKED",
                 "R28 lacked exact SAT checked model")
            meta["route"]="r28_pure_sat"
            pure_status="SAT";pure_proof=answer["proof"]
        else:
            meta["prep_abstain"]="r28_not_proven_pure_sat"
        return source_rows,imported,meta,pure_status,pure_proof
    # All other arms retain original source; turn OTF Gauss OFF in CMS.
    # Prefix signal is a *guard*, not a claim of a useful XOR runtime reason.
    n,original=exact.parse_dimacs(source)
    need(n==sig["vars"] and len(original)==m,"original DIMACS parser mismatch")
    if time.perf_counter()-begun>MAX_TOTAL_PREP:
        meta["prep_abstain"]="parse_budget_exceeded"
        return source_rows,imported,meta,pure_status,pure_proof
    source_rows=r195.certified_source_rows(original)[:MAX_SOURCE_ROWS]
    if not source_rows:
        meta["prep_abstain"]="no_certified_full_source_xor"
        return source_rows,imported,meta,pure_status,pure_proof
    # replay each imported parity truth table independently from full CNF.
    mre1.replay_source_xors(original,source_rows)
    meta.update(source_rows=len(source_rows),source_proof_replayed=True,
                route="certified_source_xor")
    if mode=="xor_no_otf" or m>MAX_CNF_FOR_CRR:
        if m>MAX_CNF_FOR_CRR:meta["prep_abstain"]="crr_larger_source_abstain"
        return source_rows,imported,meta,pure_status,pure_proof
    if time.perf_counter()-begun>=MAX_TOTAL_PREP:
        meta["prep_abstain"]="crr_prep_budget_before_derive"
        return source_rows,imported,meta,pure_status,pure_proof
    # Low-cost and conservative: cap every stage, then independently replay.
    saved=(mre1.MAX_SOURCE_ROWS,mre1.MAX_DERIVED,
           mre1.MAX_BINARY_POOL,mre1.MAX_CHECKS)
    try:
        mre1.MAX_SOURCE_ROWS=MAX_SOURCE_ROWS
        mre1.MAX_DERIVED=12
        mre1.MAX_BINARY_POOL=64
        mre1.MAX_CHECKS=224
        rows,proofs,evidence=mre1.derive(original,max_s=MAX_DERIVE_BUDGET)
    finally:
        (mre1.MAX_SOURCE_ROWS,mre1.MAX_DERIVED,
         mre1.MAX_BINARY_POOL,mre1.MAX_CHECKS)=saved
    need(evidence["proof_replayed"],"MRE1 independent proof replay failed")
    meta.update(derived_lemmas=len(proofs),proof_replayed=True)
    if time.perf_counter()-begun>=MAX_TOTAL_PREP:
        meta["prep_abstain"]="crr_derive_over_budget"
        return source_rows,imported,meta,pure_status,pure_proof
    # Only import certified short clauses with measurable bounded BCP effect.
    # This is a bounded PRE-SOLVE proxy; NOT a CDCL trail-reason event.
    eligible=[p for p in proofs if len(p["clause"])<=2][:10]
    if not eligible:
        meta["prep_abstain"]="no_replayed_short_lemma"
        return source_rows,imported,meta,pure_status,pure_proof
    selected,gstats=mre2.gate(original,eligible,budget_s=MAX_BCP_BUDGET)
    new_effect=gstats.get("new_implications",0)+gstats.get("new_conflicts",0)
    meta.update(root_probe_implications=gstats.get("new_implications",0),
                root_probe_conflicts=gstats.get("new_conflicts",0),
                approx_root_units=gstats.get("novel_units",0))
    if time.perf_counter()-begun>=MAX_TOTAL_PREP:
        meta["prep_abstain"]="crr_bcp_over_total_budget"
        return source_rows,imported,meta,pure_status,pure_proof
    if not selected or new_effect<2:
        meta["prep_abstain"]="no_sufficient_novel_bcp"
        return source_rows,imported,meta,pure_status,pure_proof
    imported=selected[:MAX_ADDED_LEMMAS]
    available={tuple(p["clause"]) for p in proofs}
    need(all(tuple(p["clause"]) in available for p in imported),
         "unproven CRR lemma")
    need(mre1.verify_proofs(original,rows,proofs),
         "MRE1 full proof replay failed at import boundary")
    meta["approved_lemmas"]=len(imported)
    if mode=="crr_active":
        meta["route"]="mre4_safe_crr_active"
    else:
        meta["route"]="mre4_same_prep_shadow_no_import"
    return source_rows,(imported if mode=="crr_active" else []),meta,pure_status,pure_proof

def one(case,rep,mode,binary):
    source=r195.FROZEN/case["name"]
    begun=time.perf_counter()
    need(r195.digest(source)==case["sha256"],"frozen source SHA drift")
    seed=int(sha(PROTO+case["sha256"]+str(rep))[:8],16)
    rows,imported,meta,fast_status,fast_proof=prepare(source,mode)
    prep_s=time.perf_counter()-begun
    status="TIMEOUT";stats={}
    witness_proof="CAP_TIMEOUT"
    if fast_status=="SAT":
        status="SAT";witness_proof=fast_proof
    else:
        remain=CAP-(time.perf_counter()-begun)
        if remain>=0.10:
            with tempfile.TemporaryDirectory(prefix="mre4-") as tmp:
                tmp=pathlib.Path(tmp)
                cnf=source
                if imported:
                    n,original=exact.parse_dimacs(source)
                    cnf=tmp/"augmented.cnf"
                    mre1.write_cnf(cnf,n,original,imported)
                xor=tmp/"source.tsv";empty=tmp/"empty.tsv"
                # If gate declined / timed out, no source imports at all:
                # avoid unnecessary CMS XOR conversion. Shadow applies the
                # same source rows and proof effort but no derived clauses.
                mre1.write_xors(xor,rows)
                empty.write_text("")
                native_mode="cms_native" if not rows else "source_xor_no_gauss"
                # All arms use same CMS native config with OTF Gauss disabled.
                try:
                    proc=subprocess.run([str(pathlib.Path(binary).resolve()),
                        str(cnf.resolve()),str(xor.resolve()),
                        str(empty.resolve()),native_mode,str(seed)],
                        text=True,capture_output=True,errors="replace",
                        timeout=max(.001,CAP-(time.perf_counter()-begun)),check=False)
                except subprocess.TimeoutExpired:
                    proc=None
                if proc is not None:
                    need(proc.returncode==0,"native CMS terminated: "+proc.stderr[-1400:])
                    status,model,stats=r195.parsed_native(proc.stdout)
                    if status=="SAT":
                        r195.verify_model(source,model)
                        witness_proof="ORIGINAL_CNF_SAT_MODEL_CHECKED"
                    elif status=="UNSAT":
                        witness_proof="CMS_UNSAT_NO_INDEPENDENT_LRAT"
    wall_s=time.perf_counter()-begun
    if wall_s>=CAP:
        status="TIMEOUT";witness_proof="CAP_TIMEOUT"
    if status!="TIMEOUT":
        need(status==case["expected"],"verdict mismatch with source reference")
    return dict(protocol=PROTO,source_sha256=case["sha256"],
         case=case["name"],cohort=case["cohort"],mode=mode,rep=rep,seed=seed,
         status=status,wall_s=round(wall_s,6),
         prep_s=round(prep_s,6),
         par2_s=round(CAP*2 if status=="TIMEOUT" else wall_s,6),
         proof=witness_proof,
         active_lemmas=len(imported),
         source_xor_rows=len(rows),
         cms_conflicts=stats.get("conflicts"),
         cms_decisions=stats.get("decisions"),
         cms_propagations=stats.get("propagations"),
         meta=meta,
         native_otf_gauss=False,
         real_cdcl_reason_usage="NOT_MEASURED_NO_SOURCE_HOOK",
         commit=os.environ.get("GITHUB_SHA","local"))

def shard(k,binary):
    need(0<=k<SHARDS,"shard range")
    cs=r195.cases()
    need(len(cs)==32 and len({x["sha256"] for x in cs})==32,
         "development source manifest changed")
    ROOT.mkdir(parents=True,exist_ok=True)
    trial_rows=[]
    for case in cs[k::SHARDS]:
        for rep in range(REPS):
            modes=list(MODES)
            random.Random(PROTO+case["sha256"]+str(rep)).shuffle(modes)
            for mode in modes:
                row=one(case,rep,mode,binary)
                trial_rows.append(row)
                save(ROOT/f"shard-{k}.json",trial_rows)
                print("MRE4_TRIAL",json.dumps({q:row[q] for q in (
                    "case","cohort","mode","rep","status","wall_s","par2_s",
                    "prep_s","active_lemmas","source_xor_rows",
                    "cms_conflicts","cms_decisions","cms_propagations")},
                    sort_keys=True),flush=True)
    need(len(trial_rows)==len(cs[k::SHARDS])*REPS*len(MODES),
         "incomplete shard")
    print("MRE4_SHARD_PASS",k,len(trial_rows),flush=True)

def audit():
    cs=r195.cases()
    bysha={x["sha256"]:x for x in cs}
    all_rows=[]
    pairs=collections.defaultdict(dict)
    for k in range(SHARDS):
        rr=json.loads((ROOT/f"shard-{k}.json").read_text())
        need(len(rr)==len(cs[k::SHARDS])*REPS*len(MODES),
             "incomplete frozen shard "+str(k))
        all_rows.extend(rr)
    need(len(all_rows)==32*REPS*len(MODES)==320,"missing 320 records")
    for r in all_rows:
        need(r["source_sha256"] in bysha,"unknown CNF hash")
        need(r["case"]==bysha[r["source_sha256"]]["name"],"mislabeled source")
        need(r["native_otf_gauss"] is False,"unsafe CMS OTF Gauss enabled")
        need(r["real_cdcl_reason_usage"]=="NOT_MEASURED_NO_SOURCE_HOOK",
             "false live reason usage claim")
        key=(r["source_sha256"],r["rep"])
        need(r["mode"] not in pairs[key],"duplicate mode")
        pairs[key][r["mode"]]=r
        need(abs(r["par2_s"]-(2*CAP if r["status"]=="TIMEOUT"
                             else r["wall_s"]))<1e-5,"incorrect PAR2")
        if r["status"]=="SAT":
            need(r["proof"] in ("ORIGINAL_CNF_SAT_MODEL_CHECKED",
                "EXACT_CNFEQUIV_GAUSS_SAT_MODEL_CHECKED"),"unchecked SAT")
        if r["active_lemmas"]>0:
            need(r["mode"]=="crr_active" and
                 r["meta"]["proof_replayed"] is True and
                 r["meta"]["approved_lemmas"]>=r["active_lemmas"],
                 "unproven active clause")
        if r["mode"]=="crr_shadow":
            need(r["active_lemmas"]==0,"shadow altered formula")
    need(len(pairs)==32*REPS,"missing paired original SHA/repetition")
    for p in pairs.values():
        need(set(p)==set(MODES),"missing paired arms")
        need(len({r["status"] for r in p.values()
                  if r["status"]!="TIMEOUT"})<=1,
             "SAT/UNSAT verdict conflict")
    results={}
    for cohort in ("reused_official_2026","reused_synthetic_controls",
                   "new_mixed_xor_cnf","all"):
        rows=[r for r in all_rows if r["cohort"]==cohort or cohort=="all"]
        results[cohort]={}
        for mode in MODES:
            a=[r for r in rows if r["mode"]==mode]
            results[cohort][mode]=dict(trials=len(a),
                solved=sum(r["status"]!="TIMEOUT" for r in a),
                par2_s=round(sum(r["par2_s"] for r in a),6),
                prep_s=round(sum(r["prep_s"] for r in a),6),
                approved_lemmas=sum(r["meta"]["approved_lemmas"] for r in a),
                active_lemmas=sum(r["active_lemmas"] for r in a),
                routed_r28_sat=sum(r["meta"]["route"]=="r28_pure_sat" for r in a),
                early_abstains=sum(bool(r["meta"]["prep_abstain"]) for r in a))
    report=dict(protocol=PROTO,status="MRE4_P1_AUDIT_PASS",
        trials=len(all_rows),source_count=32,
        independent_SAT_original_model_verified=True,
        independent_UNSAT_LRAT=False,all_OTF_gauss_disabled=True,
        borrowed_R28_pure_sat_proof_replayed=True,
        native_cms_CDCL_counters=True,
        live_per_reason_hook=False,
        development_reused_NOT_blind=True,
        no_unsound_derived_xor_import=True,
        constraints="No proof, no effect, no time budget => abstain",
        results=results,
        promotion_requirements=[
           "paired active beats same-prep shadow and XOR-only on unseen official",
           "new CDCL reason event telemetry before claiming live reasoning",
           "all SAT witnesses independently checked and UNSAT proof audit",
           "full preparation included and no meaningful regression"])
    save(ROOT/"report.json",report)
    print("MRE4_FINAL",json.dumps(report,sort_keys=True),flush=True)

def selftest():
    import tempfile
    need(len(MODES)==5 and 32*REPS*len(MODES)==320,"protocol")
    with tempfile.TemporaryDirectory() as tmp:
        p=pathlib.Path(tmp)/"sample.cnf"
        clauses=r195.xor_cnf((1,2,3),1)+r195.xor_cnf((2,3,4),0)
        p.write_text("p cnf 4 %d\n"%len(clauses)+
            "".join(" ".join(map(str,c))+" 0\n" for c in clauses))
        n,m=header(p)
        need(n==4 and m==8,"header selftest")
        need(prefix_signal(p)["reason"]=="cheap_size_abstain",
             "cheap guard missed tiny CNF")
    print("MRE4_SELFTEST_PASS",PROTO,flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=["selftest","shard","audit"])
    p.add_argument("--shard",type=int,default=0)
    p.add_argument("--binary",default="mre4_p1/native")
    a=p.parse_args()
    if a.action=="selftest":selftest()
    elif a.action=="shard":shard(a.shard,a.binary)
    else:audit()
