#!/usr/bin/env python3
"""DRNAS MRE X: source-only MRE11 certified quotient + C3 canonical duplicate
removal and C4 clause-order causal control. DEVELOPMENT BENCHMARK ONLY.

Freeze EXACT existing 12 SAT2021-25 SHA originals from MRE11-EASY12 / C3,
and 1 additional C1/C4 SAT2021-23 known duplicate-heavy original.
All these sources have been observed before; NO blind-holdout claims.
7 native C++ arms, 4 independent SHA-paired seeds, 12s end-to-end cap:
x_native, x_mre11, x_dedup, x_tail, x_joint, x_composed, x_adaptive.
SAT witness verified on complete original CNF, UNSAT prior reference/CaDiCaL
agreement only (no independent LRAT). Never auto-promote.
C5-inspired bounded early CDCL diagnostic is separate from PAR2.
"""
from __future__ import annotations
import argparse, collections, hashlib, itertools, json, os, pathlib
import random, shutil, subprocess, tempfile, time
import r195_native_cms_benchmark as cms
import r164_pure_exact_gf2 as exact

PROTO="DRNAS-MRE-X-C3-MRE11-13SHA-7ARMS-4SEED-12S-PAR2-v1"
ROOT=pathlib.Path("mre_x")
C3_SOURCE=pathlib.Path("mre11_easy")
C1_SOURCE=pathlib.Path("mre11b_blind")
C1_EXTRA_GBD="220bb8aa093e502c47afcdac3140d67c"
C1_EXTRA_SHA="69aa8b6bb96a5952fedf1007994b4255d06f7e32023390bc4c342b1b30a0356a"
MRE11_REFERENCE=pathlib.Path("mre11_ref/mre11/bin/standalone")
MODES=("x_native","x_mre11","x_dedup","x_tail","x_joint","x_composed","x_adaptive")
REPS=4
SHARDS=4
CAP=12.0
NUM_ORIGINALS=13
SOURCE_REPS=NUM_ORIGINALS*REPS
TRIALS=NUM_ORIGINALS*REPS*len(MODES)
C4_C3_CAUSAL_GBDS=(
    "220bb8aa093e502c47afcdac3140d67c",
    "fdfcd52a21824b7181d66672f283ba04",
    "695d8f6a2ee6e89e5a4f5d94abc3aca6",
    "037d21e060a2e3eab8b080aa84ceee75",
)
CERTIFICATES={
    "x_native":"original_CNF_unchanged",
    "x_mre11":"two_original_CNF_binary_clauses_transitive_closure",
    "x_dedup":"original_CNF_clause_identity",
    "x_tail":"original_CNF_exact_clause_permutation",
    "x_joint":"two_original_CNF_binary_clauses_transitive_closure",
    "x_composed":"original_CNF_certified_equivalence_plus_exact_duplicate_identity",
    "x_adaptive":"original_CNF_certified_equivalence_plus_exact_duplicate_identity",
}

def need(x,msg):
    if not x:raise RuntimeError("MRE_X_FAIL_CLOSED "+str(msg))
def sha(x):return hashlib.sha256(x).hexdigest()
def dump(path,value):
    p=pathlib.Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(value,sort_keys=True,indent=2)+"\n")
def seed(c,rep):
    need(0<=rep<REPS,"invalid frozen seed repetition")
    return int(sha((PROTO+"|SEED|"+c["sha256"]+"|"+str(rep)).encode())[:8],16)

def parse_gate(out,mode):
    q=[l.split(" ",1)[1] for l in out.splitlines() if l.startswith("MRE10_GATE ")]
    need(len(q)==1,"missing or repeated native C++ gate")
    g=json.loads(q[0])
    need(g.get("mode")==mode and g.get("certificate")==CERTIFICATES[mode],
         "gate proof tag, native selected arm, or certificate differs")
    need(type(g.get("applied")) is bool,"bad applied flag")
    return g

