#!/usr/bin/env python3
"""R182 certified XOR3 extraction / GF(2) proof / structural backdoor SAT bench.

Primary: 53 *reference-calibrated* generated SAT+UNSAT mixed CNFs,
frozen in R179 run 42192469296, splits 40/9/4 predeclared before DRNAS run.
Do NOT call these industrial, distribution-blind, or external formulas.
All modes use same SHA and CaDiCaL 2.1.0 binary. SAT verified on original CNF;
GF2 contradiction reconstructed from four-clause XOR encoding and replayed.
UNSAT from CaDiCaL not independently LRAT-certified.
"""
from __future__ import annotations
import argparse,collections,hashlib,itertools,json,math,pathlib,random,re,statistics,subprocess,time
ROOT=pathlib.Path("r182")
SRC=pathlib.Path("r179/frozen")
MODES=("clean","gf2_gate","gf2_units")
SHARDS=8
REPS=2
CAP=12.0
PROTO="DRNAS-R182-MIXED-STRUCTURAL-BACKDOOR-v1"

def need(cond,msg):
    if not cond:raise RuntimeError("R182_FAIL_CLOSED "+str(msg))
def sha(path):return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
def load(path):return json.loads(pathlib.Path(path).read_text())
def save(path,obj):
    path=pathlib.Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,indent=2,sort_keys=True)+"\n")
def dimacs(path):
    n=0;m=-1;clauses=[];partial=[]
    for ln in pathlib.Path(path).read_text().splitlines():
        line=ln.strip()
        if not line or line[0]=="c":continue
        if line.startswith("p "):
            seg=line.split();need(len(seg)==4 and seg[:2]==["p","cnf"],"bad CNF header")
            n=int(seg[2]);m=int(seg[3]);continue
        for s in line.split():
            val=int(s)
            if val==0:
                clauses.append(tuple(partial));partial=[]
            else:
                need(0<abs(val)<=n,"literal out of range")
                partial.append(val)
    need(n>0 and m==len(clauses) and not partial,"DIMACS clause count")
    return n,clauses

def xor3_extract(clauses):
    """Each complete four-clause forbidden-assignment quartet CERTIFIES an XOR3.
    Residual CNF is retained: XOR structure alone does not establish pure XOR.
    """
    groups=collections.defaultdict(lambda:collections.defaultdict(set))
    for i,c in enumerate(clauses):
        if len(c)!=3 or len(set(abs(x) for x in c))!=3:continue
        ordered=sorted(c,key=lambda x:abs(x))
        vs=tuple(abs(x) for x in ordered)
        assignment=sum((1<<k) for k,x in enumerate(ordered) if x<0)
        groups[vs][assignment].add(i)
    rows=[];covered=set()
    for vs,patterns in groups.items():
        for p in (0,1):
            wanted=[a for a in range(8) if a.bit_count()%2==p]
            if all(a in patterns for a in wanted):
                ids=[min(patterns[a]) for a in wanted]
                # Four CNF clauses prohibit exactly parity p assignments.
                rows.append((vs,1-p,ids))
                covered.update(ids)
    rows.sort(key=lambda x:(x[0],x[1]))
    return rows,covered

