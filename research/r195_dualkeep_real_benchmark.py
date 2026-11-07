#!/usr/bin/env python3
"""DRNAS R195: precommitted dual-keep real CNF benchmark with causal controls.

25 previously used R193 real GBD instances plus up to 12 selected official
SAT Competition 2026 original CNFs (if objectively fetchable within frozen
size/timeout criteria). Official set selection is SHA-order before solving.
No result-, source-ID- or SAT-label-based policy. Original CNF SHA per run.
No claim official 2026 IDs have never appeared in OTHER prior DRNAS builds.
7 modes x 2 repetitions; 30/45 sec cap; test overhead fully wall charged.
"""
import argparse,bz2,collections,gzip,hashlib,json,lzma,pathlib,random,re,subprocess,time,urllib.request
import r188_feedback_benchmark as helpers

ROOT=pathlib.Path("r195")
FROZEN=ROOT/"frozen"
PROTO="DRNAS-R195-DUALKEEP-REAL-CAUSAL-PROSPECTIVE-20261107-v1"
URI="https://raw.githubusercontent.com/satcompetition/2026/main/downloads/track_main_2026.uri"
PREVIOUS_SHA="9eebc6fc1e8ad3006fc3ecc8b451e1e57d3087932190ba5a91fd60aabf278658"
ARMS=("default","sat","split128","split256","dual_keep_default",
      "dual_keep_sat","dual_keep_guarded")
REPS=2
SHARDS=8
MAX_COMPRESSED=4*1024*1024
MAX_ORIGINAL=28*1024*1024
MAX_ATTEMPT=36
TARGET_NEW=12

def need(ok,msg):
    if not ok:raise RuntimeError("R195_FAIL_CLOSED "+str(msg))
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def load(p):return json.loads(pathlib.Path(p).read_text())
def save(p,data):
    p=pathlib.Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(data,sort_keys=True,indent=2)+"\n")

def selftest():
    need(len(ARMS)==7 and len(set(ARMS))==7,"mode preregistration")
    need(TARGET_NEW==12 and MAX_ATTEMPT==36,"source selection modified")
    need(REPS==2 and SHARDS==8,"repetition/matrix changed")
    for head in ("p cnf 10 20\n1 -2 0\n","c comment\np cnf 3 1\n1 0\n"):
        need(re.search(r"(?m)^p cnf \d+ \d+\s*$",head),"bad DIMACS parser")
    print("R195_SELFTEST_PASS",flush=True)

def download_bytes(url,max_bytes=MAX_COMPRESSED,timeout=14):
    req=urllib.request.Request(url,headers={"User-Agent":"DRNAS-Research-R195/1.0"})
    with urllib.request.urlopen(req,timeout=timeout) as res:
        data=res.read(max_bytes+1)
    need(0<len(data)<=max_bytes,"download exceeds compressed size cap")
    return data

def decode_cnf(data):
    try:
        if data.startswith(b"\x1f\x8b"):data=gzip.decompress(data)
        elif data.startswith(b"BZh"):data=bz2.decompress(data)
        elif data.startswith(b"\xfd7zXZ\x00"):data=lzma.decompress(data)
        elif data.startswith(b"\x28\xb5\x2f\xfd"):
            with subprocess.Popen(["zstd","-d","-q","-c"],stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE,stderr=subprocess.PIPE) as p:
                out,err=p.communicate(input=data,timeout=8)
                need(p.returncode==0,"zstd decompression failure: "+err[-100:].decode(errors="replace"))
                data=out
    except Exception as e:
        raise ValueError("decompression error: "+str(e))
    need(20<len(data)<=MAX_ORIGINAL,"CNF original too large or empty")
    # A strong syntactic gate without rewriting or preprocessing the original.
    head=data[:40000].decode("ascii")
    need(re.search(r"(?m)^p cnf [1-9]\d* [1-9]\d*\s*$",head),
         "not a valid DIMACS CNF header")
    need(b"\x00" not in data[:2000],"binary payload not CNF")
    return data

