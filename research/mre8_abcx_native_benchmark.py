#!/usr/bin/env python3
"""MRE8 A/B/C/D/E/X5/X50 native-C++ causal ablation vs exact native CMS.

16 already-selected SAT2021-2025 sources are a developmental cohort, not new
holdout. No prior PAR2 is used for exclusions. Eight arms, four predeclared
paired seed paths, 8-second total wall including C++ preprocessing. Independent
SAT witness validated on ORIGINAL source after quotient-model lifting.
UNSAT agreement is with a previously screened CaDiCaL, not independent LRAT.
"""
from __future__ import annotations
import argparse,collections,hashlib,json,os,pathlib,random,subprocess,tempfile,time
import mre7_extended_easy_freeze as freeze
import r195_native_cms_benchmark as r195
import r164_pure_exact_gf2 as exact

ROOT=pathlib.Path("mre8")
SOURCE=pathlib.Path("mre7_easy")
PROTO="DRNAS-MRE8-ABCD-EX5X50-NATIVE-16SHA-4SEED-8S-v1"
MODES=("N","A","B","C","D","E","X5","X50")
REPS=4
SHARDS=8
CAP=8.0
EXPECTED=16

def need(ok,why):
    if not ok:raise RuntimeError("MRE8_AUDIT_FAIL_CLOSED "+str(why))
def sha(data):return hashlib.sha256(data).hexdigest()
def seed_for(case,rep):
    return int(hashlib.sha256(("MRE7-FROZEN-SEED|"+case["sha256"]+"|"+str(rep)).encode()).hexdigest()[:8],16)
def cases():
    freeze.verify()
    manifest=json.loads((SOURCE/"manifest.json").read_text())
    cc=manifest["selected_cases"]
    need(len(cc)==EXPECTED and manifest["parent_six_SHA_untouched"],
         "source set or original six SHA registry drift")
    need(len({c["sha256"] for c in cc})==EXPECTED,"duplicate original SHA")
    for c in cc:need(sha((SOURCE/c["filename"]).read_bytes())==c["sha256"],
                     "exact original source SHA changed")
    return cc,manifest

def trial(case,rep,mode,binary,transform):
    need(rep in range(REPS) and mode in MODES,"unfrozen seed or mode")
    path=SOURCE/case["filename"]
    need(sha(path.read_bytes())==case["sha256"],"original SHA mismatch")
    start=time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="mre8-") as tmp:
        folder=pathlib.Path(tmp)
        used=path
        stats=dict(mode=mode,gate_accepted=False,active_quotient=False,
                   use_original=(mode=="N"),candidate_pairs=0,merged_vars=0,
                   removed_tautologies=0,removed_duplicates=0)
        mapping={}
        transform_s=0.0
        if mode!="N":
            output=folder/"rewrite.cnf";report=folder/"transform.json";mapfile=folder/"equivalence.map"
            p=subprocess.run([str(pathlib.Path(transform).resolve()),mode,
                   str(path.resolve()),str(output.resolve()),str(report.resolve()),str(mapfile.resolve())],
                   capture_output=True,text=True,timeout=CAP,check=False)
            need(p.returncode==0,"native C++ preprocessor failed: "+p.stderr[-500:])
            need(report.is_file(),"missing transform telemetry")
            stats=json.loads(report.read_text())
            need(stats["mode"]==mode and
                 stats["certificate"]=="two original opposite binary implications",
                 "different transformation or missing certificate")
            if stats["active_quotient"]:
                for line in mapfile.read_text().splitlines():
                    x,y=map(int,line.split())
                    need(x>y>=1 and x not in mapping,"malformed model-lift map")
                    mapping[x]=y
                need(len(mapping)==stats["merged_vars"],"mapping count mismatch")
            if not stats["use_original"]:
                need(output.is_file(),"missing rewritten DIMACS source")
                used=output
            transform_s=time.perf_counter()-start
        left=CAP-(time.perf_counter()-start)
        verdict="TIMEOUT";native=None;verified=False;process_s=0.0;lifting_s=0.0
        if left>0.02:
            empty=folder/"empty.tsv";empty.write_text("")
            cmd=[str(pathlib.Path(binary).resolve()),str(used.resolve()),
                 str(empty.resolve()),str(empty.resolve()),"cms_native",str(seed_for(case,rep))]
            native_start=time.perf_counter()
            try:
                result=subprocess.run(cmd,capture_output=True,text=True,errors="replace",
                    timeout=left,check=False,env=os.environ.copy())
            except subprocess.TimeoutExpired:result=None
            process_s=time.perf_counter()-native_start
            if result is not None:
                need(result.returncode==0,"CMS bridge runtime failure: "+result.stderr[-400:])
                verdict,model,native=r195.parsed_native(result.stdout)
                if verdict=="SAT":
                    if mapping:
                        for var,root in mapping.items():
                            need(root in model,"SAT lifting representative unavailable")
                            model[var]=model[root]
                    audit_start=time.perf_counter()
                    r195.verify_model(path,model)
                    lifting_s=time.perf_counter()-audit_start
                    verified=True
                need(verdict not in ("SAT","UNSAT") or verdict==case["reference_screen_status"],
                     "unexpected original SAT vs UNSAT mismatch")
        wall=time.perf_counter()-start
        if verdict in ("SAT","UNSAT") and wall>CAP:
            verdict="TIMEOUT";verified=False
        need(verdict!="SAT" or verified,"SAT without original model certificate")
        return dict(protocol=PROTO,gbd=case["gbd"],year=case["year"],
           sha256=case["sha256"],rep=rep,mode=mode,seed=seed_for(case,rep),
           reference_status=case["reference_screen_status"],
           status=verdict,original_sat_verified=verified,
           UNSAT_crosschecked_CaDiCaL_without_independent_LRAT=verdict=="UNSAT",
           wall_s=round(wall,6),
           native_cpp_preprocessing_s=round(transform_s,6),
           CMS_subprocess_s=round(process_s,6),
           source_witness_validation_s=round(lifting_s,6),
           par2_s=round(wall if verdict in ("SAT","UNSAT") else 2*CAP,6),
           native_stats=native,transform=stats,
           frozen_case=True,no_promotion=True)

