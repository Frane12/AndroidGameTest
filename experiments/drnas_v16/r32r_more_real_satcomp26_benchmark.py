#!/usr/bin/env python3
"""DRNAS R32r: prospective SATComp2026 CNFs, exact algebra R28 vs Kissat and R32n.

Frozen official GBD Main 2026 candidate indices published before execution.
NO synthetic source input, NO concurrent solver on same CNF, NO process
communication, NO watchdog policy, no training on test results.
All attempted download rejections retained. Each source is SHA-locked and
benchmark modes have identical per-attempt timing procedure. Source-size
restrictions are engineering censoring, not claims about benchmark coverage.
"""
from __future__ import annotations
import argparse,bz2,collections,gzip,hashlib,io,json,lzma,os,random,re,statistics,subprocess,time,urllib.request
from pathlib import Path

PROTO="DRNAS-R32R-PROSPECTIVE-REAL2026-EXACT-GF2-20261103-v1"
OFFICIAL_URI="https://satcompetition.github.io/2026/downloads/track_main_2026.uri"
MAIN_SOURCE="https://github.com/satcompetition/2026/blob/main/downloads/track_main_2026.uri"
PINS=[
 (9,"07df5e6f674201e2bf31bcaa8866ba75"),
 (27,"12535b3264a9c88bac14522171b497ef"),
 (46,"1eea3d913d346b900252d77fc0cb25c8"),
 (64,"284dec9d0d0404c8b80d8bd8064e4c68"),
 (81,"306a29e966fa6293d407bc7ebbc3ecb1"),
 (99,"3a9dfcbcb56689f1118fd7a2150c3c0c"),
 (116,"44452f4bac1e77157bbc900c5cc0756d"),
 (133,"510df610f94d5d57073a2c3b694dac4c"),
 (151,"5d02aa18eac7304c705577f1cce07784"),
 (168,"65bf849f3e86ab275e339934f4d140a0"),
 (186,"727ebce936c010888c7f71f00885e643"),
 (203,"7db30d12cb06f0dc2f30abff80d96d6a"),
 (221,"878bcc11e1e243680f7946bcf428f465"),
 (238,"91e0db01b254eb78f6643328045bfeb9"),
 (256,"9ba8145e0d02318dea5507fc3ba03472"),
 (273,"a789d0722f1aa0d44c5a38b374719c69"),
 (291,"ad6bc2d583c43ff9ef00faad7e29a9c2"),
 (308,"b76b9699c2deb74dd9b4a99a05179acd"),
 (326,"c62a1855a4db8ae0b4bd625455332a4c"),
 (343,"d737aeb8e2eb9baed7f007056b3874af"),
 (361,"e305def35c314eec8266087e89a9ab46"),
 (378,"f1d1a4fee20e2907c33465a88d1e24f2"),
 (394,"fca71c20202ef404349136c3a00465eb"),
]
RAW_LIMIT=28*1024*1024
CNF_LIMIT=56*1024*1024
REPS=2
CAP=30.0
SHARDS=4
MODES=("clean","native_off","full","r28_exact")
MIN_READY=5

def check(v,msg):
    if not v:raise RuntimeError("R32R_OFFICIAL_AUDIT_FAILURE "+str(msg))
def sha(v):
    h=hashlib.sha256()
    if isinstance(v,(str,Path)):
        with open(v,"rb") as file:
            for chunk in iter(lambda:file.read(1<<20),b""):h.update(chunk)
    else:h.update(v)
    return h.hexdigest()

def request_url(url,bytes_max,seconds=40):
    req=urllib.request.Request(url,headers={"User-Agent":"DRNAS-Research-Source-Audit-R32p/1.0",
        "Accept":"application/octet-stream"})
    with urllib.request.urlopen(req,timeout=seconds) as stream:
        raw=stream.read(bytes_max+1)
        check(len(raw)<=bytes_max,"remote payload exceeds precommitted size cap")
        return raw,stream.geturl()

