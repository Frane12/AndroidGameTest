#!/usr/bin/env python3
"""R88.2 fair-budget cooperative SAT ablation on EXACT R88.1 frozen CNFs.

Distinct arms: pinned clean Kissat, legacy cooperative (original 48 lemmas),
lean certified cross-community exchange, and scout-gated lean fallback.
Every arm has ONE 12s end-to-end allowance. 12s cap includes CNF reading,
local learning, CNF writing, optional clean scout, and final solver.
On timeout, PAR2=24s WITHOUT exceeding the cap or adding a bonus.
Development replay on R88.1 previously seen inputs; NOT a blind holdout.
"""
from __future__ import annotations
import argparse, collections, csv, hashlib, json, os, random, sqlite3, statistics, subprocess, tempfile, time
from pathlib import Path
import r88_cooperative as base

PROTO="DRNAS-R88V2-END2END-CERTIFIED-COOPERATIVE-DEVELOPMENT-20261104-v1"
SOURCE_PROTO="DRNAS-R88-BULK-OFFICIAL-CNF-20261104-v1"
MODES=("clean","legacy_corrected","lean_exchange","scout_gate")
YEARS=(0,2025,2026)
SHARDS=4
REPS=2
CAP=12.0
SCOUT=0.055
MAX_LEAN_LEMMAS=16

def require(v,msg):
    if not v:raise RuntimeError("R88V2_FAIL_CLOSED "+str(msg))
def sha(p):return base.sha(p)
def dump(path,v):Path(path).write_text(json.dumps(v,sort_keys=True,indent=2)+"\n")

def header_probe(path):
    """Bounded deterministic source-only census; no timed solving/label leaks."""
    start=time.monotonic()
    n=m=None;seen=0;binary=horn=0
    with Path(path).open(encoding="ascii",errors="strict") as f:
        for line in f:
            s=line.strip()
            if not s or s.startswith(("c","%")):continue
            if s.startswith("p "):
                q=s.split()
                require(len(q)==4 and q[1]=="cnf" and n is None,"bad source header")
                n=int(q[2]);m=int(q[3])
                continue
            require(n is not None,"header missing")
            lits=[int(x) for x in s.split()]
            # A complete original clause may span multiple lines in DIMACS.
            # This probe is strictly advisory: ambiguous formatting -> no gate.
            if not lits or lits[-1]!=0 or 0 in lits[:-1]:
                return dict(eligible=False,reason="multiline_or_multi_clause",
                    elapsed_s=time.monotonic()-start,n=n,m=m)
            clause=lits[:-1]
            seen+=1;binary+=len(clause)==2;horn+=sum(x>0 for x in clause)<=1
            if seen>=2000:break
    require(n is not None and m is not None,"source header absent")
    binary_share=binary/max(1,seen)
    horn_share=horn/max(1,seen)
    # Predefined structural hypotheses; not selected using solved times.
    eligible=(Path(path).stat().st_size>=131072 and n>=256 and m>=1500
        and seen>=200 and (binary_share>=.50 or horn_share>=.86))
    reason=("structural_candidate" if eligible else "low_value_or_uncertain_structure")
    return dict(eligible=eligible,reason=reason,n=n,m=m,seen=seen,
        sample_binary_fraction=round(binary_share,5),
        sample_horn_fraction=round(horn_share,5),
        elapsed_s=time.monotonic()-start)

def select_useful(clauses,raw,stats,cap=MAX_LEAN_LEMMAS):
    """Filter original/tautological/uncertified-broadcast-noise; never invent lemmas.

    Each retained lemma is from the old source-subset+earlier certified broadcast
    RUP chain; original formula logically implies the whole chain. Dropping any
    individually entailed lemma preserves SAT/UNSAT equivalence.
    """
    origin={tuple(sorted(set(c),key=lambda x:(abs(x),x))) for c in clauses
            if c and not any(-x in c for x in c)}
    ledger=stats["proof_chain"]
    require(len(ledger)==len(raw),"cross-group proof ledger must be 1:1")
    rank=[];seen=set();drop=collections.Counter()
    for entry,lemma in zip(ledger,raw):
        tup=tuple(lemma)
        require(tuple(entry["lemma"])==tup and entry["bcp_verified"],
                "RUP ledger drift")
        if tup in origin:
            drop["already_original"]+=1;continue
        if len(tup)>2:
            drop["wide"]+=1;continue
        if tup in seen:
            drop["duplicate"]+=1;continue
        if not entry["causal_cross_group"] and not entry["prior_shared"]:
            drop["no_demonstrated_reception"]+=1;continue
        seen.add(tup)
        # Causal cross-reason first, then binary and unit, deterministic ties.
        rank.append((not entry["causal_cross_group"],len(tup),tup,entry))
    rank.sort(key=lambda r:(r[0],r[1],r[2]))
    selected=[r[2] for r in rank[:cap]]
    drop["budgeted_out"]=max(0,len(rank)-cap)
    return selected,dict(removed=dict(drop),causal_kept=sum(
        e["causal_cross_group"] for _,_,_,e in rank[:cap]),
        selected=len(selected),certified_raw=len(raw))

