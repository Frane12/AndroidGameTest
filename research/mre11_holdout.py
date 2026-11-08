#!/usr/bin/env python3
"""DRNAS MRE11: prospective SAT2026 official cohort, pre-registered source-only
selector. Eight original 2026 GBD source files, 4 SHA-paired seeds, 5 native
C++ arms, 8-second end-to-end PAR2. No runtime or formula structures used
for choosing sources. MRE10 development source files were from 2022-2025;
historical registry exclusions are best-effort and NOT globally exhaustive.
SAT witness checked against ORIGINAL SHA; UNSAT published CaDiCaL result,
not an independently verified LRAT certificate. No automatic promotion.
"""
from __future__ import annotations
import argparse, collections, csv, hashlib, io, json, os, pathlib
import random, re, subprocess, tempfile, time
import mre6b_blind_freeze as historical
import r195_native_cms_benchmark as native_ref
import r164_pure_exact_gf2 as exact

PROTO="DRNAS-MRE11-PROSPR-SAT2026-8-ORIGINAL-5ARMS-4SEEDS-8S-v1"
SALT="DRNAS-MRE11-NO-TUNING-SAT2026-SOURCE-20261108-LOCKED-v1"
ROOT=pathlib.Path("mre11")
MODES=("cpp_native","cpp_clean","cpp_rename","cpp_joint","cpp_mre11_sel")
REPS=4
SHARDS=4
CAP=8.0
TARGET=8
MIN_READY=6
MAX_FETCH=160
MAX_RAW=10*1024*1024
MAX_PLAIN=12*1024*1024
MAX_VARS=12000
MAX_CLAUSES=35000
OFFICIAL_STATUS={"sat-verified":"SAT","unsat-verified":"UNSAT"}

def need(ok,msg):
    if not ok: raise RuntimeError("MRE11_FAIL_CLOSED "+str(msg))
def sha(b): return hashlib.sha256(b).hexdigest()
def save(path, obj):
    pathlib.Path(path).write_text(json.dumps(obj,indent=2,sort_keys=True)+"\n")
def seed(c,rep):
    return int(sha((PROTO+"|SEED|"+c["sha256"]+"|"+str(rep)).encode())[:8],16)
def cases():
    m=json.loads((ROOT/"manifest.json").read_text())
    need(m["protocol"]==PROTO and MIN_READY<=len(m["cases"])<=TARGET,"invalid frozen manifest")
    need(len({c["gbd"] for c in m["cases"]})==len(m["cases"]),"duplicate GBD")
    need(len({c["sha256"] for c in m["cases"]})==len(m["cases"]),"duplicate source SHA")
    for c in m["cases"]:
        b=(ROOT/c["filename"]).read_bytes()
        need(sha(b)==c["sha256"] and len(b)==c["bytes"],"original SHA mismatch")
        need(c["official_status"] in ("SAT","UNSAT"),"unverified official result")
        need(c["year"]==2026,"non-2026 contamination")
    return m["cases"]

