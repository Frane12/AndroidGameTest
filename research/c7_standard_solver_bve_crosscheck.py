#!/usr/bin/env python3
"""C7: Standard solver cross-check of CMS BVE × original-CNF dedup.

Source-locked six C6 DEVELOPMENT originals (4 with duplicates, 2 controls).
CaDiCaL default/no-elim × original/identity-certified dedup,
Kissat 4.0.4 default × original/dedup,
CryptoMiniSat 5.11.15 (pinned C2/C6) native/noBVE × original/dedup.
All 10 arms solve EXACT original problem, and SAT models are independently
replayed on the original SHA. Derived-CNF preprocessing time is included in
each externally preprocessed trial; native includes in-process preparation.
2 repetitions and 25s real wall cap = 120 real end-to-end attempts. No blind
claims; external solver defaults repeated rather than independent random seeds.
"""
from __future__ import annotations
import argparse,collections,hashlib,json,os,pathlib,random,re,statistics,subprocess,tempfile,time
import c6_cms_inprocessing_factorial as c6
import c2_cnf_clean_ablation as c2
import r195_native_cms_benchmark as cms
import mre11b_prospective_benchmark as ref

PROTO="DRNAS-C7-6SOURCE-10ARM-CMS-CADICAL-KISSAT-BVE-DEDUP-2REP-25S-v1"
CAP=25.0
REPS=2
OUT=pathlib.Path("c7_out")
DEDUP=pathlib.Path("c7_source")/"dedup"
MODES=("cms_default","cms_nobve","cms_dedup","cms_dedup_nobve",
       "cadical_default","cadical_noelim","cadical_dedup","cadical_dedup_noelim",
       "kissat_default","kissat_dedup")
EXTERNAL=frozenset(x for x in MODES if x.startswith(("cadical","kissat")))
EXT_DEDUP=frozenset(("cadical_dedup","cadical_dedup_noelim","kissat_dedup"))
CMS_MODE={"cms_default":"cpp_native","cms_nobve":"c6_native_nobve",
          "cms_dedup":"cpp_dedup","cms_dedup_nobve":"c6_dedup_nobve"}
def need(b,why):
    if not b:raise RuntimeError("C7_FAIL_CLOSED "+str(why))
def digest(path):
    h=hashlib.sha256()
    with pathlib.Path(path).open("rb") as f:
        for chunk in iter(lambda:f.read(1<<20),b""):h.update(chunk)
    return h.hexdigest()
def source_cases():
    cc=c6.sources()
    need(len(cc)==6 and len({c["sha256"] for c in cc})==6,
         "original source SHA roster drift")
    for c in cc:
        need(digest(c["path"])==c["sha256"],"source SHA mismatch")
    return cc
def get_cases():
    cc=source_cases()
    manifest=json.loads((DEDUP/"manifest.json").read_text())
    need(manifest["protocol"]==PROTO and len(manifest["sources"])==6,
         "invalid frozen dedup source derivation")
    bysha={c["sha256"]:c for c in cc}
    need(set(manifest["sources"])==set(bysha),
         "derived source manifest differs from six frozen originals")
    for sha,m in manifest["sources"].items():
        c=bysha[sha]
        need(m["gbd"]==c["gbd"] and m["original_sha256"]==sha,
             "derived registry source mismatch")
        target=DEDUP/(c["gbd"]+".cnf")
        need(digest(target)==m["derived_sha256"],
             "source-certified dedup CNF SHA mismatch")
    return cc,manifest
def canonical(clauses):
    return [tuple(sorted(set(cl))) for cl in clauses]
def derive(c,destination):
    # Standalone C2 binary; source-equivalent exact-duplicate removal only.
    t=time.perf_counter()
    p=subprocess.run(["c2/bin/emit","--emit",str(c["path"]),
                      "cpp_dedup",str(destination)],
        capture_output=True,text=True,errors="replace",check=True)
    prep=time.perf_counter()-t
    gate=c2.parse_native_gate(p.stdout,"cpp_dedup")
    need(gate["variables_eliminated"]==0 and
         gate["taut_clauses_removed"]==0 and
         gate["duplicate_literals_removed"]==0,"dedup had non-identity transformation")
    return prep,gate
