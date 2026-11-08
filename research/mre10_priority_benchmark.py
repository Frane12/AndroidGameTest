#!/usr/bin/env python3
"""DRNAS MRE10 native in-process C++ priority experiment.

Keep R28 untouched. 10 arms × 16 exact already-seen SAT original SHA × 4 paired
frozen MRE8 seeds = 640 real SAT/UNSAT wall/PAR2 observations. This is
DEVELOPMENT ONLY. Replays exact Python C_joint/B_clean and stream baseline,
and isolates in-process MRE9-derived cpp native/rename/clean/joint/route/6f.
"""
from __future__ import annotations
import argparse, collections, hashlib, json, os, pathlib, random, subprocess, tempfile, time
import mre8_abcx_ablation as prior
import r195_native_cms_benchmark as r195
import r164_pure_exact_gf2 as exact

PROTO="DRNAS-MRE10-CPP-INPROCESS-MRE8-JOINT-10ARMS-16SHA-4SEED-8S-v1"
ROOT=pathlib.Path("mre10")
CAP=8.0
REPS=4
SHARDS=8
EXPECTED=16
MODES=("N_ext","B_clean_py","C_joint_py","Xc_stream_py",
       "cpp_native","cpp_rename","cpp_clean","cpp_joint",
       "cpp_route","cpp_ref_6f")
CPP_MAP={"cpp_native":"cpp_native","cpp_rename":"cpp_rename",
    "cpp_clean":"cpp_clean","cpp_joint":"cpp_joint",
    "cpp_route":"cpp_route","cpp_ref_6f":"cpp_ref_6f"}
PY_MAP={"B_clean_py":"B_clean","C_joint_py":"C_joint",
        "Xc_stream_py":"Xc_stream_joint"}

def need(ok,msg):
    if not ok:raise RuntimeError("MRE10_FAIL_CLOSED "+str(msg))

def source_set():
    cc=prior.frozen_cases()
    need(len(cc)==EXPECTED and len({c["sha256"] for c in cc})==EXPECTED,
         "16 original source SHA changed")
    return cc

def seed(c,rep):
    return prior.seed_for(c,rep)

def parse_cpp(stdout):
    found=[line.split(" ",1)[1] for line in stdout.splitlines()
           if line.startswith("MRE10_GATE ")]
    need(len(found)==1,"missing in-process C++ gate trace")
    g=json.loads(found[0])
    need(g["certificate"]=="two_original_CNF_binary_clauses_transitive_closure",
         "C++ source proof mismatch")
    return g

def trial(c,rep,mode,extbin,cppbin):
    need(mode in MODES and rep in range(REPS),"invalid arm or frozen seed")
    src=prior.frozen.ROOT/c["filename"]
    need(hashlib.sha256(src.read_bytes()).hexdigest()==c["sha256"],
         "original source bytes changed")
    start=time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="mre10-") as td:
        t=pathlib.Path(td)
        native=None;gate={"applied":False,"reason":"EXTERNAL_ORIGINAL"}
        transform_s=0.0
        cmd=[]
        if mode in CPP_MAP:
            cmd=[str(pathlib.Path(cppbin).resolve()),
                 str(src.resolve()),CPP_MAP[mode],str(seed(c,rep))]
        else:
            used=src;mapping={}
            meta={"changed":False,"arm":mode,"method":"none"}
            if mode in PY_MAP:
                used,mapping,meta=prior.transform(src,PY_MAP[mode],t/"rewritten.cnf")
                transform_s=time.perf_counter()-start
            empt=t/"empty.tsv";empt.write_text("")
            cmd=[str(pathlib.Path(extbin).resolve()),str(used.resolve()),
                 str(empt.resolve()),str(empt.resolve()),
                 "cms_native",str(seed(c,rep))]
        left=CAP-(time.perf_counter()-start)
        verdict="TIMEOUT";stats=None;verified=False;cmd_s=0.0
        if left>0.03:
            t0=time.perf_counter()
            try:
                p=subprocess.run(cmd,capture_output=True,text=True,
                    errors="replace",timeout=left,check=False,env=os.environ.copy())
            except subprocess.TimeoutExpired:
                p=None
            cmd_s=time.perf_counter()-t0
            if p is not None:
                need(p.returncode==0,mode+" solver error: "+p.stderr[-600:])
                if mode in CPP_MAP:gate=parse_cpp(p.stdout)
                else:gate={"applied":bool(meta.get("changed",False)),
                    "reason":meta.get("method","EXTERNAL_ORIGINAL"),"meta":meta}
                verdict,model,stats=r195.parsed_native(p.stdout)
                need(verdict in ("SAT","UNSAT","UNKNOWN"),
                     "unknown native solver verdict "+str(verdict))
                if verdict=="SAT":
                    if mode not in CPP_MAP and mode in PY_MAP:
                        if mapping:
                            model.update({v:model[root] for v,root in mapping.items()})
                    r195.verify_model(src,model)
                    verified=True
                if verdict in ("SAT","UNSAT"):
                    need(verdict==c["reference_screen_status"],
                         "SAT/UNSAT contradicts original source screen")
        wall=time.perf_counter()-start
        if verdict in ("SAT","UNSAT") and wall>CAP:
            verdict="TIMEOUT";verified=False
        if verdict=="UNKNOWN":verdict="TIMEOUT"
        need(verdict!="SAT" or verified,"original SAT witness not verified")
        return dict(proto=PROTO,year=c["year"],gbd=c["gbd"],
            sha256=c["sha256"],mode=mode,rep=rep,seed=seed(c,rep),
            verdict=verdict,source_screen=c["reference_screen_status"],
            original_sat_verified=verified,
            UNSAT_agreement_CaDiCaL_no_independent_LRAT=(verdict=="UNSAT"),
            wall_s=round(wall,6),preprocess_s=round(transform_s,6),
            native_process_s=round(cmd_s,6),
            par2_s=round(wall if verdict in ("SAT","UNSAT") else 2*CAP,6),
            native=stats,gate=gate,source_known_dev=True,run_sha=os.getenv("GITHUB_SHA","local"))

