#!/usr/bin/env python3
"""X5.7 CHB scheduling follow-up: fresh-to-REAL36 original SAT2024 CNFs.

Original SAT Competition 2024 archive, no random/synthetic formula generator.
Source selection is fixed by archive name + compressed size *before* solver runs.
Exclude all 36 original REAL36 names + raw SHAs, select up to 12
scheduling-related sources and 8 other-family controls (20 total).
These are fresh *relative to X57 REAL36*, NOT globally blind; other
project experiments may have used SAT2024 originals.
"""
from __future__ import annotations
import argparse,bz2,collections,gzip,hashlib,json,lzma,os,pathlib,random,re,subprocess,tempfile,time
import drnas_x55_cpu_real36 as B

ARCHIVE="https://zenodo.org/records/15095752/files/sat-competition-2024-main-benchmarks.zip?download=1"
ROOT=pathlib.Path("x57_sched_unseen")
CASES=ROOT/"cases"
ORIGINAL_PRIOR=pathlib.Path("real36_previous/real36_final/manifest.json")
SHARDS=4
REPS=2
CAP=15.0
ARMS=("VSIDS","CHB","LRB","KISSAT","CADICAL")
BINARY={"VSIDS":"build/drnas-x57","CHB":"build/drnas-x57","LRB":"build/drnas-x57",
        "KISSAT":"build/kissat","CADICAL":"build/cadical"}
MAX_RAW=12_000_000
LOW_COMP=2_000
HIGH_COMP=350_000
SELECTION_SEED=571714

def h(b):return hashlib.sha256(b).hexdigest()
def emit(tag,obj):print(tag+" "+json.dumps(obj,sort_keys=True,separators=(",",":")),flush=True)
def dump(path,obj):
    path=pathlib.Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,sort_keys=True,indent=2)+"\n")

def filename(path):return pathlib.PurePosixPath(path).name
def schedule_family(name):
    name=filename(name).lower()
    if name.startswith(("worker_","worker-")):return "scheduling-worker"
    if name.startswith(("break_","break-")):return "scheduling-break"
    if "pcmax-scheduling" in name or "pcmax_scheduling" in name:return "scheduling-pcmax"
    if re.search(r"job.?shop|flow.?shop|rcpsp|time.?tab|open.?shop|resource.?sched|project.?sched",name):
        return "scheduling-other-filename"
    return None
def name_family(path):
    s=filename(path).lower()
    s=re.sub(r"\.cnf(?:\.(?:xz|bz2|gz))?$","",s)
    s=s.replace(".sanitized","")
    s=re.sub(r"\d+","#",s)
    s=re.sub(r"[_\-.]+","-",s).strip("-")
    return s

