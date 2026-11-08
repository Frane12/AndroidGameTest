#!/usr/bin/env python3
"""Bounded, CMS-baseline-conditioned, 10-family MRE11 medium-difficulty DEVELOPMENT study.
4 already frozen old official sources + 2 selected from 5 deterministic candidates
per family. Selection uses ONLY cpp_native baseline, never DRNAS transforms.
Candidate window 0.1-2.0s is a target, not claimed for short-control families.
All original source SHA locked before five-arm testing. No index/web scans.
"""
from __future__ import annotations
import argparse, collections, hashlib, itertools, json, math, os, pathlib, random
import shutil, subprocess, tempfile, time
import mre11_diverse_easy24 as prev
import mre11_easy_benchmark as easy
import mre11_holdout as pinned

PROTO="DRNAS-MRE11-MEDIUM24-10F-BASELINE-CALIBRATED-5ARMS-4SEEDS-6S-v1"
ROOT=pathlib.Path("mre11_medium24")
PREV=pathlib.Path("mre11_easy")
SALT="MRE11-MEDIUM24-CALIBRATE-20261108-FIXED-v1"
CAP=6.0
REPS=4
MODES=easy.MODES
FAMILIES=prev.FAMILIES
PILOT_SEED=117
PILOT_CAP=2.4
TARGET_LO,TARGET_HI=0.10,2.0
CANDIDATES=5

def need(ok,message):
    if not ok:raise RuntimeError("MRE11_MEDIUM_FAIL_CLOSED "+message)
def sha(b):return hashlib.sha256(b).hexdigest()
def save(path,obj):prev.save(path,obj)
def seed(c,rep):
    need(rep in range(REPS),"bad repetition")
    return int(sha((PROTO+"|SEED|"+c["sha256"]+"|"+str(rep)).encode())[:8],16)
