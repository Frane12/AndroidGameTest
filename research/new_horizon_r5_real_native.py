#!/usr/bin/env python3
"""DRNAS New Horizon R5: first-contact 2026 external original SAT, native profiles.

Freeze GBD original DIMACS SHA and source-only cohort BEFORE running solvers.
Original source and same CaDiCaL 2.1 binary for all six arms:
default, sat profile, unsat profile, bounded source router, R4b, R4d.

"First contact" means SHA / IDs excluded from enumerated ledgers only;
not a guarantee a formula has never been used elsewhere.
"""
from __future__ import annotations

import argparse,collections,csv,hashlib,json,pathlib,random,re,subprocess,time
import r154_unseen_freeze as catalog
import r152_lightsout_unseen as old_sources
import new_horizon_r4b as r4b
import new_horizon_r4d as r4d
import new_horizon_sat as nh
import r182_mixed_engine as exact

ROOT=pathlib.Path("new_horizon_r5")
SRC=ROOT/"frozen"
PRIOR=ROOT/"prior-r183/frozen/manifest.json"
PROTO="DRNAS-NH-R5-PROSPECTIVE-EXTERNAL-MAIN2026-NATIVE6-v1"
FAMILIES=("cryptography","miter","xor-chain","linear-equations","lights-out")
TRACKS=("main_2026",)
QUOTA_PER_FAMILY=4
TARGET=16
MIN_CASES=12
MAX_ATTEMPTS=120
MAX_RAW_BYTES=7*1024*1024
MAX_PLAIN_BYTES=2_500_000
MAX_VARS=20_000
MAX_CLAUSES=170_000
REPS=2
SHARDS=8
CAP_S=8.0
ARMS=("default","sat","unsat","header_router","r4b","r4d")
KNOWN_R183_MANIFEST_SHA="102c8bdef78163aad8e08ab044c0ff7a123df4d67b0a714c50370b13447543c4"

def need(v,msg):
    if not v:raise AssertionError("NH_R5_FAIL_CLOSED "+str(msg))
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def load(p):return json.loads(pathlib.Path(p).read_text())
def save(p,obj):
    p=pathlib.Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(obj,sort_keys=True,indent=2)+"\n")

def historical():
    """Important: exclusion covers ONLY explicitly imported historical ledgers."""
    need(PRIOR.exists() and sha(PRIOR)==KNOWN_R183_MANIFEST_SHA,
         "R183 historical original-source ledger absent or drifted")
    old=load(PRIOR)
    need(len(old["cases"])==12,"R183 known original count mismatch")
    ids={str(x).lower() for x in old_sources.KNOWN_IDS|old_sources.OLD_R32P}
    shas=set()
    for c in old["cases"]:
        ids.add(str(c["id"]).lower())
        shas.add(c["sha256"].lower())
    old106=load("research/r106_manifest.json")
    for row in old106["cases"]:
        ids.add(row[2].lower())
        shas.add(row[3].lower())
    return ids,shas

def source_meta(path):
    """Only CNF header fields, no solver timings, no SAT/UNSAT labels."""
    n=m=None
    with pathlib.Path(path).open(encoding="ascii") as f:
        for line in f:
            if line.startswith("p cnf "):
                x=line.split()
                need(len(x)==4,"unsupported source header")
                n,m=int(x[2]),int(x[3])
                break
    need(n is not None and m is not None and n>=1 and m>=1,
         "CNF header missing or degenerate")
    return n,m

