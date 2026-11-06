#!/usr/bin/env python3
"""R187: R186 low-cost source selector + R177 certified live GF2↔CDCL bridge.

Fixed development-only suite:
* 25 previously seen R154/R155 source-original GBD CNFs (R155 run 42112755104)
  of which 13 were solved by CryptoMiniSat under 15s in historical R155.
* 13 reference-calibrated *generated* R179 controls (9 validation, 4 sealed).
Both source sets were seen in past work; no claims of blind novelty.

Compare one clean CaDiCaL 2.1.0 solver and three selective GF2 strategies:
  clean, selective_gate, selective_feedback, selective_cooldown.
All start from same original SHA, randomized per pair, 15s END-TO-END wall cap,
2 paired repetitions, 8 shards. Independent SAT check on original source.
Source GF2 traces replayed. CaDiCaL UNSAT without GF2 source proof is not LRAT.
"""
from __future__ import annotations
import argparse, collections, hashlib, itertools, json, math, pathlib, random, re
import shutil, statistics, subprocess, time
import r182_mixed_engine as gf
import r183_external_mixed as ext
import r186_cheap_selector as r186

ROOT=pathlib.Path("r188")
R188_SOURCE_PROTO="DRNAS-R188-FEEDBACK-CLAUSE-EXPORT-CAUSAL-v1"
R188_SOURCE_SHA="3f0f67bea5547daa1ba07d9a1dba31d8d33f7d734db8eb6e8cae358a46c91ef3"
FROZEN=ROOT/"frozen"
CAP=15.0
REPS=2
SHARDS=8
MODES=("clean","selective_gate","selective_feedback64","selective_feedback_short8","selective_feedback_shadow8")
PROTO="DRNAS-R187-REAL25-SELECTIVE-LIVE-GF2-20261106-v1"
R155_SOURCE_MANIFEST_SHA="2fb130a7b8d8cb1c34d96cbf71932c11f4a5962e82422b8bd60d8f40ffce8f4a"
R179_SOURCE_PROTO="DRNAS-R179-MIXED-MEDIUM-SAT-UNSAT-REFERENCE-CALIBRATION-v1"

def need(ok,message):
    if not ok:raise RuntimeError("R188_FAIL_CLOSED "+str(message))
def sha(path):
    h=hashlib.sha256()
    with pathlib.Path(path).open("rb") as f:
        for a in iter(lambda:f.read(1024*1024),b""):h.update(a)
    return h.hexdigest()
def read(path):return json.loads(pathlib.Path(path).read_text())
def save(path,obj):
    path=pathlib.Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,sort_keys=True,indent=2)+"\n")

def freeze():
    src_real=ROOT/"prior_real"/"frozen"
    src_syn=ROOT/"prior_synthetic"/"r179"
    original=read(src_real/"manifest.json")
    need(sha(src_real/"manifest.json")==R155_SOURCE_MANIFEST_SHA,
         "R155 original 25 source manifest SHA changed")
    need(len(original["cases"])==25,"original R155 real 25 count changed")
    medium=read(src_syn/"r179-selected-freeze.json")
    need(medium["protocol"]==R179_SOURCE_PROTO and
         sha(src_syn/"frozen/manifest.json")==medium["source_manifest_sha256"],
         "R179 source checksum/protocol mismatch")
    controls=[c for c in medium["selected"] if c["split"] in
      ("validation","sealed_reference_calibrated_holdout")]
    need(len(controls)==13 and all(c["origin"]=="generated_tseitin_mixed"
                                   for c in controls),"R179 13 control sources drift")
    FROZEN.mkdir(parents=True,exist_ok=True)
    cases=[]
    for c in original["cases"]:
        src=src_real/(c["id"]+".cnf")
        need(sha(src)==c["sha256"],"R155 source original SHA drift")
        shutil.copyfile(src,FROZEN/(c["id"]+".cnf"))
        cases.append({"id":c["id"],"sha256":c["sha256"],"suite":"real_R154_R155_known",
            "family":c["cohort"],"expected":"UNKNOWN","real":True})
    for c in controls:
        src=src_syn/"frozen"/(c["id"]+".cnf")
        need(sha(src)==c["sha256"],"R179 control source drift")
        shutil.copyfile(src,FROZEN/(c["id"]+".cnf"))
        cases.append({"id":c["id"],"sha256":c["sha256"],
            "suite":"synthetic_R179_reference_calibrated_known",
            "family":"generated_tseitin_mixed","expected":c["class"],"real":False})
    cases.sort(key=lambda c:c["sha256"])
    need(len(cases)==38 and len(set(x["sha256"] for x in cases))==38,
         "source collisions")
    summary={"protocol":PROTO,"originals":25,"synthetic_controls":13,
      "cap_seconds":CAP,"repetitions":REPS,"R155_original_manifest_sha":R155_SOURCE_MANIFEST_SHA,
      "R179_selected_manifest_sha":sha(src_syn/"r179-selected-freeze.json"),
      "source_frozen_before_R188_trials":True,
      "not_new_blind_originals":True,"real_source_solved_historically_by_CryptoMiniSat":13,
      "history":"R155 13/25 CryptoMiniSat within 15s (not a current benchmark result)",
      "cases":cases}
    save(FROZEN/"manifest.json",summary)
    verify()
    print("R188_FREEZE_PASS",json.dumps({"cases":38,
      "real_known":25,"synthetic_known":13,
      "frozen_sha256":sha(FROZEN/"manifest.json")},sort_keys=True),flush=True)

