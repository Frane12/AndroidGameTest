#!/usr/bin/env python3
"""DRNAS SCC-C1 native C control: exact SCC-equivalence quotient before pinned CDCL.
Real E2E wall covers preprocessing, rewriting, model lifting, and solver execution.
No learned selector; historical official CNFs are NOT prospective/blind.
"""
from __future__ import annotations
import argparse, collections, hashlib, json, os, pathlib, random, subprocess, tempfile, time
ROOT=pathlib.Path("scc_c1_inputs")
OUT=pathlib.Path("scc_c1_out")
PROTO="DRNAS-SCC-C1-20-OFFICIAL-12-SYNTH-4ARMS-2REPS-12S-v1"
ARMS=("kissat","cadical","scc_kissat","scc_cadical")
CAP=12.0; REPS=2; SHARDS=4
REFERENCES=(
    (pathlib.Path("c12ref/c12_sources/manifest.json"),pathlib.Path("c12ref/c12_sources"),"official2026_C12_historical"),
    (pathlib.Path("c13_sources/manifest.json"),pathlib.Path("c13_sources"),"official2026_C13_historical"),
)
def need(cond,msg):
    if not cond:raise RuntimeError("SCC_C1_FAIL_CLOSED "+str(msg))
def sha(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for b in iter(lambda:f.read(1<<20),b""):h.update(b)
    return h.hexdigest()
def save(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,indent=2,sort_keys=True)+"\n")
def synthetic(i):
    # Deterministic planted SAT: 4 dense equivalence, 4 sparse, 2 no-SCC,
    # 2 2-SAT contradictory SCC. Generator frozen before timings.
    rng=random.Random(202611090200+i)
    n=[160,192,224,256,288,320,352,384,192,256,160,192][i]
    classes=[]
    if i<4: step=5
    elif i<8: step=3
    else: step=1
    truth=[False]*(n+1)
    equiv=[]
    for first in range(1,n+1,step):
        members=list(range(first,min(first+step,n+1)))
        bit=bool(rng.getrandbits(1))
        truth[first]=bit
        for v in members[1:]:
            same=bool(rng.getrandbits(1));truth[v]=bit if same else not bit
            a=first;b=v if same else -v
            equiv.extend([[-a,b],[a,-b]])
    for v in range(1,n+1):
        if v not in {x for cl in [] for x in cl} and step==1:truth[v]=bool(rng.getrandbits(1))
    cls=list(equiv)
    for _ in range(round(n*3.9)):
        vars=rng.sample(range(1,n+1),3)
        lit=[v if rng.getrandbits(1) else -v for v in vars]
        if not any(truth[abs(z)]==(z>0) for z in lit):
            j=rng.randrange(3);lit[j]=-lit[j]
        cls.append(lit)
    status="SAT"
    if i>=10:
        # Closed 2-SAT implications enforce a <-> not a, so UNSAT is sound.
        a,b,c=1,2,3
        cls.extend([[-a,b],[-b,-a],[a,c],[-c,a]])
        status="UNSAT"
    text="p cnf %d %d\n"%(n,len(cls))+"".join(" ".join(map(str,cl))+" 0\n" for cl in cls)
    return text,status,n,len(cls),len(equiv)
def prepare():
    ROOT.mkdir(exist_ok=True)
    cc=[];seen=set()
    for mp,basedir,cohort in REFERENCES:
        need(mp.is_file(),"missing historical SHA manifest "+str(mp))
        d=json.loads(mp.read_text());need(len(d["cases"]) in (8,12),"unexpected historical cohort size")
        for x in d["cases"]:
            source=basedir/x["filename"]
            need(source.is_file() and sha(source)==x["sha256"],"historical original SHA changed")
            need(x["sha256"] not in seen,"historical duplicate source SHA")
            seen.add(x["sha256"])
            cc.append(dict(name=x["gbd"],filename=str(source),cohort=cohort,
                    sha256=x["sha256"],status=x["status"],nvars=x.get("nvars",x.get("variables")),
                    nclauses=x.get("nclauses",x.get("clauses"))))
    for i in range(12):
        txt,status,n,m,eq=synthetic(i)
        p=ROOT/("synth-%02d.cnf"%i);p.write_text(txt)
        h=sha(p);need(h not in seen,"synthetic SHA collision");seen.add(h)
        cc.append(dict(name="synth-%02d"%i,filename=str(p),cohort="synthetic_equivalence" if i<8 else "synthetic_plain_or_unsat",
                       sha256=h,status=status,nvars=n,nclauses=m,generated_equiv_clauses=eq))
    need(len(cc)==32 and len(seen)==32,"unexpected cohort size")
    save(ROOT/"manifest.json",dict(protocol=PROTO,cases=cc,source_count=32,
         historical_official_cohorts_are_NOT_blind=True,synth_sources_precommitted=True,
         frozen_native_C_source="research/scc_c1_native.c",cap_s=CAP,
         no_auto_promotion=True,unsat_independent_LRAT=False))
    print("SCC_C1_FROZEN",json.dumps(dict(sources=len(cc),official=20,synthetic=12),sort_keys=True),flush=True)
