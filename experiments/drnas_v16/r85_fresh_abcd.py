#!/usr/bin/env python3
"""R85: genuinely new, original SAT Competition 2025 CNF cohort, frozen before solve.

A, B, C, D vs clean Kissat in parallel CI jobs. Selection is SHA-ranked,
excluding all R82 attempted official IDs, R73 attempted IDs, and a conservative
R72 first-150 candidate prefix, with no solver speed screening.
Four structurally exact XOR-positive and eight original-CNF controls are the
predeclared target. Explicit structural enrichment is NOT a representative
sample of all official SAT problems. All selected original CNFs are real GBD
files, byte-SHA anchored, not synthesized. If four new XOR cases cannot
be frozen within budget, fail closed rather than reusing earlier sources.
"""
from __future__ import annotations
import argparse,hashlib,json,os,random,re,subprocess,time
from pathlib import Path
import r73_fresh_quick_unseen_2025 as r73
import r32p_real_satcomp26_benchmark as r32p
import r52_prospective_2026_toprefs as r52
import r63_real2026_xor_prevalence_fallback as r63
import r83_live_xor_cdcl_wide as r83
import r32t_certified_short_xor as cert
cert.CAP_BYTES=24*1024*1024
cert.CAP_VARIABLES=4096
cert.CAP_CLAUSES=60000

PROTO="DRNAS-R85-ABCD-FRESH-OFFICIAL2025-XOR-STRATIFIED-20261104-v1"
SALT="DRNAS-R85-NOSPEED-NEVER-R82-R73-R72-SOURCE-SALT-20261104-v1"
R82=r83.R82_PROTO
TARGET_XOR,TARGET_CONTROL=4,8
SHARDS=12
MAX_FETCHES=235
CAP=35.0
REPS=2
MODES=("clean","A_passive16","B_active16","B_active4","C_diverse64_4","D_diverse128_4")
PROG=re.compile(r"^c R85_PROGRESS (.+)$",re.M)
SELECTION=re.compile(r"^c R85_SELECTION diverse=(\d+) source_candidates=(\d+) selected=(\d+)$",re.M)
R32U_ROWS=r83.SOURCE_ROW

def ck(v,m):
    if not v:raise RuntimeError("R85_FAIL_CLOSED "+str(m))
def sha(path):return r83.sha(path)
def store(path,obj):
    Path(path).write_text(json.dumps(obj,sort_keys=True,indent=2)+"\n")
def score(g):return hashlib.sha256((SALT+"/"+g).encode()).hexdigest()