def freeze():
    OUT.mkdir(exist_ok=True)
    DEDUP.mkdir(parents=True,exist_ok=True)
    registry={}
    for c in source_cases():
        n,original=c2.read_clauses(c["path"])
        unique=set(canonical(original))
        target=DEDUP/(c["gbd"]+".cnf")
        prep,gate=derive(c,target)
        n2,rewritten=c2.read_clauses(target)
        need(n==n2 and set(canonical(rewritten))==unique and
             len(rewritten)==len(unique),
             "derived dedup was not exactly original CNF unique clause semantics")
        need(gate["duplicate_clauses_removed"]==len(original)-len(rewritten),
             "dedup count inconsistent with independent source scan")
        registry[c["sha256"]]=dict(gbd=c["gbd"],original_sha256=c["sha256"],
             derived_sha256=digest(target),original_clauses=len(original),
             dedup_clauses=len(rewritten),
             duplicates_removed=len(original)-len(rewritten),
             preparation_s=round(prep,6),source_type=(
                 "no_duplicate_control" if c["control"] else "selected_C4_development"))
        print("C7_DERIVED_SOURCE",json.dumps(registry[c["sha256"]],sort_keys=True),flush=True)
    (DEDUP/"manifest.json").write_text(json.dumps(dict(
        protocol=PROTO,provenance="six previously used development original CNF SHA, NOT blind",
        source_equivalence="identical canonical clause sets and variable count",
        sources=registry),indent=2,sort_keys=True)+"\n")
    need(sum(x["duplicates_removed"]>0 for x in registry.values())==4,
         "original four-positive/two-control duplicate class changed")
    print("C7_SOURCE_CERTIFICATE_PASS",len(registry),flush=True)
def binaries():
    return {"cadical":"/usr/bin/cadical","kissat":"built/bin/kissat_4_0_4"}
def external_cmd(mode,path):
    if mode.startswith("cadical"):
        opts=["--no-elim"] if mode.endswith("noelim") else []
        return [binaries()["cadical"],*opts,str(path.resolve())]
    if mode.startswith("kissat"):
        return [str(pathlib.Path(binaries()["kissat"]).resolve()),str(path.resolve())]
    raise RuntimeError("external mode not handled")
def smoke():
    cc,m=get_cases()
    OUT.mkdir(exist_ok=True)
    tiny=OUT/"c7_smoke.cnf"
    tiny.write_text("p cnf 4 7\n1 2 0\n2 1 0\n1 2 0\n-2 3 0\n4 -4 0\n3 0\n4 0\n")
    derived=OUT/"c7_smoke-dedup.cnf"
    _,gate=derive(dict(path=tiny),derived)
    need(gate["duplicate_clauses_removed"]==2,"synthetic duplicate test failed")
    for family in ("cadical","kissat"):
        pth=binaries()[family]
        ver=subprocess.run([pth,"--version"],capture_output=True,text=True,check=False)
        need(ver.returncode==0,"missing standard solver binary "+family)
        version=(ver.stdout+" "+ver.stderr).strip()
        (OUT/(family+"-version.txt")).write_text(version+"\n")
        for mode in [x for x in EXTERNAL if x.startswith(family)]:
            p=subprocess.run(external_cmd(mode,derived if mode in EXT_DEDUP else tiny),
                capture_output=True,text=True,errors="replace",timeout=10,check=False)
            status,model=ref.external_parse(p)
            need(status=="SAT","external smoke option unsupported "+mode+
                 " stderr="+p.stderr[-400:])
            cms.verify_model(tiny,model)
    # Ensure the CMS inprocess 4 modes also work with C2 control and certified model.
    for mode in ("cms_default","cms_nobve","cms_dedup","cms_dedup_nobve"):
        exe=("c2/bin/native" if mode in ("cms_default","cms_dedup") else "c6/bin/native")
        p=subprocess.run([exe,str(tiny),CMS_MODE[mode],"42"],
                         capture_output=True,text=True,timeout=10,check=True)
        status,model,native=cms.parsed_native(p.stdout)
        need(status=="SAT","CMS original source smoke failed")
        cms.verify_model(tiny,model)
        c6.native_gate(p.stdout,CMS_MODE[mode])
    print("C7_STANDARD_SOLVER_OPTIONS_AND_WITNESS_SMOKE_PASS",flush=True)
