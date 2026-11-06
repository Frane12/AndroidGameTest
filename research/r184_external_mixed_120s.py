#!/usr/bin/env python3
"""DRNAS R183 external first-contact mixed CNF transfer test.

Select official GBD 2025/2026 CNFs by SOURCE FEATURES only, never by solver
time or expected SAT outcome. Exclude known R154/R106 IDs and SHA hashes.
Selected sources are frozen before any R183 solver runs. No synthetic cases.
'New' means absent from enumerated prior ledgers, not globally guaranteed unseen.
GF(2) rows require COMPLETE source CNF encodings of XOR of width 2..6.
Source-traced contradiction/units are checked before injection.
"""
from __future__ import annotations
import argparse,collections,hashlib,itertools,json,math,pathlib,random,re,statistics,subprocess,time
import r182_mixed_engine as r182
import r154_unseen_freeze as prior
ROOT=pathlib.Path("r184")
FROZEN=ROOT/"frozen"
PROTO="DRNAS-R184-EXTERNAL-MIXED-120S-v1"
FROZEN_PROTO="DRNAS-R183-EXTERNAL-SHA-FROZEN-MIXED-v1"
PINNED_MANIFEST_SHA256="102c8bdef78163aad8e08ab044c0ff7a123df4d67b0a714c50370b13447543c4"
SHARDS=6
REPS=2
CAP=120.0
MODES=("clean","gf2_gate","gf2_units")
FAMILIES=("cryptography","miter","xor-chain","linear-equations","lights-out")
TRACKS=("main_2026","main_2025")
QUOTAS={"mixed_encoding":10,"no_complete_xor_control":6}
MAX_FETCH=105
MAX_CNF_BYTES=8*1024*1024
MAX_COMPRESSED=12*1024*1024
MAX_CLAUSES=110000
MAX_VARS=8000

def need(ok,msg):
    if not ok:raise RuntimeError("R184_FAIL_CLOSED "+str(msg))
def sha(path):return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
def save(path,obj):r182.save(path,obj)
def load(path):return json.loads(pathlib.Path(path).read_text())

def xor_source(clauses):
    groups=collections.defaultdict(lambda:collections.defaultdict(set))
    for i,c in enumerate(clauses):
        k=len(c)
        if k<2 or k>6 or len(set(map(abs,c)))!=k:continue
        ordered=sorted(c,key=lambda x:abs(x))
        vs=tuple(abs(x) for x in ordered)
        assignment=sum(1<<bit for bit,lit in enumerate(ordered) if lit<0)
        groups[vs][assignment].add(i)
    rows=[];covered=set()
    for vs,patterns in groups.items():
        k=len(vs)
        for p in (0,1):
            all_forbidden=[a for a in range(1<<k) if a.bit_count()%2==p]
            if all(a in patterns for a in all_forbidden):
                ids=[min(patterns[a]) for a in all_forbidden]
                rows.append((vs,1-p,ids))
                covered.update(ids)
    rows.sort(key=lambda x:(x[0],x[1]))
    return rows,covered

def source_info(path,full=False):
    n,clauses=r182.dimacs(path)
    rows,covered=xor_source(clauses)
    residual=len(clauses)-len(covered)
    xorvars={v for vs,_,_ in rows for v in vs}
    boundary=sum(any(abs(v) in xorvars for v in c) for i,c in enumerate(clauses)
                 if i not in covered)
    cohort="mixed_encoding" if rows and residual else (
         "pure_xor_encoding" if rows else "no_complete_xor_control")
    features={"variables":n,"clauses":len(clauses),"xor_rows":len(rows),
              "source_xor_covered":len(covered),"residual_clauses":residual,
              "xor_boundary_clauses":boundary,"cohort":cohort,
              "schaefer_classes":r182.class_cnf(clauses)}
    if full:
        gf=r182.gaussian(rows)
        features["gf2_contradiction"]=gf["conflict"]
        features["gf2_rank"]=gf["rank"]
        features["gf2_units"]=len(gf["units"])
        if n<=200 and len(clauses)<=3000:
            features["small_strong_backdoor"]=r182.strong_backdoor(clauses,rows)
        else:
            features["small_strong_backdoor"]={"certified":False,"class":None,
              "reason":"large instance, backdoor test abstained"}
        return n,clauses,rows,gf,features
    return features

