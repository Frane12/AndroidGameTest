#!/usr/bin/env python3
"""R63: prospective occurrence of exact XOR CNF blocks on real SATComp2026 sources.

No selected formula is synthetic. Official Main2026 original GBD identifiers
selected by salted SHA rank only; no DRNAS solver performance used to choose.
Excludes previously known R32p/R32r/R52/R55b/R57/R60/R61 SHA/GBD cohorts.

Two separate questions:
  1. How common are *provably encoded complete XOR constraints* in a
     predeclared, size-censored set of real SAT Competition 2026 Main CNFs?
     Also count parity-shaped INCOMPLETE groups, which are not proved XOR.
  2. Is the *existing* sound R28 front-end, with unchanged pinned Kissat
     fallback, actually faster end-to-end than clean pinned Kissat on the
     same original CNFs? Include all native parsing, GF2, fallback, and
     SAT original-model verification within a strict 40-second wall cap.

The C++ R28 front-end only examines original CNF <=12 MiB, n<=3000,
clauses<=150000 and exact width 2..6 parity encodings. Other cases
fall back to unchanged Kissat. "Zero exact blocks" outside that gate is
NOT evidence of XOR absence. Report this denominator separately.

This is not a published SAT Competition score, a novel GF(2) algorithm, a
general P=NP result, or evidence that incomplete XOR-shaped blocks can be
used for sound algebraic elimination.
"""
from __future__ import annotations
import argparse, collections, csv, hashlib, io, json, math, os, random
import re, resource, subprocess, time
from pathlib import Path

import r28_exact_gf2_benchmark as r28
import r32p_real_satcomp26_benchmark as r32p
import r32r_more_real_satcomp26_benchmark as r32r
import r52_prospective_2026_toprefs as r52

PROTO="DRNAS-R63-OFFICIAL2026-XOR-PREVALENCE-FALLBACK-20261103-v1"
SALT="R63-PRECOMMIT-RANDOM-MAIN2026-SHA-DISJOINT-PREVALENCE-V1"
PREVIOUS={"r52":11,"r55b":11,"r57":8,"r60":9,"r61":16}
TARGET=32
MIN_READY=24
MAX_ATTEMPTS=125
SHARDS=8
REPS=2
MODES=("clean_kissat","r28_exact_gf2_fallback")
CAP=40.0
RAW_MAX=28*1024*1024
CNF_MAX=48*1024*1024
R28_BYTES_MAX=12*1024*1024
R28_VARS_MAX=3000
R28_CLAUSES_MAX=150000

def ck(v,msg):
    if not v: raise RuntimeError("R63_FAIL_CLOSED "+str(msg))
def sha(v):return r52.digest(v)
def order_hash(s):
    return hashlib.sha256((SALT+":"+s).encode()).hexdigest()

def complete_parity_mask(k,even):
    masks=0
    for bits in range(1<<k):
        if bits.bit_count()%2==(0 if even else 1):
            masks|=1<<bits
    return masks

