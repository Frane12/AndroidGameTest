#!/usr/bin/env python3
"""R57 precommitted R56 short-binary-fraction hypothesis on new 2026 sources.

Discovery: R56 retrospective 9 R49-active formulas; selected binary_frac >
0.5210833 from sampled 1..4-literal clauses, with a standard R49 pivot gate.
Confirmation: new source IDs are SHA-disjoint from R32p/R32r/R52/R55b and
selected from official CaDiCaL status/time strata using a precommitted SALT,
never DRNAS outcomes. Single trial cap includes ALL preprocessing and SAT
witness check. Do not tune threshold on this cohort.
"""
from __future__ import annotations
import argparse,csv,hashlib,io,json,os,random,resource,subprocess,tempfile,time
from pathlib import Path
import r32p_real_satcomp26_benchmark as r32p
import r32r_more_real_satcomp26_benchmark as r32r
import r52_prospective_2026_toprefs as r52
import r49_pivot_coherence_gate as r49
import r47_partial_links as r47

PROTO="DRNAS-R57-STRUCTURAL-BINARY-GATE-BLIND2026-20261103-v1"
SALT="R57-BINARY-SIGNAL-PRECOMMITTED-20261103-INDEPENDENT"
THRESHOLD=0.5210833
CAP=40.0
REPS=2
SHARDS=6
MODES=("clean","r49_full40","r56_binary_gate40","cadical_3_0_1")
STRATA=("sat_fast","unsat_fast","sat_mid","unsat_mid")
PER_STRATUM=3
MAX_TRIES=16
MAX_COMPRESSED=28*1024*1024
MAX_UNCOMPRESSED=48*1024*1024
R52_RUN=41684183452
R55B_RUN=41691243486
def check(x,msg):
 if not x: raise RuntimeError("R57_AUDIT_FAIL "+str(msg))
def sha(x):return r52.digest(x)
def selection_hash(s):return hashlib.sha256((SALT+"/"+s).encode()).hexdigest()
def bin_feature(original):
 n,selected,trace=r47.sample_original(original)
 check(n is not None and selected,"no short original clauses")
 return round(sum(len(c)==2 for c in selected)/len(selected),7),len(selected)

