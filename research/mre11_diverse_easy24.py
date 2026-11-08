#!/usr/bin/env python3
"""MRE11 diverse easy developmental replay: 4 reused official and 20 NEW synthetic
CNFs across 10 logical families. New generated examples are not official blind
holdouts. Source choice is fixed BEFORE any MRE11 run. CaDiCaL checks originals
but independent UNSAT LRAT is not produced. Exact pinned MRE11 C++ binary.
"""
from __future__ import annotations
import argparse, collections, hashlib, itertools, json, pathlib, random, shutil, subprocess, tempfile
import mre11_easy_benchmark as old
import mre11_holdout as pinned

PROTO="DRNAS-MRE11-DIVERSE-EASY24-4REAL-20NEW-10F-5ARM-4SEED-5S-v1"
SALT="MRE11-EASY24-20261108-PRECOMMITTED-V1"
ROOT=pathlib.Path("mre11_diverse24")
PREV=pathlib.Path("mre11_easy")
CAP=5.0
REPS=4
SHARDS=4
MODES=old.MODES
FAMILIES=("planted_3sat","mixed_xor_sat","mixed_xor_unsat",
 "graph_3color_sat","graph_3color_unsat","pigeonhole_unsat",
 "two_sat_unsat","horn_sat","equivalence_sat","duplicate_clean_sat")
def need(b,m):
    if not b: raise RuntimeError("MRE11_DIVERSE_FAIL_CLOSED "+m)
def sha(b): return hashlib.sha256(b).hexdigest()
def save(p,obj):
    p=pathlib.Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(obj,sort_keys=True,indent=2)+"\n")
def seed(c,rep):
    need(rep in range(REPS),"seed repetition invalid")
    return int(sha((PROTO+"|SEED|"+c["sha256"]+"|"+str(rep)).encode())[:8],16)