def original_sources():
    c3=json.loads((C3_SOURCE/"manifest.json").read_text())
    need(c3["protocol"]=="DRNAS-MRE11-EASY12-2021-2025-DEVREPLAY-5ARMS-4SEEDS-12S-v1",
         "old C3/MRE11 easy12 protocol changed")
    arr=c3["cases"]
    need(len(arr)==12,"not exact 12 original C3 source files")
    chosen=[]
    for c in arr:
        p=C3_SOURCE/c["filename"]
        need(p.is_file() and sha(p.read_bytes())==c["sha256"] and
             p.stat().st_size==c["bytes"],"C3 source SHA drift")
        need(c["reference_screen_status"] in ("SAT","UNSAT"),"unverified reference")
        chosen.append(dict(gbd=c["gbd"],sha256=c["sha256"],
            original_path=str(p),year=c["year"],
            reference_status=c["reference_screen_status"],
            family="C3_MRE11_EASY12_DEVELOPMENT",
            reference_label="MRE11_EASY12_CMS_original_CaDiCaL_reference"))
    c1=json.loads((C1_SOURCE/"manifest.json").read_text())
    need(c1["protocol"]=="DRNAS-MRE11B-MINISAT1M-SOURCELOCK-2021-23-8SHA-20261108-v1",
         "C1 source SHA manifest unexpectedly changed")
    matches=[c for c in c1["source_cases"] if c["gbd"]==C1_EXTRA_GBD]
    need(len(matches)==1,"missing exact C1 original C4 validation source")
    extra=matches[0];p=C1_SOURCE/extra["filename"]
    need(extra["sha256"]==C1_EXTRA_SHA and sha(p.read_bytes())==C1_EXTRA_SHA,
         "C4 source SHA mismatch")
    # C4 benchmark on exactly this original confirmed original SAT witnesses.
    chosen.append(dict(gbd=extra["gbd"],sha256=extra["sha256"],
        original_path=str(p),year=extra["year"],reference_status="SAT",
        family="C4_C1_KNOWN_DUPLICATE_DEVELOPMENT",
        reference_label="C4_verified_original_SAT_witness"))
    need(len(chosen)==NUM_ORIGINALS and
         len({x["gbd"] for x in chosen})==NUM_ORIGINALS and
         len({x["sha256"] for x in chosen})==NUM_ORIGINALS,
         "duplicate or absent original SHA")
    return chosen

def freeze():
    ROOT.mkdir(exist_ok=True)
    cases=[]
    for c in original_sources():
        p=pathlib.Path(c["original_path"])
        dest=ROOT/(c["gbd"]+".cnf")
        shutil.copyfile(p,dest)
        cases.append(dict(gbd=c["gbd"],sha256=c["sha256"],
            filename=dest.name,bytes=dest.stat().st_size,
            year=c["year"],family=c["family"],
            reference_status=c["reference_status"],
            reference_label=c["reference_label"]))
    manifest={
        "protocol":PROTO,"cases":cases,"source_count":len(cases),
        "seed_count":REPS,"modes":list(MODES),"expected_trials":TRIALS,
        "cap_s":CAP,"source_selection":"12 C3/MRE11 Easy12 + 1 C4 original SHA, locked before MRE X trials",
        "not_new_or_unseen_sources":True,"development_not_holdout":True,
        "combination_strategy":"certified MRE11 THEN exact C3 source-clause identity; adaptive source-only duplicate filter >=64 and >=2 percent",
        "no_sat_probe_in_gate":True,"no_auto_promotion":True,
        "independent_unsat_lrat":False,
        "four_known_C4_mechanism_ids":list(C4_C3_CAUSAL_GBDS)}
    dump(ROOT/"manifest.json",manifest)
    (ROOT/"source.sha256").write_text("".join(
        c["sha256"]+"  "+c["filename"]+"\n" for c in cases))
    print("MRE_X_FROZEN",json.dumps(dict(proto=PROTO,cases=len(cases),
        statuses=dict(collections.Counter(c["reference_status"] for c in cases)),
        trials=TRIALS,cap_s=CAP,not_blind=True),sort_keys=True),flush=True)

def cases():
    p=ROOT/"manifest.json"
    need(p.is_file(),"missing source freeze")
    m=json.loads(p.read_text())
    need(m["protocol"]==PROTO and m["expected_trials"]==TRIALS and
         m["cap_s"]==CAP and m["modes"]==list(MODES),"original MRE X protocol drift")
    cs=m["cases"]
    need(len(cs)==NUM_ORIGINALS and
         len({x["sha256"] for x in cs})==NUM_ORIGINALS,"SHA13 cardinality changed")
    for c in cs:
        p=ROOT/c["filename"]
        need(p.is_file() and sha(p.read_bytes())==c["sha256"] and
             p.stat().st_size==c["bytes"],"original source SHA mutated")
        need(c["reference_status"] in ("SAT","UNSAT"),"unknown reference truth")
    return cs