def save_augmented(n,clauses,extras,path):
    # Stream instead of duplicating the whole original CNF clause list.
    with Path(path).open("w") as f:
        f.write(f"p cnf {n} {len(clauses)+len(extras)}\n")
        for clause in clauses:
            f.write(" ".join(map(str,clause))+" 0\n")
        for clause in extras:
            f.write(" ".join(map(str,clause))+" 0\n")

def prepare(n,clauses,parse_cost,mode,path):
    t=time.monotonic()
    if mode=="legacy_corrected":
        extras,stats=base.cooperative_learn(clauses,max_lemmas=48,rounds=3)
        filtering={"selected":len(extras),"certified_raw":len(extras),
                   "causal_kept":stats["causal_cross_group_lemmas"],
                   "removed":{}}
    elif mode=="lean_exchange":
        raw,stats=base.cooperative_learn(clauses,max_lemmas=16,rounds=2)
        extras,filtering=select_useful(clauses,raw,stats)
    else:raise RuntimeError("unknown preparation")
    if extras:
        save_augmented(n,clauses,extras,path)
    # If no beneficial output, reuse the pristine source and skip CNF rewrite.
    preparation= time.monotonic()-t+parse_cost
    return dict(mode=mode,extras=extras,path=Path(path) if extras else None,
       prep_s=preparation,learn_s=time.monotonic()-t,
       stats={k:v for k,v in stats.items() if k!="proof_chain"},
       filtering=filtering)

def score(result,extra_s=0,stage="none",scout=None,gate=None,prep=None):
    wall=extra_s+result.get("wall_s",0)
    answered=result.get("answer","TIMEOUT")
    solved=answered in ("SAT","UNSAT") and wall<=CAP
    return dict(answer=answered if solved else "TIMEOUT",
      solved=solved,wall_s=round(min(CAP,wall),6),
      par2_s=round(wall if solved else 2*CAP,6),
      prep_s=round(extra_s,6),stage=stage,scout=scout,gate=gate,
      proof_lemmas=(len(prep["extras"]) if prep else 0),
      causal_kept=(prep["filtering"]["causal_kept"] if prep else 0),
      removed=(prep["filtering"]["removed"] if prep else {}),
      model_verified=solved and answered=="SAT")

def solve_budget(exe,path,original,preparation=0):
    if preparation>=CAP:
        return dict(answer="TIMEOUT",wall_s=0,par2_s=2*CAP)
    return base.solve(exe,path,original,CAP-preparation,native=False)

def one(mode,source,compiled,probe,preps):
    clean=compiled/"clean"
    if mode=="clean":
        return score(solve_budget(clean,source),stage="original")
    if mode in ("legacy_corrected","lean_exchange"):
        p=preps[mode]
        return score(solve_budget(clean,p["path"] or source,source,p["prep_s"]),
            p["prep_s"],stage=mode,prep=p)
    if mode!="scout_gate":raise RuntimeError("invalid mode")
    begin=time.monotonic()
    scout=base.solve(clean,source,source,SCOUT,native=False)
    scout_s=time.monotonic()-begin
    if scout["answer"] in ("SAT","UNSAT"):
        return score(scout,0,stage="fast_clean_scout",
                     scout={"wall_s":round(scout_s,6),"solved":True},gate=None)
    eligibility=bool(probe["eligible"])
    probe_s=probe["elapsed_s"]
    used=scout_s+probe_s
    if not eligibility:
        return score(solve_budget(clean,source,source,used),used,
            stage="no_cooperation_original_fallback",
            scout={"wall_s":round(scout_s,6),"solved":False},
            gate={k:v for k,v in probe.items() if k!="elapsed_s"})
    p=preps["lean_exchange"]
    used+=p["prep_s"]
    return score(solve_budget(clean,p["path"] or source,source,used),used,
        stage="scout_then_structurally_gated_lean",
        scout={"wall_s":round(scout_s,6),"solved":False},
        gate={k:v for k,v in probe.items() if k!="elapsed_s"},prep=p)

