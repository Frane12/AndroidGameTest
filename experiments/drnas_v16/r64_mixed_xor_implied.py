#!/usr/bin/env python3
"""R64: mechanism replay on R63's frozen real SATComp2026 originals.

Test whether adding ONLY algebraically implied unit/binary CNF clauses from
provably complete XOR blocks helps Kissat on MIXED official formulas.
Incomplete parity-looking clause groups are never treated as equations.

The 2026 originals were already benchmarked in R63: this is exploratory
mechanism/replay, NOT source-blind confirmation or official competition scoring.
All preprocessing, subprocess time, and original SAT-model checks are timed.
"""
from __future__ import annotations
import argparse, collections, hashlib, json, os, random, re, subprocess
import tempfile, time
from pathlib import Path

import r63_real2026_xor_prevalence_fallback as r63
import r32p_real_satcomp26_benchmark as r32p

PROTO="DRNAS-R64-MIXED-XOR-LOWWEIGHT-IMPLICATIONS-20261103-v1"
SHARDS=8
REPS=2
CAP=40.0
SCAN_BUDGET=1.5
MAX_DERIVED=512
MODES=("clean_kissat","r28_exact_gf2_fallback","r64_mixed_implied")
GROUPS=("mixed_exact","pure_exact","partial_only","no_exact","unscannable")

def ck(ok,why):
    if not ok: raise RuntimeError("R64_FAIL_CLOSED "+str(why))

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def group(case):
    if not case["supported"]: return "unscannable"
    if case["pure_exact_xor"]: return "pure_exact"
    if case["complete_blocks"]>0: return "mixed_exact"
    if case["partial_support_groups"]>0: return "partial_only"
    return "no_exact"

def freeze(args):
    root=Path(args.sources)
    base=json.loads((root/"manifest.json").read_text())
    ck(base["protocol"]==r63.PROTO and len(base["cases"])==32,
       "R63 frozen source manifest mismatch")
    cases=base["cases"]
    for c in cases:
        ck(digest(root/c["filename"])==c["sha256"],"original CNF SHA drift")
    strat={g:sorted((c for c in cases if group(c)==g),
                     key=lambda c:c["sha256"]) for g in GROUPS}
    # Every complete-XOR mixed source, one pure positive control, every
    # incomplete-only decoy up to 3, 4 no-exact controls and 2 size-guard cases.
    chosen=(strat["mixed_exact"]+strat["pure_exact"][:1]+
            strat["partial_only"][:3]+strat["no_exact"][:4]+
            strat["unscannable"][:2])
    ck(len(chosen)>=12 and len({c["sha256"] for c in chosen})==len(chosen),
       "cohort selection missing or duplicated sources")
    ck(len(strat["mixed_exact"])>=5,"not enough real mixed XOR sources")
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    selected=[dict(c,group=group(c)) for c in chosen]
    spec=dict(protocol=PROTO,source_protocol=r63.PROTO,
         source_manifest_sha=digest(root/"manifest.json"),
         source_run_id=41707669490,
         selection="all exact mixed, pure positive, <=3 partial-only, <=4 no-exact and <=2 unsupported SHA-sorted controls",
         groups={k:len(v) for k,v in strat.items()},
         cases=selected,shards=SHARDS,repeats=REPS,cap_s=CAP,
         scan_budget_s=SCAN_BUDGET,max_derived=MAX_DERIVED,
         modes=list(MODES),
         cautions=["R63 replay, NOT previously unseen source holdout",
                   "Stratified on known structural features, not performance",
                   "Only complete parity sign-mask sets imply XOR equations",
                   "No equation may be inferred from partial parity-shaped CNF",
                   "Only unit and binary consequences of GF2 row reduction are added",
                   "Preserve original CNF clauses; include all elapsed overhead",
                   "Original-model SAT verification; fallback UNSAT not proof certified",
                   "Pure XOR positive control uses the unchanged certified R28 path",
                   "Any speedup requires independent source-disjoint validation"])
    (out/"manifest.json").write_text(json.dumps(spec,indent=2)+"\n")
    print("R64_FROZEN_COHORT",json.dumps(
       {"count":len(selected),"groups":dict(collections.Counter(c["group"] for c in selected)),
        "source_manifest_sha":spec["source_manifest_sha"]},sort_keys=True),flush=True)