def emit(binpath,src,mode,dst):
    p=subprocess.run([str(pathlib.Path(binpath).resolve()),"--emit",
        str(pathlib.Path(src).resolve()),mode,str(pathlib.Path(dst).resolve())],
        capture_output=True,text=True,check=False,timeout=30)
    need(p.returncode==0,mode+" certificate emission failed: "+p.stderr[-700:])
    return parse_gate(p.stdout,mode)

def read_simple(path):
    text=pathlib.Path(path).read_text().splitlines()
    n=None;count=None;clauses=[]
    for line in text:
        q=line.strip()
        if not q or q.startswith("c"):continue
        if q.startswith("p "):
            t=q.split();need(t[1]=="cnf","not CNF")
            n=int(t[2]);count=int(t[3]);continue
        literals=tuple(map(int,q.split()))
        need(literals[-1]==0,"bad DIMACS end")
        clauses.append(literals[:-1])
    need(n is not None and len(clauses)==count,"bad DIMACS formula")
    return n,clauses

def brute(path):
    n,cs=read_simple(path)
    need(n<=8,"selftest brute force too many variables")
    for bits in itertools.product((False,True),repeat=n):
        if all(any(bits[abs(l)-1]==(l>0) for l in clause) for clause in cs):
            return True
    return False

def selftest(standalone,native):
    need(len(MODES)==7 and REPS==4 and SHARDS==4 and CAP==12.0,
         "MRE X protocol drift")
    with tempfile.TemporaryDirectory(prefix="mre-x-selftest-") as td:
        td=pathlib.Path(td)
        # Three independently checkable formulas: positive equivalence,
        # exact clause duplication and UNSAT. No benchmark formula used.
        tests=[
            (6,[(1,-2),(-1,2),(1,3),(1,3),(2,4),(2,4),(-3,5),(6,)]),
            (3,[(1,),(-1,),(-2,3),(-2,3)]),
            (4,[(1,2),(-1,3),(2,3),(1,2),(4,-4)])]
        for j,(n,clauses) in enumerate(tests):
            src=td/("input-%d.cnf"%j)
            src.write_text("p cnf %d %d\n"%(n,len(clauses))+
                "".join(" ".join(map(str,c))+" 0\n" for c in clauses))
            truth=brute(src)
            for mode in MODES:
                out=td/("emit-%d-%s.cnf"%(j,mode))
                g=emit(standalone,src,mode,out)
                need(brute(out)==truth,"MRE X changes SAT/UNSAT ground truth: "+mode)
                if mode=="x_native":need(not g["applied"],"native changed source")
                if mode=="x_tail":need(g["duplicate_clauses_removed"]==0,
                                        "tail removed original clause")
                p=subprocess.run([str(pathlib.Path(native).resolve()),
                    str(src.resolve()),mode,"101"],
                    capture_output=True,text=True,timeout=12,check=False,
                    errors="replace")
                need(p.returncode==0,mode+" selftest C++ solver crashed: "+p.stderr)
                v,model,stats=cms.parsed_native(p.stdout)
                need(v==("SAT" if truth else "UNSAT"),
                     mode+" disagrees with independent exhaustive truth")
                if v=="SAT":cms.verify_model(src,model)
    print("MRE_X_CERTIFIED_COMPOSE_BRUTE_FORCE_SELFTEST_PASS",
          json.dumps(dict(arms=len(MODES),independent_formulas=len(tests),
          sat_witness_replayed=True,original_model_lifting=True),sort_keys=True),flush=True)