def trial(c,rep,mode,manifest):
    need(rep in range(REPS) and mode in MODES,"unregistered C7 arm")
    original=c["path"]
    need(digest(original)==c["sha256"],"original source input changed")
    seed=c6.seed(c,rep)
    t=time.perf_counter()
    external=mode in EXTERNAL
    prep=0.0;gate={};native=None
    status="TIMEOUT";verified=False
    inp=original
    # Charge external dedup *per attempt* and verify exact derived SHA,
    # rather than passing free preprocessed copies into external solvers.
    with tempfile.TemporaryDirectory(prefix="c7dedup-",dir=OUT) as temp:
        if mode in EXT_DEDUP:
            inp=pathlib.Path(temp)/(c["gbd"]+".cnf")
            prep,gate=derive(c,inp)
            need(digest(inp)==manifest["sources"][c["sha256"]]["derived_sha256"],
                 "derived source hash differs from preregistered C2 transformation")
        if external:
            cmd=external_cmd(mode,inp)
        else:
            exe=("c2/bin/native" if mode in ("cms_default","cms_dedup")
                 else "c6/bin/native")
            cmd=[str(pathlib.Path(exe).resolve()),str(original.resolve()),
                 CMS_MODE[mode],str(seed)]
        remaining=CAP-(time.perf_counter()-t)
        p=None
        if remaining>0.05:
            env=os.environ.copy();env.pop("DRNAS_MAX_CONFLICTS",None)
            try:
                p=subprocess.run(cmd,capture_output=True,text=True,errors="replace",
                                 check=False,timeout=remaining,env=env)
            except subprocess.TimeoutExpired:
                pass
        if p is not None:
            if external:
                status,model=ref.external_parse(p)
            else:
                need(p.returncode==0,"CMS C2/C6 crash "+p.stderr[-700:])
                gate=c6.native_gate(p.stdout,CMS_MODE[mode])
                status,model,native=cms.parsed_native(p.stdout)
            need(status in ("SAT","UNSAT","UNKNOWN","TIMEOUT"),
                 "solver gave unexpected verdict")
            if status=="SAT":
                cms.verify_model(original,model)
                verified=True
            if status in ("SAT","UNSAT"):
                need(status==c["expected_status"],
                     "solver terminal disagrees with original SHA reference")
    wall=time.perf_counter()-t
    if status not in ("SAT","UNSAT") or wall>CAP:
        status="TIMEOUT";verified=False;native=None
    need(status!="SAT" or verified,"SAT without original CNF model proof")
    return dict(protocol=PROTO,original_sha256=c["sha256"],gbd=c["gbd"],
        rep=rep,seed=seed,mode=mode,status=status,
        independent_seed_applied=not external,
        wall_s=round(wall,6),prep_s=round(prep,6),
        cap_s=CAP,par2_s=round(wall if status in ("SAT","UNSAT") else 2*CAP,6),
        original_SAT_witness_verified=verified,
        UNSAT_independent_LRAT=False,
        native_stats=native,gate=gate,
        derived_sha256=(manifest["sources"][c["sha256"]]["derived_sha256"]
                        if mode in EXT_DEDUP else None),
        build_sha=os.getenv("GITHUB_SHA","local"))
