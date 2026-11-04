#!/usr/bin/env python3
"""R85 frozen real-new official CNF matched A/B/C/D vs clean Kissat benchmark.

Eight actual never-DRNAS-benchmarked original SAT Competition 2025/2026
CNFs selected without solver timing or XOR screen. Exactly ONE mixed XOR source
happened to appear in the selection (not preselected to win). Two repeats on
each SHA, five serial modes on same runner, randomized fixed order, one CPU,
35s charged end-to-end, timeout PAR2=70s. Six other sources exceed native XOR
guards; report no transfer rather than invent gain. All original SAT witnesses
independently validated; UNSAT original proof not independently LRAT-certified.
"""
from __future__ import annotations
import argparse,hashlib,json,os,random,re,subprocess,time
from pathlib import Path
import r83_live_xor_cdcl_wide as r83
import r32p_real_satcomp26_benchmark as r32p
import r85_freeze_unseen2025_2026 as frozen

PROTO="DRNAS-R85-ABCD-MATCHED-REAL-UNSEEN-2025-2026-v1"
MODES=frozen.MODES
REPS,CAP,SHARDS=frozen.REPS,frozen.CAP,frozen.SHARDS
ROW_RE=r83.SOURCE_ROW
ARM_RE=re.compile(r"^c R85_ARM id=(\d+) source_rows=(\d+) requested=(\d+)$",re.M)
PROGRESS_RE=re.compile(r"^c R85_PROGRESS (.+)$",re.M)
ARM_IDS={"A_passive":0,"B_active64":1,"C_spread64":2,"D_wide256":3}
REQ_ROWS={0:64,1:64,2:256,3:256}

def ck(test,why):
    if not test:raise RuntimeError("R85_MEASUREMENT_AUDIT_FAIL_CLOSED "+str(why))
def sha(path):return r83.sha(path)
def save(path,payload):
    Path(path).write_text(json.dumps(payload,indent=2,sort_keys=True)+"\n")
def source(root):
    m=json.loads((Path(root)/"manifest.json").read_text())
    ck(m["protocol"]==frozen.PROTO and len(m["cases"])==8 and
       m["cap_s"]==CAP and m["modes"]==list(MODES),
       "wrong frozen prospective manifest")
    ck(len({c["gbd"] for c in m["cases"]})==8 and
       len({c["sha256"] for c in m["cases"]})==8,
       "original SHA duplicate")
    ck(sum(c["year"]==2025 for c in m["cases"])==4 and
       sum(c["year"]==2026 for c in m["cases"])==4,
       "wrong source year split")
    return m

def parse_native(text,mode,case,src,checked):
    if mode=="clean":
        ck(not ARM_RE.search(text) and not PROGRESS_RE.search(text),
           "unmodified original Kissat has DRNAS native telemetry")
        return dict(rows=0,snapshots=0,last=None,arm=None,
                    original_xor_rows_verified=True)
    tags=ARM_RE.findall(text)
    progress=[]
    for raw in PROGRESS_RE.findall(text):
        entry={}
        for pair in raw.split():
            k,v=pair.split("=",1)
            entry[k]=float(v) if k=="cpu_ms" else int(v)
        progress.append(entry)
    cert_rows=[(tuple(int(v) for v in vars_.split(",")),int(rhs))
               for rhs,vars_ in ROW_RE.findall(text)]
    expect=ARM_IDS[mode]
    ck(len(tags)<=1,"multiple inconsistent native arm tags")
    if tags:
        k,n,requested=map(int,tags[0])
        ck(k==expect and requested==REQ_ROWS[k] and n==len(cert_rows),
           "native arm or selected source proofs not pinned")
    else:
        ck(not cert_rows and not progress,"source rows emitted without native arm record")
    if cert_rows:
        source_id=case["sha256"]
        if source_id not in checked:
            ck(r83.source_prove_rows(src,cert_rows)==len(cert_rows),
               "source linear GF2 consequence not independently certified")
            checked[source_id]=tuple(cert_rows)
        else:
            ck(checked[source_id]==tuple(cert_rows),
               "different parity row certificates within same formula")
    if progress:
        last=progress[-1]
        ck(last["arm"]==expect and last["rows"]==len(cert_rows),
           "R85 progress/source provenance discrepancy")
        for aa,bb in zip(progress,progress[1:]):
            for key in ("scans","attached","no_slot","unimported","eliminated",
                        "bad_lit","multi_free","full_assigned","eligible",
                        "uip_reason_matches","conflicts","decisions"):
                ck(aa[key]<=bb[key],"nonmonotonic R85 "+key)
        ck(last["eligible"]>=last["attached"],
           "native attached more reasons than eligible implications")
        if mode=="A_passive":
            ck(last["attached"]==0 and last["uip_reason_matches"]==0,
               "passive method mutated solver")
    return dict(rows=len(cert_rows),snapshots=len(progress),
                last=progress[-1] if progress else None,
                arm=expect,original_xor_rows_verified=True)