def parity(standalone,reference):
    cc=cases()
    need(pathlib.Path(reference).exists(),"missing immutable original MRE11 binary")
    with tempfile.TemporaryDirectory(prefix="mre-x-original-policy-") as td:
        a=pathlib.Path(td)/"x.cnf";b=pathlib.Path(td)/"original-mre11.cnf"
        for c in cc:
            src=ROOT/c["filename"]
            q=emit(standalone,src,"x_mre11",a)
            p=subprocess.run([str(pathlib.Path(reference).resolve()),"--emit",
                str(src.resolve()),"cpp_mre11_sel",str(b.resolve())],
                capture_output=True,text=True,timeout=25,check=False)
            need(p.returncode==0,"source-locked original MRE11 standalone failed")
            ref_gate=[x.split(" ",1)[1] for x in p.stdout.splitlines()
                    if x.startswith("MRE10_GATE ")]
            need(len(ref_gate)==1,"missing MRE11 source policy response")
            orig=json.loads(ref_gate[0])
            need(bool(q["applied"])==bool(orig["applied"]),
                 "MRE X MRE11 gate diverged from immutable original")
            need(exact.parse_dimacs(a)==exact.parse_dimacs(b),
                 "MRE X C++ MRE11 CNF not bitwise logically equal to original MRE11")
            print("MRE_X_MRE11_POLICY_PARITY",json.dumps(
                dict(gbd=c["gbd"],source_sha256=c["sha256"],
                     applied=q["applied"],reason=q["reason"]),
                sort_keys=True),flush=True)
    print("MRE_X_ORIGINAL_MRE11_CERTIFIED_POLICY_PARITY_PASS",len(cc),flush=True)

def diagnostic(standalone):
    cc=cases();output=[]
    with tempfile.TemporaryDirectory(prefix="mre-x-struct-") as td:
        p=pathlib.Path(td)/"out.cnf"
        for c in cc:
            source=ROOT/c["filename"]
            row=dict(gbd=c["gbd"],SHA=c["sha256"],family=c["family"],arms={})
            for mode in MODES:row["arms"][mode]=emit(standalone,source,mode,p)
            output.append(row)
            print("MRE_X_SOURCE_DIAGNOSTIC",json.dumps(row,sort_keys=True),flush=True)
    dump(ROOT/"structural.json",output)
    print("MRE_X_CERTIFICATE_INVENTORY_PASS",len(output),flush=True)

def trial(c,rep,mode,binary):
    need(mode in MODES and rep in range(REPS),"unsupported MRE X trial")
    src=ROOT/c["filename"];need(sha(src.read_bytes())==c["sha256"],"source SHA changed")
    start=time.perf_counter()
    p=None
    try:
        p=subprocess.run([str(pathlib.Path(binary).resolve()),
            str(src.resolve()),mode,str(seed(c,rep))],
            capture_output=True,text=True,errors="replace",check=False,timeout=CAP)
    except subprocess.TimeoutExpired:pass
    elapsed=time.perf_counter()-start
    status="TIMEOUT";gate=None;native=None;witness=False
    if p is not None:
        need(p.returncode==0,"MRE X native failed "+mode+": "+p.stderr[-1000:])
        gate=parse_gate(p.stdout,mode)
        status,model,native=cms.parsed_native(p.stdout)
        need(status in ("SAT","UNSAT","UNKNOWN","BUDGET"),
             "bad solver terminal "+status)
        if status=="SAT":
            cms.verify_model(src,model);witness=True
        if status in ("SAT","UNSAT"):
            need(status==c["reference_status"],
                 "MRE X changed original SAT/UNSAT truth status")
    if status in ("UNKNOWN","BUDGET") or elapsed>CAP:
        status="TIMEOUT";witness=False
    return dict(protocol=PROTO,source_sha256=c["sha256"],gbd=c["gbd"],
        family=c["family"],year=c["year"],reference_status=c["reference_status"],
        seed=seed(c,rep),rep=rep,mode=mode,status=status,
        elapsed_s=round(elapsed,6),PAR2_s=round(
          elapsed if status in ("SAT","UNSAT") else 2*CAP,6),
        SAT_original_witness_verified=witness,
        UNSAT_prior_reference_agreement_no_independent_LRAT=(status=="UNSAT"),
        gate=gate,native_stats=native)

