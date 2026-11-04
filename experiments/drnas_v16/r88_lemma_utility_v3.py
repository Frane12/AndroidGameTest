#!/usr/bin/env python3
"""DRNAS R88.3: source-paired interventional cooperative clause-utility audit.

Known 60 original SAT competition CNFs from R88.2, development sample.
4 arms, same pinned Kissat -s statistics:
  clean: original CNF untouched
  placebo: original clauses duplicated to match number of certified lemmas
  certified16: <=16 short RUP-certified cross-community clauses
  certified8: <=8 prefix of the same predeclared ranking
Each attempt has a single 12s start-to-finish clock with prep charged.
Report completed-run conflicts/decisions/propagations AND full PAR2 incl timeout.
Causal effect of adding clauses is NOT inferred from "number of lemmas" alone.
Preserves prior branch, native compiler, and historical SQL. No world claims.
"""
from __future__ import annotations
import argparse, collections, csv, hashlib, json, os, random, re, sqlite3, statistics, subprocess, tempfile, time
from pathlib import Path
import r88_cooperative as old
import r88_cooperative_v2 as v2
import r32p_real_satcomp26_benchmark as original_sat

PROTO="DRNAS-R88V3-SOURCE-PAIRED-LEMMA-UTILITY-PLACEBO-20261104-v1"
SOURCE_PROTO="DRNAS-R88-BULK-OFFICIAL-CNF-20261104-v1"
YEARS=(0,2025,2026); SHARDS=4; REPS=2; CAP=12.0
MODES=("clean","placebo","certified16","certified8")
MAX_LEMMAS=16; MAX_ROUNDS=2

def guard(ok,msg):
    if not ok:raise RuntimeError("R88V3_FAIL_CLOSED "+str(msg))
def sha(p):return old.sha(p)
def persist(path,obj):Path(path).write_text(json.dumps(obj,sort_keys=True,indent=2)+"\n")

def stats_from_output(stdout):
    """Kissat -s output formats vary: accept both 'c 123 conflicts' and
    'c conflicts: 123' but never silently treat absent stats as zero."""
    counts={}
    for key in ("conflicts","decisions","propagations","restarts"):
        patterns=(rf"^\s*c\s+(\d[\d,]*)\s+{key}\b",
                  rf"^\s*c\s+{key}\s*:\s*(\d[\d,]*)\b",
                  rf"^\s*c\s+{key}\s+(\d[\d,]*)\b")
        found=[]
        for line in stdout.splitlines():
            for pattern in patterns:
                m=re.match(pattern,line,re.I)
                if m:
                    found.append(int(m.group(1).replace(",","")))
                    break
        counts[key]=found[-1] if found else None
    return counts

def checked_runtime(executable,cnf,original,charged_prep):
    if charged_prep>=CAP:
        return dict(answer="TIMEOUT",wall_s=CAP,par2_s=2*CAP,
                    stats=stats_from_output(""),stats_available=False,
                    original_sat_witness_verified=False)
    started=time.monotonic()
    code=None;stdout="";answer="TIMEOUT"
    try:
        p=subprocess.run([str(executable),"-s",str(cnf)],
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,
            text=True,errors="replace",
            timeout=max(.001,CAP-charged_prep),
            preexec_fn=old.memory_limit)
        code=p.returncode;stdout=p.stdout
        guard(code in (10,20),"pinned solver exit code "+str(code)+" "+
               p.stderr[-350:])
        answer="SAT" if code==10 else "UNSAT"
        if answer=="SAT":
            original_sat.verify_sat_witness(original,stdout)
    except subprocess.TimeoutExpired as e:
        answer="TIMEOUT"
    elapsed=time.monotonic()-started
    combined=charged_prep+elapsed
    if combined>CAP:answer="TIMEOUT"
    counters=stats_from_output(stdout if answer!="TIMEOUT" else "")
    return dict(answer=answer,wall_s=round(min(CAP,combined),6),
                par2_s=round(combined if answer!="TIMEOUT" else 2*CAP,6),
                stats=counters,
                stats_available=any(v is not None for v in counters.values()),
                original_sat_witness_verified=(answer=="SAT"))

