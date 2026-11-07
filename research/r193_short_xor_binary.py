#!/usr/bin/env python3
"""R193-SHORT: six-arm R193 dual live comparison across short XOR/binary/general CNFs.

44 freshly generated synthetic formulas, 11 structural families, 4 seeds,
2 paired repetitions, 6 arms = 528 source-matched attempts, 2.0 sec caps.
Build reuses EXACT SHA-pinned original R193 CaDiCaL native executable.
Synthetic generators and families are familiar (NOT blind industrial formulas).
SAT witnesses checked against original DIMACS; CDCL UNSAT is not LRAT verified.
"""
from __future__ import annotations
import argparse,collections,hashlib,itertools,json,pathlib,random,time
import r186_cheap_selector as gen
import r193_dual_live_benchmark as dual

ROOT=pathlib.Path("r193short")
FROZEN=ROOT/"frozen"
PROTO="R193-SHORT-XOR-2SAT-ALL-PAIRED-20261107-v1"
FAMILIES=(
 "xor_pure_sat","xor_pure_unsat",
 "mixed_xor_sat","mixed_xor_unsat",
 "two_sat_sat","two_sat_unsat",
 "horn_sat","planted_3sat",
 "pigeonhole_unsat","graph_3color_sat","graph_3color_unsat")
SEEDS=(24,32,40,48)
MODES=("default","sat","dual_fast","dual_learning",
       "dual_keep_default","dual_keep_sat")
CAP=2.0;REPS=2;SHARDS=8
R193_BINARY_SHA="3f355d18566d2ec080c8a38c0c317276f41c79c304c326f99ad63672b5a02c3b"

def need(x,msg):
    if not x:raise RuntimeError("R193SHORT_FAIL_CLOSED "+str(msg))
def sha(path):return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(pathlib.Path(path).read_text())
def save(path,data):
    p=pathlib.Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(data,indent=2,sort_keys=True)+"\n")

def generated(family,i):
    if family in gen.FAMILIES:
        return gen.generated(family,i)
    rnd=random.Random(761127+1009*FAMILIES.index(family)+i*97)
    n=60+2*i
    witness=[False]+[bool(rnd.getrandbits(1)) for _ in range(n)]
    clauses=[]
    expected="SAT"
    if family in ("xor_pure_sat","xor_pure_unsat"):
        seen=set()
        def quartet(vs,rhs):
            for bits in itertools.product((0,1),repeat=3):
                if (bits[0]^bits[1]^bits[2])!=rhs:
                    clauses.append(tuple(v if bit==0 else -v for v,bit in zip(vs,bits)))
        for k in range(min(n*2,96)):
            while True:
                vs=tuple(sorted(rnd.sample(range(1,n+1),3)))
                if vs not in seen:seen.add(vs);break
            rhs=sum(witness[v] for v in vs)%2
            quartet(vs,rhs)
            if k==0 and family=="xor_pure_unsat":
                quartet(vs,1-rhs)
                expected="UNSAT"
    elif family=="two_sat_sat":
        # Every binary clause has at least one literal true in fixed witness.
        for _ in range(n*4):
            a,b=rnd.sample(range(1,n+1),2)
            la=a if rnd.getrandbits(1) else -a
            lb=b if rnd.getrandbits(1) else -b
            if not ((la>0)==witness[a] or (lb>0)==witness[b]):
                lb=b if witness[b] else -b
            clauses.append((la,lb))
    else:raise RuntimeError("unknown generated family "+family)
    clauses=list(dict.fromkeys(clauses))
    return n,clauses,expected

def selftest():
    need(len(FAMILIES)==11 and len(set(FAMILIES))==11,"family set drift")
    need(len(SEEDS)==4 and CAP==2.0 and len(MODES)==6,"experiment plan drift")
    for family in FAMILIES:
        n,clauses,expected=generated(family,SEEDS[0])
        need(n>0 and clauses and expected in ("SAT","UNSAT"),"invalid generator "+family)
        if family.startswith("xor_pure_"):
            need(all(len(c)==3 for c in clauses),"pure XOR emitted non-3 clause")
        if family=="two_sat_sat":
            need(all(len(c)==2 for c in clauses),"2SAT emitted nonbinary")
    print("R193SHORT_SELFTEST_PASS",flush=True)

