#!/usr/bin/env python3
"""R185: four independently benchmarked, mathematically distinct SAT strategies.

Methods: gf2_gate, gf2_short4, live_feedback, live_cooldown.
All share ONE frozen suite: 12 source-pinned external GBD originals from R183
(known to us from R183/R184; not blind) + 13 previously calibrated *synthetic*
R179 validation/sealed instances, labeled explicitly development-only.
Two same-SHA repeats at a uniform 25-second wall cap per attempted solve.
Each method has its OWN paired clean CaDiCaL arm on the same runner.
Do not assert a fastest external solver if all are censored at cap.
"""
from __future__ import annotations
import argparse,collections,hashlib,itertools,json,math,os,pathlib,random,re,shutil,statistics,subprocess,time
import r182_mixed_engine as gf
import r184_external_mixed_120s as old

ROOT=pathlib.Path("r185")
FROZEN=ROOT/"frozen"
SOURCE_EXTERNAL=ROOT/"source_external"/"frozen"
SOURCE_SYNTH=ROOT/"source_synthetic"/"r179"
CAP=25.0
REPS=2
SHARDS=6
METHODS=("gf2_gate","gf2_short4","live_feedback","live_cooldown")
PROTOCOL="DRNAS-R185-FOUR-INDEPENDENT-METHODS-FROZEN-SHA-v1"
EXTERNAL_MANIFEST_SHA="102c8bdef78163aad8e08ab044c0ff7a123df4d67b0a714c50370b13447543c4"
CADICAL_COMMIT="31f9aae44947c673dc6190c9beb399acb9ffec6a"

def need(flag,message):
    if not flag:raise RuntimeError("R185_FAIL_CLOSED "+str(message))
def sha(path):
    h=hashlib.sha256()
    with pathlib.Path(path).open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""):h.update(b)
    return h.hexdigest()
def save(path,data):
    p=pathlib.Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(data,sort_keys=True,indent=2)+"\n")
def load(path):return json.loads(pathlib.Path(path).read_text())

def freeze():
    src_ext=ROOT/"source_external"
    src_syn=SOURCE_SYNTH
    external=load(src_ext/"frozen/manifest.json")
    need(sha(src_ext/"frozen/manifest.json")==EXTERNAL_MANIFEST_SHA,
        "must reuse exactly R183 source identities, not reselect")
    need(external["protocol"]=="DRNAS-R183-EXTERNAL-SHA-FROZEN-MIXED-v1" and
         len(external["cases"])==12,"R183 original suite mismatch")
    synthetic=load(src_syn/"r179-selected-freeze.json")
    need(synthetic["protocol"]==
        "DRNAS-R179-MIXED-MEDIUM-SAT-UNSAT-REFERENCE-CALIBRATION-v1",
        "R179 calibrated selected synthetic protocol mismatch")
    test=[c for c in synthetic["selected"] if c["split"] in (
          "validation","sealed_reference_calibrated_holdout")]
    need(len(test)==13 and all(c["origin"]=="generated_tseitin_mixed" for c in test),
         "expected exact 13 medium synthetic controls")
    need(sha(src_syn/"frozen/manifest.json")==synthetic["source_manifest_sha256"],
         "frozen source manifest mismatch")
    FROZEN.mkdir(parents=True,exist_ok=True)
    cases=[]
    for c in external["cases"]:
        p=src_ext/"frozen"/(c["id"]+".cnf")
        need(sha(p)==c["sha256"],"external original SHA mismatch")
        dest=FROZEN/(c["id"]+".cnf")
        shutil.copyfile(p,dest)
        cases.append({"id":c["id"],"sha256":c["sha256"],
            "suite":"external_r183_known","cohort":c["cohort"],"origin":"GBD_original",
            "expected_truth":"UNKNOWN","source_run":42206668113})
    for c in test:
        p=src_syn/"frozen"/(c["id"]+".cnf")
        need(sha(p)==c["sha256"],"R179 synthetic SHA mismatch")
        shutil.copyfile(p,FROZEN/(c["id"]+".cnf"))
        cases.append({"id":c["id"],"sha256":c["sha256"],
           "suite":"synthetic_reference_calibrated_known","cohort":"generated_tseitin_mixed",
           "origin":"generated","expected_truth":c["class"],
           "source_run":42192469296})
    cases.sort(key=lambda c:c["sha256"])
    need(len(cases)==25 and len({c["sha256"] for c in cases})==25,
         "source suite not unique 25")
    data={"protocol":PROTOCOL,"cases":cases,"count":25,
       "external_cases":12,"synthetic_cases":13,
       "cap_seconds":CAP,"repetitions":REPS,
       "R183_manifest_sha256":EXTERNAL_MANIFEST_SHA,
       "R179_selected_manifest_sha256":sha(src_syn/"r179-selected-freeze.json"),
       "not_new_unseen":True,"not_world_competition_ranking":True,
       "source_frozen_before_R185_any_solver_timing":True}
    save(FROZEN/"manifest.json",data)
    print("R185_FREEZE_PASS",json.dumps({"count":len(cases),
        "external":12,"synthetic":13,
        "manifest_sha256":sha(FROZEN/"manifest.json")},sort_keys=True),flush=True)

