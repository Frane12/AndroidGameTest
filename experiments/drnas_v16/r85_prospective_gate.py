#!/usr/bin/env python3
"""R85: prospective SHA-disjoint official-original test of the frozen R83 structural gate.

R83 is DEVELOPMENT, not blind evidence. This code and selection salt are frozen
BEFORE R85 trials. It reuses the same SHA-pinned clean/native Kissat binaries,
native soundness checks and exact GF(2) source-span verifier from R83.
No V15.3.1 solver or heuristics are changed.
"""
from __future__ import annotations
import argparse, collections, csv, hashlib, io, json, os, random, subprocess
from pathlib import Path
import r82_wide_official_2025_2026 as src
import r83_live_xor_cdcl_wide as native

PROTO="DRNAS-R85-PROSPECTIVE-SHA-DISJOINT-R83-GATE-20261104-v2"
SALT="DRNAS-R85-FROZEN-BEFORE-ANY-R85-SOLVE-20261104-v1"
MODES=("clean_pinned","passive_native","active_native","r83_structural_gate","kissat_404")
CAP=25.0
REPS=2
SHARDS=8
TARGET={2025:20,2026:4}
TRIES={2025:115,2026:100}

def check(ok,why):
    if not ok: raise RuntimeError("R85_FAIL_CLOSED "+str(why))

def digest(p): return native.sha(p)
def dump(p,obj):
    Path(p).write_text(json.dumps(obj,indent=2,sort_keys=True)+"\n")

def priors(a):
    paths={k:Path(getattr(a,"old"+k))/"manifest.json"
           for k in ("82","63","66","67","73","81")}
    for k,p in paths.items():check(p.is_file(),"missing old provenance "+k)
    ms={k:json.loads(p.read_text()) for k,p in paths.items()}
    check(len(ms["82"]["cases"])==48 and ms["82"]["protocol"]==src.PROTO,
          "R82 prior source cohort not frozen")
    registered=set(ms["63"]["excludes_previously_seen_gbd"])
    for k in ("63","66","67","81"):
        m=ms[k]
        registered.update(x["gbd"] for x in m["cases"])
        registered.update(x["gbd"] for x in m.get("selection_attempts",m.get("attempts",[]))
                          if "gbd" in x)
    previous_sha=set()
    previous_ids=set()
    for k,m in ms.items():
        previous_sha.update(x["sha256"] for x in m["cases"] if "sha256" in x)
        previous_ids.update(x["gbd"] for x in m["cases"] if "gbd" in x)
        previous_ids.update(x["gbd"] for x in
            m.get("source_selection_attempts",m.get("selection_attempts",m.get("attempts",[])))
            if "gbd" in x)
    previous_ids.update(registered)
    return ms,paths,registered,previous_sha,previous_ids

