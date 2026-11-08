#!/usr/bin/env python3
"""MRE6i prospective official SAT2026 + new synthetic XOR/CNF controls freeze.

New official sources chosen by published *external* CaDiCaL3 runtimes,
SHA256-salted deterministic order, valid status, file size and CNF size
ONLY. Never use DRNAS speed or structure to include/exclude an official.
2 old anchors are explicitly calibration (not blind). 2 synthetic controls
are fixed planted-SAT XOR/CNF with separately verifiable truth assignment.
"""
from __future__ import annotations
import argparse,csv,hashlib,io,json,pathlib,random,shutil,sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/"experiments"/"drnas_v16"))
import r32p_real_satcomp26_benchmark as r32p
import r52_prospective_2026_toprefs as r52
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import mre7_medium_freeze as old_frozen
import r195_native_cms_benchmark as r195

ROOT=pathlib.Path("mre6i_sources")
MRE7=pathlib.Path("mre7_medium")
PROTO="DRNAS-MRE6I-20261108-4FRESH2026-2KNOWN-2NEW-SYNTH-v1"
SALT="DRNAS-MRE6I-NEW-OFFICIAL-20261108-STRUCTURE-INDEPENDENT-SHA-LOCK-v1"
CAP=35.
MAX_VARS,MAX_CLAUSES=80000,150000
MAX_RAW,MAX_DIMACS=30*1024**2,55*1024**2
SYN_N=(240,480)
REPS=2

def need(ok,reason):
    if not ok:raise RuntimeError("MRE6I_FREEZE_FAIL_CLOSED "+str(reason))
def digest(raw):return hashlib.sha256(raw).hexdigest()

def synthetic(idx):
    n=SYN_N[idx]
    seed=int(digest((SALT+"|new-synthetic|"+str(idx)).encode())[:14],16)
    rng=random.Random(seed)
    assignment={i:rng.randrange(2) for i in range(1,n+1)}
    clauses=[]
    # Multiple independently encoded GF2 equations; adjacent rows share
    # 2 variables and imply nontrivial *signed* equivalence.
    eqs=[]
    for g in range(5):
        a,b,c,d=[4*g+1,4*g+2,4*g+3,4*g+4]
        eqs.append(((a,b,c),assignment[a]^assignment[b]^assignment[c]))
        eqs.append(((a,b,d),assignment[a]^assignment[b]^assignment[d]))
    for vs,rhs in eqs:
        for mask in range(1<<len(vs)):
            if (mask.bit_count()&1)==rhs:continue
            clauses.append(tuple(-v if (mask&(1<<j)) else v for j,v in enumerate(vs)))
    for i in range(int(3.5*n)):
        vs=rng.sample(range(1,n+1),3)
        c=[v if rng.randrange(2) else -v for v in vs]
        if not any(assignment[abs(v)]==(v>0) for v in c):
            j=rng.randrange(3);v=vs[j];c[j]=v if assignment[v] else -v
        clauses.append(tuple(c))
    need(all(any(assignment[abs(l)]==(l>0) for l in c) for c in clauses),
         "synthetic SAT plant does not satisfy generated CNF")
    body=("c MRE6i new deterministic synthetic SAT mechanistic control\n"+
          "p cnf %d %d\n"%(n,len(clauses))+
          "".join(" ".join(map(str,c))+" 0\n" for c in clauses)).encode()
    return body,seed,len(eqs)