def shard(idx,binary):
    need(0<=idx<SHARDS,"invalid shard number")
    cc=cases();selected=[c for j,c in enumerate(cc) if j%SHARDS==idx]
    need(3<=len(selected)<=4,"unbalanced source-shard division")
    out=[]
    for c in selected:
        for rep in range(REPS):
            order=list(MODES)
            random.Random(sha((PROTO+"|ORDER|"+c["sha256"]+"|"+str(rep)).encode())).shuffle(order)
            for mode in order:
                row=trial(c,rep,mode,binary)
                out.append(row)
                dump(ROOT/("shard-%d.json"%idx),out)
                print("MRE_X_TRIAL",json.dumps(row,sort_keys=True),flush=True)
    need(len(out)==len(selected)*REPS*len(MODES),"short MRE X shard")
    print("MRE_X_SHARD_PASS",idx,len(out),flush=True)

def early(binary):
    # Three frozen arms: original CDCL, C3 dedup CDCL, MRE X adaptive CDCL.
    # Two fresh independent bounded runs per case (100/1000 conflicts).
    # These are NEVER mixed into complete SAT/UNSAT PAR2.
    cc={c["gbd"]:c for c in cases()};out=[]
    for gbd in C4_C3_CAUSAL_GBDS:
        need(gbd in cc,"missing original C3/C4 source")
        c=cc[gbd];src=ROOT/c["filename"]
        need(c["reference_status"]=="SAT","early causal cases were not SAT")
        for budget in (100,1000):
            for mode in ("x_native","x_dedup","x_adaptive"):
                env=os.environ.copy();env["DRNAS_MAX_CONFLICTS"]=str(budget)
                begin=time.perf_counter()
                p=subprocess.run([str(pathlib.Path(binary).resolve()),
                    str(src.resolve()),mode,str(seed(c,0))],
                    env=env,capture_output=True,text=True,check=False,
                    errors="replace",timeout=15)
                wall=time.perf_counter()-begin
                need(p.returncode==0,"bounded C5 diagnostic crashed: "+p.stderr[-600:])
                gate=parse_gate(p.stdout,mode)
                # R195 parser intentionally accepts only complete SAT/UNSAT;
                # C5 diagnostic needs its own explicit BUDGET-aware telemetry.
                import re
                mm=re.search(r"^R195_RESULT status=(SAT|UNSAT|BUDGET|UNKNOWN) conflicts=(\\d+) decisions=(\\d+) propagations=(\\d+) source_rows=(\\d+) derived_rows=(\\d+)$",p.stdout,re.M)
                need(mm is not None,"bounded native telemetry marker missing")
                verdict=mm.group(1)
                stats=dict(conflicts=int(mm.group(2)),
                    decisions=int(mm.group(3)),
                    propagations=int(mm.group(4)),
                    source_rows=int(mm.group(5)),
                    derived_rows=int(mm.group(6)))
                need(verdict in ("SAT","BUDGET"),
                     "not bounded causal or SAT verdict")
                if verdict=="SAT":
                    v,model,complete_stats=cms.parsed_native(p.stdout)
                    need(v=="SAT","bounded SAT parse disagreement")
                    cms.verify_model(src,model)
                row=dict(gbd=gbd,sha256=c["sha256"],mode=mode,
                  seed=seed(c,0),conflict_budget=budget,verdict=verdict,
                  bounded_not_end_to_end=True,
                  conflicts=stats.get("conflicts") if stats else None,
                  decisions=stats.get("decisions") if stats else None,
                  propagations=stats.get("propagations") if stats else None,
                  wall_s=round(wall,6),gate=gate)
                out.append(row)
                print("MRE_X_BOUNDED_DIAGNOSTIC",json.dumps(row,sort_keys=True),flush=True)
    dump(ROOT/"early_cdcl_diagnostic.json",out)
    need(len(out)==24,"not exactly 24 C5 diagnostic runs")
    print("MRE_X_BOUNDED_C5_TELEMETRY_PASS",len(out),flush=True)

