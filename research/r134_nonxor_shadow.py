#!/usr/bin/env python3
"""DRNAS R134: NON-XOR read-only structural shadow audit of already-seen R132 CNFs.

Hypothesis: binary implication graph (BIG), Horn/dual-Horn ratios and pairwise
negative mutex density are cheaper, more general clause features than
exhaustive XOR/gate rewriting; they could guide later frozen CDCL presets.
Exploratory development only: NEVER tune or promote from this reused R132
holdout. No solver, compilation, CNF mutation or new blind benchmark.
"""
import argparse
import collections
import csv
import hashlib
import json
import pathlib
import statistics
import time

ROOT=pathlib.Path("r134")
SOURCES=pathlib.Path("r132/frozen")
R132=pathlib.Path("r132")
MODES=("kissat","cadical","r118","r130","r132")
PROTO="DRNAS-R134-NONXOR-BIG-HORN-MUTEX-SHADOW-20261105-v1"
SOURCE_PROTO="DRNAS-R132-WIDE-K2-K6-FROZEN-PROSPECTIVE-20261105-v1"
MAX_SCAN_BYTES=8*1024*1024
MAX_SCAN_CLAUSES=120000
MAX_BINARY_EDGES=200000

def need(value,message):
    if not value:raise RuntimeError("R134_SHADOW_AUDIT_REFUSED "+str(message))
def digest(path):
    h=hashlib.sha256()
    with pathlib.Path(path).open("rb") as f:
        for block in iter(lambda:f.read(1024*1024),b""):h.update(block)
    return h.hexdigest()
def rounded(x):
    return round(x,6)
def median(a):
    return rounded(statistics.median(a)) if a else None
def ratio(x,total):
    return rounded(x/total) if total else 0.0