def freeze(a):
    ms,paths,registered,used_sha,used_ids=priors(a)
    root=Path(a.out);root.mkdir(parents=True,exist_ok=True)
    index25=src.r52.fetch_bytes(src.r73.SC2025,100000)
    index26=src.r52.fetch_bytes(src.r52.URI,100000)
    scores=src.r52.fetch_bytes(src.r52.SCORES,32*1024*1024)
    check(hashlib.sha256(index25).hexdigest()==ms["82"]["index_2025_sha256"],
          "official 2025 index drift")
    check(hashlib.sha256(index26).hexdigest()==ms["82"]["index_2026_sha256"],
          "official 2026 index drift")
    check(hashlib.sha256(scores).hexdigest()==ms["82"]["scores_2026_reference_sha256"],
          "2026 externally verified labels drift")
    ids25=[v.rsplit("/",1)[-1] for v in index25.decode().splitlines() if v.strip()]
    ids26=[v.rsplit("/",1)[-1] for v in index26.decode().splitlines() if v.strip()]
    check(len(ids25)>=300 and len(ids25)==len(set(ids25)),"2025 official index size")
    check(len(ids26)==400 and len(set(ids26))==400,"2026 official index size")
    labels={x["instanceid"]:x["status"] for x in csv.DictReader(io.StringIO(scores.decode()))
            if x["solverid"]=="biere_cadical3[main]"}
    check(len(labels)==400,"2026 verification table size")
    # Reproduce R82's documented R72 possible-attempt exclusion, then add R82
    # attempted identifiers and SHA from all available prior source manifests.
    old_r72_salt="DRNAS-R72-NEW-SHA-AND-ATTEMPT-DISJOINT-20261103-v1"
    candidates=sorted((g for g in ids25 if g not in registered and g not in set(ids26)),
        key=lambda g:hashlib.sha256((old_r72_salt+":"+g).encode()).hexdigest())
    used_ids.update(candidates[:100])
    selected=[];attempts=[];new_sha=set()
    src.r32p.CNF_LIMIT=48*1024*1024
    for year,all_ids in ((2025,ids25),(2026,ids26)):
        eligible=sorted((g for g in all_ids if g not in used_ids),
            key=lambda g:hashlib.sha256((SALT+"/"+str(year)+"/"+g).encode()).hexdigest())
        for g in eligible[:TRIES[year]]:
            if sum(c["year"]==year for c in selected)>=TARGET[year]:break
            ext=labels.get(g) if year==2026 else None
            note=dict(gbd=g,year=year)
            if year==2026 and ext not in ("sat-verified","unsat-verified"):
                note["state"]="SKIP_UNVERIFIED_2026";attempts.append(note);continue
            filename=str(year)+"-"+g+".cnf"
            target=root/filename
            try:
                packed,redirect=src.r32p.request_url(
                    "https://benchmark-database.de/file/"+g,24*1024*1024,seconds=30)
                plain,compression=src.r32p.decode(packed)
                check(len(plain)<=48*1024*1024,"decompressed source over 48MiB")
                n,clauses=src.r32p.parse_dimacs_metadata(plain)
                target.write_bytes(plain)
                h=digest(target)
                check(h not in used_sha and h not in new_sha,
                      "SHA previously benchmarked or collision")
                structure=src.r63.inspect_exact_xor(target,n,clauses)
                c=dict(gbd=g,year=year,filename=filename,sha256=h,
                       source_url="https://benchmark-database.de/file/"+g,
                       source_verified_status=(year==2026),
                       official_status=("SAT" if ext=="sat-verified" else
                                        "UNSAT" if ext=="unsat-verified" else "UNKNOWN"),
                       variables=n,clauses=clauses,bytes=len(plain),
                       compression=compression,original_redirect=redirect,
                       prior_drnas_benchmarked=False,**structure)
                c["group"]=src.r64.group(c)
                c["structural_xor_positive"]=bool(c["supported"] and
                                                  c["complete_blocks"] is not None and
                                                  c["complete_blocks"]>0)
                selected.append(c);new_sha.add(h)
                note.update(state="READY",sha256=h,group=c["group"],
                            gate_eligible=native.expected_gate(c))
            except Exception as e:
                target.unlink(missing_ok=True)
                note.update(state="SKIP_FETCH_SIZE_OR_AUDIT",
                            reason=(type(e).__name__+": "+str(e))[:210])
            attempts.append(note)
            print("R85_SOURCE",json.dumps(note,sort_keys=True),flush=True)
        print("R85_YEAR_READY",year,sum(x["year"]==year for x in selected),
              "of",TARGET[year],flush=True)
    check(len(selected)==24 and len(new_sha)==24,
          "strict freeze requires 20+4 SHA-distinct original sources")
    manifest=dict(protocol=PROTO,cohort="PROSPECTIVE_TEST",
       development="R83 already examined R82 sources, NOT reused here",
       source_indices_sha256={"2025":hashlib.sha256(index25).hexdigest(),
                              "2026":hashlib.sha256(index26).hexdigest()},
       scores_2026_sha256=hashlib.sha256(scores).hexdigest(),
       history_manifest_sha256={k:digest(p) for k,p in paths.items()},
       excluded_historical_gbd=len(used_ids),
       excluded_historical_source_sha=len(used_sha),
       selection_salt=SALT,selected_without_speed_xor_or_solver_screen=True,
       known_old_sha_overlap=0,source_attempts=attempts,
       cases=selected,year_counts={"2025":20,"2026":4},
       cap_s=CAP,repetitions=REPS,methods=MODES,shards=SHARDS,
       primary_claim=dict(gate="r83_structural_gate",reference="clean_pinned",
          min_cases=24,min_relative_par2_improvement=0.05,
          bootstrap_95pct_lower_saved_seconds_gt=0,
          no_fewer_solved=True),
       limitations=[
        "R83 gate was frozen from previously used R82 development sources.",
        "Pre-solve availability amendment: first freeze found only four eligible 2026 sources; changed year quotas 12+12 to 20+4 before any R85 solver trial, kept selection salt and all SHA exclusions.",
        "R85 new SHA and identifiers are disjoint from six recorded historical manifest sets and R72 exclusion; unrecorded work cannot be ruled out.",
        "2025 official labels are not independently imported; UNSAT lacks independent proof.",
        "2026 correct verdicts compared against published statuses, not a new UNSAT proof.",
        "No solver/XOR/timing screen; size/availability screen biases the official pool.",
        "Runtime structural gate scan is charged end-to-end inside a 25s cap.",
        "Each formula is one bootstrap unit; two repeats are not independent.",
        "R85 GitHub runner is not the SAT Competition and no world-record claim is possible."])
    dump(root/"manifest.json",manifest)
    (root/"source.sha256").write_text("".join(c["sha256"]+"  "+c["filename"]+"\n"
                                               for c in selected))
    print("R85_FREEZE_PASS",len(selected),digest(root/"manifest.json"),flush=True)