def gaussian(rows):
    """GF(2) row reduction with explicit XOR trace back to certified source rows."""
    pivots={};conflict=None
    for i,(vs,rhs,ids) in enumerate(rows):
        mask=sum(1<<(v-1) for v in vs);trace=1<<i
        while mask:
            bit=mask.bit_length()-1
            if bit not in pivots:
                pivots[bit]=(mask,rhs,trace);break
            pm,pr,pt=pivots[bit]
            mask^=pm;rhs^=pr;trace^=pt
        if not mask and rhs:
            conflict=trace;break
    if conflict is not None:
        check_trace(rows,0,1,conflict)
        return {"conflict":True,"conflict_trace":conflict,"units":{},"rank":len(pivots)}
    # Back substitute: XOR lower pivots from all higher rows
    for k in sorted(pivots):
        lk,lr,lt=pivots[k]
        for h in sorted(pivots):
            if h>k and (pivots[h][0] & (1<<k)):
                mask,rhs,tr=pivots[h]
                pivots[h]=(mask^lk,rhs^lr,tr^lt)
    units={}
    for mask,rhs,trace in pivots.values():
        if mask.bit_count()==1:
            v=mask.bit_length()
            check_trace(rows,mask,rhs,trace)
            need(v not in units or units[v][0]==rhs,"inconsistent derived units")
            units[v]=(rhs,trace)
    return {"conflict":False,"conflict_trace":None,"units":units,"rank":len(pivots)}

def check_trace(rows,target_mask,target_rhs,trace):
    mask=0;rhs=0
    for i,(vs,parity,ids) in enumerate(rows):
        if trace>>i&1:
            for v in vs:mask^=1<<(v-1)
            rhs^=parity
    need(mask==target_mask and rhs==target_rhs,"GF2 source-trace proof invalid")

def class_cnf(clauses):
    return {
      "horn":all(sum(x>0 for x in c)<=1 for c in clauses),
      "dual_horn":all(sum(x<0 for x in c)<=1 for c in clauses),
      "two_sat":all(len(c)<=2 for c in clauses),
      "zero_valid":all(any(x<0 for x in c) for c in clauses),
      "one_valid":all(any(x>0 for x in c) for c in clauses),
    }

def simplify(cnf,assignment):
    rest=[]
    for clause in cnf:
        if any(v in assignment and assignment[v]==(lit>0)
               for lit in clause for v in [abs(lit)]):
            continue
        rest.append(tuple(lit for lit in clause if abs(lit) not in assignment))
    return rest

def strong_backdoor(clauses,rows,max_candidates=8,max_depth=2):
    """Enumerate ALL assignments to candidate sets; non-found == UNKNOWN,
    not proof that no small backdoor exists.
    """
    base=class_cnf(clauses)
    for target in ("two_sat","horn","dual_horn"):
        if base[target]:return {"class":target,"vars":[],"certified":True}
    freq=collections.Counter(abs(l) for c in clauses for l in c)
    xorvars={v for vs,_,_ in rows for v in vs}
    residual_count=collections.Counter()
    for c in clauses:
        for lit in c:
            if abs(lit) in xorvars:residual_count[abs(lit)]+=1
    candidates=sorted(freq,key=lambda v:(-residual_count[v],-freq[v],v))[:max_candidates]
    for width in range(1,max_depth+1):
        for chosen in itertools.combinations(candidates,width):
            for target in ("two_sat","horn","dual_horn"):
                if all(class_cnf(simplify(clauses,dict(zip(chosen,bits))))[target]
                       for bits in itertools.product((False,True),repeat=width)):
                    return {"class":target,"vars":list(chosen),"certified":True}
    return {"class":None,"vars":[],"certified":False,"searched_candidates":len(candidates),
            "searched_max_depth":max_depth}

def analyze(path,backdoor=True):
    start=time.perf_counter()
    n,clauses=dimacs(path);rows,covered=xor3_extract(clauses)
    gf=gaussian(rows);classes=class_cnf(clauses)
    xorvars={v for vs,_,_ in rows for v in vs}
    crossing=sum(bool(set(map(abs,c))&xorvars) for i,c in enumerate(clauses)
                 if i not in covered)
    bd=strong_backdoor(clauses,rows) if backdoor else {"class":None,"certified":False}
    time_s=time.perf_counter()-start
    info={"variables":n,"clauses":len(clauses),"xor_rows":len(rows),
       "xor_covered_clauses":len(covered),"residual_clauses":len(clauses)-len(covered),
       "xor_var_count":len(xorvars),"residual_crossing":crossing,
       "syntactic_pure_xor_encoding":bool(rows) and len(covered)==len(clauses),
       "class_membership":classes,"strong_backdoor":bd,
       "certified_gf2_contradiction":gf["conflict"],"gf2_rank":gf["rank"],
       "certified_units":len(gf["units"])}
    return n,clauses,rows,gf,info,time_s

