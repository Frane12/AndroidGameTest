#!/usr/bin/env python3
"""DRNAS-YALSAT005-FRESH2026-v1: frozen, SHA-paired, predeclared holdout.

Arms: pure CMS 5.11.15 vs YalSAT (0.05s) followed by pure CMS.
Official cohort: NEW chosen 2026 SAT Competition Main originals from canonical
GBD index, excluding tracked previous DRNAS source IDs and R1/R2 frozen SHA.
This checks only known exposure; global novelty across all untracked artifacts
cannot be established. Synthetic cohort: newly generated seeds, never used in
the preceding YalSAT R1/R2 benchmark. NEVER pool cohorts for real-world claim.
No tuning on these sources before all attempts complete.
"""
from __future__ import annotations
import argparse, bz2, collections, csv, gzip, hashlib, io, json, lzma
import os, pathlib, random, re, subprocess, sys, time, urllib.request

sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import drnas_yalsat_scout as r1

ROOT=pathlib.Path("drnas_yalsat_unseen")
FROZEN=ROOT/"frozen"
PROTO="DRNAS-YALSAT005-UNSEEN2026-REAL8-SYN16-3REPS-30S-v1"
SALT="DRNAS-YALSAT005-UNSEEN-OFFICIAL-20261108-SHA-SORT-V1"
SYN_SALT="DRNAS-YALSAT-UNSEEN-SYNTHETIC-20261108-v1"
URI="https://satcompetition.github.io/2026/downloads/track_main_2026.uri"
SCORES="https://satcompetition.github.io/2026/downloads/scores.csv"
GBD="https://benchmark-database.de/file/"
TARGET_REAL=8
MIN_REAL=6
MAX_ATTEMPTS=200
TARGET_SYN=16
SHARDS=8
REPS=3
CAP=30.
SCOUT=.05
MAX_COMPRESSED=18*1024*1024
MAX_DECOMPRESSED=24*1024*1024
MODES=("cms","yalsat005_cms")

def need(ok,msg):
    if not ok:raise RuntimeError("Y005_FRESH_FAIL_CLOSED: "+str(msg))

def digest(p):
    h=hashlib.sha256()
    with open(p,"rb") as f:
        for b in iter(lambda:f.read(1<<20),b""):h.update(b)
    return h.hexdigest()

def sha_bytes(b):return hashlib.sha256(b).hexdigest()

def save(p,obj):
    p=pathlib.Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(obj,sort_keys=True,indent=2)+"\n")

def fetch(url,max_len,timeout=25):
    req=urllib.request.Request(url,headers={
        "User-Agent":"DRNAS-YalSAT-unseen2026-v1 research benchmark",
        "Accept":"application/octet-stream"})
    with urllib.request.urlopen(req,timeout=timeout) as r:
        cl=r.headers.get("Content-Length")
        if cl and int(cl)>max_len:
            raise ValueError("file over precommitted compressed limit")
        raw=r.read(max_len+1)
        need(len(raw)<=max_len,"source compressed limit")
        return raw,r.geturl()

def decompress(data):
    if data.startswith(b"\xfd7zXZ\x00"):
        f=lzma.LZMAFile(io.BytesIO(data));kind="xz"
    elif data.startswith(b"\x1f\x8b"):
        f=gzip.GzipFile(fileobj=io.BytesIO(data));kind="gzip"
    elif data.startswith(b"BZh"):
        f=bz2.BZ2File(io.BytesIO(data));kind="bzip2"
    else:
        need(len(data)<=MAX_DECOMPRESSED,"plain CNF over limit")
        return data,"plain"
    with f:
        out=f.read(MAX_DECOMPRESSED+1)
    need(len(out)<=MAX_DECOMPRESSED,"decompressed CNF over limit")
    return out,kind

def metadata(data):
    headers=[x for x in data.splitlines() if x.startswith(b"p cnf ")]
    need(len(headers)==1,"DIMACS must have exactly one header")
    hdr=headers[0].split()
    need(len(hdr)==4,"DIMACS header invalid")
    n,m=map(int,hdr[2:])
    need(0<n<=50000000 and 0<m<=100000000,"bad CNF dimensions")
    return n,m