def verify():
    d=load(FROZEN/"manifest.json")
    need(d["protocol"]==PROTOCOL and d["count"]==25 and
         d["cap_seconds"]==CAP,"R185 frozen manifest changed")
    need(sum(c["suite"]=="external_r183_known" for c in d["cases"])==12 and
         sum(c["suite"]=="synthetic_reference_calibrated_known" for c in d["cases"])==13,
         "source suite counts changed")
    for c in d["cases"]:
        need(sha(FROZEN/(c["id"]+".cnf"))==c["sha256"],"R185 source sha changed")
    return d["cases"]

def gf2_rows(path):
    n,clauses=gf.dimacs(path)
    rows,covered=old.xor_source(clauses)
    return n,clauses,rows,covered

def explain_short(rows,max_new_clauses,clauses):
    """Every emitted parity equation is a source-traced XOR combination;
    expand 2..4-wide equations into CNF, not an unverified XOR guess.
    """
    original=set(tuple(sorted(c)) for c in clauses)
    masks=[]
    for i,(vs,rhs,_) in enumerate(rows):
        bitmask=0
        for v in vs:bitmask^=1<<(v-1)
        masks.append((bitmask,rhs,1<<i))
    found={}
    # Gaussian row echelon basis, with complete source trace.
    basis={}
    for bitmask,rhs,trace in masks:
        x,p,t=bitmask,rhs,trace
        while x:
            b=x.bit_length()-1
            if b not in basis:
                basis[b]=(x,p,t);break
            xx,pp,tt=basis[b];x^=xx;p^=pp;t^=tt
    for v in basis.values():
        mask,rhs,tr=v
        if 2<=mask.bit_count()<=4: found[(mask,rhs)]=tr
    # Bounded pairwise source-equation closure, not exponential search.
    for i in range(min(len(masks),240)):
        a,p,t=masks[i]
        for j in range(i+1,min(len(masks),240)):
            b,q,u=masks[j]
            if not (a&b):continue
            x=a^b
            if 2<=x.bit_count()<=4:
                found.setdefault((x,p^q),t^u)
            if len(found)>=250:break
        if len(found)>=250:break
    derived=[];extra=[]
    for (mask,rhs),trace in sorted(found.items(),key=lambda x:(
            x[0][0].bit_count(),x[0][0],x[0][1])):
        gf.check_trace(rows,mask,rhs,trace)
        variables=[v+1 for v in range(mask.bit_length()) if mask>>v&1]
        width=len(variables)
        encoded=[]
        for assignment in range(1<<width):
            if assignment.bit_count()%2==rhs:continue
            c=tuple(sorted((-v if assignment>>i&1 else v)
                  for i,v in enumerate(variables)))
            if c not in original:
                encoded.append(c)
        if not encoded:continue
        if len(extra)+len(encoded)>max_new_clauses:continue
        derived.append({"vars":variables,"rhs":rhs,"source_trace_bit_count":trace.bit_count()})
        for clause in encoded:
            if clause not in original:
                extra.append(clause);original.add(clause)
    return extra,derived

