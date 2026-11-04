#!/usr/bin/env python3
"""R87 prospective, historical-ledger SHA-disjoint original SAT2025/2026 holdout.

The R87 adaptive rule was frozen BEFORE source selection and timing. Historical
attempts and source SHA are conservatively excluded; undocumented experiments
cannot be exhaustively ruled out. Sourced original CNFs are NOT synthesized.
This is an unofficial GitHub-runner benchmark, not SAT Competition scoring.
"""
from __future__ import annotations
import argparse,csv,hashlib,io,json,os,random,subprocess
from pathlib import Path
import r87_feedback_replay as dev
import r85_fresh_abcd as old
import r82_wide_official_2025_2026 as wide

PROTO="DRNAS-R87-PROSPECTIVE-ORIGINAL-SHA-DISJOINT-20261104-v1"
SALT="DRNAS-R87-PRECOMMITTED-UNSEEN-2025-2026-HASH-20261104-v1"
SHARDS,REPS,CAP=8,2,35.0
MODES=("clean","active4","active64","adaptive")
R72_SALT="DRNAS-R72-NEW-SHA-AND-ATTEMPT-DISJOINT-20261103-v1"

def ck(x,reason):
    if not x:raise RuntimeError("R87_HOLDOUT_FAIL_CLOSED "+str(reason))
def sha(path):return old.sha(path)
def write(path,v):Path(path).write_text(json.dumps(v,sort_keys=True,indent=2)+"\n")
def order(year,gbd):return hashlib.sha256((SALT+"/"+str(year)+"/"+gbd).encode()).hexdigest()

def priors(a):
    sources={"R82":Path(a.r82)/"manifest.json",
             "R73":Path(a.r73)/"manifest.json",
             "R85_12":Path(a.r85)/"manifest.json",
             "R85_24":Path(a.r85b)/"manifest.json",
             "R85_8":Path(a.r85eight)/"manifest.json"}
    for k,p in sources.items():ck(p.is_file(),"historical source manifest absent "+k)
    ledger={k:json.loads(p.read_text()) for k,p in sources.items()}
    ck(len(ledger["R82"]["cases"])==48 and
       ledger["R82"]["protocol"]==wide.PROTO,"R82 provenance mismatch")
    ck(len(ledger["R85_12"]["cases"])==12 and
       ledger["R85_12"]["protocol"]==old.PROTO,"R85 A/B/C/D history mismatch")
    ck(len(ledger["R85_24"]["cases"])==24,"R85b earlier sample mismatch")
    ck(len(ledger["R85_8"]["cases"])==8,"R85 additional 8-case history mismatch")
    blocked_ids=set();blocked_sha=set()
    for k,m in ledger.items():
        for x in m.get("cases",[]):
            if x.get("gbd"):blocked_ids.add(x["gbd"])
            if x.get("sha256"):blocked_sha.add(x["sha256"])
        for field in ("source_attempts","source_selection_attempts",
                      "selection_attempts","attempts"):
            for x in m.get(field,[]):
                if isinstance(x,dict) and x.get("gbd"):blocked_ids.add(x["gbd"])
    return ledger,sources,blocked_ids,blocked_sha

