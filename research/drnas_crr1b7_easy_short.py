#!/usr/bin/env python3
"""CRR1-B7: SHORT full-solve benchmark on two genuinely easier W4 originals
plus two clearly separated deterministic synthetic XOR sanity controls.

Originals were previously solved with independent SAT-model / UNSAT DRAT checks.
Synthetic controls are not SAT competition instances and never contribute to
an "official SAT2026 speedup" claim.

Kissat plain, B3L8 and B5multi8 share the pinned Kissat backend. Original
source SHA and GF2 reason replay are checked for every appended clause.
All native 6s attempt times include preparation. Proof checking is done
after stopping each attempt timer; proof check time is reported separately.
An unverified or timed-out answer is penalized by PAR2 and is never solved.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import random
import re
import signal
import statistics
import subprocess
import sys
import time

import drnas_crr1a_shadow as a
import drnas_crr1b_active as b
import drnas_crr1b5_discrimination as b5
import drnas_crr1b6_conflict_profile as parent

ROOT=Path("crr1b7")
SOURCE=a.SOURCE
PROTO="DRNAS-CRR1B7-EASY-W4-2-PLUS-XOR-CONTROLS-2-3ARMS-3REPS-6S-v1"
CAP=6.0
REPS=3
SHARDS=4
MODES=("kissat_plain","b3_loose8","b5_multi8")
OFFICIAL=(
 ("2fcd8533eba981967292f1b6e41f7433","fdae904ea92d7ec0c8c53d82ce826395c69826bfc00419e4e21bb72d80ce434b","SAT"),
 ("12cd0c3196589ac8105653cbfe613fc6","a6413aa01392e6e8e14fde6162e67d5c613df4962b27430fdf93187dc6d45624","UNSAT"),
)
SYNTH=("xor_control_sat","xor_control_unsat")

def need(ok,msg):
    if not ok:raise RuntimeError("CRR1B7_FAIL_CLOSED "+msg)

def save(path,obj):a.save(path,obj)

def original_cases():
    m={c["id"]:c for c in a.manifest_cases()}
    cc=[]
    for ident,sha,outcome in OFFICIAL:
        need(ident in m and m[ident]["sha256"]==sha,
             "historical W4 original SHA mismatch")
        cc.append({"id":ident,"sha256":sha,"cohort":"original_SAT2026_W4",
                   "historically_verified":outcome,"path":str(SOURCE/(ident+".cnf"))})
    return cc

def synthetic_clauses(kind):
    need(kind in SYNTH,"unknown synthetic control type")
    model={}
    rows=[]
    # Distinct shared-pair XOR triples make GF2-derived binary candidates:
    # XOR(u,v,w)=0 and XOR(u,v,z)=i%2, thus XOR(w,z)=i%2.
    for i in range(18):
        u=4*i+1;v=u+1;w=u+2;z=u+3
        bit=i%2
        uv=((i*7+1)%2,(i//2)%2)
        val_w=uv[0]^uv[1];val_z=val_w^bit
        model.update({u:bool(uv[0]),v:bool(uv[1]),
                      w:bool(val_w),z:bool(val_z)})
        rows.extend(a.fixture_xor((u,v,w),0))
        rows.extend(a.fixture_xor((u,v,z),bit))
    rng=random.Random(20261108)
    variables=list(model)
    # Planted satisfiable ternary clauses connect XOR blocks.
    for _ in range(75):
        vs=rng.sample(variables,3)
        lits=[v if rng.getrandbits(1) else -v for v in vs]
        if not any(model[abs(l)]==(l>0) for l in lits):
            lits[0]=-lits[0]
        need(any(model[abs(l)]==(l>0) for l in lits),"planted clause invalid")
        rows.append(tuple(lits))
    if kind=="xor_control_sat":
        for i in range(5):
            v=4*(i*3)+1
            rows.append((v if model[v] else -v,))
    else:
        # Two root literals conflict with GF2 consequence w0 XOR z0 = 0?
        # For i=1, XOR(w,z)=1, so forcing both equal is unsatisfiable.
        w=4*1+3; z=w+1
        need(model[w]!=model[z],"UNSAT fixture parity was not unequal")
        rows.append((w,))
        rows.append((z,))
    return 72,rows

def write_synthetic(path,kind):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    n,rows=synthetic_clauses(kind)
    with path.open("w") as f:
        f.write("p cnf %d %d\n"%(n,len(rows)))
        for row in rows:f.write(" ".join(map(str,row))+" 0\n")
    a.parse(path)
    return a.sha(path)

def cases_from_manifest():
    m=json.loads((ROOT/"manifest.json").read_text())
    return m["cases"]

def verify():
    m=json.loads((ROOT/"manifest.json").read_text())
    need(m["protocol"]==PROTO and m["reps"]==REPS
         and m["cap_s"]==CAP and m["modes"]==list(MODES)
         and len(m["cases"])==SHARDS and
         m["w4_manifest_sha256"]==a.sha("history/w4sources/manifest.json"),
         "protocol/manifest mismatch")
    originals=original_cases()
    need([x["sha256"] for x in m["cases"][:2]]==
         [x["sha256"] for x in originals],
         "official SHA mismatch")
    for p,d in json.loads((ROOT/"pins.json").read_text()).items():
        need(a.sha(p)==d,"script/workflow checksum drift "+p)
    for c in m["cases"]:
        need(a.sha(c["path"])==c["sha256"],"formula byte SHA drift "+c["id"])
    return m["cases"]

def selftest():
    b5.selftest()
    for kind in SYNTH:
        n,clauses=synthetic_clauses(kind)
        need(n==72 and len(clauses)>150,"generated control malformed")
        # B2/B5 proof construction is replayed against original CNF later.
        derived,cert,details=parent.b2.make_bridge(n,clauses)
        if derived:
            need(b.certify_added(clauses,cert)==set(derived),
                 "control GF2 certificate invalid")
        if kind=="xor_control_sat":
            # Direct model satisfying all planted XOR blocks and links.
            # SAT actually independently checked by native solver later.
            need(details["complete_xor_equations"]>0,
                 "SAT control has no detected XOR structure")
        else:
            need(details["complete_xor_equations"]>0,
                 "UNSAT control has no detected XOR structure")
    print("CRR1B7_SELFTEST_PASS",flush=True)

def prepare():
    selftest()
    need(a.KISSAT.is_file() and a.CHECKER.is_file(),"pinned tools missing")
    originals=original_cases()
    for c in originals:
        need(a.sha(c["path"])==c["sha256"],"frozen easy original changed")
    cc=list(originals)
    for kind in SYNTH:
        path=str(ROOT/"sources"/(kind+".cnf"))
        sha=write_synthetic(path,kind)
        cc.append({"id":kind,"sha256":sha,"cohort":"synthetic_XOR_control",
                   "historically_verified":"TEST_ONLY","path":path})
    meta={"protocol":PROTO,"cases":cc,"reps":REPS,"shards":SHARDS,
          "modes":list(MODES),"cap_s":CAP,
          "w4_manifest_sha256":a.sha("history/w4sources/manifest.json"),
          "originals_prior_history":{"SAT":"0.051-0.053 seconds",
                                      "UNSAT":"2.459-2.566 seconds"},
          "originals_posthoc_development":True,
          "synthetic_controls_not_official":True,
          "proof_policy":"SAT original witness, UNSAT augmented DRAT, GF2 replay",
          "promotion_allowed":False,"source_selection_blind":False,
          "B5_selection_seed":101,
          "native_solve_only_no_conflict_cap":True,
          "no_saved_native_proofs":True}
    save(ROOT/"manifest.json",meta)
    pinned=["research/drnas_crr1b7_easy_short.py",
            "research/drnas_crr1b6_conflict_profile.py",
            "research/drnas_crr1b5_discrimination.py",
            "research/drnas_crr1b4_value.py",
            "research/drnas_crr1b3loose.py",
            "research/drnas_crr1b2_telemetry.py",
            "research/drnas_crr1b_active.py",
            "research/drnas_crr1a_shadow.py",
            ".github/workflows/drnas-crr1b7-easy-short.yml",
            "history/w4sources/manifest.json",
            "crr1b7/manifest.json"]
    save(ROOT/"pins.json",{p:a.sha(p) for p in pinned})
    verify()
    print("CRR1B7_PREP_PASS",a.sha(ROOT/"manifest.json"),flush=True)

def worker(source,mode,folder):
    folder=Path(folder)
    start=time.perf_counter()
    n,original=a.parse(source)
    picked,cert,meta=parent.select_input(n,original,mode)
    need(len(picked)==len(cert),"selection certificate count")
    if picked:
        need(b.certify_added(original,cert)==set(picked),
             "original-GF2 certification failure")
    target=Path(source)
    if picked:
        target=folder/"augmented.cnf"
        with target.open("w") as out:
            out.write("p cnf %d %d\n"%(n,len(original)+len(picked)))
            for c in original:
                out.write(" ".join(map(str,c))+" 0\n")
            for c in picked:
                out.write(" ".join(map(str,c))+" 0\n")
        save(folder/"certificates.json",cert)
    ready={"source_sha256":a.sha(source),"target_sha256":a.sha(target),
           "selected_clauses":[list(c) for c in picked],"mode":mode,
           "prep_s":round(time.perf_counter()-start,6),"selector":meta}
    save(folder/"telemetry.json",ready)
    print("CRR1B7_READY",json.dumps({k:v for k,v in ready.items()
             if k!="selected_clauses"},sort_keys=True),flush=True)
    proof=folder/"native.drat"
    t=time.perf_counter()
    p=subprocess.run([str(a.KISSAT.resolve()),"--statistics",
              str(target.resolve()),str(proof.resolve())],
              stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    solve_s=time.perf_counter()-t
    matches=re.findall(r"(?m)^s (SATISFIABLE|UNSATISFIABLE)\s*$",p.stdout)
    need(len(matches)==1,"Kissat no unique terminal SAT/UNSAT")
    sat=(matches[0]=="SATISFIABLE")
    need(p.returncode==(10 if sat else 20),"Kissat incorrect status code")
    if sat:save(folder/"model.json",parent.witness(p.stdout,original,picked))
    native=parent.native_statistics(p.stdout)
    (folder/"native.log").write_text(p.stdout[-3000:])
    terminal={"status":"SAT" if sat else "UNSAT","solve_s":round(solve_s,6),
              "stats":native,"source_sha256":a.sha(source),
              "target_sha256":a.sha(target)}
    save(folder/"terminal.json",terminal)
    print("CRR1B7_TERMINAL",json.dumps(terminal,sort_keys=True),flush=True)

def verify_native_input(source,folder,ready):
    need(ready["source_sha256"]==a.sha(source),"source SHA changed")
    chosen=[tuple(c) for c in ready["selected_clauses"]]
    if not chosen:
        need(ready["target_sha256"]==a.sha(source),"plain original mutated")
        return source
    augmented=folder/"augmented.cnf"
    n,original=a.parse(source)
    nn,all_clauses=a.parse(augmented)
    proofs=json.loads((folder/"certificates.json").read_text())
    need(n==nn and all_clauses[:len(original)]==original
         and all_clauses[len(original):]==chosen
         and b.certify_added(original,proofs)==set(chosen),
         "augmented proof/source drift")
    need(ready["target_sha256"]==a.sha(augmented),"target byte SHA drift")
    return augmented

def trial(c,mode,rep,shard):
    source=Path(c["path"])
    need(a.sha(source)==c["sha256"],"original source SHA mismatch")
    folder=ROOT/"raw"/str(shard)/(c["id"]+"-"+mode+"-rep"+str(rep))
    folder.mkdir(parents=True,exist_ok=True)
    t=time.perf_counter()
    p=subprocess.Popen([sys.executable,__file__,"worker",
              "--source",str(source),"--mode",mode,"--directory",str(folder)],
              stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
              text=True,start_new_session=True)
    timedout=False
    try:out,_=p.communicate(timeout=max(.001,CAP-(time.perf_counter()-t)))
    except subprocess.TimeoutExpired:
        timedout=True
        try:os.killpg(p.pid,signal.SIGKILL)
        except ProcessLookupError:pass
        out,_=p.communicate()
    elapsed=min(CAP,time.perf_counter()-t)
    ready_file=folder/"telemetry.json"
    term_file=folder/"terminal.json"
    ready=json.loads(ready_file.read_text()) if ready_file.exists() else None
    term=json.loads(term_file.read_text()) if term_file.exists() else None
    status="TIMEOUT";evidence="WALL_CAP_TIMEOUT"
    if ready:
        need(ready["mode"]==mode and ready["source_sha256"]==c["sha256"],
             "invalid persisted metadata")
        native_input=verify_native_input(source,folder,ready)
    else:native_input=source
    proof_check_s=None
    if not timedout:
        need(p.returncode==0 and ready is not None and term is not None,
             "worker crashed: "+out[-1500:])
        need(term["source_sha256"]==c["sha256"] and
             term["target_sha256"]==ready["target_sha256"],
             "native terminal file mismatched")
        if term["status"]=="SAT":
            model={int(k):v for k,v in json.loads(
                  (folder/"model.json").read_text()).items()}
            _,original=a.parse(source)
            need(all(any(model.get(abs(v))==(v>0) for v in clause)
                 for clause in original),"SAT model original recheck")
            status="SAT";evidence="SAT_ORIGINAL_MODEL_VERIFIED"
        elif term["status"]=="UNSAT":
            proof=folder/"native.drat"
            t0=time.perf_counter()
            if proof.is_file() and proof.stat().st_size>0:
                try:
                    result=subprocess.run([str(a.CHECKER.resolve()),
                        str(native_input.resolve()),str(proof.resolve())],
                        stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                        text=True,timeout=40)
                    if result.returncode==0 and "s VERIFIED" in result.stdout:
                        status="UNSAT"
                        evidence="UNSAT_AUGMENTED_DRAT_AND_SOURCE_GF2_VERIFIED"
                    else:evidence="UNSAT_PROOF_INVALID_NOT_SCORED"
                except subprocess.TimeoutExpired:
                    evidence="UNSAT_PROOF_TIMEOUT_NOT_SCORED"
            else:evidence="UNSAT_PROOF_MISSING_NOT_SCORED"
            proof_check_s=round(time.perf_counter()-t0,6)
        else:need(False,"invalid native result")
    for name in ("augmented.cnf","certificates.json","model.json",
                 "native.drat","native.log","terminal.json"):
        path=folder/name
        if path.exists():path.unlink()
    solved=status in ("SAT","UNSAT")
    row={"protocol":PROTO,"id":c["id"],"sha256":c["sha256"],
        "cohort":c["cohort"],"mode":mode,"rep":rep,"shard":shard,
        "status":status,"proof":evidence,
        "elapsed_s":round(elapsed,6),
        "par2_s":round(elapsed if solved else 2*CAP,6),
        "prep_s":ready["prep_s"] if ready else None,
        "native_s":term["solve_s"] if term else None,
        "added":len(ready["selected_clauses"]) if ready else None,
        "selected_clauses":ready["selected_clauses"] if ready else None,
        "selector":ready["selector"] if ready else None,
        "native":term["stats"] if term else None,
        "proof_check_s":proof_check_s}
    print("CRR1B7_TRIAL",json.dumps({k:v for k,v in row.items()
       if k!="selected_clauses"},sort_keys=True),flush=True)
    return row

def shard(index):
    cc=verify()
    need(0<=index<SHARDS,"invalid shard")
    if hasattr(os,"sched_getaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    c=cc[index]
    rows=[]
    for rep in range(REPS):
        modes=list(MODES)
        random.Random(PROTO+c["sha256"]+str(rep)).shuffle(modes)
        for mode in modes:
            row=trial(c,mode,rep,index)
            rows.append(row)
            save(ROOT/("shard-%d.json"%index),rows)
    need(len(rows)==REPS*len(MODES),"incomplete short shard")
    print("CRR1B7_SHARD_PASS",index,len(rows),flush=True)

def audit():
    cc=verify()
    rows=[];seen=set()
    for index,c in enumerate(cc):
        group=json.loads((ROOT/("shard-%d.json"%index)).read_text())
        need(len(group)==REPS*len(MODES),"missing trials")
        for r in group:
            key=(r["sha256"],r["rep"],r["mode"])
            need(key not in seen and r["protocol"]==PROTO and
                 r["sha256"]==c["sha256"] and r["id"]==c["id"] and
                 r["cohort"]==c["cohort"] and r["rep"] in range(REPS) and
                 r["mode"] in MODES and r["shard"]==index,
                 "attempt provenance incorrect")
            seen.add(key)
            need(r["status"] in ("SAT","UNSAT","TIMEOUT") and
                 abs(r["par2_s"]-(r["elapsed_s"]
                   if r["status"] in ("SAT","UNSAT") else 2*CAP))<0.00001,
                 "PAR2 status invalid")
            need(r["status"]!="SAT" or
                 r["proof"]=="SAT_ORIGINAL_MODEL_VERIFIED",
                 "unverified SAT improperly scored")
            need(r["status"]!="UNSAT" or
                 r["proof"]=="UNSAT_AUGMENTED_DRAT_AND_SOURCE_GF2_VERIFIED",
                 "unverified UNSAT improperly scored")
            rows.append(r)
    expected={(c["sha256"],rep,mode) for c in cc
             for rep in range(REPS) for mode in MODES}
    need(seen==expected and len(rows)==SHARDS*REPS*len(MODES),
         "short benchmark not completely paired")
    for c in cc:
        outcomes={r["status"] for r in rows if r["id"]==c["id"] and
                  r["status"]!="TIMEOUT"}
        need(len(outcomes)<=1,"contradictory verified source verdict")
        if c["cohort"]=="original_SAT2026_W4" and outcomes:
            need(next(iter(outcomes))==c["historically_verified"],
                 "historically verified original contradicts current verdict")
    per_case=[]
    for c in cc:
        subset=[r for r in rows if r["id"]==c["id"]]
        by={}
        for mode in MODES:
            x=[r for r in subset if r["mode"]==mode]
            by[mode]={"attempts":len(x),"solved":sum(r["status"]!="TIMEOUT" for r in x),
               "SAT":sum(r["status"]=="SAT" for r in x),
               "UNSAT_verified":sum(r["status"]=="UNSAT" for r in x),
               "PAR2_s":round(sum(r["par2_s"] for r in x),6),
               "median_wall_s":round(statistics.median(r["elapsed_s"] for r in x),6),
               "median_prep_s":round(statistics.median(r["prep_s"] for r in x
                                  if r["prep_s"] is not None),6)
                         if any(r["prep_s"] is not None for r in x) else None,
               "added":sorted({r["added"] for r in x if r["added"] is not None}),
               "native":[r["native"] for r in x],
               "statuses":[r["status"] for r in x]}
        per_case.append({"id":c["id"],"cohort":c["cohort"],
              "expected":c["historically_verified"],"modes":by})
    by_cohort={}
    for cohort in ("original_SAT2026_W4","synthetic_XOR_control"):
        group=[r for r in rows if r["cohort"]==cohort]
        metrics={}
        for mode in MODES:
            s=[r for r in group if r["mode"]==mode]
            metrics[mode]={"attempts":len(s),
               "solved":sum(r["status"] in ("SAT","UNSAT") for r in s),
               "PAR2_s":round(sum(r["par2_s"] for r in s),6),
               "total_wall_s":round(sum(r["elapsed_s"] for r in s),6)}
        by_cohort[cohort]=metrics
    paired=[]
    for cohort in by_cohort:
        for comparator in ("kissat_plain","b3_loose8"):
            ratios=[]
            for c in cc:
                if c["cohort"]!=cohort:continue
                for rep in range(REPS):
                    ba=next(r for r in rows if r["id"]==c["id"] and
                            r["rep"]==rep and r["mode"]==comparator)
                    v=next(r for r in rows if r["id"]==c["id"] and
                            r["rep"]==rep and r["mode"]=="b5_multi8")
                    if (ba["status"] in ("SAT","UNSAT") and
                        v["status"] in ("SAT","UNSAT")):
                        ratios.append(ba["elapsed_s"]/v["elapsed_s"])
            gm=math.exp(sum(math.log(v) for v in ratios)/len(ratios)) if ratios else None
            paired.append({"cohort":cohort,"comparator":comparator,
                "valid_solved_pairs":len(ratios),
                "geomean_wall_speedup_b5":round(gm,6) if gm is not None else None})
    report={"status":"CRR1B7_AUDIT_PASS","protocol":PROTO,
       "attempts":len(rows),"formulas":len(cc),"cap_s":CAP,"reps":REPS,
       "by_formula":per_case,"by_cohort":by_cohort,"paired":paired,
       "synthetic_separated_from_official":True,
       "official_not_blind_posthoc":True,"promotion_allowed":False,
       "proof_gated":True}
    save(ROOT/"report.json",report)
    save(ROOT/"all-trials.json",rows)
    print("CRR1B7_FINAL",json.dumps(report,sort_keys=True),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("selftest","prepare","worker","shard","audit"))
    p.add_argument("--source");p.add_argument("--mode")
    p.add_argument("--directory");p.add_argument("--shard",type=int,default=0)
    opt=p.parse_args()
    if opt.action=="worker":
        need(opt.mode in MODES,"bad worker mode")
        worker(opt.source,opt.mode,opt.directory)
    elif opt.action=="shard":shard(opt.shard)
    else:globals()[opt.action]()
