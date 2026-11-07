#!/usr/bin/env python3
"""DRNAS New Horizon SAT v1: frozen SHA-matched paired structural experiment.
Reused external originals are not blind; generated families are not novel.
"""
from __future__ import annotations
import argparse, collections, csv, hashlib, itertools, json, pathlib, random, statistics
import new_horizon_sat as nh
import r186_cheap_selector as gen

ROOT=pathlib.Path("new_horizon")
FROZEN=ROOT/"frozen"
PROTO="DRNAS-NEW-HORIZON-SAT-STRUCTURAL-POINTER-R1-v1"
PREVIOUS_MANIFEST_SHA="3f0f67bea5547daa1ba07d9a1dba31d8d33f7d734db8eb6e8cae358a46c91ef3"
MODES=("clean","shadow","forced","new_horizon")
REPS=2
SHARDS=4
EXTERNAL_COUNT=12
GENERATED_COUNT=32
PURE_COUNT=10
COUPLED_COUNT=20
TOTAL=EXTERNAL_COUNT+GENERATED_COUNT+PURE_COUNT+COUPLED_COUNT

def need(v,msg):
    if not v:raise RuntimeError("NEW_HORIZON_AUDIT_FAIL_CLOSED "+str(msg))
def read(p):return json.loads(pathlib.Path(p).read_text())
def save(p,obj):
    p=pathlib.Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(obj,sort_keys=True,indent=2)+"\n")
def make_cnf(n,clauses,comment):
    return "c "+comment+"\n"+f"p cnf {n} {len(clauses)}\n"+"".join(" ".join(map(str,c))+" 0\n" for c in clauses)
def exact_xor(vs,rhs):
    return [tuple(-v if mask>>j&1 else v for j,v in enumerate(vs))
            for mask in range(8) if (mask.bit_count()&1)!=rhs]
def generated_pure(i):
    rng=random.Random(2026110701+i*97)
    n=24;w=[0]+[rng.randrange(2) for _ in range(n)]
    rows=set()
    while len(rows)<8:rows.add(tuple(sorted(rng.sample(range(1,n+1),3))))
    rows=sorted(rows)
    clauses=[]
    for vs in rows:
        rhs=w[vs[0]]^w[vs[1]]^w[vs[2]]
        clauses.extend(exact_xor(vs,rhs))
    kind="SAT"
    if i%2:
        vs=rows[0];rhs=w[vs[0]]^w[vs[1]]^w[vs[2]]
        clauses.extend(exact_xor(vs,1-rhs))
        kind="UNSAT"
    rng.shuffle(clauses)
    return n,clauses,kind
