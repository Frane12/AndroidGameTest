#!/usr/bin/env python3
"""R65x-Live V2 controlled replay: same 2025 CNFs and identical binary pins.

Compare V1 native 1600-eq cap and V2 native 4096-eq cap with the same CDCL
reason pathway; compare fixed16 vs feedback-gated adaptive in both versions.
Source selection: 4 preexisting exact-XOR positives and 2 short controls,
all from the R85 frozen 2025 SHA manifest. REPLAY, not blind holdout.
"""
from __future__ import annotations
import argparse,collections,hashlib,json,os,random,subprocess
from pathlib import Path
import r65xl_live_trial as parent

PROTO="DRNAS-R65XLV2-2025-4096-EQ-REPLAY-V1"
SHARDS=(1,2,5,7,8,9)
REPS=2
MODES=("clean_default","clean_compatible",
       "v1_fixed16","v1_adaptive","v2_fixed16","v2_adaptive")
NATIVE_MAP={
  "v1_fixed16":("v1","gf2_live_fixed16"),
  "v1_adaptive":("v1","gf2_live_adaptive"),
  "v2_fixed16":("v2","gf2_live_fixed16"),
  "v2_adaptive":("v2","gf2_live_adaptive")}

def ck(ok,why):
    if not ok:raise RuntimeError("R65XLV2_FAIL_CLOSED "+str(why))

def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def write(path,content):
    Path(path).write_text(json.dumps(content,indent=2,sort_keys=True)+"\n")

def prepare_bin(root):
    old=root/"old";new=root/"new"
    clean=old/"clean";v1=old/"native-r65xl";v2=new/"native-r65xl-v2"
    for p in (clean,v1,v2):
        ck(p.is_file() and os.access(p,os.X_OK),"missing executable "+str(p))
    ck(subprocess.run(["sha256sum","-c","r65xl-binaries.sha256"],cwd=old,
          capture_output=True).returncode==0,"original V1 frozen binary checksum changed")
    ck(subprocess.run(["sha256sum","-c","r65xl-v2-binaries.sha256"],cwd=new,
          capture_output=True).returncode==0,"V2 compiled binary checksum changed")
    return clean,{"v1":v1,"v2":v2}

