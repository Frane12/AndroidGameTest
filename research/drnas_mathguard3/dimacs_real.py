#!/usr/bin/env python3
"""Unmodified public DIMACS graph instances; fair 3-colour proof-checked A/B/C.

Source graph bytes are downloaded from Carnegie Mellon University (CMU)
and SHA-frozen in the artifact. We neither plant motifs nor filter by outcome.
3-colour CNFs use the exact same encoding for BASE, GUARD2 and GUARD3.
"""
from pathlib import Path
import hashlib
import json
import os
import random
import resource
import signal
import statistics
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"research/drnas_mathguard1"))
import graph3 as graph

SOLVER=ROOT/"build/drnas-mathguard3"
DRAT=ROOT/"external/drat-trim/drat-trim"
OUT=ROOT/"mathguard3_dimacs_real"
SOURCE_DIR=OUT/"source"
CAP=3.0
REPEATS=2
ARMS=("BASE","GUARD2","GUARD3")

CASES=(
    ("myciel3",11,20,"https://mat.tepper.cmu.edu/COLOR/instances/myciel3.col","MYC"),
    ("myciel4",23,71,"https://mat.tepper.cmu.edu/COLOR/instances/myciel4.col","MYC"),
    ("myciel5",47,236,"https://mat.tepper.cmu.edu/COLOR/instances/myciel5.col","MYC"),
    ("myciel6",95,755,"https://mat.tepper.cmu.edu/COLOR/instances/myciel6.col","MYC"),
    ("myciel7",191,2360,"https://mat.tepper.cmu.edu/COLOR/instances/myciel7.col","MYC"),
    ("school1",385,19095,"https://mat.tepper.cmu.edu/COLOR/instances/school1.col","SCH"),
    ("school1_nsh",352,14612,"https://mat.tepper.cmu.edu/COLOR/instances/school1_nsh.col","SCH"),
    ("DSJC125.1",125,736,"https://mat.tepper.cmu.edu/COLOR04/INSTANCES/DSJC125.1.col","DSJC"),
    ("DSJC125.5",125,3891,"https://mat.tepper.cmu.edu/COLOR04/INSTANCES/DSJC125.5.col","DSJC"),
    ("DSJC125.9",125,6961,"https://mat.tepper.cmu.edu/COLOR04/INSTANCES/DSJC125.9.col","DSJC"),
)

def sha(b):return hashlib.sha256(b).hexdigest()

def parse_graph(data,name,n_expected,e_expected):
    text=data.decode("utf-8")
    header=None
    edges=[]
    for i,line in enumerate(text.splitlines(),1):
        line=line.strip()
        if not line or line[0]=="c":continue
        row=line.split()
        if row[0]=="p":
            if header is not None or len(row)!=4 or row[1]!="edge":
                raise ValueError(("BAD_HEADER",name,i,row))
            header=(int(row[2]),int(row[3]))
        elif row[0]=="e":
            if len(row)!=3 or header is None:raise ValueError(("BAD_EDGE",name,i,row))
            a,b=map(int,row[1:])
            if a==b or not(1<=a<=header[0] and 1<=b<=header[0]):
                raise ValueError(("BAD_VERTEX",name,i,a,b))
            edges.append(tuple(sorted((a-1,b-1))))
        else:
            raise ValueError(("UNEXPECTED_LINE",name,i,line[:60]))
    if header!=(n_expected,e_expected):
        raise ValueError(("GRAPH_HEADER_MISMATCH",name,header,n_expected,e_expected))
    if len(edges)!=e_expected or len(set(edges))!=e_expected:
        raise ValueError(("GRAPH_EDGE_MISMATCH_OR_DUPLICATES",name,len(edges),len(set(edges))))
    return sorted(edges)

def motifs(n,edges):
    adj=[set() for _ in range(n)]
    for u,v in edges:
        adj[u].add(v);adj[v].add(u)
    tri=0;diamonds=0;has_k4=False
    for u,v in edges:
        both=adj[u]&adj[v]
        tri+=sum(w>v for w in both)
        diamonds+=len(both)*(len(both)-1)//2
        if not has_k4 and len(both)>=2:
            for w in both:
                if adj[w] & both:
                    has_k4=True
                    break
    return dict(triangles=tri,diamond_candidates=diamonds,k4_certificate=has_k4)