def history():
    ids=set();shas=set()
    # Pinned original 25 dataset. These were tested in R154/R155.
    p=pathlib.Path("r183/prior/frozen/manifest.json")
    need(p.exists(),"prior R154/R155 25 manifest is required for exclusions")
    m=load(p); need(len(m["cases"])==25,"prior source identities incomplete")
    for c in m["cases"]:
        ids.add(c["id"].lower());shas.add(c["sha256"].lower())
    known=load(pathlib.Path("research/r106_manifest.json"))
    for row in known["cases"]:
        ids.add(row[2].lower());shas.add(row[3].lower())
    # R152 hardcoded historical source IDs included to strengthen exclusion.
    import r152_lightsout_unseen as r152
    ids.update(x.lower() for x in r152.KNOWN_IDS|r152.OLD_R32P)
    return ids,shas

def freeze():
    ROOT.mkdir(parents=True,exist_ok=True);FROZEN.mkdir(parents=True,exist_ok=True)
    ids,shas=history()
    catalogs=[];candidates={}
    for family in FAMILIES:
        for track in TRACKS:
            try:
                rows,digest=prior.get_catalog(family,track)
                catalogs.append({"family":family,"track":track,"rows":len(rows),
                                 "catalog_sha256":digest})
                for c in rows:
                    if c["id"] not in ids and c["id"] not in candidates:
                        candidates[c["id"]]=c
                print("R184_CATALOG",family,track,len(rows),flush=True)
            except Exception as e:
                print("R184_CATALOG_WARNING",family,track,type(e).__name__,
                      str(e)[:140],flush=True)
    need(len(candidates)>=10,"GBD catalogs yielded insufficient unseen-by-ledger candidates")
    pool=sorted(candidates.values(),key=lambda c:c["id"])
    random.Random(PROTO+"|PRECOMMITTED-SEED").shuffle(pool)
    selected=[];seen=set();counts=collections.Counter();skip=collections.Counter()
    for c in pool[:MAX_FETCH]:
        if all(counts[k]>=v for k,v in QUOTAS.items()):break
        try:
            raw,_=prior.orig.source.request_url(
                "https://benchmark-database.de/file/"+c["id"],MAX_COMPRESSED,seconds=35)
            plain,_=prior.orig.source.decode(raw)
            if len(plain)>MAX_CNF_BYTES:
                skip["too_large"]+=1;continue
            digest=hashlib.sha256(plain).hexdigest()
            if digest in shas or digest in seen:
                skip["source_sha_prior_or_duplicate"]+=1;continue
            path=FROZEN/(c["id"]+".cnf")
            path.write_bytes(plain)
            sig=source_info(path)
            if sig["variables"]>MAX_VARS or sig["clauses"]>MAX_CLAUSES:
                path.unlink();skip["dimensions"]+=1;continue
            cohort=sig["cohort"]
            if cohort not in QUOTAS or counts[cohort]>=QUOTAS[cohort]:
                path.unlink();skip["cohort_quota_or_pure_xor"]+=1;continue
            item={"id":c["id"],"sha256":digest,"family":c["family"],
                  "track":c["track"],"origin":"GBD_external_original",
                  "cohort":cohort,"source_features":sig,
                  "filename":c["filename"],
                  "gbd_expected_status_metadata_not_used_for_selection":c["gbd_status"]}
            selected.append(item);seen.add(digest);counts[cohort]+=1
            print("R184_FROZEN",len(selected),item["id"],cohort,
                  "xor_rows",sig["xor_rows"],"residual",sig["residual_clauses"],
                  flush=True)
        except Exception as e:
            skip[type(e).__name__]+=1
            print("R184_SOURCE_SKIP",c["id"],type(e).__name__,str(e)[:120],flush=True)
            (FROZEN/(c["id"]+".cnf")).unlink(missing_ok=True)
    need(counts["mixed_encoding"]>=4 and len(selected)>=8,
         "not enough true external structurally mixed formulas: fail closed")
    selected.sort(key=lambda c:c["sha256"])
    manifest={"protocol":PROTO,"source_frozen_before_any_R184_benchmark":True,
        "distribution_blind":False,"global_unseen_guaranteed":False,
        "known_sources_excluded":len(ids),"known_sha_excluded":len(shas),
        "sampling":"precommitted catalog shuffle, structural-only quotas",
        "synthetic_sources":0,"genuine_external_originals":len(selected),
        "counts":dict(counts),"skips":dict(skip),"catalogs":catalogs,
        "fetched_candidates_limit":MAX_FETCH,"cases":selected}
    save(FROZEN/"manifest.json",manifest)
    verify()
    print("R184_FREEZE_PASS",json.dumps({"cases":len(selected),
        "cohorts":dict(counts),"seen_ids_excluded":len(ids)},sort_keys=True),flush=True)