def decode(raw):
    # Bounded decompression to avoid exceeding job memory.
    if raw.startswith(b"\xfd7zXZ\x00"):
        f=lzma.LZMAFile(io.BytesIO(raw))
        kind="xz"
    elif raw.startswith(b"\x1f\x8b"):
        f=gzip.GzipFile(fileobj=io.BytesIO(raw))
        kind="gzip"
    elif raw.startswith(b"BZh"):
        f=bz2.BZ2File(io.BytesIO(raw))
        kind="bzip2"
    else:
        return raw,"plain"
    with f:
        content=f.read(CNF_LIMIT+1)
    check(len(content)<=CNF_LIMIT,"uncompressed DIMACS exceeds precommitted cap")
    return content,kind

def parse_dimacs_metadata(data):
    check(len(data)<=CNF_LIMIT,"DIMACS source too large")
    p=[line for line in data.splitlines() if line.startswith(b"p cnf ")]
    check(len(p)==1,"Original CNF must have exactly one p cnf header")
    hdr=p[0].split()
    check(len(hdr)==4 and hdr[:2]==[b"p",b"cnf"],"DIMACS invalid header")
    variables,clauses=map(int,hdr[2:])
    check(0<variables<=50000000 and 0<clauses<=100000000,"DIMACS implausible dimensions")
    return variables,clauses