def fetch_cases():
    SOURCE_DIR.mkdir(parents=True,exist_ok=True)
    cases=[]
    for name,n,m,url,family in CASES:
        req=urllib.request.Request(url,headers={"User-Agent":"DRNAS-mathguard-public-benchmark/1.0"})
        with urllib.request.urlopen(req,timeout=30) as response:
            raw=response.read(2_000_001)
            final_url=response.geturl()
        if len(raw)>2_000_000:raise RuntimeError(("SOURCE_TOO_LARGE",name))
        if final_url!=url:raise RuntimeError(("UNEXPECTED_REDIRECT",name,url,final_url))
        edges=parse_graph(raw,name,n,m)
        path=SOURCE_DIR/(name+".col")
        path.write_bytes(raw)
        case=dict(name=name,n=n,edges=edges,family=family,url=url,
            raw_sha256=sha(raw),raw_bytes=len(raw),
            **motifs(n,edges))
        cases.append(case)
        print("DIMACS_SOURCE "+json.dumps({k:v for k,v in case.items() if k!="edges"},sort_keys=True),flush=True)
    if len(set(c["raw_sha256"] for c in cases))!=len(cases):
        raise RuntimeError("DUPLICATED_SOURCE")
    manifest=[{k:v for k,v in case.items() if k!="edges"} for case in cases]
    OUT.mkdir(exist_ok=True)
    (OUT/"source_manifest.json").write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n")
    return cases

def parse_one(err,prefix):
    rows=[s[len(prefix)+1:] for s in err.splitlines() if s.startswith(prefix+" ")]
    return json.loads(rows[0]) if len(rows)==1 else {}

def test_case(case,arm,rep,temp):
    clauses=graph.cnf(case["n"],case["edges"])
    cnf=temp/"input.cnf"
    cnf.write_text(f"p cnf {3*case['n']} {len(clauses)}\n"+
        "".join(" ".join(map(str,c))+" 0\n" for c in clauses))
    cnf_sha=sha(cnf.read_bytes())
    proof=temp/"proof.drat"
    usage=temp/"usage.txt"
    cmd=[str(SOLVER),str(cnf),"--mode","core","--time",str(CAP-0.12),
         "--x5-no-minimize","--stats","--proof",str(proof)]
    if arm=="GUARD2":cmd+=["--math-guard2","--math-guard2-budget-ms","8"]
    if arm=="GUARD3":cmd+=["--math-guard3","--math-guard2-budget-ms","8"]
    command=["/usr/bin/time","-f","%U %S %M","-o",str(usage),*cmd]
    def limits():
        resource.setrlimit(resource.RLIMIT_AS,(3*1024**3,3*1024**3))
        resource.setrlimit(resource.RLIMIT_FSIZE,(128*1024**2,128*1024**2))
    start=time.perf_counter()
    p=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
        text=True,start_new_session=True,preexec_fn=limits)
    killed=False
    try:
        stdout,stderr=p.communicate(timeout=CAP+0.20)
    except subprocess.TimeoutExpired:
        killed=True
        os.killpg(p.pid,signal.SIGKILL)
        stdout,stderr=p.communicate()
    wall=time.perf_counter()-start
    status="TIMEOUT" if killed else "UNKNOWN"
    check_s=0
    if not killed and p.returncode==10:
        if not graph.sat_model(stdout,case["n"],clauses,case["edges"]):
            raise RuntimeError(("INVALID_SAT_MODEL",case["name"],arm,rep))
        status="SAT_VERIFIED"
    elif not killed and p.returncode==20:
        if not proof.exists() or not proof.stat().st_size:
            raise RuntimeError(("MISSING_UNSAT_PROOF",case["name"],arm,rep))
        start_verify=time.perf_counter()
        try:
            v=subprocess.run([str(DRAT),str(cnf),str(proof)],capture_output=True,
                             text=True,timeout=45)
        except subprocess.TimeoutExpired:
            status="UNSAT_PROOF_CHECK_TIMEOUT"
        else:
            if v.returncode!=0 or "s VERIFIED" not in v.stdout:
                raise RuntimeError(("INVALID_DRAT",case["name"],arm,rep,
                                    v.stdout[-600:],v.stderr[-300:]))
            status="UNSAT_CERTIFIED"
        check_s=time.perf_counter()-start_verify
    elif not killed and p.returncode not in (0,153):
        raise RuntimeError(("SOLVER_ERROR",case["name"],arm,rep,p.returncode,stderr[-600:]))
    verified=status in ("SAT_VERIFIED","UNSAT_CERTIFIED") and wall<=CAP
    t=parse_one(stderr,"X41_STATS")
    g2=parse_one(stderr,"MATH_GUARD2_STATS")
    g3=parse_one(stderr,"MATH_GUARD3_STATS")
    if not killed and arm=="GUARD3" and not g3.get("enabled"):
        raise RuntimeError(("MISSING_GUARD3_STATS",case["name"],rep))
    if not killed and arm=="GUARD3":
        if not g3.get("triggered") and g2.get("lemmas",0):
            raise RuntimeError(("LEMMAS_WITHOUT_GUARD3_TRIGGER",case["name"],rep))
    cpu_s=maxrss=None
    if usage.exists():
        parts=usage.read_text().split()
        if len(parts)==3:
            cpu_s=float(parts[0])+float(parts[1]);maxrss=int(parts[2])
    proof.unlink(missing_ok=True)
    row=dict(graph=case["name"],family=case["family"],vertices=case["n"],
        edges=len(case["edges"]),graph_sha256=case["raw_sha256"],cnf_sha256=cnf_sha,
        rep=rep,arm=arm,status=status,verified=verified,
        wall_e2e_s=wall,cpu_s=cpu_s,maxrss_kib=maxrss,proof_check_s=check_s,
        PAR2_verified_s=wall if verified else 2*CAP,
        conflicts=t.get("conflicts"),decisions=t.get("decisions"),
        guard2_lemmas=g2.get("lemmas",0),guard2_budget_hit=g2.get("budget_hit",False),
        guard3_trigger=g3.get("triggered",False),guard3_equalities=g3.get("equalities",0),
        guard3_path=g3.get("selected_path",0),guard_wall_ms=g2.get("wall_ms",0))
    print("DIMACS_REAL_TRIAL "+json.dumps(row,sort_keys=True),flush=True)
    return row