def cases():
    d=json.loads((ROOT/"manifest.json").read_text());need(d["protocol"]==PROTO,"protocol drift")
    cc=d["cases"];need(len(cc)==32,"missing sources")
    for x in cc:need(pathlib.Path(x["filename"]).is_file() and sha(x["filename"])==x["sha256"],"source SHA mismatch")
    return cc
def solver_binary(arm):
    return str(pathlib.Path("built/bin/kissat_4_0_4" if "kissat" in arm else "c8c/bin/plain").resolve())
def model(stdout,n):
    xs={}
    for line in stdout.splitlines():
        if line.startswith("v "):
            for t in line[2:].split():
                v=int(t)
                if v:xs[abs(v)]=(v>0)
    return [False]+[xs.get(i,False) for i in range(1,n+1)]
def original_sat_verified(filename,values):
    with open(filename,encoding="ascii",errors="replace") as f:
        clause=[]
        for line in f:
            s=line.strip()
            if not s or s.startswith(("c","p","%")):continue
            for t in s.split():
                lit=int(t)
                if lit==0:
                    if not any(values[abs(x)]==(x>0) for x in clause):return False
                    clause=[]
                else:
                    if abs(lit)>=len(values):return False
                    clause.append(lit)
        return not clause
def lift(mapping,reduced):
    lines=pathlib.Path(mapping).read_text().splitlines()
    need(lines[0].startswith("p map "),"mapping header missing")
    n=int(lines[0].split()[2]);need(len(lines)==n+1,"mapping size mismatch")
    mp=[int(x) for x in lines[1:]]
    need(all(1<=abs(v)<len(reduced) for v in mp),"reconstruction index outside solver model")
    return [False]+[reduced[abs(v)] if v>0 else not reduced[abs(v)] for v in mp]
def trial(x,arm,rep,position,seed):
    start=time.perf_counter();report=None;status="TIMEOUT";witness=False
    original=pathlib.Path(x["filename"]).resolve()
    with tempfile.TemporaryDirectory(prefix="scc-c1-") as tmp:
        reduced=pathlib.Path(tmp)/"reduced.cnf";mapping=pathlib.Path(tmp)/"mapping.txt"
        inp=original
        try:
            if arm.startswith("scc_"):
                remaining=CAP-(time.perf_counter()-start);need(remaining>0,"zero preprocess budget")
                z=subprocess.run(["scc_c1_bin/drnas_scc",str(original),str(reduced),str(mapping)],
                        text=True,capture_output=True,timeout=remaining)
                need(z.returncode==0,"native C preprocess failed: "+z.stderr[-800:])
                marks=[l for l in z.stdout.splitlines() if l.startswith("SCC_C1_FINAL ")]
                need(len(marks)==1,"missing native SCC meta")
                report=json.loads(marks[0].split(" ",1)[1])
                if report["status"]!="NO_CHANGE":inp=reduced
                else:need(report["merged_vars"]==0,"no-change mismatch")
            remaining=CAP-(time.perf_counter()-start)
            if remaining>0:
                z=subprocess.run([solver_binary(arm),str(inp)],text=True,capture_output=True,timeout=remaining)
                need(z.returncode in (10,20),"unexpected solver exit: "+str(z.returncode)+" "+z.stderr[-150:])
                status="SAT" if z.returncode==10 else "UNSAT"
                if status=="SAT":
                    k=int(report["new_vars"]) if report and report["status"]=="REDUCED" else x["nvars"]
                    vals=model(z.stdout,k)
                    if report and report["status"]=="REDUCED":vals=lift(mapping,vals)
                    elapsed=time.perf_counter()-start
                    witness=original_sat_verified(original,vals)
                    need(witness,"SAT output cannot be reconstructed into original satisfying assignment")
                else:elapsed=time.perf_counter()-start
                need(status==x["status"],"solver contradicts published reference")
            else:elapsed=time.perf_counter()-start
        except subprocess.TimeoutExpired:
            elapsed=time.perf_counter()-start;status="TIMEOUT"
    if elapsed>CAP:status="TIMEOUT";witness=False
    return dict(protocol=PROTO,source_sha256=x["sha256"],name=x["name"],cohort=x["cohort"],
                reference=x["status"],arm=arm,rep=rep,order_seed=seed,order_position=position,
                status=status,wall_s=round(elapsed,6),PAR2_s=round(elapsed if status!="TIMEOUT" else 2*CAP,6),
                solver_seed_changed=False,cap_s=CAP,full_E2E_preprocessing_and_model_lift_included=True,
                SAT_original_witness_verified=witness,UNSAT_independent_LRAT=False,
                scc=report,commit_sha=os.environ.get("GITHUB_SHA","local"))
