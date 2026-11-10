#!/usr/bin/env python3
"""DRNAS GF2-S2: source-selected SAT2024/25, eight fresh-relative-to-frozen
original CNF SHA, six arms, two repetitions, twelve-second one-CPU E2E.
No GF2 or SAT outcome used to select sources. Algebraic proof != LRAT.
"""
import argparse, hashlib, json, pathlib
import drnas_gf2_proof_first_s1 as engine
import drnas_binary_scc2_e2e as s2
import drnas_equiv9_prospective_seed_holdout as e9

ROOT=pathlib.Path("mre_gf2_s2")
PROTO="DRNAS-GF2-S2-2024-25-SHA-DISJOINT-8SHA-6ARM-2REP-12S-v1"
SALT="DRNAS-GF2-S2-OFFICIAL-2024-25-20261110-PRECOMMIT-SOURCE-ONLY-v1"
CAP=12.0
REPS=2
SHARDS=4
NCASE=8
EXPECTED=96
TARGET={0:4,1:4}
MAX_SCAN=400
MAX_RAW=12*1024*1024
MAX_PLAIN=12*1024*1024
MAX_VARS=30000
MAX_CLAUSES=130000
SOURCE=e9.SOURCE
MANIFESTS=("mre_equiv9/manifest.json","mre_equiv10m5/manifest.json",
           "mre_equiv12/manifest.json","mre_equiv13/manifest.json")

def need(test,why):
    if not test:raise RuntimeError("GF2_S2_FAIL_CLOSED "+str(why))
def digest(p):return e9.digest(p)
def read(p):return json.loads(pathlib.Path(p).read_text())
def write(p,obj):
    p=pathlib.Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(obj,indent=2,sort_keys=True)+"\n")
def exclude():
    shas,ids,old=e9.registries()
    seals={}
    for path in MANIFESTS:
        need(pathlib.Path(path).is_file(),"missing exclusion manifest "+path)
        seals[path]=digest(path)
        for c in read(path).get("cases",[]):
            if "sha256" in c:shas.add(c["sha256"])
            if "gbd" in c:ids.add(c["gbd"])
    return shas,ids,dict(manifests=seals,prior=old)
def cases():return read(ROOT/"manifest.json")["cases"]
def original_path(c):
    p=SOURCE/c["filename"]
    need(p.is_file() and digest(p)==c["sha256"],"original SHA changed")
    return p
def official_candidates():
    import mre7_extended_easy_freeze as pool
    pool_entries=[];indexes={}
    for year in ("2024","2025"):
        ids,sha=pool.getids("track=main_"+year)
        easy,esha=pool.getids("track=main_"+year+" and minisat1m=yes")
        need(len(ids)==400 and set(easy)<=set(ids),"official index drift")
        indexes[year]=dict(main=sha,easy=esha,count=len(ids),easy_count=len(easy))
        easyset=set(easy)
        pool_entries.extend((0 if v in easyset else 1,year,v) for v in ids)
    pool_entries.sort(key=lambda x:(x[0],hashlib.sha256(
        (SALT+"|"+x[1]+"|"+x[2]).encode()).hexdigest()))
    return pool_entries,indexes

def freeze():
    ROOT.mkdir(exist_ok=True,parents=True);SOURCE.mkdir(exist_ok=True,parents=True)
    s2.ROOT.mkdir(exist_ok=True,parents=True)
    need(engine.BIN.is_file() and e9.NATIVE.is_file() and e9.KISSAT.is_file(),
         "missing pinned GF2 and backend binaries")
    excluded_sha,excluded_ids,old=exclude()
    source_list,indexes=official_candidates()
    import mre7_reference_easy_freeze as fetch
    selected=[];seen=set();trace=[];counts={0:0,1:0}
    for tier,year,gbd in source_list:
        if len(selected)==NCASE:break
        if counts[tier]>=TARGET[tier] or gbd in excluded_ids or gbd in seen:continue
        seen.add(gbd)
        need(len(seen)<=MAX_SCAN,"source geometry screening limit")
        f=SOURCE/(gbd+".cnf")
        entry=dict(gbd=gbd,year=year,tier=tier)
        try:
            raw=fetch.get("https://benchmark-database.de/file/"+gbd,MAX_RAW,seconds=25)
            plain,_=fetch.prior.r32p.decode(raw)
            need(len(plain)<=MAX_PLAIN,"source byte cap")
            n,k=fetch.prior.r32p.parse_dimacs_metadata(plain)
            need(0<n<=MAX_VARS and 0<k<=MAX_CLAUSES,"source geometry cap")
            sha=hashlib.sha256(plain).hexdigest()
            need(sha not in excluded_sha,"prior SHA collision")
            f.write_bytes(plain)
            nn,clauses=e9.x22.read_cnf(f)
            need(nn==n and len(clauses)==k,"DIMACS metadata mismatch")
            selected.append(dict(year=year,gbd=gbd,sha256=sha,filename=f.name,
                 bytes=len(plain),vars=n,clauses=k,cohort="holdout",
                 tier="minisat1m_yes" if tier==0 else "main_other"))
            counts[tier]+=1;excluded_sha.add(sha);excluded_ids.add(gbd)
            entry.update(action="frozen_without_solver_or_GF2_outcomes",
                         sha256=sha,vars=n,clauses=k)
        except Exception as exc:
            f.unlink(missing_ok=True)
            entry.update(action="excluded_before_solving",reason=str(exc)[:140])
        trace.append(entry)
        write(ROOT/"selection-progress.json",dict(counts=counts,
              selections=selected,trace=trace))
        print("GF2_S2_SOURCE "+json.dumps(entry,sort_keys=True),flush=True)
    need(len(selected)==NCASE and counts==TARGET,
         "insufficient precommitted SHA-disjoint source-only candidates")
    m=dict(protocol=PROTO,cases=selected,source_count=NCASE,
        arms=list(engine.ARMS),reps=REPS,shards=SHARDS,cap_s=CAP,
        expected=EXPECTED,source_only=True,no_solution_outcome_selection=True,
        source_index_sha=indexes,source_tier_distribution=counts,
        prior_registry_digests=old,selection_trace=trace,
        globally_blind=False,history_exclusions_not_globally_exhaustive=True,
        SHA_disjoint_from_specified_frozen_registry=True,
        independent_original_GF2_proof_replay=True,
        GF2_proof_not_standard_LRAT=True,
        one_logical_cpu=True,no_parallel_solver_children=True,
        no_automatic_promotion=True,
        cpp_sha=digest("research/drnas_gf2_proof_first_s1.cpp"),
        scanner_sha=digest(engine.BIN),
        script_sha=digest(__file__),
        engine_sha=digest("research/drnas_gf2_proof_first_s1.py"),
        native_sha=digest(e9.NATIVE),kissat_sha=digest(e9.KISSAT))
    write(ROOT/"manifest.json",m);verify()
    print("GF2_S2_FROZEN "+json.dumps(dict(original_sha=NCASE,
          easy=TARGET[0],other=TARGET[1],trials=EXPECTED,
          selected_without_solvers=True),sort_keys=True),flush=True)