def verify():
    m=read(FROZEN/"manifest.json")
    need(sha(FROZEN/"manifest.json")==R188_SOURCE_SHA,"source manifest changed")
    need(m["protocol"]==R188_SOURCE_PROTO and len(m["cases"])==38
      and m["originals"]==25 and m["synthetic_controls"]==13,"source manifest invalid")
    for c in m["cases"]:
        need(sha(FROZEN/(c["id"]+".cnf"))==c["sha256"],
             "original source SHA mismatch")
    return m["cases"]

def wide_shallow_gate(path):
    """R187 complementary width2..4 quartet screen if R186 early XOR3 missed.
    Original source only, bounded first 16k clauses. Neither SAT/UNSAT nor
    historical performance influences routing. Expensive work is charged.
    """
    start=time.perf_counter()
    with pathlib.Path(path).open(encoding="ascii") as f:
        for line in f:
            if line.startswith("p cnf "):
                z=line.split()
                need(len(z)==4,"DIMACS header malformed")
                n,m=int(z[2]),int(z[3]);break
        else:raise RuntimeError("missing header")
        if n<30 or m<100:return False,"small_cnf",time.perf_counter()-start
        groups=collections.defaultdict(set)
        found=set();scanned=0
        for line in f:
            if not line or line.startswith("c"):continue
            scanned+=1
            if scanned>16000:break
            clause=line.strip().split()
            if not 3<=len(clause)<=5 or clause[-1]!="0":continue
            try:lits=[int(x) for x in clause[:-1]]
            except ValueError:continue
            k=len(lits)
            if not 2<=k<=4 or len(set(abs(x) for x in lits))!=k:continue
            sorted_lits=sorted(lits,key=lambda z:abs(z))
            vars=tuple(abs(x) for x in sorted_lits)
            signs=sum(1<<i for i,v in enumerate(sorted_lits) if v<0)
            maskset=groups[vars]
            maskset.add(signs)
            if len(maskset)>1 and len(maskset)>=1<<(k-1):
                for parity in (0,1):
                    if all(a in maskset for a in range(1<<k)
                           if a.bit_count()%2==parity):
                        found.add(vars)
                        if len(found)>=2:
                            return (True,"r187_two_complete_xor_width2_4",
                                    time.perf_counter()-start)
        return False,"no_two_source_complete_xor_width2_4",time.perf_counter()-start

def route(path):
    started=time.perf_counter()
    selected,reason,_=r186.cheap_gate(path)
    if selected:
        return True,"r186_"+reason,time.perf_counter()-started
    wide,reason2,_=wide_shallow_gate(path)
    return wide,reason2,time.perf_counter()-started

def stats(raw):
    counts={}
    for key in ("conflicts","decisions","propagations","learned"):
        candidates=re.findall(r"(?:^|\n)\s*(?:c\s+)?"+key+r":\s+(\d+)\b",raw,re.M)
        counts[key]=int(candidates[-1]) if candidates else -1
    return counts

def telemetry(raw):
    m=re.search(r"^R166X_RESULT ([^\n]+)",raw,re.M)
    if not m:return {}
    return {k:int(v) for k,v in re.findall(
      r"\b(propagate_calls|feedback_clauses_consumed|feedback_candidates|feedback_shadow_admitted|feedback_rejected_width|feedback_rejected_budget|feedback_conflicts_detected|"
      r"direct_proposals|reason_clauses_completed|rows_scanned|watch_lookups|"
      r"backtracks|assignments)=(\d+)\b",m.group(1))}