def scan(src):
    start=time.perf_counter()
    size=src.stat().st_size
    counts=collections.Counter()
    outgoing=collections.Counter()
    incoming=collections.Counter()
    header=None
    scanned=0
    clause_length=pos=neg=0
    lits=[]
    truncated=False
    reason="complete"
    seen_header=False
    # Deterministic bounded full-or-prefix original-CNF scan; no source rewrite.
    with src.open("rb") as f:
        for raw in f:
            scanned+=len(raw)
            if scanned>MAX_SCAN_BYTES:
                truncated=True;reason="byte_budget";break
            line=raw.strip()
            if not line:continue
            if line[:1] in (b"c",b"%") and (len(line)==1 or line[1:2] in (b" ",b"\t")):
                continue
            if line.startswith(b"p "):
                fields=line.split()
                need(len(fields)==4 and fields[1]==b"cnf", "bad DIMACS header "+src.name)
                need(not seen_header,"duplicate header")
                header=(int(fields[2]),int(fields[3]))
                seen_header=True
                continue
            need(seen_header,"missing DIMACS header "+src.name)
            for token in line.split():
                val=int(token)
                if val:
                    need(abs(val)<=header[0],"literal over header bound "+src.name)
                    clause_length+=1
                    if val>0:pos+=1
                    else:neg+=1
                    if len(lits)<2:lits.append(val)
                else:
                    counts["clauses"]+=1
                    counts["literals"]+=clause_length
                    if clause_length==0:counts["empty"]+=1
                    if clause_length==1:counts["units"]+=1
                    if clause_length==2:
                        counts["binary"]+=1
                        a,b=lits
                        if a!=b and a!=-b:
                            counts["usable_binary"]+=1
                            if len(outgoing)<MAX_BINARY_EDGES and counts["usable_binary"]*2<=MAX_BINARY_EDGES:
                                outgoing[-a]+=1;incoming[b]+=1
                                outgoing[-b]+=1;incoming[a]+=1
                                counts["edges"]+=2
                            else:counts["edge_budget_skipped"]+=1
                        if a<0 and b<0 and a!=b:
                            counts["pairwise_amo_mutex"]+=1
                        if a>0 and b>0 and a!=b:
                            counts["pairwise_atleast_one"]+=1
                    if clause_length==3:counts["ternary"]+=1
                    if clause_length>=4:counts["long"]+=1
                    if pos<=1:counts["horn"]+=1
                    if neg<=1:counts["dual_horn"]+=1
                    if pos==1 and neg==1:counts["mixed_binary"]+=1
                    clause_length=pos=neg=0
                    lits=[]
                    if counts["clauses"]>=MAX_SCAN_CLAUSES:
                        truncated=True;reason="clause_budget";break
            if truncated:break
    need(header is not None,"header missing "+src.name)
    if not truncated:
        need(clause_length==0,"incomplete DIMACS last clause "+src.name)
        need(counts["clauses"]==header[1],"DIMACS clause-count mismatch "+src.name)
    nodes=set(incoming)|set(outgoing)
    two_step=sum(incoming[u]*outgoing[u] for u in nodes)
    top_out=max(outgoing.values(),default=0)
    n=counts["clauses"]
    result=dict(source_bytes=size,scan_bytes=scanned,coverage_bytes_pct=rounded(100*min(scanned,size)/size) if size else 100,
      fully_scanned=not truncated,scan_budget_reason=reason,
      header_variables=header[0],header_clauses=header[1],
      observed_clauses=n,observed_literals=counts["literals"],
      clauses_binary=counts["binary"],clauses_ternary=counts["ternary"],clauses_long=counts["long"],
      clauses_units=counts["units"],clauses_empty=counts["empty"],
      horn_ratio=ratio(counts["horn"],n),dual_horn_ratio=ratio(counts["dual_horn"],n),
      binary_ratio=ratio(counts["binary"],n),ternary_ratio=ratio(counts["ternary"],n),
      pairwise_mutex_ratio=ratio(counts["pairwise_amo_mutex"],n),
      positive_binary_ratio=ratio(counts["pairwise_atleast_one"],n),
      implication_edges_recorded=counts["edges"],unique_graph_literals=len(nodes),
      max_implication_fanout=top_out,estimated_two_hop_implications=two_step,
      edge_budget_skipped=counts["edge_budget_skipped"],
      probe_wall_s=rounded(time.perf_counter()-start))
    # Prefix-only features may NOT be interpreted as whole-formula properties.
    return result

