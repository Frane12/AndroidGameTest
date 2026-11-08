#!/usr/bin/env python3
"""DRNAS MRE X3: explain spread, NOT a blind benchmark.
A source-frozen, seven-order dose experiment on 4 duplicate-bearing CNFs
and one negative control. Same C++ native CMS library and identical solver seed.
Track end-to-end PAR2 separately from load/solve stages and bounded CDCL.
SAT models are replayed against the ORIGINAL CNF; UNSAT uses pre-existing
reference agreement, with NO independent LRAT claim.
"""
from __future__ import annotations
import argparse,collections,hashlib,json,pathlib,random,re,subprocess,tempfile,time
import mre_x_benchmark as base
import mre_x2_clause_order_causal as x2

OUT=pathlib.Path("mre_x3")
PROTO="DRNAS-MRE-X3-SPREAD-DOSE-5SHA-7ORDERS-4SEEDS-12S-v1"
CAP=12.0
REPS=4
SHARDS=4
MODES=("original","spread25","spread50","spread75","spread100","front100","tail100")
TARGETS=("69aa8b6bb96a5952fedf1007994b4255d06f7e32023390bc4c342b1b30a0356a",
 "7f25d0862e92fb60d957ea903ded020ec2b83b2ceec2ba4bf015bdcb1d4c3ac1",
 "eb9a4740b712b149f08d5b430ae5907109eac3f231ce549a281703bc8e0965fb",
 "b84bff752c8292bacf847078d0fe2c2bf8ef86f429c08250e973a0525b607c39",
 "818eea0ab4e59102c589549d3ca487bf7c8a03e1e51644a126cba75a911e53de")
EXPECTED=5*7*4
BUDGETS=(100,1000,5000)
DIAG_CASES=TARGETS[:4]

def need(v,msg):
    if not v:raise RuntimeError("MRE_X3_FAIL_CLOSED "+str(msg))
def sha(b):return hashlib.sha256(b).hexdigest()
def dump(p,data):
    p=pathlib.Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(data,indent=2,sort_keys=True)+"\n")
def source_cases():
    data={c["sha256"]:c for c in base.cases()}
    need(all(k in data for k in TARGETS),"source cohort changed")
    return [data[k] for k in TARGETS]
def source(c):return base.ROOT/c["filename"]
def path(c,mode):return OUT/(c["gbd"]+"."+mode+".cnf")
def key(clause):return tuple(sorted(set(clause)))
def duplicates(clauses):
    seen=set();indices=[]
    for i,c in enumerate(clauses):
        k=key(c)
        if k in seen:indices.append(i)
        else:seen.add(k)
    return indices
