#!/usr/bin/env python3
"""R38: bounded passive XOR/CNF scan and retrospective R37 utility audit.

Watchdog limits: CPU/wall time, graph visits, clauses, candidate count and
consecutive candidate scans without a NEW verified implication.
A cutoff is NEVER interpreted as "no structure exists".
No solver modification, no runtime policy trained on evaluation data.
"""
import argparse
import collections
import csv
import hashlib
import json
import os
from pathlib import Path
import resource
import statistics
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE/"research/drnas-sat-v7-8"))
from official_v94_select import download_and_features

CLAUSE_BUDGET=100000
SOURCE_BUDGET=24
VISITS_PER_BFS=1500
GLOBAL_VISIT_BUDGET=16000
STALL_BUDGET=8
DEPTH_BUDGET=40
SOFT_SECONDS=4.0
HARD_SECONDS=8.0
RUN_ID=41632056202
MODES=("ca_plain","orig_v76","orig_v76_plain","v92_sparse","v94_cautious")

def bounded_scan(path):
    start=time.monotonic()
    graph=collections.defaultdict(list)
    groups=collections.defaultdict(set)
    binary={}
    clauses=0
    pending=[]
    nvar=0
    stop="complete"
    def overtime():
        return time.monotonic()-start>SOFT_SECONDS
    with path.open("rb") as fp:
        for line in fp:
            if (clauses&511)==0 and overtime():
                stop="time_budget"; break
            line=line.strip()
            if not line or line.startswith((b"c",b"%")): continue
            if line.startswith(b"p "):
                nvar=int(line.split()[2]); continue
            for tok in line.split():
                x=int(tok)
                if x:
                    pending.append(x); continue
                c=tuple(pending); pending.clear()
                clauses+=1
                if 2<=len(c)<=4 and len(set(map(abs,c)))==len(c):
                    key=tuple(sorted(map(abs,c)))
                    ordered=sorted(c,key=abs)
                    mask=sum((1<<i) for i,v in enumerate(ordered) if v<0)
                    groups[key].add(mask)
                if len(c)==2 and c[0]!=c[1] and c[0]!=-c[1]:
                    a,b=c; binary[clauses]=(a,b)
                    graph[-a].append((b,clauses))
                    graph[-b].append((a,clauses))
                if clauses>=CLAUSE_BUDGET:
                    stop="clause_budget"; break
            if stop!="complete": break
    xor_vars=set()
    for key,masks in groups.items():
        k=len(key)
        for parity in (0,1):
            if all(j in masks for j in range(1<<k) if j.bit_count()%2==parity):
                xor_vars.update(key);break
    degrees=collections.Counter()
    for lit,edges in graph.items():
        if abs(lit) in xor_vars:degrees[abs(lit)]+=len(edges)
    candidates=[v for v,_ in degrees.most_common(SOURCE_BUDGET)]
    units={}
    visited_global=0
    scanned_sources=0
    stagnant=0
    capped_searches=0
    def bfs(source,target):
        nonlocal visited_global,capped_searches
        q=collections.deque([(source,0)])
        prev={source:None}
        capped=False
        while q:
            if visited_global>=GLOBAL_VISIT_BUDGET or overtime():
                return None,"global_budget"
            if len(prev)>=VISITS_PER_BFS:
                capped=True;break
            v,depth=q.popleft()
            visited_global+=1
            if v==target:
                path_edges=[]
                while prev[v] is not None:
                    parent,idx=prev[v]
                    path_edges.append(idx);v=parent
                return list(reversed(path_edges)),"found"
            if depth>=DEPTH_BUDGET: continue
            for next_v,idx in graph.get(v,()):
                if next_v not in prev:
                    prev[next_v]=(v,idx)
                    q.append((next_v,depth+1))
        if capped:capped_searches+=1
        return None,"local_budget" if capped else "not_found"
    for v in candidates:
        if overtime() or visited_global>=GLOBAL_VISIT_BUDGET:
            stop="time_budget" if overtime() else "visit_budget";break
        before=len(units)
        for lit in (v,-v):
            proof,reason=bfs(lit,-lit)
            if reason=="global_budget":
                stop="time_budget" if overtime() else "visit_budget";break
            if proof is None:continue
            current=lit
            for idx in proof:
                a,b=binary[idx]
                if current==-a:current=b
                elif current==-b:current=a
                else:raise RuntimeError("Broken binary certificate")
            if current!=-lit:raise RuntimeError("Wrong implication endpoint")
            units[-lit]=len(proof)
        scanned_sources+=1
        stagnant=stagnant+1 if len(units)==before else 0
        if stop!="complete":break
        if stagnant>=STALL_BUDGET:
            stop="stagnation";break
    if stop=="complete" and len(degrees)>SOURCE_BUDGET:
        stop="source_budget"
    return dict(status="partial" if stop!="complete" else "complete",
        stop_reason=stop, scanned_clauses=clauses, declared_vars=nvar,
        xor_variables=len(xor_vars), binary_implication_edges=2*len(binary),
        eligible_sources=len(degrees), searched_sources=scanned_sources,
        certified_units=len(units), certified_literals=sorted(units),
        total_bfs_visits=visited_global, capped_searches=capped_searches,
        stagnant_sources=stagnant, elapsed_s=round(time.monotonic()-start,6),
        limits=dict(clauses=CLAUSE_BUDGET,sources=SOURCE_BUDGET,
           visits_per_bfs=VISITS_PER_BFS,global_visits=GLOBAL_VISIT_BUDGET,
           stall_sources=STALL_BUDGET,depth=DEPTH_BUDGET,
           soft_wall_s=SOFT_SECONDS,hard_wall_s=HARD_SECONDS),
        mode="passive_no_solver_intervention")