def freeze():
    SRC.mkdir(parents=True,exist_ok=True)
    ids,historical_shas=historical()
    found={};catalogs=[];errors={}
    for family in FAMILIES:
        for track in TRACKS:
            try:
                records,digest=catalog.get_catalog(family,track)
                catalogs.append(dict(family=family,track=track,
                                     records=len(records),sha256=digest))
                for c in records:
                    if c["id"] not in ids and c["id"] not in found:
                        found[c["id"]]=c
                print("NH_R5_GBD_CATALOG",family,track,len(records),flush=True)
            except Exception as e:
                errors[family]=type(e).__name__+":"+str(e)[:90]
                print("NH_R5_GBD_CATALOG_WARNING",family,str(e)[:120],flush=True)
    need(found,"no GBD main_2026 external entries available")
    pool=sorted(found.values(),key=lambda c:c["id"])
    random.Random(PROTO+"|PRECOMMITTED-NEW-SOURCE-ORDER").shuffle(pool)
    used_sha=set()
    chosen=[]
    skipped=collections.Counter()
    quotas=collections.Counter()
    for c in pool[:MAX_ATTEMPTS]:
        if len(chosen)>=TARGET:break
        if quotas[c["family"]]>=QUOTA_PER_FAMILY:
            skipped["family_quota"]+=1;continue
        try:
            compressed,_=catalog.orig.source.request_url(
                "https://benchmark-database.de/file/"+c["id"],
                 MAX_RAW_BYTES,seconds=25)
            plain,_=catalog.orig.source.decode(compressed)
            if not plain.startswith((b"c",b"p",b"\n")):
                raise ValueError("unexpected original text")
            if len(plain)>MAX_PLAIN_BYTES:
                skipped["source_bytes_limit"]+=1;continue
            digest=hashlib.sha256(plain).hexdigest()
            if digest in historical_shas or digest in used_sha:
                skipped["known_prior_sha_or_duplicate"]+=1;continue
            p=SRC/(c["id"]+".cnf")
            p.write_bytes(plain)
            n,m=source_meta(p)
            if n>MAX_VARS or m>MAX_CLAUSES:
                p.unlink()
                skipped["dimension_limit"]+=1;continue
            # Validate ORIGINAL content independent of any solver outcome.
            parsed_n,clauses=exact.dimacs(p)
            need(parsed_n==n and len(clauses)==m,
                 "source parser/header disagreement")
            case=dict(id=c["id"],source_sha256=digest,
                compressed_sha256=hashlib.sha256(compressed).hexdigest(),
                family=c["family"],track=c["track"],
                source="GBD_original_main_2026",
                source_n=n,source_m=m,bytes=len(plain),cap_s=CAP_S,
                expected_from_GBD_if_published=c["gbd_status"]
                    if c["gbd_status"] in ("sat","unsat") else "UNKNOWN")
            chosen.append(case)
            used_sha.add(digest);quotas[c["family"]]+=1
            print("NH_R5_REAL_FROZEN",len(chosen),c["id"],
                  c["family"],n,m,len(plain),flush=True)
        except Exception as e:
            skipped[type(e).__name__]+=1
            print("NH_R5_REAL_SKIPPED",c["id"],type(e).__name__,
                  str(e)[:100],flush=True)
            (SRC/(c["id"]+".cnf")).unlink(missing_ok=True)
    need(len(chosen)>=MIN_CASES,
         f"less than {MIN_CASES} SHA-disjoint real 2026 originals; abort")
    need(len({c["source_sha256"] for c in chosen})==len(chosen),
         "duplicate SHA on frozen real")
    random.Random(PROTO+"|FROZEN-PAIR-SHUFFLE").shuffle(chosen)
    save(SRC/"manifest.json",dict(protocol=PROTO,cases=chosen,
        source_catalogs=catalogs,catalog_errors=errors,
        candidates_before_filter=len(found),
        source_candidates_examined=min(MAX_ATTEMPTS,len(pool)),
        skipped=dict(skipped),prior_id_count=len(ids),
        prior_source_sha_count=len(historical_shas),
        historical_ledgers=["r152 known IDs","r106 source manifest",
                            "R183 SHA-pinned 12 original CNFs"],
        cannot_certify_globally_unseen=True,
        selection_source_only_before_any_R5_timing=True,
        status_metadata_not_used_for_source_choice_or_policy=True,
        identical_native_binary_all_arms=True,
        arms=ARMS,reps=REPS,shards=SHARDS,cap_seconds=CAP_S))
    verify()
    print("NH_R5_FREEZE_PASS",json.dumps({
         "sources":len(chosen),"family_counts":dict(quotas),
         "manifest_sha256":sha(SRC/"manifest.json"),
         "skipped":dict(skipped)}),flush=True)