def freeze():
    ROOT.mkdir(exist_ok=True)
    # Official 2026 competition URI and instance-wise published CaDiCaL labels.
    raw=historical.r52.fetch_bytes(historical.r52.URI,100000)
    ids=[x.strip().rsplit("/",1)[-1] for x in raw.decode().splitlines() if x.strip()]
    need(len(ids)==400 and len(set(ids))==400,"official 2026 GBD index drift")
    need(all(re.fullmatch(r"[0-9a-f]{32}",g) for g in ids),"bad official 2026 GBD")
    results=historical.r52.fetch_bytes(historical.r52.SCORES,24*1024*1024)
    labels={x["instanceid"]:OFFICIAL_STATUS.get(x["status"])
            for x in csv.DictReader(io.StringIO(results.decode()))
            if x.get("solverid")=="biere_cadical3[main]"}
    need(len(labels)==400,"published CaDiCaL 2026 status set incomplete")
    need(historical.PRIOR.exists(),"prior source registry unavailable")
    history={x.strip() for x in historical.PRIOR.read_text().splitlines()
             if re.fullmatch(r"[0-9a-f]{32}",x.strip())}
    ids_seen,sha_seen=historical.inspect_repo_ids(set(ids))
    # Conservative superset of earlier R82 2026 benchmark pool, even if
    # R82 was unable to retrieve each candidate successfully.
    r82=set(sorted(ids,key=lambda g:sha(
        ("DRNAS-R82-PRECOMMIT-WIDE-RANDOM-ORIGINALS-2025-2026-20261104-v1/2026/"+g).encode()))[:220])
    exclude=history|ids_seen|r82
    eligible=sorted((g for g in ids if g not in exclude),
                    key=lambda g:sha((SALT+"|"+g).encode()))
    need(len(eligible)>=TARGET,"prior exclusion leaves too few official sources")
    trace=[];selected=[];quota={"SAT":0,"UNSAT":0}
    historical.r32p.CNF_LIMIT=MAX_PLAIN
    for g in eligible[:MAX_FETCH]:
        if len(selected)>=TARGET:break
        status=labels.get(g)
        entry={"gbd":g,"official_status":status}
        if status not in quota:
            entry["reason"]="unverified_or_unknown_official_status"
            trace.append(entry);continue
        if quota[status]>=TARGET//2:
            entry["reason"]="precommitted_status_quota"
            trace.append(entry);continue
        path=ROOT/(g+".cnf")
        try:
            rawfile,_=historical.r32p.request_url(
                "https://benchmark-database.de/file/"+g,MAX_RAW,seconds=35)
            plain,kind=historical.r32p.decode(rawfile)
            need(len(plain)<=MAX_PLAIN,"plain DIMACS resource cap")
            n,m=historical.r32p.parse_dimacs_metadata(plain)
            need(n<=MAX_VARS and m<=MAX_CLAUSES,
                 "declared variable/clause resource cap")
            digest=sha(plain)
            need(digest not in sha_seen,"prior source content SHA appears in repo")
            need(digest not in {c["sha256"] for c in selected},"duplicate original")
            path.write_bytes(plain)
            c={"gbd":g,"filename":path.name,"sha256":digest,
               "bytes":len(plain),"variables":n,"clauses":m,"year":2026,
               "official_status":status,"source_url":"https://benchmark-database.de/file/"+g,
               "compression":kind}
            selected.append(c);quota[status]+=1
            entry.update(reason="frozen_before_MRE11_run",sha256=digest,vars=n,clauses=m)
        except Exception as e:
            path.unlink(missing_ok=True)
            entry.update(reason="download_or_resource_limit",error=(type(e).__name__+": "+str(e))[:180])
        trace.append(entry)
        print("MRE11_FREEZE_SCAN",json.dumps(entry,sort_keys=True),flush=True)
    need(len(selected)>=MIN_READY,"insufficient prospectively frozen 2026 sources")
    need(min(quota.values())>=2,"SAT/UNSAT balance missing")
    manifest={"protocol":PROTO,"cases":selected,"target":TARGET,
              "actual":len(selected),"shortfall":TARGET-len(selected),
              "status_counts":quota,
              "selection_policy":"official CaDiCaL labels, salted GBD ranking, fixed resource limits; no MRE11 performance or source structure",
              "official_index":historical.r52.URI,"official_index_sha256":sha(raw),
              "official_scores":historical.r52.SCORES,"official_scores_sha256":sha(results),
              "historical_exclusions":len(set(ids)&exclude),
              "R82_early_220_excluded":True,
              "historical_registry_global_exhaustiveness_unproven":True,
              "disjoint_to_MRE10_2022_2025":True,"SAT_witness_original_verified":True,
              "UNSAT_official_CaDiCaL_not_independent_LRAT":True,
              "repeats":REPS,"cap_s":CAP,"modes":list(MODES),"traces":trace}
    save(ROOT/"manifest.json",manifest)
    (ROOT/"source.sha256").write_text("".join(
        c["sha256"]+"  "+c["filename"]+"\n" for c in selected))
    print("MRE11_FREEZE_FINAL",json.dumps({k:v for k,v in manifest.items()
          if k not in ("cases","traces")},sort_keys=True),flush=True)

