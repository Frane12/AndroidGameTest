#!/usr/bin/env python3
"""DRNAS R85 frozen real previously unbenchmarked SAT Competition 2026 Main CNFs.

PREDECLARED structural stratification (3 complete mixed XOR, 5 controls).
No SAT solver is run, no outcome/timing used to choose a formula. Exclusions:
historical R63 list, R66/R67/R81 cases and attempts, R82 attempts and cases,
plus earlier test IDs already included in R63's exclusions. Disjoint source
sha256 and GBD from all registered history. Source-size/availability and
predeclared structural criteria can bias the sample. It is prospective with
respect to solve-time; it is NOT random representative competition scoring.
"""
from __future__ import annotations
import argparse,csv,hashlib,io,json,shutil,collections
from pathlib import Path
import r52_prospective_2026_toprefs as r52
import r32p_real_satcomp26_benchmark as r32p
import r63_real2026_xor_prevalence_fallback as r63
import r64_mixed_xor_implied as r64
import r83_live_xor_cdcl_wide as old

PROTO="DRNAS-R85-2026-PROSPECTIVE-MIXED-XOR-ABCD-20261104-v1"
SALT="DRNAS-R85-PRECOMMIT-2026-UNSEEN-GBD-SHA-RANK-STRUCTURAL-ABCD-v1"
TARGET_MIXED,TARGET_CONTROL=3,5
MAX_FETCH=130
RAW_MAX=25*1024*1024
PLAIN_MAX=48*1024*1024
REPS,CAP,SHARDS=2,35.0,8
MODES=("clean","A_passive","B_active64","C_spread64","D_wide256")

def ck(x,why):
    if not x:raise RuntimeError("R85_SOURCE_FREEZE_FAIL_CLOSED "+str(why))
def writejson(path,v):Path(path).write_text(json.dumps(v,indent=2,sort_keys=True)+"\n")
def digest(p):return old.sha(p)
def hashorder(s):return hashlib.sha256((SALT+"/"+str(s)).encode()).hexdigest()

def history(manifests):
    previously=set();shas=set();provenance={}
    for name,path in sorted(manifests.items()):
        p=Path(path)
        m=json.loads(p.read_text())
        provenance[name]=dict(protocol=m["protocol"],manifest_sha256=digest(p))
        for k in ("cases","source_selection_attempts","selection_attempts","attempts"):
            for c in m.get(k,[]):
                if c.get("gbd"):previously.add(c["gbd"])
                if c.get("sha256"):shas.add(c["sha256"])
        if name=="r63":
            previously.update(m["excludes_previously_seen_gbd"])
    ck(len(previously)>=80,"historical exclusion registry suspiciously small")
    return previously,shas,provenance