def freeze(root):
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    logs=[];cases=[]
    check(len(PINS)==23 and len({x for _,x in PINS})==23,"Changed external source protocol")
    # Exact main-track GBD URI list was verified by GitHub repository file
    # before selecting the indices, not based on measured solver runtimes.
    for index,gbd in PINS:
        url="https://benchmark-database.de/file/"+gbd
        trace=dict(index=index,gbd=gbd,url=url)
        try:
            raw,redirect=request_url(url,RAW_LIMIT)
            cnf,compression=decode(raw)
            check(len(cnf)<=CNF_LIMIT,"uncompressed original exceeds cap")
            n,m=parse_dimacs_metadata(cnf)
            name=gbd+".cnf"
            path=root/name
            path.write_bytes(cnf)
            ident=sha(path)
            check(path.stat().st_size==len(cnf),"Corrupt downloaded source")
            case=dict(name=name,index=index,gbd=gbd,sha256=ident,
                      source=url,redirect=redirect,raw_sha256=sha(raw),
                      compressed_bytes=len(raw),bytes=len(cnf),
                      vars=n,clauses=m,compression=compression,
                      provenance="2026 SAT Competition Main GBD canonical URI")
            cases.append(case)
            trace.update(status="READY",sha256=ident,raw_bytes=len(raw),bytes=len(cnf),
                         vars=n,clauses=m,compression=compression)
        except Exception as error:
            trace.update(status="EXCLUDED_DOWNLOAD_OR_SIZE",
                         reason=(type(error).__name__+": "+str(error))[:280])
        logs.append(trace)
        print("R32R_SOURCE",json.dumps(trace,sort_keys=True),flush=True)
    manifest=dict(protocol=PROTO,source_list=OFFICIAL_URI,canonical_repository=MAIN_SOURCE,
        precommitted_candidates=[dict(index=i,gbd=h) for i,h in PINS],
        complete_download_log=logs,cases=cases,repeats=REPS,modes=MODES,
        shards=SHARDS,timeout_seconds=CAP,par2_timeout_s=CAP*2,
        max_raw_bytes=RAW_LIMIT,max_dimacs_bytes=CNF_LIMIT,
        limitations=[
          "Official Main 2026 source files, not independently submitted new competition instances",
          "All 23 candidates SHA-pinned before testing; only download/size exclusions",
          "No score-based selection or substitution of unavailable inputs",
          "Potential overlap with older DRNAS comparisons not exhaustively ruled out by source hashes",
          "All source CNFs independently SHA-fingerprinted before benchmark",
          "Original Kissat versus native OFF measures instrumentation overhead",
          "R28 is PRIOR ART full-XOR Gaussian elimination; R32n is size/unit-gated root injection",
          "R28 classifies source only below its 12MiB, 3000-var, 150000-clause guard; otherwise falls back to identical clean Kissat",
          "Full GF2 unit injection sound only if mathematically independently checked",
          "Most industrial formulas may exceed native 8MiB/1024-var/10000-clause guard; record abstentions",
          "One solver per trial and fixed process timeout only; no search watchdog or portfolio",
          "SAT verdict certified against unchanged original CNF witness",
          "UNSAT replies compared across solvers but not independently LRAT-proof checked",
          "Official SAT Competition uses different hardware and a different time cap; these are LOCAL results",
          "Size cap creates a biased restricted sample; no claim of benchmark-wide performance"])
    (root/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
    (root/"source.sha256").write_text("".join(f'{x["sha256"]}  {x["name"]}\n' for x in cases))
    check(len(cases)>=MIN_READY,
          f"Fewer than {MIN_READY} verified size-bounded external CNFs available: {len(cases)}; see manifest")
    print("R32R_OFFICIAL_FROZEN_PASS",len(cases),"of",len(PINS),
          "originals SHA",sha(root/"manifest.json"),flush=True)

def verify_sat_witness(original,output):
    vals={}
    for line in output.splitlines():
        if line.startswith("v "):
            for word in line[2:].split():
                t=int(word)
                if t:vals[abs(t)]=t>0
    check(bool(vals),"Missing Kissat SAT witness for original CNF")
    # Original DIMACS can be tens of MiB; check one streaming clause at a time.
    nc=0;clause=[];fulfilled=False;header=False
    with open(original,encoding="ascii",errors="strict") as input:
        for raw in input:
            t=raw.strip()
            if not t or t.startswith(("c","%")):continue
            if t.startswith("p "):
                check(not header,"Duplicate CNF header")
                v=t.split();check(len(v)==4 and v[1]=="cnf","Original DIMACS invalid")
                expected=int(v[3]);header=True;continue
            check(header,"Source DIMACS missing header")
            for word in t.split():
                lit=int(word)
                if lit:
                    clause.append(lit)
                    if vals.get(abs(lit),None)==(lit>0):fulfilled=True
                else:
                    check(clause and fulfilled,"Claimed SAT model violates source clause "+str(nc))
                    nc+=1;clause=[];fulfilled=False
    check(header and not clause and nc==expected,"Original DIMACS clause count invalid")
    return True

def native_telemetry(out,mode,source):
    trace=dict(abstention=None,injected=0,root_signal=None,proof="not_needed")
    if mode=="clean":
        check("R32K_ABLATION" not in out,"Clean baseline contains native proof extension")
        return trace
    marks=re.findall(r"^c R32K_ABLATION variant=(\w+) available=(\d+) injected=(\d+) equations=(\d+) resolved=(\d+)$",
                     out,re.MULTILINE)
    if mode=="native_off":
        check(not marks,"Native OFF unexpectedly entered GF2 mode")
        return trace
    # Native may deliberately reject oversized CNF *before* logging ablation.
    if not marks:
        trace["abstention"]="guard_or_no_source_capture"
        check("R32C_INJECTED_LITS" not in out,
              "Native injection despite unavailable GF2 certificate")
        return trace
    check(len(marks)==1 and marks[0][0]=="full","Native GF2 mode mismatch")
    trace["injected"]=int(marks[0][2]);trace["root_signal"]="reported"
    signed=re.findall(r"^c R32C_INJECTED_LITS count=(\d+) lits=([0-9,-]+)$",out,re.MULTILINE)
    if trace["injected"]==0:
        check(not signed,"Unexpected root literal despite abstention")
        trace["abstention"]="no_certified_additional_units"
        return trace
    check(len(signed)==1 and int(signed[0][0])==trace["injected"],
          "Native inserted units not reported with exact signed basis")
    # Validate original-source GF2 proof independently using known R32b logic.
    import r32b_native_shadow_benchmark as b
    probes,final=b.parse_native(out)
    root=b.get_root(probes)
    proof=b.compare_root(root,source)
    check(proof["status"]=="independent_proof_match",
          "GF2 source proof failed on official original CNF")
    literal_list=[int(v) for v in signed[0][1].split(",")]
    check(len(literal_list)==trace["injected"] and
          literal_list==root["sample"][:trace["injected"]],
          "Native real-CNF root literals differ from independent exact GF2 proof")
    trace["root_signal"]=root["signal"];trace["proof"]="independently_checked"
    return trace

def r28_trace(output,source,answer):
    # Established R28 complete-parity gate either directly certifies a
    # consequence of the full original CNF or execs pinned clean Kissat.
    import r28_exact_gf2_benchmark as r28
    mark=re.findall(r"^c R28_ROUTE (\S+)(?: .*)?$",output,re.MULTILINE)
    check(len(mark)==1,"R28 must explicitly report direct algebra or plain fallback")
    route=mark[0]
    check(route in ("certified_pure_xor_sat",
       "certified_xor_contradiction","fallback"),"Unknown R28 result route")
    t=dict(route=route,certified_full_formula=False,certified_unsat=False,
           injected=0,proof="not_needed")
    if route=="certified_pure_xor_sat":
        check(answer=="SAT","Pure XOR algebra produced invalid answer status")
        m=re.search(r"^c R28_ROUTE certified_pure_xor_sat rank=(\d+) equations=(\d+) clauses=(\d+) covered=(\d+)$",
                    output,re.MULTILINE)
        check(m is not None and int(m[3])==int(m[4]) and int(m[3])>0,
              "Native pure-XOR route lacks full source coverage")
        t["certified_full_formula"]=True
        t["rank"]=int(m[1]);t["equations"]=int(m[2])
        t["proof"]="original_sat_witness_validated"
    elif route=="certified_xor_contradiction":
        check(answer=="UNSAT","Native parity contradiction not UNSAT")
        n,clauses=r28.load_clauses(source)
        check(r28.check_gf2_unsat_proof(output,clauses),
              "Original-source GF2 UNSAT certificate independently invalid")
        t["certified_unsat"]=True
        t["proof"]="original_source_parity_contradiction_independently_verified"
    return t

def trial(case,path,mode,binaries):
    env=os.environ.copy()
    env["R32B_MODE"]="r32k" if mode=="full" else "off"
    if mode=="full":env["R32K_VARIANT"]="full"
    env["R32L_TRACE"]="0"
    env["R32M_PHASES"]="0"
    if mode=="r28_exact":
        command=[str(binaries["r28"]),str(path),str(binaries["clean"])]
    else:
        binary=binaries["clean"] if mode=="clean" else binaries["native"]
        command=[str(binary),str(path)]
    began=time.monotonic()
    try:
        p=subprocess.run(command,env=env,stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,encoding="utf-8",errors="replace",timeout=CAP)
        ended=time.monotonic()
        check(p.returncode in (10,20),
              "SAT solver process failure: "+str(p.returncode)+" "+p.stderr[-500:])
        answer="SAT" if p.returncode==10 else "UNSAT"
        if answer=="SAT":verify_sat_witness(path,p.stdout)
        trace=r28_trace(p.stdout,path,answer) if mode=="r28_exact" else native_telemetry(p.stdout,mode,path)
        return dict(answer=answer,time_s=round(ended-began,6),
                    par2_s=round(ended-began,6),trace=trace)
    except subprocess.TimeoutExpired:
        ended=time.monotonic()
        return dict(answer="TIMEOUT",time_s=round(ended-began,6),
                    par2_s=CAP*2,trace=dict(abstention="timed_out",injected=0,route="timeout"))

def measure(args):
    root=Path(args.inputs);m=json.loads((root/"manifest.json").read_text())
    check(m["protocol"]==PROTO and m["timeout_seconds"]==CAP,"Frozen protocol mismatch")
    check(0<=args.shard<SHARDS,"Shard index out of range")
    if hasattr(os,"sched_getaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    binaries={x:Path(getattr(args,x)).resolve() for x in ("clean","native","r28")}
    check(all(p.is_file() for p in binaries.values()),"No original Kissat pair")
    cases=m["cases"][args.shard::SHARDS];out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    (out/"meta.json").write_text(json.dumps(dict(shard=args.shard,
        original_manifest_sha=sha(root/"manifest.json"),
        binaries={x:sha(p) for x,p in binaries.items()}),indent=2))
    rows=[]
    for case in cases:
        original=root/case["name"]
        check(sha(original)==case["sha256"],"Official source SHA changed")
        for rep in range(REPS):
            ordered=list(MODES)
            random.Random(int(hashlib.sha256((case["sha256"]+str(rep)+PROTO).encode()).hexdigest(),16)).shuffle(ordered)
            for mode in ordered:
                result=trial(case,original,mode,binaries)
                rows.append(dict(gbd=case["gbd"],index=case["index"],n=case["vars"],
                                 m=case["clauses"],repeat=rep,mode=mode,**result))
                print("R32R_TRIAL",case["gbd"],rep,mode,result["answer"],
                      result["time_s"],result["trace"],flush=True)
        (out/"rows.json").write_text(json.dumps(rows)+"\n")
    print("R32R_SHARD_PASS",args.shard,len(rows),flush=True)

def aggregate(args):
    root=Path(args.inputs)
    m=json.loads((root/"manifest.json").read_text())
    check(m["protocol"]==PROTO and len(m["cases"])>=MIN_READY,"Wrong frozen official protocol")
    rows=[];binary_keys=set()
    for shard in range(SHARDS):
        folder=Path(args.combined)/f"r32r-shard-{shard}"/"results"
        info=json.loads((folder/"meta.json").read_text())
        check(info["shard"]==shard and
              info["original_manifest_sha"]==sha(root/"manifest.json"),
              "Input archive changed during official trial")
        binary_keys.add(json.dumps(info["binaries"],sort_keys=True))
        group=json.loads((folder/"rows.json").read_text())
        check(len(group)==len(m["cases"][shard::SHARDS])*REPS*len(MODES),
              "Official benchmark has incomplete paired trial rows")
        rows.extend(group)
    check(len(binary_keys)==1 and len(rows)==len(m["cases"])*REPS*len(MODES),
          "Incomplete official trial count or different solver sources")
    percase=[]
    for case in m["cases"]:
        group=[x for x in rows if x["gbd"]==case["gbd"]]
        check(len(group)==REPS*len(MODES),"Per-original trial missing")
        for rep in range(REPS):
            sample=[r for r in group if r["repeat"]==rep]
            check({r["mode"] for r in sample}==set(MODES),"Unpaired solver measurements")
            answers={r["answer"] for r in sample}-{"TIMEOUT"}
            check(len(answers)<=1,"Official CNF result contradiction")
        pol={}
        for mode in MODES:
            subset=[x for x in group if x["mode"]==mode]
            pol[mode]=dict(median_s=round(statistics.median(x["par2_s"] for x in subset),6),
               sum_PAR2_s=round(sum(x["par2_s"] for x in subset),6),
               answer=subset[-1]["answer"],
               timeout_attempts=sum(x["answer"]=="TIMEOUT" for x in subset),
               GF2_injected=max(x["trace"].get("injected",0) for x in subset),
               R28_routes=dict(collections.Counter(x["trace"].get("route","-") for x in subset)))
        percase.append(dict(index=case["index"],gbd=case["gbd"],
                     vars=case["vars"],clauses=case["clauses"],
                     bytes=case["bytes"],policies=pol))
    summary={}
    for mode in MODES:
        attempt=[x for x in rows if x["mode"]==mode]
        summary[mode]=dict(sum_PAR2_s=round(sum(x["par2_s"] for x in attempt),6),
            solved_attempts=sum(x["answer"]!="TIMEOUT" for x in attempt),
            solved_sources=sum(all(x["answer"]!="TIMEOUT" for x in attempt
                    if x["gbd"]==c["gbd"]) for c in m["cases"]),
            timeouts=sum(x["answer"]=="TIMEOUT" for x in attempt),
            active_GF2_injection_trials=sum(x["trace"].get("injected",0)>0 for x in attempt),
            exact_XOR_direct_solved=sum(x["trace"].get("route","") in
                  ("certified_pure_xor_sat","certified_xor_contradiction") for x in attempt),
            routes=dict(collections.Counter(x["trace"].get("route","-") for x in attempt)))
    data=dict(protocol=PROTO,external_source=m["source_list"],
          original_attempts=len(PINS),downloaded_originals=len(m["cases"]),
          source_exclusions=[x for x in m["complete_download_log"] if x["status"]!="READY"],
          summary=summary,per_case=percase,rows=rows,limitations=m["limitations"])
    Path(args.output).write_text(json.dumps(data,indent=2)+"\n")
    lines=["# DRNAS SAT R32r — prospective 2026 official CNFs, exact GF2 versus pinned Kissat",
      "Main 2026 canonical GBD URI list: 23 fixed unseen-in-R32p candidate IDs, "
        +str(len(m["cases"]))+" verified and size-qualified sources.",
      "One solver per attempt, 30s cap, 60s PAR2, two randomized repeats.",
      "Four modes: clean pinned Kissat; instrumented native OFF;",
      "R32n certified root-unit insertion; R28 full exact XOR with pinned Kissat fallback.",
      "R28 is established XOR Gaussian elimination, not a new complexity-theoretic method.",
      "Every original SAT answer independently checked against all DIMACS clauses.",
      "Direct XOR UNSAT answers need complete clause-based GF2 independent certificates.",
      "No synthetic cases; no winner-only selection; not the competition hardware or cutoff.",
      "Precommitted candidate failures are all recorded, not substituted.",
      "",
      "| Mode | Solved sources | Solved attempts | PAR2 total s | Exact GF2 direct solves | Root injected attempts |",
      "|---|---:|---:|---:|---:|---:|"]
    for mode in MODES:
        x=summary[mode]
        lines.append(f'| {mode} | {x["solved_sources"]}/{len(m["cases"])} | {x["solved_attempts"]}/{len(m["cases"])*REPS} | {x["sum_PAR2_s"]:.4f} | {x["exact_XOR_direct_solved"]} | {x["active_GF2_injection_trials"]} |')
    lines+=["","## Individual official original results — seconds",
        "| GBD ID | Variables | Clauses | Clean s (median PAR2) | Native OFF s | DRNAS R32n s | Exact GF2 R28 s | Exact R28 route |",
        "|---|---:|---:|---:|---:|---:|---:|---|"]
    for c in percase:
        modes=c["policies"]
        r28r=str(modes["r28_exact"]["R28_routes"])
        lines.append(f'| {c["gbd"]} | {c["vars"]} | {c["clauses"]} | {modes["clean"]["median_s"]:.4f} | {modes["native_off"]["median_s"]:.4f} | {modes["full"]["median_s"]:.4f} | {modes["r28_exact"]["median_s"]:.4f} | {r28r} |')
    lines+=["","## Unavailable / size-excluded official instances"]
    for c in data["source_exclusions"]:
        lines.append(f'- List position {c["index"]} GBD {c["gbd"]}: {c["reason"]}')
    lines+=["","## Interpretation and caveats",
      "Timeout is right-censored at 30s, PAR2 penalty 60s.",
      "If R28 took fallback, observed differences are overhead and runner noise,",
      "not claimed as a full-GF2 algorithmic speedup.",
      "If R32n inserted no original-certified literals, it made no XOR intervention.",
      "The absence of exact GF2 in a source does NOT imply lack of hidden XOR;",
      "the R28 complete block recognizer is deliberately conservative.",
      "No general competition leaderboard claim, P=NP claim or universal gain."]
    Path(args.report).write_text("\n".join(lines)+"\n")
    print("R32R_REAL_OFFICIAL_AUDIT_PASS",len(m["cases"]),"original CNFs",len(rows),"attempts",
          json.dumps(summary,sort_keys=True),flush=True)

def main():
    parser=argparse.ArgumentParser()
    sub=parser.add_subparsers(dest="cmd",required=True)
    q=sub.add_parser("freeze");q.add_argument("--out",required=True)
    q=sub.add_parser("measure")
    for name in ("inputs","clean","native","r28","out"):q.add_argument("--"+name,required=True)
    q.add_argument("--shard",type=int,required=True)
    q=sub.add_parser("aggregate")
    for name in ("inputs","combined","output","report"):q.add_argument("--"+name,required=True)
    a=parser.parse_args()
    if a.cmd=="freeze":freeze(a.out)
    elif a.cmd=="measure":measure(a)
    else:aggregate(a)
if __name__=="__main__":main()
