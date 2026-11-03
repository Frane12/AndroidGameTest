#!/usr/bin/env python3
"""R32t: original real SATComp26 CNFs, exact certified partial XOR promotion.
This is an exploratory cross-solver diagnostic, NOT a DRNAS/Kissat GF2 integration.
For each original formula compare native Kissat, DRNAS Full, CryptoMiniSat plain
and CryptoMiniSat with *redundant implied* explicitly recovered XOR clauses.
No clause is removed; a full 2^(k-1) falsifying-assignment block independently
certifies each parity implication. No partial-pattern guesses. No winner claim
from right-censored timeouts or a single timing repetition.
"""
from __future__ import annotations
import argparse,collections,hashlib,json,os,random,re,subprocess,time
from pathlib import Path
import r32r_more_real_satcomp26_benchmark as old

PROTO="DRNAS-R32T-EXPLICIT-PARTIAL-XOR-REAL2026-20261103-v1"
CAP=75.0
IDS=(
    "284dec9d0d0404c8b80d8bd8064e4c68", # sparse parity control
    "7db30d12cb06f0dc2f30abff80d96d6a", # high parity coverage
    "b76b9699c2deb74dd9b4a99a05179acd", # mixed parity
    "e305def35c314eec8266087e89a9ab46", # solved SAT negative control
    "727ebce936c010888c7f71f00885e643", # non-parity control
)
MODES=("kissat_clean","drnas_full","cms_plain","cms_xor")

def check(cond, msg):
    if not cond: raise RuntimeError("R32T_AUDIT_FAIL "+str(msg))
def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def load_cnf(path):
    n=m=None; clauses=[]; pending=[]
    with open(path,encoding="ascii",errors="strict") as source:
        for line in source:
            strip=line.strip()
            if not strip or strip[0] in "c%":continue
            if strip.startswith("p "):
                check(n is None,"multiple headers")
                fields=strip.split()
                check(len(fields)==4 and fields[1]=="cnf","bad CNF header")
                n=int(fields[2]);m=int(fields[3]);continue
            check(n is not None,"missing header")
            for token in strip.split():
                v=int(token)
                if v:
                    check(0<abs(v)<=n,"out-of-range variable")
                    pending.append(v)
                else:
                    check(bool(pending),"empty clause unsupported by this experiment")
                    clauses.append(tuple(pending));pending=[]
    check(not pending and n is not None and len(clauses)==m,"CNF count")
    return n,clauses

def recover_complete_parities(clauses):
    """Exact local CNF proof: 2^(k-1) forbidden assignments all share parity.
    Equivalence: the recovered XOR is implied by the original unchanged clauses.
    """
    groups=collections.defaultdict(set)
    for clause in clauses:
        k=len(clause)
        if not 2<=k<=5:continue
        key=tuple(sorted(set(abs(lit) for lit in clause)))
        if len(key)!=k:continue
        signs={abs(lit):lit<0 for lit in clause}
        forbidden=sum((1<<i) for i,var in enumerate(key) if signs[var])
        groups[key].add(forbidden)
    certified=[]
    for key,forbidden in groups.items():
        k=len(key)
        if len(forbidden)!=(1<<(k-1)):continue
        parity={mask.bit_count()&1 for mask in forbidden}
        if len(parity)!=1:continue
        forbidden_parity=next(iter(parity))
        expected={mask for mask in range(1<<k) if mask.bit_count()%2==forbidden_parity}
        check(forbidden==expected,"bad complete local parity certificate")
        rhs=1-forbidden_parity
        certified.append((key,rhs))
    return sorted(certified)

def prepare(source,folder,clauses,n):
    folder.mkdir(parents=True,exist_ok=True)
    plain=folder/"original-normalized.cnf"
    enriched=folder/"original-plus-certified-xor.cnf"
    certified=recover_complete_parities(clauses) if len(clauses)<=100000 else []
    lines=[(" ".join(map(str,c))+" 0\n") for c in clauses]
    plain.write_text(f"p cnf {n} {len(clauses)}\n"+"".join(lines),encoding="ascii")
    extra=[]
    for variables,rhs in certified:
        lits=list(variables)
        if rhs==0:lits[0]=-lits[0]
        extra.append("x"+" ".join(map(str,lits))+" 0\n")
    enriched.write_text(f"p cnf {n} {len(clauses)+len(extra)}\n"+"".join(lines)+"".join(extra),encoding="ascii")
    check(len(certified)==len(extra),"bad XOR output count")
    covered=set()
    for variables,rhs in certified:
        covered.add(tuple(variables))
    covered_clauses=sum(1 for c in clauses
        if len(c) in (2,3,4,5) and
        tuple(sorted(set(abs(v) for v in c))) in covered)
    return dict(plain=plain,enriched=enriched,
        xor_equations=len(certified),
        covered_clauses=covered_clauses,
        covered_pct=round(covered_clauses*100/len(clauses),4),
        equations_sha256=hashlib.sha256(repr(certified).encode()).hexdigest(),
        classification_guard=len(clauses)>100000,
        normalized_sha256=sha(plain),enhanced_sha256=sha(enriched))