def known_exposure():
    """Best-effort frozen disclosure registry: checked-in textual IDs and R1 inputs."""
    ids=set(); hashes=set()
    p=subprocess.run(["git","grep","-I","-o","-E","[[:xdigit:]]{32,64}","--",
       "*.py","*.json","*.yml","*.yaml","*.md","*.txt","*.csv","*.sql"],
       capture_output=True,text=True,errors="replace")
    need(p.returncode in (0,1),"git grep failed")
    for l in p.stdout.splitlines():
        s=l.rsplit(":",1)[-1].lower()
        if re.fullmatch(r"[0-9a-f]{32}",s):ids.add(s)
        elif re.fullmatch(r"[0-9a-f]{64}",s):hashes.add(s)
    previous=r1.FROZEN/"manifest.json"
    need(digest(previous)==r1.SOURCE_SHA,"old R1/R2 input manifest changed")
    x=json.loads(previous.read_text())
    for c in x["cases"]:
        hashes.add(c["sha256"])
        if re.fullmatch(r"[a-f0-9]{32}",c["id"]):ids.add(c["id"])
    return ids,hashes

def real_index():
    raw,_=fetch(URI,1024*1024)
    urls=[s.strip() for s in raw.decode().splitlines() if s.strip().startswith("http")]
    ids=[s.rsplit("/",1)[-1] for s in urls]
    need(len(ids)==400 and len(set(ids))==400,"official 2026 URI list changed")
    raw_scores,_=fetch(SCORES,32*1024*1024)
    table=list(csv.DictReader(io.StringIO(raw_scores.decode("utf-8-sig"))))
    ref=[r for r in table if r.get("solverid")=="biere_cadical3[main]"]
    need(len(ref)==400,"official verified status table not complete")
    byid={r["instanceid"]:r["status"] for r in ref}
    need(set(ids)==set(byid),"status IDs inconsistent with official URI list")
    return ids,byid,sha_bytes(raw),sha_bytes(raw_scores)

def planted_three(i,seed):
    rng=random.Random(seed)
    n=180+18*i
    m=int(n*3.85)
    plant={x:bool(rng.randrange(2)) for x in range(1,n+1)}
    clauses=[]
    for _ in range(m):
        vars=rng.sample(range(1,n+1),3)
        clause=[v if rng.randrange(2) else -v for v in vars]
        if not any(plant[abs(q)]==(q>0) for q in clause):
            k=rng.randrange(3);v=vars[k];clause[k]=v if plant[v] else -v
        clauses.append(clause)
    return n,clauses,"SAT"

def xor_sat(i,seed):
    rng=random.Random(seed)
    n=75+10*(i-6)
    plant={x:bool(rng.randrange(2)) for x in range(1,n+1)}
    clauses=[]
    for _ in range(2*n):
        vars=rng.sample(range(1,n+1),3)
        parity=sum(plant[v] for v in vars)%2
        for bits in range(8):
            chosen=[bool(bits&(1<<k)) for k in range(3)]
            if sum(chosen)%2==parity:continue
            # Exclude exactly this assignment.
            clauses.append([-v if chosen[k] else v for k,v in enumerate(vars)])
    return n,clauses,"SAT"

def pigeonhole(i):
    pigeons=7+(i-12)
    holes=pigeons-1
    n=pigeons*holes
    var=lambda p,h:p*holes+h+1
    clauses=[]
    for p in range(pigeons):
        clauses.append([var(p,h) for h in range(holes)])
    for h in range(holes):
        for a in range(pigeons):
            for b in range(a+1,pigeons):
                clauses.append([-var(a,h),-var(b,h)])
    return n,clauses,"UNSAT"