def worker(args):
    resource.setrlimit(resource.RLIMIT_AS,(1024*1024*1024,1024*1024*1024))
    resource.setrlimit(resource.RLIMIT_CPU,(6,7))
    result=bounded_scan(Path(args.input))
    Path(args.output).write_text(json.dumps(result,sort_keys=True)+"\n")

def verify_manifest(path):
    obj=json.loads(Path(path).read_text())
    assert len(obj["cases"])==12 and len({x["id"] for x in obj["cases"]})==12
    assert not(set(x["id"] for x in obj["cases"])&set(obj["original_18_excluded"]))
    return obj

def scan_shard(args):
    manifest=verify_manifest(args.manifest)
    assert 0<=args.shard<4
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    rows=[]
    for c in manifest["cases"][args.shard*3:args.shard*3+3]:
        dest=out/(c["id"]+".cnf")
        resultfile=out/(c["id"]+".worker.json")
        row=dict(case_id=c["id"],sha256=c["sha256"],label=c["official_label"])
        try:
            meta=download_and_features(c["id"],dest)
            if meta["sha256"]!=c["sha256"] or meta["features"]!=c["features"]:
                raise ValueError("CNF sha/features mismatch")
            p=subprocess.run([sys.executable,__file__,"worker",
               "--input",str(dest),"--output",str(resultfile)],
               capture_output=True,text=True,timeout=HARD_SECONDS)
            if p.returncode==0 and resultfile.exists():
                row.update(json.loads(resultfile.read_text()))
            else:
                row.update(status="watchdog_kill",stop_reason="worker_exit_"+str(p.returncode),
                    worker_stderr=p.stderr[-300:])
        except subprocess.TimeoutExpired:
            row.update(status="watchdog_kill",stop_reason="hard_wall_timeout")
        except Exception as exc:
            row.update(status="input_error",stop_reason=str(exc)[:200])
        finally:
            dest.unlink(missing_ok=True)
            resultfile.unlink(missing_ok=True)
        rows.append(row)
        print("R38_WATCHDOG",json.dumps(row,sort_keys=True),flush=True)
    assert len(rows)==3
    (out/"scan.json").write_text(json.dumps(dict(
      protocol="R38_WATCHDOG_V1",r37_run=RUN_ID,
      manifest_sha256=hashlib.sha256(Path(args.manifest).read_bytes()).hexdigest(),
      rows=rows),indent=2)+"\n")
    print("R38_SHARD_PASS",args.shard,len(rows),flush=True)