def measure(a):
    root=Path(a.sources).resolve()
    spec=parent.validate_manifest(root)
    ck(a.shard in SHARDS,"not an eligible four-XOR/two-control shard")
    case=spec["cases"][a.shard]
    group="xor_exact" if case["structural_xor_positive"] else "control"
    ck(group==("control" if a.shard in (5,7) else "xor_exact"),
       "source structural grouping drift")
    source=(root/case["filename"]).resolve()
    clean,binmap=prepare_bin(Path(a.compiled).resolve())
    if hasattr(os,"sched_setaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    caches={"v1":{},"v2":{}}
    rows=[]
    for rep in range(REPS):
        order=list(MODES)
        seed=int(hashlib.sha256((PROTO+case["sha256"]+str(rep)).encode()).hexdigest(),16)
        random.Random(seed).shuffle(order)
        for mode in order:
            if mode.startswith("clean_"):
                label=mode;binary=binmap["v1"];cache=caches["v1"]
            else:
                version,label=NATIVE_MAP[mode]
                binary=binmap[version]
                cache=caches[version]
            result=parent.run_one(source,label,clean,binary,cache)
            item=dict(gbd=case["gbd"],sha256=case["sha256"],
                      exact_blocks=case["complete_blocks"],group=group,
                      mode=mode,rep=rep,**result)
            rows.append(item)
            write(out/"results.json",dict(protocol=PROTO,source_manifest_sha=digest(root/"manifest.json"),
                  shard=a.shard, binaries=dict(clean=digest(clean),
                      native_v1=digest(binmap["v1"]),native_v2=digest(binmap["v2"])),
                  rows=rows))
            live=(result.get("live") or {}).get("last") or {}
            gate=result.get("source_gate") or {}
            print("R65XLV2_TRIAL",json.dumps(dict(
               gbd=case["gbd"],group=group,mode=mode,rep=rep,
               status=result["answer"],sec=result["wall_s"],par2=result["par2_s"],
               rows=live.get("rows",0),attached=live.get("xor_to_cdcl_reasons",0),
               uip=live.get("cdcl_first_uip_uses",0),
               checked=live.get("trail_row_checks",0),interval=live.get("interval",0),
               gate=gate),sort_keys=True),flush=True)
    ck(len(rows)==REPS*len(MODES),"incomplete shard")
    print("R65XLV2_SHARD_PASS",a.shard,len(rows),flush=True)

def audit(a):
    root=Path(a.sources).resolve()
    spec=parent.validate_manifest(root)
    rows=[];pin=set()
    for sh in SHARDS:
        file=Path(a.combined)/f"r65xlv2-shard-{sh}"/"results"/"results.json"
        ck(file.is_file(),"missing paired completed shard "+str(sh))
        data=json.loads(file.read_text())
        ck(data["protocol"]==PROTO and
           data["source_manifest_sha"]==digest(root/"manifest.json") and
           data["shard"]==sh,"source SHA changed")
        pin.add(json.dumps(data["binaries"],sort_keys=True))
        block=data["rows"]
        case=spec["cases"][sh]
        ck(len(block)==REPS*len(MODES),"missing complete trials")
        for rep in range(REPS):
            trial=[x for x in block if x["rep"]==rep]
            ck(len(trial)==len(MODES) and {x["mode"] for x in trial}==set(MODES),
               "incomplete trial arms")
            ck(all(x["sha256"]==case["sha256"] for x in trial),"formula SHA drift")
            answers={x["answer"] for x in trial if x["answer"]!="TIMEOUT"}
            ck(len(answers)<=1,"inconsistent SAT/UNSAT claim")
        rows.extend(block)
    ck(len(pin)==1 and len(rows)==len(SHARDS)*REPS*len(MODES),
       "binary pin drift/incomplete paired measurements")
    groups={}
    for group in ("ALL","xor_exact","control"):
        chosen=[r for r in rows if group=="ALL" or r["group"]==group]
        stats={}
        for mode in MODES:
            sample=[r for r in chosen if r["mode"]==mode]
            live=[((x.get("live") or {}).get("last") or {}) for x in sample]
            gate=[x.get("source_gate") or {} for x in sample]
            stats[mode]=dict(trials=len(sample),
               solved=sum(x["answer"]!="TIMEOUT" for x in sample),
               par2_s=round(sum(x["par2_s"] for x in sample),6),
               avg_rows=round(sum(x.get("rows",0) for x in live)/len(sample),2),
               checks=sum(x.get("trail_row_checks",0) for x in live),
               reasons=sum(x.get("xor_to_cdcl_reasons",0) for x in live),
               uip=sum(x.get("cdcl_first_uip_uses",0) for x in live),
               source_gate_eq=[x.get("observed_equations",None) for x in gate
                               if x.get("observed_equations") is not None])
        groups[group]=stats
    report=dict(protocol=PROTO,status="PASS_2025_REPLAY",
       source_sha=digest(root/"manifest.json"),
       cases=len(SHARDS),trials=len(rows),groups=groups,
       limitations=[
          "R85 SAT Competition 2025 original source replay; not new unseen official holdout",
          "Four structurally exact XOR positives, two negative controls; biased sample",
          "V1 vs V2 change includes larger source equation cap AND adaptive cost-policy change",
          "Compare fixed16 V1 vs V2 to isolate capacity, adaptive V1 vs V2 as combined change",
          "Native source-certified GF2 rows and SAT witnesses verified; UNSAT lacks external LRAT proof",
          "One CPU per attempt, 30s wall cap, PAR2=60s timeout; default clean can preprocess",
          "No claim to faster solving when both variants time out",
          "No concurrent multi-process worker communication; this is in-process CDCL trail<->GF2"])
    write(a.json,report)
    lines=["# R65x-Live V2 — safe 4096-source-equation window / adaptive cost budget",
           "", "R85 SHA-frozen SAT2025: four exact XOR positives + two non-XOR controls;",
           "two repeats, 30s total wall cap, one CPU; 72 paired attempts.",
           "**Exploratory replay, not source-blind confirmation.**",
           "", "| Group | Arm | Solved | PAR2 (s) | Avg rows | Trail checks | XOR reasons | First UIP |",
           "|---|---|---:|---:|---:|---:|---:|---:|"]
    for grp,vals in groups.items():
        for mode,x in vals.items():
            lines.append(f"| {grp} | {mode} | {x['solved']}/{x['trials']} | "+
                f"{x['par2_s']:.3f} | {x['avg_rows']:.2f} | "+
                f"{x['checks']} | {x['reasons']} | {x['uip']} |")
    lines+=["","## Limitations"]+["- "+x for x in report["limitations"]]
    Path(a.md).write_text("\n".join(lines)+"\n")
    print("R65XLV2_FULL_AUDIT_PASS",json.dumps(groups,sort_keys=True),flush=True)

def main():
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest="cmd",required=True)
    q=sub.add_parser("measure")
    q.add_argument("--sources",required=True)
    q.add_argument("--compiled",required=True)
    q.add_argument("--shard",type=int,required=True)
    q.add_argument("--out",required=True)
    q=sub.add_parser("audit")
    for k in ("sources","combined","json","md"):q.add_argument("--"+k,required=True)
    args=p.parse_args()
    if args.cmd=="measure":measure(args)
    else:audit(args)

if __name__=="__main__":main()