def verify():
    obj=load(SRC/"manifest.json")
    need(obj["protocol"]==PROTO and MIN_CASES<=len(obj["cases"])<=TARGET,
         "frozen manifest protocol or count")
    for c in obj["cases"]:
        p=SRC/(c["id"]+".cnf")
        need(sha(p)==c["source_sha256"],
             "immutable original source SHA changed "+c["id"])
    need(len({c["source_sha256"] for c in obj["cases"]})==len(obj["cases"]),
         "repeated source in manifest")
    return obj["cases"]

def header_router(path):
    """Bounded first 96 clauses. All approximate signals affect PROFILE ONLY.

    CaDiCaL default, sat and unsat profiles are all complete SAT solvers.
    Any uncertain source falls back to default. Never changes a clause.
    """
    begin=time.perf_counter()
    n,m=source_meta(path)
    if n<100 or m<700:
        return ("default","metadata_too_small",
                time.perf_counter()-begin,None)
    sample=0;ternary=0;binary=0;horn=0
    literals=[]
    budget=24_000
    with pathlib.Path(path).open(encoding="ascii") as f:
        for line in f:
            budget-=len(line)
            if budget<0 or sample>=96:break
            if not line.strip() or line.startswith(("c","p","%")):continue
            for tok in line.split():
                v=int(tok)
                if v:
                    literals.append(v)
                else:
                    sample+=1
                    ternary+=len(literals)==3
                    binary+=len(literals)==2
                    horn+=sum(x>0 for x in literals)<=1
                    literals=[]
                    if sample>=96:break
    seconds=time.perf_counter()-begin
    if sample<32 or seconds>0.012:
        return ("default","limited_source_observer_abstained",seconds,None)
    f3=ternary/sample
    f2=binary/sample
    frac_horn=horn/sample
    density=m/max(1,n)
    prof="default";reason="conservative"
    if f2>=.40 or frac_horn>=.75:
        reason="binary_or_horn_default"
    elif f3>=.70 and density>=4.25:
        prof="unsat";reason="ternary_dense_profile"
    elif f3>=.70 and density<=3.20:
        prof="sat";reason="ternary_sparse_profile"
    else:
        reason="mixed_default"
    return prof,reason,seconds,dict(n=n,m=m,density=round(density,3),
                sampled=sample,p3=round(f3,3),p2=round(f2,3),
                phorn=round(frac_horn,3))

def native_profile(binary,source,remaining,profile):
    need(profile in ("default","sat","unsat"),"bad CaDiCaL profile")
    cmd=[str(pathlib.Path(binary).resolve()),str(pathlib.Path(source).resolve()),
         str(max(0.1,remaining)),profile]
    try:
        run=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                           timeout=remaining+3,check=False)
    except subprocess.TimeoutExpired:
        return "TIMEOUT",{},"process_timeout"
    need(run.returncode==0,
         "native solver driver errored "+run.stderr.decode(errors="replace")[-550:])
    output=run.stdout.decode(errors="replace")
    status=re.search(r"^R182_STATUS status=(SAT|UNSAT|TIMEOUT) solver_s=([0-9.]+) variables=(\d+)$",
                     output,re.M)
    need(status is not None,"native status missing")
    returned=re.search(r"^R190_PROFILE (default|sat|unsat)$",output,re.M)
    need(returned is not None and returned[1]==profile,"native profile not applied")
    model={}
    if status[1]=="SAT":
        for line in output.splitlines():
            if line.startswith("v "):
                for tok in line[2:].split():
                    x=int(tok)
                    if not x:continue
                    v=abs(x)
                    need(v not in model or model[v]==(x>0),
                         "conflicting native SAT witness")
                    model[v]=x>0
    return status[1],model,profile