def select_zip_members(members,old):
    previous_names={x["filename"] for x in old}|{x["archive_entry"] for x in old}
    eligible=[e for e in members
              if not e.is_dir()
              and e.filename.lower().endswith((".cnf",".cnf.xz",".cnf.gz",".cnf.bz2"))
              and LOW_COMP<=e.file_size<=HIGH_COMP
              and filename(e.filename) not in previous_names]
    schedule=collections.defaultdict(list)
    control=collections.defaultdict(list)
    for e in eligible:
        sf=schedule_family(e.filename)
        if sf:schedule[sf].append(e)
        else:control[name_family(e.filename)].append(e)
    for v in schedule.values():v.sort(key=lambda e:(e.file_size,e.filename))
    for v in control.values():v.sort(key=lambda e:(e.file_size,e.filename))
    # Group targets are frozen ahead of evaluation, not based on SAT labels.
    target={"scheduling-worker":4,"scheduling-break":4,"scheduling-pcmax":4}
    def candidates_for(group,q):
        arr=schedule.get(group,[])
        if not arr:return []
        if len(arr)<=q:return arr[:]
        # Select compressed-size quantiles across the family, not quick solves.
        indices=sorted(set(min(len(arr)-1,((2*k+1)*len(arr))//(2*q)) for k in range(q)))
        return [arr[i] for i in indices]
    chosen=[]
    for cat,quota in target.items():
        chosen.extend((e,cat) for e in candidates_for(cat,quota))
    chosen_names={e.filename for e,_ in chosen}
    # Scheduling-adjacent fallback fills missing slots from genuinely named
    # scheduling groups. If too few exist, reserve remaining slots for controls;
    # the manifest reports true counts and never labels controls as scheduling.
    extra=[(e,cat) for cat,v in schedule.items() for e in v
           if e.filename not in chosen_names]
    extra.sort(key=lambda t:(h((str(SELECTION_SEED)+t[0].filename).encode()),t[0].filename))
    for e,cat in extra:
        if len(chosen)>=12:break
        chosen.append((e,cat))
    if len(chosen)<3:
        raise RuntimeError(f"Only {len(chosen)} filename-identifiable scheduling original CNFs; refuse mislabeled benchmark")
    # Controls from diverse name families only, ranked by compressed size
    # strata. Never inspect a previous SAT result to pick controls.
    group_reps=[min(group,key=lambda e:(abs(e.file_size-30_000),e.filename))
                for group in control.values()]
    group_reps.sort(key=lambda e:(e.file_size,e.filename))
    count=20-len(chosen)
    if len(group_reps)<count:
        raise RuntimeError(f"insufficient non-scheduling distinct filename families: {len(group_reps)} < {count}")
    indexes=[min(len(group_reps)-1,((2*i+1)*len(group_reps))//(2*count))
             for i in range(count)]
    if len(set(indexes))!=count:raise RuntimeError("duplicate quantiles")
    chosen.extend((group_reps[i],"control-other-filename") for i in indexes)
    assert len(chosen)==20 and len({e.filename for e,_ in chosen})==20
    # Spread scheduling/control across source shards (round-robin by group).
    q=collections.defaultdict(list)
    for e,cat in chosen:q[cat].append((e,cat))
    for k in q:q[k].sort(key=lambda a:(a[0].file_size,a[0].filename))
    ordered=[]
    groups=sorted(q)
    while any(q.values()):
        for g in groups:
            if q[g]:ordered.append(q[g].pop(0))
    assert len(ordered)==20
    return ordered,{"eligible":len(eligible),"scheduling_candidates":{k:len(v) for k,v in schedule.items()},
                    "control_name_families":len(group_reps),"selected_sched":sum(x[1]!="control-other-filename" for x in ordered),
                    "selected_control":sum(x[1]=="control-other-filename" for x in ordered)}

def decode(info,content):
    name=info.filename.lower()
    if name.endswith(".xz"):
        dec=lzma.LZMADecompressor()
        raw=dec.decompress(content,max_length=MAX_RAW+1)
        if len(raw)>MAX_RAW or not dec.eof:raise RuntimeError("too-large xz decompression")
    elif name.endswith(".bz2"):raw=bz2.decompress(content)
    elif name.endswith(".gz"):raw=gzip.decompress(content)
    else:raw=content
    if len(raw)>MAX_RAW:raise RuntimeError("source exceeds MAX_RAW")
    if not re.search(rb"(?m)^p cnf [0-9]+ [0-9]+",raw):raise RuntimeError("no DIMACS p cnf header")
    return raw

def prepare():
    from remotezip import RemoteZip
    old=json.loads(ORIGINAL_PRIOR.read_text())
    assert len(old)==36 and len({x["sha256"] for x in old})==36
    previous={x["sha256"] for x in old}
    CASES.mkdir(parents=True,exist_ok=True)
    with RemoteZip(ARCHIVE,timeout=120) as archive:
        selection,inventory=select_zip_members(archive.infolist(),old)
        emit("X57_SCHED_SELECTION",inventory)
        sources=[]
        for index,(entry,category) in enumerate(selection):
            raw=decode(entry,archive.read(entry))
            sha=h(raw)
            if sha in previous:raise RuntimeError("SHA-overlap with previous REAL36!")
            if any(x["sha256"]==sha for x in sources):raise RuntimeError("duplicate new formula SHA")
            n,clauses=B.parse_cnf(raw)
            if n<1 or len(clauses)<1:raise RuntimeError("invalid DIMACS dimensions")
            filename_on_disk=f"{index:03d}_{sha[:16]}.cnf"
            path=CASES/filename_on_disk
            path.write_bytes(raw)
            src={"id":index,"sha256":sha,"source_name":filename(entry.filename),
                 "archive_entry":entry.filename,
                 "family":category,"nvars":n,"nclauses":len(clauses),
                 "raw_bytes":len(raw),"archive_zip_member_bytes":entry.file_size,
                 "path":str(path),"selection_type":"metadata_only_before_any_solver"}
            sources.append(src);emit("X57_SCHED_SOURCE",src)
    m={
       "schema":"x57-sched-original-v1","official_archive":ARCHIVE,
       "selection_seed":SELECTION_SEED,
       "old_x57_run":43418696306,
       "prior_REAL36_SHA_count":len(previous),
       "previous_manifest_sha256":h(ORIGINAL_PRIOR.read_bytes()),
       "source_count":len(sources),"source_selection":inventory,
       "global_novelty_guaranteed":False,
       "blind_globally":False,
       "new_to_REAL36":True,
       "difficulty_screened_by_runtime":False,
       "difficulty_is_metadata_proxy_only":True,
       "source_sha256":[x["sha256"] for x in sources],
       "sources":sources
    }
    dump(ROOT/"manifest.json",m)
    emit("X57_SCHED_PREPARE_COMPLETE",{"sources":len(sources),
        "scheduling_count":inventory["selected_sched"],
        "control_count":inventory["selected_control"],
        "manifest_sha256":h((ROOT/"manifest.json").read_bytes())})

def verified_sources():
    m=json.loads((ROOT/"manifest.json").read_text())
    assert m["schema"]=="x57-sched-original-v1" and m["source_count"]==20
    assert [v["sha256"] for v in m["sources"]]==m["source_sha256"]
    for x in m["sources"]:
        p=pathlib.Path(x["path"])
        assert p.exists() and h(p.read_bytes())==x["sha256"]
    return m["sources"],m

def freeze():
    sources,m=verified_sources()
    conf={
        "schema":"x57-sched-freeze-v1","archive":ARCHIVE,
        "source_manifest_sha256":h((ROOT/"manifest.json").read_bytes()),
        "source_sha256":[x["sha256"] for x in sources],
        "binary_sha256":{arm:h(pathlib.Path(path).read_bytes()) for arm,path in BINARY.items()},
        "arms":list(ARMS),"cap_s":CAP,"shards":SHARDS,"repeats":REPS,
        "total_trials":20*REPS*len(ARMS),"proof_output_cap_bytes":512*1024*1024,
        "fixed_heuristics":"VSIDS CHB LRB policy binary from x57 completed run",
        "cpu":"one logical CPU per solver, serial arms, shuffled order",
        "verification":"independent SAT witness on original CNF; independent drat-trim for UNSAT",
        "no_promotion":True,"globally_blind":False,
        "same_formula_grouping":"two repetitions treated as one source cluster",
    }
    dump(ROOT/"protocol.json",conf)
    emit("X57_SCHED_FREEZE",conf)

def trial(source,arm,rep,temp):
    file=pathlib.Path(source["path"]);raw=file.read_bytes()
    if h(raw)!=source["sha256"]:raise RuntimeError("CNF source modified")
    n,clauses=B.parse_cnf(raw)
    stdout,stderr,usage,proof=(temp/x for x in ("stdout","stderr","usage","proof.drat"))
    for f in (stdout,stderr,usage,proof):f.unlink(missing_ok=True)
    if arm in ("VSIDS","CHB","LRB"):
        cmd=[BINARY[arm],str(file),"--mode","core","--time",str(CAP),
             "--stats","--proof",str(proof),"--x52-proof-deletions",
             "--x53-policy","baseline","--x53-progress",
             "--x57-branch",arm.lower()]
    elif arm=="KISSAT":cmd=[BINARY[arm],str(file),str(proof)]
    else:cmd=[BINARY[arm],"-q","--no-binary",str(file),str(proof)]
    rc,wall,expired,rss,cpu=B.run_process(cmd,stdout,stderr,usage,CAP+0.3)
    out=stdout.read_text(errors="replace");err=stderr.read_text(errors="replace")
    x57={};native={};progress=[]
    for line in err.splitlines():
        if line.startswith("X57_STATS "):
            try:x57=json.loads(line.split(" ",1)[1])
            except json.JSONDecodeError:pass
        if line.startswith("X41_STATS "):
            try:native=json.loads(line.split(" ",1)[1])
            except json.JSONDecodeError:pass
        if line.startswith("X57_PROGRESS "):
            try:progress.append(json.loads(line.split(" ",1)[1]))
            except json.JSONDecodeError:pass
    if arm in ("VSIDS","CHB","LRB") and not expired and rc in (0,10,20):
        if not x57 or x57["requested"]!=arm or x57["fallback"]:
            raise RuntimeError(f"expected {arm}, received {x57}")
    status="timeout" if expired else "UNKNOWN"
    check_s=0.0
    if not expired:
        if rc==10:
            if not B.check_sat(out,clauses,n):
                raise RuntimeError(f"INCORRECT SAT witness: {source['id']} {arm}")
            status="SAT_VERIFIED"
        elif rc==20:
            status="UNSAT_UNVERIFIED"
            if proof.exists() and proof.stat().st_size>0:
                tick=time.perf_counter()
                try:
                    ck=subprocess.run(["build/drat-trim",str(file),str(proof)],
                        capture_output=True,text=True,timeout=18)
                    check_s=time.perf_counter()-tick
                    if ck.returncode==0 and "s VERIFIED" in ck.stdout:
                        status="UNSAT_CERTIFIED"
                    elif ck.returncode==0:
                        raise RuntimeError("Verifier success but missing 'VERIFIED' assertion")
                    else:
                        raise RuntimeError(f"REJECTED UNSAT proof id={source['id']} arm={arm}: {ck.stdout[-450:]} {ck.stderr[-450:]}")
                except subprocess.TimeoutExpired:
                    check_s=time.perf_counter()-tick
                    status="UNSAT_CHECK_TIMEOUT"
        elif rc==153 and proof.exists() and proof.stat().st_size==512*1024*1024:
            status="PROOF_FILE_LIMIT"
        elif rc!=0:
            raise RuntimeError(f"process failure: id={source['id']} arm={arm}, returncode={rc}: {err[-400:]}")
    accepted=wall<=CAP and status in ("SAT_VERIFIED","UNSAT_CERTIFIED")
    return {
      "id":source["id"],"family":source["family"],"source_sha256":source["sha256"],
      "source_name":source["source_name"],"rep":rep,"arm":arm,
      "status":status,"accepted":accepted,
      "PAR2_s":round(wall if accepted else 2*CAP,6),
      "solve_e2e_s":round(wall,6),"cpu_s":cpu,"maxrss_kib":rss,
      "proof_check_s":round(check_s,6),"proof_bytes":proof.stat().st_size if proof.exists() else 0,
      "proof_limit":status=="PROOF_FILE_LIMIT",
      "stats":native,"learning":x57,"last_progress":progress[-1] if progress else {},
      "progress_samples":len(progress)
    }

def shard(index):
    sources,m=verified_sources()
    conf=json.loads((ROOT/"protocol.json").read_text())
    assert conf["source_sha256"]==[x["sha256"] for x in sources]
    assert conf["source_manifest_sha256"]==h((ROOT/"manifest.json").read_bytes())
    for arm,path in BINARY.items():
        if h(pathlib.Path(path).read_bytes())!=conf["binary_sha256"][arm]:
            raise RuntimeError(f"binary hash changed {arm}")
    chosen=[x for x in sources if x["id"]%SHARDS==index]
    assert len(chosen)==5
    path=pathlib.Path("x57_sched_shards")/str(index)
    path.mkdir(parents=True,exist_ok=False)
    with tempfile.TemporaryDirectory() as d,(path/"trials.jsonl").open("w") as fd:
        temp=pathlib.Path(d)
        for source in chosen:
            for rep in range(REPS):
                order=list(ARMS)
                random.Random(SELECTION_SEED+source["id"]*53+rep).shuffle(order)
                for arm in order:
                    row=trial(source,arm,rep,temp)
                    fd.write(json.dumps(row,sort_keys=True,separators=(",",":"))+"\n");fd.flush()
                    emit("X57_SCHED_TRIAL",{
                        k:row[k] for k in ("id","family","rep","arm","status","accepted",
                                         "PAR2_s","solve_e2e_s","cpu_s","maxrss_kib")})
                emit("X57_SCHED_PROGRESS",{"shard":index,"id":source["id"],"rep":rep})
    dump(path/"report.json",{
         "shard":index,"source_sha256":[x["sha256"] for x in chosen],
         "source_manifest_sha256":conf["source_manifest_sha256"],
         "binary_sha256":conf["binary_sha256"],"trials":len(chosen)*REPS*len(ARMS)})
    emit("X57_SCHED_SHARD_FINAL",{"shard":index,"trials":len(chosen)*REPS*len(ARMS)})

def totals(rows):
    result={}
    for arm in ARMS:
        rr=[r for r in rows if r["arm"]==arm]
        result[arm]={
          "attempts":len(rr),"solved":sum(r["accepted"] for r in rr),
          "SAT_verified":sum(r["accepted"] and r["status"]=="SAT_VERIFIED" for r in rr),
          "UNSAT_certified":sum(r["accepted"] and r["status"]=="UNSAT_CERTIFIED" for r in rr),
          "PAR2_s":round(sum(r["PAR2_s"] for r in rr),6),
          "wall_s":round(sum(r["solve_e2e_s"] for r in rr),6),
          "cpu_s":round(sum(r["cpu_s"] or 0 for r in rr),6),
          "cpu_missing":sum(r["cpu_s"] is None for r in rr),
          "proof_check_s":round(sum(r["proof_check_s"] for r in rr),6),
          "maxrss_kib":max((r["maxrss_kib"] or 0 for r in rr),default=0),
          "score_updates":sum((r["learning"] or r["last_progress"]).get("score_updates",0) for r in rr),
          "decisions":sum((r["stats"] or r["last_progress"]).get("decisions",0) for r in rr),
          "conflicts":sum((r["stats"] or r["last_progress"]).get("conflicts",0) for r in rr),
        }
    return result

def comparison(rows,baseline,candidate,metric):
    grouped=collections.defaultdict(list)
    for row in rows:grouped[row["source_sha256"]].append(row)
    deltas=[]
    for source,items in sorted(grouped.items()):
        a=[x for x in items if x["arm"]==baseline]
        b=[x for x in items if x["arm"]==candidate]
        assert len(a)==len(b)==REPS
        if any(x[metric] is None for x in a+b):
            return {"available":False,"reason":"missing CPU; no zero imputation"}
        deltas.append(sum(x[metric] for x in b)-sum(x[metric] for x in a))
    rng=random.Random(SELECTION_SEED)
    draws=sorted(sum(rng.choices(deltas,k=len(deltas))) for _ in range(4000))
    return {
      "available":True,"delta_candidate_minus_reference_s":round(sum(deltas),6),
      "source_cluster_bootstrap95":[round(draws[100],6),round(draws[3899],6)],
      "source_clusters":len(deltas),"repeats_per_source":REPS}

def finish():
    sources,manifest=verified_sources()
    conf=json.loads((ROOT/"protocol.json").read_text())
    assert conf["source_manifest_sha256"]==h((ROOT/"manifest.json").read_bytes())
    rows=[]
    for shard_index in range(SHARDS):
        directory=pathlib.Path("x57_sched_downloads")/f"x57sched-shard-{shard_index}"
        report=json.loads((directory/"report.json").read_text())
        assert report["shard"]==shard_index
        assert report["binary_sha256"]==conf["binary_sha256"]
        assert report["source_manifest_sha256"]==conf["source_manifest_sha256"]
        batch=[json.loads(x) for x in (directory/"trials.jsonl").read_text().splitlines()]
        assert len(batch)==report["trials"]==50
        assert {x["source_sha256"] for x in batch}==set(report["source_sha256"])
        rows.extend(batch)
    expected={(x["sha256"],r,a) for x in sources for r in range(REPS) for a in ARMS}
    actual={(x["source_sha256"],x["rep"],x["arm"]) for x in rows}
    assert len(rows)==len(expected)==200 and actual==expected
    for src in sources:
        answers={x["status"][:3] for x in rows if x["source_sha256"]==src["sha256"] and x["accepted"]}
        assert len(answers)<=1,("contradictory verified SAT/UNSAT status",src["id"],answers)
    groups={"all":lambda x:True,
            "scheduling_filename":lambda x:x["family"].startswith("scheduling-"),
            "control_other":lambda x:x["family"]=="control-other-filename"}
    category={}
    for name,pred in groups.items():
        subset=[x for x in rows if pred(x)]
        category[name]={
           "source_count":len({x["source_sha256"] for x in subset}),
           "arms":totals(subset),
           "CHB_minus_VSIDS":comparison(subset,"VSIDS","CHB","PAR2_s"),
           "LRB_minus_VSIDS":comparison(subset,"VSIDS","LRB","PAR2_s")}
    by_family={f:{
       "source_count":len({x["source_sha256"] for x in rows if x["family"]==f}),
       "arms":totals([x for x in rows if x["family"]==f]),
       "CHB_minus_VSIDS":comparison([x for x in rows if x["family"]==f],"VSIDS","CHB","PAR2_s")}
       for f in sorted(set(x["family"] for x in rows))}
    report={
       "status":"COMPLETE","protocol":conf,"source_manifest":manifest,
       "groups":category,"by_family":by_family,
       "per_formula":[{
          "id":src["id"],"filename":src["source_name"],"family":src["family"],
          "sha256":src["sha256"],
          "arms":totals([r for r in rows if r["source_sha256"]==src["sha256"]])
       } for src in sources],
       "limitations":[
        "SAT Competition 2024 examples are new only relative to X57 REAL36, NOT globally blind.",
        "Scheduling category is assigned from source filename, not a verified semantic ontology.",
        "Medium difficulty is a metadata size stratification, not selected by solve runtime.",
        "All SAT need original CNF model verification; UNSAT needs independent DRAT.",
        "All scores fixed before new data, no policy tuning during evaluation.",
        "Two repetitions of one original source count as one cluster.",
        "No automatic promotion without distinct, unexposed family-disjoint validation."
       ]
    }
    out=pathlib.Path("x57_sched_final");out.mkdir(exist_ok=True)
    dump(out/"report.json",report)
    (out/"paired_trials.jsonl").write_text("".join(json.dumps(x,sort_keys=True)+"\n" for x in rows))
    emit("X57_SCHED_FINAL",{"status":"COMPLETE","groups":category,"by_family":by_family})

def main():
    p=argparse.ArgumentParser()
    p.add_argument("stage",choices=("prepare","freeze","shard","finish"))
    p.add_argument("--shard",type=int,default=0)
    args=p.parse_args()
    {"prepare":prepare,"freeze":freeze,"shard":lambda:shard(args.shard),"finish":finish}[args.stage]()

if __name__=="__main__":main()