def main():
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    if not SOLVER.is_file() or not DRAT.is_file():raise RuntimeError("MISSING_BINARY")
    cases=fetch_cases()
    rows=[]
    with tempfile.TemporaryDirectory() as root:
        for case in cases:
            for rep in range(REPEATS):
                arms=list(ARMS)
                random.Random(int(case["raw_sha256"][:16],16)+rep*101).shuffle(arms)
                for arm in arms:
                    with tempfile.TemporaryDirectory(dir=root) as tmp:
                        rows.append(test_case(case,arm,rep,Path(tmp)))
    (OUT/"trials.json").write_text(json.dumps(rows,indent=2,sort_keys=True)+"\n")
    aggregate={}
    for arm in ARMS:
        x=[r for r in rows if r["arm"]==arm]
        aggregate[arm]=dict(verified=sum(r["verified"] for r in x),
            PAR2_verified_s=sum(r["PAR2_verified_s"] for r in x),
            cpu_s=sum(r["cpu_s"] for r in x if r["cpu_s"] is not None),
            conflicts=sum(r["conflicts"] or 0 for r in x),
            decisions=sum(r["decisions"] or 0 for r in x),
            guard_lemmas=sum(r["guard2_lemmas"] for r in x),
            triggered=sum(r["guard3_trigger"] for r in x),
            budget_hits=sum(r["guard2_budget_hit"] for r in x))
    per_graph=[]
    speedups=[]
    for case in cases:
        group=[r for r in rows if r["graph"]==case["name"]]
        entry=dict(name=case["name"],family=case["family"],
            vertices=case["n"],edges=len(case["edges"]),
            triangles=case["triangles"],diamonds=case["diamond_candidates"],
            k4=case["k4_certificate"],arms={})
        for arm in ARMS:
            x=[r for r in group if r["arm"]==arm]
            entry["arms"][arm]=dict(statuses=[r["status"] for r in x],
                verified=sum(r["verified"] for r in x),
                PAR2_s=sum(r["PAR2_verified_s"] for r in x),
                wall_s=[r["wall_e2e_s"] for r in x],
                conflicts=[r["conflicts"] for r in x],
                guard_lemmas=[r["guard2_lemmas"] for r in x],
                triggered=[r["guard3_trigger"] for r in x],
                budget_hit=[r["guard2_budget_hit"] for r in x])
        for rep in range(REPEATS):
            a=next(r for r in group if r["rep"]==rep and r["arm"]=="BASE")
            b=next(r for r in group if r["rep"]==rep and r["arm"]=="GUARD3")
            if a["verified"] and b["verified"]:
                if a["status"]!=b["status"]:
                    raise RuntimeError(("CONTRADICTORY_VERIFIED_VERDICT",case["name"],rep))
                speedups.append(a["wall_e2e_s"]/b["wall_e2e_s"])
        per_graph.append(entry)
    report=dict(graphs=len(cases),runs=len(rows),repetitions=REPEATS,
        one_logical_cpu=True,one_process_at_a_time=True,
        original_public_graphs=True,synthetic=False,
        verified_both_pairs=len(speedups),
        median_verified_speedup=statistics.median(speedups) if speedups else None,
        aggregate=aggregate,per_graph=per_graph,
        admission="experimental_only_no_promotion",
        cap_s=CAP)
    (OUT/"report.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print("DIMACS_REAL_FINAL "+json.dumps({
        k:v for k,v in report.items() if k!="per_graph"},sort_keys=True),flush=True)
    for g in per_graph:
        print("DIMACS_REAL_GRAPH "+json.dumps(g,sort_keys=True),flush=True)

if __name__=="__main__":main()
