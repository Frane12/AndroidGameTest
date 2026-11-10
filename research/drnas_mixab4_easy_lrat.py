#!/usr/bin/env python3
"""DRNAS MIXAB4: reference-screened easier 6 prospective originals, one CPU, externally verified LRAT.
A/B exact GF2 1.5s scanner versus 120ms bounded scanner; 12s CMS17/Kissat4
untouched baselines and routed variants; original SAT witness and original CNF
algebraic GF2 proof independently verified. Backend UNSAT requires reference
agreement for PAR2; no LRAT and no globally-blind claims.
"""
from __future__ import annotations
import argparse,collections,hashlib,json,os,pathlib,random,shutil,subprocess,tempfile,time
import drnas_gf2_proof_first_s1 as gf
import drnas_equiv9_prospective_seed_holdout as e9
import drnas_binary_scc2_e2e as s2

ROOT=pathlib.Path("mre_mixab4")
SOURCE=ROOT / "cases"
e9.SOURCE=SOURCE
SEARCH6=pathlib.Path("mre_search6")
SEARCH5=pathlib.Path("mre_search5")
CMS=pathlib.Path("mre_equiv12/bin/cryptominisat5")
PROTO="DRNAS-MIXAB4-REFERENCE-EASY6-6ARM-LRAT-GF2-CMS17-KISSAT4-1CPU-12S-v1"
ARMS=("kissat_plain","cms_plain","gf2_budget_kissat",
      "combo_full","combo_budget","combo_budget_placebo")
N=6
REPS=2
SHARDS=3
CAP=12.0
EXPECTED=N*len(ARMS)*REPS
XOR_ROUTE_MIN=16
# Cheap source geometry gate; avoid expensive scanning on very large inputs.
GATE_MAX_CLAUSES=65000
GATE_MAX_BYTES=6*1024*1024

def need(x,s):
    if not x:raise RuntimeError("MIXAB4_FAIL_CLOSED "+str(s))
def sha(p):return e9.digest(p)
def read(p):return json.loads(pathlib.Path(p).read_text())
def save(p,x):
    p=pathlib.Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(x,indent=2,sort_keys=True)+"\n")

# Source-lock: reference-only CaDiCaL screening BEFORE any DRNAS/CMS/Kissat
# scoring. Reference selection is openly biased and not globally blind.
YEARS=("2024","2025","2023","2022","2021")
SALT="MIXAB4-20261110-EASY-SCREEN-SHA-REFERENCE-CADICAL-ONLY"
SCREEN_CAP=4.0
MAX_CANDIDATES=240
MAX_SOURCE_BYTES=16*1024*1024
CHECKER=pathlib.Path("mre_mixab4/bin/lrat-check")
CADICAL=pathlib.Path("/usr/bin/cadical")
PRIOR_PATHS=(
 "mre_search5/manifest.json","mre_search6/manifest.json",
 "mre_equiv9/manifest.json","mre_equiv7/manifest.json",
 "mre_equiv10medium/manifest.json","mre_equiv10m5/manifest.json",
 "mre_x20/manifest.json","prior_x22/mre_x22/manifest.json",
 "prior_equiv6/mre_equiv6/manifest.json",
 "mre_mixab3/manifest.json",
)
def registry_snapshot():
    import re
    excluded_sha,excluded_ids=set(),set()
    checks={}
    def visit(v,key=""):
        if isinstance(v,dict):
            for k,z in v.items():visit(z,k.lower())
        elif isinstance(v,list):
            for z in v:visit(z,key)
        elif isinstance(v,str):
            if re.fullmatch("[0-9a-f]{64}",v) and key in ("sha256","original_sha256","sha","source_sha256"):
                excluded_sha.add(v)
            elif re.fullmatch("[0-9a-f]{32}",v) and key in ("gbd","gbd_id","gbdid"):
                excluded_ids.add(v)
    for path in PRIOR_PATHS:
        p=pathlib.Path(path)
        need(p.is_file(),"missing prior registry "+path)
        checks[path]=sha(p)
        obj=read(p)
        for key in ("cases","original_cases","original_SHA_sources",
                    "selected_cases","source_cases","holdout_cases","smoke_cases"):
            if key in obj:visit(obj[key])
    return excluded_sha,excluded_ids,checks

