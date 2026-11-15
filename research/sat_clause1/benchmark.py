#!/usr/bin/env python3
"""SAT-CLAUSE1 paired native-SAT pilot. Deterministic synthetic source-disjoint cases.
No training, solver portfolio, unverified UNSAT credit, or unpinned mutable inputs.
"""
import hashlib, json, os, random, re, statistics, subprocess, tempfile, time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BIN=ROOT/"build"/"drnas-sat-clause1"
OUT=ROOT/"sat_clause1_results"
CAP=1.0
ARMS={"OFF":[], "CLAUSE_SCORE":["--sat-clause1-score"],
      "CLAUSE_PROBE":["--sat-clause1-probe"]}
SEED=20261115
TIER='small'

def planted(seed, n=44, ratio=4.1):
    r=random.Random(seed); witness=[bool(r.randrange(2)) for _ in range(n)]
    out=[]
    for _ in range(round(n*ratio)):
        vs=r.sample(range(1,n+1),3)
        while True:
            c=[v if r.randrange(2) else -v for v in vs]
            if any((v>0)==witness[abs(v)-1] for v in c):break
        out.append(c)
    return n,out

def colorable(seed, vertices=13):
    r=random.Random(seed); colors=[r.randrange(3) for _ in range(vertices)]
    def var(v,c):return 3*v+c+1
    clauses=[]
    for v in range(vertices):
        clauses.append([var(v,c) for c in range(3)])
        for a in range(3):
            for b in range(a+1,3):clauses.append([-var(v,a),-var(v,b)])
    for a in range(vertices):
        for b in range(a+1,vertices):
            if colors[a]!=colors[b] and r.random()<0.60:
                for c in range(3):clauses.append([-var(a,c),-var(b,c)])
    return vertices*3,clauses

def parity(seed, n=22, eqs=27):
    r=random.Random(seed); witness=[r.randrange(2) for _ in range(n)]
    clauses=[]
    for _ in range(eqs):
        vs=r.sample(range(1,n+1),3)
        parity=sum(witness[v-1] for v in vs)%2
        for b0 in (0,1):
            for b1 in (0,1):
                for b2 in (0,1):
                    bits=(b0,b1,b2)
                    if sum(bits)%2==parity:continue
                    clauses.append([(-v if bit else v) for v,bit in zip(vs,bits)])
    return n,clauses

def matching(seed, resources=11, jobs=9):
    r=random.Random(seed); choices=[]
    # A known satisfying matching is included in each job's possible resources.
    assigned=r.sample(range(resources), jobs)
    for j in range(jobs):
        c=set([assigned[j]])
        c.update(r.sample(range(resources),4))
        choices.append(sorted(c))
    def v(j,k):return j*resources+k+1
    clauses=[]
    for j,items in enumerate(choices):
        clauses.append([v(j,k) for k in items])
        for a in items:
            for b in items:
                if a<b:clauses.append([-v(j,a),-v(j,b)])
    for k in range(resources):
        for i in range(jobs):
            for j in range(i+1,jobs):
                if k in choices[i] and k in choices[j]:
                    clauses.append([-v(i,k),-v(j,k)])
    return jobs*resources,clauses

def make_case(family,index):
    seed=SEED+1009*index+{"planted":17,"color":29,"parity":41,"matching":53}[family]
    if TIER=="medium":
        seed+=100000000
        if family=="planted":return planted(seed,n=100+20*(index%3),ratio=4.12)
        if family=="color":return colorable(seed,vertices=22+4*(index%3))
        if family=="parity":
            n=38+4*(index%3)
            return parity(seed,n=n,eqs=n+6)
        if family=="matching":
            n=21+3*(index%3)
            return matching(seed,resources=n,jobs=n-3)
    return {"planted":planted,"color":colorable,"parity":parity,
            "matching":matching}[family](seed)

def cnf_text(n,clauses):
    assert n>0 and all(all(0<abs(l)<=n for l in c) for c in clauses)
    return f"p cnf {n} {len(clauses)}\n"+"".join(" ".join(map(str,c))+" 0\n" for c in clauses)

def independent_sat_check(n,clauses,stdout):
    assignments={}
    for line in stdout.splitlines():
        if not line.startswith("v "):continue
        for word in line.split()[1:]:
            lit=int(word)
            if not lit:continue
            v=abs(lit)
            if not 1<=v<=n or (v in assignments and assignments[v]!=(lit>0)):
                return False
            assignments[v]=(lit>0)
    # Require a complete witness, and check ORIGINAL CNF, not transformed CNF.
    if len(assignments)!=n:return False
    return all(any(assignments[abs(l)]==(l>0) for l in c) for c in clauses)