def inspect_exact_xor(original,n,m):
    """Independent exact parity support scan of the entire small original CNF.

    Exact only if all 2^(k-1) sign assignments of one parity class are
    present for identical variable support. Counts verified blocks,
    proportion of original clauses covered, and suggestive partial blocks.
    No equation is inferred from a partial block. Each clause can span lines.
    """
    start=time.monotonic()
    original=Path(original)
    if original.stat().st_size>R28_BYTES_MAX or n>R28_VARS_MAX or m>R28_CLAUSES_MAX:
        return dict(supported=False,reason="native_r28_input_guard",
            actual_file_bytes=original.stat().st_size,
            complete_blocks=None,complete_parity_groups=None,
            partial_support_groups=None,distinct_width2to6_groups=None,
            covered_clauses=None,coverage_fraction=None,
            pure_exact_xor=None,scan_s=round(time.monotonic()-start,6))
    patterns={}
    locations=[]
    current=[]
    header=False
    observed=0
    def take_clause(c):
        nonlocal observed
        observed+=1
        if not 2<=len(c)<=6:return
        lit=sorted(((abs(x),x<0) for x in c))
        if any(lit[i][0]==lit[i-1][0] for i in range(1,len(lit))):
            return
        support=tuple(x[0] for x in lit)
        mask=sum(1<<i for i,(_,negative) in enumerate(lit) if negative)
        entry=patterns.get(support)
        if entry is None:
            entry=[0,collections.Counter()]
            patterns[support]=entry
        entry[0]|=1<<mask
        entry[1][mask]+=1
        locations.append((support,mask))
    with original.open(encoding="ascii",errors="strict") as file:
        for line in file:
            row=line.strip()
            if not row or row[0] in "c%":continue
            if row.startswith("p "):
                ck(not header,"two headers")
                words=row.split()
                ck(len(words)==4 and words[1]=="cnf","bad DIMACS header")
                ck(int(words[2])==n and int(words[3])==m,"header changed")
                header=True
                continue
            ck(header,"missing header")
            for word in row.split():
                lit=int(word)
                if lit:
                    ck(abs(lit)<=n,"literal out of bounds")
                    current.append(lit)
                else:
                    take_clause(current)
                    current=[]
    ck(header and not current and observed==m,"source CNF lost clauses")
    complete=0
    full_rows=collections.Counter()
    partial=0
    for support,(bits,instances) in patterns.items():
        k=len(support)
        even=complete_parity_mask(k,True)
        odd=complete_parity_mask(k,False)
        flags=(bits&even)==even,(bits&odd)==odd
        recognized=0
        if flags[0]:
            complete+=1
            recognized|=even
        if flags[1]:
            complete+=1
            recognized|=odd
        if not any(flags) and bits.bit_count()>=2:
            partial+=1
        for mask,count in instances.items():
            if recognized & (1<<mask):
                full_rows[support]+=count
    covered=sum(full_rows.values())
    ck(0<=covered<=m,"overcount original XOR coverage")
    return dict(supported=True,reason="scanned_full_original",
        actual_file_bytes=original.stat().st_size,
        complete_blocks=complete,complete_parity_groups=sum(1 for x in full_rows if full_rows[x]),
        partial_support_groups=partial,
        distinct_width2to6_groups=len(patterns),
        covered_clauses=covered,
        coverage_fraction=round(covered/max(1,m),7),
        pure_exact_xor=bool(m and covered==m),
        scan_s=round(time.monotonic()-start,6))

def selftest():
    with __import__("tempfile").TemporaryDirectory() as folder:
        p=Path(folder)/"test.cnf"
        def write(cs):
            p.write_text("p cnf 3 "+str(len(cs))+"\n"+
              "".join(" ".join(map(str,c))+" 0\n" for c in cs))
        # For support (1,2,3), masks 1,2,4,7 are a complete parity block.
        xor=[(-1,2,3),(1,-2,3),(1,2,-3),(-1,-2,-3)]
        write(xor)
        a=inspect_exact_xor(p,3,4)
        ck(a["complete_blocks"]==1 and a["covered_clauses"]==4
            and a["pure_exact_xor"],"complete pure XOR detector broken")
        write(xor[:3])
        a=inspect_exact_xor(p,3,3)
        ck(a["complete_blocks"]==0 and a["partial_support_groups"]==1,
            "partial XOR falsely certified")
        write(xor+[(1,)])
        a=inspect_exact_xor(p,3,5)
        ck(a["complete_blocks"]==1 and a["covered_clauses"]==4
            and not a["pure_exact_xor"],"mixed exact XOR detector broken")
        write([(1,2),(-1,2)])
        a=inspect_exact_xor(p,3,2)
        ck(a["complete_blocks"]==1 and a["pure_exact_xor"],
           "binary parity block detector broken")
    print("R63_PARITY_SCANNER_SELFTEST_PASS",flush=True)