def shard(i):
    need(i in range(SHARDS),"bad shard");cc=cases();OUT.mkdir(exist_ok=True)
    subset=[x for j,x in enumerate(cc) if j%SHARDS==i]
    need(len(subset)==8,"shard split")
    rows=[]
    for x in subset:
        for rep in range(REPS):
            seed=int(hashlib.sha256((PROTO+"|"+x["sha256"]+"|"+str(rep)).encode()).hexdigest()[:8],16)
            order=list(ARMS);random.Random(seed).shuffle(order)
            for pos,arm in enumerate(order):
                r=trial(x,arm,rep,pos,seed);rows.append(r)
                save(OUT/("shard-%d.json"%i),rows)
                print("SCC_C1_TRIAL",json.dumps(r,sort_keys=True),flush=True)
    need(len(rows)==64,"partial shard")
    print("SCC_C1_SHARD_PASS",i,len(rows),flush=True)
def audit():
    cc=cases();bysha={x["sha256"]:x for x in cc};rows=[]
    for i in range(SHARDS):
        p=OUT/("shard-%d.json"%i);need(p.is_file(),"missing shard")
        v=json.loads(p.read_text());need(len(v)==64,"incomplete shard");rows+=v
    need(len(rows)==256,"missing paired attempts")
    keys=set()
    for r in rows:
        x=bysha.get(r["source_sha256"])
        need(x is not None and x["name"]==r["name"],"bad source")
        need(r["arm"] in ARMS and r["rep"] in range(REPS),"bad arm or rep")
        k=(r["source_sha256"],r["arm"],r["rep"]);need(k not in keys,"duplicate paired trial");keys.add(k)
        need(r["full_E2E_preprocessing_and_model_lift_included"],"invalid end-to-end")
        if r["status"]=="TIMEOUT":need(r["PAR2_s"]==2*CAP,"wrong timeout PAR2")
        else:
            need(r["status"]==x["status"],"reference disagreement")
            if r["status"]=="SAT":need(r["SAT_original_witness_verified"],"no original witness")
    scores={}
    for cohort in ("all","official2026_C12_historical","official2026_C13_historical","synthetic_equivalence","synthetic_plain_or_unsat"):
        rs=[r for r in rows if cohort=="all" or r["cohort"]==cohort]
        group={}
        for arm in ARMS:
            aa=[r for r in rs if r["arm"]==arm]
            group[arm]=dict(PAR2_s=round(sum(v["PAR2_s"] for v in aa),6),
                             solved=sum(v["status"]!="TIMEOUT" for v in aa),
                             timeouts=sum(v["status"]=="TIMEOUT" for v in aa),attempts=len(aa),
                             reduced=sum(bool(v["scc"] and v["scc"]["status"]=="REDUCED") for v in aa))
        for arm in ARMS:
            base=group["kissat" if "kissat" in arm else "cadical"]["PAR2_s"]
            group[arm]["speedup_vs_same_backend_x"]=round(base/group[arm]["PAR2_s"],6)
        scores[cohort]=group
    per=[]
    for x in cc:
        aa=[r for r in rows if r["source_sha256"]==x["sha256"]]
        byarm={arm:dict(PAR2_s=round(sum(r["PAR2_s"] for r in aa if r["arm"]==arm),6),
                        solved=sum(r["status"]!="TIMEOUT" for r in aa if r["arm"]==arm)) for arm in ARMS}
        reduced=next((r["scc"] for r in aa if r["scc"] is not None),None)
        per.append(dict(name=x["name"],cohort=x["cohort"],sha256=x["sha256"],reference=x["status"],
                        geometry=reduced,arms=byarm))
    report=dict(protocol=PROTO,source_count=32,real_E2E_trials=256,cap_s=CAP,
                scores=scores,per_case=per,
                official_sources_were_previously_benchmarked=True,synthetic_families_precommitted=True,
                independent_solver_seeds=False,independent_UNSAT_LRAT=False,
                no_adaptive_routing=True,no_auto_promotion=True)
    save(OUT/"report.json",report)
    print("SCC_C1_FINAL",json.dumps({k:v for k,v in report.items() if k!="per_case"},sort_keys=True),flush=True)
    for row in per:print("SCC_C1_CASE",json.dumps(row,sort_keys=True),flush=True)
def main():
    p=argparse.ArgumentParser();p.add_argument("action",choices=("prepare","verify","shard","audit"))
    p.add_argument("--shard",type=int,default=0)
    a=p.parse_args()
    if a.action=="prepare":prepare()
    elif a.action=="verify":print("SCC_C1_SHA_VERIFIED",len(cases()),flush=True)
    elif a.action=="shard":shard(a.shard)
    else:audit()
if __name__=="__main__":main()
