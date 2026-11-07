#!/usr/bin/env python3
"""R32c certified root-unit ablation on matched Kissat binaries.

51 PREVIOUS R32b diagnostics + 42 genuinely new SHA-locked SYNTHETIC cases.
Two repeats, four modes (clean, native OFF, native passive, native active).
The active mode may add only 1..12 root units proven from complete XOR CNF
patterns / sound resolvents, subject to original-CNF root BCP; other cases
abstain. Native active is NOT a claim about generic SAT speedup.
"""
from __future__ import annotations
import argparse,collections,hashlib,json,os,random,re,statistics,subprocess,time
from pathlib import Path
import r31_consistent_gf2_test as r31
import r32b_native_shadow_benchmark as b

PROTO="DRNAS-R32C-FROZEN-NATIVE-GF2-ROOT-UNITS-20261103-v1"
REPS=2
SHARDS=4
CAP=4.0
MODES=("clean","native_off","R32B_native_shadow","R32C_active")
FRESH_INDICES=tuple(range(13,19))

def check(ok,msg):
    if not ok: raise RuntimeError("R32C_AUDIT_FAILURE "+str(msg))
def sha(path):
    return b.sha(path)

def freeze(prior,dest):
    previous=Path(prior)
    out=Path(dest);out.mkdir(parents=True,exist_ok=True)
    old=json.loads((previous/"manifest.json").read_text())
    check(old["protocol"]==b.PROTO and len(old["cases"])==51,"R32b 51-input manifest required")
    cases=[]
    for case in old["cases"]:
        raw=(previous/case["name"]).read_bytes()
        check(sha(raw)==case["sha256"],"Old SHA drift "+case["name"])
        (out/case["name"]).write_bytes(raw)
        cases.append(dict(name=case["name"],family=case["family"],
                          expected=case["expected"],sha256=case["sha256"],
                          cohort="R32b_diagnostic"))
    for family in r31.FAMILIES:
        for idx in FRESH_INDICES:
            n,clauses,expected,_=r31.make_case(family,idx)
            raw=r31.encode(n,clauses)
            name=f"r32c_blind_{family}_{idx:02d}.cnf"
            (out/name).write_bytes(raw)
            cases.append(dict(name=name,family=family,
                              expected=expected,sha256=sha(raw),
                              cohort="fresh_synthetic_holdout"))
    check(len(cases)==93 and len({x["sha256"] for x in cases})==93,
          "93 unique original CNF checksums required")
    manifest=dict(protocol=PROTO,previous_protocol=b.PROTO,
                  previous_sha256=sha(previous/"manifest.json"),
                  modes=MODES,repeats=REPS,shards=SHARDS,cap=CAP,
                  fresh_indices=FRESH_INDICES,cases=cases,
                  cautions=[
                   "42 SHA-distinct holdout cases are deterministic synthetic, not unseen external SAT Competition formulas",
                   "51 older cases are not blind",
                   "2 previously seen SAT Competition 2026 GBD cases are guarded timeout controls",
                   "R32c only adds unconditional GF2 root units from complete proven XOR subsystem",
                   "Contradictory, unknown, oversized or more than 12 candidate roots abstain",
                   "4s timeout, PAR-2 8s; tiny solve-time differences may be system noise",
                   "SAT witnesses checked on original CNF; UNSAT is label-matched, no DRAT/LRAT certification",
                   "No implication for P versus NP or worldwide SAT ranking"])
    (out/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
    (out/"cnf.sha256").write_text("".join(
        f'{x["sha256"]}  {x["name"]}\n' for x in cases))
    print("R32C_SHA_FROZEN",len(cases),"fresh",42,sha(out/"manifest.json"),flush=True)

def one_trial(case,path,mode,bins):
    binary=bins["clean"] if mode=="clean" else bins["native"]
    env=os.environ.copy()
    env["R32B_MODE"]={"clean":"off","native_off":"off",
                     "R32B_native_shadow":"shadow",
                     "R32C_active":"active"}[mode]
    started=time.monotonic()
    try:
        p=subprocess.run([str(binary),str(path)],env=env,
                         stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                         text=True,errors="replace",timeout=CAP)
        elapsed=time.monotonic()-started
        check(p.returncode in (10,20),f"{mode} bad Kissat exit: {p.returncode} {p.stderr[-400:]}")
        status="SAT" if p.returncode==10 else "UNSAT"
        check(not case["expected"] or status==case["expected"].upper(),
              f"Incorrect expected label on {case['name']} mode={mode}")
        verification=b.sat_check(path,p.stdout) if status=="SAT" else "reference_label_only"
        stdout=p.stdout
    except subprocess.TimeoutExpired as exc:
        elapsed=time.monotonic()-started
        status="TIMEOUT";verification="censored"
        stdout=exc.stdout or b""
        if isinstance(stdout,bytes):stdout=stdout.decode(errors="replace")
    probes,final=b.parse_native(stdout)
    if mode=="clean":check(not probes and final is None,"Clean binary unexpectedly instrumented")
    if mode=="native_off":check(not probes,"OFF ran probe")
    root=None;proof=None
    if mode in ("R32B_native_shadow","R32C_active"):
        root=b.get_root(probes)
        proof=b.compare_root(root,path)
        check(proof["status"] in ("independent_proof_match","old_python_guard"),
              "Independent GF2 source verification failure")
    active=None
    if mode=="R32C_active":
        matches=re.findall(r"^c R32C_ACTIVE signal=([A-Z_]+) injected=(\d+) certified=(\d+)$",
                           stdout,re.MULTILINE)
        check(len(matches)==1,"Missing/duplicated active intervention log")
        signal,inj,cert=matches[0]
        active=dict(signal=signal,injected=int(inj),certified=int(cert))
        expected=int(root.get("extra",0)) if root["signal"]=="CONSISTENT_GAP" else 0
        approved=expected if 0<expected<=12 else 0
        check(active["injected"]==approved,
              f"Unsound active unit count on {case['name']}: {active} expected={approved}")
        check(active["certified"]>=active["injected"],"Uncertified injection")
        if approved:
            check(signal=="APPLIED","Unit-eligible but not applied")
            literal_lines=re.findall(r"^c R32C_INJECTED_LITS count=(\d+) lits=([0-9,-]+)$",
                                     stdout,re.MULTILINE)
            check(len(literal_lines)==1,"No signed literal disclosure for active injection")
            count_str,signed=literal_lines[0]
            literals=[int(z) for z in signed.split(",")]
            check(int(count_str)==len(literals)==approved,
                  "Injected literal count does not match independent proof")
            check(sorted(literals)==sorted(root["sample"]),
                  "Injected literals do not match independently proven signed units")
            active["literals"]=literals
        else:
            check(signal!="APPLIED","Active intervention on abstained formula")
            check("R32C_INJECTED_LITS" not in stdout,
                  "Disclosed root injection on abstained formula")
    if status!="TIMEOUT" and mode!="clean":
        check(final is not None,"Native final counters missing")
        check(final["status"]==(10 if status=="SAT" else 20),
              "Invalid native final status")
    return dict(status=status,seconds=round(elapsed,6),
                par2=round(elapsed,6) if status!="TIMEOUT" else 2*CAP,
                verification=verification,root=root,
                validated_proof=proof["status"] if proof else None,
                probes=len(probes),active=active,final=final)

def measure(args):
    frozen=Path(args.inputs)
    manifest=json.loads((frozen/"manifest.json").read_text())
    check(manifest["protocol"]==PROTO and tuple(manifest["modes"])==MODES,
          "Changed protocol")
    check(0<=args.shard<SHARDS,"Shard range")
    if hasattr(os,"sched_getaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    bins={k:Path(getattr(args,k)).resolve() for k in ("clean","native")}
    check(all(x.is_file() for x in bins.values()),"Missing pinned binary")
    out=Path(args.outdir);out.mkdir(parents=True,exist_ok=True)
    (out/"meta.json").write_text(json.dumps(dict(
        shard=args.shard,manifest=sha(frozen/"manifest.json"),
        binary_sha256={key:sha(val) for key,val in bins.items()}),indent=2))
    rows=[]
    for case in manifest["cases"][args.shard::SHARDS]:
        path=frozen/case["name"]
        check(sha(path)==case["sha256"],"Unfrozen source")
        for rep in range(REPS):
            order=list(MODES)
            random.Random(int(sha((case["sha256"]+":"+str(rep)+":R32C").encode()),16)).shuffle(order)
            for mode in order:
                row=one_trial(case,path,mode,bins)
                rows.append(dict(case=case["name"],family=case["family"],
                                 cohort=case["cohort"],repeat=rep,mode=mode,**row))
                (out/"rows.json").write_text(json.dumps(rows)+"\n")
                print("R32C_TRIAL",args.shard,case["name"],rep,mode,
                      row["status"],row["seconds"],"injected",
                      row["active"]["injected"] if row["active"] else "-",flush=True)
        statuses={x["status"] for x in rows if x["case"]==case["name"]}-{"TIMEOUT"}
        check(len(statuses)<=1,"Contradictory SAT/UNSAT between arms")
    print("R32C_SHARD_COMPLETE",args.shard,len(rows),flush=True)

def aggregate(args):
    root=Path(args.inputs);manifest=json.loads((root/"manifest.json").read_text())
    check(manifest["protocol"]==PROTO,"Wrong frozen manifest")
    rows=[];fingerprints=set()
    for shard in range(SHARDS):
        d=Path(args.combined)/f"r32c-shard-{shard}"/"results"
        meta=json.loads((d/"meta.json").read_text())
        check(meta["shard"]==shard and meta["manifest"]==sha(root/"manifest.json"),
              "Manifest checksum mismatch")
        fingerprints.add(json.dumps(meta["binary_sha256"],sort_keys=True))
        piece=json.loads((d/"rows.json").read_text())
        check(len(piece)==len(manifest["cases"][shard::SHARDS])*REPS*len(MODES),
              "Missing paired trials")
        rows.extend(piece)
    check(len(rows)==93*REPS*len(MODES) and len(fingerprints)==1,
          "Expected 744 attempts at identical binary identities")
    bycase={c["name"]:[r for r in rows if r["case"]==c["name"]]
            for c in manifest["cases"]}
    failed_policy=[]
    for name,arr in bycase.items():
        for rep in range(REPS):
            bymode={x["mode"]:x for x in arr if x["repeat"]==rep}
            off=bymode["native_off"];shadow=bymode["R32B_native_shadow"]
            active=bymode["R32C_active"]
            check(off["status"]=="TIMEOUT" or shadow["status"]=="TIMEOUT"
                  or off["status"]==shadow["status"],
                  "Passive output diverged")
            if off["final"] and shadow["final"] and off["final"]!=shadow["final"]:
                failed_policy.append(dict(name=name,rep=rep,type="OFF_VS_SHADOW",
                                          off=off["final"],shadow=shadow["final"]))
            if (active["active"]["injected"]==0 and
                off["final"] and active["final"] and
                off["final"]!=active["final"]):
                failed_policy.append(dict(name=name,rep=rep,type="ABSTENTION_DRIFT",
                                          off=off["final"],active=active["final"]))
    check(not failed_policy,"Invariance failed: "+json.dumps(failed_policy[:3]))
    groups={"ALL":manifest["cases"],
            "fresh_synthetic_holdout":[x for x in manifest["cases"] if x["cohort"]=="fresh_synthetic_holdout"],
            "R32b_diagnostic":[x for x in manifest["cases"] if x["cohort"]=="R32b_diagnostic"]}
    for family in r31.FAMILIES:
        groups[family]=[x for x in manifest["cases"] if x["family"]==family]
    summaries={}
    for group,cases in groups.items():
        names={x["name"] for x in cases}
        d={}
        for mode in MODES:
            part=[x for x in rows if x["mode"]==mode and x["case"] in names]
            check(len(part)==2*len(cases),"Missing mode trials")
            d[mode]=dict(sum_PAR2=round(sum(x["par2"] for x in part),6),
                         solved=sum(all(x["status"]!="TIMEOUT" for x in part if x["case"]==c["name"])
                                    for c in cases),
                         timeouts=sum(x["status"]=="TIMEOUT" for x in part))
        active=[x for x in rows if x["mode"]=="R32C_active" and x["case"] in names]
        d["root_injected_unit_attempts"]=sum(x["active"]["injected"] for x in active)
        d["cases_with_proven_injection"]=sum(any(z["active"]["injected"]>0 for z in active
            if z["case"]==c["name"]) for c in cases)
        d["root_signals"]=dict(collections.Counter(x["root"]["signal"] for x in active))
        baseline=d["native_off"]["sum_PAR2"]
        d["active_vs_native_off_pct"]=round(100*(d["R32C_active"]["sum_PAR2"]-baseline)/max(1e-9,baseline),4)
        summaries[group]=d
        print("R32C_SUMMARY",group,json.dumps(d,sort_keys=True),flush=True)
    per_case=[]
    for case in manifest["cases"]:
        relevant=bycase[case["name"]]
        times={m:round(statistics.median(z["par2"] for z in relevant if z["mode"]==m),6)
               for m in MODES}
        act=next(x for x in relevant if x["mode"]=="R32C_active")
        per_case.append(dict(name=case["name"],family=case["family"],cohort=case["cohort"],
                             injected=act["active"]["injected"],
                             classification=act["active"]["signal"],
                             root=act["root"]["signal"],
                             verified=act["validated_proof"],times=times))
    out=dict(protocol=PROTO,sha256=sha(root/"manifest.json"),summary=summaries,
             per_case=per_case,rows=rows,
             warnings=manifest["cautions"])
    Path(args.output).write_text(json.dumps(out,indent=2)+"\n")
    md=["# DRNAS R32c — active certified native GF(2) root-unit ablation",
        "93 original SHA-distinct CNFs (51 prior diagnostics, 42 fresh synthetic holdout)",
        "2 repeats x 4 matched native policies = 744 attempts; timeout 4s, PAR-2=8s.",
        "Active units inserted ONLY if independently verifiable complete source parity entails root literal.",
        "Root contradictions, incomplete patterns and guards NEVER generate units.",
        "Source-level audit: OFF and SHADOW counters match; any active no-op must match OFF.",
        "This is NOT a real external blind industrial or official world competition.",
        "","| Group | Clean PAR-2 s | Native OFF PAR-2 s | R32b passive PAR-2 s | R32c active PAR-2 s | Delta active vs OFF | Cases injected |",
        "|---|---:|---:|---:|---:|---:|---:|"]
    for fam,d in summaries.items():
        md.append(f'| {fam} | {d["clean"]["sum_PAR2"]:.5f} | {d["native_off"]["sum_PAR2"]:.5f} | {d["R32B_native_shadow"]["sum_PAR2"]:.5f} | {d["R32C_active"]["sum_PAR2"]:.5f} | {d["active_vs_native_off_pct"]:+.3f}% | {d["cases_with_proven_injection"]} |')
    md+=["","| Formula | Cohort | Root | Injected | Clean s | R32b s | R32c s |",
         "|---|---|---|---:|---:|---:|---:|"]
    for p in per_case:
        t=p["times"]
        md.append(f'| {p["name"]} | {p["cohort"]} | {p["root"]} | {p["injected"]} | {t["clean"]:.5f} | {t["R32B_native_shadow"]:.5f} | {t["R32C_active"]:.5f} |')
    Path(args.report).write_text("\n".join(md)+"\n")
    print("R32C_AUDIT_PASS",len(rows),"attempts",len(per_case),"formulas",flush=True)

def main():
    ap=argparse.ArgumentParser()
    sp=ap.add_subparsers(dest="command",required=True)
    s=sp.add_parser("freeze")
    s.add_argument("--prior",required=True);s.add_argument("--dest",required=True)
    s=sp.add_parser("measure")
    for f in ("inputs","clean","native","outdir"):s.add_argument("--"+f,required=True)
    s.add_argument("--shard",type=int,required=True)
    s=sp.add_parser("aggregate")
    for f in ("inputs","combined","output","report"):s.add_argument("--"+f,required=True)
    args=ap.parse_args()
    if args.command=="freeze":freeze(args.prior,args.dest)
    elif args.command=="measure":measure(args)
    else:aggregate(args)

if __name__=="__main__":main()