def verify():
    m=load(FROZEN/"manifest.json")
    need(m["protocol"]==FROZEN_PROTO and m["synthetic_sources"]==0,"not frozen external sources")
    need(sha(FROZEN/"manifest.json")==PINNED_MANIFEST_SHA256,"R183 source manifest SHA changed")
    need(len(m["cases"])>=8,"source cohort too small")
    for c in m["cases"]:
        src=FROZEN/(c["id"]+".cnf")
        need(src.is_file() and sha(src)==c["sha256"],"source SHA drift")
        need(source_info(src)==c["source_features"],"source-only feature mismatch")
    return m["cases"]

def native(binary,path,cap):
    start=time.perf_counter()
    try:
        p=subprocess.run([str(binary.resolve()),str(path.resolve()),str(cap)],
            capture_output=True,timeout=cap+5)
    except subprocess.TimeoutExpired:
        return "TIMEOUT",time.perf_counter()-start,{}
    elapsed=time.perf_counter()-start
    need(p.returncode==0,"native driver failed "+p.stderr.decode(errors="replace")[-600:])
    raw=p.stdout.decode(errors="replace")
    m=re.search(r"^R182_STATUS status=(SAT|UNSAT|TIMEOUT) solver_s=([0-9.]+) variables=(\d+)$",raw,re.M)
    need(m,"native result missing")
    model={}
    if m.group(1)=="SAT":
        for line in raw.splitlines():
            if line.startswith("v "):
                x=int(line.split()[1]);need(x!=0,"null model literal")
                need(abs(x) not in model or model[abs(x)]==(x>0),"inconsistent model")
                model[abs(x)]=x>0
    return m.group(1),elapsed,model