def extract_equations(path,n,m,start):
    """Independent exact sign-mask identification, bounded runtime."""
    patterns={}
    short=set()
    clause=[]
    observed=0
    header=False
    def emit(c):
        nonlocal observed
        observed+=1
        if len(c)<=2:
            short.add(tuple(sorted(c)))
        if not 2<=len(c)<=6:return
        pairs=sorted((abs(v),int(v<0)) for v in c)
        if len({v for v,_ in pairs})!=len(pairs):return
        support=tuple(v for v,_ in pairs)
        sign=sum(1<<i for i,(_,neg) in enumerate(pairs) if neg)
        patterns[support]=patterns.get(support,0)|(1<<sign)
    with Path(path).open(encoding="ascii",errors="strict") as f:
        for line in f:
            if line.lstrip().startswith(("c","%")) or not line.strip():continue
            if line.startswith("p "):
                ck(not header and line.split()[:2]==["p","cnf"],"bad DIMACS header")
                data=line.split()
                ck(len(data)==4 and int(data[2])==n and int(data[3])==m,
                   "DIMACS source changed")
                header=True
                continue
            ck(header,"missing header")
            for item in line.split():
                v=int(item)
                if v==0:
                    emit(clause);clause=[]
                    if observed%2048==0 and time.monotonic()-start>SCAN_BUDGET:
                        raise TimeoutError("R64 scan budget exceeded")
                else:
                    ck(abs(v)<=n and abs(v)>0,"bad literal")
                    clause.append(v)
    ck(header and not clause and observed==m,"DIMACS clause mismatch")
    equations=[]
    for support,bits in patterns.items():
        k=len(support)
        even=r63.complete_parity_mask(k,True)
        odd=r63.complete_parity_mask(k,False)
        if bits&even==even: equations.append((support,1))
        if bits&odd==odd: equations.append((support,0))
    return equations,short

def implied_clauses(equations,existing):
    # Row operations over GF(2) preserve logical entailment.
    ck(len(equations)<=20000,"too many complete XOR equations")
    basis={}
    for vs,rhs in equations:
        vector=sum(1<<(v-1) for v in vs)
        while vector:
            p=vector.bit_length()-1
            if p not in basis:
                basis[p]=(vector,rhs);break
            old,bit=basis[p]
            vector^=old;rhs^=bit
        if vector==0 and rhs==1:
            return [],True
    # Reduce to canonical low-weight equations (no unsound partial patterns).
    for p in sorted(basis):
        row,rhs=basis[p]
        for q in sorted(basis):
            if q>p and (basis[q][0]>>p)&1:
                vec,bit=basis[q]
                basis[q]=(vec^row,bit^rhs)
    additions=set()
    for mask,rhs in basis.values():
        variables=[]
        while mask:
            lsb=mask&-mask
            variables.append(lsb.bit_length())
            mask^=lsb
        if len(variables)==1:
            v=variables[0]
            additions.add((v if rhs else -v,))
        elif len(variables)==2:
            a,b=variables
            if rhs:
                additions.add(tuple(sorted((a,b))))
                additions.add(tuple(sorted((-a,-b))))
            else:
                additions.add(tuple(sorted((-a,b))))
                additions.add(tuple(sorted((a,-b))))
    new=sorted(additions-existing)
    return new[:MAX_DERIVED],False

def augment(original,output,n,m,clauses):
    data=Path(original).read_text(encoding="ascii")
    parts=data.splitlines(keepends=True)
    indices=[i for i,line in enumerate(parts) if line.startswith("p ")]
    ck(len(indices)==1,"unexpected header while augmenting")
    p=indices[0]
    ck(parts[p].split()==["p","cnf",str(n),str(m)],
       "DIMACS augmentation header drift")
    parts[p]=f"p cnf {n} {m+len(clauses)}\n"
    with Path(output).open("w",encoding="ascii") as f:
        f.writelines(parts)
        if not data.endswith("\n"):f.write("\n")
        for c in clauses:
            f.write(" ".join(map(str,c))+" 0\n")