def generated(family,i):
    need(family in FAMILIES and 0<=i<CANDIDATES,"unprecommitted source")
    rnd=random.Random(int(sha((SALT+"|"+family+"|"+str(i)).encode())[:15],16))
    clauses=[];expected="SAT"
    n=110+42*i
    witness=[False]+[bool(rnd.getrandbits(1)) for _ in range(n)]
    def clause(c):clauses.append(tuple(c))
    def planted(k,restrict=None):
        ids=list(restrict) if restrict is not None else list(range(1,n+1))
        for _ in range(k):
            vs=rnd.sample(ids,3)
            ls=[v if rnd.getrandbits(1) else -v for v in vs]
            if not any((l>0)==witness[abs(l)] for l in ls):
                j=rnd.randrange(3); v=vs[j]; ls[j]=v if witness[v] else -v
            clause(ls)
    def xor3(vs,rhs):
        for bits in itertools.product((0,1),repeat=3):
            if (bits[0]^bits[1]^bits[2])!=rhs:
                clause(tuple(-v if bit else v for v,bit in zip(vs,bits)))
    if family=="planted_3sat":
        planted(int(n*4.12))
    elif family in ("mixed_xor_sat","mixed_xor_unsat"):
        # Random 3-XOR rows, no adjacent direct contradictory copy.
        n=24+8*i
        witness=[False]+[bool(rnd.getrandbits(1)) for _ in range(n)]
        rows=[];used=set()
        for _ in range(n+max(3,i)):
            while True:
                vs=tuple(sorted(rnd.sample(range(1,n+1),3)))
                if vs not in used:used.add(vs);break
            rhs=sum(witness[v] for v in vs)%2
            rows.append((vs,rhs))
        if family=="mixed_xor_unsat":
            expected="UNSAT"
            # Four distinct 3-XOR rows whose left sides XOR to zero.
            # Flipping precisely one RHS is a deterministic UNSAT certificate.
            a,b,c,d,e,f=rnd.sample(range(1,n+1),6)
            gadget=((a,b,c),(a,d,e),(b,d,f),(c,e,f))
            for j,vs in enumerate(gadget):
                rhs=sum(witness[v] for v in vs)%2
                rows.append((tuple(sorted(vs)),rhs^(j==3)))
        for vs,rhs in rows:xor3(vs,rhs)
        planted(n)
    elif family in ("graph_3color_sat","graph_3color_unsat"):
        if family=="graph_3color_sat":
            v=32+12*i
            colors=[rnd.randrange(3) for _ in range(v)]
            edges=set()
            for _ in range(5*v):
                a,b=sorted(rnd.sample(range(v),2))
                if colors[a]!=colors[b]:edges.add((a,b))
        else:
            expected="UNSAT"
            # Mycielski construction of odd cycle: triangle-free 4-chromatic graph,
            # more informative than the previously trivial K4 obstruction.
            v0=7+4*i
            v=2*v0+1
            edges=set()
            for a in range(v0):
                b=(a+1)%v0
                edges.add(tuple(sorted((a,b))))
                edges.add(tuple(sorted((a,b+v0))))
                edges.add(tuple(sorted((b,a+v0))))
            for a in range(v0):edges.add((a+v0,2*v0))
        n=3*v
        def colorvar(a,b):return 3*a+b+1
        for a in range(v):
            clause(tuple(colorvar(a,b) for b in range(3)))
            for b,c in itertools.combinations(range(3),2):
                clause((-colorvar(a,b),-colorvar(a,c)))
        for a,b in sorted(edges):
            for c in range(3):clause((-colorvar(a,c),-colorvar(b,c)))
    elif family=="pigeonhole_unsat":
        expected="UNSAT"
        p=6+i;h=p-1;n=p*h
        var=lambda a,b:a*h+b+1
        for a in range(p):clause(tuple(var(a,b) for b in range(h)))
        for b in range(h):
            for a,c in itertools.combinations(range(p),2):
                clause((-var(a,b),-var(c,b)))
    elif family=="two_sat_unsat":
        # Linear-time control family. A long implication chain is still 2-SAT,
        # so its pilot may legitimately stay below 0.1s.
        expected="UNSAT";n=750+750*i
        clause((1,))
        for a in range(1,n):clause((-a,a+1))
        clause((-n,))
        for _ in range(n):
            a,b=rnd.sample(range(1,n+1),2)
            clause((-a,b))
    elif family=="horn_sat":
        # A polynomial-time control rather than a misleading artificial "hard" instance.
        n=800+900*i
        clause((1,))
        for a in range(1,n):clause((-a,a+1))
        for _ in range(2*n):
            a,b=rnd.sample(range(1,n+1),2)
            clause((-a,b))
    elif family=="equivalence_sat":
        n=500+400*i
        witness=[False]+[bool(rnd.getrandbits(1)) for _ in range(n)]
        for v in range(2,n//2):
            clause((-1,v));clause((1,-v))
            witness[v]=witness[1]
        # Additional 3-CNF is constructed SAT under the SAME equivalence witness.
        planted(3*n)
    elif family=="duplicate_clean_sat":
        n=200+100*i
        witness=[False]+[bool(rnd.getrandbits(1)) for _ in range(n)]
        planted(3*n)
        fixed=clauses[:min(90,len(clauses))]
        for j in range(1000+1200*i):clause(fixed[j%len(fixed)])
    else:raise ValueError(family)
    need(n>0 and len(clauses)>0 and all(1<=abs(l)<=n for c in clauses for l in c),
         "invalid DIMACS generator")
    raw=(f"c MRE11 medium candidate {family} index={i} precommitted\n"+
         f"p cnf {n} {len(clauses)}\n"+
         "".join(" ".join(map(str,c))+" 0\n" for c in clauses)).encode()
    return raw,expected,n,len(clauses)

def pilot(source,binary):
    begin=time.perf_counter()
    try:
        p=subprocess.run([str(pathlib.Path(binary).resolve()),str(source.resolve()),
                         "cpp_native",str(PILOT_SEED)],capture_output=True,text=True,
                         timeout=PILOT_CAP,check=False,errors="replace")
    except subprocess.TimeoutExpired:
        return dict(status="TIMEOUT",seconds=PILOT_CAP,witness_verified=False)
    wall=time.perf_counter()-begin
    need(p.returncode==0,"pilot original native failed: "+p.stderr[-200:])
    gate=pinned.parse_gate(p.stdout)
    need(not gate["applied"],"pilot must use original native CMS")
    verdict,model,_=pinned.native_ref.parsed_native(p.stdout)
    need(verdict in ("SAT","UNSAT"),"unexpected pilot terminal")
    if verdict=="SAT":pinned.native_ref.verify_model(source,model)
    return dict(status=verdict,seconds=round(wall,6),witness_verified=verdict=="SAT")

def freeze(binary,cadical):
    ROOT.mkdir(exist_ok=True)
    m=json.loads((PREV/"manifest.json").read_text())
    need(len(m["cases"])==12 and
         m["protocol"]=="DRNAS-MRE11-EASY12-2021-2025-DEVREPLAY-5ARMS-4SEEDS-12S-v1",
         "wrong previous frozen official cohort")
    # Four fixed originals from earlier MRE11 reference cohort, source-only criterion.
    chosen=sorted(m["cases"],key=lambda c:(abs(math.log(float(c["reference_screen_s"])/0.55)),
                        c["sha256"]))[:4]
    out=[];trace=[]
    for c in chosen:
        src=PREV/c["filename"]
        need(sha(src.read_bytes())==c["sha256"],"prior official original SHA mismatch")
        name="official-"+c["sha256"][:16]+".cnf";dst=ROOT/name
        shutil.copyfile(src,dst)
        prev.check_cadical(dst,c["reference_screen_status"],cadical)
        out.append(dict(id=name[:-4],gbd=c["gbd"],filename=name,
            sha256=sha(dst.read_bytes()),bytes=dst.stat().st_size,year=c["year"],
            family="reused_official_medium",origin="previous_official_replay_not_blind",
            expected=c["reference_screen_status"],
            reference_screen_status=c["reference_screen_status"],
            reference_screen_s=c["reference_screen_s"],
            source_screen_band="previous_reference"))
    binary=str(pathlib.Path(binary).resolve())
    # Bounded at EXACTLY 5 original-only probes per family (50 total max).
    # No MRE11 gate, no DRNAS arm, no unbounded index scan and no retries.
    with tempfile.TemporaryDirectory(prefix="mre11-medium-pilot-") as t:
        temp=pathlib.Path(t)
        for family in FAMILIES:
            candidates=[]
            for i in range(CANDIDATES):
                raw,expected,n,k=generated(family,i)
                path=temp/(family+"-"+str(i)+".cnf")
                path.write_bytes(raw)
                verdict=pilot(path,binary)
                c=dict(id=f"synth-{family}-{i}",family=family,index=i,raw=raw,
                       sha256=sha(raw),expected=expected,vars=n,clauses=k,pilot=verdict)
                c["status_ok"]=verdict["status"]==expected
                candidates.append(c)
                trace.append(dict(id=c["id"],family=family,expected=expected,
                     source_SHA=c["sha256"],pilot=verdict))
                print("MRE11_MEDIUM_PILOT",json.dumps(trace[-1],sort_keys=True),flush=True)
            viable=[c for c in candidates if c["status_ok"]]
            need(len(viable)>=2,"fewer than 2 native-verified candidates "+family)
            def order(c):
                sec=c["pilot"]["seconds"]
                inside=TARGET_LO<=sec<=TARGET_HI
                return (not inside,abs(math.log(max(sec,0.0001)/0.45)),c["index"])
            # Reference-only preselection, two per family; preserve provenance.
            finalists=sorted(viable,key=order)
            selected=0
            for c in finalists:
                name=c["id"]+".cnf";dst=ROOT/name
                dst.write_bytes(c["raw"])
                try:
                    prev.check_cadical(dst,c["expected"],cadical)
                except (subprocess.TimeoutExpired,RuntimeError) as e:
                    dst.unlink(missing_ok=True)
                    trace.append(dict(id=c["id"],family=family,
                                      verifier_rejected=str(e)[:160]))
                    continue
                out.append(dict(id=c["id"],gbd=c["id"],filename=name,
                   sha256=c["sha256"],bytes=len(c["raw"]),year="synthetic",
                   family=family,origin="new_baseline_conditioned_synthetic",
                   expected=c["expected"],reference_screen_status=c["expected"],
                   reference_screen_s=c["pilot"]["seconds"],vars=c["vars"],
                   clauses=c["clauses"],
                   source_screen_band=("0.1_to_2s" if TARGET_LO<=c["pilot"]["seconds"]<=TARGET_HI
                                       else "fast_control_outside_band")))
                selected+=1
                if selected==2:break
            need(selected==2,"too few reference-verified formulas "+family)
    need(len(out)==24 and len({c["sha256"] for c in out})==24,
         "not exactly 24 distinct SHA-locked formulas")
    for c in out:
        need(sha((ROOT/c["filename"]).read_bytes())==c["sha256"],"source changed")
    distribution=collections.Counter(c["source_screen_band"] for c in out)
    save(ROOT/"manifest.json",dict(protocol=PROTO,cases=out,
        source_count=24,official_reused=4,synthetic_new=20,
        families=list(FAMILIES),source_selection_baseline_conditioned=True,
        source_pilot_per_family_max=CANDIDATES,source_pilot_cap_s=PILOT_CAP,
        target_baseline_s=[TARGET_LO,TARGET_HI],band_counts=dict(distribution),
        synthetic_not_official=True,development_not_blind=True,
        no_external_source_scanning=True,no_MRE11_during_source_selection=True,
        original_status_CaDiCaL_crosschecked=True,independent_UNSAT_LRAT=False,
        repetitions=REPS,cap_s=CAP,modes=list(MODES),
        expected_trials=24*REPS*len(MODES),no_auto_promotion=True,
        baseline_source_screen_trace=trace))
    (ROOT/"source.sha256").write_text("".join(c["sha256"]+"  "+c["filename"]+"\n"
                                               for c in out))
    print("MRE11_MEDIUM_FREEZE_PASS",json.dumps(dict(
         source_count=len(out),synthetic=20,official=4,band_counts=dict(distribution),
         max_pilots=50),sort_keys=True),flush=True)

def cases():
    m=json.loads((ROOT/"manifest.json").read_text())
    need(m["protocol"]==PROTO and len(m["cases"])==24 and
         m["expected_trials"]==480 and m["cap_s"]==CAP and
         m["modes"]==list(MODES),"frozen medium manifest drift")
    cc=m["cases"]
    need(len({c["sha256"] for c in cc})==24,"duplicate CNFs")
    for c in cc:
        p=ROOT/c["filename"]
        need(p.exists() and sha(p.read_bytes())==c["sha256"] and
             p.stat().st_size==c["bytes"],"original SHA mismatch "+c["id"])
        need(c["expected"] in ("SAT","UNSAT"),"unverified truth")
    return cc

# Reuse the proven MRE11 comparator and audit verbatim, varying only frozen
# source identities, repetitions' SHA-derived seed, end-to-end cap and protocol.
prev.PROTO=PROTO
prev.ROOT=ROOT
prev.CAP=CAP
prev.seed=seed
prev.cases=cases
prev.old.PROTO=PROTO
prev.old.ROOT=ROOT
prev.old.CAP=CAP
prev.old.seed=seed
prev.old.REPS=REPS

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("action",choices=("freeze","verify","diagnostic","shard","audit"))
    ap.add_argument("--native",default="mre11/bin/native")
    ap.add_argument("--standalone",default="mre11/bin/standalone")
    ap.add_argument("--cadical",default="/usr/bin/cadical")
    ap.add_argument("--shard",type=int,default=0)
    a=ap.parse_args()
    if a.action=="freeze":freeze(a.native,a.cadical)
    elif a.action=="verify":print("MRE11_MEDIUM_VERIFY_PASS",len(cases()),flush=True)
    elif a.action=="diagnostic":prev.diagnostic(a.standalone)
    elif a.action=="shard":prev.shard(a.shard,a.native)
    else:prev.audit()