def trial(source,arm,rep,cnf):
    cmd=[str(BIN),str(cnf),"--mode","core","--time",str(CAP),"--stats"]+ARMS[arm]
    start=time.perf_counter()
    try:
        proc=subprocess.run(cmd,capture_output=True,text=True,timeout=CAP+0.3,check=False)
        expired=False
    except subprocess.TimeoutExpired:
        proc=None;expired=True
    elapsed=time.perf_counter()-start
    status="TIMEOUT" if expired else "UNKNOWN"
    model=False;debug={}
    if proc is not None:
        if proc.returncode==10 and "s SATISFIABLE" in proc.stdout:
            model=independent_sat_check(source["n"],source["clauses"],proc.stdout)
            status="SAT_VERIFIED" if model else "INVALID_MODEL"
        elif proc.returncode==20:status="UNSAT_UNVERIFIED"
        elif proc.returncode not in (0,10,20):status="SOLVER_ERROR"
        for line in proc.stderr.splitlines():
            if line.startswith("X41_STATS "):
                try:
                    x=json.loads(line.split(" ",1)[1])
                    debug.update(decisions=x.get("decisions"),conflicts=x.get("conflicts"))
                except ValueError:pass
            if line.startswith("SAT_CLAUSE1_STATS "):
                try:debug.update(json.loads(line.split(" ",1)[1]))
                except ValueError:pass
    # All generated sources are SAT by construction; no UNSAT may be accepted.
    if status in ("INVALID_MODEL","SOLVER_ERROR","UNSAT_UNVERIFIED"):
        raise RuntimeError(f"CRITICAL {source['family']} #{source['id']} {arm} "
                           f"status={status}, stderr={(proc.stderr if proc else '')[-500:]}")
    accepted=model and elapsed<=CAP
    return dict(id=source["id"],family=source["family"],sha256=source["sha256"],
                arm=arm,rep=rep,status=status,accepted=accepted,
                e2e_s=elapsed,PAR2_s=elapsed if accepted else 2*CAP,**debug)

def run_tier(tier):
    global CAP,TIER
    TIER=tier
    CAP=1.0 if tier=='small' else 2.0
    if not BIN.is_file():raise RuntimeError(f"missing {BIN}")
    out=OUT/tier
    out.mkdir(parents=True,exist_ok=True)
    # Separate source identities; no outcomes or labels feed any policy.
    sources=[]
    for family in ("planted","color","parity","matching"):
        for index in range(12 if tier=='small' else 8):
            n,clauses=make_case(family,index)
            text=cnf_text(n,clauses)
            sid=f"{family}-{index:02d}"
            sources.append(dict(id=sid,family=family,n=n,clauses=clauses,
                                sha256=hashlib.sha256(text.encode()).hexdigest(),text=text))
    saved=[];started=time.perf_counter()
    try:
        cpu=min(os.sched_getaffinity(0))
        os.sched_setaffinity(0,{cpu})
        assert len(os.sched_getaffinity(0))==1
    except AttributeError:cpu=None
    with tempfile.TemporaryDirectory() as tmp:
        path=Path(tmp)/"source.cnf"
        for ix,source in enumerate(sources):
            path.write_text(source["text"])
            assert hashlib.sha256(path.read_bytes()).hexdigest()==source["sha256"]
            # Rotate order to reduce systematic time/order bias.
            for rep in range(2):
                arms=list(ARMS)
                offset=(ix+rep)%len(arms)
                for arm in arms[offset:]+arms[:offset]:
                    saved.append(trial(source,arm,rep,path))
    for family in ("planted","color","parity","matching","ALL"):
        subset=[r for r in saved if family=="ALL" or r["family"]==family]
        sums={}
        for arm in ARMS:
            xs=[r for r in subset if r["arm"]==arm]
            sums[arm]=dict(solved=sum(r["accepted"] for r in xs),
                           total=len(xs),par2_sum=round(sum(r["PAR2_s"] for r in xs),6),
                           median_s=round(statistics.median(r["e2e_s"] for r in xs),6),
                           flips=sum(r.get("phase_flips",0) for r in xs),
                           probes=sum(r.get("probe_pairs",0) for r in xs),
                           failed_literals=sum(r.get("failed_literals",0) for r in xs))
        print("SAT_CLAUSE1_SUMMARY "+json.dumps(dict(tier=tier,family=family,arms=sums),sort_keys=True),flush=True)
    manifest=[{k:s[k] for k in ("id","family","n","sha256")} for s in sources]
    (out/"manifest.json").write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n")
    (out/"trials.json").write_text(json.dumps(saved,indent=2,sort_keys=True)+"\n")
    (out/"protocol.json").write_text(json.dumps(dict(tier=tier,cap_s=CAP,repetitions=2,
               cpu=cpu,source_count=len(sources),seed=SEED,arms=ARMS,
               git_sha=os.environ.get("GITHUB_SHA"),elapsed_s=time.perf_counter()-started,
               note="synthetic SAT-only pilot; no generalization, no independent UNSAT proof"),
               indent=2,sort_keys=True)+"\n")
    print("SAT_CLAUSE1_DONE "+json.dumps(dict(sources=len(sources),
         tier=tier,trials=len(saved),artifact=str(out),elapsed_s=round(time.perf_counter()-started,3))),flush=True)

if __name__=="__main__":
    for tier in ("small","medium"):
        run_tier(tier)