def run_one(source,binary,cap,mode,scratch):
    need(mode in ARMS,"bad method")
    if mode in ("r4b","r4d"):
        result=r4d.run_one(source,binary,cap,mode,scratch)
        return dict(status=result["status"],elapsed_s=result["elapsed"],
            profile="default",route=result["route"],reason=result["reason"],
            proof=result["proof"],screen_s=0)
    started=time.perf_counter()
    profile=mode
    reason="static_profile"
    screen_s=0.
    if mode=="header_router":
        profile,reason,screen_s,_=header_router(source)
    remaining=cap-(time.perf_counter()-started)
    status="TIMEOUT";model={}
    if remaining>.14:
        status,model,_=native_profile(binary,source,remaining,profile)
    elapsed=time.perf_counter()-started
    if elapsed>=cap:
        status="TIMEOUT"
    if status=="SAT":
        nh.verify_model(source,model)
        proof="SOURCE_ORIGINAL_SAT_WITNESS_CHECKED"
    elif status=="UNSAT":
        proof="NATIVE_CDCL_UNSAT_NO_INDEPENDENT_LRAT"
    else:proof="TIME_LIMIT"
    return dict(status=status,elapsed_s=elapsed,profile=profile,
                route=profile,reason=reason,proof=proof,screen_s=screen_s)

def selftest():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p=pathlib.Path(d)/"smoke.cnf"
        p.write_text("p cnf 3 2\n1 0\n-1 2 0\n")
        profile,reason,s,_=header_router(p)
        need(profile=="default","small source leaked router profile")
    need(len(ARMS)==6 and REPS==2 and SHARDS==8 and CAP_S==8.0,
         "R5 frozen protocol drift")
    need(len(set(FAMILIES))==len(FAMILIES) and len(TRACKS)==1,
         "GBD source query drift")
    print("NH_R5_SELFTEST_PASS",flush=True)

def trial(c,mode,rep,binary):
    source=SRC/(c["id"]+".cnf")
    need(sha(source)==c["source_sha256"],"timed source SHA mismatch")
    x=run_one(source,binary,c["cap_s"],mode,
          ROOT/"scratch"/(c["source_sha256"][:14]+f"-{mode}-{rep}"))
    status=x["status"]
    need(status in ("SAT","UNSAT","TIMEOUT"),"invalid status")
    expect=c["expected_from_GBD_if_published"].upper()
    if status!="TIMEOUT" and expect in ("SAT","UNSAT"):
        need(status==expect,"conflicting published GBD source status")
    t=round(x["elapsed_s"],6)
    return dict(id=c["id"],source_sha256=c["source_sha256"],family=c["family"],
        track=c["track"],mode=mode,rep=rep,status=status,elapsed_s=t,
        par2_s=round(2*c["cap_s"] if status=="TIMEOUT" else t,6),
        cap_s=c["cap_s"],profile=x["profile"],route=x["route"],
        reason=x["reason"],proof=x["proof"],screen_s=round(x["screen_s"],6))

def shard(index,binary):
    cases=verify()
    need(0<=index<SHARDS and pathlib.Path(binary).is_file(),
         "missing native binary or invalid index")
    rows=[]
    for c in cases[index::SHARDS]:
        for rep in range(REPS):
            arms=list(ARMS)
            random.Random(PROTO+c["source_sha256"]+str(rep)).shuffle(arms)
            for arm in arms:
                x=trial(c,arm,rep,binary)
                rows.append(x)
                save(ROOT/f"shard-{index}.json",rows)
                print("NH_R5_TRIAL",json.dumps({k:x[k] for k in
                    ("id","family","mode","status","elapsed_s",
                     "profile","route")}),flush=True)
    need(len(rows)==len(cases[index::SHARDS])*REPS*len(ARMS),
         "incomplete R5 shard")
    print("NH_R5_SHARD_PASS",index,len(rows),flush=True)