def freeze():
    source=ROOT/"source"/"frozen"
    need(sha(source/"manifest.json")==PREVIOUS_SHA,
         "R193 original manifest not identical")
    old=load(source/"manifest.json")["cases"]
    cases=[]
    FROZEN.mkdir(parents=True,exist_ok=True)
    previous_ids=set()
    for c in old:
        if c["cohort"]!="reused_external_original":continue
        name=c["id"];previous_ids.add(name)
        p=source/(name+".cnf")
        need(sha(p)==c["sha256"],"known real source unexpectedly changed")
        (FROZEN/(name+".cnf")).write_bytes(p.read_bytes())
        cases.append(dict(id=name,cohort="reused_real_r193",
            source="R193 exact GBD original",expected=c["expected"],
            original_sha256=c["sha256"],cap_s=30.0))
    need(len(cases)==25,"not 25 archived real formulas")
    uri=download_bytes(URI,150000,14).decode("ascii").splitlines()
    urls=[x.strip() for x in uri if re.fullmatch(
        r"https?://benchmark-database\.de/file/[a-f0-9]{32}",x.strip())]
    need(len(urls)>100 and len(urls)==len(set(urls)),"official GBD index invalid")
    seed_order=sorted(urls,key=lambda x:hashlib.sha256((PROTO+x).encode()).hexdigest())
    attempts=[];fresh=0
    for url in seed_order:
        ident=url.split("/")[-1]
        if ident in previous_ids:continue
        if len(attempts)>=MAX_ATTEMPT or fresh>=TARGET_NEW:break
        try:
            data=None
            # Same GBD ID, always preserve downloaded original bytes.
            for target in (url.replace("http://","https://",1),url):
                try:
                    compressed=download_bytes(target,MAX_COMPRESSED,14)
                    data=decode_cnf(compressed)
                    break
                except Exception as e:
                    last=str(e)
            need(data is not None,last)
            digest=hashlib.sha256(data).hexdigest()
            need(digest not in {x["original_sha256"] for x in cases},
                 "duplicate original SHA")
            (FROZEN/(ident+".cnf")).write_bytes(data)
            cases.append(dict(id=ident,cohort="new_r193_holdout_official_2026",
                 source=url,expected="UNKNOWN",original_sha256=digest,cap_s=45.0))
            attempts.append(dict(id=ident,success=True,bytes=len(data)))
            fresh+=1
            print("R195_OFFICIAL_ACCEPT",ident,len(data),digest,flush=True)
        except Exception as e:
            attempts.append(dict(id=ident,success=False,error=str(e)[:180]))
            print("R195_OFFICIAL_REJECT",ident,str(e)[:180],flush=True)
    random.Random(PROTO).shuffle(cases)
    save(FROZEN/"manifest.json",dict(protocol=PROTO,
        source_list=URI,source_list_sha256=hashlib.sha256("\n".join(uri).encode()).hexdigest(),
        previous_manifest_sha256=PREVIOUS_SHA,
        official_selected_by_hash_precommitted=True,
        official_selected_after_size_and_availability_only=True,
        prior_R193_real_excluded_by_GBD_id=True,
        global_prior_DRNAS_exposure_not_verified=True,
        official_attempts=attempts,official_count=fresh,
        previous_real_count=25,cases=cases))
    verify()
    print("R195_FREEZE_PASS",json.dumps(dict(total=len(cases),known=25,
        official=fresh,manifest_sha256=sha(FROZEN/"manifest.json"))),flush=True)

def verify():
    d=load(FROZEN/"manifest.json")
    cases=d["cases"]
    need(d["protocol"]==PROTO and len(cases)==25+d["official_count"],
         "frozen source set mismatch")
    need(len({c["original_sha256"] for c in cases})==len(cases),
         "duplicated source SHA")
    for c in cases:
        need(sha(FROZEN/(c["id"]+".cnf"))==c["original_sha256"],
             "original CNF SHA mismatch: "+c["id"])
    return cases