def freeze():
    FROZEN.mkdir(parents=True,exist_ok=True)
    cases=[]
    for family in FAMILIES:
        for index in SEEDS:
            n,clauses,expected=generated(family,index)
            cid=f"r193s-{family}-{index}"
            p=FROZEN/(cid+".cnf")
            raw=(f"c R193SHORT synthetic {family} index={index}\n"
                 +f"p cnf {n} {len(clauses)}\n"
                 +"".join(" ".join(str(v) for v in c)+" 0\n" for c in clauses))
            p.write_text(raw)
            cases.append(dict(id=cid,family=family,seed_index=index,
                cohort="new_seed_synthetic_known_generator_family",
                variables=n,clauses=len(clauses),status_expected=expected,
                sha256=sha(p),cap_s=CAP))
    need(len(cases)==44 and len({c["sha256"] for c in cases})==44,
         "44 SHA-unique CNFs required")
    random.Random(PROTO).shuffle(cases)
    save(FROZEN/"manifest.json",dict(protocol=PROTO,cases=cases,
      not_real_industrial=True,new_seed_known_families=True,
      R193_exact_native_sha256=R193_BINARY_SHA,
      cap_s=CAP,paired_repetitions=REPS,modes=MODES))
    verify()
    print("R193SHORT_FREEZE_PASS",json.dumps(dict(formulas=len(cases),
          families=len(FAMILIES),manifest_sha256=sha(FROZEN/"manifest.json"))),
          flush=True)

def verify():
    data=read(FROZEN/"manifest.json")
    need(data["protocol"]==PROTO and len(data["cases"])==44,
         "unexpected manifest")
    for c in data["cases"]:
        need(sha(FROZEN/(c["id"]+".cnf"))==c["sha256"],"source SHA drift")
    return data["cases"]

def trial(c,mode,rep,binary):
    src=FROZEN/(c["id"]+".cnf")
    need(sha(src)==c["sha256"],"source SHA drift inside trial")
    order=int(hashlib.sha256((PROTO+c["sha256"]+str(rep)).encode()).hexdigest()[:5],16)%2
    start=time.perf_counter()
    r=dual.native(binary,src,CAP,mode,order)
    elapsed=time.perf_counter()-start
    status=r["status"]
    if elapsed>=CAP:status="TIMEOUT"
    proof="CAP" if status=="TIMEOUT" else "CADICAL_UNSAT_NO_INDEPENDENT_LRAT"
    if status=="SAT":
        _,original=dual.helpers.gf.dimacs(src)
        dual.helpers.gf.sat_check(original,r["model"])
        proof="SAT_MODEL_VERIFIED_ORIGINAL"
    if status!="TIMEOUT":
        need(status==c["status_expected"],"generator result mismatch "+c["id"])
    return dict(id=c["id"],sha256=c["sha256"],family=c["family"],
       seed_index=c["seed_index"],mode=mode,rep=rep,order=order,
       status=status,expected=c["status_expected"],
       elapsed_s=round(elapsed,6),
       par2_s=round(2*CAP if status=="TIMEOUT" else elapsed,6),
       cap_s=CAP,choice=r["choice"],reason=r["reason"],
       pilot_s=round(sum(p["elapsed_s"] for p in r["pilots"]),6),
       proof=proof,**r["stats"])

def shard(index,binary):
    cases=verify()
    need(0<=index<SHARDS and binary.is_file() and sha(binary)==R193_BINARY_SHA,
         "native SHA / shard mismatch")
    rows=[]
    for c in cases[index::SHARDS]:
        for rep in range(REPS):
            modes=list(MODES)
            random.Random(PROTO+c["sha256"]+str(rep)).shuffle(modes)
            for mode in modes:
                row=trial(c,mode,rep,binary)
                rows.append(row)
                save(ROOT/f"shard-{index}.json",rows)
                print("R193SHORT_TRIAL",json.dumps({k:row[k] for k in
                  ("family","id","mode","rep","status","elapsed_s","pilot_s","choice")},
                  sort_keys=True),flush=True)
    need(len(rows)==len(cases[index::SHARDS])*REPS*len(MODES),
         "incomplete shard")
    print("R193SHORT_SHARD_PASS",index,len(rows),flush=True)