def parse_cdcl_stats(raw):
    stats={}
    for key in ("conflicts","decisions","propagations","learned"):
        vals=re.findall(r"(?:^|\n)\s*(?:c\s+)?"+key+r":\s+(\d+)\b",raw,re.M)
        stats[key]=int(vals[-1]) if vals else -1
    return stats

def model_from_stdout(raw):
    model={}
    for line in raw.splitlines():
        if line.startswith("v "):
            for x in map(int,line[2:].split()):
                if not x:continue
                need(abs(x) not in model or model[abs(x)]==(x>0),
                     "SAT model contains contradictory literals")
                model[abs(x)]=x>0
    return model

def native(cmd,cap,source,native_mode):
    begun=time.perf_counter()
    try:
        p=subprocess.run(cmd,capture_output=True,
            timeout=cap+3,check=False)
    except subprocess.TimeoutExpired:
        return "TIMEOUT",time.perf_counter()-begun,{},{"conflicts":-1,
          "decisions":-1,"propagations":-1,"learned":-1}
    raw=p.stdout.decode(errors="replace")
    stderr=p.stderr.decode(errors="replace")
    wall=time.perf_counter()-begun
    if native_mode=="r177":
        need(p.returncode in (0,10,20) and "R166X_RESULT " in raw,
            "R177 native failure rc="+str(p.returncode)+" "+stderr[-800:]+" "+raw[-600:])
        match=re.search(r"^R166X_RESULT mode=\w+ status=(SAT|UNSAT|UNKNOWN)\b",raw,re.M)
        need(match,"R177 missing result status")
        status="TIMEOUT" if match[1]=="UNKNOWN" else match[1]
    else:
        need(p.returncode==0 and "R182_STATUS " in raw,
             "R185 CDCL native failure rc="+str(p.returncode)+" "+stderr[-700:])
        match=re.search(r"^R182_STATUS status=(SAT|UNSAT|TIMEOUT)\b",raw,re.M)
        need(match,"CaDiCaL driver result missing")
        status=match[1]
    return status,wall,model_from_stdout(raw) if status=="SAT" else {},parse_cdcl_stats(raw)

def source_tsv(path,rows,clauses):
    # R177 native TSV parser is bounded to 300 rows. Choose highest-CNF
    # crossing incidence first, with deterministic tie-breaking.
    cnt=collections.Counter(abs(l) for c in clauses for l in c)
    ordered=sorted(rows,key=lambda row:(-sum(cnt[v] for v in row[0]),row[0],row[1]))[:300]
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text("".join(f"{len(vs)} {rhs} "+" ".join(map(str,vs))+"\n"
                            for vs,rhs,_ in ordered))
    return len(ordered)

def make_cnf(path,n,clauses,extra):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w") as f:
        f.write(f"p cnf {n} {len(clauses)+len(extra)}\n")
        for c in itertools.chain(clauses,extra):
            f.write(" ".join(map(str,c))+" 0\n")