def run():
    ROOT.mkdir(exist_ok=True)
    mp=SOURCES/"manifest.json"
    meta=json.loads(mp.read_text())
    need(meta.get("protocol")==SOURCE_PROTO,"wrong historical source protocol")
    cases=meta["cases"]
    need(len(cases)==125,"expected all 125 original R132 source cases")
    need(len(set(c["sha256"] for c in cases))==len(cases),"source SHA duplicates")
    source_sha=digest(mp)
    shards=[json.loads((R132/f"shard-{i}.json").read_text()) for i in range(8)]
    need(all(x.get("protocol")==SOURCE_PROTO and x.get("source_manifest_sha256")==source_sha for x in shards),"frozen source mismatch")
    need(len(set(json.dumps(x["binary_sha256"],sort_keys=True) for x in shards))==1,"original solver binary mismatch")
    original_rows=[r for sh in shards for r in sh["rows"]]
    need(len(original_rows)==len(cases)*2*len(MODES),"incomplete original R132 paired runs")
    ci={c["sha256"]:c for c in cases}
    keys={}
    for r in original_rows:
        c=ci.get(r["sha256"])
        need(c and c["id"]==r["id"],"original row identity mismatched")
        need(r["mode"] in MODES and r["repeat"] in (0,1),"unexpected mode or repeat")
        need(r["status"] in ("SAT","UNSAT","TIMEOUT"),"bad solver status")
        need(abs(r["par2"]-(30.0 if r["status"]=="TIMEOUT" else r["seconds"]))<1e-5,"PAR2 mismatch")
        if r["status"]=="SAT":need(r["proof"]=="source_SAT_witness_verified","unchecked SAT witness")
        if r["status"]=="UNSAT":need(r["proof"]=="UNSAT_without_independent_LRAT_proof","invalid UNSAT proof tier")
        key=(r["sha256"],r["repeat"],r["mode"])
        need(key not in keys,"duplicate original measure")
        keys[key]=r
    for c in cases:
        for rep in range(2):
            statuses=set(keys[(c["sha256"],rep,m)]["status"] for m in MODES)-{"TIMEOUT"}
            need(len(statuses)<=1,"SAT/UNSAT disagreement: "+c["id"])

    analyses=[]
    for i,c in enumerate(cases):
        src=SOURCES/c["id"]
        need(src.is_file() and digest(src)==c["sha256"],"original CNF SHA changed "+c["id"])
        obs=scan(src)
        sums={m:sum(keys[(c["sha256"],rep,m)]["par2"] for rep in (0,1)) for m in MODES}
        solved={m:sum(keys[(c["sha256"],rep,m)]["status"]!="TIMEOUT" for rep in (0,1)) for m in MODES}
        analyses.append(dict(id=c["id"],sha256=c["sha256"],cohort=c["cohort"],
            **obs,par2_kissat=rounded(sums["kissat"]),par2_cadical=rounded(sums["cadical"]),
            par2_r118=rounded(sums["r118"]),par2_r130=rounded(sums["r130"]),par2_r132=rounded(sums["r132"]),
            cadical_minus_kissat_par2=rounded(sums["cadical"]-sums["kissat"]),
            r132_minus_kissat_par2=rounded(sums["r132"]-sums["kissat"]),
            solved_kissat=solved["kissat"],solved_cadical=solved["cadical"],solved_r132=solved["r132"]))
        print("R134_SHADOW_SOURCE",i+1,c["id"],c["cohort"],"full="+str(obs["fully_scanned"]),"binary="+str(obs["binary_ratio"]),flush=True)

    def cohort_summary(group):
        if not group:return {}
        return dict(formulas=len(group),fully_scanned=sum(x["fully_scanned"] for x in group),
            total_original_bytes=sum(x["source_bytes"] for x in group),
            total_shadow_probe_wall_s=rounded(sum(x["probe_wall_s"] for x in group)),
            median_shadow_probe_wall_s=median([x["probe_wall_s"] for x in group]),
            median_binary_fraction=median([x["binary_ratio"] for x in group if x["fully_scanned"]]),
            median_horn_fraction=median([x["horn_ratio"] for x in group if x["fully_scanned"]]),
            median_mutex_fraction=median([x["pairwise_mutex_ratio"] for x in group if x["fully_scanned"]]),
            kissat_par2=rounded(sum(x["par2_kissat"] for x in group)),
            cadical_par2=rounded(sum(x["par2_cadical"] for x in group)),
            r132_par2=rounded(sum(x["par2_r132"] for x in group)),
            cadical_faster_formula_count=sum(x["cadical_minus_kissat_par2"]<-.00001 for x in group),
            cadical_slower_formula_count=sum(x["cadical_minus_kissat_par2"]>.00001 for x in group),
            kissat_solved_attempts=sum(x["solved_kissat"] for x in group),
            cadical_solved_attempts=sum(x["solved_cadical"] for x in group))
    full=sorted((x for x in analyses if x["fully_scanned"]),key=lambda x:(x["binary_ratio"],x["sha256"]))
    quartiles={}
    for i in range(4):
        low=(i*len(full))//4;high=((i+1)*len(full))//4
        quartiles[f"Q{i+1}_binary_fraction"] = cohort_summary(full[low:high])
    report=dict(protocol=PROTO,
        analysis_kind="NONBLIND_READ_ONLY_DEVELOPMENT_REUSE_OF_R132",
        previous_source_run=42050320220,previous_audit_only_recovery_run=42058541681,
        source_manifest_sha256=source_sha,full_source_sha_audit=True,
        full_paired_rows_audited=len(original_rows),formulas=len(cases),
        never_compiled=True,never_executed_solver=True,never_modified_original_CNF=True,
        max_shadow_scan_bytes=MAX_SCAN_BYTES,max_shadow_clauses=MAX_SCAN_CLAUSES,
        original_CNF_coverage={'fully_scanned':len(full),'prefix_limited':len(analyses)-len(full),
            'by_limit':dict(collections.Counter(x["scan_budget_reason"] for x in analyses))},
        by_cohort={c:cohort_summary([x for x in analyses if x["cohort"]==c]) for c in sorted(set(x["cohort"] for x in analyses))},
        aggregate=cohort_summary(analyses),fully_scanned_binary_fraction_quartiles=quartiles,
        hypotheses=[
          "binary-implication topology and short implication chains might predict CDCL propagation cost",
          "Horn and dual-Horn composition may separate easy unit-propagation structure from XOR-heavy families",
          "pairwise negative mutex density suggests at-most-one/cardinality encodings, but never proves them",
          "only after independent training, freeze cost-bounded structural selector and test on NEW SHA-disjoint SAT Competition CNFs"],
        caveats=[
          "R132 holdout has already been inspected: all statistical associations are exploratory in-sample only",
          "partial file scans are flagged and never pooled into full-file feature quantiles",
          "no independent UNSAT proof or causal claim; no per-formula cherry-picked promotion",
          "R132 jobs ran on multiple runner models; sub-second comparisons are noisy",
          "R134 shadow cost is measured separately and not a substitute for future end-to-end solver wall time"],
        verdict="NO_PROMOTION_SHADOW_DIAGNOSTIC_ONLY")
    (ROOT/"report.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    with (ROOT/"features_and_old_timings.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(analyses[0].keys()))
        w.writeheader();w.writerows(analyses)
    lines=["# DRNAS R134 — NON-XOR shadow dijagnostika (bez ponavljanja solvera)",
      "",f"- Originalna baza: R132, {len(cases)} SHA-provjerenih formula i {len(original_rows)} postojećih pariranih mjerenja.",
      f"- Potpuno skenirano: {len(full)}/{len(cases)}; ostale formule imaju **označene** ograničene prefikse.",
      f"- Ukupni odvojeni trošak skenera: {report['aggregate']['total_shadow_probe_wall_s']:.3f} s.",
      "- Nije pokrenut nijedan solver, kompajliranje niti ponovno mjerenje; ovo je razvojni (ne slijepi) uzorak.",
      "", "## Po skupinama", "",
      "| Skupina | Formule | Potpuni sken | Kissat PAR-2 | CaDiCaL PAR-2 | CaDiCaL pobjede (formula) |",
      "|---|---:|---:|---:|---:|---:|"]
    for name,z in report["by_cohort"].items():
        lines.append(f"| {name} | {z['formulas']} | {z['fully_scanned']} | {z['kissat_par2']:.3f} | {z['cadical_par2']:.3f} | {z['cadical_faster_formula_count']} |")
    lines.extend(["","## Sljedeći eksperiment","",
      "Preporuka: najprije svesti binarne implikacije, Horn/dual-Horn omjere i mutex gustoću na jeftinu, unaprijed definiranu klasifikaciju. ",
      "Zatim **zamrznuti** hipotezu i provjeriti stvarnu korist na NOVIM SHA-disjoint SAT Competition 2025/2026 formulama, "
      "parirano s Kissatom, CaDiCaL-om i R118, uz ukupni wall, PAR-2, regresije, SAT svjedoke i neovisne UNSAT certifikate.",
      "", "**Status:** bez promjene frozen solvera i bez tvrdnje o napretku brzine.",
      ""])
    (ROOT/"report.md").write_text("\n".join(lines))
    print("R134_NONXOR_FINAL",json.dumps(report,sort_keys=True),flush=True)

if __name__=="__main__":
    ap=argparse.ArgumentParser();ap.add_argument("mode",choices=("analyze",));args=ap.parse_args()
    run()