def parse_gate(out):
    lines=[x.split(" ",1)[1] for x in out.splitlines() if x.startswith("MRE10_GATE ")]
    need(len(lines)==1,"missing certified C++ gate JSON")
    g=json.loads(lines[0])
    need(g["certificate"]=="two_original_CNF_binary_clauses_transitive_closure",
         "uncertified gate transformation")
    return g

def subprocess_gate(src,mode,output,binary):
    cmd=[str(pathlib.Path(binary).resolve()),"--emit",str(src.resolve()),
         mode,str(output.resolve())]
    p=subprocess.run(cmd,capture_output=True,text=True,check=False,timeout=25)
    need(p.returncode==0,"standalone gate failed: "+p.stderr[-400:])
    return parse_gate(p.stdout)

def selftest(binary):
    need(len(MODES)==5 and TARGET==8 and REPS==4 and SHARDS==4 and CAP==8.0,
         "protocol reconfigured")
    # Construct synthetic original-CNF fixtures with independently provable
    # positive equivalences or exact duplicate clauses.
    with tempfile.TemporaryDirectory(prefix="mre11-selftest-") as td:
        td=pathlib.Path(td);src=td/"input.cnf";out=td/"output.cnf"
        fixtures=[]
        eq=[]
        for v in range(2,7):
            eq.extend([(-1,v),(1,-v)])
        eq.extend([(2,7),(-2,7)])
        fixtures.append(("MRE11_SOURCE_SELECT_RENAME",7,eq))
        clean=[(1,2)]*81+[(1,3),(-1,3)]
        fixtures.append(("MRE11_SOURCE_SELECT_CLEAN",3,clean))
        fixtures.append(("MRE11_ABSTAIN_NO_STRONG_SOURCE_SIGNAL",3,[(1,2),(2,3),(-2,3)])
        for want,n,cl in fixtures:
            src.write_text("p cnf %d %d\n"%(n,len(cl))+
                           "".join(" ".join(map(str,c))+" 0\n" for c in cl))
            gate=subprocess_gate(src,"cpp_mre11_sel",out,binary)
            need(gate["reason"]==want,
                 "selector synthetic route changed: "+str(gate))
            # Changed DIMACS has a clause-level exact parity against the arm
            # selected by the predeclared structural policy.
            arm="cpp_rename" if "RENAME" in want else (
                 "cpp_clean" if "CLEAN" in want else "cpp_native")
            baseline=td/"reference.cnf"
            subprocess_gate(src,arm,baseline,binary)
            need(exact.parse_dimacs(out)==exact.parse_dimacs(baseline),
                 "selected output not identical to declared certified arm")
    print("MRE11_SYNTHETIC_SOURCE_POLICY_PASS",PROTO,flush=True)

def parity(binary):
    cc=cases()
    counts=collections.Counter()
    with tempfile.TemporaryDirectory(prefix="mre11-parity-") as td:
        d=pathlib.Path(td)
        for c in cc:
            src=ROOT/c["filename"]
            selected=d/"selected.cnf"
            g=subprocess_gate(src,"cpp_mre11_sel",selected,binary)
            mode=("cpp_rename" if g["reason"]=="MRE11_SOURCE_SELECT_RENAME" else
                  "cpp_clean" if g["reason"]=="MRE11_SOURCE_SELECT_CLEAN" else
                  "cpp_native")
            witness=d/"expected.cnf"
            subprocess_gate(src,mode,witness,binary)
            need(exact.parse_dimacs(selected)==exact.parse_dimacs(witness),
                 "selected source differs from certified exact arm "+c["gbd"])
            # The original reference is re-parsed from the SHA-verified file.
            exact.parse_dimacs(src)
            counts[mode]+=1
    print("MRE11_SOURCE_EXACT_ARM_PARITY_PASS",json.dumps(counts,sort_keys=True),flush=True)

def trial(c,rep,mode,binary):
    need(rep in range(REPS) and mode in MODES,"invalid mode/seed")
    source=ROOT/c["filename"]
    need(sha(source.read_bytes())==c["sha256"],"source mutation")
    start=time.perf_counter()
    cmd=[str(pathlib.Path(binary).resolve()),str(source.resolve()),mode,str(seed(c,rep))]
    p=None
    try:
        p=subprocess.run(cmd,capture_output=True,text=True,
                         timeout=CAP,check=False,errors="replace")
    except subprocess.TimeoutExpired:
        pass
    wall=time.perf_counter()-start
    verdict="TIMEOUT";gate=None;native=None;verified=False
    if p is not None:
        need(p.returncode==0,mode+" C++ native solver error: "+p.stderr[-500:])
        gate=parse_gate(p.stdout)
        verdict,model,native=native_ref.parsed_native(p.stdout)
        need(verdict in ("SAT","UNSAT","UNKNOWN","BUDGET"),
             "invalid SAT solver verdict "+str(verdict))
        if verdict=="SAT":
            native_ref.verify_model(source,model)
            verified=True
        if verdict in ("SAT","UNSAT"):
            need(verdict==c["official_status"],"official 2026 CaDiCaL disagreement")
    if verdict in ("UNKNOWN","BUDGET") or wall>CAP: verdict="TIMEOUT"
    if verdict=="TIMEOUT":verified=False
    return {"protocol":PROTO,"gbd":c["gbd"],"source_sha256":c["sha256"],
        "official_status":c["official_status"],"year":2026,
        "rep":rep,"seed":seed(c,rep),"mode":mode,"verdict":verdict,
        "original_SAT_witness_verified":verified,
        "UNSAT_official_agreement_without_LRAT":verdict=="UNSAT",
        "wall_s":round(wall,6),
        "par2_s":round(wall if verdict in ("SAT","UNSAT") else 2*CAP,6),
        "native_stats":native,"gate":gate,
        "run_sha":os.getenv("GITHUB_SHA","local")}
def shard(index,binary):
    need(index in range(SHARDS),"invalid shard")
    cc=cases()
    todo=[c for j,c in enumerate(cc) if j%SHARDS==index]
    need(todo,"empty shard")
    rows=[]
    for c in todo:
        for rep in range(REPS):
            order=list(MODES)
            random.Random(PROTO+c["sha256"]+str(rep)).shuffle(order)
            for m in order:
                r=trial(c,rep,m,binary)
                rows.append(r)
                save(ROOT/("shard-%d.json"%index),rows)
                print("MRE11_TRIAL",json.dumps(r,sort_keys=True),flush=True)
    need(len(rows)==len(todo)*REPS*len(MODES),"missing paired trial")
    print("MRE11_SHARD_PASS",index,len(rows),flush=True)

def audit():
    cc=cases()
    rows=[]
    for sh in range(SHARDS):
        file=ROOT/("shard-%d.json"%sh)
        need(file.exists(),"shard missing "+str(sh))
        rows.extend(json.loads(file.read_text()))
    need(len(rows)==len(cc)*REPS*len(MODES),"incomplete paired audit")
    keyed=collections.defaultdict(dict)
    case_map={c["sha256"]:c for c in cc}
    for r in rows:
        c=case_map.get(r["source_sha256"])
        need(c is not None and c["gbd"]==r["gbd"],"alien input SHA")
        need(r["protocol"]==PROTO and r["rep"] in range(REPS) and r["mode"] in MODES,
             "unfrozen mode or protocol")
        need(r["seed"]==seed(c,r["rep"]),"unpaired seed")
        need(r["verdict"] in ("SAT","UNSAT","TIMEOUT"),"unknown result")
        if r["verdict"]=="SAT":
            need(r["original_SAT_witness_verified"] and c["official_status"]=="SAT",
                 "SAT not original independently verified")
        if r["verdict"]=="UNSAT":
            need(r["UNSAT_official_agreement_without_LRAT"] and c["official_status"]=="UNSAT",
                 "UNSAT disagrees with official CaDiCaL")
        key=(c["sha256"],r["rep"])
        need(r["mode"] not in keyed[key],"duplicate source/seed arm")
        keyed[key][r["mode"]]=r
    need(len(keyed)==len(cc)*REPS,"missing source/seed")
    for group in keyed.values():
        need(set(group)==set(MODES),"incomplete group")
        need(len({g["seed"] for g in group.values()})==1,"not SHA-paired")
    scores={}
    for mode in MODES:
        xs=[r for r in rows if r["mode"]==mode]
        scores[mode]={"trials":len(xs),
              "solved":sum(r["verdict"] in ("SAT","UNSAT") for r in xs),
              "SAT":sum(r["verdict"]=="SAT" for r in xs),
              "UNSAT_official_no_LRAT":sum(r["verdict"]=="UNSAT" for r in xs),
              "timeouts":sum(r["verdict"]=="TIMEOUT" for r in xs),
              "PAR2_total_s":round(sum(r["par2_s"] for r in xs),6),
              "applied":sum(bool((r["gate"] or {}).get("applied")) for r in xs)}
    baseline=scores["cpp_native"]["PAR2_total_s"]
    for s in scores.values():
        s["PAR2_speedup_vs_native_x"]=round(baseline/s["PAR2_total_s"],6)
    per_source=[]
    for c in cc:
        sample=[r for r in rows if r["source_sha256"]==c["sha256"]]
        d={}
        for mode in MODES:
            ss=[r for r in sample if r["mode"]==mode]
            d[mode]={"par2_s":round(sum(r["par2_s"] for r in ss),6),
                     "solved":sum(r["verdict"] in ("SAT","UNSAT") for r in ss),
                     "applied":sum(bool((r["gate"] or {}).get("applied")) for r in ss),
                     "reasons":sorted(set((r["gate"] or {}).get("reason","TIMEOUT") for r in ss))}
        per_source.append({"gbd":c["gbd"],"original_sha256":c["sha256"],
                           "official_status":c["official_status"],
                           "variables":c["variables"],"clauses":c["clauses"],
                           "modes":d})
    report={"protocol":PROTO,"official_2026_sources":len(cc),
            "total_trials":len(rows),"modes":list(MODES),"repeats":REPS,
            "cap_s":CAP,"selection_no_solving_or_tuning":True,
            "historical_registry_not_guaranteed_exhaustive":True,
            "strict_MRE10_2022_2025_disjoint":True,
            "published_CaDiCaL_UNSAT_without_independent_LRAT":True,
            "SAT_original_model_verified":True,
            "no_auto_promotion":True,"R28_reference_code_untouched":True,
            "scores":scores,"per_source":per_source}
    save(ROOT/"report.json",report)
    print("MRE11_FINAL",json.dumps({k:v for k,v in report.items() if k!="per_source"},
          sort_keys=True),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("freeze","verify","selftest","parity","shard","audit"))
    p.add_argument("--shard",type=int,default=0)
    p.add_argument("--binary",default="mre11/bin/native")
    p.add_argument("--standalone",default="mre11/bin/standalone")
    args=p.parse_args()
    if args.action=="freeze":freeze()
    elif args.action=="verify":
        print("MRE11_SOURCE_VERIFIED",len(cases()),flush=True)
    elif args.action=="selftest":selftest(args.standalone)
    elif args.action=="parity":parity(args.standalone)
    elif args.action=="shard":shard(args.shard,args.binary)
    else:audit()