def shard(index,binary,transform):
    need(0<=index<SHARDS,"bad shard number")
    cc,_=cases()
    subset=[c for k,c in enumerate(cc) if k%SHARDS==index]
    need(len(subset)==2,"unexpected shard source count")
    ROOT.mkdir(exist_ok=True)
    rows=[]
    for c in subset:
        for rep in range(REPS):
            order=list(MODES)
            random.Random(PROTO+"|"+c["sha256"]+"|"+str(rep)).shuffle(order)
            for mode in order:
                row=trial(c,rep,mode,binary,transform)
                rows.append(row)
                (ROOT/("shard-%d.json"%index)).write_text(json.dumps(rows,sort_keys=True)+"\n")
                print("MRE8_TRIAL",json.dumps(row,sort_keys=True),flush=True)
    need(len(rows)==2*REPS*len(MODES),"incomplete benchmark shard")
    print("MRE8_SHARD_PASS",index,len(rows),flush=True)

def audit():
    cc,manifest=cases()
    rows=[]
    for i in range(SHARDS):
        fn=ROOT/("shard-%d.json"%i)
        need(fn.is_file(),"missing shard "+str(i))
        rows.extend(json.loads(fn.read_text()))
    need(len(rows)==EXPECTED*REPS*len(MODES),"incomplete factorial benchmark")
    originals={c["sha256"]:c for c in cc}
    paired=collections.defaultdict(dict)
    for r in rows:
        c=originals.get(r["sha256"])
        need(bool(c) and c["gbd"]==r["gbd"],"original not in locked 16")
        need(r["protocol"]==PROTO and r["rep"] in range(REPS),"protocol drift")
        need(r["seed"]==seed_for(c,r["rep"]),"non-paired seed")
        need(r["status"] in ("SAT","UNSAT","TIMEOUT"),"unexpected solver terminal")
        if r["status"]=="SAT":need(r["original_sat_verified"],"unverified SAT")
        if r["status"]=="UNSAT":
            need(c["reference_screen_status"]=="UNSAT" and
                 r["UNSAT_crosschecked_CaDiCaL_without_independent_LRAT"],
                 "UNSAT not cross-solver checked")
        key=(r["sha256"],r["rep"])
        need(r["mode"] not in paired[key],"duplicate exact arm")
        paired[key][r["mode"]]=r
    need(len(paired)==EXPECTED*REPS,"missing paired source seed")
    for p in paired.values():need(set(p)==set(MODES),"missing arm for paired seed")
    score={}
    for mode in MODES:
        subset=[r for r in rows if r["mode"]==mode]
        score[mode]=dict(trials=len(subset),
            SAT=sum(r["status"]=="SAT" for r in subset),
            UNSAT_crosschecked_without_LRAT=sum(r["status"]=="UNSAT" for r in subset),
            solved=sum(r["status"] in ("SAT","UNSAT") for r in subset),
            timeout=sum(r["status"]=="TIMEOUT" for r in subset),
            par2_s=round(sum(r["par2_s"] for r in subset),6),
            wall_s=round(sum(r["wall_s"] for r in subset),6),
            native_cpp_preprocessing_s=round(sum(r["native_cpp_preprocessing_s"] for r in subset),6),
            active_reductions=sum(bool(r["transform"]["active_quotient"]) for r in subset),
            gate_accepts=sum(bool(r["transform"].get("gate_accepted")) for r in subset))
    base=score["N"]["par2_s"]
    for mode in MODES:
        score[mode]["speedup_vs_N_PAR2_x"]=round(base/score[mode]["par2_s"],6)
    pairs=[]
    for key,v in paired.items():
        head=v["N"]
        pairs.append(dict(sha256=key[0],year=head["year"],gbd=head["gbd"],rep=key[1],
            original_status=head["reference_status"],seed=head["seed"],
            arms={mode:dict(status=v[mode]["status"],wall_s=v[mode]["wall_s"],
                            par2_s=v[mode]["par2_s"],cpp_pre_s=v[mode]["native_cpp_preprocessing_s"],
                            stats=v[mode]["native_stats"],
                            transform=v[mode]["transform"]) for mode in MODES}))
    report=dict(protocol=PROTO,original_cases=EXPECTED,seed_reps=REPS,
       seed_formula="SHA256('MRE7-FROZEN-SEED|original_SHA|rep') first 32 bits",
       tested_arms=list(MODES),factorial_trials=len(rows),cap_s=CAP,
       collection="MRE7e previously frozen SAT2021-25 16 original SHAs",
       source_selection_on_CMS_reference=True,
       uses_development_cases_known_from_MRE7e=True,
       not_new_unseen_holdout=True,
       not_independent_UNSAT_LRAT=True,
       SAT_witness_checked_on_original=True,
       all_variant_time_includes_Cpp_preprocessing=True,
       transformations_are_orig_certified_positive_equality_only=True,
       no_auto_promotion=True,
       scores=score,pairs=pairs)
    ROOT.mkdir(exist_ok=True)
    (ROOT/"report.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print("MRE8_FINAL",json.dumps({k:v for k,v in report.items() if k!="pairs"},sort_keys=True),flush=True)

def selftest(transform):
    # Independent truth-table SAT equivalence of all seven C++ arms.
    ROOT.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mre8-selftest-") as t:
        p=pathlib.Path(t);src=p/"in.cnf"
        clauses=[[-1,2],[1,-2],[-2,3],[2,-3],[-3,4],[3,-4],
                 [1,2,3],[-4],[-4],[2,-2],[-2,2],[4,1,4]]
        with src.open("w") as f:
            f.write("p cnf 4 "+str(len(clauses))+"\n")
            for c in clauses:f.write(" ".join(map(str,c))+" 0\n")
        def satisfiable(cs,n):
            return any(all(any((bool(bits&(1<<(abs(x)-1)))==(x>0)) for x in c)
                           for c in cs) for bits in range(1<<n))
        need(satisfiable(clauses,4)==False,"selftest expected UNSAT fixture")
        for mode in MODES[1:]:
            out=p/(mode+".cnf");report=p/(mode+".json");mapping=p/(mode+".map")
            run=subprocess.run([str(pathlib.Path(transform).resolve()),mode,
                str(src),str(out),str(report),str(mapping)],capture_output=True,text=True)
            need(run.returncode==0,"C++ "+mode+" selftest failed: "+run.stderr[-500:])
            data=json.loads(report.read_text())
            if data["use_original"]:continue
            n,rew=exact.parse_dimacs(out)
            need(satisfiable(clauses,4)==satisfiable(rew,n),
                 "ablation changed SAT-equivalence: "+mode)
            need(data["candidate_pairs"]==3,"missed original verified equivalence edge")
            need(data["merged_vars"]==3 or mode=="A" or data["use_original"],
                 "wrong transitive equality mapping: "+mode)
    print("MRE8_SELFTEST_PASS",list(MODES),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("selftest","shard","audit"))
    p.add_argument("--shard",type=int,default=0)
    p.add_argument("--cms",default="mre7_easy/bin/native")
    p.add_argument("--transform",default="mre8/bin/transform")
    a=p.parse_args()
    if a.action=="selftest":selftest(a.transform)
    elif a.action=="shard":shard(a.shard,a.cms,a.transform)
    else:audit()