def freeze(a):
    old=json.loads((Path(a.old)/"manifest.json").read_text())
    other=json.loads((Path(a.r73)/"manifest.json").read_text())
    ck(old["protocol"]==R82 and len(old["cases"])==48,
       "prior R82 source ledger is missing")
    ck(other["protocol"]==r73.PROTO,"R73 attempted source ledger not genuine")
    idx=r52.fetch_bytes(r73.SC2025,100000)
    ids=[s.rsplit("/",1)[-1] for s in idx.decode().strip().splitlines()]
    ck(len(ids)>=300 and len(ids)==len(set(ids)),"official SC2025 index not complete")
    blocked={c["gbd"] for c in old["cases"]}
    blocked.update(x["gbd"] for x in old["source_selection_attempts"])
    blocked.update(c["gbd"] for c in other["cases"])
    blocked.update(x["gbd"] for x in other["selection_attempts"])
    # R72 historical ranked possible source attempts were 100 IDs after
    # prior-known excludes; conservatively exclude the first 150 from ALL
    # 2025 IDs (prefix superset with sufficient slack; also log limitation).
    r72salt="DRNAS-R72-NEW-SHA-AND-ATTEMPT-DISJOINT-20261103-v1"
    prior72=sorted(ids,key=lambda x:hashlib.sha256((r72salt+":"+x).encode()).hexdigest())[:150]
    blocked.update(prior72)
    already_sha={c["sha256"] for c in old["cases"]}
    already_sha.update(c["sha256"] for c in other["cases"])
    root=Path(a.out);root.mkdir(parents=True,exist_ok=True)
    rows=[];attempts=[];xor=ctrl=0
    r32p.CNF_LIMIT=24*1024*1024
    candidates=sorted(set(ids)-blocked,key=score)
    for g in candidates[:MAX_FETCHES]:
        if xor>=TARGET_XOR and ctrl>=TARGET_CONTROL:break
        item=dict(gbd=g,year=2025)
        file=root/("2025-"+g+".cnf")
        try:
            compressed,redirect=r32p.request_url(
                "https://benchmark-database.de/file/"+g,16*1024*1024,seconds=20)
            raw,encoding=r32p.decode(compressed)
            ck(len(raw)<=24*1024*1024,"source size limit 24 MiB")
            n,clauses=r32p.parse_dimacs_metadata(raw)
            # Preserve the exact known R32u C engine bounds; no support
            # screening on solution time, SAT answer or solver metadata.
            ck(n<=4096 and clauses<=60000 and
                len(raw)<=12*1024*1024,"out of R32u original capture scope")
            file.write_bytes(raw)
            digest=sha(file)
            ck(digest not in already_sha and
                all(digest!=c["sha256"] for c in rows),
               "duplicate CNF with earlier frozen 2025 studies")
            info=r63.inspect_exact_xor(file,n,clauses)
            isxor=bool(info["supported"] and info["complete_blocks"]>=1)
            if (isxor and xor>=TARGET_XOR) or ((not isxor) and ctrl>=TARGET_CONTROL):
                file.unlink(missing_ok=True)
                item.update(state="STRUCTURAL_COHORT_FULL",xor=isxor)
                attempts.append(item)
                continue
            case=dict(gbd=g,year=2025,filename=file.name,
                      sha256=digest,size_bytes=len(raw),variables=n,clauses=clauses,
                      official_status="UNKNOWN",source_verified_status=False,
                      source_url="https://benchmark-database.de/file/"+g,
                      compressed_bytes=len(compressed),encoding=encoding,
                      redirect=redirect,structural_xor_positive=isxor,
                      group="xor_exact" if isxor else "control",
                      **info)
            rows.append(case)
            xor+=int(isxor);ctrl+=int(not isxor)
            item.update(state="ACCEPTED",sha256=digest,xor=isxor,
                        vars=n,clauses=clauses)
        except Exception as e:
            file.unlink(missing_ok=True)
            item.update(state="UNSUPPORTED_SOURCE",why=(type(e).__name__+
                        " "+str(e))[:230])
        attempts.append(item)
        print("R85_FRESH_INPUT_ATTEMPT",json.dumps(item),flush=True)
    ck(xor==TARGET_XOR and ctrl==TARGET_CONTROL,
       f"insufficient unseen original XOR {xor}/{TARGET_XOR} controls {ctrl}/{TARGET_CONTROL}")
    ck(len(rows)==SHARDS and len({x["gbd"] for x in rows})==SHARDS,
       "wrong source count")
    selected={x["gbd"] for x in rows}
    ck(not selected.intersection(blocked),"source was already benchmarked")
    rows.sort(key=lambda c:score(c["gbd"]))
    manifest=dict(protocol=PROTO,salt=SALT,source_index=r73.SC2025,
        source_index_sha256=hashlib.sha256(idx).hexdigest(),
        R82_manifest_sha=sha(Path(a.old)/"manifest.json"),
        R73_manifest_sha=sha(Path(a.r73)/"manifest.json"),
        precommitted_mode_order=MODES,repeats=REPS,cap_s=CAP,
        selection_rule="4 source-exact-XOR plus 8 structural controls (in R32u scope), SHA-ranked, never solved before freezing",
        excluded_identifiers=len(blocked),excluded_prefix_r72=150,
        max_fetched=MAX_FETCHES,actual_attempts=len(attempts),
        source_attempts=attempts,cases=rows,
        limitations=[
          "Fresh means absent from documented R72 candidate prefix, R73 and R82 attempts/accepted source ledgers; cannot rule out undocumented historical use.",
          "2025 originals are hosted by the official SAT Competition 2025 source index and benchmark-database.de SHA-identified GBD files.",
          "Structurally enriched 4 XOR / 8 non-XOR sample is NOT broadly representative and cannot ground world-ranking claims.",
          "Source limits <=4096 vars, <=60000 clauses, <=12 MiB (R32u source capture) impose a strong input bias.",
          "No baseline run or solver speed result influences source selection.",
          "SAT witness validated on untouched original; UNSAT not independently proven by LRAT and not a certified UNSAT competition result."
        ])
    store(root/"manifest.json",manifest)
    (root/"source.sha256").write_text("".join(
         c["sha256"]+"  "+c["filename"]+"\n" for c in rows))
    print("R85_UNSEEN_REAL_2025_FROZEN_PASS",json.dumps({
        "cases":len(rows),"xor":xor,"controls":ctrl,"attempted":len(attempts)}),
        flush=True)