def native(executable,args,limit,live):
    start=time.perf_counter()
    try:p=subprocess.run([str(executable.resolve())]+list(map(str,args)),
          capture_output=True,timeout=limit+4,check=False)
    except subprocess.TimeoutExpired:
        return "TIMEOUT",time.perf_counter()-start,{},{
          "conflicts":-1,"decisions":-1,"propagations":-1,"learned":-1},{}
    elapsed=time.perf_counter()-start
    raw=p.stdout.decode(errors="replace")
    err=p.stderr.decode(errors="replace")
    if live:
        need(p.returncode in (0,10,20),"live solver error "+err[-600:])
        m=re.search(r"^R166X_RESULT mode=\w+ status=(SAT|UNSAT|UNKNOWN)\b",raw,re.M)
    else:
        need(p.returncode==0,"clean solver error "+err[-600:])
        m=re.search(r"^R182_STATUS status=(SAT|UNSAT|TIMEOUT)\b",raw,re.M)
    need(m is not None,"native missing conclusive status "+err[-500:]+raw[-400:])
    status="TIMEOUT" if m[1] in ("UNKNOWN","TIMEOUT") else m[1]
    model={}
    if status=="SAT":
        for line in raw.splitlines():
            if line.startswith("v "):
                for v in map(int,line[2:].split()):
                    if v==0:continue
                    need(abs(v) not in model or model[abs(v)]==(v>0),
                         "inconsistent native SAT model")
                    model[abs(v)]=v>0
    return status,elapsed,model,stats(raw),telemetry(raw) if live else {}

def save_rows(path,rows,clauses):
    # bounded to native IPASIR-UP maximum 300 rows, deterministic and source-certified
    count=collections.Counter(abs(v) for c in clauses for v in c)
    chosen=sorted(rows,key=lambda r:(-sum(count[v] for v in r[0]),r[0],r[1]))[:300]
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text("".join(f"{len(vs)} {rhs} "+" ".join(map(str,vs))+"\n"
                     for vs,rhs,_ in chosen))
    return len(chosen)

def write_units(path,n,clauses,gauss,rows):
    unitlist=[]
    for var,(rhs,trace) in sorted(gauss["units"].items()):
        gf.check_trace(rows,1<<(var-1),rhs,trace)
        unitlist.append(var if rhs else -var)
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w") as f:
        f.write(f"p cnf {n} {len(clauses)+len(unitlist)}\n")
        for clause in clauses:f.write(" ".join(map(str,clause))+" 0\n")
        for unit in unitlist:f.write(str(unit)+" 0\n")
    return len(unitlist)

def trial(case,mode,rep,driver,live_bin):
    source=FROZEN/(case["id"]+".cnf")
    need(sha(source)==case["sha256"],"source mutated after freeze")
    started=time.perf_counter()
    use_live=False;certified=False;xor_rows=0;fed=0;injected=0
    selector_reason="baseline";select_s=0
    proof="NO_INDEPENDENT_UNSAT_LRAT";solverstats={
      "conflicts":-1,"decisions":-1,"propagations":-1,"learned":-1}
    bridge={}
    status="TIMEOUT";model={}
    input_path=source
    if mode!="clean":
        enabled,selector_reason,select_s=route(source)
        if enabled:
            n,clauses=gf.dimacs(source)
            rows,covered=ext.xor_source(clauses)
            xor_rows=len(rows)
            g=gf.gaussian(rows)
            if g["conflict"]:
                gf.check_trace(rows,0,1,g["conflict_trace"])
                status="UNSAT";certified=True
                proof="SOURCE_GF2_CONTRADICTION_REPLAYED"
            elif rows and mode in ("selective_feedback64","selective_feedback_short8","selective_feedback_shadow8"):
                tsv=ROOT/"scratch"/mode/(case["id"]+"-"+str(rep)+".tsv")
                fed=save_rows(tsv,rows,clauses)
                remaining=CAP-(time.perf_counter()-started)
                if remaining>1.2:
                    backend={"selective_feedback64":"direct_full_feedback",
                             "selective_feedback_short8":"direct_full_feedback_budget8",
                             "selective_feedback_shadow8":"direct_full_feedback_shadow8"}[mode]
                    status,_,model,solverstats,bridge=native(live_bin,
                      [backend,source,tsv,remaining],remaining,True)
                    use_live=True
            else:
                if rows and g["units"]:
                    dest=ROOT/"scratch"/mode/(case["id"]+"-"+str(rep)+".cnf")
                    injected=write_units(dest,n,clauses,g,rows)
                    input_path=dest
    # If no exact contradiction and native live wasn't invoked, use clean
    # CDCL as a conservative fallback; charge all source screening first.
    if not certified and not use_live:
        remaining=CAP-(time.perf_counter()-started)
        if remaining>0.15:
            status,_,model,solverstats,_=native(driver,[input_path,remaining],remaining,False)
    elapsed=time.perf_counter()-started
    if elapsed>=CAP:
        status="TIMEOUT";proof="CAP"
    if status=="SAT":
        _,original=gf.dimacs(source)
        gf.sat_check(original,model)
        proof="SAT_WITNESS_ORIGINAL_CNF_VERIFIED"
    if case["expected"]!="UNKNOWN" and status!="TIMEOUT":
        need(status==case["expected"],"expected source truth mismatch")
    return {"id":case["id"],"sha256":case["sha256"],"suite":case["suite"],
      "family":case["family"],"mode":mode,"rep":rep,
      "status":status,"elapsed_s":round(elapsed,6),
      "par2_s":round(2*CAP if status=="TIMEOUT" else elapsed,6),
      "proof":proof,"selected":mode!="clean" and selector_reason.startswith((
          "r186_two","r187_two")),
      "selector_reason":selector_reason,"selector_s":round(select_s,6),
      "xor_rows":xor_rows,"source_contradiction":certified,
      "injected_units":injected,"live_source_rows":fed,
      "live_invoked":use_live,"bridge":bridge,**solverstats}

