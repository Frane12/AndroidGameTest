#!/usr/bin/env python3
"""T0-FRONTIER1: pre-registered CNF-only branch score vs X5's real first branch.

Research diagnostic only: same original X5 source, identical flags and CNFs;
one execution keeps the first polarity, one flips only that polarity.
The offline score NEVER alters either solver run and never uses the answer.
All SAT outputs must satisfy original CNF; UNSAT requires original-CNF DRAT.
"""
from __future__ import annotations
import collections
import hashlib
import io
import json
import math
import os
from pathlib import Path
import random
import re
import signal
import subprocess
import tarfile
import tempfile
import time
import urllib.request

HERE=Path("t0_frontier1")
HERE.mkdir(exist_ok=True)
BIN=Path("build/drnas-t0-frontier1").resolve()
DRAT=Path("build/drat-trim").resolve()
CAP=2.0
# Fixed before reading any result. SATLIB is a published, retrospective set,
# NOT independent industrial or blind competition holdout.
SETS=("uf50-218","uuf50-218","uf75-325","uuf75-325",
      "uf100-430","uuf100-430")
PER_SET=6
BASE_URL="https://www.cs.ubc.ca/~hoos/SATLIB/Benchmarks/SAT/RND3SAT/"

def emit(tag,obj):
    print(tag+" "+json.dumps(obj,sort_keys=True,separators=(",",":")),flush=True)

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def parse(raw):
    n=expected=None
    clauses=[];partial=[]
    for line in raw.decode("ascii").splitlines():
        line=line.strip()
        if not line or line.startswith(("c","%")):continue
        if line.startswith("p "):
            words=line.split()
            assert len(words)==4 and words[1]=="cnf" and n is None
            n,expected=int(words[2]),int(words[3])
            continue
        assert n is not None
        for token in line.split():
            if token in ("c","%"):break
            lit=int(token)
            assert abs(lit)<=n
            if lit:partial.append(lit)
            else:
                clauses.append(tuple(partial))
                partial=[]
    assert n is not None and not partial and len(clauses)==expected
    return n,clauses

def canonical(n,clauses):
    return (f"p cnf {n} {len(clauses)}\n"+
            "".join(" ".join(map(str,c))+" 0\n" for c in clauses)).encode()

def download(family):
    url=BASE_URL+family+".tar.gz"
    err=None
    for retry in range(3):
        try:
            with urllib.request.urlopen(url,timeout=45) as resp:
                buf=resp.read(32*1024*1024+1)
            assert len(buf)<32*1024*1024, "archive limit"
            break
        except Exception as exc:
            err=exc
            if retry==2:raise RuntimeError(f"SATLIB fetch failed {family}: {err}")
            time.sleep(1+retry)
    with tarfile.open(fileobj=io.BytesIO(buf),mode="r:gz") as tf:
        items=sorted(
            (m for m in tf.getmembers() if m.isfile() and
             m.name.lower().endswith(".cnf")),
            key=lambda m:sha((family+"|"+Path(m.name).name).encode()))
        assert len(items)>=PER_SET
        result=[]
        for member in items[:PER_SET]:
            raw=tf.extractfile(member).read()
            n,clauses=parse(raw)
            data=canonical(n,clauses)
            name=family+"_"+Path(member.name).name
            path=HERE/(name if name.endswith(".cnf") else name+".cnf")
            path.write_bytes(data)
            result.append({"family":family,"name":name,"path":str(path),
                           "archive_sha256":sha(buf),"member":member.name,
                           "sha256":sha(data),"n":n,"clauses":len(clauses),
                           "label":("UNSAT" if family.startswith("uuf") else "SAT")})
        return result

def bcp(clauses,assumptions):
    values={}
    pending=list(assumptions)
    pending.extend(c[0] for c in clauses if len(c)==1)
    if any(not c for c in clauses):return None
    while pending:
        lit=pending.pop()
        v=abs(lit);sign=lit>0
        if v in values:
            if values[v]!=sign:return None
            continue
        values[v]=sign
        for clause in clauses:
            satisfied=False;unknown=0;single=0
            for x in clause:
                status=values.get(abs(x))
                if status is None:unknown+=1;single=x
                elif status==(x>0):
                    satisfied=True
                    break
            if satisfied:continue
            if unknown==0:return None
            if unknown==1:pending.append(single)
    return values

def residual(n,clauses,values):
    active=[]
    for clause in clauses:
        sat=False;out=[]
        for lit in clause:
            val=values.get(abs(lit))
            if val is None:out.append(abs(lit))
            elif val==(lit>0):sat=True;break
        if not sat:
            assert len(out)>1,("BCP_INCOMPLETE",clause)
            active.append(out)
    unassigned={v for v in range(1,n+1) if v not in values}
    edges=set()
    parent={v:v for v in unassigned}
    def root(v):
        while parent[v]!=v:
            parent[v]=parent[parent[v]]
            v=parent[v]
        return v
    for row in active:
        for i,a in enumerate(row):
            for b in row[i+1:]:
                if a==b:continue
                u,v=sorted((a,b))
                edges.add((u,v))
                ra,rb=root(u),root(v)
                if ra!=rb:parent[ra]=rb
    sizes=collections.Counter(root(v) for v in unassigned)
    return {"free":len(unassigned),"edges":len(edges),"clauses":len(active),
            "binary":sum(len(c)==2 for c in active),
            "max_component":max(sizes.values(),default=0),
            "components":len(sizes),
            "pair_mass":sum(x*x for x in sizes.values())}