def shard(i):
    cc,manifest=get_cases()
    need(i in range(len(cc)),"unknown source shard")
    OUT.mkdir(exist_ok=True)
    c=cc[i];rows=[]
    for rep in range(REPS):
        order=list(MODES)
        random.Random(PROTO+"|"+c["sha256"]+"|"+str(rep)).shuffle(order)
        for mode in order:
            x=trial(c,rep,mode,manifest);rows.append(x)
            (OUT/("shard-%d.json"%i)).write_text(
                json.dumps(rows,indent=2,sort_keys=True)+"\n")
            print("C7_TRIAL",json.dumps(x,sort_keys=True),flush=True)
    need(len(rows)==REPS*len(MODES),"incomplete standard solver shard")
    print("C7_SHARD_PASS",i,len(rows),flush=True)
def diagnostics(i):
    cc,manifest=get_cases()
    c=cc[i]
    OUT.mkdir(exist_ok=True)
    records=[]
    for mode in ("cadical_default","cadical_noelim","kissat_default"):
        cmd=external_cmd(mode,c["path"])
        # Separate stats-only run, excluded from PAR2 and bounded at 15s.
        args=cmd[:-1]+(["-v"] if mode.startswith("cadical") else ["--statistics"])+cmd[-1:]
        t=time.perf_counter()
        try:
            p=subprocess.run(args,capture_output=True,text=True,errors="replace",
                 timeout=15,check=False)
        except subprocess.TimeoutExpired:
            p=None
        lines=(p.stdout.splitlines() if p else [])
        stats=[l for l in lines if re.search(
           r"eliminat|conflicts|decisions|propagations|restarts|vivif|probing|reduction|subsum",
           l,re.I)]
        records.append(dict(mode=mode,gbd=c["gbd"],status="TIMEOUT" if p is None else
             "COMPLETED",returncode=None if p is None else p.returncode,
             wall_s=round(time.perf_counter()-t,6),
             selected_stat_lines=stats[-70:]))
    (OUT/("diagnostic-%d.json"%i)).write_text(json.dumps(records,indent=2)+"\n")
    print("C7_DIAGNOSTIC_SEPARATE_FROM_PAR2",json.dumps(
        [dict(mode=x["mode"],status=x["status"],line_count=len(x["selected_stat_lines"]))
         for x in records]),flush=True)