def trial(c,mode,rep,binary):
    path=FROZEN/(c["id"]+".cnf");need(sha(path)==c["sha256"],"source SHA drift")
    start=time.perf_counter()
    proof="NONE";details={}
    if mode=="clean":
        status,t,model=native(binary,path,CAP)
    else:
        n,clauses,rows,gf,info=source_info(path,full=True)
        details={"gf2_contradiction":gf["conflict"],"xor_rows":len(rows),
                 "gf2_units":len(gf["units"])}
        if gf["conflict"]:
            r182.check_trace(rows,0,1,gf["conflict_trace"])
            status="UNSAT";model={}
            proof="SOURCE_XOR_CONTRADICTION_INDEPENDENTLY_REPLAYED"
        else:
            inp=path
            if mode=="gf2_units" and gf["units"]:
                out=ROOT/"generated"/(c["id"]+"-"+str(rep)+".cnf")
                out.parent.mkdir(parents=True,exist_ok=True)
                injected=[v if value else -v for v,(value,trace) in sorted(gf["units"].items())]
                out.write_text("p cnf "+str(n)+" "+str(len(clauses)+len(injected))+"\n"+
                    "".join(" ".join(map(str,cl))+" 0\n" for cl in clauses)+
                    "".join(str(x)+" 0\n" for x in injected))
                inp=out
            status,t,model=native(binary,inp,CAP)
    elapsed=time.perf_counter()-start
    if status=="SAT":
        # Verify every SAT result on the ORIGINAL CNF; checker not scored as
        # a solver speed improvement and same checker applies to all arms.
        _,source_clauses=r182.dimacs(path)
        r182.sat_check(source_clauses,model)
        proof="ORIGINAL_SAT_WITNESS_CHECKED"
    if status=="UNSAT" and proof=="NONE":
        proof="CADICAL_UNSAT_WITHOUT_INDEPENDENT_LRAT"
    if elapsed>CAP:
        status="TIMEOUT";proof="CAPPED"
    return {"id":c["id"],"sha256":c["sha256"],"family":c["family"],
          "cohort":c["cohort"],"mode":mode,"repeat":rep,"status":status,
          "elapsed_s":round(elapsed,6),"par2_s":round(
              2*CAP if status=="TIMEOUT" else elapsed,6),
          "proof":proof,**details}

def shard(index,binary):
    need(0<=index<SHARDS,"shard index")
    cases=verify();ROOT.mkdir(parents=True,exist_ok=True)
    out=[]
    for c in cases[index::SHARDS]:
        for rep in range(REPS):
            modes=list(MODES)
            random.Random(PROTO+c["sha256"]+str(rep)).shuffle(modes)
            for mode in modes:
                r=trial(c,mode,rep,binary)
                out.append(r)
                save(ROOT/f"shard-{index}.json",out)
                print("R184_TRIAL",json.dumps({k:r[k] for k in (
                    "id","cohort","mode","repeat","status","elapsed_s","proof")},
                    sort_keys=True),flush=True)
    need(len(out)==len(cases[index::SHARDS])*REPS*len(MODES),"incomplete shard")
    print("R184_SHARD_PASS",index,len(out),flush=True)

