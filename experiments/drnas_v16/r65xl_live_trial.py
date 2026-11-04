#!/usr/bin/env python3
"""R65x-Live: source-pinned 2025 real SAT paired native trail<->GF2 causal test.

Modes: clean_default; clean_compatible; source-GF2 passive; native live fixed;
native live adaptive. All native and clean_compatible use identical no-preprocess
flags and one CPU. Each native source parity row is independently re-proven by
existing R85 source-proof audit. SAT witness verified against unchanged original.
UNSAT is *not* externally LRAT-certified. Already used R85 2025 source set:
development replay, NEVER claim source-blind world result.
"""
from __future__ import annotations
import argparse,collections,hashlib,json,os,random,re,subprocess,time
from pathlib import Path
import r85_fresh_abcd as r85
import r32p_real_satcomp26_benchmark as r32p

PROTO="DRNAS-R65XL-NATIVE-TRAIL-REASON-2025-V1"
SHARDS=12
REPS=2
CAP=30.0
MODES=("clean_default","clean_compatible","gf2_passive16",
       "gf2_live_fixed16","gf2_live_adaptive")
FLAGS=("--no-luckyearly","--no-luckylate","--no-preprocess")
LIVE=re.compile(r"^c R65XL_LIVE (.+)$",re.M)

def ck(test,why):
    if not test:raise RuntimeError("R65XL_FAIL_CLOSED "+str(why))

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def save(path,d):
    Path(path).write_text(json.dumps(d,indent=2,sort_keys=True)+"\n")

def validate_manifest(root):
    mf=json.loads((root/"manifest.json").read_text())
    ck(mf["protocol"]==r85.PROTO and len(mf["cases"])==SHARDS,
       "expected R85 frozen 2025 sources")
    ck(sum(c["structural_xor_positive"] for c in mf["cases"])==4,
       "missing exact XOR source group")
    ck(len({c["sha256"] for c in mf["cases"]})==SHARDS,
       "duplicate source SHA")
    for c in mf["cases"]:
        ck(c["year"]==2025 and digest(root/c["filename"])==c["sha256"],
           "wrong year or source SHA")
    return mf

def parse_live(stdout,mode):
    items=[]
    for line in LIVE.findall(stdout):
        data={}
        for word in line.split():
            if "=" not in word:continue
            k,v=word.split("=",1)
            data[k]=float(v) if k=="cpu_ms" else int(v)
        items.append(data)
    ck(bool(items),"missing live CDCL/XOR stats")
    for a,b in zip(items,items[1:]):
        for field in ("trail_row_checks","xor_candidates","xor_to_cdcl_reasons",
                      "cdcl_first_uip_uses","scans","decisions","conflicts"):
            ck(a[field]<=b[field],"regressed live telemetry "+field)
    last=items[-1]
    ck(last["xor_to_cdcl_reasons"]<=last["xor_candidates"],
       "reason without actual certified live implication")
    if mode=="gf2_passive16":
        ck(last["xor_to_cdcl_reasons"]==0 and last["cdcl_first_uip_uses"]==0,
           "passive accidentally attached reason")
    ck(last["adaptive"]==int(mode=="gf2_live_adaptive"),
       "live mode flag missing")
    return dict(last=last,snapshots=len(items))

def run_one(source,mode,clean,native,cache):
    start=time.monotonic()
    env=os.environ.copy()
    default=(mode=="clean_default")
    clean_mode=mode.startswith("clean_")
    if not clean_mode:
        env.update(R32B_MODE="r32u",
                   R32U_ACTIVE="0" if mode=="gf2_passive16" else "1",
                   R84_SCAN_EVERY="16",R85_DIVERSE="0",R85_CAP="64",
                   R65XL_POLICY="adaptive" if mode=="gf2_live_adaptive" else "fixed",
                   R32S_PASSIVE_TRACE="0")
    binary=clean if clean_mode else native
    args=[str(binary)]+([] if default else list(FLAGS))+[str(source)]
    try:
        res=subprocess.run(args,env=env,capture_output=True,
                           text=True,errors="replace",timeout=CAP)
        ck(res.returncode in (10,20),
           "bad solver exit "+str(res.returncode)+" "+res.stderr[-400:])
        answer="SAT" if res.returncode==10 else "UNSAT"
        stdout=res.stdout
    except subprocess.TimeoutExpired as e:
        answer="TIMEOUT"
        stdout=e.stdout or b""
        if isinstance(stdout,bytes):stdout=stdout.decode(errors="replace")
    elapsed=time.monotonic()-start
    if answer=="SAT":
        r32p.verify_sat_witness(source,stdout)
    tel=None;live=None
    if not clean_mode:
        # R85 performs independent original-source GF2 proof validation
        # and verifies every native reason/telemetry invariant.
        mapped="A_passive16" if mode=="gf2_passive16" else "B_active16"
        tel=r85.parse_counts(stdout,mapped,source,cache)
        live=parse_live(stdout,mode)
        ck(tel["last"]["attached"]==live["last"]["xor_to_cdcl_reasons"],
           "native and live attached counters disagree")
        ck(tel["last"]["first_uip_reason_uses"]==
           live["last"]["cdcl_first_uip_uses"],
           "native and live UIP counters disagree")
    gate_match=re.search(r"^c R65XLV2_SOURCE_GATE (.+)$",stdout,re.M)
    source_gate=None
    if gate_match:
        source_gate={}
        for item in gate_match.group(1).split():
            if "=" in item:
                key,value=item.split("=",1)
                source_gate[key]=int(value)
    result=dict(answer=answer if elapsed<=CAP else "TIMEOUT",
                wall_s=round(min(elapsed,CAP),6),
                par2_s=round(elapsed if answer!="TIMEOUT" and elapsed<=CAP
                             else 2*CAP,6),
                sat_witness_checked=answer=="SAT",
                unsat_external_proof_checked=False,
                solver="clean" if clean_mode else "native-r65xl",
                prep_preserved=not default,telemetry=tel,live=live,
                source_gate=source_gate)
    return result