def audit():
    cc,manifest=get_cases()
    rows=[]
    for i in range(6):
        p=OUT/("shard-%d.json"%i)
        need(p.exists(),"missing shard "+str(i))
        part=json.loads(p.read_text())
        need(len(part)==REPS*len(MODES),"partial shard "+str(i))
        rows+=part
    need(len(rows)==6*REPS*len(MODES),"not 120 trials")
    bysha={x["sha256"]:x for x in cc}
    pairs=collections.defaultdict(dict)
    for x in rows:
        c=bysha.get(x["original_sha256"])
        need(c is not None and x["gbd"]==c["gbd"],"alien source SHA")
        need(x["protocol"]==PROTO and x["rep"] in range(REPS) and
             x["mode"] in MODES and x["seed"]==c6.seed(c,x["rep"]) and
             x["cap_s"]==CAP,"protocol or seed drift")
        need(x["status"] in ("SAT","UNSAT","TIMEOUT"),"invalid terminal status")
        if x["status"]!="TIMEOUT":
            need(x["status"]==c["expected_status"],"SAT UNSAT contradiction")
            need(abs(x["par2_s"]-x["wall_s"])<0.000002,
                 "solved PAR2 mismatch")
            if x["status"]=="SAT":need(x["original_SAT_witness_verified"],
                "SAT original-CNF witness not verified")
        else:
            need(x["par2_s"]==2*CAP and not x["original_SAT_witness_verified"],
                 "timeout incorrectly scored or certified")
        if x["mode"] in EXT_DEDUP:
            need(x["derived_sha256"]==
                 manifest["sources"][c["sha256"]]["derived_sha256"],
                 "external derived SHA mismatch")
        if x["mode"] in EXTERNAL:
            need(not x["independent_seed_applied"],"external seed was not pinned")
        key=(c["sha256"],x["rep"])
        need(x["mode"] not in pairs[key],"duplicate source-rep arm")
        pairs[key][x["mode"]]=x
    need(len(pairs)==6*REPS and all(set(p)==set(MODES) for p in pairs.values()),
         "paired ten-arm matrix incomplete")
    scores={}
    for mode in MODES:
        a=[x for x in rows if x["mode"]==mode]
        scores[mode]=dict(trials=len(a),
            solved=sum(x["status"]!="TIMEOUT" for x in a),
            SAT=sum(x["status"]=="SAT" for x in a),
            UNSAT_no_independent_LRAT=sum(x["status"]=="UNSAT" for x in a),
            timeouts=sum(x["status"]=="TIMEOUT" for x in a),
            PAR2_s=round(sum(x["par2_s"] for x in a),6),
            measured_wall_s=round(sum(x["wall_s"] for x in a),6),
            measured_external_prep_s=round(sum(x["prep_s"] for x in a),6))
    original=scores["cms_default"]["PAR2_s"]
    for mode in MODES:
        scores[mode]["speedup_vs_CMS_native_x"]=round(original/scores[mode]["PAR2_s"],5)
    per_source=[]
    for c in cc:
        groups={m:[x for x in rows if x["mode"]==m and x["original_sha256"]==c["sha256"]]
             for m in MODES}
        per_source.append(dict(gbd=c["gbd"],source_sha256=c["sha256"],
            original_status=c["expected_status"],
            duplicates_removed=manifest["sources"][c["sha256"]]["duplicates_removed"],
            source_control=c["control"],
            by_mode={m:dict(solved=sum(x["status"]!="TIMEOUT" for x in a),
                 PAR2_s=round(sum(x["par2_s"] for x in a),6),
                 individual_wall_s=[x["wall_s"] for x in sorted(a,key=lambda z:z["rep"])])
                 for m,a in groups.items()}))
    report=dict(protocol=PROTO,cohort="SIX PREVIOUSLY STUDIED original SHA DEVELOPMENT not blind",
        original_SHA6=[c["sha256"] for c in cc],solvers=
        {"CaDiCaL":"APT installed version recorded in artifact",
         "Kissat":"4.0.4 pinned SHA from original MRE11b binary artifact",
         "CryptoMiniSat":"pinned 5.11.15 C2/C6 native shared library"},
        external_solver_seed_not_independent=True,
        source_count=6,repetitions=REPS,cap_s=CAP,
        end_to_end_real_status=True,independent_UNSAT_LRAT=False,
        frozen_derived_cnf_SHA=True,
        external_dedup_prep_charged_in_every_trial=True,
        no_auto_promotion=True,
        paired_source_reps=len(pairs),trials=len(rows),
        scores=scores,per_source=per_source)
    OUT.mkdir(exist_ok=True)
    (OUT/"report.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print("C7_FINAL",json.dumps({k:v for k,v in report.items() if k!="per_source"},
                                 sort_keys=True),flush=True)
if __name__=="__main__":
    a=argparse.ArgumentParser()
    a.add_argument("action",choices=("freeze","verify","smoke","shard","diagnostics","audit"))
    a.add_argument("--shard",type=int,default=0)
    args=a.parse_args()
    if args.action=="freeze":freeze()
    elif args.action=="verify":
        c,m=get_cases()
        print("C7_ORIGINAL_AND_DERIVED_SHA6_PASS",len(c),flush=True)
    elif args.action=="smoke":smoke()
    elif args.action=="shard":shard(args.shard)
    elif args.action=="diagnostics":diagnostics(args.shard)
    else:audit()