def parse_counts(stdout,mode,source,cache):
    if mode=="clean":
        ck(not PROG.search(stdout),"clean Kissat was instrumented unexpectedly")
        return dict(snapshots=0,last=None,source_rows=0,verified=True)
    entries=[]
    for raw in PROG.findall(stdout):
        j={}
        for entry in raw.split():
            key,value=entry.split("=",1)
            j[key]=float(value) if key=="cpu_ms" else int(value)
        entries.append(j)
    ck(bool(entries),"native patch omitted timed progress")
    last=entries[-1]
    for old,new in zip(entries,entries[1:]):
        for k in ("missing_import","eliminated","bad_literal","out_of_scope",
                  "multi_unassigned","all_assigned","one_missing","attached",
                  "first_uip_reason_uses","scans","conflicts","decisions"):
            ck(old[k]<=new[k],"native monotonic diagnostic counter violation "+k)
    emitted=[(tuple(map(int,varstr.split(","))),int(rhs))
             for rhs,varstr in R32U_ROWS.findall(stdout)]
    ck(last["prepared"]==len(emitted),"bad native-source GF2 row count")
    if emitted:
        key=(sha(source),int(mode.startswith(("C_","D_"))),128 if mode.startswith("D_") else 64)
        if key in cache:
            ck(cache[key]==tuple(emitted),
               "native source XOR equations changed among same mode")
        else:
            r83.source_prove_rows(source,emitted)
            cache[key]=tuple(emitted)
    ck(last["attached"]<=last["one_missing"],
       "invalid reason attachment accounting")
    if mode=="A_passive16":
        ck(last["attached"]==0 and last["first_uip_reason_uses"]==0,
           "passive mode improperly performed XOR reasons")
    policy=SELECTION.findall(stdout)
    if not policy:
        # The original native guard rejects contradictory BCP/root input
        # before source-row selection, retaining sound fail-closed abstention.
        ck(not emitted and last["prepared"]==0 and "R32U_GUARD" in stdout,
           "no native row-selection tag without an explicit original guard")
        candidates=selected=0
    else:
        ck(len(policy)==1,"more than one native source selection")
        diverse,candidates,selected=map(int,policy[0])
        ck(diverse==int(mode.startswith("C_") or mode.startswith("D_")),
           "native row policy not matching cohort arm")
        ck(selected==len(emitted),"actual native selected parity count mismatch")
        if mode.startswith("D_"):
            ck(selected<=128,"expanded cap exceeded")
        else:
            ck(selected<=64,"standard source cap exceeded")
    return dict(snapshots=len(entries),last=last,source_rows=len(emitted),
                total_candidates=candidates,verified=True)