def audit():
    cc=cases();allrows=[]
    for i in range(SHARDS):
        p=ROOT/("shard-%d.json"%i)
        need(p.exists(),"missing source-paired shard")
        allrows+=json.loads(p.read_text())
    need(len(allrows)==TRIALS,"incomplete MRE X real SAT PAR2")
    source={x["sha256"]:x for x in cc};obs={}
    for row in allrows:
        c=source.get(row["source_sha256"])
        need(c is not None and row["protocol"]==PROTO and
             row["gbd"]==c["gbd"] and row["family"]==c["family"],
             "wrong original source in MRE X")
        need(row["mode"] in MODES and row["rep"] in range(REPS) and
             row["seed"]==seed(c,row["rep"]),"unpaired case/seed/mode")
        need(row["reference_status"]==c["reference_status"] and
             row["status"] in ("SAT","UNSAT","TIMEOUT"),"wrong original answer")
        if row["status"]=="SAT":
            need(row["SAT_original_witness_verified"] and
                 c["reference_status"]=="SAT","original SAT witness not checked")
        if row["status"]=="UNSAT":
            need(row["UNSAT_prior_reference_agreement_no_independent_LRAT"] and
                 c["reference_status"]=="UNSAT","UNSAT reference disagreement")
        if row["status"]=="TIMEOUT":
            need(row["PAR2_s"]==2*CAP,"wrong timeout PAR2 penalty")
        key=(c["sha256"],row["rep"],row["mode"])
        need(key not in obs,"duplicate original-source trial")
        obs[key]=row
    need(len(obs)==TRIALS,"missing source pairs")
    for c in cc:
        for rep in range(REPS):
            need(all((c["sha256"],rep,mode) in obs for mode in MODES),
                 "not paired on same original SHA and seed")
    scores={}
    for mode in MODES:
        subset=[row for row in allrows if row["mode"]==mode]
        scores[mode]=dict(n=len(subset),
            solved=sum(x["status"] in ("SAT","UNSAT") for x in subset),
            SAT=sum(x["status"]=="SAT" for x in subset),
            UNSAT_prior_reference_no_independent_LRAT=sum(x["status"]=="UNSAT" for x in subset),
            timeouts=sum(x["status"]=="TIMEOUT" for x in subset),
            PAR2_s=round(sum(x["PAR2_s"] for x in subset),6),
            gate_applied_visible=sum(bool((x["gate"] or {}).get("applied")) for x in subset))
    control=scores["x_native"]["PAR2_s"]
    for x in scores.values():x["PAR2_speedup_vs_native_x"]=round(control/x["PAR2_s"],6)
    per_source=[]
    for c in cc:
        sub=[x for x in allrows if x["source_sha256"]==c["sha256"]]
        per_source.append(dict(gbd=c["gbd"],sha=c["sha256"],family=c["family"],
            reference=c["reference_status"],
            PAR2_s={m:round(sum(x["PAR2_s"] for x in sub if x["mode"]==m),6) for m in MODES},
            solved={m:sum(x["status"] in ("SAT","UNSAT") for x in sub if x["mode"]==m) for m in MODES}))
    report=dict(protocol=PROTO,source_count=len(cc),total_trials=TRIALS,
        cap_s=CAP,seed_repeats=REPS,modes=list(MODES),
        development_source_replay_not_blind=True,
        C3_evidence_frozen=True,
        MRE11_certified_original_policy_parity_checked=True,
        end_to_end_original_sat_unsat=True,
        SAT_original_model_checked=True,
        UNSAT_reference_agreement_no_independent_LRAT=True,
        C5_bounded_diagnostics_not_PAR2=True,
        no_auto_promotion=True,score=scores,per_source=per_source)
    dump(ROOT/"report.json",report)
    print("MRE_X_FINAL",json.dumps({k:v for k,v in report.items()
        if k!="per_source"},sort_keys=True),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("freeze","verify","selftest","parity",
       "diagnostic","early","shard","audit"))
    p.add_argument("--shard",type=int,default=0)
    p.add_argument("--native",default="mre_x/bin/native")
    p.add_argument("--emit",default="mre_x/bin/emit")
    p.add_argument("--reference",default=str(MRE11_REFERENCE))
    args=p.parse_args()
    if args.action=="freeze":freeze()
    elif args.action=="verify":
        print("MRE_X_ORIGINAL_SOURCE_SHA_VERIFY_PASS",len(cases()),flush=True)
    elif args.action=="selftest":selftest(args.emit,args.native)
    elif args.action=="parity":parity(args.emit,args.reference)
    elif args.action=="diagnostic":diagnostic(args.emit)
    elif args.action=="early":early(args.native)
    elif args.action=="shard":shard(args.shard,args.native)
    else:audit()
