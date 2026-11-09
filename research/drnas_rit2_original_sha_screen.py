#!/usr/bin/env python3
"""DRNAS RIT2: bounded, source-SHA-locked GF(2)/SCC intersection screening.

DIAGNOSTIC ONLY. Does not launch SAT/CDCL or emit modified CNF.
All source rows are either exact complete XOR (2/3 literals) or SCC binary implications.
Short consequences are classified as algebraic and separately original-CNF RUP checked.
"""
import argparse
import collections
import csv
import hashlib
import itertools
import json
import pathlib
import signal
import subprocess
import sys
import time

import drnas_crr1_gf2_scc_rup as core

PROTO = "DRNAS-RIT2-X22-FROZEN-24-SHA-GF2-SCC-DIAGNOSTIC-v1"
SOURCE_RUN = 42591977333
SHARDS = 2
TIMEOUT_S = 9
MAX_RELATIONS = 4096
MAX_CANDIDATES = 24
MAX_COMBINATIONS = 12000
MAX_WIDTH = 512

class BudgetExceeded(Exception):
    pass

def sha(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for b in iter(lambda:f.read(1048576),b""):h.update(b)
    return h.hexdigest()

def manifest(path):
    data=json.loads(pathlib.Path(path).read_text())
    cases=data["cases"]
    assert len(cases)==24 and len({c["sha256"] for c in cases})==24
    assert data.get("source_run_id")==42586193407
    for c in cases:
        assert all(k in c for k in ("filename","sha256","gbd","year"))
        assert pathlib.PurePath(c["filename"]).name==c["filename"]
        assert len(c["sha256"])==64
    return cases

def normalize(rows):
    return {(frozenset(vs),int(rhs)) for vs,rhs in rows}

def reduce_row(bits,rhs,basis):
    bits=set(bits)
    while bits:
        p=min(bits)
        if p not in basis:break
        other,b=basis[p];bits.symmetric_difference_update(other);rhs^=b
    return bits,rhs

def basis_from(rows):
    basis={};contradiction=False;truncated=False
    for bits,rhs in sorted(rows,key=lambda z:(len(z[0]),tuple(sorted(z[0])),z[1])):
        bits,rhs=reduce_row(bits,rhs,basis)
        if not bits:
            if rhs:contradiction=True
            continue
        if len(bits)>MAX_WIDTH:
            truncated=True;continue
        basis[min(bits)]=(bits,rhs)
    return basis,contradiction,truncated

def encoded(bits,rhs):
    vs=tuple(sorted(bits))
    if not vs:return ()
    if len(vs)==1:return ((vs[0] if rhs else -vs[0],),)
    if len(vs)==2:
        a,b=vs
        return ((-a,b),(a,-b)) if rhs==0 else ((a,b),(-a,-b))
    return ()

def candidates(basis):
    rows=[(frozenset(vs),rhs) for vs,rhs in basis.values()]
    short=set((v,r) for v,r in rows if len(v)<=2)
    # Limited pair elimination can produce short rows absent from the pivot basis.
    combinations=0
    for i,(v,r) in enumerate(rows):
        if combinations>=MAX_COMBINATIONS:break
        for w,q in rows[i+1:]:
            if combinations>=MAX_COMBINATIONS:break
            if v.isdisjoint(w):continue
            combinations+=1
            mix=v^w
            if len(mix)<=2:short.add((frozenset(mix),r^q))
    return short,combinations,combinations>=MAX_COMBINATIONS

def algebraically_follows(equation,basis,contradictory=False):
    if contradictory:return None
    v,r=reduce_row(equation[0],equation[1],basis)
    return not v and not r

def inspect(source,expected_sha,gbd,year):
    start=time.perf_counter()
    phase="parse"
    def deadline(sig,frame):raise BudgetExceeded()
    signal.signal(signal.SIGALRM,deadline)
    signal.setitimer(signal.ITIMER_REAL,TIMEOUT_S-0.6)
    row=dict(protocol=PROTO,source_sha256=expected_sha,gbd=gbd,year=year,
             stage="INCOMPLETE", SAT_UNSAT="NOT_RUN", PAR2_s=None,
             independent_UNSAT_LRAT=False)
    try:
        assert sha(source)==expected_sha,"original SHA mismatch"
        n,clauses=core.parse(source)
        row.update(variables=n,clauses=len(clauses),
                   binary_clauses=sum(len(c)==2 for c in clauses))
        phase="extract"
        xor=normalize(core.gf2_rows(clauses))
        scc=normalize(core.scc_rows(clauses,n))
        row.update(gf2_rows=len(xor),scc_rows=len(scc),
                   exact_overlap=len(xor&scc),
                   opposite_overlap=sum((v,1-r) in scc for v,r in xor))
        xv=set().union(*(v for v,_ in xor)) if xor else set()
        sv=set().union(*(v for v,_ in scc)) if scc else set()
        row["shared_variables"]=len(xv&sv)
        row["exclusive_gf2_variables"]=len(xv-sv)
        row["exclusive_scc_variables"]=len(sv-xv)
        row["source_relation_count"]=len(xor)+len(scc)
        if len(xor)+len(scc)>MAX_RELATIONS:
            row.update(stage="RELATION_LIMIT",limit=MAX_RELATIONS)
            return row
        phase="linear_bases"
        gb,gcontr,gtr=basis_from(xor)
        sb,scontr,strunc=basis_from(scc)
        jb,jcontr,jtr=basis_from(xor|scc)
        row.update(gf2_rank=len(gb),scc_rank=len(sb),joint_rank=len(jb),
                   gf2_contradictory=gcontr,scc_contradictory=scontr,
                   joint_contradictory=jcontr,
                   algebra_truncated=gtr or strunc or jtr)
        phase="closure"
        relations,pair_checked,pair_cap=candidates(jb)
        row.update(short_relations=len(relations),pair_combinations=pair_checked,
                   pair_truncated=pair_cap)
        # A contradiction or incomplete algebra makes "combined-only" inconclusive.
        reliable=not (gtr or strunc or jtr or gcontr or scontr or jcontr)
        original={tuple(sorted(set(c))) for c in clauses}
        audit=[]
        for v,rhs in sorted(relations,key=lambda x:(len(x[0]),tuple(sorted(x[0])),x[1])):
            if not v or len(v)>2:continue
            if algebraically_follows((v,rhs),jb,jcontr) is not True:continue
            from_g=algebraically_follows((v,rhs),gb,gcontr)
            from_s=algebraically_follows((v,rhs),sb,scontr)
            mixed_only=(from_g is False and from_s is False) if reliable else None
            for clause in encoded(v,rhs):
                if tuple(sorted(clause)) in original:continue
                audit.append((clause,mixed_only))
        audit.sort(key=lambda t:(t[1] is not True,len(t[0]),t[0]))
        row.update(algebraic_candidates=len(audit),
                   algebraic_mixed_only=sum(flag is True for _,flag in audit),
                   algebraic_mixed_only_units=sum(flag is True and len(c)==1 for c,flag in audit),
                   algebraic_mixed_only_binaries=sum(flag is True and len(c)==2 for c,flag in audit))
        phase="RUP"
        checked=0;passed=0;mixed_rup=0;units=0;binaries=0;examples=[]
        for clause,flag in audit[:MAX_CANDIDATES]:
            is_rup=core.rup(clauses,clause)
            checked+=1
            if is_rup:
                passed+=1;units+=len(clause)==1;binaries+=len(clause)==2
                mixed_rup+=flag is True
            if len(examples)<8 and (flag is True or is_rup):
                examples.append(dict(clause=list(clause),mixed_only=flag,rup=is_rup))
        row.update(rup_checked=checked,rup_passed=passed,rup_mixed_only=mixed_rup,
                   rup_units=units,rup_binaries=binaries,examples=examples,
                   rup_candidate_limited=len(audit)>MAX_CANDIDATES)
        row["stage"]="OK"
    except BudgetExceeded:
        row["stage"]="TIME_BUDGET"
        row["stopped_phase"]=phase
    except (AssertionError, ValueError, OSError, RuntimeError) as e:
        row["stage"]="REJECTED"
        row["error"]=str(e)[:180]
    finally:
        signal.setitimer(signal.ITIMER_REAL,0)
        row["analysis_wall_s"]=round(time.perf_counter()-start,5)
        row["source_SHA_verified"]=sha(source)==expected_sha
    return row

def case_action(args):
    row=inspect(pathlib.Path(args.source),args.sha,args.gbd,args.year)
    print("RIT2_CASE "+json.dumps(row,sort_keys=True),flush=True)

def shard_action(args):
    cases=manifest(args.manifest)
    out=pathlib.Path(args.out);out.parent.mkdir(parents=True,exist_ok=True)
    rows=[]
    for i,case in enumerate(cases):
        if i%SHARDS!=args.shard:continue
        p=pathlib.Path(args.cases)/case["filename"]
        assert p.exists() and sha(p)==case["sha256"],"frozen source missing/drift"
        cmd=[sys.executable,__file__,"case","--source",str(p),
             "--sha",case["sha256"],"--gbd",case["gbd"],"--year",str(case["year"])]
        try:
            run=subprocess.run(cmd,capture_output=True,text=True,timeout=TIMEOUT_S+1)
            if run.returncode:raise RuntimeError(run.stderr[-300:])
            matches=[line for line in run.stdout.splitlines() if line.startswith("RIT2_CASE ")]
            assert len(matches)==1,"missing case output"
            item=json.loads(matches[0].split(" ",1)[1])
        except subprocess.TimeoutExpired:
            item=dict(protocol=PROTO,source_sha256=case["sha256"],gbd=case["gbd"],
                      year=case["year"],stage="PROCESS_TIMEOUT",
                      SAT_UNSAT="NOT_RUN",PAR2_s=None,independent_UNSAT_LRAT=False)
        item["shard"]=args.shard
        rows.append(item)
        out.write_text(json.dumps(rows,indent=2)+"\n")
        print("RIT2_TRIAL "+json.dumps(item,sort_keys=True),flush=True)
    assert len(rows)==12
    print("RIT2_SHARD_PASS",args.shard,len(rows),flush=True)

def audit_action(args):
    cases=manifest(args.manifest)
    found=[]
    for shard in range(SHARDS):
        part=json.loads((pathlib.Path(args.results)/f"shard-{shard}.json").read_text())
        assert len(part)==12
        found.extend(part)
    expected={c["sha256"] for c in cases}
    assert len(found)==24 and {r["source_sha256"] for r in found}==expected
    assert len({r["source_sha256"] for r in found})==24
    assert all(r["protocol"]==PROTO and r["SAT_UNSAT"]=="NOT_RUN" and r["PAR2_s"] is None
               and not r["independent_UNSAT_LRAT"] for r in found)
    found.sort(key=lambda r:(-r.get("rup_mixed_only",0),
                             -r.get("algebraic_mixed_only",0),
                             -r.get("shared_variables",0),
                             r["source_sha256"]))
    results=pathlib.Path(args.results);results.mkdir(parents=True,exist_ok=True)
    fields=["source_sha256","gbd","year","stage","variables","clauses",
            "gf2_rows","scc_rows","shared_variables","exact_overlap","opposite_overlap",
            "gf2_rank","scc_rank","joint_rank","algebraic_candidates",
            "algebraic_mixed_only","rup_checked","rup_passed","rup_mixed_only",
            "rup_units","rup_binaries","analysis_wall_s","stopped_phase"]
    with (results/"table.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore")
        w.writeheader();w.writerows(found)
    (results/"table.json").write_text(json.dumps(found,indent=2)+"\n")
    summary=dict(protocol=PROTO,original_sources=24,unique_SHA=24,
                 completed=sum(r["stage"]=="OK" for r in found),
                 incomplete=sum(r["stage"]!="OK" for r in found),
                 with_shared_vars=sum(r.get("shared_variables",0)>0 for r in found),
                 with_mixed_algebraic=sum(r.get("algebraic_mixed_only",0)>0 for r in found),
                 with_mixed_RUP=sum(r.get("rup_mixed_only",0)>0 for r in found),
                 total_gf2_rows=sum(r.get("gf2_rows",0) for r in found),
                 total_scc_rows=sum(r.get("scc_rows",0) for r in found),
                 total_RUP=sum(r.get("rup_passed",0) for r in found),
                 total_mixed_RUP=sum(r.get("rup_mixed_only",0) for r in found),
                 selected_top_SHA=[r["source_sha256"] for r in found
                                   if r["stage"]=="OK" and r.get("rup_mixed_only",0)>0][:6],
                 evaluation="SEEN_X21_X22_REPLAY_NOT_BLIND", SAT_UNSAT="NOT_RUN",PAR2_s=None,
                 independent_UNSAT_LRAT=False)
    (results/"summary.json").write_text(json.dumps(summary,indent=2)+"\n")
    print("RIT2_FINAL "+json.dumps(summary,sort_keys=True),flush=True)

def selftest():
    # The exact four-clause XOR(a,b,c)=0 plus SCC equivalence b=c implies a=0.
    def xor(vs,rhs):
        out=[]
        for flags in itertools.product((False,True),repeat=len(vs)):
            if (sum(flags)&1)==rhs:continue
            out.append(tuple(-v if flags[i] else v for i,v in enumerate(vs)))
        return out
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        src=pathlib.Path(d)/"test.cnf"
        clauses=xor((1,2,3),0)+[(2,-3),(-2,3)]
        src.write_text(f"p cnf 3 {len(clauses)}\n"+
                       "".join(" ".join(map(str,c))+" 0\n" for c in clauses))
        row=inspect(src,sha(src),"selftest",2026)
        assert row["stage"]=="OK",row
        assert row["gf2_rows"]>=1 and row["scc_rows"]>=1,row
        assert row["shared_variables"]>=2,row
        assert row["algebraic_mixed_only_units"]>=1,row
        assert row["SAT_UNSAT"]=="NOT_RUN",row
        print("RIT2_SELFTEST_PASS "+json.dumps(row,sort_keys=True),flush=True)

def main():
    p=argparse.ArgumentParser()
    sub=p.add_subparsers(dest="action",required=True)
    c=sub.add_parser("case")
    for flag in ("source","sha","gbd","year"):c.add_argument("--"+flag,required=True)
    s=sub.add_parser("shard")
    s.add_argument("--manifest",required=True);s.add_argument("--cases",required=True)
    s.add_argument("--shard",type=int,required=True,choices=(0,1))
    s.add_argument("--out",required=True)
    a=sub.add_parser("audit")
    a.add_argument("--manifest",required=True)
    a.add_argument("--results",required=True)
    sub.add_parser("selftest")
    args=p.parse_args()
    dict(case=case_action,shard=shard_action,audit=audit_action,selftest=lambda a:selftest())[args.action](args)
if __name__=="__main__":main()