def audit(args):
    m=verify_manifest(args.manifest)
    old=json.loads(Path(args.report).read_text())
    assert old["count"]==12 and old["all_raw_trials"]==120
    assert old["repeat"]==2 and old["cap_s"]==15 and not old["errors"]
    digest=hashlib.sha256(Path(args.manifest).read_bytes()).hexdigest()
    scanned=[]
    for shard in range(4):
        f=Path(args.scans)/("r38-shard-"+str(shard))/"scan.json"
        doc=json.loads(f.read_text())
        assert doc["r37_run"]==RUN_ID and doc["manifest_sha256"]==digest
        assert doc["protocol"]=="R38_WATCHDOG_V1" and len(doc["rows"])==3
        scanned.extend(doc["rows"])
    byscan={x["case_id"]:x for x in scanned}
    byold={x["case"]:x for x in old["per_case"]}
    assert len(byscan)==len(byold)==12
    assert set(byscan)==set(byold)=={x["id"] for x in m["cases"]}
    rows=[]
    for c in m["cases"]:
        new=byscan[c["id"]]; prev=byold[c["id"]]
        assert new["sha256"]==prev["sha256"]==c["sha256"]
        cost=prev["cost"]
        assert set(cost)==set(MODES)
        best=min(MODES,key=lambda mode:cost[mode])
        rows.append(dict(id=c["id"][:12],label=c["official_label"],
          xor_vars=new.get("xor_variables","unknown"),
          certified_units=new.get("certified_units","unknown"),
          scan_status=new["status"], stop_reason=new["stop_reason"],
          scan_s=new.get("elapsed_s","unknown"),
          CaDiCaL_s=round(cost["ca_plain"],4),
          V92_s=round(cost["v92_sparse"],4),
          V94_s=round(cost["v94_cautious"],4),
          hindsight_best_mode=best,hindsight_best_s=round(cost[best],4),
          missed_vs_best_s=round(cost["v94_cautious"]-cost[best],4),
          theoretical_net_upper_bound_s=round(
            cost["v94_cautious"]-cost[best]-
            (new.get("elapsed_s") if isinstance(new.get("elapsed_s"),(float,int)) else 8.),4),
          probe_decision=(
            "INSUFFICIENT_EVIDENCE" if new["status"]!="complete" else
            "CERTIFIED_SIGNAL" if new.get("certified_units",0)>0 else
            "XOR_ONLY" if new.get("xor_variables",0)>0 else
            "NO_SIGNAL_IN_BOUNDED_SCAN"))))
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    with (out/"r38_cases.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]))
        w.writeheader();w.writerows(rows)
    finished=[r for r in rows if r["scan_status"]=="complete"]
    partial=[r for r in rows if r["scan_status"]=="partial"]
    killed=[r for r in rows if r["scan_status"]=="watchdog_kill"]
    failed=[r for r in rows if r["scan_status"]=="input_error"]
    summary=dict(protocol="R38_WATCHDOG_V1",r37_run=RUN_ID,
       cases=len(rows),new_solver_runs=0,archived_solver_attempts=120,
       watchdog_complete=len(finished),watchdog_partial=len(partial),
       watchdog_killed=len(killed),input_errors=len(failed),
       stop_reasons=dict(collections.Counter(r["stop_reason"] for r in rows)),
       scanned_xor_positive=sum(isinstance(r["xor_vars"],int) and r["xor_vars"]>0 for r in rows),
       scanned_binary_units=sum(r["certified_units"] for r in rows if isinstance(r["certified_units"],int)),
       missed_hindsight_cases=sum(r["missed_vs_best_s"]>0.05 for r in rows),
       hindsight_scan_covered_by_max_savings=sum(r["theoretical_net_upper_bound_s"]>0 for r in rows),
       scan_would_cost_more_than_oracle_savings=sum(r["theoretical_net_upper_bound_s"]<=0 for r in rows),
       probe_decisions=dict(collections.Counter(r["probe_decision"] for r in rows)),
       original_mean_PAR2_s=old["mean_PAR2_s"],
       caveats=["Passive retrospective audit, NOT a new blind benchmark",
         "Best mode per formula is a hindsight oracle, not a deployable predictor",
         "Incomplete or killed scans cannot be classified as XOR-negative",
         "Oracle-minus-scan overhead is a hindsight upper bound, not an executable predictor",
       "Watchdog limits bound structural scanning, NOT CDCL solver runtime",
         "Any candidate policy must be frozen and separately validated on unseen inputs"])
    (out/"r38_summary.json").write_text(json.dumps(summary,indent=2)+"\n")
    lines=["# DRNAS R38 bounded search / watchdog audit","",
      "Reused SHA-locked R37 official 12-case measurements (120 runs).",
      "**No new solver benchmark:** passive scan with hard kill + stagnation/visit budgets.","",
      "| Metric | Value |","|---|---:|"]
    for k in ("watchdog_complete","watchdog_partial","watchdog_killed","input_errors",
              "scanned_xor_positive","scanned_binary_units","missed_hindsight_cases",
              "hindsight_scan_covered_by_max_savings","scan_would_cost_more_than_oracle_savings"):
        lines.append("| "+k+" | "+str(summary[k])+" |")
    lines.extend(["","## Per case",
      "| ID | XOR vars | units | scan | reason | decision | CaDiCaL s | V9.2 s | V9.4 s | missed vs oracle s | max hypothetical net s |",
      "|---|---:|---:|---|---|---|---:|---:|---:|---:|---:|"])
    for r in rows:
        lines.append("| "+ " | ".join(str(r[k]) for k in ("id","xor_vars","certified_units","scan_status","stop_reason","probe_decision","CaDiCaL_s","V92_s","V94_s","missed_vs_best_s","theoretical_net_upper_bound_s")) +" |")
    lines.extend(["","## Interpretation",
      "A stopped scan means **insufficient evidence**, not absence of an XOR structure.",
      "The oracle columns diagnose possible missed opportunities, NOT achieved acceleration.",
      "The hypothetical net bound is oracle saving minus measured scan time, assuming one scan on the critical path. It is an upper bound, NOT speedup.",
      "Separate fresh official benchmark required before making general speed claims."])
    report="\n".join(lines)+"\n"
    (out/"r38_report.md").write_text(report)
    print(report)
    print("R38_AUDIT_PASS",len(rows),flush=True)

def selftest():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p=Path(d)/"toy.cnf"
        # XOR x!=y encoded by (x or y) and (!x or !y), plus unit x
        p.write_text("p cnf 2 3\n1 2 0\n-1 -2 0\n1 0\n")
        result=bounded_scan(p)
        assert result["xor_variables"]==2,result
        assert result["stop_reason"]=="complete",result
        p.write_text("p cnf 2 3\n1 2 0\n-1 -2 0\n1 -2 0\n")
        result=bounded_scan(p)
        assert result["certified_units"]>=1,result
        # Eight independent XOR pairs yield no binary units; terminate on no progress.
        clauses=[]
        for i in range(1,21,2):
            clauses.extend([f"{i} {i+1} 0",f"-{i} -{i+1} 0"])
        p.write_text("p cnf 20 20\n"+"\n".join(clauses)+"\n")
        result=bounded_scan(p)
        assert result["stop_reason"]=="stagnation" and result["status"]=="partial",result
    print("R38_SELFTEST_PASS")

def main():
    p=argparse.ArgumentParser()
    s=p.add_subparsers(dest="cmd",required=True)
    a=s.add_parser("worker");a.add_argument("--input",required=True);a.add_argument("--output",required=True)
    a=s.add_parser("scan");a.add_argument("--manifest",required=True);a.add_argument("--shard",type=int,required=True);a.add_argument("--out",required=True)
    a=s.add_parser("audit");a.add_argument("--manifest",required=True);a.add_argument("--report",required=True);a.add_argument("--scans",required=True);a.add_argument("--out",required=True)
    s.add_parser("selftest")
    args=p.parse_args()
    {"worker":worker,"scan":scan_shard,"audit":audit,"selftest":lambda _:selftest()}[args.cmd](args)
if __name__=="__main__":main()