def freeze(a):
 root=Path(a.out);root.mkdir(parents=True,exist_ok=True)
 old52=json.loads((Path(a.r52_sources)/"manifest.json").read_text())
 old55=json.loads((Path(a.r55b_sources)/"manifest.json").read_text())
 check(old52["protocol"]==r52.PROTO and len(old52["cases"])==11,"wrong R52 parents")
 check(old55["protocol"].startswith("DRNAS-R55B-") and len(old55["cases"])==11,"wrong R55b parents")
 old_ids=set(g for _,g in r32p.PINS)|set(g for _,g in r32r.PINS)
 check(len(old_ids)==37,"old exclusion registry changed")
 old_ids|={x["gbd"] for x in old52["cases"]}
 old_ids|={x["gbd"] for x in old55["cases"]}
 check(len(old_ids)==59,"overlap in earlier cohorts")
 official_list=r52.fetch_bytes(r52.URI,100000).decode().strip().splitlines()
 valid_ids=[s.rsplit("/",1)[-1] for s in official_list]
 check(len(valid_ids)==400 and len(set(valid_ids))==400,"official 2026 URI list drift")
 scoreboard=r52.fetch_bytes(r52.SCORES,32*1024*1024)
 raw=list(csv.DictReader(io.StringIO(scoreboard.decode("utf-8"))))
 data=[x for x in raw if x["solverid"]=="biere_cadical3[main]"
       and x["instanceid"] in valid_ids]
 check(len(data)==400,"official scoring rows changed")
 pools={q:[] for q in STRATA}
 for e in data:
  if e["instanceid"] in old_ids or e["status"] not in ("sat-verified","unsat-verified"):
   continue
  tm=float(e["runtime"])
  tier="fast" if 0<=tm<10 else "mid" if 10<=tm<80 else None
  if not tier:continue
  label=("sat" if e["status"]=="sat-verified" else "unsat")+"_"+tier
  pools[label].append(dict(gbd=e["instanceid"],status="SAT" if e["status"]=="sat-verified" else "UNSAT",
      official_seconds=tm))
 r32p.CNF_LIMIT=MAX_UNCOMPRESSED
 cases=[];download_log=[];attempted=set()
 for stratum in STRATA:
  ordered=sorted(pools[stratum],key=lambda x:selection_hash(stratum+"/"+x["gbd"]))
  found=0
  for candidate in ordered[:MAX_TRIES]:
   g=candidate["gbd"];check(g not in attempted,"cross-stratum duplicate");attempted.add(g)
   note=dict(gbd=g,stratum=stratum)
   path=root/(g+".cnf")
   try:
    packed,redirect=r32p.request_url("https://benchmark-database.de/file/"+g,
       MAX_COMPRESSED,seconds=65)
    cnf,compression=r32p.decode(packed)
    check(len(cnf)<=MAX_UNCOMPRESSED,"uncompressed size cap")
    n,m=r32p.parse_dimacs_metadata(cnf)
    path.write_bytes(cnf)
    plan=r49.compute_plan(path)
    ratio,samples=bin_feature(path)
    eligible=bool(plan["gate"] and ratio>THRESHOLD)
    source_sha=sha(path)
    check(source_sha not in {z.get("sha256",z.get("source_sha256")) for z in
       old52["cases"]+old55["cases"]},"reused original SHA")
    cases.append(dict(**candidate,filename=path.name,sha256=source_sha,
       compression=compression,bytes=len(cnf),vars=n,original_clauses=m,
       r49_gate=plan["gate"],derived=plan["derived"],
       certificate_sha256=plan["certificate_sha256"],
       sampled_short_clauses=samples,short_binary_ratio=ratio,
       r56_binary_gate=eligible))
    found+=1
    note.update(state="READY",ratio=ratio,derived=plan["derived"],
                eligible=eligible,sha256=source_sha)
   except Exception as e:
    path.unlink(missing_ok=True)
    note.update(state="EXCLUDED_SIZE_OR_PARSE",reason=str(e)[:300])
   download_log.append(note)
   print("R57_FREEZE_CANDIDATE",json.dumps(note),flush=True)
   if found>=PER_STRATUM:break
 check(8<=len(cases)<=12,"too few official new sources")
 check(len({x["sha256"] for x in cases})==len(cases),"duplicate SHA new source")
 manifest=dict(protocol=PROTO,selection_salt=SALT,
    threshold=THRESHOLD,
    disjoint_prior_sha_mani=[sha(Path(a.r52_sources)/"manifest.json"),
                            sha(Path(a.r55b_sources)/"manifest.json")],
    previous_ids=sorted(old_ids),
    source_url=r52.URI,score_url=r52.SCORES,
    mode_list=list(MODES),reps=REPS,shards=SHARDS,
    cap_s=CAP,choice_logic="R49 gate AND sampled two-literal fraction strictly > 0.5210833",
    selection_logic="Public official CaDiCaL SAT/UNSAT and runtime strata only",
    no_DRNAS_outcomes_for_source_selection=True,
    not_verified_against_entire_historical_project=True,
    not_world_ranking=True,
    cases=cases,download_log=download_log)
 (root/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
 (root/"source.sha256").write_text("".join(c["sha256"]+"  "+c["filename"]+"\n" for c in cases))
 print("R57_FROZEN_PASS",len(cases),"active_binary_gate",
       sum(c["r56_binary_gate"] for c in cases),
       "old_r49_gate",sum(c["r49_gate"] for c in cases),flush=True)

def capmem():
 resource.setrlimit(resource.RLIMIT_AS,(3*1024**3,3*1024**3))
def trial(original,case,kissat,cadical,mode):
 start=time.monotonic();candidate=original;added=0;status="TIMEOUT"
 with tempfile.TemporaryDirectory(prefix="drnas-r57-") as folder:
  if mode in ("r49_full40","r56_binary_gate40"):
   p=r49.compute_plan(original)
   check(p["certificate_sha256"]==case["certificate_sha256"] and
         p["derived"]==case["derived"] and p["gate"]==case["r49_gate"],
         "frozen proof or structure mismatch")
   if mode=="r56_binary_gate40":
    ratio,samples=bin_feature(original)
    check(ratio==case["short_binary_ratio"] and
          samples==case["sampled_short_clauses"],"features changed")
    active=bool(p["gate"] and ratio>THRESHOLD)
    check(active==case["r56_binary_gate"],"frozen selector drift")
   else:active=p["gate"]
   if active:
    selected=p["clauses"]
    added=len(selected)
    if selected:
     candidate=Path(folder)/"augmented.cnf"
     rw=r49.r48.safe_rewrite(original,candidate,selected)
     check(rw["added"]==added,"CNF rewrite count mismatch")
  prep=time.monotonic()-start
  if prep<CAP:
   cmd=cadical if mode=="cadical_3_0_1" else kissat
   try:
    p=subprocess.run([str(cmd),str(candidate)],capture_output=True,
        text=True,errors="replace",timeout=CAP-prep,preexec_fn=capmem)
    check(p.returncode in (10,20),"solver code "+str(p.returncode)+": "+p.stderr[-150:])
    status="SAT" if p.returncode==10 else "UNSAT"
    if status=="SAT":r32p.verify_sat_witness(original,p.stdout)
   except subprocess.TimeoutExpired:status="TIMEOUT"
  elapsed=time.monotonic()-start
 if elapsed>CAP:status="TIMEOUT"
 wall=round(min(elapsed,CAP),6)
 return dict(status=status,wall_s=wall,par2_s=round(wall if status!="TIMEOUT" else 80,6),
     prep_s=round(prep,6),added=added)

def measure(a):
 m=json.loads((Path(a.sources)/"manifest.json").read_text())
 check(m["protocol"]==PROTO and a.shard in range(SHARDS),"source manifest drift")
 origroot=Path(a.sources)
 if hasattr(os,"sched_setaffinity"):
  os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
 bins={k:Path(getattr(a,k)).resolve() for k in ("kissat","cadical")}
 check(all(x.is_file() for x in bins.values()),"pinned binaries missing")
 out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
 (out/"meta.json").write_text(json.dumps(dict(protocol=PROTO,shard=a.shard,
   source_sha=sha(origroot/"manifest.json"),kissat_sha=sha(bins["kissat"]),
   cadical_sha=sha(bins["cadical"])),indent=2)+"\n")
 rows=[]
 for c in m["cases"][a.shard::SHARDS]:
  original=origroot/c["filename"]
  check(sha(original)==c["sha256"],"original changed")
  for rep in range(REPS):
   order=list(MODES)
   random.Random(int(selection_hash(c["sha256"]+str(rep)),16)).shuffle(order)
   for mode in order:
    result=trial(original,c,bins["kissat"],bins["cadical"],mode)
    check(result["status"]=="TIMEOUT" or result["status"]==c["status"],
          "wrong SAT answer vs official")
    r=dict(gbd=c["gbd"],rep=rep,mode=mode,origin_sha=c["sha256"],**result)
    rows.append(r)
    print("R57_REAL2026_TRIAL",c["gbd"],"rep",rep,mode,result["status"],
          result["wall_s"],"PAR2",result["par2_s"],"added",result["added"],flush=True)
    (out/"rows.json").write_text(json.dumps(rows,indent=2)+"\n")
 check(len(rows)==len(m["cases"][a.shard::SHARDS])*REPS*len(MODES),
       "incomplete shard")

def audit(a):
 m=json.loads((Path(a.sources)/"manifest.json").read_text())
 check(m["protocol"]==PROTO,"wrong frozen protocol")
 rows=[];shas=set()
 for shard in range(SHARDS):
  folder=Path(a.combined)/("r57-shard-"+str(shard))/"results"
  meta=json.loads((folder/"meta.json").read_text())
  check(meta["protocol"]==PROTO and meta["shard"]==shard and
        meta["source_sha"]==sha(Path(a.sources)/"manifest.json"),
        "source or shard mismatch")
  shas.add((meta["kissat_sha"],meta["cadical_sha"]))
  part=json.loads((folder/"rows.json").read_text())
  check(len(part)==len(m["cases"][shard::SHARDS])*REPS*len(MODES),
        "incomplete shard records")
  rows+=part
 check(len(shas)==1 and len(rows)==len(m["cases"])*REPS*len(MODES),
       "binary mismatch or rows missing")
 stats={}
 for mode in MODES:
  x=[r for r in rows if r["mode"]==mode]
  stats[mode]=dict(attempts=len(x),solved=sum(r["status"]!="TIMEOUT" for r in x),
      PAR2_s=round(sum(r["par2_s"] for r in x),6),
      interventions=sum(r["added"]>0 for r in x))
 base=stats["clean"]["PAR2_s"]
 for v in stats.values():v["delta_pct"]=round(100*(v["PAR2_s"]/base-1),4)
 cases={}
 for c in m["cases"]:
  rr=[r for r in rows if r["gbd"]==c["gbd"]]
  check(len(rr)==REPS*len(MODES) and
        all(r["origin_sha"]==c["sha256"] for r in rr),"case missing or altered")
  assert all({r["mode"] for r in rr if r["rep"]==rep}==set(MODES) for rep in range(REPS))
  cases[c["gbd"]]=dict(selector_active=c["r56_binary_gate"],
      short_binary_ratio=c["short_binary_ratio"],derived=c["derived"],
      modes={mode:dict(times=[r["wall_s"] if r["status"]!="TIMEOUT" else "TO" for r in
                  sorted(rr,key=lambda z:z["rep"]) if r["mode"]==mode],
               par2=round(sum(r["par2_s"] for r in rr if r["mode"]==mode),6))
             for mode in MODES})
 report=dict(protocol=PROTO,total_trials=len(rows),cases_count=len(cases),
      gate_active=sum(c["r56_binary_gate"] for c in m["cases"]),
      old_gate_active=sum(c["r49_gate"] for c in m["cases"]),
      summary=stats,cases=cases,rows=rows,manifest=m,sha_binaries=next(iter(shas)),
      limitations=["Prospective within R32p/R32r/R52/R55b exclusion registry",
        "Selection has public CaDiCaL time-based stratification; not unbiased natural distribution",
        "Threshold is from tiny nine-source retrospective R56 analysis",
        "All preprocessing and witness checks included in 40 s cap",
        "Not benchmarked against winning SATComp 2026 binary",
        "Not a formal generality or world-record claim"])
 Path(a.json).write_text(json.dumps(report,indent=2)+"\n")
 lines=["# R57 prospective frozen binary-clause-ratio gate versus prior R49",
   f"{len(cases)} source-disjoint official 2026 originals, {len(rows)} paired attempts, two repeats, 40s cap.",
   "Rule fixed before timing: R49 gate AND sampled original short-clause binary fraction > 0.5210833.",
   "", "| Mode | Solved | PAR2 s | Delta vs clean | Activated trials |",
   "|---|---:|---:|---:|---:|"]
 for mode in MODES:
  v=stats[mode]
  lines.append(f'| {mode} | {v["solved"]}/{v["attempts"]} | {v["PAR2_s"]:.3f} | {v["delta_pct"]:+.2f}% | {v["interventions"]} |')
 lines+=["","## By original (two-attempt PAR2 in seconds)",
     "| Formula | Binary ratio | Gate active | "+" | ".join(MODES)+" |",
     "|---|---:|---|"+("|---:|"*len(MODES))]
 for c in m["cases"]:
  item=cases[c["gbd"]]
  lines.append(f'| {c["gbd"][:12]} | {item["short_binary_ratio"]:.3f} | {item["selector_active"]} | '+
     " | ".join(f'{item["modes"][mode]["par2"]:.3f}' for mode in MODES)+" |")
 lines+=["","Source chosen without checking any of the prospective DRNAS outcomes.",
   "Zero selector activations implies this cohort cannot establish benefit of proposed rule.",
   "Gate selection incurs its own measured preprocessing cost; abstain can still slow.",
   "No independent UNSAT LRAT certificate or world SAT solver comparison."]
 Path(a.md).write_text("\n".join(lines)+"\n")
 print("R57_FINAL_AUDIT_PASS",json.dumps(stats), "gate_active",
     report["gate_active"],"of",len(cases),flush=True)

if __name__=="__main__":
 p=argparse.ArgumentParser();sub=p.add_subparsers(dest="task",required=True)
 f=sub.add_parser("freeze")
 for s in ("r52_sources","r55b_sources","out"):f.add_argument("--"+s.replace("_","-"),required=True)
 t=sub.add_parser("measure")
 for s in ("sources","shard","kissat","cadical","out"):t.add_argument("--"+s,required=True)
 a=sub.add_parser("audit")
 for s in ("sources","combined","json","md"):a.add_argument("--"+s,required=True)
 args=p.parse_args()
 if args.task=="freeze":freeze(args)
 elif args.task=="measure":
  args.shard=int(args.shard);measure(args)
 else:audit(args)