def verify():
    m=read(ROOT/"manifest.json")
    need(m["protocol"]==PROTO and m["cases"]==cases()
         and m["source_count"]==NCASE and m["expected"]==EXPECTED
         and m["shards"]==SHARDS and m["reps"]==REPS
         and m["cap_s"]==CAP and m["arms"]==list(engine.ARMS)
         and m["source_tier_distribution"]=={"0":4,"1":4},
         "manifest protocol mismatch")
    need(m["cpp_sha"]==digest("research/drnas_gf2_proof_first_s1.cpp")
         and m["scanner_sha"]==digest(engine.BIN)
         and m["script_sha"]==digest(__file__)
         and m["engine_sha"]==digest("research/drnas_gf2_proof_first_s1.py")
         and m["native_sha"]==digest(e9.NATIVE)
         and m["kissat_sha"]==digest(e9.KISSAT),"frozen code/backend drift")
    sha,gbd,old=exclude()
    need(old==m["prior_registry_digests"],"historical registry changed")
    need(len(set(c["sha256"] for c in m["cases"]))==NCASE,"duplicate SHA")
    for c in m["cases"]:
        need(c["sha256"] not in sha and c["gbd"] not in gbd,
             "previously frozen original overlap")
        original_path(c)
    s2.ROOT.mkdir(exist_ok=True,parents=True)
    return m

def selftest():
    import tempfile
    ROOT.mkdir(exist_ok=True,parents=True)
    for k in (2,3,4):
        with tempfile.TemporaryDirectory() as d:
            f=pathlib.Path(d)/"toy.cnf";cl=[]
            for parity in (0,1):
                for mask in range(1<<k):
                    if mask.bit_count()%2==parity:
                        cl.append([-(i+1) if mask&(1<<i) else i+1 for i in range(k)])
            for count,expected in ((len(cl),True),(len(cl)-1,False)):
                cs=cl[:count]
                f.write_text("p cnf %d %d\n"%(k,len(cs))+
                 "".join(" ".join(map(str,c))+" 0\n" for c in cs))
                need(engine.scan(f)["proved"]==expected,
                     "GF2 independent SAT/UNSAT toy control invalid")
    print("GF2_S2_SELFTEST_PASS "+json.dumps(dict(
       complete_XOR_UNSAT_toys=3,incomplete_SAT_toys=3,
       independent_source_CNF_algebraic_replay=True)),flush=True)

# Engine dispatch explicitly shares audited source checker/trial logic.
engine.ROOT=ROOT
engine.BIN=ROOT/"bin/gf2_exact"
engine.PROTO=PROTO
engine.CAP=CAP
engine.SHARDS=SHARDS
engine.NCASE=NCASE
engine.EXPECTED=EXPECTED
engine.cases=cases
engine.original_path=original_path
engine.verify=verify

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("selftest","freeze","verify","shard","audit"))
    p.add_argument("--shard",type=int,default=0)
    a=p.parse_args()
    if a.action=="selftest":selftest()
    elif a.action=="freeze":freeze()
    elif a.action=="verify":verify();print("GF2_S2_VERIFY_PASS",flush=True)
    elif a.action=="shard":engine.shard(a.shard)
    elif a.action=="audit":engine.audit()