def freeze():
    FROZEN.mkdir(parents=True,exist_ok=True)
    known_ids,known_hashes=known_exposure()
    ids,labels,uri_sha,scores_sha=real_index()
    ranked=sorted((gbd for gbd in ids if
           gbd not in known_ids and labels[gbd] in ("sat-verified","unsat-verified")),
           key=lambda x:sha_bytes((SALT+x).encode()))
    need(len(ranked)>=MAX_ATTEMPTS,"unseen eligible official pool too small")
    real=[];attempts=[]
    for index,gbd in enumerate(ranked[:MAX_ATTEMPTS]):
        if len(real)>=TARGET_REAL:break
        item=dict(rank=index,gbd=gbd,source=GBD+gbd,
                  official_status=labels[gbd])
        try:
            raw,redirect=fetch(GBD+gbd,MAX_COMPRESSED,timeout=20)
            out,kind=decompress(raw)
            n,m=metadata(out)
            digest=sha_bytes(out)
            need(digest not in known_hashes,"source SHA previously exposed")
            need(digest not in {c["sha256"] for c in real},"duplicate CNF SHA")
            name="official-"+gbd+".cnf"
            (FROZEN/name).write_bytes(out)
            c=dict(name=name,gbd=gbd,sha256=digest,bytes=len(out),
                   family="official_2026",cohort="official_2026_new_to_tracked",
                   source=GBD+gbd,official_status=labels[gbd],
                   expected=("SAT" if labels[gbd]=="sat-verified" else "UNSAT"),
                   variables=n,clauses=m,compression=kind,raw_sha256=sha_bytes(raw))
            real.append(c)
            item.update(state="SELECTED",sha256=digest,bytes=len(out))
        except Exception as exc:
            item.update(state="EXCLUDED_DOWNLOAD_SIZE_OR_KNOWN_SHA",
                       reason=(type(exc).__name__+": "+str(exc))[:180])
        attempts.append(item)
        print("Y005_FRESH_SOURCE",json.dumps(item,sort_keys=True),flush=True)
    need(len(real)>=MIN_REAL,"insufficient unseen official 2026 originals")
    synthetic=[]
    for i in range(TARGET_SYN):
        seed=int(sha_bytes((SYN_SALT+"/"+str(i)).encode())[:16],16)
        if i<6:n,clauses,status=planted_three(i,seed);family="planted_3sat"
        elif i<12:n,clauses,status=xor_sat(i,seed);family="xor_parity_sat"
        else:n,clauses,status=pigeonhole(i);family="pigeonhole_unsat"
        content="c DRNAS new independent synthetic SHA-frozen holdout seed %d\n"%seed
        content+="p cnf %d %d\n"%(n,len(clauses))
        content+="".join(" ".join(map(str,c))+" 0\n" for c in clauses)
        name="fresh-syn-%02d.cnf"%i
        p=FROZEN/name;p.write_text(content)
        s=digest(p)
        need(s not in known_hashes and s not in {c["sha256"] for c in real+synthetic},
             "synthetic source unexpectedly reused")
        synthetic.append(dict(name=name,sha256=s,bytes=p.stat().st_size,
             seed=seed,cohort="fresh_synthetic",family=family,expected=status,
             variables=n,clauses=len(clauses),source="new fixed 20261108 generator"))
    all_cases=real+synthetic
    need(len(all_cases)>=MIN_REAL+16,"incomplete holdout")
    manifest=dict(protocol=PROTO,selection_salt=SALT,synthetic_salt=SYN_SALT,
        source_manifest_sha256_prior=r1.SOURCE_SHA,
        official_uri=URI,official_uri_sha256=uri_sha,
        official_scores=SCORES,official_scores_sha256=scores_sha,
        prior_checked_in_32hex_exclusion_count=len(known_ids),
        prior_checked_in_64hex_exclusion_count=len(known_hashes),
        official_attempts=attempts,
        known_exposure_limitations=[
         "Scanned tracked text and R1/R2 source hashes; cannot exclude all old off-repository artifacts",
         "Precommitted selection based only on official 2026 membership and size/download feasibility",
         "Real and newly generated synthetic cohorts must be reported separately",
         "Historical 2026 competition instances, not new 2026 submissions by this project"],
        official_count=len(real),synthetic_count=len(synthetic),
        cases=all_cases)
    save(FROZEN/"manifest.json",manifest)
    (FROZEN/"source.sha256").write_text(
        "".join(c["sha256"]+"  "+c["name"]+"\n" for c in all_cases))
    print("Y005_FRESH_FREEZE_PASS",len(real),len(synthetic),flush=True)