def roster():
    cs=read(ROOT/"manifest.json")["original_cases"]
    need(len(cs)==N and len({x["sha256"] for x in cs})==N
         and len({x["gbd"] for x in cs})==N,"original source roster drift")
    return sorted(cs,key=lambda x:x["sha256"])

def source(c):
    p=SOURCE/c["filename"]
    need(p.is_file() and sha(p)==c["sha256"],"original CNF SHA mismatch")
    return p

def signature():
    _,_,checks=registry_snapshot()
    return dict(code_sha=sha(__file__),
       cpp_source_sha=sha("research/drnas_gf2_proof_first_s1.cpp"),
       scanner_binary_sha=sha(gf.BIN),native_bin_sha=sha(e9.NATIVE),
       kissat_bin_sha=sha(e9.KISSAT),cms_bin_sha=sha(CMS),
       cadical_bin_sha=sha(CADICAL),independent_lrat_checker_bin_sha=sha(CHECKER),
       previous_registries=checks)

def lrat_check(cnf,proof,seconds=12):
    need(pathlib.Path(proof).is_file(),"LRAT proof absent")
    need(0<pathlib.Path(proof).stat().st_size<=16*1024*1024,"LRAT proof size cap")
    v=subprocess.run([str(CHECKER.resolve()),str(cnf.resolve()),str(proof.resolve())],
                     capture_output=True,text=True,timeout=seconds)
    return v.returncode==0 and "c VERIFIED" in v.stdout and "NOT VERIFIED" not in v.stdout

def reference_probe(p,seconds=SCREEN_CAP):
    import tempfile
    with tempfile.TemporaryDirectory(dir=ROOT) as td:
        proof=pathlib.Path(td)/"result.lrat"
        cmd=[str(CADICAL),"--lrat","--no-binary","--no-factor",
             str(p),str(proof)]
        try:
            r=subprocess.run(cmd,capture_output=True,text=True,timeout=seconds)
        except subprocess.TimeoutExpired:
            return dict(status="TIMEOUT",reason="reference_4s_timeout")
        if r.returncode not in (10,20):
            return dict(status="SKIP",reason="reference_solver_error",
                        returncode=r.returncode,stderr=r.stderr[-250:])
        n,clauses=e9.x22.read_cnf(p)
        if r.returncode==10:
            status,verified=e9.x22.solver_result("cadical",10,r.stdout,clauses,{})
            need(status=="SAT" and verified,"reference SAT invalid original model")
            return dict(status="SAT",reference_witness_verified=True)
        need("s UNSATISFIABLE" in r.stdout,"reference UNSAT status missing")
        if not lrat_check(p,proof,seconds=6):
            return dict(status="SKIP",reason="independent_lrat_verifier_rejected")
        return dict(status="UNSAT",lrat_bytes=proof.stat().st_size,
                    proof_raw=proof.read_bytes())