def trial(c,method,rep,arm,driver,live_bin):
    path=FROZEN/(c["id"]+".cnf")
    need(sha(path)==c["sha256"],"SHA changed after source freeze")
    begun=time.perf_counter()
    proof="NONE";stats={"conflicts":-1,"decisions":-1,"propagations":-1,"learned":-1};added=0;xorrows=0;derived_count=0
    n,original=gf.dimacs(path)
    if arm=="clean":
        cmd=[str(driver.resolve()),str(path.resolve()),str(CAP)]
        status,wall,model,stats=native(cmd,CAP,path,"clean")
    else:
        n,original,rows,covered=gf2_rows(path)
        xorrows=len(rows)
        reduction=gf.gaussian(rows)
        if reduction["conflict"]:
            gf.check_trace(rows,0,1,reduction["conflict_trace"])
            status="UNSAT";model={};proof="GF2_SOURCE_TRACE_REPLAYED"
        elif method in ("gf2_gate","gf2_short4"):
            extra=[(v if parity else -v,) for v,(parity,trace) in reduction["units"].items()]
            for v,(parity,trace) in reduction["units"].items():
                gf.check_trace(rows,1<<(v-1),parity,trace)
            if method=="gf2_short4":
                short,derived=explain_short(rows,96,original)
                extra.extend(short);derived_count=len(derived)
            added=len(extra)
            dest=ROOT/"scratch"/method/(c["id"]+"-"+str(rep)+".cnf")
            if extra:
                make_cnf(dest,n,original,extra)
                src=dest
            else:src=path
            remaining=CAP-(time.perf_counter()-begun)
            if remaining<=0.1:
                status="TIMEOUT";model={}
            else:
                status,wall,model,stats=native([
                    str(driver.resolve()),str(src.resolve()),str(remaining)],
                    remaining,src,"clean")
        else:
            tsv=ROOT/"scratch"/method/(c["id"]+"-"+str(rep)+".tsv")
            added=source_tsv(tsv,rows,original)
            native_mode={"live_feedback":"direct_full_feedback",
                         "live_cooldown":"direct_cooldown"}[method]
            remaining=CAP-(time.perf_counter()-begun)
            if remaining<=1.0:
                status="TIMEOUT";model={}
            else:
                status,wall,model,stats=native([
                    str(live_bin.resolve()),native_mode,str(path.resolve()),
                    str(tsv.resolve()),str(remaining)],
                    remaining,path,"r177")
    elapsed=time.perf_counter()-begun
    if status=="SAT":
        gf.sat_check(original,model)
        proof="SAT_ORIGINAL_CNF_VERIFIED"
    elif status=="UNSAT" and proof=="NONE":
        proof="CADICAL_UNSAT_NO_INDEPENDENT_LRAT"
    if elapsed>=CAP:
        status="TIMEOUT";proof="CAP"
    if c["expected_truth"]!="UNKNOWN" and status!="TIMEOUT":
        need(status==c["expected_truth"],"source SAT truth mismatch")
    return {"id":c["id"],"sha256":c["sha256"],"suite":c["suite"],
      "cohort":c["cohort"],"method":method,"arm":arm,"rep":rep,
      "cap_s":CAP,"status":status,"elapsed_s":round(elapsed,6),
      "par2_s":round(2*CAP if status=="TIMEOUT" else elapsed,6),
      "proof":proof,"xor_rows":xorrows,"added_units_or_source_rows":added,
      "short_derived_equations":derived_count,**stats}

def shard(index,method,driver,live):
    need(method in METHODS and 0<=index<SHARDS,"unknown method/shard")
    cases=verify()
    data=[]
    for c in cases[index::SHARDS]:
        for rep in range(REPS):
            arms=["clean","method"]
            random.Random(PROTOCOL+"|"+method+"|"+c["sha256"]+"|"+str(rep)).shuffle(arms)
            for arm in arms:
                x=trial(c,method,rep,arm,driver,live)
                data.append(x)
                save(ROOT/"results"/(f"shard-{index}.json"),data)
                print("R185_TRIAL",json.dumps({k:x[k] for k in (
                     "id","suite","method","arm","rep","status",
                     "elapsed_s","xor_rows","short_derived_equations",
                     "conflicts","decisions")},sort_keys=True),flush=True)
    need(len(data)==len(cases[index::SHARDS])*REPS*2,"shard trial count")
    print("R185_SHARD_PASS",method,index,len(data),flush=True)