def load():
    m=json.loads((FROZEN/"manifest.json").read_text())
    need(m["protocol"]==PROTO and m["synthetic_count"]==16,"manifest protocol changed")
    need(MIN_REAL<=m["official_count"]<=TARGET_REAL,"official cohort count")
    need(len(m["cases"])==m["official_count"]+16,"missing frozen sources")
    need(len({c["sha256"] for c in m["cases"]})==len(m["cases"]),"duplicate CNF SHA")
    for c in m["cases"]:
        p=FROZEN/c["name"]
        need(p.stat().st_size==c["bytes"] and digest(p)==c["sha256"],"SHA pin drift "+c["name"])
    return m

def one(c,rep,mode,yals,cms):
    path=(FROZEN/c["name"]).resolve()
    st=time.perf_counter()
    # Causal: no label, cohort, family or expected outcome used to select the arm.
    seed=int(sha_bytes((PROTO+c["sha256"]+str(rep)).encode())[:12],16)
    chain=[]
    if mode=="yalsat005_cms":
        rem=max(.01,min(SCOUT,CAP-(time.perf_counter()-st)))
        pilot=r1.invoke("yalsat",path,rem,0,seed,"",cms,yals)
        chain.append(dict(solver="yalsat",elapsed_s=round(pilot["elapsed"],6),
                          status=pilot["status"],proof=pilot["proof"]))
        if pilot["status"]=="SAT":result=pilot
        else:
            rem=max(0,CAP-(time.perf_counter()-st))
            result=r1.invoke("cms",path,rem,0,seed,"",cms,yals)
            chain.append(dict(solver="cms",elapsed_s=round(result["elapsed"],6),
                              status=result["status"],proof=result["proof"]))
    else:
        rem=max(0,CAP-(time.perf_counter()-st))
        result=r1.invoke("cms",path,rem,0,seed,"",cms,yals)
        chain.append(dict(solver="cms",elapsed_s=round(result["elapsed"],6),
                          status=result["status"],proof=result["proof"]))
    elapsed=time.perf_counter()-st
    status=result["status"] if elapsed<CAP else "TIMEOUT"
    if status!="TIMEOUT":
        need(status==c["expected"],"expected known official/generator status disagrees")
    return dict(protocol=PROTO,id=c["name"],source_sha256=c["sha256"],
         family=c["family"],cohort=c["cohort"],rep=rep,mode=mode,
         status=status,elapsed_s=round(elapsed,6),par2_s=round(
             CAP*2 if status=="TIMEOUT" else elapsed,6),
         proof=result["proof"] if status!="TIMEOUT" else "CAP_TIMEOUT",
         chain=chain,seed=seed,sha_verified=True,
         runner=os.environ.get("RUNNER_NAME","local"),
         commit=os.environ.get("GITHUB_SHA","local"),
         run_id=os.environ.get("GITHUB_RUN_ID","local"))

def shard(k,yals,cms):
    m=load();cs=m["cases"]
    need(0<=k<SHARDS,"invalid shard")
    rows=[]
    # Assign by stable position within frozen manifest.
    for c in cs[k::SHARDS]:
        for rep in range(REPS):
            order=list(MODES)
            random.Random(c["sha256"]+"/"+str(rep)+"/Y005-FRESH").shuffle(order)
            for mode in order:
                r=one(c,rep,mode,yals,cms)
                rows.append(r)
                save(ROOT/("shard-%d.json"%k),rows)
                print("Y005_FRESH_TRIAL",json.dumps({x:r[x] for x in
                     ("id","cohort","mode","rep","status","elapsed_s","par2_s","chain")},
                     sort_keys=True),flush=True)
    need(len(rows)==len(cs[k::SHARDS])*REPS*len(MODES),"shard incomplete")
    print("Y005_FRESH_SHARD_PASS",k,len(rows),flush=True)