def transform(original,mode):
    need(mode in MODES,"unknown mode")
    if mode=="original":return list(original),0
    indices=duplicates(original)
    if not indices:return list(original),0
    if mode in ("front100","tail100"):
        chosen=set(indices)
        uniq=[c for i,c in enumerate(original) if i not in chosen]
        dup=[original[i] for i in indices]
        return (dup+uniq if mode=="front100" else uniq+dup),len(dup)
    frac={"spread25":0.25,"spread50":0.5,"spread75":0.75,"spread100":1.0}[mode]
    amount=(len(indices)*int(frac*100))//100
    selected=set(indices[:amount])
    retained=[c for i,c in enumerate(original) if i not in selected]
    moved=[original[i] for i in indices[:amount]]
    gaps=[((i+1)*(len(retained)+1))//(amount+1) for i in range(amount)]
    buckets=[[] for _ in range(len(retained)+1)]
    for gap,c in zip(gaps,moved):buckets[gap].append(c)
    out=[]
    for i in range(len(retained)+1):
        out.extend(buckets[i])
        if i<len(retained):out.append(retained[i])
    need(len(out)==len(original),"clause count changed")
    return out,amount
def positions(clauses):
    seen=set();bins=[0]*10;total=0
    for i,c in enumerate(clauses):
        k=key(c)
        if k in seen:
            bins[min(9,i*10//len(clauses))]+=1;total+=1
        else:seen.add(k)
    return bins,total
def test_self():
    tests=[
       (4,[(1,-2),(1,-2),(-1,2),(1,3),(1,3),(4,)]),
       (3,[(1,),(-1,),(1,),(-2,3),(-2,3)]),
       (4,[(1,2),(-1,3),(2,3),(1,2),(4,-4)])]
    with tempfile.TemporaryDirectory() as tmp:
        td=pathlib.Path(tmp)
        for i,(nv,cs) in enumerate(tests):
            src=td/("original-%d.cnf"%i);x2.write(src,nv,cs)
            truth=base.brute(src)
            for mode in MODES:
                order,moved=transform(cs,mode)
                dst=td/(mode+"-%d.cnf"%i);x2.write(dst,nv,order)
                need(collections.Counter(cs)==collections.Counter(order),
                     "selftest raw multiset difference")
                need(base.brute(dst)==truth,"SAT truth changed")
                if mode=="spread100":
                    need(order==x2.permutation(cs,"duplicate_spread",sha(src.read_bytes())),
                         "X2 spread100 not identical")
                if mode=="front100":
                    need(order==x2.permutation(cs,"duplicate_front",sha(src.read_bytes())),
                         "X2 front100 not identical")
                if mode=="tail100":
                    need(order==x2.permutation(cs,"duplicate_tail",sha(src.read_bytes())),
                         "X2 tail100 not identical")
    print("MRE_X3_SELFTEST_PASS 3 7",flush=True)

def freeze():
    OUT.mkdir(exist_ok=True)
    rows=[]
    for c in source_cases():
        nv,cs=x2.parse(source(c))
        duplicate=duplicates(cs)
        row=dict(gbd=c["gbd"],sha256=c["sha256"],reference_status=c["reference_status"],
            family=c["family"],source_clauses=len(cs),vars=nv,
            canonical_duplicate_count=len(duplicate),modes={})
        for mode in MODES:
            order,moved=transform(cs,mode)
            need(collections.Counter(cs)==collections.Counter(order),
                 "original raw clause multiset differs")
            dst=path(c,mode);x2.write(dst,nv,order)
            bins,count=positions(order)
            need(count==len(duplicate),"moved mode changed semantic dup count")
            row["modes"][mode]=dict(sha256=sha(dst.read_bytes()),moved=moved,
                                     duplicate_prefix_decile=bins)
            if mode in ("spread100","front100","tail100"):
                x2mode={"spread100":"duplicate_spread",
                         "front100":"duplicate_front",
                         "tail100":"duplicate_tail"}[mode]
                need(x2.parse(dst)==x2.parse(x2.OUT/(c["gbd"]+"."+x2mode+".cnf")),
                     "MRE X3 diverged from exact MRE X2 saved permutation")
        rows.append(row)
        print("MRE_X3_SOURCE",json.dumps({k:v for k,v in row.items()
                if k!="modes"},sort_keys=True),flush=True)
    need(sum(x["canonical_duplicate_count"]>0 for x in rows)==4,
         "4 duplicate sources not present")
    need(rows[-1]["canonical_duplicate_count"]==0,"negative control not free of duplicate")
    dump(OUT/"manifest.json",dict(protocol=PROTO,source_count=len(rows),
       modes=list(MODES),expected=EXPECTED,cap_s=CAP,seed_repeats=REPS,
       development_not_holdout=True,raw_clause_multiset_identical=True,
       same_X2_seed_for_each_sha_rep=True,independent_UNSAT_LRAT=False,
       no_auto_promotion=True,cases=rows))
    print("MRE_X3_FREEZE_PASS 5 7",flush=True)

def verify():
    m=json.loads((OUT/"manifest.json").read_text())
    need(m["protocol"]==PROTO and m["expected"]==EXPECTED and
         m["modes"]==list(MODES) and len(m["cases"])==5,"X3 manifest changed")
    for r,c in zip(m["cases"],source_cases()):
        need(r["sha256"]==c["sha256"],"source mismatch")
        nv,cs=x2.parse(source(c))
        for mode in MODES:
            p=path(c,mode)
            need(sha(p.read_bytes())==r["modes"][mode]["sha256"],"variant SHA drift")
            n,order=x2.parse(p)
            actual,moved=transform(cs,mode)
            need(n==nv and order==actual,"order strategy drift")
            need(collections.Counter(cs)==collections.Counter(order),"multiset drift")
            need(moved==r["modes"][mode]["moved"],"dose drift")
    print("MRE_X3_VERIFY_PASS 5 7",flush=True)

def native_run(c,rep,mode,binary,budget=None):
    src=source(c);nv,cs=x2.parse(src)
    use=path(c,mode)
    need(sha(src.read_bytes())==c["sha256"],"source drift")
    env=None
    if budget is not None:
        import os
        env=os.environ.copy();env["DRNAS_MAX_CONFLICTS"]=str(budget)
    begin=time.perf_counter()
    p=None
    try:
        p=subprocess.run([str(pathlib.Path(binary).resolve()),str(use.resolve()),
          "x_native",str(base.seed(c,rep))],capture_output=True,text=True,errors="replace",
          check=False,timeout=(CAP if budget is None else 15),env=env)
    except subprocess.TimeoutExpired:pass
    wall=time.perf_counter()-begin
    status="TIMEOUT";gate=None;stat=None;stages=None;verified=False
    if p is not None:
        need(p.returncode==0,"native exited nonzero: "+p.stderr[-700:])
        gate=base.parse_gate(p.stdout,"x_native")
        need(not gate["applied"],"stage binary changed source CNF")
        marks=[x.split(" ",1)[1] for x in p.stdout.splitlines()
               if x.startswith("MRE_X3_STAGE ")]
        need(len(marks)==1,"missing native stage telemetry")
        stages=json.loads(marks[0])
        need(not stages["root_unsat"] or c["reference_status"]=="UNSAT",
             "root UNSAT on reference SAT")
        need(stages["working_clauses"]==len(cs) and
             stages["clauses_loaded"]<=len(cs),"stage count wrong")
        m=re.search(r"^R195_RESULT status=(SAT|UNSAT|BUDGET|UNKNOWN) conflicts=(\d+) decisions=(\d+) propagations=(\d+) source_rows=(\d+) derived_rows=(\d+)$",
             p.stdout,re.M)
        need(m is not None,"no original-native CDCL stats")
        status=m.group(1)
        stat=dict(conflicts=int(m.group(2)),decisions=int(m.group(3)),
                  propagations=int(m.group(4)),source_rows=int(m.group(5)),
                  derived_rows=int(m.group(6)))
        if status=="SAT":
            verdict,model,_=base.cms.parsed_native(p.stdout)
            need(verdict=="SAT","inconsistent native model")
            base.cms.verify_model(src,model);verified=True
        if status in ("SAT","UNSAT"):
            need(status==c["reference_status"],"wrong source SAT/UNSAT")
    if budget is None and (status not in ("SAT","UNSAT") or wall>CAP):
        status="TIMEOUT";verified=False
    if budget is not None:
        need(status in ("SAT","UNSAT","BUDGET"),"unexpected bounded status")
    mode_record=dict(protocol=PROTO,sha256=c["sha256"],gbd=c["gbd"],
        reference_status=c["reference_status"],mode=mode,
        rep=rep,seed=base.seed(c,rep),status=status,wall_s=round(wall,6),
        native_stats=stat,stages=stages,SAT_original_witness_verified=verified,
        UNSAT_reference_no_LRAT=(status=="UNSAT"),bounded=(budget is not None))
    if budget is None:mode_record["PAR2_s"]=round(
        wall if status in ("SAT","UNSAT") else 2*CAP,6)
    else:mode_record["conflict_budget"]=budget
    return mode_record

def shard(idx,binary):
    need(0<=idx<SHARDS,"wrong shard")
    cc=[c for i,c in enumerate(source_cases()) if i%SHARDS==idx]
    arr=[]
    for c in cc:
        for rep in range(REPS):
            order=list(MODES)
            random.Random(int(sha((PROTO+"|ORDER|"+c["sha256"]+"|"+str(rep))
                     .encode())[:16],16)).shuffle(order)
            for mode in order:
                row=native_run(c,rep,mode,binary)
                arr.append(row);dump(OUT/("shard-%d.json"%idx),arr)
                print("MRE_X3_TRIAL",json.dumps(row,sort_keys=True),flush=True)
    need(len(arr)==len(cc)*REPS*len(MODES),"short shard")
    print("MRE_X3_SHARD_PASS",idx,len(arr),flush=True)

def bounded(binary):
    cc={c["sha256"]:c for c in source_cases()}
    arr=[]
    for key in DIAG_CASES:
        c=cc[key]
        for cap in BUDGETS:
            for mode in MODES:
                row=native_run(c,0,mode,binary,budget=cap)
                arr.append(row);dump(OUT/"bounded.json",arr)
                print("MRE_X3_BOUNDED",json.dumps(row,sort_keys=True),flush=True)
    need(len(arr)==4*3*7,"not 84 bounded diagnostics")
    print("MRE_X3_BOUNDED_PASS",len(arr),flush=True)

def audit():
    cs=source_cases();obs=set();rows=[]
    for i in range(SHARDS):
        p=OUT/("shard-%d.json"%i)
        need(p.exists(),"missing shard")
        rows.extend(json.loads(p.read_text()))
    need(len(rows)==EXPECTED,"not 140 trials")
    bysha={c["sha256"]:c for c in cs}
    for r in rows:
        c=bysha.get(r["sha256"])
        need(c and r["gbd"]==c["gbd"] and r["protocol"]==PROTO,"source mismatch")
        need(r["rep"] in range(REPS) and r["mode"] in MODES and
             r["seed"]==base.seed(c,r["rep"]),"not paired")
        need(r["status"] in ("SAT","UNSAT","TIMEOUT"),"unexpected status")
        need(r["status"]=="TIMEOUT" or r["status"]==c["reference_status"],
             "unverified verdict")
        if r["status"]=="SAT":need(r["SAT_original_witness_verified"],"SAT witness false")
        if r["status"]=="UNSAT":need(r["UNSAT_reference_no_LRAT"],"UNSAT no reference")
        if r["status"]=="TIMEOUT":need(r["PAR2_s"]==2*CAP,"bad PAR2 timeout")
        k=(r["sha256"],r["rep"],r["mode"])
        need(k not in obs,"duplicate triple");obs.add(k)
    need(len(obs)==EXPECTED,"missing trial")
    score={}
    for mode in MODES:
        a=[r for r in rows if r["mode"]==mode]
        stages=[r["stages"] for r in a if r["stages"]]
        solved=[r for r in a if r["status"]!="TIMEOUT"]
        score[mode]=dict(n=len(a),solved=len(solved),timeouts=len(a)-len(solved),
         PAR2_s=round(sum(r["PAR2_s"] for r in a),6),
         avg_add_s=round(sum(s["add_s"] for s in stages)/len(stages),6),
         avg_solve_s=round(sum(s["solve_s"] for s in stages)/len(stages),6),
         native_conflicts_solved=sum(r["native_stats"]["conflicts"] for r in solved))
    orig=score["original"]["PAR2_s"]
    for x in score.values():x["speedup_vs_original"]=round(orig/x["PAR2_s"],6)
    sub=[]
    for c in cs:
        a=[r for r in rows if r["sha256"]==c["sha256"]]
        sub.append(dict(sha256=c["sha256"],gbd=c["gbd"],status=c["reference_status"],
          PAR2={mode:round(sum(r["PAR2_s"] for r in a if r["mode"]==mode),6)
              for mode in MODES},
          solved={mode:sum(r["status"]!="TIMEOUT" for r in a if r["mode"]==mode)
              for mode in MODES},
          by_seed=[dict(rep=rep,rows={m:next((x for x in a
                if x["rep"]==rep and x["mode"]==m),None) for m in MODES})
                for rep in range(REPS)]))
    bounded_file=OUT/"bounded.json";diagnostic=None
    if bounded_file.exists():
        b=json.loads(bounded_file.read_text())
        need(len(b)==84,"bounded diag not complete")
        diagnostic=[dict(sha256=key,budget=cap,
                  modes={m:next((x for x in b if x["sha256"]==key
                     and x["conflict_budget"]==cap and x["mode"]==m),None)
                      for m in MODES})
               for key in DIAG_CASES for cap in BUDGETS]
    result=dict(protocol=PROTO,n=len(rows),source_count=len(cs),seed_count=REPS,
      cap_s=CAP,development_not_blind=True,original_CNF_models_verified=True,
      UNSAT_reference_no_LRAT=True,no_auto_promotion=True,
      separate_bounded_not_PAR2=True,score=score,per_source=sub,bounded=diagnostic)
    dump(OUT/"report.json",result)
    print("MRE_X3_FINAL",json.dumps({k:v for k,v in result.items()
        if k not in ("per_source","bounded")},sort_keys=True),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("selftest","freeze","verify","shard","bounded","audit"))
    p.add_argument("--shard",type=int,default=0)
    p.add_argument("--native",default="mre_x3/bin/native")
    args=p.parse_args()
    if args.action=="selftest":test_self()
    elif args.action=="freeze":freeze()
    elif args.action=="verify":verify()
    elif args.action=="shard":shard(args.shard,args.native)
    elif args.action=="bounded":bounded(args.native)
    else:audit()