def chosen_placebo(clauses,learned):
    """Match the number of added clauses, but add ONLY original clauses.
    Never fabricate constraints not entailed by original CNF."""
    if not learned:return []
    originals=collections.defaultdict(list)
    for c in clauses:
        if c and not any(-x in c for x in c):
            originals[len(c)].append(tuple(c))
    lengths=sorted(originals)
    guard(bool(lengths),"no original non-tautological clause available")
    duplicates=[]
    for i,c in enumerate(learned):
        length=min(lengths,key=lambda k:(abs(k-len(c)),k))
        arr=originals[length]
        duplicates.append(arr[i%len(arr)])
    return duplicates

def prepare(source,n,clauses,parse_s,temp):
    """Proof-bearing R88v2 learning, strict <=16, then <=8 nested ablation."""
    t=time.monotonic()
    raw,telemetry=old.cooperative_learn(clauses,
              max_lemmas=MAX_LEMMAS,rounds=MAX_ROUNDS)
    selected,selection=v2.select_useful(clauses,raw,telemetry,MAX_LEMMAS)
    t_learning=time.monotonic()-t
    # The original proof ledger is replayed in cooperative_learn(), and
    # v2.select_useful() checks each returned lemma's certified origin.
    # The nested 8-lemma subset cannot increase clause count/semantics.
    variants={}
    for arm,extras in (("certified16",selected),
                       ("certified8",selected[:8]),
                       ("placebo",chosen_placebo(clauses,selected))):
        started=time.monotonic()
        target=Path(temp)/(arm+".cnf")
        if extras:
            v2.save_augmented(n,clauses,extras,target)
            path=target
        else:
            path=source
        rewrite_s=time.monotonic()-started
        charge=parse_s+rewrite_s+(t_learning if arm!="placebo" else 0)
        variants[arm]=dict(path=path,charged_prep=charge,
            prep_parse_s=parse_s,prep_learn_s=t_learning if arm!="placebo" else 0,
            prep_write_s=rewrite_s,
            extra_count=len(extras),
            causal_kept=(selection["causal_kept"] if arm=="certified16" else
              sum(1 for e in telemetry["proof_chain"] if e["causal_cross_group"]
                  and tuple(e["lemma"]) in set(extras))
              if arm=="certified8" else 0),
            pre_certified=len(raw) if arm!="placebo" else 0,
            is_original_only_placebo=arm=="placebo",
            removed=selection["removed"] if arm!="placebo" else {})
    return variants