def trial(case,orig,mode,binaries,checked):
    arm=ARM_IDS.get(mode)
    binary=binaries["clean"] if mode=="clean" else binaries["native"]
    env=os.environ.copy()
    if arm is not None:
        env.update(R32B_MODE="r32u",R32U_ACTIVE="0" if arm==0 else "1",
                   R85_ARM="ABCD"[arm],R84_SCAN_EVERY="4" if arm==3 else "16",
                   R32S_PASSIVE_TRACE="0",R32L_TRACE="0",R32M_PHASES="0")
    start=time.monotonic();finished=False;stdout="";answer="TIMEOUT"
    try:
        p=subprocess.run([str(binary),str(orig)],env=env,
            capture_output=True,text=True,errors="replace",timeout=CAP)
        ck(p.returncode in (10,20),
           "unexpected native solver exit "+str(p.returncode)+" stderr "+p.stderr[-350:])
        stdout=p.stdout;finished=True
        answer="SAT" if p.returncode==10 else "UNSAT"
    except subprocess.TimeoutExpired as e:
        stdout=e.stdout or b""
        if isinstance(stdout,bytes):stdout=stdout.decode(errors="replace")
    elapsed=time.monotonic()-start
    solved=finished and elapsed<=CAP
    if answer=="SAT":r32p.verify_sat_witness(orig,stdout)
    if solved and case["source_verified_status"]:
        ck(answer==case["official_status"],"wrong official verified 2026 status")
    native=parse_native(stdout,mode,case,orig,checked)
    return dict(answer=answer if solved else "TIMEOUT",solved=solved,
                wall_s=round(min(elapsed,CAP),6),
                par2_s=round(elapsed if solved else 2*CAP,6),
                native=native,sat_model_checked=(answer=="SAT"),
                unsat_lrat_checked=False)