def test_cpp_parity(cppbin):
    source_set()
    # Original exact 16 inputs; 3 equivalent representations, no posthoc
    # exclusion. Every Python/Pure-C++ output must be identical clause-for-clause.
    counts=collections.Counter()
    for c in source_set():
        src=prior.frozen.ROOT/c["filename"]
        n,original=exact.parse_dimacs(src)
        for m1,m2 in (("B_clean","cpp_clean"),
                      ("A_rename","cpp_rename"),
                      ("C_joint","cpp_joint")):
            with tempfile.TemporaryDirectory(prefix="mre10-parity-") as td:
                d=pathlib.Path(td)
                py,mapping,meta=prior.transform(src,m1,d/"py.cnf")
                target=d/"cpp.cnf"
                run=subprocess.run([str(pathlib.Path(cppbin).resolve()),
                     "--emit",str(src.resolve()),m2,str(target)],
                     capture_output=True,text=True,check=False,timeout=20)
                need(run.returncode==0,
                     "native emission failed on "+c["gbd"]+" "+m2+" "+run.stderr[-250:])
                g=parse_cpp(run.stdout)
                _,pp=exact.parse_dimacs(py)
                nc,cp=exact.parse_dimacs(target)
                need(nc==n and pp==cp,
                     "C++ and Python changed clauses differently: "+c["gbd"]+" "+m2)
                if m2=="cpp_rename" or m2=="cpp_joint":
                    expected=len(mapping)
                    if original==pp:expected=0
                    need(g["variables_eliminated"]==expected or not g["applied"],
                         "C++ exact-quotient witness count mismatch")
                counts[m2]+=1
    print("MRE10_16ORIGINAL_EXACT_CLAUSE_PARITY_PASS",dict(counts),flush=True)

def shard(index,extbin,cppbin):
    need(index in range(SHARDS),"bad shard")
    cc=source_set()
    todo=[c for i,c in enumerate(cc) if i%SHARDS==index]
    need(len(todo)==2,"two SHA originals required per shard")
    ROOT.mkdir(exist_ok=True)
    rows=[]
    for c in todo:
        for rep in range(REPS):
            order=list(MODES)
            random.Random(PROTO+c["sha256"]+str(rep)).shuffle(order)
            for mode in order:
                r=trial(c,rep,mode,extbin,cppbin)
                rows.append(r)
                (ROOT/("shard-%d.json"%index)).write_text(json.dumps(rows,sort_keys=True)+"\n")
                print("MRE10_TRIAL",json.dumps(r,sort_keys=True),flush=True)
    need(len(rows)==2*REPS*len(MODES),"missing trial from shard")
    print("MRE10_SHARD_PASS",index,len(rows),flush=True)