def selected():
    data=load(pathlib.Path("r179/r179-selected-freeze.json"))
    need(data["protocol"]=="DRNAS-R179-MIXED-MEDIUM-SAT-UNSAT-REFERENCE-CALIBRATION-v1",
         "unexpected benchmark source")
    cases=data["selected"]
    need(len(cases)==53 and data["split_counts"]=={
      "development":40,"validation":9,"sealed_reference_calibrated_holdout":4},
      "R179 selected 53 split drift")
    need(all(x["origin"]=="generated_tseitin_mixed" and
             x["class"] in ("SAT","UNSAT") for x in cases),
         "only source-frozen generated SAT+UNSAT cases eligible")
    need(sha("r179/frozen/manifest.json")==data["source_manifest_sha256"],
         "source reference manifest changed")
    for x in cases:need(sha(SRC/(x["id"]+".cnf"))==x["sha256"],"case SHA mismatch")
    return cases

def native(binary,src,cap):
    started=time.perf_counter()
    try:
        p=subprocess.run([str(binary.resolve()),str(pathlib.Path(src).resolve()),str(cap)],
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=cap+4,check=False)
    except subprocess.TimeoutExpired:
        return "TIMEOUT",time.perf_counter()-started,{}
    elapsed=time.perf_counter()-started
    need(p.returncode==0,"native driver fail "+p.stderr.decode(errors="replace")[-800:])
    out=p.stdout.decode(errors="replace")
    m=re.search(r"^R182_STATUS status=(SAT|UNSAT|TIMEOUT) solver_s=([0-9.]+) variables=(\d+)$",out,re.M)
    need(m,"missing native status")
    model={}
    if m[1]=="SAT":
        for line in out.splitlines():
            if line.startswith("v "):
                lit=int(line.split()[1])
                need(lit!=0 and (abs(lit) not in model or model[abs(lit)]==(lit>0)),
                     "invalid native model")
                model[abs(lit)]=lit>0
    return m[1],elapsed,model

def sat_check(clauses,model):
    need(model and all(any(model.get(abs(lit))==(lit>0) for lit in c) for c in clauses),
         "independent original SAT witness invalid")

def trial(case,mode,rep,binary):
    src=SRC/(case["id"]+".cnf")
    need(sha(src)==case["sha256"],"source drift")
    t=time.perf_counter()
    proof="NONE";derived_units=0;crossing=0;bd=None
    if mode=="clean":
        n,clauses=dimacs(src)
        status,_,model=native(binary,src,CAP)
    else:
        n,clauses,rows,gf,info,analysis_s=analyze(src,backdoor=False)
        derived_units=len(gf["units"]);crossing=info["residual_crossing"]
        if gf["conflict"]:
            # Hard UNSAT certificate: trace is XOR sum of source-certified rows.
            check_trace(rows,0,1,gf["conflict_trace"])
            status="UNSAT";model={};proof="GF2_SOURCE_CONTRADICTION_REPLAYED"
        else:
            inp=src
            if mode=="gf2_units" and gf["units"]:
                out=ROOT/"derived"/(case["id"]+"-"+str(rep)+".cnf")
                out.parent.mkdir(parents=True,exist_ok=True)
                units=[v if val else -v for v,(val,trace) in gf["units"].items()]
                out.write_text("p cnf "+str(n)+" "+str(len(clauses)+len(units))+"\n"+
                    "".join(" ".join(map(str,c))+" 0\n" for c in clauses)+
                    "".join(str(v)+" 0\n" for v in units))
                inp=out
            status,_,model=native(binary,inp,CAP)
    elapsed=time.perf_counter()-t
    if status=="SAT":sat_check(clauses,model);proof="SAT_ORIGINAL_MODEL_VERIFIED"
    if status=="UNSAT" and proof=="NONE":proof="CADICAL_UNSAT_NOT_INDEPENDENT_LRAT"
    if elapsed>CAP:status="TIMEOUT";proof="TIMEOUT"
    need(status=="TIMEOUT" or status==case["class"],
         "expected source truth mismatch "+case["id"]+" "+mode)
    rec={"id":case["id"],"sha256":case["sha256"],"split":case["split"],
       "class":case["class"],"mode":mode,"repeat":rep,"cap_s":CAP,
       "status":status,"elapsed_s":round(elapsed,6),
       "par2_s":round(2*CAP if status=="TIMEOUT" else elapsed,6),
       "proof":proof,"derived_units":derived_units,"residual_crossing":crossing}
    return rec