def one_trial(source,mode,case,clean,native,cache):
    start=time.monotonic();env=os.environ.copy()
    if mode!="clean":
        env.update(R32B_MODE="r32u",
                   R32U_ACTIVE="0" if mode=="A_passive16" else "1",
                   R84_SCAN_EVERY="4" if mode in
                     ("B_active4","C_diverse64_4","D_diverse128_4") else "16",
                   R85_DIVERSE="1" if mode.startswith(("C_","D_")) else "0",
                   R85_CAP="128" if mode.startswith("D_") else "64",
                   R32S_PASSIVE_TRACE="0")
    exe=clean if mode=="clean" else native
    try:
        p=subprocess.run([str(exe),str(source)],env=env,
             capture_output=True,text=True,errors="replace",timeout=CAP)
        ck(p.returncode in (10,20),"unexpected native result code "+
             str(p.returncode)+" "+p.stderr[-260:])
        stdout=p.stdout
        verdict="SAT" if p.returncode==10 else "UNSAT"
    except subprocess.TimeoutExpired as e:
        stdout=e.stdout or b""
        if isinstance(stdout,bytes):stdout=stdout.decode(errors="replace")
        verdict="TIMEOUT"
    elapsed=time.monotonic()-start
    if verdict=="SAT":r32p.verify_sat_witness(source,stdout)
    telemetry=parse_counts(stdout,mode,source,cache)
    return dict(answer=verdict if elapsed<=CAP else "TIMEOUT",
                wall_s=round(min(elapsed,CAP),6),
                par2_s=round(elapsed if verdict!="TIMEOUT" and elapsed<=CAP else 2*CAP,6),
                telemetry=telemetry,original_sat_model_checked=(verdict=="SAT"),
                external_unsat_proof_checked=False)