def freeze(a):
    led,paths,blocked_ids,blocked_sha=priors(a)
    root=Path(a.out);root.mkdir(parents=True,exist_ok=True)
    idx25=wide.r52.fetch_bytes(wide.r73.SC2025,100000)
    idx26=wide.r52.fetch_bytes(wide.r52.URI,100000)
    official=wide.r52.fetch_bytes(wide.r52.SCORES,32*1024*1024)
    ck(hashlib.sha256(idx25).hexdigest()==led["R82"]["index_2025_sha256"],
       "2025 source index checksum drift")
    ck(hashlib.sha256(idx26).hexdigest()==led["R82"]["index_2026_sha256"],
       "2026 source index checksum drift")
    ck(hashlib.sha256(official).hexdigest()==led["R82"]["scores_2026_reference_sha256"],
       "2026 published verdict source changed")
    ids25=[v.rsplit("/",1)[-1] for v in idx25.decode().splitlines() if v.strip()]
    ids26=[v.rsplit("/",1)[-1] for v in idx26.decode().splitlines() if v.strip()]
    ck(len(ids25)>=300 and len(ids25)==len(set(ids25)),"2025 index invalid")
    ck(len(ids26)==400 and len(ids26)==len(set(ids26)),"2026 index invalid")
    verified={r["instanceid"]:r["status"]
              for r in csv.DictReader(io.StringIO(official.decode()))
              if r["solverid"]=="biere_cadical3[main]"}
    ck(len(verified)==400,"2026 external reference table invalid")
    # Conservative R72 prefix: no attempts from earlier documented hash cohort.
    no72=sorted(ids25,key=lambda g:hashlib.sha256(
        (R72_SALT+":"+g).encode()).hexdigest())[:150]
    blocked_ids.update(no72)
    candidates={2025:sorted((g for g in ids25 if g not in blocked_ids),
                            key=lambda g:order(2025,g)),
                2026:sorted((g for g in ids26 if g not in blocked_ids),
                            key=lambda g:order(2026,g))}
    # Fixed and transparent quota: attempt up to three from 2025, then at least
    # five from 2026. If fewer from 2025 are eligible, 2026 supplies the rest.
    rows=[];attempts=[];new_sha=set()
    wide.r32p.CNF_LIMIT=24*1024*1024
    for year,limit in ((2025,3),(2026,8)):
        for g in candidates[year][:170]:
            if len(rows)>=SHARDS or (year==2025 and
                sum(c["year"]==2025 for c in rows)>=limit):break
            note=dict(gbd=g,year=year)
            ext=verified.get(g) if year==2026 else None
            if year==2026 and ext not in ("sat-verified","unsat-verified"):
                note["state"]="SKIP_UNVERIFIED_2026";attempts.append(note);continue
            p=root/(f"{year}-{g}.cnf")
            try:
                rawpack,redirect=wide.r32p.request_url(
                    "https://benchmark-database.de/file/"+g,16*1024*1024,seconds=25)
                raw,encoding=wide.r32p.decode(rawpack)
                ck(len(raw)<=12*1024*1024,"source >12MiB certified native cap")
                n,k=wide.r32p.parse_dimacs_metadata(raw)
                ck(n<=4096 and k<=60000,"outside certified native capture scope")
                p.write_bytes(raw);digest=sha(p)
                ck(digest not in blocked_sha and digest not in new_sha,
                   "duplicated historical/source SHA")
                features=wide.r63.inspect_exact_xor(p,n,k)
                row=dict(gbd=g,year=year,filename=p.name,sha256=digest,
                   size_bytes=len(raw),variables=n,clauses=k,
                   source_url="https://benchmark-database.de/file/"+g,
                   compression=encoding,redirect=redirect,**features,
                   structural_xor_positive=bool(features["supported"] and
                                                features["complete_blocks"]>0),
                   official_status=("SAT" if ext=="sat-verified" else
                                    "UNSAT" if ext=="unsat-verified" else "UNKNOWN"),
                   source_verified_status=(year==2026))
                row["group"]=("XOR_EXACT" if row["structural_xor_positive"]
                              else "CONTROL")
                rows.append(row);new_sha.add(digest)
                note.update(state="ACCEPTED",sha256=digest,group=row["group"])
            except Exception as e:
                p.unlink(missing_ok=True)
                note.update(state="SKIP_AUDITED",reason=(
                    type(e).__name__+" "+str(e))[:210])
            attempts.append(note)
            print("R87_FRESH_ATTEMPT",json.dumps(note,sort_keys=True),flush=True)
        print("R87_YEAR_FREEZE",year,len([c for c in rows if c["year"]==year]),
              flush=True)
    ck(len(rows)==SHARDS and len(new_sha)==SHARDS,
       "not enough distinct original held-out sources (never reuse old inputs)")
    # Do not pretend this represents all official SAT instances: size filters
    # and known historical source exclusions bias both years.
    manifest=dict(protocol=PROTO,salt=SALT,
      historical_manifest_sha256={k:sha(p) for k,p in paths.items()},
      historical_excluded_ids=len(blocked_ids),
      historical_excluded_sha=len(blocked_sha),
      attempts=attempts,cases=rows,shards=SHARDS,cap_s=CAP,
      methods=MODES,repeats=REPS,
      no_solver_or_time_preselection=True,
      source_indices_sha256={"2025":hashlib.sha256(idx25).hexdigest(),
                             "2026":hashlib.sha256(idx26).hexdigest()},
      reference_verdict_sha256=hashlib.sha256(official).hexdigest(),
      primary_precommitted=dict(candidate="adaptive",reference="clean",
        no_fewer_solved=True,relative_PAR2_gain_at_least=0.05,
        paired_source_bootstrap_CI_lower_above_zero=True),
      limitations=[
        "Original official 2025/2026 source CNFs, not a competition-ranked run.",
        "Only declared historical source/attempt registries excluded; undocumented older tests cannot be ruled out.",
        "No speed or SAT-label selection; size and native-support caps bias the sample.",
        "2025 answers not independently verified against SAT Competition official outcomes.",
        "SAT witnesses independently checked against unchanged original CNF; no external LRAT for UNSAT.",
        "2026 SAT/UNSAT answers compared to published verified statuses, not a new UNSAT certificate.",
        "New sample could contain few or no XOR-positive inputs; report that rather than posthoc reshuffle.",
        "Two repeats on one original count as ONE independent formula for bootstrap.",
        "A development replay of R85 and R86 precedes this SHA-disjoint R87 cohort; no world record is claimed."])
    write(root/"manifest.json",manifest)
    (root/"source.sha256").write_text("".join(
       c["sha256"]+"  "+c["filename"]+"\n" for c in rows))
    print("R87_FRESH_OFFICIAL_FREEZE_PASS",json.dumps({
      "sources":SHARDS,"years":{str(y):sum(c["year"]==y for c in rows)
      for y in (2025,2026)},"xor":sum(c["structural_xor_positive"] for c in rows)}),
      flush=True)