def shard(index,binary):
    need(0<=index<SHARDS,"invalid shard");cases=selected()
    ROOT.mkdir(exist_ok=True)
    out=[]
    for c in cases[index::SHARDS]:
        n,cls,rows,gf,info,delay=analyze(SRC/(c["id"]+".cnf"))
        obs={"id":c["id"],"sha256":c["sha256"],"split":c["split"],
             "class":c["class"],"struct":info,"classify_s":delay}
        for cutoff in (64,256):
            import r181_early_conflict_shazam as r181
            # Independent early probes, measured separately, never reused as solves.
            p=ROOT/"r181-probe"
            obs["probe_"+str(cutoff)]=r181.probe(SRC/(c["id"]+".cnf"),
                                                   p,cutoff,20.0)
        for rep in range(REPS):
            order=list(MODES)
            random.Random(PROTO+c["sha256"]+str(rep)).shuffle(order)
            for mode in order:
                rec=trial(c,mode,rep,binary)
                out.append(rec)
                save(ROOT/f"shard-{index}.json",{"trials":out,"structures":{}})
                print("R182_TRIAL",json.dumps({k:rec[k] for k in (
                    "id","class","mode","repeat","status","elapsed_s","proof")}),
                    flush=True)
        save(ROOT/f"structure-{index}-{c['id']}.json",obs)
    need(len(out)==len(cases[index::SHARDS])*REPS*len(MODES),"shard incomplete")
    print("R182_SHARD_PASS",index,len(out),flush=True)