def freeze(a):
    folder=Path(a.out);folder.mkdir(parents=True,exist_ok=True)
    history={}
    seen=set(g for _,g in r32p.PINS)|set(g for _,g in r32r.PINS)
    ck(len(seen)==37,"old pinned sources changed")
    source_sha=set()
    for key,expected in PREVIOUS.items():
        root=Path(getattr(a,key))
        mf=json.loads((root/"manifest.json").read_text())
        ck(len(mf["cases"])==expected,"prior cohort count mismatch "+key)
        history[key]=sha(root/"manifest.json")
        for case in mf["cases"]:
            g=case["gbd"]
            ck(g not in seen,"historical GBD collision "+key)
            seen.add(g)
            digest=case.get("sha256",case.get("source_sha256"))
            ck(digest is not None and digest not in source_sha,
               "historical source SHA collision")
            source_sha.add(digest)
    ck(len(seen)==37+sum(PREVIOUS.values()),"old source registry drift")
    raw_index=r52.fetch_bytes(r52.URI,100000)
    ids=[line.rsplit("/",1)[-1] for line in raw_index.decode().strip().splitlines()]
    ck(len(ids)==400 and len(set(ids))==400,"official Main2026 URI list changed")
    raw_csv=r52.fetch_bytes(r52.SCORES,32*1024*1024)
    ref=[x for x in csv.DictReader(io.StringIO(raw_csv.decode()))
         if x["solverid"]=="biere_cadical3[main]" and x["instanceid"] in set(ids)]
    ck(len(ref)==400,"official CaDiCaL 2026 score sheet changed")
    status={x["instanceid"]:x["status"] for x in ref}
    # Source selection is SHA-ranked uniform over eligible canonical 2026 IDs,
    # not by expected outcome, XOR features, or DRNAS timing.
    candidates=sorted([g for g in ids if g not in seen],key=lambda g:order_hash(g))
    acks=[];ready=[]
    r32p.CNF_LIMIT=CNF_MAX
    for g in candidates[:MAX_ATTEMPTS]:
        if len(ready)>=TARGET:break
        s=status.get(g)
        note=dict(gbd=g,status=s)
        p=folder/(g+".cnf")
        if s not in ("sat-verified","unsat-verified"):
            note["state"]="EXCLUDED_UNVERIFIED_OFFICIAL_STATUS"
            acks.append(note)
            continue
        try:
            packed,redirect=r32p.request_url(
                "https://benchmark-database.de/file/"+g,RAW_MAX,seconds=55)
            plain,compression=r32p.decode(packed)
            ck(len(plain)<=CNF_MAX,"uncompressed source too big")
            n,m=r32p.parse_dimacs_metadata(plain)
            p.write_bytes(plain)
            ident=sha(p)
            ck(ident not in source_sha,"previous SHA reused")
            details=inspect_exact_xor(p,n,m)
            row=dict(gbd=g,sha256=ident,filename=p.name,
                official_status=("SAT" if s=="sat-verified" else "UNSAT"),
                variables=n,clauses=m,bytes=len(plain),compression=compression,
                compressed_bytes=len(packed),redirect=redirect,**details)
            ready.append(row)
            note.update(state="READY",sha256=ident,
               supported=details["supported"],
               complete_blocks=details["complete_blocks"],
               partial_support_groups=details["partial_support_groups"],
               pure_xor=details["pure_exact_xor"],
               scan_s=details["scan_s"],bytes=len(plain))
        except Exception as exc:
            p.unlink(missing_ok=True)
            note.update(state="EXCLUDED_SIZE_FETCH_OR_PARSE",
                reason=(type(exc).__name__+": "+str(exc))[:240])
        acks.append(note)
        print("R63_SOURCE_SCAN",json.dumps(note,sort_keys=True),flush=True)
    ck(MIN_READY<=len(ready)<=TARGET and
       len({x["sha256"] for x in ready})==len(ready),
       "too few distinct official 2026 originals")
    eligible=[x for x in ready if x["supported"]]
    summary=dict(attempted_candidates=len(acks),
       ready_originals=len(ready),native_scannable=len(eligible),
       native_unscannable=len(ready)-len(eligible),
       formulas_with_complete_xor=sum(x["complete_blocks"]>0 for x in eligible),
       formulas_with_partial_pattern=sum(x["partial_support_groups"]>0 for x in eligible),
       formulas_pure_xor=sum(x["pure_exact_xor"] for x in eligible),
       total_complete_blocks=sum(x["complete_blocks"] for x in eligible),
       total_partial_supports=sum(x["partial_support_groups"] for x in eligible),
       total_original_cnf_bytes=sum(x["bytes"] for x in ready))
    manifest=dict(protocol=PROTO,precommitted_source_salt=SALT,
       official_main_uri=r52.URI,score_uri=r52.SCORES,
       official_index_sha=hashlib.sha256(raw_index).hexdigest(),
       official_scores_sha=hashlib.sha256(raw_csv).hexdigest(),
       excludes_previously_seen_gbd=sorted(seen),
       excluded_prior_manifest_sha=history,
       cases=ready,selection_attempts=acks,pre_solver_scan_summary=summary,
       experiment_modes=list(MODES),cap_seconds=CAP,repeats=REPS,
       shards=SHARDS,max_accepted_originals=TARGET,
       precommitted_exclusions=["source compressed >28MiB","original >48MiB",
          "official not SAT-verified/UNSAT-verified"],
       native_r28_support_limits=dict(file_bytes=R28_BYTES_MAX,
          variables=R28_VARS_MAX,clauses=R28_CLAUSES_MAX,widths=[2,3,4,5,6]),
       limitations=[
          "Size-censored sample from official Main2026; not whole 400-problem prevalence",
          "Out-of-native-guard CNFs NOT scanned for XOR; denominator restricted",
          "Complete XOR clause block is mathematical parity encoding",
          "Partial same-support sign masks are NOT proof of a parity equation",
          "Existing R28 can solve pure XOR or XOR-UNSAT; mixed consistent XOR falls back",
          "R28 detection overhead is included in final elapsed timings",
          "Prospective disjoint only from the enumerated prior DRNAS cohorts, not the entire project",
          "A uniform salted GBD order can still correlate with source size selection",
          "UNSAT from fallback is not independently LRAT-certified; verified official status checked",
          "No official competition/hardware/performance claim"])
    (folder/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
    (folder/"source.sha256").write_text("".join(
        x["sha256"]+"  "+x["filename"]+"\n" for x in ready))
    print("R63_PREVALENCE_SOURCE_FREEZE_PASS",
          json.dumps(summary,sort_keys=True),flush=True)

def child():
    resource.setrlimit(resource.RLIMIT_AS,(3*1024**3,3*1024**3))

def one(source,case,kissat,gf2,mode):
    start=time.monotonic()
    command=([str(kissat),str(source)] if mode=="clean_kissat"
        else [str(gf2),str(source),str(kissat)])
    answer="TIMEOUT";route="timeout";proof="none"
    try:
        p=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
            text=True,errors="replace",timeout=CAP,
            preexec_fn=child)
        ck(p.returncode in (10,20),"unexpected child exit code "+str(p.returncode)+
           " "+p.stderr[-180:])
        answer="SAT" if p.returncode==10 else "UNSAT"
        route="plain_original"
        if mode!="clean_kissat":
            marks=re.findall(r"^c R28_ROUTE (\S+)",p.stdout,re.MULTILINE)
            ck(len(marks)==1,"missing or multiple R28 route tags")
            route=marks[0]
            ck(route in ("fallback","certified_pure_xor_sat",
                "certified_xor_contradiction"),"unknown native route")
            if route=="certified_pure_xor_sat":
                ck(case["supported"] and case["pure_exact_xor"],
                    "native solver claimed pure XOR without independent scan")
            if route=="certified_xor_contradiction":
                ck(case["supported"] and case["complete_blocks"]>0,
                    "native UNSAT parity route without independently verified blocks")
                # This route can include an original UNSAT proof. Stream original
                # clauses into the independent verifier only for rare XOR UNSAT.
                n,cs=r28.load_clauses(source)
                ck(r28.check_gf2_unsat_proof(p.stdout,cs),
                   "invalid independently checked XOR parity UNSAT certificate")
                proof="GF2_independently_verified"
        ck(answer==case["official_status"],
          "result contradicts published official source status")
        if answer=="SAT":
            r32p.verify_sat_witness(source,p.stdout)
            proof="SAT_original_model_verified"
        elif proof=="none":proof="UNSAT_native_or_fallback_official_status_only"
    except subprocess.TimeoutExpired:
        answer="TIMEOUT"
        route="timeout"
    elapsed=time.monotonic()-start
    if elapsed>CAP:answer="TIMEOUT";route="censored_after_verification"
    wall=min(CAP,elapsed)
    return dict(answer=answer,wall_s=round(wall,6),
        par2_s=round(wall if answer!="TIMEOUT" else 2*CAP,6),
        native_route=route,proof=proof)