def measure(a):
    root=Path(a.sources).resolve()
    mf=json.loads((root/"manifest.json").read_text())
    require(mf["protocol"]==SOURCE_PROTO and mf["year"]==a.year and
       mf["shard"]==a.shard and len(mf["cases"])==5,
       "wrong exact original 2025/2026/archive source cohort")
    compiled=Path(a.compiled).resolve()
    require(subprocess.run(["sha256sum","-c","r87-binaries.sha256"],
        cwd=compiled,capture_output=True).returncode==0,"pinned base binary checksum drift")
    clean=compiled/"clean"
    require(clean.exists() and os.access(clean,os.X_OK),"missing original clean Kissat")
    if hasattr(os,"sched_setaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    rows=[];provenance=dict(proto=PROTO,source_manifest_sha256=sha(root/"manifest.json"),
        source_year=a.year,source_shard=a.shard,pinned_clean_sha256=sha(clean),
        runner=os.environ.get("RUNNER_NAME"),commit=os.environ.get("GITHUB_SHA"),
        run_id=os.environ.get("GITHUB_RUN_ID"))
    for case in mf["cases"]:
        source=root/case["filename"]
        require(sha(source)==case["sha256"],"original CNF SHA mismatch")
        parse_start=time.monotonic()
        n,clauses=base.read_cnf(source)
        parse_s=time.monotonic()-parse_start
        # Fingerprint is analytical metadata, NOT an input to gate or a hidden
        # cost for any solver; full replay source fingerprints were frozen.
        meta=base.fingerprint(n,clauses)
        probe=header_probe(source)
        with tempfile.TemporaryDirectory() as temp:
            preps={}
            for mode in ("legacy_corrected","lean_exchange"):
                preps[mode]=prepare(n,clauses,parse_s,mode,
                                    Path(temp)/(mode+".cnf"))
            for rep in range(REPS):
                modes=list(MODES)
                random.Random(int(hashlib.sha256((PROTO+case["sha256"]+str(rep))
                         .encode()).hexdigest(),16)).shuffle(modes)
                for mode in modes:
                    r=one(mode,source,compiled,probe,preps)
                    label=case.get("official_status","UNKNOWN")
                    if label in ("SAT","UNSAT") and r["answer"]!="TIMEOUT":
                        require(r["answer"]==label,
                            "published verified original SAT2026 outcome violated")
                    row=dict(source_sha=case["sha256"],source_id=case["gbd"],
                      year=case["year"],group=meta["structure"],rep=rep,mode=mode,
                      verified_source_status=label,
                      source_selection_reused_R88v1=True,
                      **meta,**r)
                    rows.append(row)
                    dump(out/"results.json",dict(**provenance,rows=rows))
                    print("R88V2_TRIAL",json.dumps(dict(year=a.year,shard=a.shard,
                      source=case["gbd"],mode=mode,rep=rep,answer=r["answer"],
                      par2=r["par2_s"],prep=r["prep_s"],stage=r["stage"],
                      lemmas=r["proof_lemmas"],causal=r["causal_kept"])),flush=True)
    require(len(rows)==5*REPS*len(MODES),"incomplete paired cohort")
    print("R88V2_SHARD_PASS",a.year,a.shard,len(rows),flush=True)