def call_native(binary,source,cap,mode,order,seed):
    started=time.perf_counter()
    try:
        p=subprocess.run([str(binary.resolve()),str(source),str(cap),
                          mode,str(order),str(seed)],capture_output=True,
                         timeout=cap+4,check=False)
    except subprocess.TimeoutExpired:
        return dict(status="TIMEOUT",elapsed_s=time.perf_counter()-started,
             model={},policy={},stats={})
    elapsed=time.perf_counter()-started
    raw=p.stdout.decode(errors="replace")
    err=p.stderr.decode(errors="replace")
    need(p.returncode==0,"native driver failed: "+err[-500:])
    s=re.search(r"^R182_STATUS status=(SAT|UNSAT|TIMEOUT)\b",raw,re.M)
    q=re.search(r"^R195_POLICY choice=(default|sat) reason=(\w+) "
        r"actual_dual=(\d+) pilot_s=([0-9.]+) windows=(\d+) "
        r"declared_vars=(\d+) declared_clauses=(\d+) "
        r"learned_preserved=(\d+)$",raw,re.M)
    need(s is not None and q is not None,"native answer or policy telemetry missing")
    pol=dict(choice=q[1],reason=q[2],actual_dual=int(q[3]),
        pilot_s=float(q[4]),windows=int(q[5]),variables=int(q[6]),
        clauses=int(q[7]),preserved=int(q[8]))
    need(pol["pilot_s"]<=elapsed+1e-3,"pilot exceeds walltime")
    if mode.startswith("dual_") and mode!="dual_keep_guarded":
        need(pol["actual_dual"]==1,"dual arm bypassed without gate")
    model={}
    if s[1]=="SAT":
        for line in raw.splitlines():
            if line.startswith("v "):
                for lit in map(int,line[2:].split()):
                    if not lit:continue
                    need(abs(lit) not in model or model[abs(lit)]==(lit>0),
                         "native contradictory SAT witness")
                    model[abs(lit)]=lit>0
    return dict(status=s[1],elapsed_s=elapsed,model=model,
                policy=pol,stats=helpers.stats(raw))

def trial(c,mode,rep,binary):
    p=FROZEN/(c["id"]+".cnf")
    need(sha(p)==c["original_sha256"],"source drift at trial")
    order=int(hashlib.sha256((PROTO+c["original_sha256"]+str(rep)).encode()).hexdigest()[:5],16)%2
    seed=(11,23)[rep]
    cap=c["cap_s"]
    start=time.perf_counter()
    n=call_native(binary,p,cap,mode,order,seed)
    elapsed=time.perf_counter()-start
    status=n["status"]
    if elapsed>=cap:status="TIMEOUT"
    proof="UNSAT_BY_PINNED_CADICAL_NOT_INDEPENDENT_LRAT" if status=="UNSAT" else "CAP"
    if status=="SAT":
        _,clauses=helpers.gf.dimacs(p)
        helpers.gf.sat_check(clauses,n["model"])
        proof="SAT_MODEL_CHECKED_ORIGINAL"
    if c["expected"]!="UNKNOWN" and status!="TIMEOUT":
        need(status==c["expected"],"known expected result mismatch")
    return dict(id=c["id"],cohort=c["cohort"],source=c["source"],
       sha256=c["original_sha256"],mode=mode,rep=rep,
       order=order,seed=seed,cap_s=cap,status=status,
       elapsed_s=round(elapsed,6),
       par2_s=round(2*cap if status=="TIMEOUT" else elapsed,6),
       proof=proof,**n["policy"],**n["stats"])

def shard(idx,binary):
    cases=verify()
    need(0<=idx<SHARDS and binary.is_file(),"invalid shard/native")
    recs=[]
    for c in cases[idx::SHARDS]:
        for rep in range(REPS):
            modes=list(ARMS)
            random.Random(PROTO+c["original_sha256"]+str(rep)).shuffle(modes)
            for mode in modes:
                r=trial(c,mode,rep,binary)
                recs.append(r)
                save(ROOT/f"shard-{idx}.json",recs)
                print("R195_TRIAL",json.dumps({k:r.get(k) for k in
                  ("id","cohort","mode","rep","status","elapsed_s",
                   "pilot_s","choice","actual_dual","reason")},sort_keys=True),flush=True)
    need(len(recs)==len(cases[idx::SHARDS])*REPS*len(ARMS),
         "incomplete shard")
    print("R195_SHARD_PASS",idx,len(recs),flush=True)