def freeze():
    old_frozen.verify(MRE7)
    prior=json.loads((MRE7/"manifest.json").read_text())
    need(len(prior["cases"])==6,"MRE7 prior source cohort drift")
    ROOT.mkdir(parents=True,exist_ok=True)
    cases=[];attempts=[]
    for c in prior["cases"][:2]:
        need(c["cohort"]=="REUSED_known_solved_diagnostic",
             "expected only frozen reused calibration anchors")
        src=MRE7/c["name"]
        need(r195.digest(src)==c["sha256"],"reused SHA changed")
        shutil.copyfile(src,ROOT/c["name"])
        cases.append(dict(name=c["name"],sha256=c["sha256"],bytes=src.stat().st_size,
                          expected=c["expected"],cohort="REUSED_known_solved_diagnostic",
                          official_reference_s=None,old_mre7_name=c["name"]))
    official_uri=r52.fetch_bytes(r52.URI,100000)
    gbds=[u.strip().rsplit("/",1)[-1] for u in official_uri.decode().strip().splitlines()]
    need(len(gbds)==400 and len(set(gbds))==400,"official Main2026 index changed")
    scoreblob=r52.fetch_bytes(r52.SCORES,32*1024*1024)
    entries=list(csv.DictReader(io.StringIO(scoreblob.decode())))
    known={c.get("gbd") for c in prior["cases"] if c.get("gbd")}
    known|={c["name"].replace("official-","").replace(".cnf","") for c in prior["cases"]}
    registry=pathlib.Path("research/mre6b_official_prior_gbd.txt")
    need(registry.exists(),"historical 2026 registry missing")
    known|={ln.strip() for ln in registry.read_text().splitlines()
             if ln.strip() and not ln.startswith("#")}
    allowed=set(gbds)
    reference=[]
    for x in entries:
        if x.get("solverid")!="biere_cadical3[main]" or x.get("instanceid") not in allowed:continue
        g=x["instanceid"]
        if g in known:continue
        status={"sat-verified":"SAT","unsat-verified":"UNSAT"}.get(x["status"])
        if status is None:continue
        try:sec=float(x["runtime"])
        except (ValueError,TypeError):continue
        if .75<=sec<15:
            reference.append(dict(gbd=g,expected=status,official_reference_s=sec))
    for expected in ("SAT","UNSAT"):
        for lo,hi in ((.75,5.),(5.,15.)):
            pool=[p for p in reference if p["expected"]==expected and
                  lo<=p["official_reference_s"]<hi]
            pool.sort(key=lambda p:digest((SALT+"|"+expected+"|"+
                       str(lo)+"|"+p["gbd"]).encode()))
            need(len(pool)>=1,"no published reference strata candidates")
            accepted=False
            for c in pool[:60]:
                g=c["gbd"]
                try:
                    raw,redir=r32p.request_url(
                      "https://benchmark-database.de/file/"+g,MAX_RAW,seconds=45)
                    payload,compression=r32p.decode(raw)
                    need(len(payload)<=MAX_DIMACS,"large decompressed CNF")
                    n,m=r32p.parse_dimacs_metadata(payload)
                    need(n<=MAX_VARS and m<=MAX_CLAUSES,"large n or m")
                    sha=digest(payload)
                    need(sha not in {x["sha256"] for x in cases},
                         "source SHA collision")
                    name=g+".cnf"
                    (ROOT/name).write_bytes(payload)
                    cases.append(dict(name=name,gbd=g,sha256=sha,
                         bytes=len(payload),vars=n,clauses=m,
                         expected=expected,cohort="NEW_official_reference_medium",
                         official_reference_s=c["official_reference_s"],
                         compression=compression,source_url_redirect=redir,
                         selection="precommitted_external_CaDiCaL3_runtime_ONLY"))
                    attempts.append(dict(gbd=g,action="frozen",sha256=sha,
                                         expected=expected,reference_s=c["official_reference_s"]))
                    print("MRE6I_NEW2026_FROZEN",json.dumps(attempts[-1],sort_keys=True),flush=True)
                    accepted=True
                    break
                except Exception as e:
                    attempts.append(dict(gbd=g,action="excluded_download_or_size",
                         reason=(type(e).__name__+": "+str(e))[:135]))
            need(accepted,"could not download official "+expected+str(lo))
    need(len(cases)==6,"new official selection must yield 4 separate originals")
    for i in range(2):
        payload,seed,eqs=synthetic(i)
        p=ROOT/("mre6i-new-planted-xor-%d.cnf"%i)
        p.write_bytes(payload)
        cases.append(dict(name=p.name,sha256=digest(payload),bytes=len(payload),
           expected="SAT",cohort="NEW_synthetic_XOR_controls",
           official_reference_s=None,seed=seed,
           planted_GF2_source_equations=eqs,
           selection="fixed_seed_synthetic_mechanism_NOT_official"))
    need(len(cases)==8 and len({c["sha256"] for c in cases})==8,
         "expected 8 distinct original CNF files")
    manifest=dict(protocol=PROTO,salt=SALT,cap_s=CAP,repetitions=REPS,
        cases=cases,provenance_official_index_sha256=digest(official_uri),
        provenance_official_results_sha256=digest(scoreblob),
        old_mre7_manifest_sha256=r195.digest(MRE7/"manifest.json"),
        new_official_count=4,reused_calibration_count=2,new_synthetic_count=2,
        structure_and_DRNAS_runtimes_NOT_used_for_new_official_inclusion=True,
        historical_disjoint_registry_not_exhaustive=True,
        attempts=attempts)
    (ROOT/"manifest.json").write_text(json.dumps(manifest,sort_keys=True,indent=2)+"\n")
    (ROOT/"source.sha256").write_text("".join(c["sha256"]+"  "+c["name"]+"\n"
                                               for c in cases))
    verify()
    print("MRE6I_FREEZE_PASS",len(cases),flush=True)

def verify():
    m=json.loads((ROOT/"manifest.json").read_text())
    need(m["protocol"]==PROTO and len(m["cases"])==8,
         "manifest version/case count drift")
    need(len({x["sha256"] for x in m["cases"]})==8,"duplicate sources")
    need(sum(x["cohort"]=="NEW_official_reference_medium" for x in m["cases"])==4,
         "official new count changed")
    need(sum(x["cohort"]=="REUSED_known_solved_diagnostic" for x in m["cases"])==2,
         "reused count changed")
    need(sum(x["cohort"]=="NEW_synthetic_XOR_controls" for x in m["cases"])==2,
         "synthetic count changed")
    for c in m["cases"]:
        path=ROOT/c["name"]
        need(path.exists() and r195.digest(path)==c["sha256"] and
             path.stat().st_size==c["bytes"],"source SHA or byte length drift")
    print("MRE6I_SOURCES_VERIFIED",len(m["cases"]),flush=True)

def selftest():
    for i in range(2):
        payload,seed,eqs=synthetic(i)
        need(payload.startswith(b"c MRE6i"),"synthetic generator header drift")
        need(eqs==10 and len(payload)>5000,"expected planted XOR/CNF size")
    need(CAP==35. and REPS==2 and len(SYN_N)==2,"freeze parameters drift")
    print("MRE6I_FREEZE_SELFTEST_PASS",PROTO,flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("mode",choices=("selftest","freeze","verify"))
    z=p.parse_args()
    if z.mode=="selftest":selftest()
    elif z.mode=="freeze":freeze()
    else:verify()