def freeze(a):
    src=Path(a.out);src.mkdir(parents=True,exist_ok=True)
    paths={k:getattr(a,k) for k in ("r63","r66","r67","r81","r82")}
    old_ids,old_shas,hist=history(paths)
    index=r52.fetch_bytes(r52.URI,100000)
    ids=[line.rsplit("/",1)[-1] for line in index.decode().strip().splitlines()]
    ck(len(ids)==400 and len(set(ids))==400,"2026 Main URI index changed")
    scores=r52.fetch_bytes(r52.SCORES,32*1024*1024)
    labels={x["instanceid"]:x["status"] for x in csv.DictReader(io.StringIO(scores.decode()))
            if x["solverid"]=="biere_cadical3[main]"}
    ck(len(labels)==400,"2026 official score sheet incomplete")
    candidates=sorted((g for g in ids if g not in old_ids),key=hashorder)
    selected=[];attempts=[];selected_sha=set()
    counts=collections.Counter()
    r32p.CNF_LIMIT=PLAIN_MAX
    for g in candidates[:MAX_FETCH]:
        if counts["mixed_exact"]>=TARGET_MIXED and counts["control"]>=TARGET_CONTROL:break
        row=dict(gbd=g,reference_status=labels.get(g))
        name=g+".cnf"; dest=src/name
        if labels.get(g) not in ("sat-verified","unsat-verified"):
            row["state"]="unverified_excluded";attempts.append(row);continue
        try:
            raw,redirect=r32p.request_url(
              "https://benchmark-database.de/file/"+g,RAW_MAX,seconds=26)
            data,compression=r32p.decode(raw)
            ck(len(data)<=PLAIN_MAX,"oversized DIMACS")
            n,m=r32p.parse_dimacs_metadata(data)
            ck(n>0 and m>0,"empty input")
            dest.write_bytes(data)
            h=digest(dest)
            ck(h not in old_shas and h not in selected_sha,
               "source SHA reused from documented benchmark")
            feature=r63.inspect_exact_xor(dest,n,m)
            group=r64.group(feature)
            # Native original-CNF capture cannot accept larger sources.
            # This is a predeclared structural/size restriction, NOT speed.
            mixed=group=="mixed_exact" and feature["complete_blocks"]>=2 \
                  and n<=4096 and m<=60000
            slot="mixed_exact" if mixed else "control"
            if counts[slot]>= (TARGET_MIXED if mixed else TARGET_CONTROL):
                dest.unlink()
                row.update(state="structural_quota_full",group=group)
                attempts.append(row);continue
            case=dict(gbd=g,year=2026,filename=name,sha256=h,
                official_status="SAT" if labels[g]=="sat-verified" else "UNSAT",
                source_verified_status=True,source_url="https://benchmark-database.de/file/"+g,
                size_bytes=len(data),variables=n,clauses=m,compression=compression,
                compressed_bytes=len(raw),redirect=redirect,
                group=group,stratum=slot,prior_drnas_benchmarked=False,
                **feature)
            selected.append(case);selected_sha.add(h);counts[slot]+=1
            row.update(state="READY",group=group,stratum=slot,sha256=h,vars=n,clauses=m)
        except Exception as e:
            dest.unlink(missing_ok=True)
            row.update(state="fetch_size_or_parse_fail",reason=(type(e).__name__+": "+str(e))[:180])
        attempts.append(row)
        print("R85_SOURCE",json.dumps(row,sort_keys=True),flush=True)
    ck(counts["mixed_exact"]==TARGET_MIXED and counts["control"]==TARGET_CONTROL,
       "did not achieve predeclared 3 mixed XOR + 5 controls, counts="+str(counts))
    ck(len(selected)==8 and len({x["gbd"] for x in selected})==8 and
       len({x["sha256"] for x in selected})==8,"duplicate or missing source")
    mf=dict(protocol=PROTO,sources="original SAT Competition 2026 Main CNF",
       source_index=r52.URI,index_sha256=hashlib.sha256(index).hexdigest(),
       reference_scores_sha256=hashlib.sha256(scores).hexdigest(),
       selection_salt=SALT,prior_manifest_refs=hist,
       excluded_historical_ids=len(old_ids),
       selection_method="SHA-ranked prospective; original source structure only; no solver runtime/solution selection",
       precommitted_quota={"mixed_exact":TARGET_MIXED,"control":TARGET_CONTROL},
       source_selection_attempts=attempts,attempt_limit=MAX_FETCH,
       cases=selected,shards=SHARDS,reps=REPS,cap_s=CAP,modes=MODES,
       limitations=[
          "Excludes all recorded R63/R66/R67/R81/R82 originals and attempted IDs; unknown undocumented external use cannot be ruled out.",
          "Precommitted structural stratification is NOT an unbiased full SAT Competition sample.",
          "The original SAT2026 source and labels are verified; UNSAT lacks independent LRAT proof.",
          "Source availability, size, and native parser structural guards influence sample.",
          "No candidate is ever selected on solve time or observed performance.",
          "Results apply only to this newly frozen 2026 original CNF cohort, on CI hardware."])
    writejson(src/"manifest.json",mf)
    (src/"source.sha256").write_text("".join(x["sha256"]+"  "+x["filename"]+"\n" for x in selected))
    print("R85_NEW_REAL_UNSEEN_FREEZE_PASS",
          json.dumps(dict(sources=8,mixed=counts["mixed_exact"],controls=counts["control"],
              attempts=len(attempts),excluded_historical=len(old_ids),
              years=[2026])),flush=True)

def main():
    p=argparse.ArgumentParser()
    for name in ("r63","r66","r67","r81","r82","out"):
        p.add_argument("--"+name,required=True)
    freeze(p.parse_args())
if __name__=="__main__":main()