def audit(a):
    sources=Path(a.sources);res=Path(a.combined);records=[]
    bins=set();sha_ids=set();meta_sha=[]
    for year in YEARS:
        for shard in range(SHARDS):
            tag=f"{year}-{shard}"
            source_root=sources/("r88-sources-"+tag)/"sources"
            manifest=source_root/"manifest.json"
            require(manifest.exists(),"missing original source manifest "+tag)
            orig=json.loads(manifest.read_text())
            require(orig["protocol"]==SOURCE_PROTO and orig["year"]==year and
                    orig["shard"]==shard and len(orig["cases"])==5,
                    "wrong original manifest")
            for c in orig["cases"]:
                require(sha(source_root/c["filename"])==c["sha256"],
                        "source SHA mismatch "+tag)
                require(c["sha256"] not in sha_ids,"cross-shard duplicated source SHA")
                sha_ids.add(c["sha256"])
            p=res/("r88v2-results-"+tag)/"results"/"results.json"
            require(p.exists(),"missing completed comparison "+tag)
            item=json.loads(p.read_text())
            require(item["proto"]==PROTO and
                    item["source_manifest_sha256"]==sha(manifest),
                    "source/protocol altered "+tag)
            require(item["source_year"]==year and item["source_shard"]==shard,
                    "wrong shard mapping")
            require(item["runner"] and item["commit"] and item["run_id"],
                    "missing independent run provenance")
            bins.add(item["pinned_clean_sha256"])
            require(len(item["rows"])==5*REPS*len(MODES),
                    "incomplete paired result "+tag)
            for c in orig["cases"]:
                for rep in range(REPS):
                    xs=[r for r in item["rows"] if
                        r["source_sha"]==c["sha256"] and r["rep"]==rep]
                    require(len(xs)==len(MODES) and
                        {r["mode"] for r in xs}==set(MODES),"unpaired modes")
                    require(all(r["answer"] in ("SAT","UNSAT","TIMEOUT")
                       and 0<=r["wall_s"]<=CAP and
                       0<=r["prep_s"] and
                       (r["par2_s"]==2*CAP if r["answer"]=="TIMEOUT"
                        else r["par2_s"]<=CAP)
                       for r in xs),"invalid global budget or PAR2")
                    require(len({r["answer"] for r in xs if
                        r["answer"]!="TIMEOUT"})<=1,"SAT/UNSAT solver contradiction")
            records.extend(item["rows"])
            meta_sha.append(sha(manifest))
    require(len(bins)==1 and len(records)==60*REPS*len(MODES)
       and len(sha_ids)==60,"incomplete independent source/solver identity")
    groups={}
    for label, subset in [("ALL",records),
                          ("ARCHIVE_2002_2024",[r for r in records if r["year"]==0]),
                          ("SAT2025",[r for r in records if r["year"]==2025]),
                          ("SAT2026",[r for r in records if r["year"]==2026])]:
        groups[label]={}
        for mode in MODES:
            x=[r for r in subset if r["mode"]==mode]
            groups[label][mode]=dict(trials=len(x),
                solved=sum(r["answer"]!="TIMEOUT" for r in x),
                par2_s=round(sum(r["par2_s"] for r in x),6),
                prep_s=round(sum(r["prep_s"] for r in x),6),
                broadcast_lemmas=sum(r["proof_lemmas"] for r in x),
                causal_cross_kept=sum(r["causal_kept"] for r in x))
    by_source=collections.defaultdict(dict)
    for r in records:
        k=(r["source_sha"],r["mode"])
        by_source[k].setdefault("times",[]).append(r["par2_s"])
    distinct={r["source_sha"] for r in records}
    source_deltas={}
    rng=random.Random(882114)
    for mode in MODES[1:]:
        deltas=[(sum(by_source[s,"clean"]["times"])/REPS
                 -sum(by_source[s,mode]["times"])/REPS) for s in sorted(distinct)]
        boot=sorted(sum(deltas[rng.randrange(len(deltas))]
                     for _ in deltas)/len(deltas) for _ in range(3000))
        source_deltas[mode]=dict(mean_saved_s=round(statistics.mean(deltas),6),
            paired_source_bootstrap_95ci_s=[round(boot[74],6),round(boot[2924],6)])
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    summary=dict(protocol=PROTO,status="PASS_DEVELOPMENT_REPLAY_NOT_FRESH",
       total_trials=len(records),independent_sources=len(sha_ids),
       binary_sha256=next(iter(bins)),source_manifest_sha256=meta_sha,
       groups=groups,paired_bootstrap=source_deltas,
       claim="No generalization claim: old R88.1 formulas, 12s cap includes entire preparation and solver.",
       limitations=["Same 60 original sources selected by prior R88.1 run; development replay only.",
       "No timeout may score as solved after preprocess pushes wall above 12s.",
       "RUP-certified subset+broadcast lemmas preserve original SAT semantics; SAT witness original check.",
       "2025 UNSAT results lack independent UNSAT proof; official competition ranking not tested.",
       "All performance measures are pinned GitHub single-core runner measurements.",
       "Raw per-row output in separate SQLite and JSON; do not overwrite old R88 database."])
    dump(out/"r88v2-final.json",summary)
    with (out/"r88v2-paired.csv").open("w",newline="") as f:
        cols=("source_sha","source_id","year","group","rep","mode",
             "answer","par2_s","prep_s","stage","proof_lemmas","causal_kept")
        w=csv.DictWriter(f,fieldnames=cols);w.writeheader()
        for row in records:w.writerow({k:row[k] for k in cols})
    db=sqlite3.connect(out/"r88v2_knowledge.sqlite")
    db.executescript("""
      CREATE TABLE benchmark (
       source_sha TEXT NOT NULL, source_id TEXT, year INTEGER, group_name TEXT,
       repetition INTEGER NOT NULL, mode TEXT NOT NULL,
       answer TEXT, par2_s REAL, prep_s REAL, stage TEXT,
       proof_lemmas INTEGER, causal_kept INTEGER,
       PRIMARY KEY(source_sha,repetition,mode));
      CREATE TABLE provenance (key TEXT PRIMARY KEY,value TEXT NOT NULL);
      """)
    db.executemany("INSERT INTO benchmark VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
      [(r["source_sha"],r["source_id"],r["year"],r["group"],
         r["rep"],r["mode"],r["answer"],r["par2_s"],r["prep_s"],
         r["stage"],r["proof_lemmas"],r["causal_kept"]) for r in records])
    db.execute("INSERT INTO provenance VALUES (?,?)",("protocol",PROTO))
    db.execute("INSERT INTO provenance VALUES (?,?)",("binary_sha256",next(iter(bins))))
    db.commit();db.close()
    lines=["# R88.2 calibrated cooperative knowledge report","",
       "**Development replay of known R88.1 sources; not blind new evidence.**",
       "All four modes share one honest 12-second end-to-end per-attempt budget.",
       "Timeout penalty 24 seconds, not 24s + preprocessing cost.",
       "", "| Group | Mode | Solved | PAR-2 (s) | Preprocessing (s) | Shared lemmas |",
       "|---|---|---:|---:|---:|---:|"]
    for group,bundle in groups.items():
        for mode,z in bundle.items():
            lines.append(f"| {group} | {mode} | {z['solved']}/{z['trials']} "
                f"| {z['par2_s']:.3f} | {z['prep_s']:.3f} | {z['broadcast_lemmas']} |")
    lines+=["","## Paired bootstrap at source level"]
    lines += [f"- {k}: {v}" for k,v in source_deltas.items()]
    lines+=["","## Limitations"]+["- "+v for v in summary["limitations"]]
    (out/"r88v2-report.md").write_text("\n".join(lines)+"\n")
    print("R88V2_FULL_DEVELOPMENT_AUDIT_PASS",len(records),
          json.dumps(groups["ALL"],sort_keys=True),flush=True)