def features(n,clauses,first_literal):
    root_assign=bcp(clauses,[])
    if root_assign is None:return {"eligible":False,"reason":"root_conflict"}
    root=residual(n,clauses,root_assign)
    outcomes=[]
    for lit in (first_literal,-first_literal):
        assign=bcp(clauses,[lit])
        if assign is None:
            outcomes.append({"literal":lit,"conflict":True})
            continue
        remainder=residual(n,clauses,assign)
        # Primary pre-registered "frontier reduction" score:
        # 1) fraction of previously free variables fixed after BCP,
        # 2) fraction of primal graph edges removed after BCP.
        # No SAT label, timings, lookahead result or outcome in the score.
        variable_gain=(root["free"]-remainder["free"])/max(1,root["free"])
        edge_gain=(root["edges"]-remainder["edges"])/max(1,root["edges"])
        outcomes.append({"literal":lit,"conflict":False,"after":remainder,
                         "forced":len(assign)-len(root_assign)-1,
                         "variable_gain":variable_gain,"edge_gain":edge_gain,
                         "score":variable_gain+edge_gain})
    if any(x["conflict"] for x in outcomes):
        return {"eligible":False,"reason":"immediate_conflict",
                "root":root,"arms":outcomes}
    delta=outcomes[1]["score"]-outcomes[0]["score"]
    # Ties abstain; pre-fixed threshold, never fitted on this cohort.
    suggestion=1 if delta>0.01 else -1 if delta< -0.01 else 0
    return {"eligible":True,"root":root,"arms":outcomes,
            "score_delta_flip_minus_base":delta,
            "recommendation":suggestion}

def check_sat(stdout,n,clauses):
    assignment={}
    for line in stdout.splitlines():
        if line.startswith("v "):
            for token in line[2:].split():
                lit=int(token)
                if not lit:continue
                assert 1<=abs(lit)<=n
                assert abs(lit) not in assignment or assignment[abs(lit)]==(lit>0)
                assignment[abs(lit)]=(lit>0)
    return all(any(assignment.get(abs(lit))==(lit>0) for lit in c)
               for c in clauses)

def native(source,flip,n,clauses):
    with tempfile.TemporaryDirectory() as td:
        proof=Path(td)/"result.drat"
        cmd=[str(BIN),str(Path(source["path"]).resolve()),
             "--mode","core","--time",str(CAP),"--stats",
             "--x5-no-minimize","--branch-at","1","--proof",str(proof)]
        if flip:cmd.append("--flip-branch")
        t=time.perf_counter()
        p=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                           text=True,start_new_session=True)
        expired=False
        try:out,err=p.communicate(timeout=CAP+0.7)
        except subprocess.TimeoutExpired:
            expired=True
            os.killpg(p.pid,signal.SIGKILL)
            out,err=p.communicate()
        wall=time.perf_counter()-t
        assert expired or p.returncode in (0,10,20),(
            "SOLVER_EXIT",p.returncode,err[-500:])
        status="TIMEOUT" if expired else ("SAT" if p.returncode==10 else
               "UNSAT" if p.returncode==20 else "UNKNOWN")
        verified=False;check_s=0.
        if status=="SAT":
            verified=check_sat(out,n,clauses)
            assert verified,("INVALID_ORIGINAL_MODEL",source["name"],flip)
        if status=="UNSAT":
            assert proof.exists() and proof.stat().st_size>0,(
                "MISSING_UNSAT_PROOF",source["name"])
            t2=time.perf_counter()
            chk=subprocess.run([str(DRAT),source["path"],str(proof)],
                   text=True,capture_output=True,timeout=35)
            verified=chk.returncode==0 and "s VERIFIED" in chk.stdout
            assert verified,("ORIGINAL_DRAT_INVALID",source["name"],flip,
                             chk.stdout[-200:],chk.stderr[-200:])
            check_s=time.perf_counter()-t2
        if verified:
            assert status==source["label"],(
                "SATLIB_SOURCE_LABEL_DISAGREEMENT",source["name"],status)
        telemetry={}
        for line in err.splitlines():
            key,sep,body=line.partition(" ")
            if key in ("X41_STATS","X45_COMPARE"):
                assert key not in telemetry,("DUPLICATE_STATS",key)
                telemetry[key]=json.loads(body)
        if not expired:
            assert "X41_STATS" in telemetry and "X45_COMPARE" in telemetry
        c=telemetry.get("X45_COMPARE",{})
        s=telemetry.get("X41_STATS",{})
        return {"flip":flip,"status":status,"verified":verified,"wall_s":wall,
                "par2_s":wall if verified and wall<=CAP else 2*CAP,
                "check_s":check_s,"decisions":s.get("decisions"),
                "conflicts":s.get("conflicts"),"propagations":s.get("propagations"),
                "reached_first_branch":c.get("reached",False),
                "baseline_literal":c.get("baseline_literal"),
                "actual_literal":c.get("actual_literal"),
                "pre_state_digest":c.get("pre_state_digest")}

