#!/usr/bin/env python3
"""DRNAS TA: precommitted structural route test on 30 original 2026 CNFs.
TA is OUT-OF-DEVELOPMENT for R1/R2/R193, not guaranteed globally blind.
No solver output informs source selection or routing thresholds.
"""
import argparse,collections,csv,hashlib,json,os,pathlib,random,re,sys
import ultimate_r2t_benchmark as b
import ultimate_ta_fallback as selector

ROOT=pathlib.Path("ultimate_ta")
FROZEN=ROOT/"frozen"
PROTO="DRNAS-TA-20261107-30-SHA-DISJOINT-STRUCTURAL-PORTFOLIO-v1"
MODES=("r1a","r153","r2_clean","r2_portfolio","r2_binary")
REPS=2
SHARDS=6
COUNT=30
CAP=30.
EXCLUSIONS=(pathlib.Path("ultimate_r1/frozen/manifest.json"),
            pathlib.Path("ultimate_r2/frozen/manifest.json"),
            pathlib.Path("ta_exclusions/r193/frozen/manifest.json"))
# Configure the previously audited run_one/trial/shard machinery; it will
# run identical original R153, R1A, CaDiCaL native and frozen XOR logic.
b.ROOT=ROOT;b.FROZEN=FROZEN;b.PROTO=PROTO;b.MODES=MODES
b.REPS=REPS;b.SHARDS=SHARDS;b.NEW=COUNT;b.DEV=0;b.CAP_NEW=CAP
b.FALLBACK=pathlib.Path("research/ultimate_ta_fallback.py")
need=b.need;sha=b.sha;get=b.get;put=b.put

def excluded():
    ids=set();sha_set=set();origins={}
    for path in EXCLUSIONS:
        need(path.is_file(),"missing precommitted exclusion "+str(path))
        obj=get(path)
        instances=obj.get("cases",[])
        need(len(instances)>=20,"unexpected previous source manifest: "+str(path))
        origins[str(path)]=sha(path)
        for c in instances:
            ids.add(c["id"]);sha_set.add(c["sha256"])
    need(len(sha_set)>=102,"old source manifest missing SHA provenance")
    return ids,sha_set,origins

def freeze():
    ids,seen,provenance=excluded()
    FROZEN.mkdir(parents=True,exist_ok=True)
    lines=b.official.download_bytes(b.official.URI,150000,14).decode("ascii").splitlines()
    urlset=sorted(set(u.strip() for u in lines if re.fullmatch(
         r"https?://benchmark-database\\.de/file/[a-f0-9]{32}",u.strip())),
         key=lambda x:hashlib.sha256((PROTO+x).encode()).hexdigest())
    need(len(urlset)>100,"SAT 2026 source index not available")
    entries=[];retrieval=[];added=set()
    for url in urlset:
        if len(entries)==COUNT or len(retrieval)>=450:break
        ident=url.rsplit("/",1)[-1]
        if ident in ids or ident in added:continue
        try:
            raw=b.official.decode_cnf(
                b.official.download_bytes(url,b.official.MAX_COMPRESSED,14))
            digest=hashlib.sha256(raw).hexdigest()
            need(digest not in seen and digest not in {c["sha256"] for c in entries},
                 "source SHA overlaps previously benchmarked CNFs")
            need(0<len(raw)<=12_000_000,"source byte-envelope veto")
            head=re.search(rb"(?m)^p\\s+cnf\\s+(\\d+)\\s+(\\d+)\\s*$",raw[:8192])
            need(head is not None,"missing original DIMACS header")
            need(0<int(head[1])<=150000 and 0<=int(head[2])<=160000,
                 "outside native variable/clauses limits")
            (FROZEN/(ident+".cnf")).write_bytes(raw)
            entries.append(dict(id=ident,sha256=digest,cohort="new_to_ta",
                source=url,expected="UNKNOWN",cap_s=CAP,family="official2026"))
            retrieval.append(dict(id=ident,source_sha256=digest,accepted=True))
            added.add(ident)
            print("TA_FREEZE_ACCEPT",ident,digest,flush=True)
        except Exception as exc:
            retrieval.append(dict(id=ident,accepted=False,reason=str(exc)[:130]))
    need(len(entries)==COUNT,"cannot freeze 30 SHA-disjoint original sources")
    random.Random(PROTO).shuffle(entries)
    put(FROZEN/"manifest.json",dict(protocol=PROTO,cases=entries,
        exclusion_manifest_sha=provenance,original_source_unchanged=True,
        selected_without_solver_outcomes=True,
        source_disjoint_from_R1_R2_R193=True,
        globally_blind=False,reps=REPS,modes=MODES,retrievals=retrieval))
    verify()
    print("TA_FREEZE_PASS",json.dumps({
        "sources":COUNT,"attempts":COUNT*REPS*len(MODES),
        "manifest_sha":sha(FROZEN/"manifest.json")},sort_keys=True),flush=True)

def verify():
    ids,digests,origin=excluded()
    d=get(FROZEN/"manifest.json")
    need(d["protocol"]==PROTO and d["exclusion_manifest_sha"]==origin,
         "TA prior source manifest provenance changed")
    cases=d["cases"]
    need(len(cases)==COUNT and len({c["sha256"] for c in cases})==COUNT,
         "source count or duplicate SHA")
    for c in cases:
        need(c["cohort"]=="new_to_ta" and c["cap_s"]==CAP,
             "precommitted cap/cohort drift")
        need(c["id"] not in ids and c["sha256"] not in digests,
             "source overlaps R1 R2 R193")
        need(sha(FROZEN/(c["id"]+".cnf"))==c["sha256"],
             "original CNF bytes changed")
    return cases