def audit(method):
    need(method in METHODS,"bad method")
    cases=verify();rows=[]
    for shard_index in range(SHARDS):
        rows.extend(load(ROOT/"results"/f"shard-{shard_index}.json"))
    need(len(rows)==len(cases)*REPS*2,"not all 100 paired trials")
    by=collections.defaultdict(list)
    for r in rows:
        need(r["method"]==method,"method mismatch in consolidated shard")
        by[r["sha256"],r["arm"]].append(r)
    scores={}
    per_case=[]
    for c in cases:
        item={}
        for arm in ("clean","method"):
            data=by[c["sha256"],arm]
            need(len(data)==2 and {x["rep"] for x in data}=={0,1},
                 "unpaired repeat or swapped SHA")
            item[arm]=statistics.median(x["par2_s"] for x in data)
        statuses={x["status"] for arm in ("clean","method")
                  for x in by[c["sha256"],arm] if x["status"]!="TIMEOUT"}
        need(len(statuses)<=1,"contradictory SAT statuses")
        per_case.append({"id":c["id"],"sha256":c["sha256"],"suite":c["suite"],
            "cohort":c["cohort"],"clean_par2_s":item["clean"],
            "method_par2_s":item["method"]})
        scores[c["sha256"]]=item
    def group(sub):
        trialrows=[x for x in rows if x["sha256"] in {c["sha256"] for c in sub}]
        sums={arm:sum(scores[c["sha256"]][arm] for c in sub) for arm in ("clean","method")}
        solved={arm:sum(x["status"] in ("SAT","UNSAT") for x in trialrows if x["arm"]==arm)
                for arm in ("clean","method")}
        byclass={arm:dict(collections.Counter(x["status"] for x in trialrows
                if x["arm"]==arm)) for arm in ("clean","method")}
        return {"cases":len(sub),"clean_PAR2_s":round(sums["clean"],6),
            "method_PAR2_s":round(sums["method"],6),
            "speed_ratio_clean_over_method":round(sums["clean"]/sums["method"],6),
            "solved_repetitions":solved,"outcomes":byclass}
    groups={"external_originals":group([c for c in cases if c["suite"]=="external_r183_known"]),
       "medium_synthetic_controls":group([c for c in cases if c["suite"]=="synthetic_reference_calibrated_known"]),
       "all_mixed":group(cases)}
    report={"protocol":PROTOCOL,"method":method,"status":"R185_METHOD_AUDIT_PASS",
        "case_manifest_sha256":sha(FROZEN/"manifest.json"),
        "source_count":25,"repetitions":REPS,"attempts":len(rows),
        "external_originals_already_seen_in_R183":True,
        "synthetic_development_controls":13,"not_blind":True,
        "not_general_SAT_ranking":True,"independent_unsat_LRAT_not_checked":True,
        "groups":groups,"per_case":per_case}
    save(ROOT/"report.json",report)
    save(ROOT/"all-trials.json",rows)
    print("R185_METHOD_FINAL",json.dumps({k:report[k] for k in (
        "method","case_manifest_sha256","attempts","groups")},sort_keys=True),flush=True)

def selftest():
    # A 3-variable XOR3 pair gives an independently certified contradiction.
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        p=pathlib.Path(td)/"test.cnf"
        clauses=[]
        for signs in range(8):
            clauses.append(tuple(-v if signs>>(v-1)&1 else v for v in (1,2,3)))
        clauses.append((1,4))
        p.write_text("p cnf 4 "+str(len(clauses))+"\n"+
                     "".join(" ".join(map(str,c))+" 0\n" for c in clauses))
        n,c,rows,covered=gf2_rows(p)
        g=gf.gaussian(rows)
        need(g["conflict"] and len(rows)==2 and len(covered)==8,
             "source-certified XOR contradiction")
        gf.check_trace(rows,0,1,g["conflict_trace"])
        # Source XOR of (1,2,3) and (2,3,4) entails binary XOR of (1,4).
        rr=[((1,2,3),0,[0]),((2,3,4),0,[1])]
        extra,trace=explain_short(rr,96,[])
        need(any(x["vars"]==[1,4] for x in trace) and len(extra)>=2,
             "short parity source-traced consequence absent")
    print("R185_SELFTEST_PASS",flush=True)

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("action",choices=("selftest","freeze","verify","shard","audit"))
    ap.add_argument("--method",default="gf2_gate",choices=METHODS)
    ap.add_argument("--shard",type=int,default=0)
    ap.add_argument("--driver",default="r185/r185-driver")
    ap.add_argument("--live",default="r185/r185-live")
    args=ap.parse_args()
    if args.action=="selftest":selftest()
    elif args.action=="freeze":freeze()
    elif args.action=="verify":print("R185_VERIFY_PASS",len(verify()),flush=True)
    elif args.action=="shard":shard(args.shard,args.method,pathlib.Path(args.driver),pathlib.Path(args.live))
    else:audit(args.method)