def generated_coupling(i):
    rng=random.Random(2026110702+i*131)
    n=72;w=[0]+[rng.randrange(2) for _ in range(n)]
    mix=(0,25,50,75,100)[i//4]
    rows={(1,2,3),(1,2,4),(3,4,5)}
    while len(rows)<15: rows.add(tuple(sorted(rng.sample(range(1,37),3))))
    clauses=[]
    for vs in sorted(rows):
        rhs=w[vs[0]]^w[vs[1]]^w[vs[2]]
        clauses.extend(exact_xor(vs,rhs))
    xorpool=list(range(1,37))
    outside=list(range(37,n+1))
    for j in range(144):
        # Controlled boundary crossing, not a proof that "mix" is uniquely defined.
        crossing=(j*100//144)<mix
        if crossing:
            vs=[rng.choice(xorpool),*rng.sample(outside,2)]
        else:
            vs=rng.sample(outside,3)
        signs=[rng.randrange(2) for _ in vs]
        if not any(signs[k]==w[v] for k,v in enumerate(vs)):
            k=rng.randrange(3);signs[k]=w[vs[k]]
        clauses.append(tuple(v if signs[k] else -v for k,v in enumerate(vs)))
    clauses=list(dict.fromkeys(clauses))
    rng.shuffle(clauses)
    return n,clauses,"SAT",mix

def freeze():
    need(nh.sha(ROOT/"source/frozen/manifest.json")==PREVIOUS_MANIFEST_SHA,
         "original frozen source manifest changed")
    previous=read(ROOT/"source/frozen/manifest.json")
    known=sorted((c for c in previous["cases"] if c["real"]),key=lambda c:c["sha256"])
    need(len(known)==25,"expected original 25 real sources")
    FROZEN.mkdir(parents=True,exist_ok=True)
    cases=[]
    for c in known[:EXTERNAL_COUNT]:
        source=ROOT/"source/frozen"/(c["id"]+".cnf")
        need(nh.sha(source)==c["sha256"],"real original SHA changed")
        dest=FROZEN/("real-"+c["id"]+".cnf")
        dest.write_bytes(source.read_bytes())
        cases.append(dict(id="real-"+c["id"],origin="reused_external_original",family="original_unknown",
                          expected=c.get("expected","UNKNOWN"),sha256=nh.sha(dest),cap_s=10.0))
    for family in gen.FAMILIES:
        for j in range(4):
            i=400+j
            n,clauses,expected=gen.generated(family,i)
            id=f"new-{family}-{j}"
            path=FROZEN/(id+".cnf")
            path.write_text(make_cnf(n,clauses,"new seed; known R186 generator family"))
            cases.append(dict(id=id,origin="new_seed_known_family",family=family,
                              expected=expected,sha256=nh.sha(path),cap_s=3.0))
    for i in range(PURE_COUNT):
        n,clauses,expected=generated_pure(i)
        id=f"pure-xor3-{i}"
        path=FROZEN/(id+".cnf")
        path.write_text(make_cnf(n,clauses,"new horizon complete source XOR3"))
        cases.append(dict(id=id,origin="synthetic_controlled",family="pure_xor3",
                          expected=expected,sha256=nh.sha(path),cap_s=3.0))
    for i in range(COUPLED_COUNT):
        n,clauses,expected,mix=generated_coupling(i)
        id=f"coupled-xor3-{i}"
        path=FROZEN/(id+".cnf")
        path.write_text(make_cnf(n,clauses,f"controlled coupling percentage {mix}"))
        cases.append(dict(id=id,origin="synthetic_controlled",family="coupled_xor3",
                          expected=expected,sha256=nh.sha(path),cap_s=3.0,
                          construction_crossing_percent=mix))
    need(len(cases)==TOTAL and len({c["sha256"] for c in cases})==TOTAL,
         "source count or duplicate SHA")
    random.Random(PROTO).shuffle(cases)
    save(FROZEN/"manifest.json",dict(protocol=PROTO,cases=cases,
         original_reused_not_blind=True,
         synthetic_generator_families_known=True,
         routing_inputs_exclude_family_id_expected=True,
         baseline="CaDiCaL 2.1.0 same pinned native binary",
         modes=MODES,repetitions=REPS,shards=SHARDS))
    verify()
    print("NEW_HORIZON_FROZEN_PASS",json.dumps({"formulas":TOTAL,
         "source_sha256":nh.sha(FROZEN/"manifest.json")}),flush=True)

def verify():
    m=read(FROZEN/"manifest.json")
    need(m["protocol"]==PROTO and len(m["cases"])==TOTAL,"bad frozen manifest")
    need(len({c["sha256"] for c in m["cases"]})==TOTAL,"sha reuse")
    for c in m["cases"]:
        need(nh.sha(FROZEN/(c["id"]+".cnf"))==c["sha256"],
             "source file drift "+c["id"])
    return m["cases"]

def trial(c,mode,rep,binary):
    p=FROZEN/(c["id"]+".cnf")
    need(nh.sha(p)==c["sha256"],"input changed")
    temp=ROOT/"temp"/f"{c['sha256'][:14]}-{rep}-{mode}"
    result=nh.run_one(p,binary,float(c["cap_s"]),mode,temp)
    status=result["status"]
    need(status in ("SAT","UNSAT","TIMEOUT"),"unknown status")
    if status!="TIMEOUT" and c["expected"] in ("SAT","UNSAT"):
        need(status==c["expected"],"wrong SAT answer")
    elapsed=result["elapsed"]
    return dict(id=c["id"],sha256=c["sha256"],origin=c["origin"],
                family=c["family"],construction_crossing_percent=c.get("construction_crossing_percent"),
                mode=mode,rep=rep,status=status,
                cap_s=c["cap_s"],elapsed_s=round(elapsed,6),
                par2_s=round(2*c["cap_s"] if status=="TIMEOUT" else elapsed,6),
                proof=result["proof"],route=result["route"],reason=result["reason"],
                scan_s=round(result["screen"]["scan_s"],6) if result["screen"] else 0,
                classification=result["screen"]["classification"] if result["screen"] else None,
                motif_pointer=result["screen"]["motif_pointer"] if result["screen"] else None,
                exact_xor3=result["screen"]["complete_xor3"] if result["screen"] else None,
                boundary=result["screen"]["boundary_occurrences"] if result["screen"] else None,
                derived_units=(result["preprocess"] or {}).get("units",0))

def shard(index,binary):
    cases=verify()
    need(0<=index<SHARDS and pathlib.Path(binary).is_file(),"invalid shard or native")
    data=[]
    for c in cases[index::SHARDS]:
        for rep in range(REPS):
            order=list(MODES)
            random.Random(PROTO+c["sha256"]+str(rep)).shuffle(order)
            for mode in order:
                x=trial(c,mode,rep,binary)
                data.append(x)
                save(ROOT/f"shard-{index}.json",data)
                print("NEW_HORIZON_TRIAL",json.dumps({k:x[k] for k in
                      ("id","mode","status","elapsed_s","route","classification",
                       "exact_xor3","derived_units")}),flush=True)
    need(len(data)==len(cases[index::SHARDS])*REPS*len(MODES),
         "unfinished paired shard")
    print("NEW_HORIZON_SHARD_PASS",index,len(data),flush=True)

def audit():
    cases=verify()
    rows=[]
    for i in range(SHARDS):
        z=read(ROOT/f"shard-{i}.json")
        need(len(z)==len(cases[i::SHARDS])*REPS*len(MODES),"missing shard rows")
        rows.extend(z)
    need(len(rows)==TOTAL*REPS*len(MODES),"incomplete matched audit")
    bysha={c["sha256"]:c for c in cases}
    pairs=collections.defaultdict(list)
    for r in rows:
        need(r["sha256"] in bysha and
             r["id"]==bysha[r["sha256"]]["id"],"source/ID drift")
        need(abs(r["par2_s"]-(r["elapsed_s"] if r["status"]!="TIMEOUT"
             else 2*r["cap_s"]))<0.00001,"PAR2 accounting")
        pairs[r["sha256"],r["rep"]].append(r)
    for c in cases:
        for rep in range(REPS):
            group=pairs[c["sha256"],rep]
            need(len(group)==len(MODES) and {r["mode"] for r in group}==set(MODES),
                 "arm mismatch")
            need(len({r["status"] for r in group if r["status"]!="TIMEOUT"})<=1,
                 "contradictory solver answers")
    output={}
    for cohort in ("all","reused_external_original","new_seed_known_family",
                   "synthetic_controlled"):
        caseset={c["sha256"] for c in cases
                 if cohort=="all" or c["origin"]==cohort}
        bymode={}
        for mode in MODES:
            sub=[r for r in rows if r["mode"]==mode and r["sha256"] in caseset]
            bymode[mode]=dict(trials=len(sub),solved=sum(r["status"]!="TIMEOUT" for r in sub),
                par2_s=round(sum(r["par2_s"] for r in sub),5),
                runtime_s=round(sum(r["elapsed_s"] for r in sub),5),
                routed=collections.Counter(r["route"] for r in sub))
        output[cohort]=bymode
    for level in (0,25,50,75,100):
        for mode in MODES:
            sub=[r for r in rows if r["mode"]==mode
                 and r["construction_crossing_percent"]==level]
            output.setdefault("coupling_percent="+str(level),{})[mode]=dict(
              trials=len(sub),solved=sum(r["status"]!="TIMEOUT" for r in sub),
              par2_s=round(sum(r["par2_s"] for r in sub),5),
              derived_units=sum(r["derived_units"] for r in sub))
    report=dict(protocol=PROTO,status="AUDIT_PASS_NOT_BLIND",
                cases=TOTAL,repetitions=REPS,trials=len(rows),
                same_source_paired=True,known_external_reused=True,
                caution="No claim of general SAT advantage or blind holdout",
                summary=output)
    save(ROOT/"report.json",report)
    save(ROOT/"trials.json",rows)
    keys=list(rows[0].keys())
    with (ROOT/"trials.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(rows)
    lines=["# DRNAS New Horizon SAT R1 — SHA matched pilot","",
           f"{TOTAL} formulas; {REPS} repetitions; {len(rows)} paired attempts; NOT blind external.","",
           "| Cohort | Method | Solved | PAR2 s |",
           "|---|---|---:|---:|"]
    for cohort,v in output.items():
        if cohort.startswith("coupling_percent="):continue
        for mode,s in v.items():
            lines.append(f"| {cohort} | {mode} | {s['solved']}/{s['trials']} | {s['par2_s']:.4f} |")
    lines += ["","## Limitations",
              "- Early structural scan is an observation, not a proof that a formula is mixed.",
              "- Only complete XOR3 truth-table patterns yield certified equations.",
              "- GF(2) UNSAT derivations have replayed algebraic certificates; external LRAT not supplied.",
              "- Native CDCL UNSAT is not independently proof checked.",
              "- Reused originals are not blind. Synthetic family generation is known.",
              "- Every analysis and preprocessing step is included in elapsed wall time."]
    (ROOT/"summary.md").write_text("\n".join(lines)+"\n")
    print("NEW_HORIZON_FINAL",json.dumps({k:v["new_horizon"] for k,v in output.items()
        if not k.startswith("coupling_percent")},sort_keys=True),flush=True)

def selftest():
    nh.selftest()
    for i in range(PURE_COUNT):
        n,clauses,expect=generated_pure(i)
        with __import__("tempfile").TemporaryDirectory() as td:
            p=pathlib.Path(td)/"p.cnf"
            p.write_text(make_cnf(n,clauses,"selftest"))
            result=nh.pure.solve(p)
            need(result["status"]==expect,"source pure SAT/UNSAT")
    for i in range(COUPLED_COUNT):
        n,clauses,expect,mix=generated_coupling(i)
        with __import__("tempfile").TemporaryDirectory() as td:
            p=pathlib.Path(td)/"m.cnf"
            p.write_text(make_cnf(n,clauses,"selftest"))
            info=nh.fingerprint(p)
            need(info["complete_xor3"]>=3,"controlled XOR motifs missing")
            if mix==0:need(info["boundary_occurrences"]==0,"zero crossing was coupled")
            if mix==100:need(info["boundary_occurrences"]>0,"max crossing absent")
    print("NEW_HORIZON_GENERATOR_SELFTEST_PASS",PURE_COUNT+COUPLED_COUNT,flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("command",choices=["selftest","freeze","verify","shard","audit"])
    p.add_argument("--shard",type=int,default=0)
    p.add_argument("--binary",default="new_horizon/r190-driver")
    a=p.parse_args()
    if a.command=="selftest":selftest()
    elif a.command=="freeze":freeze()
    elif a.command=="verify":print("NEW_HORIZON_VERIFY_PASS",len(verify()))
    elif a.command=="shard":shard(a.shard,pathlib.Path(a.binary))
    elif a.command=="audit":audit()
