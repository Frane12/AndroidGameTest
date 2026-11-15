#!/usr/bin/env python3
"""SAT-MATCH1 positive constructed controls + frozen original SAT2024 screening."""
import collections,hashlib,json,os,random,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from model import construct_sat,parse_cnf,verify

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/"sat_match1_results"

def write(n,clauses,path):
    path.write_text(f"p cnf {n} {len(clauses)}\n"+
        "".join(" ".join(map(str,c))+" 0\n" for c in clauses))

def generate(seed,resources,jobs,unknown=False):
    rng=random.Random(seed)
    if unknown:
        # By pigeonhole / Hall, more jobs than available resources.
        opts=[list(range(resources)) for _ in range(jobs)]
    else:
        # A known injection makes the source SAT.
        chosen=rng.sample(range(resources),jobs)
        opts=[]
        for c in chosen:
            x=set([c])
            x.update(rng.sample(range(resources),min(3,resources)))
            opts.append(sorted(x))
    var=lambda j,r:1+j*resources+r
    clauses=[]
    for j,options in enumerate(opts):
        clauses.append([var(j,r) for r in options])
        for a in options:
            for b in options:
                if a<b:clauses.append([-var(j,a),-var(j,b)])
    for r in range(resources):
        for a in range(jobs):
            for b in range(a+1,jobs):
                if r in opts[a] and r in opts[b]:
                    clauses.append([-var(a,r),-var(b,r)])
    rng.shuffle(clauses)
    return jobs*resources,clauses

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def run():
    OUT.mkdir(parents=True,exist_ok=True)
    cpu=min(os.sched_getaffinity(0));os.sched_setaffinity(0,{cpu})
    constructed=[];start=time.perf_counter()
    for i in range(120):
        n,clauses=generate(20261115+i,resources=8+i%10,jobs=5+i%10)
        # jobs<=resources by construction. The generator wraps matching.
        status,model,info=construct_sat(n,clauses)
        if status!="SAT" or not verify(n,clauses,model):
            raise RuntimeError(f"constructed SAT model missing {i} {info}")
        constructed.append((status,info))
    for i in range(20):
        resources=3+i%4
        n,clauses=generate(202601+i,resources,resources+1,unknown=True)
        status,model,info=construct_sat(n,clauses)
        if status=="SAT":raise RuntimeError(f"invalid Hall SAT output {i}")
        constructed.append((status,info))
    # Deliberate unsupported constraints must never give an unchecked answer.
    for i in range(20):
        n,clauses=generate(202712+i,9,7)
        clauses.append([1,-2,3])
        status,model,info=construct_sat(n,clauses)
        if status!="UNKNOWN":raise RuntimeError("unsupported input must abstain")
        constructed.append((status,info))
    positive=sum(s=="SAT" for s,_ in constructed)
    print("SAT_MATCH1_CONTROLS "+json.dumps(dict(known_sat=120,verified_sat=positive,
        known_hall_unsat=20,unsupported=20,invalid_answers=0)),flush=True)
    manifest=ROOT/"cf7/manifest.json"
    if not manifest.exists():
        (OUT/"controls.json").write_text(json.dumps(dict(verified_sat=positive),indent=2))
        return
    frozen=json.loads(manifest.read_text());assert frozen["count"]==100
    rows=[];reasons=collections.Counter()
    for source in frozen["sources"]:
        file=ROOT/source["path"]
        actual=digest(file)
        if actual!=source["sha256"]:raise RuntimeError("source SHA drift "+source["path"])
        tick=time.perf_counter()
        parsed,why=parse_cnf(file)
        if parsed is None:
            status,info="UNKNOWN",{"reason":why}
        else:
            n,clauses=parsed
            status,model,info=construct_sat(n,clauses)
            if status=="SAT":
                if not verify(n,clauses,model):raise RuntimeError("invalid original SAT")
                witness=OUT/f"source-{source['id']:03d}.model"
                witness.write_text("v "+" ".join(str((i+1) if b else -(i+1))
                    for i,b in enumerate(model))+" 0\n")
        reasons[info["reason"]]+=1
        rows.append(dict(id=source["id"],source_sha256=actual,
            source_family=source["normalized_name_family"],status=status,
            reason=info["reason"],elapsed_s=round(time.perf_counter()-tick,6),
            details=info))
    (OUT/"real100.json").write_text(json.dumps(rows,indent=2,sort_keys=True)+"\n")
    (OUT/"protocol.json").write_text(json.dumps(dict(cpu=cpu,
        source_manifest_sha256=digest(manifest),original_count=100,
        model_algorithm="conservative component matching; verifies every original clause",
        gate="24MB max raw input, 15000 vars, 130000 clauses, 12000 selected literals",
        no_unsat_claims=True,synthetic_controls=160,elapsed_s=time.perf_counter()-start,
        git_sha=os.environ.get("GITHUB_SHA")),indent=2,sort_keys=True)+"\n")
    print("SAT_MATCH1_REAL100 "+json.dumps(dict(total=len(rows),
          model_verified=sum(x["status"]=="SAT" for x in rows),
          reasons=dict(reasons),elapsed_s=round(time.perf_counter()-start,3)),sort_keys=True),flush=True)

if __name__=="__main__":run()