def freeze():
    import mre7_extended_easy_freeze as pool
    import mre7_reference_easy_freeze as fetch
    ROOT.mkdir(parents=True,exist_ok=True)
    SOURCE.mkdir(parents=True,exist_ok=True)
    (ROOT/"proofs").mkdir(parents=True,exist_ok=True)
    need(all(p.is_file() for p in (gf.BIN,e9.NATIVE,e9.KISSAT,CMS,CADICAL,CHECKER)),
         "missing pinned binaries/checker")
    excluded_sha,excluded_ids,_=registry_snapshot()
    choices=[]
    for yr in YEARS:
        allids,allsha=pool.getids("track=main_"+yr)
        mini,ms=pool.getids("track=main_"+yr+" and minisat1m=yes")
        need(len(allids)==400 and set(mini)<=set(allids),"official index drift")
        ranked=lambda g:hashlib.sha256((SALT+"|"+yr+"|"+g).encode()).hexdigest()
        choices.extend((0,ranked(g),yr,g) for g in mini if g not in excluded_ids)
        choices.extend((1,ranked(g),yr,g) for g in allids if g not in set(mini) and g not in excluded_ids)
    # MiniSat1m=yes has priority; order within each metadata tier by salted hash.
    choices.sort()
    selected=[];trace=[]
    for tier,rank,yr,gbd in choices:
        if len(selected)==N:break
        if len(trace)>=MAX_CANDIDATES:break
        if gbd in excluded_ids:continue
        p=SOURCE/(gbd+".cnf")
        reason=""
        rec=dict(year=yr,gbd=gbd,index_tier=tier)
        try:
            raw=fetch.get("https://benchmark-database.de/file/"+gbd,MAX_SOURCE_BYTES,seconds=18)
            plain,_=fetch.prior.r32p.decode(raw)
            need(0<len(plain)<=MAX_SOURCE_BYTES,"fixed source byte cap")
            n,k=fetch.prior.r32p.parse_dimacs_metadata(plain)
            need(0<n<=30000 and 0<k<=120000,"fixed source geometry")
            identity=hashlib.sha256(plain).hexdigest()
            need(identity not in excluded_sha,"duplicate prior original SHA")
            p.write_bytes(plain)
            n2,cls=e9.x22.read_cnf(p)
            need(n2==n and len(cls)==k,"DIMACS parse mismatch")
            probe=reference_probe(p)
            need(probe["status"] in ("SAT","UNSAT"),
                 "reference-only screen rejected: "+probe.get("reason",""))
            proof_file=None;proof_sha=None
            if probe["status"]=="UNSAT":
                proof_file=str(pathlib.Path("proofs")/(identity+".lrat"))
                output=ROOT/proof_file
                output.write_bytes(probe["proof_raw"])
                proof_sha=sha(output)
                need(lrat_check(p,output),"independent LRAT replay after freeze")
            selected.append(dict(year=yr,gbd=gbd,sha256=identity,
                filename=p.name,vars=n,clauses=k,bytes=len(plain),
                reference_screen_status=probe["status"],
                reference_screen_cap_s=SCREEN_CAP,
                independent_lrat_proof_file=proof_file,independent_lrat_sha256=proof_sha))
            excluded_sha.add(identity);excluded_ids.add(gbd)
            rec.update(action="selected_after_reference_only_screen",
                       sha256=identity,status=probe["status"],lrat=bool(proof_file))
        except Exception as e:
            p.unlink(missing_ok=True)
            rec.update(action="excluded_before_candidate_benchmark",why=str(e)[:180])
        trace.append(rec)
        print("MIXAB4_SOURCE "+json.dumps(rec,sort_keys=True),flush=True)
        save(ROOT/"selection-progress.json",dict(trace=trace,selected=len(selected)))
    need(len(selected)==N,"not enough reference-easy originals within fixed source budget")
    m=dict(protocol=PROTO,original_cases=sorted(selected,key=lambda c:c["sha256"]),
        source_count=N,arms=list(ARMS),reps=REPS,cap_s=CAP,shards=SHARDS,trials=EXPECTED,
        route_min_complete_XOR_equations=XOR_ROUTE_MIN,
        gate_max_clauses=GATE_MAX_CLAUSES,gate_max_bytes=GATE_MAX_BYTES,
        reference_screen_cadical_cap_s=SCREEN_CAP,
        reference_only_selection_biased=True,
        reference_screen_precedes_any_compared_arm=True,
        maximum_metadata_candidates=MAX_CANDIDATES,
        official_2021_25_minisat_metadata=True,
        globally_blind=False,new_to_loaded_registries=True,
        historical_global_exclusion_incomplete=True,
        one_logical_CPU=True,no_parallel_children=True,
        original_SHA_frozen_after_reference_screen_before_candidate_benchmark=True,
        external_original_LRAT_independently_checked=True,
        original_sat_model_required=True,no_auto_promotion=True,
        selection_salt=SALT,trace=trace,signatures=signature())
    save(ROOT/"manifest.json",m)
    verify()
    print("MIXAB4_FROZEN "+json.dumps(dict(sources=N,arms=len(ARMS),
        trials=EXPECTED,source_only=False,reference_easy=True,
        independent_lrat_sources=sum(bool(c["independent_lrat_proof_file"])
                                     for c in selected))),flush=True)