def measure(a):
    root=Path(a.sources).resolve()
    mf=source(root)
    ck(0<=a.shard<SHARDS,"bad shard")
    binroot=Path(a.bins).resolve()
    ck(subprocess.run(["sha256sum","-c","r85-binaries.sha256"],
          cwd=binroot,stdout=subprocess.DEVNULL).returncode==0,
       "solver binary SHA mismatch")
    binary={"clean":binroot/"clean","native":binroot/"native-r85"}
    ck(all(p.is_file() and os.access(p,os.X_OK) for p in binary.values()),
       "binary not executable")
    if hasattr(os,"sched_setaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    case=mf["cases"][a.shard]
    orig=root/case["filename"]
    ck(sha(orig)==case["sha256"],"source file SHA drift")
    rows=[];checked={}
    for rep in range(REPS):
        order=list(MODES)
        random.Random(int(hashlib.sha256(
           (PROTO+case["sha256"]+str(rep)).encode()).hexdigest(),16)).shuffle(order)
        for mode in order:
            result=trial(case,orig,mode,binary,checked)
            row=dict(gbd=case["gbd"],sha256=case["sha256"],year=case["year"],
                     group=case["group"],rep=rep,mode=mode,**result)
            rows.append(row)
            save(out/"r85-shard.json",
                dict(protocol=PROTO,shard=a.shard,
                     source_manifest_sha=sha(root/"manifest.json"),
                     binary_sha={key:sha(path) for key,path in binary.items()},
                     rows=rows))
            count=(result["native"]["last"] or {})
            print("R85_TRIAL",json.dumps(dict(gbd=case["gbd"],year=case["year"],
                group=case["group"],rep=rep,mode=mode,answer=result["answer"],
                par2_s=result["par2_s"],wall_s=result["wall_s"],
                source_rows=result["native"]["rows"],attached=count.get("attached",0),
                eligible=count.get("eligible",0),uip_matches=count.get("uip_reason_matches",0))),
                flush=True)
    ck(len(rows)==REPS*len(MODES),"incomplete source trial")
    print("R85_SHARD_PASS",a.shard,len(rows),flush=True)

def audit(a):
    root=Path(a.sources);mf=source(root)
    allrows=[];pins=set()
    for shard in range(SHARDS):
        p=Path(a.combined)/f"r85-shard-{shard}"/"results"/"r85-shard.json"
        ck(p.is_file(),"missing source shard "+str(shard))
        j=json.loads(p.read_text())
        ck(j["protocol"]==PROTO and j["shard"]==shard and
           j["source_manifest_sha"]==sha(root/"manifest.json"),
           "foreign shard or source drift")
        pins.add(json.dumps(j["binary_sha"],sort_keys=True))
        ck(len(j["rows"])==REPS*len(MODES),"missing paired rows")
        allrows+=j["rows"]
    ck(len(pins)==1 and len(allrows)==8*2*len(MODES),
       "wrong binary cohort or missing trials")
    for case in mf["cases"]:
        qr=[r for r in allrows if r["sha256"]==case["sha256"]]
        ck(len(qr)==REPS*len(MODES),"wrong source coverage")
        for rep in range(REPS):
            subset=[r for r in qr if r["rep"]==rep]
            ck(len(subset)==len(MODES) and
               {x["mode"] for x in subset}==set(MODES),"missing solver mode")
            answers={x["answer"] for x in subset if x["answer"]!="TIMEOUT"}
            ck(len(answers)<=1,"solver verdict contradiction on same original")
            if case["source_verified_status"]:
                ck(all(x==case["official_status"] for x in answers),
                   "published official SAT2026 status differs")
            for r in subset:
                ck(r["native"]["original_xor_rows_verified"],
                   "original source XOR proofs not verified")
    groups={"ALL":mf["cases"],
            "YEAR2025":[x for x in mf["cases"] if x["year"]==2025],
            "YEAR2026":[x for x in mf["cases"] if x["year"]==2026],
            "XOR_PRESENT":[x for x in mf["cases"] if x["group"] in ("mixed_exact","pure_exact")],
            "CONTROLS":[x for x in mf["cases"] if x["group"] not in ("mixed_exact","pure_exact")]}
    summaries={}
    for name,cohort in groups.items():
        ids={c["sha256"] for c in cohort};summary={}
        for mode in MODES:
            selected=[r for r in allrows if r["sha256"] in ids and r["mode"]==mode]
            summary[mode]=dict(trials=len(selected),
              solved=sum(r["solved"] for r in selected),
              par2_s=round(sum(r["par2_s"] for r in selected),6),
              source_rows=sum(r["native"]["rows"] for r in selected),
              matched_uip_reasons=sum((r["native"]["last"] or {}).get("uip_reason_matches",0)
                                      for r in selected),
              attached=sum((r["native"]["last"] or {}).get("attached",0)
                           for r in selected))
        summaries[name]=summary
    base={r["sha256"]:r for r in mf["cases"]}
    performula=[]
    for source_hash,case in base.items():
        ss=[r for r in allrows if r["sha256"]==source_hash]
        performula.append(dict(gbd=case["gbd"],group=case["group"],year=case["year"],
            by={m:[round(r["par2_s"],6) for r in ss if r["mode"]==m] for m in MODES}))
    import random
    rng=random.Random(8500)
    comparisons={}
    for group,cs in groups.items():
        vals=[]
        for c in cs:
            r=[x for x in allrows if x["sha256"]==c["sha256"]]
            avg={m:sum(x["par2_s"] for x in r if x["mode"]==m)/REPS for m in MODES}
            vals.append(avg)
        comparisons[group]={}
        for mode in MODES[1:]:
            differences=[v["clean"]-v[mode] for v in vals]
            boot=[]
            if differences:
                for _ in range(2000):
                    boot.append(sum(differences[rng.randrange(len(differences))]
                                    for _ in differences)/len(differences))
                boot.sort()
                ci=[round(boot[50],6),round(boot[1949],6)]
                mean=sum(differences)/len(differences)
            else: ci=None;mean=None
            comparisons[group][mode]=dict(n_distinct_formulas=len(differences),
                seconds_saved_mean=None if mean is None else round(mean,6),
                bootstrap_ci95_seconds_saved=ci)
    report=dict(protocol=PROTO,status="PASS_UNOFFICIAL",sources=8,trials=len(allrows),
         original_sha_manifest=sha(root/"manifest.json"),solver_sha=json.loads(next(iter(pins))),
         cohort_counts={k:len(v) for k,v in groups.items()},
         summary=summaries,comparisons=comparisons,
         per_formula=performula,rows=allrows,
         limitations=mf["limitations"]+[
          "C uses source-proven deterministic spread-64 selection, not online learning.",
          "D uses 256 source-proven rows at 4-decision cadence; all overhead included.",
          "R85 UIP reason matching is native reason-code matching, not independent DRAT/LRAT proof.",
          "If XOR is absent/no new short rows, no general XOR advantage can be inferred.",
          "Eight formulas, two repetitions and 35s cap are exploratory, not official SAT Competition ranking.",
          "Do not pool official-verdict 2026 sources with unverified-status 2025 UNSAT as if all independently proven."])
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    save(out/"r85-final.json",report)
    lines=["# DRNAS R85 — four methods on eight newly frozen official 2025/2026 originals",
        "Prospective source SHA and GBD disjoint from documented history.",
        "Two repeats, one CPU, 35-second end-to-end cap, PAR2 timeout 70 s.",
        "A: passive64, B: active64, C: certified spread64, D: certified 256 with cadence4.",
        "Original CNF SAT models checked; no externally replayed UNSAT LRAT.",
        "", "| Solver | Solved | PAR2 s | Native GF2 reason attaches | First-UIP reason matches |",
        "|---|---:|---:|---:|---:|"]
    for m,v in summaries["ALL"].items():
        lines.append(f"| {m} | {v['solved']}/{v['trials']} | {v['par2_s']:.3f} | {v['attached']} | {v['matched_uip_reasons']} |")
    for group in ("XOR_PRESENT","CONTROLS","YEAR2025","YEAR2026"):
        lines.extend(["",f"## {group} ({len(groups[group])} distinct formulas)",
             "| Solver | Solved | PAR2 s |", "|---|---:|---:|"])
        for m,v in summaries[group].items():
            lines.append(f"| {m} | {v['solved']}/{v['trials']} | {v['par2_s']:.3f} |")
    lines+=["","## Per original formula"]
    for item in performula:
        lines.append(f"- {item['gbd']} {item['group']} ({item['year']}): "+
            ", ".join(f"{m}={v}" for m,v in item["by"].items()))
    lines+=["","## Explicit caveats"]+["- "+v for v in report["limitations"]]
    (out/"r85-final.md").write_text("\n".join(lines)+"\n")
    print("R85_FINAL_AUDIT_PASS",json.dumps(summaries["ALL"]),flush=True)

def selftest():
    sample="c R85_ARM id=2 source_rows=1 requested=256\n"+\
        "c R32U_SOURCE_ROW rhs=1 vars=1,4\n"+\
        "c R85_PROGRESS arm=2 rows=1 scans=12 attached=1 no_slot=0 unimported=1 eliminated=2 bad_lit=0 multi_free=77 full_assigned=3 eligible=4 uip_reason_matches=1 conflicts=7 decisions=66 cpu_ms=2000.1 final=0\n"
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        p=Path(td)/"xor.cnf"
        p.write_text("p cnf 4 8\n"+
          "".join(" ".join(map(str,tuple(-v if (mask>>i)&1 else v for i,v in enumerate(vs))))+
          " 0\n" for vs,mask in [((1,2,3),i) for i in (1,2,4,7)]+[((2,3,4),i) for i in (0,3,5,6)]))
        case=dict(sha256=sha(p))
        ck(parse_native(sample,"C_spread64",case,p,{})["last"]["uip_reason_matches"]==1,
           "native telemetry protocol selftest failed")
    print("R85_REAL_BENCH_PARSER_AND_ORIGINAL_GF2_PROOF_SELFTEST_PASS",flush=True)

def main():
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest="cmd",required=True)
    sub.add_parser("selftest")
    m=sub.add_parser("measure")
    for k in ("sources","bins","out"):m.add_argument("--"+k,required=True)
    m.add_argument("--shard",type=int,required=True)
    a=sub.add_parser("audit")
    for k in ("sources","combined","out"):a.add_argument("--"+k,required=True)
    x=p.parse_args()
    if x.cmd=="selftest":selftest()
    elif x.cmd=="measure":measure(x)
    else:audit(x)
if __name__=="__main__":main()
