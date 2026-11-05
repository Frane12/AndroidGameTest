#!/usr/bin/env python3
"""R149 source-verified, bounded online GF2, selective screening, and CMS paired audit.

- SATLIB 6 reused development cases (not blind).
- Exactly 24 fixed SHA-sorted original CNFs, 6/category from existing R135
  400-CNF corpus (already exposed; not prospective blind).
- 2 repetitions, 6 randomized mode orders, 10s limit per attempt.
- Every preparation/screen cost charged to the corresponding mode. No claim
  of independent UNSAT correctness proofs or official SAT ranking.
"""
import argparse
import csv
import gzip
import hashlib
import json
import os
from pathlib import Path
import random
import re
import statistics
import subprocess
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parent))
import r133c_native_gf2_benchmark as prior
import r127_early_xor_benchmark as satproof

PROTO="DRNAS-R149-BOUNDED-ONLINE-GF2-AND-SCREEN-CMS-DEVELOPMENT-20261105-v1"
CAP=10.0
REPS=2
MODES=("clean","cryptominisat","clause","direct","lazy","screen")
CATEGORIES=("official","external_application","external_xor","external_nonxor")
PER_CATEGORY=6
FIELDS=("source_rows","upfront_rows","online_rows","pair_checks",
        "online_time_s","online_cap_hit","original_clauses",
        "assignments","backtracks","watch_lookups","rows_scanned",
        "clauses_emitted","direct_proposals","direct_reason_requests",
        "direct_reason_lits","sat_witness_checked","disabled")

def check(ok,reason):
    if not ok:raise RuntimeError("R149_FAIL_CLOSED "+reason)