def audit():
    cases=selected();allrows=[];structs={}
    for i in range(SHARDS):
        d=load(ROOT/f"shard-{i}.json");allrows.extend(d["trials"])
        for c in cases[i::SHARDS]:
            obs=load(ROOT/f"structure-{i}-{c['id']}.json")
            need(obs["sha256"]==c["sha256"],"structure SHA drift")
            structs[c["id"]]=obs
    need(len(allrows)==len(cases)*REPS*len(MODES),"paired 318 trials missing")
    times=collections.defaultdict(dict);by=collections.defaultdict(list)
    for r in allrows:by[(r["id"],r["mode"])].append(r)
    for c in cases:
        for m in MODES:
            rr=by[(c["id"],m)]
            need(len(rr)==REPS and all(z["sha256"]==c["sha256"] for z in rr),
                 "paired trial identity/repeat missing")
            times[c["id"]][m]=statistics.median(z["par2_s"] for z in rr)
    summaries={}
    for group,sub in [("all",cases),
       ("development",[c for c in cases if c["split"]=="development"]),
       ("validation",[c for c in cases if c["split"]=="validation"]),
       ("sealed",[c for c in cases if c["split"]=="sealed_reference_calibrated_holdout"]),
       ("SAT",[c for c in cases if c["class"]=="SAT"]),
       ("UNSAT",[c for c in cases if c["class"]=="UNSAT"])]:
        if not sub:continue
        totals={m:round(sum(times[c["id"]][m] for c in sub),6) for m in MODES}
        oracle=sum(min(times[c["id"]].values()) for c in sub)
        summaries[group]={"n":len(sub),"par2_s":totals,
           "best_oracle_par2_s":round(oracle,6),
           "clean_oracle_headroom_x":round(totals["clean"]/oracle,5)}
    # Candidate kNN routes trained ONLY on development labels; validation
    # and sealed holdouts never influence scaling or fitted decision.
    train=[c for c in cases if c["split"]=="development"]
    verify=[c for c in cases if c["split"]!="development"]
    def features(c):
        z=structs[c["id"]];s=z["struct"];a=[
           math.log1p(s["variables"]),math.log1p(s["clauses"]),
           s["xor_rows"]/max(1,s["clauses"]),s["residual_clauses"]/max(1,s["clauses"]),
           s["residual_crossing"]/max(1,s["clauses"]),
           int(s["certified_gf2_contradiction"]),s["certified_units"],
           int(s["class_membership"]["horn"]),
           int(s["class_membership"]["dual_horn"]),
           int(s["class_membership"]["two_sat"]),
           int(s["strong_backdoor"]["certified"])]
        for cutoff in (64,256):
            p=z["probe_"+str(cutoff)]
            a += [math.log1p(max(0,p["conflicts"])),
                  math.log1p(max(0,p["decisions"])),
                  p["conflicts"]/max(1,p["decisions"]),
                  float(p["status"]=="UNKNOWN")]
        return a
    raw=[features(c) for c in train]
    scales=[max(0.1,statistics.pstdev(x[i] for x in raw))
            for i in range(len(raw[0]))]
    def choose(x):
        ranked=sorted(
            ((sum(((a-b)/s)**2 for a,b,s in zip(x,features(c),scales)),
              c["id"]) for c in train),key=lambda z:z[0])[:7]
        scores={}
        for m in MODES:
            scores[m]=sum(times[id][m]/(0.1+math.sqrt(d))
                          for d,id in ranked)/sum(1/(0.1+math.sqrt(d))
                                                  for d,id in ranked)
        chosen=min(MODES,key=lambda m:scores[m])
        if chosen!="clean" and scores[chosen]>=0.95*scores["clean"]:
            chosen="clean"
        return chosen
    holdout=[]
    for c in verify:
        z=structs[c["id"]]
        start=time.perf_counter();chosen=choose(features(c))
        classify_s=time.perf_counter()-start
        # Probing is a separate non-resumable run: charge both probes and
        # structural feature extraction to learned route.
        probe_cost=z["classify_s"]+classify_s+sum(
            z["probe_"+str(k)]["wall_s"] for k in (64,256))
        rule_mode="gf2_gate" if z["struct"]["certified_gf2_contradiction"] else "clean"
        # Rule reads CNF and extracts GF2; if rule abstains, this screening
        # cost is still charged. Selected arm gf2_gate already includes it.
        static_cost=z["classify_s"] if rule_mode=="clean" else 0
        holdout.append({"id":c["id"],"split":c["split"],"class":c["class"],
          "clean_par2_s":times[c["id"]]["clean"],
          "oracle_par2_s":min(times[c["id"]].values()),
          "chosen_ml":chosen,
          "ml_par2_s":times[c["id"]][chosen]+probe_cost,
          "rule_mode":rule_mode,
          "rule_par2_s":times[c["id"]][rule_mode]+static_cost,
          "probes_charged_s":probe_cost})
    def totals(group):
        a=[r for r in holdout if group=="all" or r["split"]==group]
        total=lambda key:sum(r[key] for r in a)
        return {"count":len(a),"clean_par2_s":round(total("clean_par2_s"),6),
           "rule_par2_s":round(total("rule_par2_s"),6),
           "ml_par2_s":round(total("ml_par2_s"),6),
           "oracle_par2_s":round(total("oracle_par2_s"),6),
           "clean_to_rule_x":round(total("clean_par2_s")/max(1e-8,total("rule_par2_s")),5),
           "clean_to_ml_x":round(total("clean_par2_s")/max(1e-8,total("ml_par2_s")),5)}
    findings={"all":totals("all"),
       "validation":totals("validation"),
       "sealed":totals("sealed_reference_calibrated_holdout")}
    report={"protocol":PROTO,"status":"R182_AUDIT_PASS",
       "source_selection":"R179 53 CaDiCaL-reference-calibrated generated SAT+UNSAT mixed CNFs",
       "synthetic_not_external":True,"reference_calibrated_not_distribution_blind":True,
       "real_originals_in_primary":0,"not_independent_LRAT_for_CDCL_UNSAT":True,
       "full_oracle_comparison":summaries,"heldout":findings,
       "claim":"This benchmark tests source-certified XOR contradictions in a synthetic Tseitin-rich cohort, NOT general SAT dominance",
       "trials":len(allrows),"cases":len(cases)}
    save(ROOT/"report.json",report);save(ROOT/"holdout.json",holdout)
    with (ROOT/"summary.md").open("w") as f:
        f.write("# R182 mixed SAT structural/backdoor certificate experiment\n\n")
        f.write("53 *generated* R179 CaDiCaL-calibrated SAT/UNSAT formulas; "
                "not external or distribution-blind.\n\n")
        f.write("|Group|N|Clean PAR2 s|GF2-gate PAR2 s|GF2-units PAR2 s|Oracle headroom x|\n"
                "|---|---:|---:|---:|---:|---:|\n")
        for label,v in summaries.items():
            f.write(f"|{label}|{v['n']}|{v['par2_s']['clean']}|"
                    f"{v['par2_s']['gf2_gate']}|{v['par2_s']['gf2_units']}|"
                    f"{v['clean_oracle_headroom_x']}|\n")
        f.write("\n## Source-only proof gate vs 64+256 CDCL Shazam (replay, all probe costs charged)\n\n")
        for label,v in findings.items():f.write(f"- {label}: {json.dumps(v,sort_keys=True)}\n")
    print("R182_FINAL",json.dumps({"summary":summaries,"holdout":findings},sort_keys=True),flush=True)