def verify():
    m=read(ROOT/"manifest.json")
    need(m["protocol"]==PROTO and m["source_count"]==N
         and m["original_cases"]==roster() and m["arms"]==list(ARMS)
         and m["reps"]==REPS and m["shards"]==SHARDS
         and m["cap_s"]==CAP and m["trials"]==EXPECTED
         and m["selection_salt"]==SALT
         and m["reference_screen_cadical_cap_s"]==SCREEN_CAP
         and m["route_min_complete_XOR_equations"]==XOR_ROUTE_MIN
         and m["gate_max_clauses"]==GATE_MAX_CLAUSES
         and m["gate_max_bytes"]==GATE_MAX_BYTES
         and m["signatures"]==signature(),"frozen protocol or binary drift")
    excluded_sha,excluded_ids,_=registry_snapshot()
    for c in m["original_cases"]:
        need(c["sha256"] not in excluded_sha and c["gbd"] not in excluded_ids,
             "historical registry overlap")
        src=source(c)
        if c["independent_lrat_proof_file"]:
            proof=ROOT/c["independent_lrat_proof_file"]
            need(sha(proof)==c["independent_lrat_sha256"],"proof SHA changed")
            need(lrat_check(src,proof),"independent original CNF LRAT replay failed")
        else:
            need(c["reference_screen_status"]=="SAT","reference screen missing cert")
    return m

def selftest():
    ROOT.mkdir(parents=True,exist_ok=True)
    need(gf.BIN.is_file() and CHECKER.is_file() and CADICAL.is_file(),
         "exact native scanner or independent LRAT checker absent")
    with tempfile.TemporaryDirectory() as td:
        q=pathlib.Path(td)/"unsat.cnf"
        q.write_text("p cnf 1 2\n1 0\n-1 0\n")
        test=reference_probe(q,seconds=3)
        need(test["status"]=="UNSAT","LRAT positive toy failed")
        bad=pathlib.Path(td)/"invalid.lrat"
        bad.write_text("1 0 0\n")
        need(not lrat_check(q,bad),"LRAT corrupt negative toy passed")
    with tempfile.TemporaryDirectory() as d:
        p=pathlib.Path(d)/"toy.cnf"
        for k in (2,3,4):
            clauses=[]
            for parity in (0,1):
                for mask in range(1<<k):
                    if mask.bit_count()%2==parity:
                        clauses.append([-(i+1) if mask&(1<<i) else i+1 for i in range(k)])
            for count,expected in ((len(clauses),True),(len(clauses)-1,False)):
                out=clauses[:count]
                p.write_text("p cnf %d %d\n"%(k,len(out))+
                    "".join(" ".join(map(str,line))+" 0\n" for line in out))
                r=gf.scan(p)
                need(r["proved"]==expected,"independent GF2 toy proof failure")
    print("MIXAB4_SELFTEST_PASS "+json.dumps(dict(
       complete_XOR_UNSAT=3,incomplete_SAT_negative=3,
       proof_checker="independent_original_CNF_replay_plus_external_LRAT",one_cpu=True)),flush=True)

def cms_trial(c,rep,cap):
    src=source(c)
    n,clauses=e9.x22.read_cnf(src)
    need(n>0 and len(clauses)>0,"CMS original CNF parse failed")
    cpu=min(os.sched_getaffinity(0))
    t=time.perf_counter()
    before=e9.x22.child_cpu()
    status="TIMEOUT";witness=False
    with tempfile.TemporaryDirectory(dir=ROOT) as temp:
        child=e9.x22.launch("cms",[str(CMS),"--verb","0","-t","1",str(src)],cpu,temp)
        try:
            while child["p"].poll() is None and time.perf_counter()-t < cap-0.018:
                time.sleep(.004)
            if child["p"].poll() is not None:
                stdout,stderr=e9.x22.read_output(child)
                status,witness=e9.x22.solver_result("cms",
                       child["p"].returncode,stdout,clauses,{})
        finally:e9.x22.cleanup([child])
    elapsed=time.perf_counter()-t
    if elapsed>=cap or status not in ("SAT","UNSAT"):
        status="TIMEOUT";witness=False
    need(status!="SAT" or witness,"CMS SAT original model NOT VERIFIED")
    return dict(status=status,SAT_original_witness_verified=bool(witness),
                wall_E2E_s=elapsed,child_CPU_s=e9.x22.child_cpu()-before)

def backend(c,rep,name,seconds):
    if seconds<=.08:return dict(status="TIMEOUT",SAT_original_witness_verified=False,
                              wall_E2E_s=0.0,child_CPU_s=0.0)
    if name=="native":
        return e9.trial(dict(c,cohort="holdout"),rep,"native1",cap=seconds)
    if name=="kissat":
        s2.ROOT.mkdir(parents=True,exist_ok=True)
        return s2.trial(dict(c,cohort="holdout"),rep,"kissat_orig",cap=seconds)
    need(name=="cms","unsupported backend")
    return cms_trial(c,rep,seconds)