def audit():
    cases=verify()
    trials=[]
    for i in range(SHARDS):
        rr=read(ROOT/f"shard-{i}.json")
        need(len(rr)==len(cases[i::SHARDS])*REPS*len(MODES),
             "incomplete matrix")
        trials+=rr
    need(len(trials)==44*REPS*len(MODES)==528,
         "expected 528 trials")
    by=collections.defaultdict(list)
    found={c["sha256"]:c for c in cases}
    for r in trials:
        need(r["sha256"] in found,"missing known formula")
        need(abs(r["par2_s"]-(2*r["cap_s"] if r["status"]=="TIMEOUT" else
               r["elapsed_s"]))<1e-5,"PAR2 accounting")
        by[r["sha256"],r["rep"]].append(r)
    for c in cases:
        for rep in range(REPS):
            rs=by[c["sha256"],rep]
            need(len(rs)==len(MODES) and
                 {x["mode"] for x in rs}==set(MODES) and
                 len({x["order"] for x in rs})==1,"nonpaired arms")
            need(len({x["status"] for x in rs if x["status"]!="TIMEOUT"})<=1,
                 "contradictory SAT/UNSAT")
    groups={"all":cases}
    for family in FAMILIES:
        groups[family]=[c for c in cases if c["family"]==family]
    summary={}
    for label,subset in groups.items():
        modes={}
        for mode in MODES:
            a=[r for c in subset for rep in range(REPS)
               for r in by[c["sha256"],rep] if r["mode"]==mode]
            modes[mode]=dict(attempts=len(a),solved=sum(r["status"]!="TIMEOUT" for r in a),
                sat=sum(r["status"]=="SAT" for r in a),
                unsat=sum(r["status"]=="UNSAT" for r in a),
                par2_s=round(sum(r["par2_s"] for r in a),6),
                elapsed_wall_s=round(sum(r["elapsed_s"] for r in a),6),
                pilot_s=round(sum(r["pilot_s"] for r in a),6),
                chose_default=sum(r["choice"]=="default" for r in a),
                chose_sat=sum(r["choice"]=="sat" for r in a))
        summary[label]=dict(formulas=len(subset),modes=modes,
           speedup_vs_default={name:round(modes["default"]["par2_s"]/x["par2_s"],5)
                  for name,x in modes.items() if name!="default"},
           speedup_vs_sat={name:round(modes["sat"]["par2_s"]/x["par2_s"],5)
                  for name,x in modes.items() if name!="sat"})
    report=dict(protocol=PROTO,status="R193SHORT_PAIRED_AUDIT_PASS",
      formulas=len(cases),families=len(FAMILIES),attempts=len(trials),
      repetitions=REPS,cap_s=CAP,sha_pinned_original_r193_driver=R193_BINARY_SHA,
      same_original_sha_all_pairs=True,
      sat_witnesses_verified=True,independent_cdcl_unsat_lrat=False,
      not_real_industrial=True,not_new_family=True,groups=summary)
    save(ROOT/"report.json",report);save(ROOT/"trials.json",trials)
    with (ROOT/"summary.md").open("w") as f:
        f.write("# R193 short XOR / binary / all structures — full benchmark\n\n")
        f.write("44 SHA-frozen synthetic original CNFs, 11 structure families, "
                "6 exact R193 modes, 2 reps, 2-second caps (528 matched). "
                "No claims about blind real SAT or independent CDCL UNSAT LRAT.\n\n")
        f.write("| Family | Mode | Solved | PAR2 s | vs default | vs SAT |\\n"
                "|---|---|---:|---:|---:|---:|\\n")
        for fam in FAMILIES+("all",):
            for mode,m in summary[fam]["modes"].items():
                f.write(f"| {fam} | {mode} | {m['solved']}/{m['attempts']} | "
                        f"{m['par2_s']} | {summary[fam]['speedup_vs_default'].get(mode,'—')} | "
                        f"{summary[fam]['speedup_vs_sat'].get(mode,'—')} |\\n")
    print("R193SHORT_FINAL",json.dumps({"groups":summary},sort_keys=True),
          flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("selftest","freeze","verify","shard","audit"))
    p.add_argument("--shard",type=int,default=0)
    p.add_argument("--binary",default="r193short/r193-driver")
    a=p.parse_args()
    if a.action=="selftest":selftest()
    elif a.action=="freeze":freeze()
    elif a.action=="verify":print("R193SHORT_VERIFY_PASS",len(verify()),flush=True)
    elif a.action=="shard":shard(a.shard,pathlib.Path(a.binary))
    else:audit()