def measure(a):
    root=Path(a.sources).resolve()
    manifest=json.loads((root/"manifest.json").read_text())
    guard(manifest["protocol"]==SOURCE_PROTO and
          manifest["year"]==a.year and manifest["shard"]==a.shard and
          len(manifest["cases"])==5,"wrong frozen R88.2 original cohort")
    binaries=Path(a.compiled).resolve()
    pin=subprocess.run(["sha256sum","-c","r87-binaries.sha256"],
        cwd=binaries,capture_output=True,text=True)
    guard(pin.returncode==0,"binary SHA mismatch "+pin.stderr[-200:])
    clean=binaries/"clean"
    guard(clean.exists() and os.access(clean,os.X_OK),"clean baseline missing")
    if hasattr(os,"sched_setaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    output=Path(a.out);output.mkdir(parents=True,exist_ok=True)
    metadata=dict(protocol=PROTO,source_manifest_sha=sha(root/"manifest.json"),
       binary_sha=sha(clean),year=a.year,shard=a.shard,
       run_id=os.environ.get("GITHUB_RUN_ID"),runner=os.environ.get("RUNNER_NAME"),
       commit=os.environ.get("GITHUB_SHA"))
    rows=[]
    for c in manifest["cases"]:
        source=root/c["filename"]
        guard(sha(source)==c["sha256"],"CNF source SHA mismatch")
        started=time.monotonic()
        n,clauses=old.read_cnf(source)
        parsed=time.monotonic()-started
        feature=old.fingerprint(n,clauses)["structure"]
        with tempfile.TemporaryDirectory() as folder:
            prep=prepare(source,n,clauses,parsed,folder)
            for rep in range(REPS):
                modes=list(MODES)
                random.Random(int(hashlib.sha256(
                    (PROTO+c["sha256"]+str(rep)).encode()).hexdigest(),16)).shuffle(modes)
                for mode in modes:
                    spec=prep.get(mode)
                    charged=spec["charged_prep"] if spec else 0
                    solution=checked_runtime(clean,spec["path"] if spec else source,
                        source,charged)
                    status=c.get("official_status","UNKNOWN")
                    if status in ("SAT","UNSAT") and solution["answer"]!="TIMEOUT":
                        guard(status==solution["answer"],"published original status differs")
                    row=dict(source_id=c["gbd"],source_sha=c["sha256"],
                        year=c["year"],group=feature,rep=rep,mode=mode,
                        original_status=status,
                        original_2026_verified=(c["year"]==2026),
                        added_clauses=spec["extra_count"] if spec else 0,
                        causal_kept=spec["causal_kept"] if spec else 0,
                        prepared_certified=spec["pre_certified"] if spec else 0,
                        extra_parse_s=round(spec["prep_parse_s"],6) if spec else 0,
                        extra_learn_s=round(spec["prep_learn_s"],6) if spec else 0,
                        extra_write_s=round(spec["prep_write_s"],6) if spec else 0,
                        charged_prep_s=round(charged,6),
                        **solution)
                    rows.append(row)
                    persist(output/"rows.json",dict(**metadata,rows=rows))
                    print("R88V3_TRIAL",json.dumps(dict(yr=a.year,shard=a.shard,
                        id=c["gbd"],mode=mode,rep=rep,ans=solution["answer"],
                        par2=solution["par2_s"],prep=round(charged,4),
                        added=row["added_clauses"],stats=solution["stats"])),flush=True)
    guard(len(rows)==5*REPS*len(MODES),"missing paired trial")
    print("R88V3_SHARD_PASS",a.year,a.shard,len(rows),flush=True)

def audit(a):
    base_root=Path(a.sources);combined=Path(a.combined)
    rows=[];ids=set();binary_shas=set()
    for year in YEARS:
        for shard in range(SHARDS):
            tag=f"{year}-{shard}"
            folder=base_root/("r88-sources-"+tag)/"sources"
            man=folder/"manifest.json"
            guard(man.exists(),"missing source "+tag)
            m=json.loads(man.read_text())
            guard(m["protocol"]==SOURCE_PROTO and len(m["cases"])==5
                  and m["year"]==year and m["shard"]==shard,"source manifest drift")
            for c in m["cases"]:
                guard(sha(folder/c["filename"])==c["sha256"],"CNF original SHA differs")
                guard(c["sha256"] not in ids,"reused same source across different shards")
                ids.add(c["sha256"])
            path=combined/("r88v3-results-"+tag)/"results"/"rows.json"
            guard(path.exists(),"missing R88v3 paired source shard "+tag)
            j=json.loads(path.read_text())
            guard(j["protocol"]==PROTO and j["source_manifest_sha"]==sha(man)
                and j["year"]==year and j["shard"]==shard,
                "source or experimental protocol mismatch")
            guard(j["run_id"] and j["runner"] and j["commit"],"missing provenance")
            binary_shas.add(j["binary_sha"])
            guard(len(j["rows"])==5*REPS*len(MODES),"incomplete 4-arm paired result")
            for c in m["cases"]:
                for rep in range(REPS):
                    paired=[r for r in j["rows"] if
                        r["source_sha"]==c["sha256"] and r["rep"]==rep]
                    guard(len(paired)==len(MODES) and {r["mode"] for r in paired}==set(MODES),
                          "incomplete paired group")
                    guard(len({r["answer"] for r in paired if r["answer"]!="TIMEOUT"})<=1,
                          "SAT UNSAT contradiction")
                    guard(all(r["par2_s"]==2*CAP if r["answer"]=="TIMEOUT"
                           else 0<=r["par2_s"]<=CAP for r in paired),
                          "time cap not honored")
                    guard(all(r["added_clauses"]<=MAX_LEMMAS and
                          0<=r["charged_prep_s"] for r in paired),
                          "improper number or cost of certified clauses")
                    n={r["mode"]:r["added_clauses"] for r in paired}
                    guard(n["placebo"]==n["certified16"] and
                          n["certified8"]<=n["certified16"] and n["clean"]==0,
                          "placebo clause-count control invalid")
                    guard(all(r["original_2026_verified"]==(year==2026)
                         for r in paired),"original status provenance mismatch")
            rows+=j["rows"]
    guard(len(binary_shas)==1 and len(rows)==60*REPS*len(MODES)
          and len(ids)==60,"missing/duplicate original sources or pinned executables")
    groups={}
    for group,pool in (("ALL",rows),
         ("ARCHIVE",[r for r in rows if r["year"]==0]),
         ("SAT2025",[r for r in rows if r["year"]==2025]),
         ("SAT2026",[r for r in rows if r["year"]==2026])):
        groups[group]={}
        for mode in MODES:
            r=[x for x in pool if x["mode"]==mode]
            groups[group][mode]=dict(trials=len(r),
                solved=sum(x["answer"]!="TIMEOUT" for x in r),
                par2_s=round(sum(x["par2_s"] for x in r),6),
                prep_s=round(sum(x["charged_prep_s"] for x in r),6),
                extra_clauses=sum(x["added_clauses"] for x in r),
                counter_completions=sum(x["answer"]!="TIMEOUT" and
                    x["stats"]["conflicts"] is not None for x in r))
    pair={}
    for r in rows:
        pair.setdefault((r["source_sha"],r["mode"]),[]).append(r)
    boot={}
    rng=random.Random(883104)
    for m in MODES[1:]:
        differences=[(sum(x["par2_s"] for x in pair[s,"clean"])/REPS
                     -sum(x["par2_s"] for x in pair[s,m])/REPS) for s in sorted(ids)]
        drawn=sorted(sum(differences[rng.randrange(len(differences))]
                    for _ in differences)/len(differences) for __ in range(3000))
        boot[m]=dict(saved_mean_s_per_formula=round(statistics.mean(differences),6),
                     ci95_s=[round(drawn[74],6),round(drawn[2924],6)])
    effects={}
    for m in ("certified16","certified8"):
        samples=[]
        for s in sorted(ids):
            p=pair[s,"placebo"];l=pair[s,m]
            valid=[(a,b) for a,b in zip(p,l)
                if a["answer"]!="TIMEOUT" and b["answer"]!="TIMEOUT" and
                   a["stats"]["conflicts"] is not None and
                   b["stats"]["conflicts"] is not None]
            for aa,bb in valid:
                samples.append(dict(source=s,year=bb["year"],
                    conflicts_placebo=aa["stats"]["conflicts"],
                    conflicts_learned=bb["stats"]["conflicts"],
                    delta_conflicts=aa["stats"]["conflicts"]-bb["stats"]["conflicts"],
                    prop_placebo=aa["stats"]["propagations"],
                    prop_learned=bb["stats"]["propagations"],
                    decisions_placebo=aa["stats"]["decisions"],
                    decisions_learned=bb["stats"]["decisions"]))
        effects[m]=dict(complete_stat_pairs=len(samples),
            decreased_conflicts=sum(x["delta_conflicts"]>0 for x in samples),
            increased_conflicts=sum(x["delta_conflicts"]<0 for x in samples),
            equal_conflicts=sum(x["delta_conflicts"]==0 for x in samples),
            details=samples)
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    summary=dict(protocol=PROTO,status="PASS_DEVELOPMENT_COUNTERFACTUAL_ABLATION",
       source_count=len(ids),total_trials=len(rows),groups=groups,
       time_source_paired_bootstrap=boot,solver_only_stats_placebo_vs_certified=effects,
       binary_sha256=next(iter(binary_shas)),
       limits=["This cohort is the already exposed R88.2 60-case cohort, not unseen.",
       "Only RUP-certified clauses added; placebo duplicates original clauses.",
       "Statistical counter values only reported for completed runs, never inferred for timeout.",
       "Machine instrumentation -s may add overhead to all arms; not official competition.",
       "Kissat and augmented original CNF have matching original SAT witness verification.",
       "Source-paired comparisons do not prove that every chosen lemma is individually causal.",
       "No UNSAT proof certificate; published 2026 results verified, 2025 and older provisional.",
       "PAR2 timeout counts 24s. Every run includes own estimated cold-start prep cost.",
       "Shared preparation is calculated once per formula then charged separately to each attempt."])
    persist(out/"r88v3-final.json",summary)
    with (out/"r88v3-paired.csv").open("w",newline="") as csvf:
        keys=("source_sha","source_id","year","group","rep","mode",
              "answer","par2_s","charged_prep_s","added_clauses","causal_kept")
        writer=csv.DictWriter(csvf,fieldnames=keys);writer.writeheader()
        for row in rows:writer.writerow({k:row[k] for k in keys})
    db=sqlite3.connect(out/"r88v3_utility.sqlite")
    db.execute("CREATE TABLE results (source_sha TEXT, year INTEGER, rep INTEGER, mode TEXT, answer TEXT, par2 REAL, prep REAL, lemmas INTEGER, conflicts INTEGER, propagations INTEGER, decisions INTEGER, PRIMARY KEY(source_sha,rep,mode))")
    db.executemany("INSERT INTO results VALUES(?,?,?,?,?,?,?,?,?,?,?)",[
        (r["source_sha"],r["year"],r["rep"],r["mode"],r["answer"],r["par2_s"],
         r["charged_prep_s"],r["added_clauses"],
         r["stats"]["conflicts"],r["stats"]["propagations"],r["stats"]["decisions"])
        for r in rows])
    db.commit();db.close()
    report=["# R88.3 Cooperative utility against clause-count placebo",
       "", "Known-source development experiment: 60 originals x2 x4 =480 paired runs.",
       "Entire per-arm preprocessing plus solver is charged inside the 12s cap.",
       "Counter data only for completed solvers with printed Kissat -s stats.",
       "", "| Corpus | Method | Solved | PAR2 seconds | Prep seconds | Added clauses | Completed conflict counters |",
       "|---|---|---:|---:|---:|---:|---:|"]
    for group,modes in groups.items():
        for mode,z in modes.items():
            report.append(f"| {group} | {mode} | {z['solved']}/{z['trials']} | {z['par2_s']:.3f} | {z['prep_s']:.3f} | {z['extra_clauses']} | {z['counter_completions']} |")
    report+=["","## Original-source paired time bootstrap"]
    report +=[f"- {k}: {v}" for k,v in boot.items()]
    report+=["","## Counterfactual solver statistics placebo versus certified clauses"]
    report +=[f"- {k}: complete pairs={v['complete_stat_pairs']}, reduced conflicts={v['decreased_conflicts']}, increased conflicts={v['increased_conflicts']}, unchanged={v['equal_conflicts']}" for k,v in effects.items()]
    report+=["","## Limitations"]+["- "+x for x in summary["limits"]]
    (out/"r88v3-report.md").write_text("\n".join(report)+"\n")
    print("R88V3_FULL_AUDIT_PASS",len(rows),json.dumps(groups["ALL"],sort_keys=True),flush=True)

def selftest():
    guard(len(MODES)==4 and CAP==12 and REPS==2,"protocol changed")
    counters=stats_from_output("c conflicts: 123\nc 456 decisions\nc propagations: 789\n")
    guard(counters["conflicts"]==123 and counters["decisions"]==456
          and counters["propagations"]==789,
          "Kissat counter decoder must accept both output layouts")
    x=[(1,2),(-1,3),(1,)]
    guard(chosen_placebo(x,[(1,),(-1,2)])==[(1,), (-1,3)],
          "placebo must duplicate only original CNF")
    guard(chosen_placebo(x,[])==[],"empty learned set must no-op")
    guard(stats_from_output("")["conflicts"] is None,
          "missing stats cannot be interpreted as zero")
    print("R88V3_CLAUSE_COUNT_PLACEBO_AND_STATS_SELFTEST_PASS")

if __name__=="__main__":
    p=argparse.ArgumentParser(); sub=p.add_subparsers(dest="command",required=True)
    sub.add_parser("selftest")
    m=sub.add_parser("measure")
    for k in ("sources","compiled","out"):m.add_argument("--"+k,required=True)
    m.add_argument("--year",required=True,type=int);m.add_argument("--shard",required=True,type=int)
    a=sub.add_parser("audit")
    for k in ("sources","combined","out"):a.add_argument("--"+k,required=True)
    args=p.parse_args()
    if args.command=="selftest":selftest()
    elif args.command=="measure":measure(args)
    else:audit(args)