def execute(mode,original,profile,clean,native,cms):
    env=os.environ.copy()
    env["R32S_PASSIVE_TRACE"]="0"
    env["R32B_MODE"]="r32k" if mode=="drnas_full" else "off"
    env["R32K_VARIANT"]="full"
    if mode=="kissat_clean":cmd=[str(clean),str(original)]
    elif mode=="drnas_full":cmd=[str(native),str(original)]
    else:
        inp=profile["plain"] if mode=="cms_plain" else profile["enriched"]
        cmd=[str(cms),"--threads","1","--verb","0",str(inp)]
    started=time.monotonic()
    try:
        p=subprocess.run(cmd,capture_output=True,text=True,errors="replace",
            env=env,timeout=CAP)
    except subprocess.TimeoutExpired:
        return dict(status="TIMEOUT",wall_s=round(time.monotonic()-started,6),
            par2_s=2*CAP,verified=False,returncode=None)
    elapsed=time.monotonic()-started
    sat=bool(re.search(r"(?m)^s SATISFIABLE\s*$",p.stdout))
    unsat=bool(re.search(r"(?m)^s UNSATISFIABLE\s*$",p.stdout))
    check(sat!=unsat,f"missing or contradictory SAT verdict {mode}, code={p.returncode}, tail={p.stdout[-250:]!r} stderr={p.stderr[-200:]!r}")
    check(p.returncode in ((0,10) if sat else (0,20)),f"invalid solver exit status {mode} {p.returncode}")
    answer="SAT" if sat else "UNSAT"
    if sat:old.verify_sat_witness(original,p.stdout)
    if mode=="drnas_full":
        telemetry=old.native_telemetry(p.stdout,"full",original)
        check(telemetry["injected"]==0,"Unexpected DRNAS root injection: examine independently")
    return dict(status=answer,wall_s=round(elapsed,6),par2_s=round(elapsed,6),
        verified=sat,returncode=p.returncode)