def measure(a):
    root=Path(a.sources)
    manifest=json.loads((root/"manifest.json").read_text())
    ck(manifest["protocol"]==PROTO and 0<=a.shard<SHARDS,"wrong source protocol")
    kb=Path(a.kissat).resolve();gf=Path(a.gf2).resolve()
    ck(kb.is_file() and gf.is_file(),"pinned binaries missing")
    if hasattr(os,"sched_setaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    folder=Path(a.out);folder.mkdir(parents=True,exist_ok=True)
    (folder/"meta.json").write_text(json.dumps(dict(
        protocol=PROTO,shard=a.shard,
        source_manifest_sha=sha(root/"manifest.json"),
        kissat_sha=sha(kb),gf2_sha=sha(gf),
        n_cases=len(manifest["cases"][a.shard::SHARDS])),indent=2)+"\n")
    records=[]
    for case in manifest["cases"][a.shard::SHARDS]:
        source=(root/case["filename"]).resolve()
        ck(sha(source)==case["sha256"],"official original bytes have changed")
        for rep in range(REPS):
            modes=list(MODES)
            random.Random(int(order_hash(case["sha256"]+"/"+str(rep)),16)).shuffle(modes)
            for mode in modes:
                x=one(source,case,kb,gf,mode)
                record=dict(gbd=case["gbd"],source_sha=case["sha256"],
                    rep=rep,mode=mode,**x)
                records.append(record)
                (folder/"rows.json").write_text(json.dumps(records,indent=2)+"\n")
                print("R63_REAL2026_TRIAL",case["gbd"],"rep",rep,mode,
                    x["answer"],x["wall_s"],"PAR2",x["par2_s"],
                    "route",x["native_route"],flush=True)
    ck(len(records)==len(manifest["cases"][a.shard::SHARDS])*REPS*len(MODES),
       "shard incomplete")

def wilson(n,k):
    if not n:return None
    z=1.959963984540054
    p=k/n
    d=1+z*z/n
    center=(p+z*z/(2*n))/d
    half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/d
    return [round(100*max(0,center-half),2),round(100*min(1,center+half),2)]

def audit(a):
    root=Path(a.sources)
    m=json.loads((root/"manifest.json").read_text())
    ck(m["protocol"]==PROTO,"wrong freeze protocol")
    out=[];pins=set()
    for shard in range(SHARDS):
        folder=Path(a.combined)/f"r63-shard-{shard}"/"results"
        meta=json.loads((folder/"meta.json").read_text())
        ck(meta["protocol"]==PROTO and meta["shard"]==shard
            and meta["source_manifest_sha"]==sha(root/"manifest.json"),
            "mixed original CNF manifests")
        pins.add((meta["kissat_sha"],meta["gf2_sha"]))
        rows=json.loads((folder/"rows.json").read_text())
        ck(len(rows)==meta["n_cases"]*REPS*len(MODES),"incomplete matched rows")
        out+=rows
    ck(len(pins)==1 and len(out)==len(m["cases"])*REPS*len(MODES),
       "pinned binary drift or missing original attempts")
    summary={}
    for mode in MODES:
        rs=[x for x in out if x["mode"]==mode]
        summary[mode]=dict(attempts=len(rs),
           solved=sum(x["answer"]!="TIMEOUT" for x in rs),
           par2_s=round(sum(x["par2_s"] for x in rs),6),
           timeouts=sum(x["answer"]=="TIMEOUT" for x in rs),
           routes=dict(collections.Counter(x["native_route"] for x in rs)))
    ref=summary["clean_kissat"]["par2_s"]
    summary["r28_exact_gf2_fallback"]["delta_vs_clean_pct"]=round(
       100*(summary["r28_exact_gf2_fallback"]["par2_s"]/ref-1),4)
    per_case={};regressions=0
    for case in m["cases"]:
        rr=[x for x in out if x["gbd"]==case["gbd"]]
        ck(len(rr)==REPS*len(MODES) and
           all(x["source_sha"]==case["sha256"] for x in rr),"per-case source loss")
        for rep in range(REPS):
            ck({x["mode"] for x in rr if x["rep"]==rep}==set(MODES),
               "paired source/rep comparison missing")
        totals={mode:round(sum(x["par2_s"] for x in rr if x["mode"]==mode),6)
                for mode in MODES}
        regressions+=totals["r28_exact_gf2_fallback"]>totals["clean_kissat"]+0.5
        per_case[case["gbd"]]=dict(scan_supported=case["supported"],
          complete_blocks=case["complete_blocks"],
          partial_support_groups=case["partial_support_groups"],
          pure_xor=case["pure_exact_xor"],times=totals,
          routes=[x["native_route"] for x in rr if x["mode"]==MODES[1]])
    scan=m["pre_solver_scan_summary"]
    n=scan["native_scannable"]
    k=scan["formulas_with_complete_xor"]
    report=dict(protocol=PROTO,source_cases=len(m["cases"]),
       attempts=len(out),scanner=scan,exact_prevalence_on_scannable_pct=
       round(k/max(n,1)*100,4),
       exact_prevalence_scannable_wilson95_pct=wilson(n,k),
       original_formula_size_censoring=True,
       regression_cases_over_half_second=regressions,
       summary=summary,per_case=per_case,rows=out,
       pinned_binary_sha=next(iter(pins)),manifest=m)
    Path(a.json).write_text(json.dumps(report,indent=2)+"\n")
    lines=["# R63 official SAT Competition 2026 exact XOR prevalence and safe fallback",
      f"**{len(m['cases'])} previously unused official originals; {len(out)} matched runtime attempts.**",
      "The original 400 Main2026 GBD ID list was SHA-rank sampled without prior DRNAS performance.",
      "CNF >48MiB or compressed >28MiB excluded; native XOR supports only <=12MiB, <=3000 vars, <=150000 clauses.",
      "The native C++ R28 is PREEXISTING exact parity detection + GF(2), then original Kissat fallback.",
      "All native scanning, Gaussian elimination, fallback and SAT model checking is included in 40s time cap.",
      "", "## Pre-solver structural prevalence on real original CNFs",
      "| Metric | Count |",
      "|---|---:|",
      f'| SHA-frozen sources accepted | {len(m["cases"])} |',
      f'| Full original CNFs within R28 scanner guard | {n} |',
      f'| Outside R28 input guard — not checked for XOR | {scan["native_unscannable"]} |',
      f'| Scannable formulas with >=1 complete mathematical XOR block | {k} / {n} |',
      f'| Scannable formulas with parity-shaped but incomplete groups (NOT proven XOR) | {scan["formulas_with_partial_pattern"]} / {n} |',
      f'| Pure complete XOR formulas | {scan["formulas_pure_xor"]} / {n} |',
      f'| Total independently recognized complete XOR parity blocks | {scan["total_complete_blocks"]} |',
      f'| Exact block prevalence among scannable | {round(k/max(n,1)*100,2)}% |',
      f'| Wilson 95% interval (%) among scannable | {wilson(n,k)} |',
      "", "## End-to-end wall-clock (all work incl. SAT witness)",
      "| Mode | Solved | PAR2 (s) | Timeout |",
      "|---|---:|---:|---:|"]
    for mode in MODES:
        z=summary[mode]
        lines.append(f'| {mode} | {z["solved"]}/{z["attempts"]} | {z["par2_s"]:.3f} | {z["timeouts"]} |')
    lines+=["",f'**PAR2 change versus clean Kissat: {summary["r28_exact_gf2_fallback"]["delta_vs_clean_pct"]:+.2f}%**',
        f"R28 regressions >0.5s per formula (two reps): {regressions}",
        "","## Per original (two attempts per method, PAR2 seconds)",
        "| GBD prefix | Native scanner | Exact blocks | Partial-only supports | Clean Kissat | R28+fallback | Route |",
        "|---|---|---:|---:|---:|---:|---|"]
    for case in m["cases"]:
        row=per_case[case["gbd"]]
        lines.append("| "+case["gbd"][:12]+" | "+("yes" if row["scan_supported"] else "no")+
          " | "+str(row["complete_blocks"] if row["complete_blocks"] is not None else "N/A")+
          " | "+str(row["partial_support_groups"] if row["partial_support_groups"] is not None else "N/A")+
          " | "+f'{row["times"][MODES[0]]:.3f} | {row["times"][MODES[1]]:.3f} | '+
          ", ".join(row["routes"])+" |")
    lines+=["","## Scientific limitations",
      "Proportions refer only to size-eligible source files (and scanner-eligible originals), NOT the full 400 formula population.",
      "Partial parity-shaped patterns cannot legally trigger a GF(2) inference.",
      "Small or absent exact blocks can be common even when formulas contain hidden/non-CNF-encoded XOR relationships.",
      "UNSAT fallback answers are checked against published official statuses but not independently LRAT-proved.",
      "A pure XOR accelerator is a specialized known algorithm, not proof of a general SAT breakthrough."]
    Path(a.md).write_text("\n".join(lines)+"\n")
    print("R63_FINAL_XOR_PREVALENCE_AUDIT_PASS",json.dumps({
      "sources":len(m["cases"]),"native_scannable":n,
      "exact_blocks_sources":k,"partial_pattern_sources":scan["formulas_with_partial_pattern"],
      "pure_xor_sources":scan["formulas_pure_xor"],
      "matched_trials":len(out),"methods":summary,
      "regressions_gt_0_5s":regressions},sort_keys=True),flush=True)

def main():
    p=argparse.ArgumentParser()
    sub=p.add_subparsers(dest="task",required=True)
    sub.add_parser("selftest")
    f=sub.add_parser("freeze")
    for key in (*PREVIOUS,"out"):f.add_argument("--"+key,required=True)
    t=sub.add_parser("measure")
    for key in ("sources","shard","kissat","gf2","out"):
        t.add_argument("--"+key,required=True)
    a=sub.add_parser("audit")
    for key in ("sources","combined","json","md"):
        a.add_argument("--"+key,required=True)
    args=p.parse_args()
    if args.task=="selftest":selftest()
    elif args.task=="freeze":freeze(args)
    elif args.task=="measure":
        args.shard=int(args.shard);measure(args)
    else:audit(args)
if __name__=="__main__":main()