def shard(index,driver,live_bin):
    cases=verify()
    need(0<=index<SHARDS,"invalid shard")
    records=[]
    for c in cases[index::SHARDS]:
        for rep in range(REPS):
            methods=list(MODES)
            random.Random(PROTO+c["sha256"]+str(rep)).shuffle(methods)
            for mode in methods:
                rec=trial(c,mode,rep,driver,live_bin)
                records.append(rec)
                save(ROOT/f"shard-{index}.json",records)
                print("R188_TRIAL",json.dumps({k:rec[k] for k in (
                     "id","suite","mode","rep","status","elapsed_s","selected",
                     "xor_rows","source_contradiction","live_invoked")},sort_keys=True),flush=True)
    need(len(records)==len(cases[index::SHARDS])*REPS*len(MODES),"shard partial")
    print("R188_SHARD_PASS",index,len(records),flush=True)

def audit():
    cases=verify()
    records=[]
    for index in range(SHARDS):records.extend(read(ROOT/f"shard-{index}.json"))
    need(len(records)==38*REPS*len(MODES)==380,"missing paired 380")
    known={c["sha256"]:c for c in cases}
    by=collections.defaultdict(list)
    for r in records:
        need(r["sha256"] in known and known[r["sha256"]]["id"]==r["id"],
             "unknown CNF in trial")
        by[r["sha256"],r["mode"]].append(r)
    for c in cases:
        for mode in MODES:
            rr=by[c["sha256"],mode]
            need(len(rr)==REPS and {x["rep"] for x in rr}=={0,1},
                 "paired source/repeat mismatch")
        for rep in range(REPS):
            answers={x["status"] for mode in MODES
                 for x in by[c["sha256"],mode] if x["rep"]==rep
                 and x["status"]!="TIMEOUT"}
            need(len(answers)<=1,"SAT/UNSAT disagreement")
    groups={
       "all":cases,
       "external_original_25":[c for c in cases if c["real"]],
       "synthetic_control_13":[c for c in cases if not c["real"]]}
    for fam in sorted(set(c["family"] for c in cases if c["real"])):
        groups["external:"+fam]=[c for c in cases if c["real"] and c["family"]==fam]
    results={}
    for name,subset in groups.items():
        md={}
        for mode in MODES:
            rr=[r for c in subset for r in by[c["sha256"],mode]]
            md[mode]={
              "attempts":len(rr),"solved":sum(r["status"]!="TIMEOUT" for r in rr),
              "sat":sum(r["status"]=="SAT" for r in rr),
              "unsat":sum(r["status"]=="UNSAT" for r in rr),
              "par2_s":round(sum(r["par2_s"] for r in rr),6),
              "live_invoked":sum(r["live_invoked"] for r in rr),
              "source_gf2_proofs":sum(r["source_contradiction"] for r in rr),
              "gate_selected":sum(r["selected"] for r in rr),
              "feedback_candidates":sum(r["bridge"].get("feedback_candidates",0) for r in rr),
              "feedback_shadow_admitted":sum(r["bridge"].get("feedback_shadow_admitted",0) for r in rr),
              "feedback_rejected_width":sum(r["bridge"].get("feedback_rejected_width",0) for r in rr),
              "feedback_rejected_budget":sum(r["bridge"].get("feedback_rejected_budget",0) for r in rr),
              "feedback_conflicts_detected":sum(r["bridge"].get("feedback_conflicts_detected",0) for r in rr),
              "delivered_feedback_clauses":sum(r["bridge"].get(
                                  "feedback_clauses_consumed",0) for r in rr),
              "external_propagation_calls":sum(r["bridge"].get(
                                  "propagate_calls",0) for r in rr),
              "conflicts_measured":sum(r["conflicts"]>=0 for r in rr),
              "total_conflicts_known":sum(max(0,r["conflicts"]) for r in rr)}
        clean=md["clean"]["par2_s"]
        results[name]={"cases":len(subset),"modes":md,
           "speed_vs_clean":{m:round(clean/md[m]["par2_s"],6) for m in MODES if m!="clean"}}
    report={
      "protocol":PROTO,"status":"R188_PAIRED_AUDIT_PASS",
      "cases":38,"external_originals":25,"synthetic_calibrated_controls":13,
      "attempts":len(records),"repetitions":REPS,"wall_cap_s":CAP,
      "R187_original_frozen_sources_SHA":R188_SOURCE_SHA,
      "experiment_target":"repair disabled feedback_clauses direct_full_feedback; full64 vs short8 vs shadow8",
      "source_frozen_before_R187":True,
      "known_reused_external_not_blind":True,"reference_crypto_solved_13_historical_R155":True,
      "no_unseen_world_record_claim":True,"CaDiCaL_UNSAT_no_independent_LRAT":True,
      "groups":results,
      "proof_counts":dict(collections.Counter(r["proof"] for r in records))}
    save(ROOT/"report.json",report);save(ROOT/"all-trials.json",records)
    with (ROOT/"summary.md").open("w") as f:
        f.write("# R187 — R186 source selector + verified live GF2/CDCL bridge\n\n"
           "25 previously seen R154/R155 genuine originals (CryptoMiniSat historically "
           "solved 13/25 at 15s); 13 reference-calibrated R179 synthetic controls. "
           "NOT blind. Same SHA, paired 2 repeats, 15-second end-to-end wall cap.\n\n")
        f.write("| Cohort | Mode | Solved/attempts | PAR2 s | clean / mode | Live calls | Consumed feedback |\n"
                "|---|---|---:|---:|---:|---:|---:|\n")
        for name,s in results.items():
            for m,measure in s["modes"].items():
                speed="—" if m=="clean" else str(s["speed_vs_clean"][m])+"×"
                f.write(f"|{name}|{m}|{measure['solved']}/{measure['attempts']}|"
                    f"{measure['par2_s']}|{speed}|{measure['external_propagation_calls']}|"
                    f"{measure['delivered_feedback_clauses']}|\n")
    print("R188_FINAL",json.dumps({
       "summary":{k:results[k] for k in ("all","external_original_25","synthetic_control_13")},
       "proof_counts":report["proof_counts"]},sort_keys=True),flush=True)