def manifest(root):
    m=json.loads((root/"manifest.json").read_text())
    ck(m["protocol"]==PROTO and len(m["cases"])==SHARDS,"frozen new cohort mismatch")
    ck(len({c["sha256"] for c in m["cases"]})==SHARDS,"duplicate new SHA")
    return m

def measure(a):
    root=Path(a.sources).resolve();mf=manifest(root)
    ck(0<=a.shard<SHARDS,"unknown shard")
    case=mf["cases"][a.shard];source=root/case["filename"]
    ck(sha(source)==case["sha256"],"original SHA mismatch")
    bins=Path(a.compiled).resolve()
    pin=subprocess.run(["sha256sum","-c","r87-binaries.sha256"],
        cwd=bins,capture_output=True,text=True)
    ck(pin.returncode==0,"binary checksum mismatch "+pin.stderr[-250:])
    clean,native=bins/"clean",bins/"native-r87"
    ck(all(p.exists() and os.access(p,os.X_OK) for p in (clean,native)),"missing binary")
    if hasattr(os,"sched_setaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    rows=[];proof_cache={};out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    for rep in range(REPS):
        modes=list(MODES)
        random.Random(int(hashlib.sha256(
          (PROTO+case["sha256"]+str(rep)).encode()).hexdigest(),16)).shuffle(modes)
        for mode in modes:
            result=dev.trial(source,case,mode,clean,native,proof_cache)
            if result["answer"]!="TIMEOUT" and case["source_verified_status"]:
                ck(result["answer"]==case["official_status"],"external 2026 outcome conflict")
            row=dict(source="original_sat_competition_index",year=case["year"],
                sha256=case["sha256"],gbd=case["gbd"],group=case["group"],
                rep=rep,mode=mode,runner=os.environ.get("RUNNER_NAME",""),
                commit=os.environ.get("GITHUB_SHA",""),
                run_id=os.environ.get("GITHUB_RUN_ID",""),
                seed=hashlib.sha256((PROTO+case["sha256"]+str(rep)).encode()).hexdigest(),
                **result)
            rows.append(row)
            write(out/"shard.json",dict(protocol=PROTO,shard=a.shard,
               source_manifest_sha=sha(root/"manifest.json"),
               binary_sha={"clean":sha(clean),"native_r87":sha(native)},rows=rows))
            d=result["telemetry"]
            print("R87_HOLDOUT_TRIAL",json.dumps(dict(
              year=case["year"],gbd=case["gbd"],group=case["group"],rep=rep,
              mode=mode,answer=result["answer"],par2_s=result["par2_s"],
              scans=(d["last"] or {}).get("scans",0),
              attached=(d["last"] or {}).get("attached",0),
              first_uip=(d["last"] or {}).get("first_uip_reason_uses",0))),
              flush=True)
    ck(len(rows)==len(MODES)*REPS,"missing paired methods/repeats")
    print("R87_HOLDOUT_SHARD_PASS",a.shard,len(rows),flush=True)

def audit(a):
    root=Path(a.sources);mf=manifest(root);rows=[];pins=set();pairs={}
    for shard,c in enumerate(mf["cases"]):
        ck(sha(root/c["filename"])==c["sha256"],"CNF SHA mismatch")
        p=Path(a.combined)/f"r87-holdout-shard-{shard}"/"results"/"shard.json"
        ck(p.is_file(),"missing complete shard "+str(shard))
        j=json.loads(p.read_text())
        ck(j["protocol"]==PROTO and j["shard"]==shard and
           j["source_manifest_sha"]==sha(root/"manifest.json"),"manifest mismatch")
        pins.add(json.dumps(j["binary_sha"],sort_keys=True))
        ck(len(j["rows"])==REPS*len(MODES),"incomplete shard rows")
        for rep in range(REPS):
            pair=[x for x in j["rows"] if x["rep"]==rep]
            ck(len(pair)==len(MODES) and {x["mode"] for x in pair}==set(MODES),
               "not a complete paired experiment")
            ck(all(x["sha256"]==c["sha256"] and x["gbd"]==c["gbd"]
                   and x["runner"] and x["commit"] and x["run_id"] and x["seed"]
                   for x in pair),"missing source/seed/runner provenance")
            answers={x["answer"] for x in pair if x["answer"]!="TIMEOUT"}
            ck(len(answers)<=1,"SAT/UNSAT contradiction between methods")
            ck(all(x["telemetry"]["verified"] for x in pair),"GF2 original proof failed")
            if c["source_verified_status"]:
                ck(all(x==c["official_status"] for x in answers),
                   "externally verified original outcome contradicted")
            pairs[(c["sha256"],rep)]={x["mode"]:x for x in pair}
        rows+=j["rows"]
    ck(len(pins)==1 and len(rows)==SHARDS*REPS*len(MODES),
       "incomplete final raw rows/binary pin drift")
    summary={}
    for group in ("ALL","2025","2026","XOR_EXACT","CONTROL"):
        part=[r for r in rows if group=="ALL" or r["group"]==group or
              (group.isdigit() and str(r["year"])==group)]
        summary[group]={}
        for mode in MODES:
            q=[r for r in part if r["mode"]==mode]
            summary[group][mode]=dict(trials=len(q),solved=sum(x["answer"]!="TIMEOUT" for x in q),
                par2_s=round(sum(x["par2_s"] for x in q),6),
                first_uip=sum((x["telemetry"]["last"] or {}).get("first_uip_reason_uses",0)
                              for x in q))
    deltas=[]
    for c in mf["cases"]:
        z=[pairs[(c["sha256"],i)] for i in range(REPS)]
        deltas.append(sum(p["clean"]["par2_s"]-p["adaptive"]["par2_s"] for p in z)/REPS)
    boot=[]
    rng=random.Random(871108)
    for _ in range(5000):
        boot.append(sum(deltas[rng.randrange(len(deltas))] for i in range(len(deltas)))/len(deltas))
    boot.sort()
    ci=[round(boot[124],6),round(boot[4874],6)]
    clean=summary["ALL"]["clean"];adapt=summary["ALL"]["adaptive"]
    gain=(clean["par2_s"]-adapt["par2_s"])/clean["par2_s"]
    passed=adapt["solved"]>=clean["solved"] and gain>=.05 and ci[0]>0
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    result=dict(protocol=PROTO,status="PASS_UNOFFICIAL_PROSPECTIVE",
      raw_trials=len(rows),distinct_original_sources=SHARDS,
      source_manifest_sha256=sha(root/"manifest.json"),
      binary_sha256=json.loads(next(iter(pins))),summary=summary,
      primary_relative_PAR2_gain=round(gain,8),
      primary_source_bootstrap_95ci_s=ci,
      precommitted_claim_pass=passed,
      verdict=("PRIMARY_GAIN_CONFIRMED_ON_THIS_SAMPLE" if passed else
               "NO_PRECOMMITTED_GAIN_ON_THIS_SAMPLE"),
      rows=rows,limitations=mf["limitations"])
    write(out/"r87-holdout-final.json",result)
    md=["# R87 genuinely new documented-ledger SHA-disjoint real-original SAT2025/2026 holdout",
      "",f"Sources {SHARDS}, paired original-source trials {len(rows)}. 35s cap, PAR2 timeout=70s.",
      "Not official competition ranking. No solver/XOR/timing preselection.",
      "", "| Subgroup | Mode | Solved/trials | PAR-2 s |",
      "|---|---|---:|---:|"]
    for group,modes in summary.items():
        for mode,z in modes.items():
            md.append(f"| {group} | {mode} | {z['solved']}/{z['trials']} | {z['par2_s']:.3f} |")
    md+=["",f"Precommitted adaptive-vs-clean PAR2 gain {gain*100:.5f}%",
         f"Source-paired bootstrap 95% CI seconds saved per source: {ci}",
         f"Precommitted >=5% + no-fewer-solved + CI lower positive: **{'PASS' if passed else 'NOT MET'}**",
         "", "## Limitations"]+["- "+x for x in mf["limitations"]]
    (out/"r87-holdout-final.md").write_text("\n".join(md)+"\n")
    print("R87_HOLDOUT_FINAL_AUDIT_PASS",json.dumps(dict(
      total=len(rows),clean=clean,adaptive=adapt,ci=ci,claim=passed)),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser();s=p.add_subparsers(dest="cmd",required=True)
    s.add_parser("selftest")
    f=s.add_parser("freeze")
    for key in ("r82","r73","r85","r85b","r85eight","out"):
        f.add_argument("--"+key,required=True)
    m=s.add_parser("measure")
    for key in ("sources","compiled","out"):m.add_argument("--"+key,required=True)
    m.add_argument("--shard",type=int,required=True)
    a=s.add_parser("audit")
    for key in ("sources","combined","out"):a.add_argument("--"+key,required=True)
    x=p.parse_args()
    if x.cmd=="selftest":
        ck(len(MODES)==4 and SHARDS==8 and CAP==35,"predeclared benchmark changed")
        ck("adaptive" in MODES and dev.SCAN["adaptive"]==16,"adaptive initial interval drift")
        print("R87_HOLDOUT_FROZEN_PROTOCOL_SELFTEST_PASS")
    elif x.cmd=="freeze":freeze(x)
    elif x.cmd=="measure":measure(x)
    else:audit(x)