def selftest():
    need(MODES==("r1a","r153","r2_clean","r2_portfolio","r2_binary"),
         "TA registered arms")
    need(COUNT==30 and REPS==2 and SHARDS==6 and CAP==30.,
         "TA source/seed/cap protocol")
    with b.tempfile.TemporaryDirectory() as t:
        f=pathlib.Path(t)/"sample.cnf"
        f.write_text("p cnf 5 30\n"+"\n".join(
            f"-{1+i%5} {1+(i+1)%5} 0" for i in range(30))+"\n")
        route,features=selector.structural_portfolio(f)
        need(route=="clean" and features["binary_fraction"]==1.,
             "TA sparse binary Horn selftest")
    print("TA_SELFTEST_PASS",flush=True)

def audit():
    cases=verify();rows=[]
    for idx in range(SHARDS):
        block=get(ROOT/f"shard-{idx}.json")
        need(len(block)==len(cases[idx::SHARDS])*REPS*len(MODES),
             "TA incomplete shard "+str(idx))
        rows.extend(block)
    need(len(rows)==COUNT*REPS*len(MODES)==300,"TA expected 300 paired attempts")
    sources={c["sha256"]:c for c in cases}
    pairs=collections.defaultdict(dict)
    for t in rows:
        c=sources.get(t["sha256"])
        need(c and t["id"]==c["id"] and t["cohort"]==c["cohort"],
             "TA source SHA mismatch")
        pair=pairs[t["sha256"],t["rep"]]
        need(t["mode"] not in pair and t["mode"] in MODES,"duplicated/unregistered arm")
        pair[t["mode"]]=t
        need(abs(t["par2_s"]-(2*t["cap_s"] if t["status"]=="TIMEOUT"
              else t["elapsed_s"]))<1e-5,"TA PAR2 drift")
        if t["status"]=="SAT":
            need(t["proof"]=="SAT_WITNESS_CHECKED_ORIGINAL_SHA","TA SAT not checked")
    for group in pairs.values():
        need(set(group)==set(MODES),"TA missing paired arm")
        need(len({x["cpu"] for x in group.values()})==1,
             "different runner CPU in paired comparison")
        need(len({x["status"] for x in group.values()
                 if x["status"]!="TIMEOUT"})<=1,"SAT/UNSAT solver contradiction")
    scores={}
    for mode in MODES:
        sample=[x for x in rows if x["mode"]==mode]
        scores[mode]=dict(n=len(sample),
            solved=sum(x["status"]!="TIMEOUT" for x in sample),
            sat=sum(x["status"]=="SAT" for x in sample),
            unsat=sum(x["status"]=="UNSAT" for x in sample),
            par2_s=round(sum(x["par2_s"] for x in sample),6),
            fallback_routes=collections.Counter(x["r2_gate"].get("reason","none")
                   for x in sample))
    comparisons={}
    for ref,cand in (("r1a","r2_portfolio"),("r2_clean","r2_portfolio"),
                     ("r153","r2_portfolio"),("r1a","r2_binary"),
                     ("r2_clean","r2_binary"),("r2_portfolio","r2_binary")):
        deltas=[arm[ref]["par2_s"]-arm[cand]["par2_s"] for arm in pairs.values()]
        comparisons[f"{cand}_vs_{ref}"]=dict(
          wins=sum(x>0.005 for x in deltas),
          losses=sum(x<-.005 for x in deltas),
          ties=sum(abs(x)<=.005 for x in deltas),
          par2_gain_s=round(sum(deltas),6))
    result=dict(status="TA_30_ORIGINAL_SHA_DISJOINT_AUDIT_PASS_NOT_GLOBAL_BLIND",
        attempts=300,source_count=30,original_SHA_verified=True,
        source_disjoint_R1_R2_R193=True,source_manifest_sha=sha(FROZEN/"manifest.json"),
        prior_frozen_R2T_unchanged=True,source_select_before_results=True,
        independent_native_UNSAT_LRAT=False,results={"all":scores},
        comparisons=comparisons)
    put(ROOT/"report.json",result);put(ROOT/"trials.json",rows)
    with (ROOT/"trials.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader()
        for x in rows:
            y=dict(x);y["r2_gate"]=json.dumps(y["r2_gate"],sort_keys=True)
            w.writerow(y)
    with (ROOT/"summary.md").open("w") as f:
        f.write("# DRNAS TA — 30 precommitted source-disjoint SAT 2026 originals\n\n")
        f.write("Source disjoint from frozen R1/R2/R193. Not globally blind. Original SAT models checked. Native UNSAT LRAT unavailable.\n\n")
        f.write("| Arm | Solved | PAR2 (s) |\n|---|---:|---:|\n")
        for mode,v in scores.items():
            f.write(f"| {mode} | {v['solved']}/{v['n']} | {v['par2_s']} |\n")
        f.write("\n"+json.dumps(comparisons,indent=2)+"\n")
    print("TA_FINAL",json.dumps(dict(status=result["status"],
        scores=scores,comparisons=comparisons),sort_keys=True),flush=True)

# Reuse the exact prior, already validated SAT witness verifier and native
# run contract, but remap every global to this TA holdout by construction.
b.verify=verify

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("action",choices=("selftest","freeze","verify","shard","audit"))
    parser.add_argument("--shard",type=int,default=0)
    args=parser.parse_args()
    {"selftest":selftest,"freeze":freeze,
     "verify":lambda:print("TA_VERIFY_PASS",len(verify()),flush=True),
     "shard":lambda:b.shard(args.shard),"audit":audit}[args.action]()