def paths_for(a):
    native_dir=Path(a.native).resolve()
    world=Path(a.world).resolve()
    for folder,checks in ((native_dir,"baselines.sha256"),(world,"binaries.sha256")):
        ck=subprocess.run(["sha256sum","-c",checks],cwd=folder,
                          stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True)
        check(ck.returncode==0,"pinned binary SHA mismatch: "+ck.stderr[-200:])
    p=dict(clean_pinned=native_dir/"clean",native=native_dir/"native",
           kissat_404=world/"kissat_4_0_4")
    check(all(f.is_file() and os.access(f,os.X_OK) for f in p.values()),
          "binary missing or not executable")
    return p

def measure(a):
    root=Path(a.sources);mf=json.loads((root/"manifest.json").read_text())
    check(mf["protocol"]==PROTO and len(mf["cases"])==24,"frozen R85 manifest")
    check(0<=a.shard<SHARDS,"shard")
    binaries=paths_for(a)
    if hasattr(os,"sched_setaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    native.CAP=CAP
    dest=Path(a.out);dest.mkdir(parents=True,exist_ok=True)
    rows=[];proof_cache={}
    for case in mf["cases"][a.shard::SHARDS]:
        original=root/case["filename"]
        check(digest(original)==case["sha256"],"original source sha")
        for rep in range(REPS):
            order=list(MODES)
            random.Random(int(hashlib.sha256(
                (PROTO+case["sha256"]+str(rep)).encode()).hexdigest(),16)).shuffle(order)
            for mode in order:
                out=native.run_one(mode,original,case,binaries,proof_cache)
                row=dict(gbd=case["gbd"],sha256=case["sha256"],
                         year=case["year"],group=case["group"],
                         rep=rep,mode=mode,runner=os.getenv("RUNNER_NAME",""),
                         run_id=os.getenv("GITHUB_RUN_ID",""),
                         commit=os.getenv("GITHUB_SHA",""),
                         seed=hashlib.sha256((PROTO+case["sha256"]+str(rep)).encode()).hexdigest(),
                         **out)
                rows.append(row)
                dump(dest/"shard.json",dict(protocol=PROTO,shard=a.shard,
                     manifest_sha=digest(root/"manifest.json"),
                     binary_sha={k:digest(v) for k,v in binaries.items()},
                     rows=rows))
                print("R85_TRIAL",json.dumps({k:row[k] for k in
                      ("gbd","rep","mode","answer","par2_s","gate_activated")}),
                      flush=True)
    check(len(rows)==len(mf["cases"][a.shard::SHARDS])*REPS*len(MODES),
          "missing per-shard paired trials")
    print("R85_SHARD_PASS",a.shard,len(rows),flush=True)

def audit(a):
    root=Path(a.sources);mf=json.loads((root/"manifest.json").read_text())
    check(mf["protocol"]==PROTO and len(mf["cases"])==24,"manifest")
    check({c["year"] for c in mf["cases"]}=={2025,2026},"year groups")
    cases={c["sha256"]:c for c in mf["cases"]}
    check(len(cases)==24,"duplicate source sha")
    for c in cases.values():check(digest(root/c["filename"])==c["sha256"],"SHA source")
    rows=[];pins=set()
    for shard in range(SHARDS):
        p=Path(a.combined)/("r85-shard-"+str(shard))/"results"/"shard.json"
        check(p.is_file(),"missing shard "+str(shard))
        j=json.loads(p.read_text())
        check(j["protocol"]==PROTO and j["shard"]==shard and
              j["manifest_sha"]==digest(root/"manifest.json"),"provenance mismatch")
        check(len(j["rows"])==len(mf["cases"][shard::SHARDS])*REPS*len(MODES),
              "incomplete measurement shard")
        pins.add(json.dumps(j["binary_sha"],sort_keys=True))
        rows+=j["rows"]
    check(len(pins)==1 and len(rows)==24*REPS*len(MODES),"inconsistent binary or count")
    pair=collections.defaultdict(dict)
    for r in rows:
        check(r["sha256"] in cases and r["rep"] in (0,1) and r["mode"] in MODES,
              "unknown source or method")
        k=(r["sha256"],r["rep"])
        check(r["mode"] not in pair[k],"duplicate row")
        pair[k][r["mode"]]=r
        check(r["runner"] and r["commit"] and r["run_id"] and r["seed"],"missing provenance")
        if cases[r["sha256"]]["source_verified_status"] and r["answer"]!="TIMEOUT":
            check(r["answer"]==cases[r["sha256"]]["official_status"],"official verdict conflict")
        check(r["native"]["original_parity_proof_checked"] or
              r["native"]["source_rows"]==0,"GF2 source proof absent")
        if r["mode"]=="r83_structural_gate":
            check(r["gate_activated"]==native.expected_gate(cases[r["sha256"]]),
                  "gate not frozen")
    check(len(pair)==24*REPS,"missing pairs")
    for p in pair.values():
        check(set(p)==set(MODES),"missing method")
        check(len({v["answer"] for v in p.values() if v["answer"]!="TIMEOUT"})<=1,
              "SAT/UNSAT method contradiction")
    summary={}
    for mode in MODES:
        q=[r for r in rows if r["mode"]==mode]
        summary[mode]=dict(solved=sum(r["solved"] for r in q),
                           trials=len(q),par2_s=round(sum(r["par2_s"] for r in q),6))
    grouped={}
    for label,cs in (("ALL",list(cases.values())),
                     ("2025",[c for c in cases.values() if c["year"]==2025]),
                     ("2026",[c for c in cases.values() if c["year"]==2026]),
                     ("GATE_ELIGIBLE",[c for c in cases.values() if native.expected_gate(c)]),
                     ("CONTROL",[c for c in cases.values() if not native.expected_gate(c)])):
        deltas=[]
        for c in cs:
            relevant=[pair[(c["sha256"],rep)] for rep in range(REPS)]
            deltas.append(sum(p["clean_pinned"]["par2_s"]-
                              p["r83_structural_gate"]["par2_s"] for p in relevant)/REPS)
        if not deltas:
            grouped[label]=dict(n=0,mean_saved_s=None,ci_95_s=None)
            continue
        rng=random.Random(int(hashlib.sha256((PROTO+label).encode()).hexdigest(),16))
        boot=sorted(sum(deltas[rng.randrange(len(deltas))]
                      for __ in range(len(deltas)))/len(deltas) for _ in range(3000))
        grouped[label]=dict(n=len(deltas),mean_saved_s=round(sum(deltas)/len(deltas),6),
             ci_95_s=[round(boot[74],6),round(boot[2924],6)])
    original=summary["clean_pinned"];gate=summary["r83_structural_gate"]
    relative=(original["par2_s"]-gate["par2_s"])/original["par2_s"]
    claim=bool(len(cases)==24 and relative>=0.05 and
               grouped["ALL"]["ci_95_s"][0]>0 and
               gate["solved"]>=original["solved"])
    dest=Path(a.out);dest.mkdir(parents=True,exist_ok=True)
    outcome=dict(protocol=PROTO,status="PASS_UNOFFICIAL",
       validated_sources=len(cases),validated_trials=len(rows),
       manifest_sha256=digest(root/"manifest.json"),
       binary_sha256=json.loads(next(iter(pins))),summary=summary,
       grouped_paired_bootstrap=grouped,
       relative_PAR2_saved_vs_clean=round(relative,8),
       prospective_primary_5pct_claim_pass=claim,
       inference="PRECOMMITTED_PRIMARY_CONFIRMED" if claim else "NO_PRECOMMITTED_PRIMARY_GAIN",
       limitations=mf["limitations"],rows=rows)
    dump(dest/"r85-final.json",outcome)
    with (dest/"r85-paired.csv").open("w",newline="") as f:
        w=csv.writer(f)
        w.writerow(["source_sha256","gbd","year","rep"]+list(MODES))
        for (h,rep),p in sorted(pair.items()):
            w.writerow([h,cases[h]["gbd"],cases[h]["year"],rep]+
                       [p[m]["par2_s"] for m in MODES])
    # Dependency-free scatter, one point per source and repeat, cap+PAR2 shown.
    dots=[]
    for p in pair.values():
        x=p["clean_pinned"]["par2_s"];y=p["r83_structural_gate"]["par2_s"]
        dots.append(f'<circle cx="{55+x*8:.2f}" cy="{475-y*8:.2f}" r="3" fill="#2563eb" fill-opacity=".6"/>')
    svg='<svg xmlns="http://www.w3.org/2000/svg" width="600" height="530" viewBox="0 0 600 530"><rect width="600" height="530" fill="white"/><path d="M55 75 V475 H455" fill="none" stroke="black"/><path d="M55 475 L455 75" stroke="#888" stroke-dasharray="4 4"/>'+''.join(dots)+'<text x="120" y="515" font-size="14">clean Kissat PAR2 seconds (lower is better)</text><text x="60" y="37" font-size="14">R85 gate PAR2 seconds; below diagonal = faster</text></svg>'
    (dest/"r85-scatter.svg").write_text(svg)
    lines=["# R85 prospective SHA-disjoint real-official test","",
        "24 new originals from 2025/2026 indices; 2 repeats; 5 paired methods.",
        "R83 source cohort is development, R85 is a prospective test relative to enumerated history.",
        "All analysis and gates are frozen before timing; 25s cap, timeout PAR2=50s.",
        "This is not a competition ranking or an independent UNSAT proof.","",
        "| Mode | Solved / 48 | PAR2 s |","|---|---:|---:|"]
    for m,s in summary.items():
        lines.append(f"| {m} | {s['solved']}/48 | {s['par2_s']:.3f} |")
    lines+=["",f"Relative PAR2 saved vs clean pinned: {relative*100:.4f}%",
            f"Precommitted >=5%, non-regression, lower-95%-CI criterion: **{'PASS' if claim else 'NOT MET'}**",
            "", "## Unique-source paired bootstrap"]
    for k,v in grouped.items():lines.append(f"- {k}: {v}")
    lines+=["","## Limitations"]+["- "+s for s in mf["limitations"]]
    (dest/"r85-final.md").write_text("\n".join(lines)+"\n")
    print("R85_FINAL_AUDIT_PASS",len(rows),json.dumps(summary),flush=True)
    print("R85_PRIMARY_CLAIM", "PASS" if claim else "NOT_CONFIRMED",flush=True)

def selftest():
    check(native.expected_gate(dict(supported=True,complete_blocks=2)),
          "gate changed from R83")
    check(not native.expected_gate(dict(supported=True,complete_blocks=1)),
          "gate boundary changed")
    check(CAP==25 and REPS==2 and len(MODES)==5,"protocol drift")
    print("R85_FROZEN_GATE_AND_DESIGN_SELFTEST_PASS")

def main():
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest="cmd",required=True)
    sub.add_parser("selftest")
    f=sub.add_parser("freeze")
    for k in ("out","old82","old63","old66","old67","old73","old81"):
        f.add_argument("--"+k,required=True)
    m=sub.add_parser("measure")
    for k in ("sources","native","world","out"):m.add_argument("--"+k,required=True)
    m.add_argument("--shard",type=int,required=True)
    a=sub.add_parser("audit")
    for k in ("sources","combined","out"):a.add_argument("--"+k,required=True)
    args=p.parse_args()
    if args.cmd=="selftest":selftest()
    elif args.cmd=="freeze":freeze(args)
    elif args.cmd=="measure":measure(args)
    else:audit(args)

if __name__=="__main__":main()