def measure(args):
    root=Path(args.sources).resolve()
    mf=validate_manifest(root)
    ck(0<=args.shard<SHARDS,"invalid shard")
    case=mf["cases"][args.shard]
    source=root/case["filename"]
    compiled=Path(args.compiled).resolve()
    clean=compiled/"clean"
    native=compiled/"native-r65xl"
    ck(clean.is_file() and native.is_file(),"missing pinned binaries")
    ck(subprocess.run(["sha256sum","-c","r65xl-binaries.sha256"],cwd=compiled,
       capture_output=True).returncode==0,"binary SHA mismatch")
    if hasattr(os,"sched_setaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    out=Path(args.out)
    out.mkdir(parents=True,exist_ok=True)
    cache={};rows=[]
    for rep in range(REPS):
        modes=list(MODES)
        seed=int(hashlib.sha256((PROTO+case["sha256"]+str(rep)).encode()).hexdigest(),16)
        random.Random(seed).shuffle(modes)
        for mode in modes:
            result=run_one(source,mode,clean,native,cache)
            row=dict(gbd=case["gbd"],source_sha=case["sha256"],
                     group="xor_exact" if case["structural_xor_positive"] else "control",
                     exact_blocks=case["complete_blocks"],rep=rep,mode=mode,**result)
            rows.append(row)
            save(out/"results.json",dict(protocol=PROTO,shard=args.shard,
               original_manifest_sha=digest(root/"manifest.json"),
               binaries={"clean":digest(clean),"native":digest(native)},
               rows=rows))
            last=(result["live"] or {}).get("last") or {}
            print("R65XL_TRIAL",json.dumps(dict(gbd=case["gbd"],rep=rep,mode=mode,
                 answer=result["answer"],par2_s=result["par2_s"],
                 wall_s=result["wall_s"],
                 source_rows=last.get("rows",0),
                 trail_checks=last.get("trail_row_checks",0),
                 xor_reasons=last.get("xor_to_cdcl_reasons",0),
                 cdcl_uip_uses=last.get("cdcl_first_uip_uses",0),
                 scan_interval=last.get("interval",0))),flush=True)
    ck(len(rows)==REPS*len(MODES),"incomplete shard")
    print("R65XL_SHARD_PASS",args.shard,len(rows),flush=True)

def audit(args):
    root=Path(args.sources).resolve()
    mf=validate_manifest(root)
    rows=[];pins=set()
    for idx,case in enumerate(mf["cases"]):
        file=Path(args.combined)/f"r65xl-shard-{idx}"/"results"/"results.json"
        ck(file.is_file(),"missing native shard "+str(idx))
        obj=json.loads(file.read_text())
        ck(obj["protocol"]==PROTO and obj["shard"]==idx and
           obj["original_manifest_sha"]==digest(root/"manifest.json"),
           "wrong source or cohort")
        pins.add(json.dumps(obj["binaries"],sort_keys=True))
        rr=obj["rows"]
        ck(len(rr)==REPS*len(MODES),"missing paired trials")
        for rep in range(REPS):
            rr2=[r for r in rr if r["rep"]==rep]
            ck(len(rr2)==len(MODES) and {r["mode"] for r in rr2}==set(MODES),
               "unpaired modes")
            ck(all(r["source_sha"]==case["sha256"] for r in rr2),
               "original source mismatch")
            verdicts={r["answer"] for r in rr2 if r["answer"]!="TIMEOUT"}
            ck(len(verdicts)<=1,"disagreeing SAT/UNSAT verdicts")
        rows.extend(rr)
    ck(len(pins)==1 and len(rows)==SHARDS*REPS*len(MODES),
       "binary drift or missing trials")
    groups={}
    for group in ("ALL","xor_exact","control"):
        selected=[r for r in rows if group=="ALL" or r["group"]==group]
        groups[group]={}
        for mode in MODES:
            rr=[r for r in selected if r["mode"]==mode]
            last=[(r.get("live") or {}).get("last") or {} for r in rr]
            groups[group][mode]=dict(trials=len(rr),
                solved=sum(r["answer"]!="TIMEOUT" for r in rr),
                par2_s=round(sum(r["par2_s"] for r in rr),6),
                trail_row_checks=sum(x.get("trail_row_checks",0) for x in last),
                xor_to_cdcl_reasons=sum(x.get("xor_to_cdcl_reasons",0) for x in last),
                cdcl_first_uip_uses=sum(x.get("cdcl_first_uip_uses",0) for x in last))
    per_formula=[]
    for case in mf["cases"]:
        rr=[r for r in rows if r["source_sha"]==case["sha256"]]
        per_formula.append(dict(gbd=case["gbd"],source_sha=case["sha256"],
            exact_blocks=case["complete_blocks"],
            group="xor_exact" if case["structural_xor_positive"] else "control",
            par2={m:round(sum(r["par2_s"] for r in rr if r["mode"]==m),6)
                  for m in MODES},
            live_uip={m:sum(((r.get("live") or {}).get("last") or {}).get(
                "cdcl_first_uip_uses",0) for r in rr if r["mode"]==m)
                for m in MODES}))
    report=dict(protocol=PROTO,status="PASS_DEVELOPMENT_REPLAY",
         cases=SHARDS,trials=len(rows),groups=groups,per_formula=per_formula,
         one_cpu_per_run=True,source_manifest_sha=digest(root/"manifest.json"),
         binary_pins=json.loads(next(iter(pins))),
         limitations=[
           "2025 R85 original CNFs were previously benchmarked: NOT blind holdout",
           "Native in-process CDCL trail->GF2->certified CNF reason; no inter-process learnt-clause exchange",
           "Only source-proved bounded short XOR equations, no learnt-XOR algebra from arbitrary CDCL clauses",
           "Default clean Kissat may preprocess and is not directly controlled against no-preprocess native",
           "The correct controlled comparison is clean_compatible/passive16/fixed16/adaptive, all no-preprocess",
           "SAT witnesses validated against original CNF, UNSAT requires independent LRAT verification",
           "Native row proofs checked against original CNF; first-UIP nonbinary reason uses are lower bounds",
           "Four XOR positives selected structurally, eight negatives; small, non-representative sample"])
    save(args.json,report)
    lines=["# R65x-Live — native in-search two-way CDCL/GF(2) propagation",
           "", "12 SHA-frozen SAT Competition 2025 originals, 4 exact XOR / 8 controls;",
           "2 repeats, 30s cap, PAR2=60s timeout, one pinned CPU.",
           "**Development replay, not source-blind holdout.**",
           "", "| Group | Mode | Solved | PAR2 s | CDCL trail checks | GF2 to CDCL reasons | First-UIP uses |",
           "|---|---|---:|---:|---:|---:|---:|"]
    for group,arms in groups.items():
        for mode,x in arms.items():
            lines.append(f"| {group} | {mode} | {x['solved']}/{x['trials']} | {x['par2_s']:.3f} | "+
              f"{x['trail_row_checks']} | {x['xor_to_cdcl_reasons']} | {x['cdcl_first_uip_uses']} |")
    lines+=["","## Individual original SHA formula metrics",
            "| GBD prefix | Group | XOR blocks | Default Kissat | Compatible clean | Fixed live | Adaptive live | UIP adaptive |",
            "|---|---|---:|---:|---:|---:|---:|---:|"]
    for x in per_formula:
        p=x["par2"]
        lines.append(f"| {x['gbd'][:12]} | {x['group']} | {x['exact_blocks']} | "+
            f"{p['clean_default']:.3f} | {p['clean_compatible']:.3f} | "+
            f"{p['gf2_live_fixed16']:.3f} | {p['gf2_live_adaptive']:.3f} | "+
            str(x["live_uip"]["gf2_live_adaptive"])+" |")
    lines+=["","## Limitations"]+["- "+v for v in report["limitations"]]
    Path(args.md).write_text("\n".join(lines)+"\n")
    print("R65XL_FINAL_AUDIT_PASS",json.dumps(groups["ALL"],sort_keys=True),flush=True)

def main():
    p=argparse.ArgumentParser()
    sub=p.add_subparsers(dest="cmd",required=True)
    a=sub.add_parser("measure")
    a.add_argument("--sources",required=True)
    a.add_argument("--compiled",required=True)
    a.add_argument("--shard",type=int,required=True)
    a.add_argument("--out",required=True)
    a=sub.add_parser("audit")
    a.add_argument("--sources",required=True)
    a.add_argument("--combined",required=True)
    a.add_argument("--json",required=True)
    a.add_argument("--md",required=True)
    opt=p.parse_args()
    if opt.cmd=="measure":measure(opt)
    else:audit(opt)

if __name__=="__main__":
    main()