def compare(a,b):
    if not a["verified"] and not b["verified"]:return 0
    if a["verified"]!=b["verified"]:return 1 if b["verified"] else -1
    cost=lambda x:4*x["conflicts"]+x["decisions"]
    d=cost(a)-cost(b)
    return 1 if d>1 else -1 if d< -1 else 0

def main():
    cpus=os.sched_getaffinity(0)
    os.sched_setaffinity(0,{min(cpus)})
    assert len(os.sched_getaffinity(0))==1
    if not BIN.is_file() or not DRAT.is_file():
        raise RuntimeError("Required binaries absent")
    all_sources=[]
    for family in SETS:all_sources.extend(download(family))
    assert len(all_sources)==36 and len({x["sha256"] for x in all_sources})==36
    manifest={"status":"FROZEN_BEFORE_SOLVER","source_count":len(all_sources),
              "one_logical_cpu":True,"source_benchmark":"published_SATLIB_random_3SAT",
              "historical_set_not_blind":True,"arms":["baseline_first","flipped_first"],
              "cap_s":CAP,"primary_score":"normalized_BCP_variable_gain_plus_primal_edge_gain",
              "margin":0.01,"no_training_or_tuning":True,"sources":all_sources}
    manifest_path=HERE/"manifest.json"
    manifest_path.write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n")
    emit("T0_FRONTIER_FROZEN",{"sources":len(all_sources),
         "families":list(SETS),"sha256":sha(manifest_path.read_bytes()),
         "one_cpu":True,"no_fitting":True})
    rows=[]
    random.Random(14061114).shuffle(all_sources)
    for source in all_sources:
        raw=Path(source["path"]).read_bytes()
        assert sha(raw)==source["sha256"]
        n,clauses=parse(raw)
        order=[False,True]
        random.Random(int(source["sha256"][:8],16)).shuffle(order)
        runs={}
        for flip in order:runs[flip]=native(source,flip,n,clauses)
        a,b=runs[False],runs[True]
        if a["reached_first_branch"] and b["reached_first_branch"]:
            assert a["pre_state_digest"]==b["pre_state_digest"],(
                "NOT_IDENTICAL_T0_STATE",source["name"])
            assert a["baseline_literal"]==b["baseline_literal"]!=0,(
                "NOT_SAME_FIRST_VARIABLE",source["name"])
            assert a["actual_literal"]==a["baseline_literal"]
            assert b["actual_literal"]==-a["baseline_literal"]
            t=time.perf_counter()
            predictor=features(n,clauses,a["baseline_literal"])
            overhead_ms=(time.perf_counter()-t)*1000
        else:
            predictor={"eligible":False,"reason":"first_branch_not_reached"}
            overhead_ms=0.
        truth=compare(a,b)
        pred=predictor.get("recommendation",0)
        row={"family":source["family"],"name":source["name"],
             "sha256":source["sha256"],"first_literal":a["baseline_literal"],
             "outcome":truth,"predicted":pred,"features":predictor,
             "feature_wall_ms_python":overhead_ms,"baseline":a,"flip":b}
        rows.append(row)
        emit("T0_FRONTIER_PAIR",{k:v for k,v in row.items()
             if k not in ("features","sha256")})
    eligible=[r for r in rows if r["predicted"]]
    informative=[r for r in eligible if r["outcome"]]
    flipped=[r for r in rows if r["predicted"]==1]
    result={
        "status":"COMPLETE","sources":len(rows),"verified_both":sum(
            r["baseline"]["verified"] and r["flip"]["verified"] for r in rows),
        "first_branch_reached_both":sum(r["first_literal"] is not None for r in rows),
        "predictive_non_tie":len(eligible),
        "decisive_prediction_pairs":len(informative),
        "direction_correct":sum(r["predicted"]==r["outcome"] for r in informative),
        "direction_wrong":sum(r["predicted"]!=r["outcome"] for r in informative),
        "predicted_flips":len(flipped),
        "predicted_flip_wins":sum(r["outcome"]==1 for r in flipped),
        "predicted_flip_losses":sum(r["outcome"]==-1 for r in flipped),
        "predicted_flip_neutral":sum(r["outcome"]==0 for r in flipped),
        "family_counts":dict(collections.Counter(r["family"] for r in rows)),
        "one_logical_cpu":True,"same_t0_snapshot_checked":True,
        "only_original_CNF_proof_checked_answers_count":True,
        "not_blind_realworld":True,"no_speedup_claim":True,
        "main_modified":False,"solver_promoted":False,
        "metric_fitted_to_outcomes":False,
        "manifest_sha256":sha(manifest_path.read_bytes())
    }
    (HERE/"rows.jsonl").write_text("".join(json.dumps(r,sort_keys=True)+"\n" for r in rows))
    (HERE/"report.json").write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    emit("T0_FRONTIER_FINAL",result)
if __name__=="__main__":main()