def audit():
    m=load();cs=m["cases"];bysha={c["sha256"]:c for c in cs}
    rows=[]
    for i in range(SHARDS):
        vals=json.loads((ROOT/("shard-%d.json"%i)).read_text())
        need(len(vals)==len(cs[i::SHARDS])*REPS*len(MODES),"incomplete shard "+str(i))
        rows+=vals
    need(len(rows)==len(cs)*REPS*len(MODES),"total attempts invalid")
    pairs=collections.defaultdict(dict)
    for r in rows:
        need(r["source_sha256"] in bysha and
             r["id"]==bysha[r["source_sha256"]]["name"],"case metadata drift")
        key=(r["source_sha256"],r["rep"])
        need(r["mode"] not in pairs[key],"duplicate pair")
        pairs[key][r["mode"]]=r
        need(abs(r["par2_s"]-(CAP*2 if r["status"]=="TIMEOUT" else r["elapsed_s"]))<1e-5,
             "PAR2 accounting")
        if r["status"]=="SAT":
            need(r["proof"]=="SAT_WITNESS_CHECKED_ORIGINAL","unverified SAT")
    need(len(pairs)==len(cs)*REPS,"missing pairs")
    for rr in pairs.values():
        need(set(rr)==set(MODES),"incomplete matched pair")
        need(len({v["status"] for v in rr.values() if v["status"]!="TIMEOUT"})<=1,
             "contradictory terminal statuses")
    summary={}
    for cohort in ("official_2026_new_to_tracked","fresh_synthetic","all"):
        subset=[r for r in rows if cohort=="all" or r["cohort"]==cohort]
        summary[cohort]={}
        for mode in MODES:
            rr=[r for r in subset if r["mode"]==mode]
            summary[cohort][mode]=dict(attempts=len(rr),
                SAT=sum(r["status"]=="SAT" for r in rr),
                UNSAT=sum(r["status"]=="UNSAT" for r in rr),
                TIMEOUT=sum(r["status"]=="TIMEOUT" for r in rr),
                solved=sum(r["status"]!="TIMEOUT" for r in rr),
                par2_sum_s=round(sum(r["par2_s"] for r in rr),6),
                par2_mean_s=round(sum(r["par2_s"] for r in rr)/len(rr),6),
                pilot_sat=sum(r["chain"][0]["solver"]=="yalsat" and
                              r["chain"][0]["status"]=="SAT" for r in rr))
    report=dict(status="Y005_FRESH_AUDIT_PASS",protocol=PROTO,
       sources=len(cs),official=m["official_count"],synthetic=16,
       reps=REPS,attempts=len(rows),cap_s=CAP,scout_s=SCOUT,
       original_sha_pinned=True,source_manifest_sha256=digest(FROZEN/"manifest.json"),
       source_selection="deterministic prior-exposure-excluded official 2026 + new synthetic",
       novelty_limitations=m["known_exposure_limitations"],
       SAT_original_witness_checked=True,
       UNSAT_independent_certificate=False,
       official_2026_not_official_competition_ranking=True,
       summaries=summary)
    save(ROOT/"report.json",report)
    save(ROOT/"all-trials.json",rows)
    print("Y005_FRESH_FINAL",json.dumps(report,sort_keys=True),flush=True)

def smoke():
    rng=random.Random(123)
    n,clauses,status=planted_three(1,123)
    assert len(clauses)>n and status=="SAT"
    n,clauses,status=xor_sat(6,123)
    assert n>0 and all(len(x)==3 for x in clauses)
    n,clauses,status=pigeonhole(12)
    assert status=="UNSAT" and len(clauses)>0
    print("Y005_FRESH_SELFTEST_PASS",flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("selftest","freeze","verify","shard","audit"))
    p.add_argument("--shard",type=int,default=0)
    p.add_argument("--yals",default="drnas_yalsat/yalsat")
    p.add_argument("--cms",default="cryptominisat5")
    a=p.parse_args()
    if a.action=="selftest":smoke()
    elif a.action=="freeze":freeze()
    elif a.action=="verify":
        m=load();print("Y005_FRESH_VERIFY_PASS",len(m["cases"]),m["official_count"],flush=True)
    elif a.action=="shard":shard(a.shard,a.yals,a.cms)
    else:audit()