def audit():
    cc=source_set()
    source={x["sha256"]:x for x in cc}
    rows=[]
    for idx in range(SHARDS):
        name=ROOT/("shard-%d.json"%idx)
        need(name.exists(),"missing shard "+str(idx))
        rows.extend(json.loads(name.read_text()))
    need(len(rows)==EXPECTED*REPS*len(MODES),"not full MRE10 factorial")
    paired=collections.defaultdict(dict)
    for r in rows:
        c=source.get(r["sha256"])
        need(c is not None and c["gbd"]==r["gbd"],"alien original")
        need(r["proto"]==PROTO and r["mode"] in MODES and r["rep"] in range(REPS),
             "unfrozen mode/protocol")
        need(r["seed"]==seed(c,r["rep"]),"wrong paired seed")
        need(r["verdict"] in ("SAT","UNSAT","TIMEOUT"),"unrecognized outcome")
        if r["verdict"]=="SAT":need(r["original_sat_verified"],"SAT not verified")
        if r["verdict"]=="UNSAT":
            need(c["reference_screen_status"]=="UNSAT" and
                 r["UNSAT_agreement_CaDiCaL_no_independent_LRAT"],
                 "UNSAT not cross-checked")
        key=(r["sha256"],r["rep"])
        need(r["mode"] not in paired[key],"duplicate arm")
        paired[key][r["mode"]]=r
    need(len(paired)==EXPECTED*REPS,"missing SHA or seed")
    for group in paired.values():
        need(set(group)==set(MODES),"missing mode in paired trial")
        need(len({v["seed"] for v in group.values()})==1,"unpaired modes")
    scores={}
    base=0.0
    for mode in MODES:
        sample=[v for v in rows if v["mode"]==mode]
        score=dict(trials=len(sample),
            SAT=sum(v["verdict"]=="SAT" for v in sample),
            UNSAT_crosschecked_no_LRAT=sum(v["verdict"]=="UNSAT" for v in sample),
            solved=sum(v["verdict"] in ("SAT","UNSAT") for v in sample),
            timeouts=sum(v["verdict"]=="TIMEOUT" for v in sample),
            par2_s=round(sum(v["par2_s"] for v in sample),6),
            prep_s=round(sum(v["preprocess_s"] for v in sample),6),
            wall_s=round(sum(v["wall_s"] for v in sample),6),
            applied=sum(bool(v["gate"].get("applied")) for v in sample))
        scores[mode]=score
        if mode=="N_ext":base=score["par2_s"]
    need(base>0,"no reference PAR2")
    for mode in MODES:
        scores[mode]["PAR2_speedup_vs_N_ext_x"]=round(base/scores[mode]["par2_s"],6)
    per_source=[]
    for c in cc:
        keys=[p for (sha,rep),p in paired.items() if sha==c["sha256"]]
        need(len(keys)==REPS,"source missing repeat")
        bymode={m:dict(solved=sum(g[m]["verdict"] in ("SAT","UNSAT") for g in keys),
            par2_s=round(sum(g[m]["par2_s"] for g in keys),6),
            conflicts=[g[m]["native"].get("conflicts") if g[m]["native"] else None for g in keys],
            propagations=[g[m]["native"].get("propagations") if g[m]["native"] else None for g in keys])
            for m in MODES}
        per_source.append(dict(gbd=c["gbd"],year=c["year"],
            source_sha256=c["sha256"],by_mode=bymode))
    report=dict(protocol=PROTO,cases=EXPECTED,repeats=REPS,total_trials=len(rows),
        source_selection="previously_used_MRE7E_MRE8_CMS_reference_easiness",
        explicitly_development_not_blind=True,
        R28_original_code_untouched=True,benchmark_cap_s=CAP,
        same_source_SHA_and_paired_seed=True,
        original_SAT_witness_checked=True,
        independent_UNSAT_LRAT=False,
        no_auto_promotion=True,
        MRE9_same_pinned_CMS_library=True,
        native_CPP_excludes_Python_quotient=True,
        scores=scores,per_source=per_source)
    ROOT.mkdir(exist_ok=True)
    (ROOT/"report.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print("MRE10_FINAL",json.dumps({k:v for k,v in report.items() if k!="per_source"},
        sort_keys=True),flush=True)

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("action",choices=("selftest","parity","shard","audit"))
    ap.add_argument("--shard",type=int,default=0)
    ap.add_argument("--ext",default="mre7_easy/bin/native")
    ap.add_argument("--cpp",default="mre10/bin/native")
    ap.add_argument("--standalone",default="mre10/bin/standalone")
    args=ap.parse_args()
    if args.action=="selftest":
        prior.selftest()
        need(len(MODES)==10 and CAP==8 and REPS==4 and SHARDS==8,"protocol drift")
        print("MRE10_SELFTEST_PASS",PROTO,flush=True)
    elif args.action=="parity":test_cpp_parity(args.standalone)
    elif args.action=="shard":shard(args.shard,args.ext,args.cpp)
    else:audit()