def audit():
    cases=verify();rows=[]
    for i in range(SHARDS):rows.extend(load(ROOT/f"shard-{i}.json"))
    need(len(rows)==len(cases)*REPS*len(MODES),"incomplete 3-arm paired dataset")
    by=collections.defaultdict(list)
    for r in rows:
        by[(r["sha256"],r["mode"])].append(r)
    scores=collections.defaultdict(dict)
    for c in cases:
        for mode in MODES:
            a=by[(c["sha256"],mode)]
            need(len(a)==REPS and {x["repeat"] for x in a}=={0,1},
                 "not same-SHA 2-repeat paired")
            solved={x["status"] for x in a if x["status"]!="TIMEOUT"}
            need(len(solved)<=1,"unstable SAT/UNSAT result across repetitions")
            scores[c["sha256"]][mode]=statistics.median(x["par2_s"] for x in a)
        observed={r["status"] for r in rows if r["sha256"]==c["sha256"]
                  and r["status"]!="TIMEOUT"}
        need(len(observed)<=1,"contradictory statuses between solvers")
    cohorts={"all":cases,
        "external_mixed":[c for c in cases if c["cohort"]=="mixed_encoding"],
        "no_xor_control":[c for c in cases if c["cohort"]=="no_complete_xor_control"]}
    stats={}
    for name,sub in cohorts.items():
        if not sub:continue
        total={m:round(sum(scores[c["sha256"]][m] for c in sub),6) for m in MODES}
        oracle=sum(min(scores[c["sha256"]].values()) for c in sub)
        stats[name]={"cases":len(sub),"PAR2_s":total,"oracle_PAR2_s":round(oracle,6),
                     "clean_to_gate_x":round(total["clean"]/total["gf2_gate"],6),
                     "clean_to_units_x":round(total["clean"]/total["gf2_units"],6)}
    byproof=collections.Counter(r["proof"] for r in rows)
    mode_outcomes={mode:dict(collections.Counter(
        row["status"] for row in rows if row["mode"]==mode)) for mode in MODES}
    cohort_outcomes={cohort: {mode: dict(collections.Counter(
        row["status"] for row in rows if row["cohort"]==cohort and row["mode"]==mode))
        for mode in MODES} for cohort in ("mixed_encoding","no_complete_xor_control")}
    results={"protocol":PROTO,"status":"R184_EXTERNAL_PAIRED_AUDIT_PASS",
        "not_world_ranking":True,"selected_by_runtime":False,
        "external_original_only":True,
        "source_history_exclusion_is_not_global_unseen_proof":True,
        "not_disjoint_from_all_possible_historical_tests":True,
        "unsat_CaDiCaL_requires_independent_LRAT":True,
        "cap_seconds":CAP,"source_freeze_run_id":42206668113,
        "source_reuse":True,"not_new_blind_instances":True,
        "mode_outcomes":mode_outcomes,"cohort_mode_outcomes":cohort_outcomes,
        "repeats":REPS,"attempts":len(rows),"groups":stats,
        "proof_counts":dict(byproof)}
    save(ROOT/"report.json",results)
    with (ROOT/"summary.md").open("w") as f:
        f.write("# R184 120-second extension of previously frozen external SAT Competition CNFs\n\n")
        f.write("GBD source-only quota freeze; no synthetic sources. "
                "Existing 12 R183 formulas reused without selection changes; NOT new blind material. Cap 120 seconds.\n\n")
        f.write("| Cohort | CNFs | Clean PAR-2 s | GF2 gate PAR-2 s | GF2 units PAR-2 s | Gate vs clean |\n"
                "|---|---:|---:|---:|---:|---:|\n")
        for name,s in stats.items():
            f.write(f"|{name}|{s['cases']}|{s['PAR2_s']['clean']}|"
              f"{s['PAR2_s']['gf2_gate']}|{s['PAR2_s']['gf2_units']}|"
              f"{s['clean_to_gate_x']}x|\n")
        f.write("\nNo claim of global ranking; UNSAT from CDCL has no independent LRAT.\n")
    print("R184_FINAL",json.dumps(results,sort_keys=True),flush=True)

def selftest():
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        root=pathlib.Path(td)
        p=root/"mixed.cnf"
        clause=[]
        for i in range(8):
            if i.bit_count()%2==0:
                clause.append(tuple(-v if i>>(v-1)&1 else v for v in (1,2,3)))
        clause.append((1,4))
        p.write_text("p cnf 4 "+str(len(clause))+"\n"+
            "".join(" ".join(map(str,c))+" 0\n" for c in clause))
        info=source_info(p)
        need(info["cohort"]=="mixed_encoding" and info["xor_rows"]==1,
             "XOR3 with CNF residual recognition failure")
        # Two complete parity sets over same support => certified contradiction.
        clause2=clause[:-1]+[
            tuple(-v if i>>(v-1)&1 else v for v in (1,2,3))
            for i in range(8) if i.bit_count()%2==1]
        p.write_text("p cnf 4 "+str(len(clause2))+"\n"+
            "".join(" ".join(map(str,c))+" 0\n" for c in clause2))
        _,_,rows,gf,details=source_info(p,full=True)
        need(gf["conflict"] and len(rows)==2,"XOR proof test failed")
        r182.check_trace(rows,0,1,gf["conflict_trace"])
    print("R184_SELFTEST_PASS",flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("selftest","freeze","verify","shard","audit"))
    p.add_argument("--shard",type=int,default=0)
    p.add_argument("--binary",default="r183/r182-driver")
    a=p.parse_args()
    if a.action=="selftest":selftest()
    elif a.action=="freeze":freeze()
    elif a.action=="verify":print("R184_VERIFY_PASS",len(verify()),flush=True)
    elif a.action=="shard":shard(a.shard,pathlib.Path(a.binary))
    else:audit()