def digest_bytes(value):return hashlib.sha256(value).hexdigest()
def digest(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as inp:
        for chunk in iter(lambda:inp.read(1<<20),b""):
            h.update(chunk)
    return h.hexdigest()

def screen_xor_prefix(path):
    """Bounded, never-changing, non-learning parity signature trigger.

    Reads at most 65,536 raw bytes or 2ms. Only a 3-literal clause with
    a complete parity sign quartet can enable the expensive exporter.
    Failure or ambiguous prefix conservatively chooses clean CaDiCaL.
    """
    t=time.perf_counter()
    budget_bytes=65536
    budget_seconds=0.002
    sig={}
    read_bytes=0
    hit=False
    scanned=0
    with Path(path).open("rb") as stream:
        for raw in stream:
            read_bytes+=len(raw)
            if read_bytes>budget_bytes or time.perf_counter()-t>=budget_seconds: break
            items=raw.strip().split()
            if not items or items[0] in (b"c",b"p",b"%"):continue
            if len(items)!=4 or items[-1]!=b"0":continue
            try: lits=[int(x) for x in items[:3]]
            except ValueError:continue
            key=tuple(sorted(abs(x) for x in lits))
            if key[0]==0 or len(set(key))!=3:continue
            bits=0
            for i,var in enumerate(key):
                if -var in lits:bits|=1<<i
            mask=sig.get(key,0)|(1<<bits)
            sig[key]=mask
            scanned+=1
            if (mask&0x69)==0x69 or (mask&0x96)==0x96:
                hit=True
                break
    cost=time.perf_counter()-t
    return dict(trigger=hit,scan_s=round(cost,6),clauses=scanned,bytes=min(read_bytes,budget_bytes),signatures=len(sig))

def make_cert(source,out):
    # The R93 exporter independently reconstructs every parity consequence.
    t=time.perf_counter()
    label=digest(source)[:16]
    rows=out/(label+".tsv")
    evidence=out/(label+".json")
    p=subprocess.run([sys.executable,"research/r93_export_verified_rows.py","export",
         "--cnf",str(source),"--rows",str(rows),"--evidence",str(evidence)],
         capture_output=True,text=True,timeout=65)
    check(p.returncode==0,"R93 exporter "+str(source)+" "+p.stderr[-800:])
    cost=time.perf_counter()-t
    obj=json.loads(evidence.read_text())
    check(obj.get("protocol")=="R93-LIVE-XOR-PROOF-CERTS-v1","cert protocol")
    check(obj.get("source_sha256")==digest(source),"cert input SHA drift")
    check(isinstance(obj.get("exported"),int),"cert count missing")
    return rows,obj,round(cost,6)

def compatible_original(raw):
    """Precommitted parsing/size scope, never based on SAT outcomes or timings."""
    if len(raw)>8_000_000:return False,"bytes"
    header=None
    literals=0
    for line in raw.splitlines():
        s=line.strip()
        if not s or s.startswith(b"c"):continue
        if s.startswith(b"%"):break
        if s.startswith(b"p "):
            items=s.split()
            if header is not None or len(items)!=4 or items[1]!=b"cnf":
                return False,"header"
            try:n,m=map(int,items[2:])
            except ValueError:return False,"header"
            if n<1 or n>150000 or m<0 or m>160000:
                return False,"n_or_m_cap"
            header=(n,m)
            continue
        if header is None:return False,"missing_header"
        for token in s.split():
            if token!=b"0":
                literals+=1
                if literals>950000:return False,"literal_cap"
    return (header is not None),"valid" if header is not None else "missing_header"

def choose_real(manifest_root,out):
    manifest=manifest_root/"manifest-400.json"
    check(manifest.is_file(),"missing R135 manifest-400.json")
    obj=json.loads(manifest.read_text())
    check(obj.get("protocol")=="DRNAS-400-PROSPECTIVE-20261105-v1" and
          obj.get("status")=="COMPLETE","unexpected R135 400 corpus")
    rows=obj.get("formulas") or []
    check(len(rows)==400,"expected frozen 400")
    check(len({c["sha256"] for c in rows})==400,"duplicate CNF SHA")
    dest=out/"original-cnf"
    dest.mkdir(parents=True,exist_ok=True)
    chosen,excluded=[],[]
    for category in CATEGORIES:
        matching=sorted((c for c in rows if c.get("category")==category),
                        key=lambda x:x["sha256"])
        check(len(matching)>=PER_CATEGORY,"missing category "+category)
        counter=0
        for c in matching:
            cp=Path(c["compressed_file"])
            check(not cp.is_absolute() and ".." not in cp.parts,"unsafe source path")
            source=cp if cp.is_file() else manifest_root/cp
            check(source.is_file(),"compressed source missing "+str(source))
            with gzip.open(source,"rb") as stream:raw=stream.read(8_000_001)
            check(digest_bytes(raw)==c["sha256"] or len(raw)>8_000_000,
                  "original CNF SHA mismatch")
            ok,reason=compatible_original(raw)
            if not ok:
                excluded.append(dict(sha256=c["sha256"],category=category,
                                     reason="PRECOMMITTED_PARSER_CAP_"+reason))
                continue
            check(digest_bytes(raw)==c["sha256"],"compatible original SHA mismatch")
            target=dest/(c["sha256"]+".cnf")
            target.write_bytes(raw)
            chosen.append(dict(path=target,sha256=c["sha256"],category=category,
                               source_manifest_sha256=digest(manifest),
                               bytes=len(raw)))
            counter+=1
            if counter==PER_CATEGORY:break
        check(counter==PER_CATEGORY,"not enough source-parser-compatible "+category)
    (out/"selection_exclusions.json").write_text(
        json.dumps(excluded,indent=2,sort_keys=True)+"\n")
    return chosen

def controls(args):
    if args.dataset=="satlib":
        sources=prior.select_controls(args.satlib)
        check(len(sources)==6,"expected six SATLIB parity sources")
        return [dict(path=p,sha256=digest(p),category="reused_satlib_parity",
                     source_manifest_sha256=digest(args.satlib/"parity.tar.gz"),
                     bytes=p.stat().st_size) for p in sources]
    return choose_real(args.holdout,args.out)

def make_cms_compatible(source,out):
    """Write a validated, logically identical DIMACS file for strict CMS.

    Unlike CaDiCaL, Ubuntu CryptoMiniSat 5.11 cannot parse some SATLIB
    multiline/nonstandard DIMACS. Charge the copy+verification to CMS.
    """
    t=time.perf_counter()
    import r93_export_verified_rows as exporter
    n,clauses=exporter.r88.read_cnf(source)
    target=out/(digest(source)[:16]+".cms.cnf")
    with target.open("w",encoding="ascii") as f:
        f.write("p cnf %d %d\n"%(n,len(clauses)))
        for c in clauses:f.write(" ".join(map(str,c))+" 0\n")
    n2,clauses2=exporter.r88.read_cnf(target)
    check(n2==n and clauses2==clauses,"CMS normalized CNF changed clauses")
    return target,round(time.perf_counter()-t,6)

def parse_native(out,mode):
    line=next((x for x in out.splitlines() if x.startswith("R149_RESULT ")),None)
    check(line is not None,"native mode missing output "+mode)
    fields=dict(re.findall(r"(\w+)=([^\s]+)",line))
    check(fields.get("mode")==mode,"native route mismatch")
    check(fields.get("disabled")=="0","native propagator fail closed")
    return fields

def execute(source,mode,binary,cms,cert,prep,screen,cms_source,cms_prep):
    trigger=screen["trigger"]
    routed=mode
    scan_s=screen["scan_s"] if mode=="screen" else 0.0
    if mode=="screen":routed="lazy" if trigger else "clean"
    certify=prep if routed not in ("clean","cryptominisat") else 0.0
    if routed=="cryptominisat":certify=cms_prep
    upfront=scan_s+certify
    if routed=="cryptominisat":cmd=[str(cms),"--verb","0",str(cms_source.resolve())]
    else:cmd=[str(binary.resolve()),routed,str(source.resolve()),str(cert.resolve())]
    if upfront>=CAP:
        return dict(status="TIMEOUT",par2_s=2*CAP,total_s=CAP,
                    timed_s=0.0,preprocess_s=round(certify,6),screen_s=scan_s,
                    screen_trigger=trigger,actual_mode=routed,
                    **{k:0 for k in FIELDS})
    st=time.perf_counter()
    try:
        p=subprocess.run(cmd,capture_output=True,text=True,timeout=CAP-upfront)
        seconds=time.perf_counter()-st
    except subprocess.TimeoutExpired:
        return dict(status="TIMEOUT",par2_s=2*CAP,total_s=CAP,
                    timed_s=round(CAP-upfront,6),preprocess_s=round(certify,6),
                    screen_s=scan_s,screen_trigger=trigger,actual_mode=routed,
                    **{k:0 for k in FIELDS})
    check(p.returncode in (10,20),"solver error "+routed+" "+str(p.returncode)+
          " "+p.stderr[-900:]+" "+p.stdout[-300:])
    result="SAT" if p.returncode==10 else "UNSAT"
    if routed=="cryptominisat":
        check(("s SATISFIABLE" if result=="SAT" else "s UNSATISFIABLE") in p.stdout,
              "CMS status text does not match exit status")
        if result=="SAT":satproof.check_original_sat(p.stdout.encode(),source)
        telemetry={k:0 for k in FIELDS}
        telemetry["sat_witness_checked"]=int(result=="SAT")
    else:
        n=parse_native(p.stdout,routed)
        check(n.get("status")==result,"telemetry solution mismatch")
        if result=="SAT":check(n["sat_witness_checked"]=="1","native original SAT witness missing")
        telemetry={k:(float(n[k]) if k=="online_time_s" else int(n[k])) for k in FIELDS}
        if routed in ("clean","clause","direct"):
            check(telemetry["online_rows"]==0,"non-lazy mode added online rows")
        if routed=="lazy":
            check(telemetry["upfront_rows"]==0,"lazy should not precompute full closure")
    total=seconds+upfront
    if total>=CAP:result="TIMEOUT"
    return dict(status=result,par2_s=2*CAP if result=="TIMEOUT" else round(total,6),
                total_s=round(min(CAP,total),6),timed_s=round(seconds,6),
                preprocess_s=round(certify,6),screen_s=scan_s,
                screen_trigger=trigger,actual_mode=routed,**telemetry)

def audit(records,args,names):
    mode_sums={}
    for mode in MODES:
        rows=[r for r in records if r["mode"]==mode]
        mode_sums[mode]=dict(n=len(rows),par2_s=round(sum(r["par2_s"] for r in rows),6),
            solved=sum(r["status"]!="TIMEOUT" for r in rows),
            timeout=sum(r["status"]=="TIMEOUT" for r in rows),
            prep_s=round(sum(r["preprocess_s"] for r in rows),6),
            screen_s=round(sum(r["screen_s"] for r in rows),6),
            online_rows=sum(r["online_rows"] for r in rows),
            direct_proposals=sum(r["direct_proposals"] for r in rows),
            pair_checks=sum(r["pair_checks"] for r in rows))
    base=mode_sums["clean"]["par2_s"]
    report=dict(protocol=PROTO,dataset=args.dataset,
        scope="REUSED SATLIB DEVELOPMENT" if args.dataset=="satlib" else
        "REUSED R135 400 FORMULAS, fixed SHA selection; NOT BLIND",
        formulas=len(names),repetitions=REPS,measurements=len(records),
        modes=mode_sums,cap_s=CAP,
        screening=dict(max_bytes=65536,max_time_s=0.002,complete_triple_pattern_only=True),
        original_source_sha_verified=True,original_cnf_unchanged=True,
        source_certified_xor=True,sat_witness_checked=True,
        independent_unsat_proof=False,no_official_ranking=True,
        same_pinned_CaDiCaL=True,cryptoMiniSat_ubuntu_noble_version="5.11.15",
        inprocess_conflict_counters_not_available=True,
        direct_vs_clean_pct=round(100*(base-mode_sums["direct"]["par2_s"])/base,5),
        lazy_vs_clean_pct=round(100*(base-mode_sums["lazy"]["par2_s"])/base,5),
        screen_vs_clean_pct=round(100*(base-mode_sums["screen"]["par2_s"])/base,5),
        verdict="DEVELOPMENT_ONLY_NO_PROMOTION")
    args.out.mkdir(parents=True,exist_ok=True)
    (args.out/"report.json").write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
    with (args.out/"paired.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(records[0]))
        w.writeheader();w.writerows(records)
    print("R149_FINAL_AUDIT",json.dumps(report,sort_keys=True),flush=True)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--dataset",choices=("satlib","real"),required=True)
    ap.add_argument("--binary",type=Path,required=True)
    ap.add_argument("--cms",type=str,default="/usr/bin/cryptominisat5")
    ap.add_argument("--satlib",type=Path)
    ap.add_argument("--holdout",type=Path)
    ap.add_argument("--shard",type=int,default=0)
    ap.add_argument("--shards",type=int,default=1)
    ap.add_argument("--out",type=Path,required=True)
    args=ap.parse_args()
    args.out.mkdir(parents=True,exist_ok=True)
    args.binary=args.binary.resolve()
    check(args.binary.is_file(),"missing R149 native")
    check(Path(args.cms).is_file(),"CryptoMiniSat package binary missing")
    if hasattr(os,"sched_getaffinity"):
        cores=os.sched_getaffinity(0)
        os.sched_setaffinity(0,{min(cores)})
    selected=controls(args)
    check(0<=args.shard<args.shards,"invalid shard")
    # Fixed index-based split: no outcome-dependent benchmark selection.
    selected=[s for i,s in enumerate(selected) if i%args.shards==args.shard]
    check(bool(selected),"no shard formulas")
    records=[]
    ledger=[]
    for c in selected:
        source=c["path"]
        check(digest(source)==c["sha256"],"original SHA mismatch")
        screened=screen_xor_prefix(source)
        cert,ev,prep=make_cert(source,args.out)
        cms_source,cms_prep=make_cms_compatible(source,args.out)
        ledger.append({k:v for k,v in c.items() if k!="path"} |
                      dict(name=source.name,screen=screened,
                           certified_rows=ev["exported"],prep_s=prep,
                           cms_compatible_sha256=digest(cms_source),
                           cms_copy_s=cms_prep))
        for repeat in range(REPS):
            order=list(MODES)
            random.Random(PROTO+c["sha256"]+str(repeat)).shuffle(order)
            answers=set()
            for mode in order:
                res=execute(source,mode,args.binary,args.cms,cert,prep,screened,
                            cms_source,cms_prep)
                rec=dict(source=c["sha256"],category=c["category"],rep=repeat,
                         mode=mode,**res)
                records.append(rec)
                if res["status"]!="TIMEOUT":answers.add(res["status"])
                check(len(answers)<=1,"SAT/UNSAT disagreement on "+c["sha256"])
                print("R149_PAIRED",json.dumps(rec,sort_keys=True),flush=True)
        print("R149_CASE_DONE",source.name,c["category"],ev["exported"],
              screened["trigger"],round(prep,6),flush=True)
    (args.out/"sources.json").write_text(json.dumps(ledger,sort_keys=True,indent=2)+"\n")
    check(len(records)==len(selected)*REPS*len(MODES),"missing trials")
    audit(records,args,selected)

if __name__=="__main__":main()