def shape_gate(c):
    clauses=c.get("clauses",c.get("source_signals",c.get("original_source_signals",{})).get("clauses",0))
    need(clauses>0 and c["bytes"]>0,"source-only shape metadata unavailable")
    return clauses<=GATE_MAX_CLAUSES and c["bytes"]<=GATE_MAX_BYTES

def budget_scan(src):
    """A/B: same immutable C++ complete-XOR detector, but 120 ms scan cap.
    Timeout -> abstain and run untouched solver; no unsound shortcut.
    Any candidate UNSAT is independently checked on original CNF.
    """
    begin=time.perf_counter()
    try:
        r=subprocess.run([str(gf.BIN.resolve()),str(src.resolve())],
                         capture_output=True,text=True,timeout=0.120)
    except subprocess.TimeoutExpired:
        return dict(proved=False,abstained=True,
                    probe_wall_s=round(time.perf_counter()-begin,6),
                    reason="budgeted_120ms_timeout",proof=None,equations=0)
    if r.returncode!=0:
        return dict(proved=False,abstained=True,
                    probe_wall_s=round(time.perf_counter()-begin,6),
                    reason="budgeted_native_abstention",proof=None,equations=0)
    lines=[line[len("GF2_S1_RESULT "):] for line in r.stdout.splitlines()
           if line.startswith("GF2_S1_RESULT ")]
    need(len(lines)==1,"budget scanner missing C++ result")
    record=json.loads(lines[0])
    proof=gf.verify_algebraic_certificate(src,record) if record["xor_unsat"] else None
    return dict(proved=proof is not None,abstained=record["abstained"],
                probe_wall_s=round(time.perf_counter()-begin,6),
                reason="independent_GF2_proof" if proof else "no_exact_contradiction",
                proof=proof,equations=record["xor_equations"],
                scan_native_ms=record["scan_ms"])

def one(c,rep,arm):
    need(arm in ARMS and rep in (0,1),"invalid arm/rep")
    cpu=min(os.sched_getaffinity(0));os.sched_setaffinity(0,{cpu})
    started=time.perf_counter()
    cpu0=time.process_time();child0=e9.x22.child_cpu()
    src=source(c);state=None;called=False
    selected={"kissat_plain":"kissat","cms_plain":"cms",
              "gf2_full_kissat":"kissat","gf2_budget_kissat":"kissat"}.get(arm)
    do_scan=arm not in ("kissat_plain","cms_plain")
    gated=arm.startswith("combo_")
    if do_scan and (not gated or shape_gate(c)):
        state=gf.scan(src) if arm in ("gf2_full_kissat","combo_full") else budget_scan(src)
    eq=state["equations"] if state else 0
    if selected is None:
        selected="cms" if eq>=XOR_ROUTE_MIN else "kissat"
    certified=bool(state and state["proved"])
    # The placebo scans and routes exactly as budgeted COMBO, but cannot short-circuit.
    shortcut=certified and arm!="combo_budget_placebo"
    backend_status=None
    status="UNSAT" if shortcut else "TIMEOUT"
    witness=False
    if not shortcut:
        left=CAP-(time.perf_counter()-started)
        if left>.08:
            called=True
            r=backend(c,rep,selected,left)
            backend_status=r["status"]
            status=r["status"];witness=r["SAT_original_witness_verified"]
    wall=time.perf_counter()-started
    if wall>=CAP:
        status="TIMEOUT";witness=False
    need(status!="SAT" or witness,"non-original SAT witness")
    need(sha(src)==c["sha256"],"original CNF modified during trial")
    return dict(protocol=PROTO,sha256=c["sha256"],gbd=c["gbd"],
         rep=rep,arm=arm,cap_s=CAP,original_SHA_verified=True,
         pinned_logical_cpu=cpu,one_solver_child_max=True,
         status=status,SAT_original_witness_verified=bool(witness if status=="SAT" else False),
         UNSAT_independent_GF2_certificate_verified=bool(shortcut),
         UNSAT_exact_GF2_found=certified,
         UNSAT_independent_LRAT=False,certificate_terms=state["proof"]["terms"] if certified else 0,
         scan_abstained=state["abstained"] if state else False,
         scan_reason=state["reason"] if state else "geometry_gate_skip" if do_scan else "no_scan_baseline",
         xor_equations=eq,scan_E2E_s=state["probe_wall_s"] if state else 0.0,
         source_only_shape_gate=shape_gate(c),
         selected_backend=selected,backend_called=called,backend_status=backend_status,
         wall_E2E_s=round(wall,6),
         actual_child_CPU_s=round(e9.x22.child_cpu()-child0,6),
         actual_parent_CPU_s=round(time.process_time()-cpu0,6))