def selftest():
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        p=pathlib.Path(td)/"test.cnf"
        # Both parity classes over (1,2,3) => source contradiction.
        clauses=[]
        for parity in (0,1):
            for assignment in range(8):
                if assignment.bit_count()%2==parity:
                    clauses.append(tuple(-v if assignment>>(v-1)&1 else v
                                          for v in (1,2,3)))
        clauses.append((1,4))
        p.write_text("p cnf 4 "+str(len(clauses))+"\n"+
              "".join(" ".join(map(str,c))+" 0\n" for c in clauses))
        n,c,rows,gf,info,t=analyze(p)
        need(len(rows)==2 and gf["conflict"] and info["residual_clauses"]==1,
             "XOR3 source contradiction not detected")
        need(not info["syntactic_pure_xor_encoding"],"mixed marker wrong")
        p.write_text("p cnf 3 2\n1 -2 0\n-1 3 0\n")
        _,_,_,gf,info,_=analyze(p)
        need(info["class_membership"]["two_sat"] and
             info["class_membership"]["horn"] and not gf["conflict"],
             "Schaefer syntactic classifier wrong")
    print("R182_SELFTEST_PASS",flush=True)

if __name__=="__main__":
    a=argparse.ArgumentParser()
    a.add_argument("action",choices=("selftest","shard","audit"))
    a.add_argument("--shard",type=int,default=0)
    a.add_argument("--binary",default="r182/r182-driver")
    args=a.parse_args()
    if args.action=="selftest":selftest()
    elif args.action=="shard":shard(args.shard,pathlib.Path(args.binary))
    else:audit()