def selftest():
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        root=pathlib.Path(td)
        c=[]
        for a in range(8):
            if a.bit_count()%2==0:
                c.append(tuple(-v if a>>(v-1)&1 else v for v in (1,2,3)))
        for a in range(8):
            if a.bit_count()%2==1:
                c.append(tuple(-v if a>>(v-1)&1 else v for v in (1,2,3)))
        c.append((3,4))
        p=root/"mixed.cnf"
        p.write_text("p cnf 4 "+str(len(c))+"\n"+
          "".join(" ".join(map(str,cl))+" 0\n" for cl in c))
        n,clauses=gf.dimacs(p)
        rows,covered=ext.xor_source(clauses)
        g=gf.gaussian(rows)
        need(g["conflict"] and len(rows)==2 and len(covered)==8,
             "independent source XOR3 UNSAT contradiction missing")
        gf.check_trace(rows,0,1,g["conflict_trace"])
        # R187 source gate may abstain on small CNFs, must not misreport.
        selected,_,_=route(p)
        need(not selected,"too-small source erroneously routed")
    print("R188_SELFTEST_PASS",flush=True)

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("action",choices=("selftest","freeze","verify","shard","audit"))
    ap.add_argument("--shard",type=int,default=0)
    ap.add_argument("--driver",default="r187/r187-driver")
    ap.add_argument("--live",default="r187/r187-live")
    a=ap.parse_args()
    if a.action=="selftest":selftest()
    elif a.action=="freeze":freeze()
    elif a.action=="verify":print("R188_VERIFY_PASS",len(verify()),flush=True)
    elif a.action=="shard":shard(a.shard,pathlib.Path(a.driver),pathlib.Path(a.live))
    else:audit()