def measure(a):
    root=Path(a.sources).resolve()
    mf=json.loads((root/"manifest.json").read_text())
    ck(mf["protocol"]==PROTO and len(mf["cases"])==SHARDS,
       "unseen frozen manifest mismatch")
    ck(0<=a.shard<SHARDS,"invalid shard")
    c=mf["cases"][a.shard]
    source=root/c["filename"]
    ck(sha(source)==c["sha256"],"real source changed")
    b=Path(a.compiled).resolve()
    ck(subprocess.run(["sha256sum","-c","r85-binaries.sha256"],cwd=b,
       capture_output=True).returncode==0,"native binaries did not match pinned checksums")
    clean=b/"clean";native=b/"native-r85"
    ck(all(x.is_file() and os.access(x,os.X_OK) for x in (clean,native)),
       "solver binary missing / not executable")
    if hasattr(os,"sched_setaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    cache={};rows=[]
    for rep in range(REPS):
        modes=list(MODES)
        random.Random(int(hashlib.sha256(
          (PROTO+c["sha256"]+str(rep)).encode()).hexdigest(),16)).shuffle(modes)
        for mode in modes:
            result=one_trial(source,mode,c,clean,native,cache)
            row=dict(gbd=c["gbd"],sha256=c["sha256"],group=c["group"],
                year=c["year"],rep=rep,mode=mode,**result)
            rows.append(row)
            store(out/"r85-shard.json",dict(protocol=PROTO,shard=a.shard,
               manifest_sha=sha(root/"manifest.json"),
               binary_sha={"clean":sha(clean),"native-r85":sha(native)},
               rows=rows))
            last=result["telemetry"]["last"] or {}
            print("R85_TRIAL",json.dumps(dict(gbd=c["gbd"],group=c["group"],
                rep=rep,mode=mode,answer=result["answer"],wall_s=result["wall_s"],
                par2_s=result["par2_s"],rows=result["telemetry"]["source_rows"],
                candidates=result["telemetry"].get("total_candidates",0),
                reasons=last.get("attached",0),uip_uses=last.get("first_uip_reason_uses",0),
                missing_import=last.get("missing_import",0),eliminated=last.get("eliminated",0),
                multi_unassigned=last.get("multi_unassigned",0),
                one_missing=last.get("one_missing",0))),flush=True)
    ck(len(rows)==REPS*len(MODES),"incomplete source paired data")
    print("R85_SHARD_PASS",a.shard,len(rows),flush=True)

def audit(a):
    root=Path(a.sources);mf=json.loads((root/"manifest.json").read_text())
    ck(mf["protocol"]==PROTO and len(mf["cases"])==SHARDS,"wrong frozen originals")
    allrows=[];pins=set()
    for i,c in enumerate(mf["cases"]):
        shard=Path(a.combined)/f"r85-shard-{i}"/"results"/"r85-shard.json"
        ck(shard.is_file(),"missing fully completed fresh source "+str(i))
        data=json.loads(shard.read_text())
        ck(data["protocol"]==PROTO and data["shard"]==i and
           data["manifest_sha"]==sha(root/"manifest.json"),"mismatched source freeze")
        pins.add(json.dumps(data["binary_sha"],sort_keys=True))
        part=data["rows"]
        ck(len(part)==REPS*len(MODES) and
           all(x["gbd"]==c["gbd"] and x["sha256"]==c["sha256"] for x in part),
           "source identity changed")
        for rep in range(REPS):
            pair=[x for x in part if x["rep"]==rep]
            ck(len(pair)==len(MODES) and {x["mode"] for x in pair}==set(MODES),
               "unpaired real original trial")
            answers={x["answer"] for x in pair if x["answer"]!="TIMEOUT"}
            ck(len(answers)<=1,"contradictory same-source answer")
            ck(all(x["telemetry"]["verified"] for x in pair),
               "some native original-source XOR rows not independently proven")
        allrows+=part
    ck(len(pins)==1 and len(allrows)==SHARDS*REPS*len(MODES),
       "unmatched native pin / missing measurements")
    summaries={}
    for group in ("ALL","XOR","CONTROL"):
        source_ids={c["sha256"] for c in mf["cases"] if group=="ALL" or
                    (group=="XOR" and c["structural_xor_positive"]) or
                    (group=="CONTROL" and not c["structural_xor_positive"])}
        summaries[group]={}
        for mode in MODES:
            rs=[r for r in allrows if r["sha256"] in source_ids and r["mode"]==mode]
            summaries[group][mode]=dict(trials=len(rs),
                solved=sum(r["answer"]!="TIMEOUT" for r in rs),
                par2_s=round(sum(r["par2_s"] for r in rs),6),
                attached_lower_bound=sum((r["telemetry"]["last"] or {}).get("attached",0) for r in rs),
                first_uip_uses_lower_bound=sum((r["telemetry"]["last"] or {}).get("first_uip_reason_uses",0) for r in rs),
                eliminated_lower_bound=sum((r["telemetry"]["last"] or {}).get("eliminated",0) for r in rs),
                multi_unassigned_lower_bound=sum((r["telemetry"]["last"] or {}).get("multi_unassigned",0) for r in rs))
    paired=[]
    for c in mf["cases"]:
        rr=[r for r in allrows if r["sha256"]==c["sha256"]]
        d={mode:sum(r["par2_s"] for r in rr if r["mode"]==mode)/REPS for mode in MODES}
        paired.append(d)
    rng=random.Random(2026110485)
    boot={}
    for mode in MODES[1:]:
        diff=[x["clean"]-x[mode] for x in paired]
        draws=sorted(sum(diff[rng.randrange(len(diff))] for _ in range(len(diff)))/len(diff)
                     for _ in range(2000))
        boot[mode]=dict(mean_saved_s_per_formula=round(sum(diff)/len(diff),6),
                        source_bootstrap_95ci=[round(draws[49],6),round(draws[1949],6)])
    result=dict(protocol=PROTO,status="PASS_UNOFFICIAL",
        actual_originals=len(mf["cases"]),trials=len(allrows),
        originals_sha256=sha(root/"manifest.json"),
        solver_pins=json.loads(next(iter(pins))),summaries=summaries,
        source_paired_bootstrap=boot,rows=allrows,
        limitations=mf["limitations"]+[
            "R85 A/B/C/D controls were frozen in GitHub source before selecting original 2025 CNFs.",
            "Binomial sample small and XOR enriched: report separately, do not generalize to competition leaderboard.",
            "Exact recorded 2025 source-ledger exclusions; hidden prior tests outside registry cannot be ruled out.",
            "No independent official 2025 UNSAT verification; SAT witnesses checked against original DIMACS.",
            "Time limit 35s with PAR2=70s per timeout, single core per runner, not official SAT Competition conditions.",
            "First-UIP count is verified nonbinary native XOR reason use, but binary reasons are not yet tracked.",
            "Each source is bootstrap unit, not each repetition."
        ])
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    store(out/"r85-final.json",result)
    md=["# DRNAS R85: A, B, C, D on genuinely fresh original 2025 CNFs",
        "",f"{SHARDS} source-SHA frozen new original formulas, 4 XOR / 8 controls, "+
        f"{len(allrows)} two-repeat paired trials, 35s cap, PAR2=70s timeout.",
        "Preselected only by official source SHA + exact XOR structure, NOT solver speed.",
        "", "| Method | Solved | PAR-2 s | XOR reasons | 1-UIP reason uses |",
        "|---|---:|---:|---:|---:|"]
    for mode,v in summaries["ALL"].items():
        md.append(f"| {mode} | {v['solved']}/{v['trials']} | {v['par2_s']:.3f} | "+
                  f"{v['attached_lower_bound']} | {v['first_uip_uses_lower_bound']} |")
    for group in ("XOR","CONTROL"):
        md+=["",f"## {group} cohort", "| Mode | Solved | PAR-2 s |", "|---|---:|---:|"]
        for mode,v in summaries[group].items():
            md.append(f"| {mode} | {v['solved']}/{v['trials']} | {v['par2_s']:.3f} |")
    md+=["","## Paired original-source bootstrap"]
    for mode,v in boot.items():md.append(f"- {mode}: {v}")
    md+=["","## Important limits"]+["- "+x for x in result["limitations"]]
    (out/"r85-final.md").write_text("\n".join(md)+"\n")
    print("R85_ABCD_FRESH_REAL_FINAL_AUDIT_PASS",json.dumps(summaries["ALL"]),flush=True)

def selftest():
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        p=Path(td)/"synthetic-proof-selftest-only.cnf"
        clauses=[]
        for var,rhs in (((1,2,3),1),((2,3,4),0)):
            for mask in range(8):
                if mask.bit_count()%2!=rhs:
                    clauses.append(tuple(-v if mask&(1<<j) else v for j,v in enumerate(var)))
        p.write_text("p cnf 4 "+str(len(clauses))+"\n"+
             "".join(" ".join(map(str,c))+" 0\n" for c in clauses))
        ck(r83.source_prove_rows(p,[((1,4),1)])==1,"original GF2 proof selftest")
        try:r83.source_prove_rows(p,[((1,4),0)])
        except RuntimeError:pass
        else:raise RuntimeError("invalid XOR row was erroneously certified")
    ck(len(MODES)==6 and SHARDS==TARGET_XOR+TARGET_CONTROL,
       "mode/cohort count changed")
    print("R85_INDEPENDENT_GF2_PROOF_AND_PROTOCOL_SELFTEST_PASS",flush=True)

def main():
    p=argparse.ArgumentParser()
    sub=p.add_subparsers(dest="cmd",required=True)
    sub.add_parser("selftest")
    z=sub.add_parser("freeze")
    z.add_argument("--old",required=True);z.add_argument("--r73",required=True)
    z.add_argument("--out",required=True)
    z=sub.add_parser("measure")
    for k in ("sources","compiled","out"):z.add_argument("--"+k,required=True)
    z.add_argument("--shard",type=int,required=True)
    z=sub.add_parser("audit")
    for k in ("sources","combined","out"):z.add_argument("--"+k,required=True)
    a=p.parse_args()
    if a.cmd=="freeze":freeze(a)
    elif a.cmd=="measure":measure(a)
    elif a.cmd=="audit":audit(a)
    else:selftest()
if __name__=="__main__":main()