def transformed(original,case,kissat,r28):
    t0=time.monotonic()
    if case["pure_exact_xor"]:
        row=r63.one(original,case,kissat,r28,"r28_exact_gf2_fallback")
        row.update(native_route="pure_control_"+row["native_route"],added_clauses=0)
        return row
    target=Path(original)
    route="no_exact"
    added=0
    if (case["supported"] and case["variables"]<=r63.R28_VARS_MAX
        and case["clauses"]<=r63.R28_CLAUSES_MAX
        and case["bytes"]<=r63.R28_BYTES_MAX):
        try:
            equations,existing=extract_equations(
                original,case["variables"],case["clauses"],t0)
        except TimeoutError:
            equations=[];existing=set();route="scan_budget_fallback"
        if equations and route!="scan_budget_fallback":
            clauses,contradiction=implied_clauses(equations,existing)
            if contradiction:
                row=r63.one(original,case,kissat,r28,"r28_exact_gf2_fallback")
                # Include the independent R64 preliminary scan time.
                elapsed=time.monotonic()-t0
                if elapsed>CAP:
                    return dict(answer="TIMEOUT",wall_s=CAP,par2_s=2*CAP,
                         native_route="censored_after_verification",
                         proof="none",added_clauses=0)
                row["wall_s"]=round(elapsed,6)
                row["par2_s"]=round(elapsed if row["answer"]!="TIMEOUT" else 2*CAP,6)
                row["native_route"]="gf2_contradiction_delegate"
                row["added_clauses"]=0
                return row
            if clauses:
                route="mixed_augmented"
                added=len(clauses)
            else:
                route="mixed_no_new_units_or_binaries"
        elif not equations and route!="scan_budget_fallback":
            route="no_complete_xor"
    else:
        clauses=[]
        route="guard_fallback"
    if route not in ("mixed_augmented",):
        clauses=[]
    answer="TIMEOUT";proof="none"
    with tempfile.TemporaryDirectory(prefix="r64-") as temp:
        if clauses:
            target=Path(temp)/"augmented.cnf"
            augment(original,target,case["variables"],case["clauses"],clauses)
        remaining=CAP-(time.monotonic()-t0)
        if remaining>0:
            try:
                proc=subprocess.run([str(kissat),str(target)],stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,text=True,errors="replace",
                    timeout=remaining,preexec_fn=r63.child)
                ck(proc.returncode in (10,20),"Kissat abnormal exit "+str(proc.returncode))
                answer="SAT" if proc.returncode==10 else "UNSAT"
                ck(answer==case["official_status"],"R64 disagrees with official status")
                if answer=="SAT":
                    r32p.verify_sat_witness(original,proc.stdout)
                    proof="SAT_original_model_verified"
                else:
                    proof="UNSAT_Kissat_official_status_only"
            except subprocess.TimeoutExpired:
                answer="TIMEOUT"
    elapsed=time.monotonic()-t0
    if elapsed>CAP:
        answer="TIMEOUT";route="censored_after_verification"
    wall=min(CAP,elapsed)
    return dict(answer=answer,wall_s=round(wall,6),
        par2_s=round(wall if answer!="TIMEOUT" else 2*CAP,6),
        native_route=route,proof=proof,added_clauses=added)

def selftest():
    with tempfile.TemporaryDirectory() as d:
        f=Path(d)/"tiny.cnf"
        def xor(vs,rhs):
            return [tuple(-v if (mask>>i)&1 else v for i,v in enumerate(vs))
                for mask in range(1<<len(vs)) if (mask.bit_count()&1)!=rhs]
        source=xor((1,2,3),0)+xor((1,2,4),0)+[(1,2,3,4)]
        f.write_text("p cnf 4 "+str(len(source))+"\n"+
              "".join(" ".join(map(str,c))+" 0\n" for c in source))
        eq,small=extract_equations(f,4,len(source),time.monotonic())
        ck(len(eq)==2,"complete-XOR scanner missed equations")
        derived,contradiction=implied_clauses(eq,small)
        ck(not contradiction and derived,"failed to derive binary consequence")
        def sat(cs,assignment):
            return all(any((assignment[abs(v)]==(v>0)) for v in c) for c in cs)
        for val in range(16):
            assignment={v:bool(val>>(v-1)&1) for v in range(1,5)}
            ck(sat(source,assignment)==sat(source+derived,assignment),
               "derived consequence not sound")
        fake=xor((1,2,3),0)[:-1]+[(1,2,3,4)]
        f.write_text("p cnf 4 "+str(len(fake))+"\n"+
              "".join(" ".join(map(str,c))+" 0\n" for c in fake))
        eq,small=extract_equations(f,4,len(fake),time.monotonic())
        ck(not eq,"partial XOR incorrectly certified")
        print("R64_SELFTEST_PASS",{"derived":derived},flush=True)

