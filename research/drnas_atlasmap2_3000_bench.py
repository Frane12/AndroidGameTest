#!/usr/bin/env python3
"""MAP2 3000 deterministic distinct mixed CNFs; 60 shards x 50 source SHA.
Strict source-disjoint 1500 train vs 1500 frozen evaluation. Original model
checks, one CPU per arm, PAR2, source SHA; no synthetic speedup claims.
"""
import hashlib,json,os,pathlib,random,sys,time
sys.path.insert(0,"research")
import drnas_atlasmap2_learn as L

SHARD=int(os.environ.get("MAP2_3K_SHARD","0"))
assert 0<=SHARD<60
CAP=20.0
OUT=pathlib.Path("mre_atlasmap2_3k")
OUT.mkdir(exist_ok=True)
BIN="mre_atlasmap2/bin/drnas_atlasmap2"
ARMS=("A","SHADOW","LIVE")
N=96
ROWS=[]
seen=set()
summary={a:{"solved":0,"timeouts":0,"PAR2_s":0.0,"E2E_s":0.0,
            "decisions":0,"conflicts":0,"live_implications":0,
            "shadow_opportunities":0} for a in ARMS}

def formula(index):
    rng=random.Random(20261111+index*997)
    truth={v:bool(rng.getrandbits(1)) for v in range(1,N+1)}
    clauses=[]
    # Certified XOR2 connected blocks; group sizes <= 32.
    for x in range(1,32):
        y=x+1
        rhs=int(truth[x]^truth[y])
        clauses.extend(([-x,y],[x,-y]) if rhs==0 else ([x,y],[-x,-y]))
    # 3-SAT background with planted SAT witness; each formula is unique.
    for _ in range(360):
        variables=rng.sample(range(1,N+1),3)
        c=[v if rng.getrandbits(1) else -v for v in variables]
        if not any(truth[abs(l)]==(l>0) for l in c):
            v=variables[0];c[0]=v if truth[v] else -v
        clauses.append(c)
    clauses.append([1 if truth[1] else -1])
    rng.shuffle(clauses)
    data=(f"p cnf {N} {len(clauses)}\n"+
          "".join(" ".join(map(str,c))+" 0\n" for c in clauses))
    return data

def save_checkpoint():
    payload={"experiment":"MAP2-3K-60shards-50each-20s-1CPU",
      "shard":SHARD,"count":len(ROWS)//3,
      "train_or_holdout":"train" if SHARD<30 else "holdout",
      "summary":summary,"rows":ROWS,
      "note":"constructed planted-SAT controls, not official unseen SAT competition",
      "UNSAT_independent_LRAT":False}
    (OUT/"audit.json").write_text(json.dumps(payload,indent=2,sort_keys=True))

for local in range(50):
    index=SHARD*50+local
    data=formula(index)
    sha=hashlib.sha256(data.encode()).hexdigest()
    if sha in seen:raise RuntimeError("duplicate formula SHA")
    seen.add(sha)
    path=OUT/"current.cnf"
    path.write_text(data)
    _,n,clauses=L.read_cnf(path)
    for arm in ARMS:
        result=L.solve(BIN,path,arm,CAP,n,clauses)
        if result["status"]=="UNSAT":
            raise RuntimeError("UNSAT invalid on planted-SAT CNF")
        if result["status"]=="SAT" and not result["SAT_original_verified"]:
            raise RuntimeError("SAT model unverified")
        result.update({"index":index,"source_sha256":sha,
                       "cohort":"train" if index<1500 else "holdout"})
        ROWS.append(result)
        agg=summary[arm]
        agg["solved"]+=int(result["status"]=="SAT")
        agg["timeouts"]+=int(result["status"]=="UNKNOWN")
        for key in ("PAR2_s","E2E_s","decisions","conflicts",
                    "live_implications","shadow_opportunities"):
            agg[key]+=result[key]
    if (local+1)%10==0:
        save_checkpoint()
        print("MAP2_3K_PROGRESS "+json.dumps({
          "shard":SHARD,"done":local+1,"of":50,
          "summary":summary},sort_keys=True),flush=True)
save_checkpoint()
print("MAP2_3K_FINAL "+json.dumps({"shard":SHARD,"count":50,
      "cohort":"train" if SHARD<15 else "holdout",
      "summary":summary},sort_keys=True),flush=True)