def measure(args):
    root=Path(args.frozen)
    manifest=json.loads((root/"manifest.json").read_text())
    check(manifest["protocol"]==old.PROTO,"unexpected R32r source manifest")
    cases={c["gbd"]:c for c in manifest["cases"]}
    check(all(g in cases for g in IDS),"missing one of five precommitted real originals")
    check(0<=args.index<len(IDS),"invalid shard")
    if hasattr(os,"sched_getaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    gbd=IDS[args.index];case=cases[gbd]
    src=(root/case["name"]).resolve()
    check(sha(src)==case["sha256"],"official original SHA mismatch")
    n,clauses=load_cnf(src)
    check(n==case["vars"] and len(clauses)==case["clauses"],"official dimensional mismatch")
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    profile=prepare(src,out/"inputs",clauses,n)
    print("R32T_STRUCTURE",gbd,json.dumps({k:v for k,v in profile.items()
        if not isinstance(v,Path)},sort_keys=True),flush=True)
    clean=Path(args.clean).resolve()
    native=Path(args.native).resolve()
    cms=Path(args.cms).resolve()
    check(all(p.is_file() for p in (clean,native,cms)),"missing pinned binary")
    check(sha(clean)==args.clean_sha and sha(native)==args.native_sha,
        "pinned Kissat binary mismatch")
    rows=[]
    order=list(MODES)
    random.Random(320203308361+args.index).shuffle(order)
    for mode in order:
        result=execute(mode,src,profile,clean,native,cms)
        row=dict(gbd=gbd,mode=mode,**result)
        rows.append(row)
        (out/"rows.json").write_text(json.dumps(rows,indent=2)+"\n")
        print("R32T_TRIAL",json.dumps(row,sort_keys=True),flush=True)
    answers={x["status"] for x in rows if x["status"]!="TIMEOUT"}
    check(len(answers)<=1,"cross-solver verdict disagreement")
    report=dict(protocol=PROTO,source_gbd=gbd,source_sha256=case["sha256"],
       vars=n,clauses=len(clauses),
       clean_sha256=sha(clean),native_sha256=sha(native),
       cms_version=args.cms_version,cms_binary_sha256=sha(cms),
       profile={k:str(v) if isinstance(v,Path) else v for k,v in profile.items()},
       rows=rows,limits=[
         "One trial per mode; exploratory only, no significance estimate",
         "Original CNF SHA verified; all clauses preserved in CMS-XOR augmented input",
         "Exact full parity blocks only (2-5 variables); no hidden parity claim",
         "CryptoMiniSat native XOR is established prior art; NOT DRNAS Kissat integration",
         "R32n active branch is tested only as existing unchanged baseline",
         "Only SAT models independently checked, UNSAT lacks independent LRAT",
         "75s wall timeout is censored and scored PAR2=150, not solved in 75",
         "Classification guard beyond 100,000 clauses; failure to detect is NOT absence",
         "Official 2026 source files but not official contest hardware or cutoff",
       ])
    (out/"report.json").write_text(json.dumps(report,indent=2)+"\n")
    print("R32T_CASE_PASS",gbd,len(rows),flush=True)

def aggregate(args):
    root=Path(args.combined)
    reports=[]
    for idx,gbd in enumerate(IDS):
        f=root/f"r32t-case-{idx}"/"results"/"report.json"
        check(f.is_file(),f"missing case {idx}")
        j=json.loads(f.read_text())
        check(j["protocol"]==PROTO and j["source_gbd"]==gbd,"case mismatch")
        check({x["mode"] for x in j["rows"]}==set(MODES),"incomplete paired attempt")
        reports.append(j)
    check(len({r["clean_sha256"] for r in reports})==1 and
          len({r["native_sha256"] for r in reports})==1 and
          len({r["cms_binary_sha256"] for r in reports})==1,"different binary across runners")
    summary={mode:dict(
       solved=sum(next(x for x in r["rows"] if x["mode"]==mode)["status"] in ("SAT","UNSAT") for r in reports),
       timeouts=sum(next(x for x in r["rows"] if x["mode"]==mode)["status"]=="TIMEOUT" for r in reports),
       par2_s=round(sum(next(x for x in r["rows"] if x["mode"]==mode)["par2_s"] for r in reports),6))
       for mode in MODES}
    report=dict(protocol=PROTO,summary=summary,cases=reports)
    Path(args.output).write_text(json.dumps(report,indent=2)+"\n")
    lines=["# DRNAS R32t — 5 original SATComp2026 XOR promotion pilot",
           "Paired original formulas. Four modes, one run per arm, 75s wall cap.",
           "**CMS explicit XOR is certified redundant CNF information, not a new DRNAS in-Kissat algorithm.**",
           "",
           "| Mode | Solved / 5 | Timeout | PAR2 total (s) |","|---|---:|---:|---:|"]
    for mode,d in summary.items():lines.append(f"| {mode} | {d['solved']} | {d['timeouts']} | {d['par2_s']:.4f} |")
    lines.extend(["","| Source (GBD prefix) | XOR eq | XOR coverage | Kissat | DRNAS | CMS original | CMS + XOR |",
                  "|---|---:|---:|---:|---:|---:|---:|"])
    for r in reports:
        d={x["mode"]:x for x in r["rows"]}
        def val(mode):
            x=d[mode]
            return f"{x['wall_s']:.3f}s" if x["status"]!="TIMEOUT" else "TIMEOUT 75s"
        lines.append(f"| {r['source_gbd'][:10]} | {r['profile']['xor_equations']} | {r['profile']['covered_pct']:.2f}% | {val('kissat_clean')} | {val('drnas_full')} | {val('cms_plain')} | {val('cms_xor')} |")
    lines.extend(["","SAT outputs checked on original clauses. UNSAT not independently certified.",
                  "A single run cannot establish a reproducible speedup, and a timeout only bounds speed.",
                  "CMS baseline and CMS + XOR isolate benefits of redundant parity representation.",
                  "Guarded classification on large formulas must not be interpreted as absence of XOR."])
    Path(args.report).write_text("\n".join(lines)+"\n")
    print("R32T_AUDIT_PASS",json.dumps(summary,sort_keys=True),flush=True)

def main():
    p=argparse.ArgumentParser()
    s=p.add_subparsers(dest="action",required=True)
    a=s.add_parser("measure")
    for k in ("frozen","clean","native","cms","clean-sha","native-sha","cms-version","out"):
        a.add_argument("--"+k,required=True)
    a.add_argument("--index",type=int,required=True)
    b=s.add_parser("aggregate")
    for k in ("combined","output","report"):b.add_argument("--"+k,required=True)
    args=p.parse_args()
    if args.action=="measure":measure(args)
    else:aggregate(args)
if __name__=="__main__":main()