def audit():
    cases=verify()
    expected={c["source_sha256"]:c for c in cases}
    data=[]
    for i in range(SHARDS):
        rr=load(ROOT/f"shard-{i}.json")
        need(len(rr)==len(cases[i::SHARDS])*REPS*len(ARMS),
             "incomplete shard "+str(i))
        data+=rr
    need(len(data)==len(cases)*REPS*len(ARMS),"missing paired measurements")
    grouped=collections.defaultdict(list)
    for r in data:
        c=expected.get(r["source_sha256"])
        need(c is not None and c["id"]==r["id"],"source SHA or ID mismatch")
        goal=2*r["cap_s"] if r["status"]=="TIMEOUT" else r["elapsed_s"]
        need(abs(r["par2_s"]-goal)<.00001,"PAR2 disagreement")
        grouped[r["source_sha256"],r["rep"]].append(r)
    for c in cases:
        for rep in range(REPS):
            group=grouped[c["source_sha256"],rep]
            need(len(group)==len(ARMS) and {r["mode"] for r in group}==set(ARMS),
                 "missing matched arm")
            need(len({r["status"] for r in group if r["status"]!="TIMEOUT"})<=1,
                 "opposing SAT UNSAT statuses!")
    groups={"all":cases}
    for family in FAMILIES:
        groups[family]=[c for c in cases if c["family"]==family]
    output={}
    for label,subset in groups.items():
        keys={c["source_sha256"] for c in subset}
        output[label]={}
        for mode in ARMS:
            z=[r for r in data if r["mode"]==mode and r["source_sha256"] in keys]
            output[label][mode]=dict(n=len(z),
                solved=sum(r["status"]!="TIMEOUT" for r in z),
                par2_s=round(sum(r["par2_s"] for r in z),6),
                elapsed_s=round(sum(r["elapsed_s"] for r in z),6),
                screening_s=round(sum(r["screen_s"] for r in z),6),
                statuses=dict(collections.Counter(r["status"] for r in z)),
                profiles=dict(collections.Counter(r["profile"] for r in z)),
                routes=dict(collections.Counter(r["route"] for r in z)))
    result=dict(protocol=PROTO,status="NH_R5_FIRST_CONTACT_AUDIT_PASS",
        source_formula_count=len(cases),trials=len(data),reps=REPS,
        original_source_SHA_frozen_before_solving=True,
        precommitted_source_selection_only=True,
        both_profiles_native_same_CaDiCaL_commit=True,
        native_UNSAT_not_independently_LRAT_checked=True,
        cannot_guarantee_globally_unseen=True,
        expected_labels_not_used_to_route=True,summary=output)
    save(ROOT/"report.json",result)
    save(ROOT/"trials.json",data)
    with (ROOT/"trials.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(data[0]))
        w.writeheader();w.writerows(data)
    md=["# DRNAS New Horizon SAT R5 — external original 2026 native speed test","",
        f"{len(cases)} SHA-frozen GBD main_2026 originals; {len(data)} paired trials;",
        "six arms × two reps; cap 8s. SHA exclusions cover enumerated ledgers only.","",
        "| Family | Method | Solved | PAR2 seconds | Statuses |",
        "|---|---|---:|---:|---|"]
    for label,methods in output.items():
        for m,x in methods.items():
            md.append(f"| {label} | {m} | {x['solved']}/{x['n']} | "+
                      f"{x['par2_s']:.6f} | {x['statuses']} |")
    md+=["","## Limits",
        "Real SAT Competition 2026 inputs, family-conditioned (not representative of whole SAT).",
        "Exclusion from R152/R106/R183 source ledgers, not a guarantee of global novelty.",
        "A 8s cap is short: timeout-to-timeout means no demonstrated speedup.",
        "All full-source exact paths keep original CNF and verify SAT witnesses.",
        "Native UNSAT has no independent LRAT/FRAT verification.",
        "This is first-contact, but the native profile heuristics existed before R5."]
    (ROOT/"summary.md").write_text("\n".join(md)+"\n")
    print("NH_R5_FINAL",json.dumps(
         dict(formulas=len(cases),attempts=len(data),summary=output["all"]),
         sort_keys=True),flush=True)

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("cmd",choices=("selftest","freeze","verify","shard","audit"))
    ap.add_argument("--shard",type=int,default=0)
    ap.add_argument("--binary",default="new_horizon_r5/r190-driver")
    args=ap.parse_args()
    if args.cmd=="selftest":selftest()
    elif args.cmd=="freeze":freeze()
    elif args.cmd=="verify":print("NH_R5_VERIFY_PASS",len(verify()))
    elif args.cmd=="shard":shard(args.shard,pathlib.Path(args.binary))
    else:audit()