def shard(index):
    m=verify()
    need(index in range(SHARDS),"invalid shard")
    cs=[c for i,c in enumerate(m["original_cases"]) if i%SHARDS==index]
    rows=[]
    for c in cs:
        for rep in range(REPS):
            order=list(ARMS)
            random.Random(c["sha256"]+str(rep)+"MIXAB4-2026").shuffle(order)
            for arm in order:
                row=one(c,rep,arm);row["shard"]=index
                need(row["wall_E2E_s"]<=CAP+0.2,"wall budget exceeded")
                rows.append(row)
                save(ROOT/f"shard-{index}.json",rows)
                print("MIXAB4_TRIAL "+json.dumps(row,sort_keys=True),flush=True)
    need(len(rows)==len(cs)*REPS*len(ARMS),"missing paired observations")
    print(f"MIXAB4_SHARD_PASS {index} {len(rows)}",flush=True)

def audit():
    m=verify();rows=[]
    for i in range(SHARDS):
        rr=read(ROOT/f"shard-{i}.json")
        need(len(rr)==len([c for j,c in enumerate(m["original_cases"]) if j%SHARDS==i])
              *REPS*len(ARMS),"missing shard trial")
        rows+=rr
    keys={(c["sha256"],rep,arm) for c in m["original_cases"]
          for rep in range(REPS) for arm in ARMS}
    seen={(r["sha256"],r["rep"],r["arm"]) for r in rows}
    need(len(rows)==len(seen)==EXPECTED and seen==keys,"duplicate or missing trials")
    bysha=collections.defaultdict(list)
    for x in rows:
        need(x["protocol"]==PROTO and x["original_SHA_verified"] and
             x["one_solver_child_max"] and x["cap_s"]==CAP and
             x["status"] in ("SAT","UNSAT","TIMEOUT") and
             x["wall_E2E_s"]<=CAP+.2 and
             (x["status"]!="SAT" or x["SAT_original_witness_verified"]),
             "trial correctness failure")
        bysha[x["sha256"]].append(x)
    math={sha for sha,rr in bysha.items()
          if any(x["UNSAT_independent_GF2_certificate_verified"] for x in rr)}
    consensus={sha for sha,rr in bysha.items()
               if any(x["arm"]=="kissat_plain" and x["status"]=="UNSAT" for x in rr)
               and any(x["arm"]=="cms_plain" and x["status"]=="UNSAT" for x in rr)}
    lrat={c["sha256"] for c in m["original_cases"]
          if c["independent_lrat_proof_file"]}
    for sha,rr in bysha.items():
        need(len({x["status"] for x in rr if x["status"]!="TIMEOUT"})<=1,
             "different SAT and UNSAT on original source")
    def verified(x):
        return (x["status"]=="SAT" and x["SAT_original_witness_verified"]) or \
               (x["status"]=="UNSAT" and x["sha256"] in (math|lrat))
    def penalty(x):return x["wall_E2E_s"] if verified(x) else 2*CAP
    def score(rr):
        return dict(attempts=len(rr),solved=sum(verified(x) for x in rr),
          SAT_original_verified=sum(x["status"]=="SAT" and verified(x) for x in rr),
          UNSAT_proved_directly_this_arm=sum(x["status"]=="UNSAT" and x["UNSAT_independent_GF2_certificate_verified"] for x in rr),
          UNSAT_GF2_proof_exists_on_SHA=sum(x["status"]=="UNSAT" and x["sha256"] in math for x in rr),
          UNSAT_cross_solver_agreed_no_LRAT=sum(x["status"]=="UNSAT" and
                       x["sha256"] in consensus-math for x in rr),
          UNSAT_independent_LRAT=sum(x["status"]=="UNSAT" and x["sha256"] in lrat for x in rr),
          UNSAT_unverified=sum(x["status"]=="UNSAT" and not verified(x) for x in rr),
          timeouts=sum(x["status"]=="TIMEOUT" for x in rr),
          PAR2_s=round(sum(penalty(x) for x in rr),6),
          total_wall_s=round(sum(x["wall_E2E_s"] for x in rr),6),
          total_CPU_s=round(sum(x["actual_parent_CPU_s"]+x["actual_child_CPU_s"] for x in rr),6),
          scan_wall_s=round(sum(x["scan_E2E_s"] for x in rr),6),
          GF2_proof_repetitions=sum(x["UNSAT_exact_GF2_found"] for x in rr),
          scanner_abstentions=sum(x["scan_abstained"] for x in rr),
          route_to_CMS=sum(x["selected_backend"]=="cms" for x in rr))
    scores={arm:score([x for x in rows if x["arm"]==arm]) for arm in ARMS}
    for arm in ARMS:
        scores[arm]["speedup_vs_kissat_PAR2_x"]=round(
            scores["kissat_plain"]["PAR2_s"]/scores[arm]["PAR2_s"],6)
    paired={}
    for arm in ARMS:
        if arm=="kissat_plain":continue
        diff=[]
        for sha,rr in bysha.items():
            for rep in range(REPS):
                a=next(x for x in rr if x["rep"]==rep and x["arm"]==arm)
                b=next(x for x in rr if x["rep"]==rep and x["arm"]=="kissat_plain")
                diff.append(penalty(a)-penalty(b))
        paired[arm]=dict(wins=sum(d<-.02 for d in diff),
             losses=sum(d>.02 for d in diff),ties=sum(abs(d)<=.02 for d in diff),
             net_PAR2_gain_s=round(-sum(diff),6),
             largest_gain_s=round(min(diff),6),largest_regression_s=round(max(diff),6))
    def comparisons(a,b):
        diff=[penalty(next(x for x in rr if x["rep"]==rep and x["arm"]==a))
             -penalty(next(x for x in rr if x["rep"]==rep and x["arm"]==b))
             for sha,rr in bysha.items() for rep in range(REPS)]
        return dict(wins=sum(x<-.02 for x in diff),losses=sum(x>.02 for x in diff),
                    ties=sum(abs(x)<=.02 for x in diff),
                    net_PAR2_gain_s=round(-sum(diff),6),
                    best_gain_s=round(min(diff),6),worst_regression_s=round(max(diff),6))
    report=dict(protocol=PROTO,sources=N,trials=EXPECTED,
      source_only_prior_frozen_SHA_not_new=False,new_to_loaded_registries=True,globally_blind=False,
      strict_original_SAT_witness=True,independent_GF2_math_proof_NOT_LRAT=True,
      no_independent_LRAT_for_backend_UNSAT=False,reference_only_selection_biased=True,
      independent_LRAT_checked_sources=sorted(lrat),no_auto_promotion=True,
      one_logical_cpu=True,no_parallel_portfolio=True,
      math_certified_originals=sorted(math),backend_UNSAT_agreement_diagnostic_only=sorted(consensus-math),
      scores=scores,paired=paired,
      paired_vs_CMS={a:comparisons(a,'cms_plain') for a in ARMS if a!='cms_plain'},
      causal_GF2_budget_vs_placebo=comparisons('combo_budget','combo_budget_placebo'),
      long_vs_budget=comparisons('combo_budget','combo_full'),
      per_shard={str(i):{a:score([x for x in rows if x["shard"]==i and x["arm"]==a])
         for a in ARMS} for i in range(SHARDS)},
      per_SHA={sha:{a:[dict(rep=x["rep"],status=x["status"],E2E_s=x["wall_E2E_s"],
                    XOR=x["xor_equations"],route=x["selected_backend"],
                    proof=x["UNSAT_independent_GF2_certificate_verified"])
                    for x in rr if x["arm"]==a] for a in ARMS} for sha,rr in bysha.items()})
    save(ROOT/"report.json",report)
    print("MIXAB4_FINAL "+json.dumps({k:v for k,v in report.items() if k not in ("per_SHA",)},sort_keys=True),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("selftest","freeze","verify","shard","audit"))
    p.add_argument("--shard",type=int,default=0)
    a=p.parse_args()
    if a.action=="shard":shard(a.shard)
    else:
        globals()[a.action]()
        if a.action=="verify":print("MIXAB4_VERIFY_PASS",flush=True)