def audit():
    cases=verify();allrows=[]
    for idx in range(SHARDS):
        p=load(ROOT/f"shard-{idx}.json")
        need(len(p)==len(cases[idx::SHARDS])*REPS*len(ARMS),
             "shard incomplete")
        allrows+=p
    need(len(allrows)==len(cases)*REPS*len(ARMS),
         "incomplete paired sample")
    hashes={c["original_sha256"]:c for c in cases}
    matched=collections.defaultdict(list)
    for r in allrows:
        need(r["sha256"] in hashes and r["id"]==hashes[r["sha256"]]["id"],
             "source identity mismatch")
        expect=r["elapsed_s"] if r["status"]!="TIMEOUT" else 2*r["cap_s"]
        need(abs(r["par2_s"]-expect)<1e-5,"invalid PAR2")
        matched[r["sha256"],r["rep"]].append(r)
    for c in cases:
        for rep in range(REPS):
            rr=matched[c["original_sha256"],rep]
            need(len(rr)==len(ARMS) and {x["mode"] for x in rr}==set(ARMS),
                 "missing paired arm")
            need(len({r["status"] for r in rr if r["status"]!="TIMEOUT"})<=1,
                 "contradictory solving outcomes")
            need(len({r["seed"] for r in rr})==1,"not same seed")
    cohorts={"all":cases}
    for cohort in ("reused_real_r193","new_r193_holdout_official_2026"):
        cohorts[cohort]=[c for c in cases if c["cohort"]==cohort]
    summary={}
    for cohort,subset in cohorts.items():
        modes={}
        for mode in ARMS:
            a=[x for c in subset for rep in range(REPS)
               for x in matched[c["original_sha256"],rep] if x["mode"]==mode]
            modes[mode]=dict(attempts=len(a),
               solved=sum(x["status"]!="TIMEOUT" for x in a),
               sat=sum(x["status"]=="SAT" for x in a),
               unsat=sum(x["status"]=="UNSAT" for x in a),
               par2_s=round(sum(x["par2_s"] for x in a),6),
               pilot_s=round(sum(x.get("pilot_s",0) for x in a),6),
               actual_dual=sum(x.get("actual_dual",0) for x in a),
               guard_bypass=sum(x.get("reason")=="small_source_guard" for x in a))
        ref=modes["default"]["par2_s"]
        sat=modes["sat"]["par2_s"]
        summary[cohort]=dict(formulas=len(subset),modes=modes,
          speedup_vs_default={m:round(ref/d["par2_s"],6) if d["par2_s"]>0 else None
                              for m,d in modes.items()},
          speedup_vs_sat={m:round(sat/d["par2_s"],6) if d["par2_s"]>0 else None
                          for m,d in modes.items()})
    report=dict(protocol=PROTO,status="R195_REAL_PAIRED_AUDIT_PASS",
       official_URI=URI,source_manifest_sha256=sha(FROZEN/"manifest.json"),
       attempts=len(allrows),formulas=len(cases),
       known_real_count=25,official_2026_count=len(cohorts["new_r193_holdout_official_2026"]),
       source_sha_verified_each_trial=True,
       SAT_witness_checked_on_original=True,
       UNSAT_not_independently_LRAT_verified=True,
       official_not_seen_in_R193=True,global_blind_history_unverified=True,
       fixed_guard_vars_lt=400,fixed_guard_clauses_lt=1200,
       same_pinned_seed_per_pair=True,groups=summary)
    save(ROOT/"report.json",report)
    save(ROOT/"all-trials.json",allrows)
    with (ROOT/"summary.md").open("w") as f:
        f.write("# R195: optimized dual keep on REAL SAT / official 2026 originals\n\n")
        f.write("25 previously seen external CNFs + up to 12 new-to-R193 official "
                "SAT2026 GBD samples selected by precommitted SHA order and only "
                "download availability/size. Every attempted source SHA frozen. "
                "7 matched modes, 2 seeds per source, 30/45s caps. "
                "The new IDs may have appeared in other DRNAS tests: NOT globally "
                "certified blind. SAT witnesses checked; UNSAT lacks independent LRAT.\n\n")
        f.write("| Cohort | Mode | Solved | PAR2 seconds | vs default | vs SAT |\n"
                "|---|---|---:|---:|---:|---:|\n")
        for group in ("reused_real_r193","new_r193_holdout_official_2026","all"):
            for mode,v in summary[group]["modes"].items():
                f.write(f"| {group} | {mode} | {v['solved']}/{v['attempts']} | "
                       f"{v['par2_s']} | {summary[group]['speedup_vs_default'][mode]} | "
                       f"{summary[group]['speedup_vs_sat'][mode]} |\n")
        f.write("\nDual_keep_guarded uses SAT-only for n<400 OR clauses<1200; "
                "otherwise the exact two-live R193 default-retention path. "
                "Split controls test whether interrupt/continue alone is causal.\n")
    print("R195_FINAL",json.dumps({k:summary[k] for k in
       ("reused_real_r193","new_r193_holdout_official_2026","all")},sort_keys=True),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("selftest","freeze","verify","shard","audit"))
    p.add_argument("--shard",type=int,default=0)
    p.add_argument("--binary",default="r195/r195-driver")
    a=p.parse_args()
    if a.action=="selftest":selftest()
    elif a.action=="freeze":freeze()
    elif a.action=="verify":print("R195_VERIFY_PASS",len(verify()),flush=True)
    elif a.action=="shard":shard(a.shard,pathlib.Path(a.binary))
    else:audit()