def selftest():
    require(len(MODES)==4 and CAP==12 and REPS==2,"fixed protocol drift")
    one=[(1,2),(-1,3),(1,),(-3,)]
    n=3
    # All local RUP checks still required on every emitted lemma.
    raw,stats=base.cooperative_learn(one,max_lemmas=16,rounds=2)
    selected,meta=select_useful(one,raw,stats)
    require(len(selected)<=16 and
       all(base.bcp_conflict(one+raw[:i],tuple(-x for x in item["lemma"]))
           for i,item in enumerate(stats["proof_chain"])),
        "source/broadcast RUP proof chain inconsistent")
    # Ineligible empty/small CNF must never mutate original CNF.
    require(not select_useful(one,[],{"proof_chain":[]})[0],
            "empty cooperative batch must remain empty")
    require(score({"answer":"SAT","wall_s":11.95},.1)["answer"]=="TIMEOUT",
            "solver beyond inclusive preparation budget wrongly counted as solved")
    require(score({"answer":"TIMEOUT","wall_s":12},.15)["par2_s"]==24,
            "timeout penalty incorrectly includes preprocessing")
    print("R88V2_SINGLE_GLOBAL_12S_CAP_AND_SAFE_FALLBACK_SELFTEST_PASS",len(selected))

if __name__=="__main__":
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest="command",required=True)
    sub.add_parser("selftest")
    m=sub.add_parser("measure")
    for x in ("sources","compiled","out"):m.add_argument("--"+x,required=True)
    m.add_argument("--year",type=int,required=True);m.add_argument("--shard",type=int,required=True)
    a=sub.add_parser("audit")
    for x in ("sources","combined","out"):a.add_argument("--"+x,required=True)
    args=p.parse_args()
    if args.command=="selftest":selftest()
    elif args.command=="measure":measure(args)
    else:audit(args)