def generated(family,i):
    need(family in FAMILIES and i in (0,1),"not a predeclared source")
    rng=random.Random(int(sha((SALT+"|"+family+"|"+str(i)).encode())[:15],16))
    n=72+32*i
    plant=[False]+[bool(rng.getrandbits(1)) for _ in range(n)]
    clauses=[];expected="SAT"
    def planted(k):
        for _ in range(k):
            vs=rng.sample(range(1,n+1),3)
            literals=[v if rng.getrandbits(1) else -v for v in vs]
            if not any((l>0)==plant[abs(l)] for l in literals):
                j=rng.randrange(3);v=vs[j]
                literals[j]=v if plant[v] else -v
            clauses.append(tuple(literals))
    def xor3(vs,rhs):
        for bits in itertools.product((0,1),repeat=3):
            if (bits[0]^bits[1]^bits[2])!=rhs:
                clauses.append(tuple(-v if bit else v for v,bit in zip(vs,bits)))
    if family=="planted_3sat":
        planted(4*n)
    elif family in ("mixed_xor_sat","mixed_xor_unsat"):
        used=set()
        for j in range(12+5*i):
            while True:
                vs=tuple(sorted(rng.sample(range(1,n//2+1),3)))
                if vs not in used:used.add(vs);break
            rhs=sum(plant[v] for v in vs)%2
            xor3(vs,rhs)
            if j==0 and family=="mixed_xor_unsat":xor3(vs,1-rhs)
        planted(3*n)
        if family=="mixed_xor_unsat":expected="UNSAT"
    elif family in ("graph_3color_sat","graph_3color_unsat"):
        vertices=16+4*i;n=3*vertices
        var=lambda v,c:3*v+c+1
        colors=[rng.randrange(3) for _ in range(vertices)]
        edges=set()
        if family=="graph_3color_unsat":
            expected="UNSAT"
            edges.update(itertools.combinations(range(4),2)) # K4 obstruction
        for _ in range(5*vertices):
            a,b=sorted(rng.sample(range(vertices),2))
            if family=="graph_3color_unsat" or colors[a]!=colors[b]:edges.add((a,b))
        for v in range(vertices):
            clauses.append(tuple(var(v,c) for c in range(3)))
            for c,d in itertools.combinations(range(3),2):
                clauses.append((-var(v,c),-var(v,d)))
        for a,b in sorted(edges):
            for c in range(3):clauses.append((-var(a,c),-var(b,c)))
    elif family=="pigeonhole_unsat":
        p=6+i;h=p-1;n=p*h;expected="UNSAT"
        var=lambda a,b:a*h+b+1
        for a in range(p):clauses.append(tuple(var(a,b) for b in range(h)))
        for b in range(h):
            for a,c in itertools.combinations(range(p),2):
                clauses.append((-var(a,b),-var(c,b)))
    elif family=="two_sat_unsat":
        expected="UNSAT"
        clauses.extend(((1,2),(1,-2),(-1,3),(-1,-3)))
        for _ in range(3*n):
            a,b=rng.sample(range(4,n+1),2)
            clauses.append((a if rng.getrandbits(1) else -a,
                            b if rng.getrandbits(1) else -b))
    elif family=="horn_sat":
        clauses.append((1,))
        for a in range(1,n):clauses.append((-a,a+1))
        for _ in range(2*n):
            a,b=rng.sample(range(1,n+1),2)
            clauses.append((-a,b))
    elif family=="equivalence_sat":
        for j in range(2,19+6*i):
            clauses.extend(((-1,j),(1,-j)))
            plant[j]=plant[1]
        planted(3*n)
    elif family=="duplicate_clean_sat":
        planted(3*n)
        saved=clauses[:3]
        for j in range(90+30*i):clauses.append(saved[j%len(saved)])
    else:raise AssertionError(family)
    need(n>0 and len(clauses)>0 and all(1<=abs(l)<=n for c in clauses for l in c),
         "invalid generator geometry")
    raw=(f"c MRE11 new deterministic synthetic {family} {i}\n"+
         f"p cnf {n} {len(clauses)}\n"+
         "".join(" ".join(map(str,c))+" 0\n" for c in clauses)).encode()
    return raw,expected,n,len(clauses)

def check_cadical(src,expected,cadical):
    p=subprocess.run([str(pathlib.Path(cadical).resolve()),str(src.resolve())],
                     capture_output=True,text=True,check=False,timeout=30)
    need(p.returncode in (10,20),"CaDiCaL did not finish "+src.name+" "+p.stderr[-200:])
    need(("SAT" if p.returncode==10 else "UNSAT")==expected,
         "independent SAT/UNSAT contradiction "+src.name)

def freeze(cadical):
    ROOT.mkdir(exist_ok=True)
    m=json.loads((PREV/"manifest.json").read_text())
    need(m["protocol"]=="DRNAS-MRE11-EASY12-2021-2025-DEVREPLAY-5ARMS-4SEEDS-12S-v1",
         "unexpected original development reference cohort")
    need(len(m["cases"])==12,"missing frozen previous official sources")
    # No timing trial, no MRE11 score, no retries or exclusions. Reference-only.
    chosen=sorted(m["cases"],key=lambda c:(float(c["reference_screen_s"]),c["sha256"]))[:4]
    cases=[]
    for c in chosen:
        src=PREV/c["filename"]
        need(sha(src.read_bytes())==c["sha256"],"old official SHA changed")
        name="official-"+c["sha256"][:16]+".cnf"
        dst=ROOT/name;shutil.copyfile(src,dst)
        cases.append(dict(id=name[:-4],gbd=c["gbd"],filename=name,
           sha256=sha(dst.read_bytes()),bytes=dst.stat().st_size,year=c["year"],
           family="reused_official_easy",origin="previous_official_replay_not_blind",
           expected=c["reference_screen_status"],
           reference_screen_status=c["reference_screen_status"],
           reference_screen_s=c["reference_screen_s"]))
    for family in FAMILIES:
        for i in (0,1):
            raw,expected,n,k=generated(family,i)
            name=f"synth-{family}-{i}.cnf"
            (ROOT/name).write_bytes(raw)
            cases.append(dict(id=name[:-4],gbd=name[:-4],filename=name,
              sha256=sha(raw),bytes=len(raw),year="synthetic",
              family=family,origin="new_deterministic_synthetic",
              expected=expected,reference_screen_status=expected,
              reference_screen_s=None,vars=n,clauses=k))
    need(len(cases)==24 and len({c["sha256"] for c in cases})==24,
         "not exactly 24 distinct originals")
    for c in cases:
        check_cadical(ROOT/c["filename"],c["expected"],cadical)
        print("MRE11_DIVERSE_SOURCE",json.dumps({"id":c["id"],"family":c["family"],
            "expected":c["expected"],"sha256":c["sha256"]}),flush=True)
    save(ROOT/"manifest.json",dict(protocol=PROTO,cases=cases,
       source_count=24,official_reused=4,synthetic_new=20,families=list(FAMILIES),
       developmental_not_blind=True,synthetic_not_official=True,
       no_external_source_scan=True,no_selector_result_based_selection=True,
       all_source_statuses_independently_cadical_crosschecked=True,
       independent_unsat_lrat=False,repetitions=REPS,cap_s=CAP,
       modes=list(MODES),expected_trials=480,no_auto_promotion=True))
    (ROOT/"source.sha256").write_text("".join(c["sha256"]+"  "+c["filename"]+"\n"
                                              for c in cases))
    print("MRE11_DIVERSE_FREEZE_PASS",len(cases),"new synthetic",20,flush=True)

def cases():
    m=json.loads((ROOT/"manifest.json").read_text())
    need(m["protocol"]==PROTO and len(m["cases"])==24 and m["expected_trials"]==480
         and m["repetitions"]==REPS and m["cap_s"]==CAP and m["modes"]==list(MODES),
         "source manifest or benchmark protocol changed")
    c=m["cases"]
    need(len({x["sha256"] for x in c})==24 and
         sum(x["origin"]=="new_deterministic_synthetic" for x in c)==20,
         "cohort provenance or uniqueness changed")
    for x in c:
        p=ROOT/x["filename"]
        need(p.exists() and sha(p.read_bytes())==x["sha256"]
             and p.stat().st_size==x["bytes"],"original SHA mismatch "+x["id"])
    return c

# Reuse the SAME pinned MRE11 native C++ trial/witness checker as prior EASY12.
# Its reference_screen_s is null for new synthetic sources (not prescreened).
old.ROOT=ROOT
old.PROTO=PROTO
old.CAP=CAP
old.seed=seed

def diagnostic(standalone):
    cc=cases();counts=collections.Counter();out=[]
    with tempfile.TemporaryDirectory(prefix="mre11-diverse-parity-") as d:
        d=pathlib.Path(d)
        for c in cc:
            src=ROOT/c["filename"];a=d/"selector.cnf";b=d/"expected.cnf"
            gate=pinned.subprocess_gate(src,"cpp_mre11_sel",a,standalone)
            reason=gate["reason"];counts[reason]+=1
            mode=("cpp_rename" if reason=="MRE11_SOURCE_SELECT_RENAME" else
                  "cpp_clean" if reason=="MRE11_SOURCE_SELECT_CLEAN" else "cpp_native")
            pinned.subprocess_gate(src,mode,b,standalone)
            need(a.read_bytes()==b.read_bytes(),"selector not exact selected C++ arm")
            out.append(dict(id=c["id"],family=c["family"],gate=gate,selected_arm=mode))
    save(ROOT/"gate_diagnostics.json",out)
    print("MRE11_DIVERSE_PARITY_PASS",json.dumps(dict(counts)),flush=True)

def shard(index,binary):
    need(index in range(SHARDS),"bad shard")
    cc=cases();subset=cc[index::SHARDS]
    need(len(subset)==6,"wrong source distribution")
    out=[]
    for c in subset:
        for rep in range(REPS):
            modes=list(MODES)
            random.Random(sha((PROTO+c["sha256"]+str(rep)).encode())).shuffle(modes)
            for mode in modes:
                r=old.trial(c,rep,mode,binary)
                r.update(id=c["id"],family=c["family"],origin=c["origin"])
                out.append(r)
                save(ROOT/f"shard-{index}.json",out)
                print("MRE11_DIVERSE_TRIAL",json.dumps(r,sort_keys=True),flush=True)
    need(len(out)==120,"missing shard trials")
    print("MRE11_DIVERSE_SHARD_PASS",index,len(out),flush=True)

def audit():
    cc=cases();orig={c["sha256"]:c for c in cc}
    rows=[]
    for sh in range(SHARDS):
        p=ROOT/f"shard-{sh}.json"
        need(p.exists(),"missing shard "+str(sh))
        rr=json.loads(p.read_text())
        need(len(rr)==120,"incomplete shard "+str(sh))
        rows+=rr
    need(len(rows)==480,"incorrect total trial count")
    unique=set()
    for r in rows:
        c=orig.get(r["original_sha256"])
        need(c is not None and r["id"]==c["id"] and r["family"]==c["family"] and
             r["origin"]==c["origin"] and r["protocol"]==PROTO and
             r["rep"] in range(REPS) and r["mode"] in MODES and
             r["seed"]==seed(c,r["rep"]),"foreign original, mode or paired seed")
        key=(c["sha256"],r["rep"],r["mode"])
        need(key not in unique,"duplicated paired trial");unique.add(key)
        need(r["verdict"] in ("SAT","UNSAT","TIMEOUT"),"invalid solver status")
        if r["verdict"]=="SAT":
            need(r["SAT_original_witness_verified"] and c["expected"]=="SAT",
                 "SAT witness or truth mismatch")
        if r["verdict"]=="UNSAT":
            need(r["UNSAT_prior_CaDiCaL_crosschecked_no_LRAT"] and c["expected"]=="UNSAT",
                 "UNSAT reference mismatch")
        goal=2*CAP if r["verdict"]=="TIMEOUT" else r["wall_s"]
        need(abs(goal-r["par2_s"])<1e-5,"PAR2 audit error")
    need(len(unique)==480,"missing source-seed-mode pair")
    def scores(rs):
        out={}
        for m in MODES:
            a=[x for x in rs if x["mode"]==m]
            out[m]=dict(trials=len(a),solved=sum(x["verdict"]!="TIMEOUT" for x in a),
              SAT=sum(x["verdict"]=="SAT" for x in a),
              UNSAT_no_independent_LRAT=sum(x["verdict"]=="UNSAT" for x in a),
              timeouts=sum(x["verdict"]=="TIMEOUT" for x in a),
              PAR2_total_s=round(sum(x["par2_s"] for x in a),6),
              gate_applied=sum(bool((x["gate"] or {}).get("applied")) for x in a))
        baseline=out["cpp_native"]["PAR2_total_s"]
        for a in out.values():
            a["speedup_vs_native_x"]=round(baseline/a["PAR2_total_s"],6)
        return out
    result=dict(protocol=PROTO,source_count=24,synthetic_new=20,official_reused=4,
      total_trials=480,repetitions=REPS,cap_s=CAP,real_end_to_end=True,
      not_globally_blind=True,synthetic_not_official=True,
      SAT_original_witness_verified=True,UNSAT_CaDiCaL_agreement_no_independent_LRAT=True,
      no_auto_promotion=True,scores=scores(rows),
      by_family={f:scores([r for r in rows if r["family"]==f])
                for f in sorted({c["family"] for c in cc})},
      by_origin={f:scores([r for r in rows if r["origin"]==f])
                for f in sorted({c["origin"] for c in cc})})
    save(ROOT/"report.json",result)
    print("MRE11_DIVERSE_FINAL",json.dumps({k:v for k,v in result.items()
          if k not in ("by_family","by_origin")},sort_keys=True),flush=True)
    for f,a in result["by_family"].items():
        print("MRE11_DIVERSE_FAMILY",json.dumps({"family":f,"scores":a},sort_keys=True),flush=True)

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("action",choices=("freeze","verify","diagnostic","shard","audit"))
    ap.add_argument("--native",default="mre11/bin/native")
    ap.add_argument("--standalone",default="mre11/bin/standalone")
    ap.add_argument("--cadical",default="/usr/bin/cadical")
    ap.add_argument("--shard",type=int,default=0)
    a=ap.parse_args()
    if a.action=="freeze":freeze(a.cadical)
    elif a.action=="verify":print("MRE11_DIVERSE_VERIFY_PASS",len(cases()),flush=True)
    elif a.action=="diagnostic":diagnostic(a.standalone)
    elif a.action=="shard":shard(a.shard,a.native)
    else:audit()
