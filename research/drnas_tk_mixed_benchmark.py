#!/usr/bin/env python3
"""Fresh, planted mixed XOR+3CNF benchmark; paired clean/shadow/active arms."""
import argparse, hashlib, itertools, json, pathlib, random, sys, statistics
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import ultimate_t2_benchmark as t

ROOT=pathlib.Path("tk-mixed")
MODES=("t_clean","c1_lazy_shadow","c1_lazy_cooldown")
CAP=8.0
REPS=3
PROFILES=((32,14,100),(48,22,190),(64,30,280))

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def parity(a): return sum(a)&1

def make(seed, profile):
    n,nxor,nres=profile; rng=random.Random(seed); planted=[0]+[rng.randrange(2) for _ in range(n)]
    clauses=[]
    used=set()
    while len(used)<nxor:
        vs=tuple(sorted(rng.sample(range(1,n+1),3)))
        if vs in used: continue
        used.add(vs); rhs=parity(planted[v] for v in vs)
        # Forbid all assignments that violate XOR; each forbidden assignment
        # becomes one clause false exactly on that assignment.
        for bits in itertools.product((0,1),repeat=3):
            if parity(bits)==rhs: continue
            clauses.append([v if bit==0 else -v for v,bit in zip(vs,bits)])
    # Planted 3-CNF residual: every clause contains a false literal at the
    # planted assignment, so the generated source has a known SAT witness.
    for _ in range(nres):
        vs=rng.sample(range(1,n+1),3)
        lits=[v if planted[v]==0 else -v for v in vs]
        flip=rng.randrange(3); lits[flip]=-lits[flip]
        clauses.append(lits)
    rng.shuffle(clauses)
    return n,clauses,planted

def freeze():
    ROOT.mkdir(exist_ok=True)
    cases=[]
    for pi,profile in enumerate(PROFILES):
        for j in range(3):
            name=f"mix-p{pi}-s{j}.cnf"; n,cs,model=make(912700+pi*100+j,profile)
            p=ROOT/name;p.write_text(f"p cnf {n} {len(cs)}\n"+"".join(" ".join(map(str,c))+" 0\n" for c in cs))
            cases.append(dict(id=name[:-4],path=str(p),sha256=sha(p),nvars=n,nclauses=len(cs),profile=pi,known="SAT",witness=[v if model[v] else -v for v in range(1,n+1)]))
    manifest=dict(protocol="TK-MIXED-PLANTED-12-v1",profiles=PROFILES,cap_s=CAP,repetitions=REPS,cases=cases,source_hashes_unique=len({c["sha256"] for c in cases})==12)
    (ROOT/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
    print("TK_MIX_FREEZE_PASS",json.dumps({"formulae":12,"attempts":12*REPS*len(MODES),"profiles":PROFILES}),flush=True)

def run_case(c, rep):
    p=pathlib.Path(c["path"]); out=[]
    order=list(MODES);random.Random(c["sha256"]+str(rep)).shuffle(order)
    for mode in order:
        status,elapsed,raw,gate,native,killed,started,progress=t.run_one(p,mode,CAP,c["sha256"])
        if not gate or gate.get("source_sha256")!=c["sha256"] or not gate.get("eligible"):
            raise RuntimeError("XOR source gate did not activate for "+c["id"]+" gate="+json.dumps(gate,sort_keys=True))
        if status=="SAT": t.prior.helper.gf.sat_check(t.prior.helper.gf.dimacs(p)[1],t.prior.model(raw))
        # Independently validate generated witness too.
        assignment={abs(x):x>0 for x in c["witness"]}
        _,dimacs=t.prior.helper.gf.dimacs(p);t.prior.helper.gf.sat_check(dimacs,assignment)
        out.append(dict(id=c["id"],sha256=c["sha256"],profile=c["profile"],rep=rep,mode=mode,status=status,elapsed_s=round(elapsed,7),prep_s=gate.get("prep_s",0),proposals=int(native.get("direct_proposals",0)),reasons=int(native.get("reason_clauses_completed",0)),progress=progress,activated=started==mode))
    return out

def shard(i):
    manifest=json.loads((ROOT/"manifest.json").read_text());rows=[]
    cases=manifest["cases"][i::3]
    for c in cases:
        for rep in range(REPS):
            rows+=run_case(c,rep)
            (ROOT/f"shard-{i}.json").write_text(json.dumps(rows,indent=2)+"\n")
            print("TK_MIX_PAIR",json.dumps(rows[-3:],sort_keys=True),flush=True)
    print("TK_MIX_SHARD_PASS",i,len(rows),flush=True)

def audit():
    m=json.loads((ROOT/"manifest.json").read_text());allrows=[]
    for i in range(3):
        rows=json.loads((ROOT/f"shard-{i}.json").read_text())
        if len(rows)!=4*REPS*len(MODES):raise RuntimeError("incomplete shard")
        allrows+=rows
    expected={(c["sha256"],r,mode) for c in m["cases"] for r in range(REPS) for mode in MODES}
    got={(x["sha256"],x["rep"],x["mode"]) for x in allrows}
    if len(got)!=len(allrows) or got!=expected:raise RuntimeError("source pairing mismatch")
    by={}
    for x in allrows:by.setdefault((x["sha256"],x["rep"]),{})[x["mode"]]=x
    formula=[]
    for c in m["cases"]:
        pairs=[by[(c["sha256"],r)] for r in range(REPS)]
        means={mode:statistics.mean(p[mode]["elapsed_s"] for p in pairs) for mode in MODES}
        clean=means["t_clean"]
        formula.append(dict(id=c["id"],profile=c["profile"],clean_mean_s=round(clean,7),shadow_mean_s=round(means["c1_lazy_shadow"],7),active_mean_s=round(means["c1_lazy_cooldown"],7),active_vs_clean_pct=round((clean/means["c1_lazy_cooldown"]-1)*100,2),shadow_vs_clean_pct=round((clean/means["c1_lazy_shadow"]-1)*100,2)))
    summary={mode:dict(solved=sum(x["status"]=="SAT" for x in allrows if x["mode"]==mode),elapsed_s=round(sum(x["elapsed_s"] for x in allrows if x["mode"]==mode),6),reasons=sum(x["reasons"] for x in allrows if x["mode"]==mode),proposals=sum(x["proposals"] for x in allrows if x["mode"]==mode)) for mode in MODES}
    report=dict(status="TK_MIXED_AUDIT_PASS",scope="12 deterministic planted SAT mixed formulas; generated cohort; not external blind benchmark",attempts=len(allrows),formulas=12,repetitions=REPS,cap_s=CAP,summary=summary,per_formula=formula)
    (ROOT/"report.json").write_text(json.dumps(report,indent=2)+"\n")
    print("TK_MIXED_FINAL",json.dumps(report,sort_keys=True),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("action",choices=("freeze","shard","audit"));p.add_argument("--shard",type=int,default=0);a=p.parse_args()
    {"freeze":freeze,"shard":lambda:shard(a.shard),"audit":audit}[a.action]()