def measure(args):
    root=Path(args.sources)
    spec=json.loads((Path(args.spec)/"manifest.json").read_text())
    ck(spec["protocol"]==PROTO and spec["source_manifest_sha"]==
       digest(root/"manifest.json"),"R64 source/spec mismatch")
    ck(0<=args.shard<SHARDS,"bad shard")
    if hasattr(os,"sched_setaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    kissat=Path(args.kissat).resolve()
    gf2=Path(args.gf2).resolve()
    ck(kissat.is_file() and gf2.is_file(),"missing binaries")
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    meta=dict(protocol=PROTO,shard=args.shard,
        spec_sha=digest(Path(args.spec)/"manifest.json"),
        source_manifest_sha=spec["source_manifest_sha"],
        kissat_sha=digest(kissat),gf2_sha=digest(gf2),
        n_cases=len(spec["cases"][args.shard::SHARDS]))
    (out/"metadata.json").write_text(json.dumps(meta,indent=2)+"\n")
    rows=[]
    for c in spec["cases"][args.shard::SHARDS]:
        source=(root/c["filename"]).resolve()
        ck(digest(source)==c["sha256"],"source SHA mismatch")
        for rep in range(REPS):
            modes=list(MODES)
            random.Random(int(hashlib.sha256(
                f"r64/{c['sha256']}/{rep}".encode()).hexdigest(),16)).shuffle(modes)
            for mode in modes:
                row=(transformed(source,c,kissat,gf2) if mode=="r64_mixed_implied"
                     else r63.one(source,c,kissat,gf2,mode))
                record=dict(gbd=c["gbd"],source_sha=c["sha256"],group=c["group"],
                    rep=rep,mode=mode,**row)
                rows.append(record)
                (out/"rows.json").write_text(json.dumps(rows,indent=2)+"\n")
                print("R64_REAL2026_TRIAL",c["gbd"],c["group"],"rep",rep,
                      mode,row["answer"],row["wall_s"],"PAR2",row["par2_s"],
                      "route",row["native_route"],"added",row.get("added_clauses",0),
                      flush=True)
    print("R64_SHARD_PASS",args.shard,len(rows),flush=True)

def audit(args):
    spec=json.loads((Path(args.spec)/"manifest.json").read_text())
    ck(spec["protocol"]==PROTO,"bad protocol")
    combined=Path(args.combined)
    rows=[];pins=set()
    for shard in range(SHARDS):
        folder=combined/f"r64-shard-{shard}"/"results"
        meta=json.loads((folder/"metadata.json").read_text())
        ck(meta["shard"]==shard and meta["spec_sha"]==
           digest(Path(args.spec)/"manifest.json"),"mixed run provenance")
        pins.add((meta["kissat_sha"],meta["gf2_sha"],meta["source_manifest_sha"]))
        block=json.loads((folder/"rows.json").read_text())
        ck(len(block)==meta["n_cases"]*REPS*len(MODES),"missing rows")
        rows+=block
    ck(len(pins)==1 and len(rows)==len(spec["cases"])*REPS*len(MODES),
       "binary drift or incomplete trials")
    per_case={}
    for c in spec["cases"]:
        xx=[r for r in rows if r["gbd"]==c["gbd"]]
        ck(len(xx)==REPS*len(MODES) and all(r["source_sha"]==c["sha256"]
            and r["group"]==c["group"] for r in xx),"missing paired provenance")
        for rep in range(REPS):
            ck({r["mode"] for r in xx if r["rep"]==rep}==set(MODES),
               "paired mode missing")
        totals={mode:round(sum(r["par2_s"] for r in xx if r["mode"]==mode),6)
                for mode in MODES}
        per_case[c["gbd"]]=dict(group=c["group"],
          complete_blocks=c["complete_blocks"],partial_supports=c["partial_support_groups"],
          par2_by_mode=totals,delta_r64_vs_kissat_s=round(
             totals["r64_mixed_implied"]-totals["clean_kissat"],6),
          r64_routes=dict(collections.Counter(r["native_route"] for r in xx
                      if r["mode"]=="r64_mixed_implied")),
          max_added_clauses=max(r.get("added_clauses",0) for r in xx))
    summaries={}
    for group in ("all",)+GROUPS:
        case_ids={c["gbd"] for c in spec["cases"] if group=="all" or c["group"]==group}
        subset=[r for r in rows if r["gbd"] in case_ids]
        methods={}
        for mode in MODES:
            trial=[r for r in subset if r["mode"]==mode]
            methods[mode]=dict(attempts=len(trial),
                solved=sum(x["answer"]!="TIMEOUT" for x in trial),
                timeouts=sum(x["answer"]=="TIMEOUT" for x in trial),
                par2_s=round(sum(x["par2_s"] for x in trial),6))
        clean=methods["clean_kissat"]["par2_s"]
        methods["r64_vs_kissat_delta_pct"]=round(
            100*(methods["r64_mixed_implied"]["par2_s"]/clean-1),4) if clean else None
        summaries[group]=methods
    regressions=sum(row["delta_r64_vs_kissat_s"]>0.5 for row in per_case.values())
    result=dict(protocol=PROTO,status="PASS",sources=len(spec["cases"]),
        matched_trials=len(rows),binaries=list(pins)[0],
        summary=summaries,regressions_gt_0_5s=regressions,per_case=per_case,
        cautions=spec["cautions"])
    Path(args.json).write_text(json.dumps(result,indent=2)+"\n")
    lines=["# DRNAS R64 — mixed exact XOR GF(2) low-weight implication replay",
      "Mechanism study on R63's existing official 2026 originals — **NOT BLIND**.",
      "Full end-to-end 40s cap, 2 repeats each; PAR2 timeouts=80s.",
      "All original SAT models verified; partial XOR patterns never implied.",
      "",
      "| Stratum | Source count | Kissat PAR2 | R28 PAR2 | R64 PAR2 | R64 delta vs Kissat |",
      "|---|---:|---:|---:|---:|---:|"]
    for g,summary in summaries.items():
        n=sum(c["group"]==g or g=="all" for c in spec["cases"])
        a,b,c=(summary[k]["par2_s"] for k in MODES)
        d=summary["r64_vs_kissat_delta_pct"]
        lines.append(f"| {g} | {n} | {a:.3f}s | {b:.3f}s | {c:.3f}s | {d:+.3f}% |")
    lines+=["",f"Regressions >0.5s per 2-rep source: {regressions}",
       "","## Per original","| GBD prefix | Stratum | Kissat PAR2 | R28 PAR2 | R64 PAR2 | Added | Route |",
       "|---|---|---:|---:|---:|---:|---|"]
    for g,c in per_case.items():
        t=c["par2_by_mode"]
        lines.append(f"| {g[:12]} | {c['group']} | {t['clean_kissat']:.3f} | "+
            f"{t['r28_exact_gf2_fallback']:.3f} | {t['r64_mixed_implied']:.3f} | "+
            f"{c['max_added_clauses']} | {','.join(c['r64_routes'])} |")
    lines+=["","## Limitations"]+["- "+x for x in spec["cautions"]]
    Path(args.md).write_text("\n".join(lines)+"\n")
    print("R64_FINAL_AUDIT_PASS",json.dumps(
        dict(sources=len(spec["cases"]),trials=len(rows),
        mixed_exact=summaries["mixed_exact"],
        total=summaries["all"],regressions_gt_0_5s=regressions),sort_keys=True),
        flush=True)

def main():
    p=argparse.ArgumentParser()
    sub=p.add_subparsers(dest="cmd",required=True)
    sub.add_parser("selftest")
    f=sub.add_parser("freeze")
    for name in ("sources","out"): f.add_argument("--"+name,required=True)
    m=sub.add_parser("measure")
    for name in ("sources","spec","kissat","gf2","out"):
        m.add_argument("--"+name,required=True)
    m.add_argument("--shard",type=int,required=True)
    a=sub.add_parser("audit")
    for name in ("spec","combined","json","md"):
        a.add_argument("--"+name,required=True)
    args=p.parse_args()
    if args.cmd=="selftest":selftest()
    elif args.cmd=="freeze":freeze(args)
    elif args.cmd=="measure":measure(args)
    else:audit(args)

if __name__=="__main__":main()
