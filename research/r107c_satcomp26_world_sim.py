#!/usr/bin/env python3
"""R107C independent unofficial SAT Competition 2026 world-vs-native benchmark.

Uses REAL published SATComp2026 Main Track CNFs (GBD IDs pinned in R32p).
This is retrospective on a size-restricted sample; NOT an official ranking,
NOT a blind holdout, NOT equivalent to 5000s/32GB HoreKa.
No synthetic fallback. Winner is the *source-built official 2026 entrant* if available.
"""
from __future__ import annotations
import argparse,csv,hashlib,io,json,os,pathlib,random,resource,statistics,subprocess,sys,time,traceback
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/"experiments/drnas_v16"))
import r32p_real_satcomp26_benchmark as r32p
import r106_verify_solver as verify

PROTO="DRNAS-R107C-REAL-SATCOMP26-WORLD-SIM-20261104-V1"
MODES=("r107c_cadical","cadical_301","kissat_404","kissat_pinned","satcomp26_champion")
CAP=30.0
REPS=2
SHARDS=4
MAX_CNF=24*1024*1024
MAX_COMPRESSED=18*1024*1024
EXPECTED=14

def ensure(cond,message):
    if not cond:raise RuntimeError("R107C_WORLD_AUDIT "+message)
def digest(p):
    h=hashlib.sha256()
    with open(p,"rb") as f:
        for data in iter(lambda:f.read(1<<20),b""):h.update(data)
    return h.hexdigest()
def dump(p,obj):
    Path(p).parent.mkdir(parents=True,exist_ok=True)
    Path(p).write_text(json.dumps(obj,indent=2,sort_keys=True)+"\n")
def official_sources():
    uri="https://satcompetition.github.io/2026/downloads/track_main_2026.uri"
    scores_url="https://satcompetition.github.io/2026/downloads/scores.csv"
    index=r32p.request_url(uri,100000,seconds=40)[0].decode().splitlines()
    identifiers=[u.strip().rsplit("/",1)[-1] for u in index if u.strip()]
    ensure(len(identifiers)==400 and len(set(identifiers))==400,"official 2026 index changed")
    scores=r32p.request_url(scores_url,32*1024*1024,seconds=60)[0].decode()
    rows=[r for r in csv.DictReader(io.StringIO(scores)) if r["solverid"]=="biere_cadical3[main]"]
    ensure(len(rows)==400,"official 2026 score table incomplete")
    labels={r["instanceid"]:r["status"] for r in rows}
    return identifiers,labels,hashlib.sha256(scores.encode()).hexdigest()
def freeze(a):
    root=Path(a.out);root.mkdir(parents=True,exist_ok=True)
    identifiers,labels,score_sha=official_sources()
    r32p.CNF_LIMIT=MAX_CNF
    cases=[];attempts=[]
    ensure(len(r32p.PINS)==EXPECTED,"changed pre-registered source list")
    for position,(i,gbd) in enumerate(r32p.PINS):
        ensure(gbd in identifiers,"GBD source not in official 2026 index: "+gbd)
        label=labels[gbd]
        row=dict(index=i,gbd=gbd,official_status=label,source_url="https://benchmark-database.de/file/"+gbd)
        if label not in ("sat-verified","unsat-verified"):
            row.update(fetch_status="NO_VERIFIED_OFFICIAL_STATUS")
            attempts.append(row);continue
        try:
            raw,redirect=r32p.request_url(row["source_url"],MAX_COMPRESSED,seconds=40)
            plain,compression=r32p.decode(raw)
            ensure(len(plain)<=MAX_CNF,"native 24MiB CNF limit exceeded")
            nv,nc=r32p.parse_dimacs_metadata(plain)
            filename=gbd+".cnf"
            path=root/filename
            path.write_bytes(plain)
            row.update(filename=filename,sha256=digest(path),bytes=len(plain),
                       variables=nv,clauses=nc,compression=compression,
                       redirect=redirect,expected="SAT" if label=="sat-verified" else "UNSAT",
                       fetch_status="READY")
            cases.append(row)
        except Exception as e:
            row.update(fetch_status="EXCLUDED_SIZE_DOWNLOAD_FORMAT",
                       reason=(type(e).__name__+": "+str(e))[:250])
        attempts.append(row)
        print("R107C_WORLD_SOURCE",json.dumps(row,sort_keys=True),flush=True)
    ensure(len(cases)>=3,"not enough actual 2026 original CNFs available")
    ensure(len({c["sha256"] for c in cases})==len(cases),"duplicate sources")
    manifest=dict(protocol=PROTO,source="SAT Competition 2026 Main Track, official GBD URI",
        official_score_sha256=score_sha,official_score_url="https://satcompetition.github.io/2026/downloads/scores.csv",
        selection="Pinned R32p 14 IDs; 24MiB decoded CNF size cap; NO performance selection in R107C",
        known_prior_exposure="These R32p candidate IDs have been used in previous DRNAS work; NOT unseen",
        caps=dict(seconds=CAP,repeats=REPS,max_original_cnf_bytes=MAX_CNF,raw_fetch_cap=MAX_COMPRESSED),
        attempted=attempts,cases=cases)
    dump(root/"manifest.json",manifest)
    (root/"source.sha256").write_text("".join(c["sha256"]+"  "+c["filename"]+"\n" for c in cases))
    print("R107C_WORLD_FREEZE",len(cases),"official originals",flush=True)
def run_cmd(cmd,limit,cwd=None):
    start=time.perf_counter()
    try:
        def setlimits():
            resource.setrlimit(resource.RLIMIT_AS,(4*1024**3,4*1024**3))
        p=subprocess.run(cmd,cwd=cwd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
            text=True,errors="replace",timeout=max(0.02,limit),preexec_fn=setlimits)
        elapsed=time.perf_counter()-start
        return dict(returncode=p.returncode,stdout=p.stdout,stderr=p.stderr,
                    wall_s=elapsed,timed_out=False)
    except subprocess.TimeoutExpired:
        return dict(returncode=None,stdout="",stderr="",wall_s=limit,timed_out=True)
def check_manifest(root):
    m=json.loads((root/"manifest.json").read_text())
    ensure(m["protocol"]==PROTO,"unexpected manifest protocol")
    for case in m["cases"]:
        path=root/case["filename"]
        ensure(path.stat().st_size==case["bytes"] and digest(path)==case["sha256"],
               "source SHA changed: "+case["filename"])
    return m
def execute(a):
    root=Path(a.sources);binaries=Path(a.built).resolve();out=Path(a.out)
    out.mkdir(parents=True,exist_ok=True)
    m=check_manifest(root)
    ensure(Path(a.built,"bin/binaries.sha256").exists(),"pinned baseline provenance missing")
    ensure(Path(a.built,"bin/r107c_native").exists(),"native R107C missing")
    winner_path=binaries/"champion_run_script.txt"
    winner_available=winner_path.exists() and bool(winner_path.read_text().strip())
    ensure(winner_available or (binaries/"winner_unavailable.txt").exists(),
           "official 2026 champion provenance missing")
    selected=[c for n,c in enumerate(m["cases"]) if n%SHARDS==a.shard]
    ensure(selected,"empty shard")
    # Restrict the benchmark orchestrator AND all children to one CPU.
    cpus=sorted(os.sched_getaffinity(0))
    os.sched_setaffinity(0,{cpus[0]})
    baseline_commands={
        "cadical_301":str(binaries/"bin/cadical_3_0_1"),
        "kissat_404":str(binaries/"bin/kissat_4_0_4"),
        "kissat_pinned":str(binaries/"bin/kissat_pinned"),
    }
    for f in baseline_commands.values():ensure(Path(f).exists(),"missing solver binary "+f)
    results=[]
    for case in selected:
        source=(root/case["filename"]).resolve()
        # Charge entire C++ native prepass in every R107C trial, never amortize it.
        for rep in range(REPS):
            order=list(MODES)
            random.Random(case["sha256"]+"/"+str(rep)+"/R107C-WORLD").shuffle(order)
            clauses=None
            for mode in order:
                prep_s=0.0;prepass=None;test_source=source
                status="UNKNOWN";note="";sat_verified=False;xor_rows=0;proof_length=0
                if mode=="satcomp26_champion" and not winner_available:
                    status="UNAVAILABLE";note=(binaries/"winner_unavailable.txt").read_text()[:240]
                    solver_s=0.0
                else:
                    if mode=="r107c_cadical":
                        work=out/("prepass-"+str(case["index"])+"-"+str(rep))
                        work.mkdir(exist_ok=True)
                        test_source=(work/"out.cnf").resolve()
                        ev=work/"evidence.json"
                        pp=run_cmd([str(binaries/"bin/r107c_native"),str(source),
                                    str(test_source),str(ev)],CAP)
                        prep_s=pp["wall_s"]
                        if not pp["timed_out"] and pp["returncode"]==0:
                            prepass=json.loads(ev.read_text())
                            xor_rows=prepass["source_xors"]
                            proof_length=prepass["proof_length"]
                            if prepass["gf2_unsat"] and case["expected"]=="SAT":
                                raise RuntimeError("R107C false GF2 contradiction on SAT original")
                            if not prepass["gf2_unsat"]:
                                ensure(digest(source)==digest(test_source),"R107C changed input without proof")
                        else:
                            status="UNSUPPORTED"
                            note="R107C prepass timeout/error "+pp["stderr"][-200:]
                    if status=="UNKNOWN":
                        remaining=CAP-prep_s
                        if remaining<=0.02:
                            status="TIMEOUT";solver_s=0.0
                        else:
                            if mode=="satcomp26_champion":
                                rel=winner_path.read_text().strip()
                                script=(binaries/"official"/rel).resolve()
                                ensure(script.is_file() and str(script).startswith(str(binaries/"official/")),
                                       "invalid winner run.sh path")
                                cmd=["bash",str(script),str(source)]
                                cwd=script.parent
                            else:
                                name="cadical_301" if mode=="r107c_cadical" else mode
                                cmd=[baseline_commands[name],str(test_source)]
                                cwd=None
                            p=run_cmd(cmd,remaining,cwd=cwd)
                            solver_s=p["wall_s"]
                            if p["timed_out"]:
                                status="TIMEOUT"
                            else:
                                try:
                                    status=verify.status(p["stdout"],p["returncode"])
                                except Exception as exc:
                                    status="INVALID"
                                    note=(str(exc)+" | "+p["stderr"][-160:])[:250]
                                if status in ("SAT","UNSAT"):
                                    if status!=case["expected"]:
                                        raise RuntimeError("OFFICIAL VERDICT MISMATCH "+mode+" "+case["filename"]+
                                                           " got "+status+" expected "+case["expected"])
                                    if status=="SAT":
                                        if clauses is None:clauses=verify.cnf_clauses(source)
                                        sat_verified=verify.model_valid(p["stdout"],clauses)
                                        if not sat_verified:
                                            status="INVALID"
                                            note="SAT model missing or not valid on original CNF"
                if status in ("UNAVAILABLE","UNSUPPORTED"):
                    solver_s=0.0
                total=prep_s+solver_s
                par2=total if status in ("SAT","UNSAT") else CAP*2
                row=dict(protocol=PROTO,shard=a.shard,formula=case["filename"],
                    sha256=case["sha256"],expected=case["expected"],rep=rep,mode=mode,
                    status=status,prep_s=round(prep_s,6),solver_s=round(solver_s,6),
                    total_s=round(total,6),par2_s=round(par2,6),
                    sat_verified=sat_verified,xor_rows=xor_rows,
                    proof_length=proof_length,note=note)
                results.append(row)
                print("R107C_WORLD_TRIAL",json.dumps(row,sort_keys=True),flush=True)
    with (out/"paired.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(results[0]));w.writeheader();w.writerows(results)
    dump(out/"shard.json",dict(protocol=PROTO,shard=a.shard,source_manifest_sha=digest(root/"manifest.json"),
                             rows=results,runner_affinity_cpu=cpus[0],winner_available=winner_available))
def audit(a):
    root=Path(a.sources);manifest=check_manifest(root)
    combined=Path(a.combined)
    allrows=[];expected_sha=digest(root/"manifest.json")
    for shard in range(SHARDS):
        matches=list(combined.rglob("shard.json"))
        hits=[]
        for path in matches:
            data=json.loads(path.read_text())
            if data.get("shard")==shard and data.get("protocol")==PROTO:hits.append(data)
        ensure(len(hits)==1,"missing/duplicate shard "+str(shard))
        ensure(hits[0]["source_manifest_sha"]==expected_sha,"shard used different source manifest")
        allrows.extend(hits[0]["rows"])
    cases=manifest["cases"]
    require_keys={(c["sha256"],rep,mode) for c in cases for rep in range(REPS) for mode in MODES}
    observed=[(r["sha256"],r["rep"],r["mode"]) for r in allrows]
    ensure(len(observed)==len(set(observed)) and set(observed)==require_keys,
           "nonmatching comparisons (no silent missing rows)")
    overview={}
    for mode in MODES:
        rows=[r for r in allrows if r["mode"]==mode]
        overview[mode]=dict(total=len(rows),solved=sum(r["status"] in ("SAT","UNSAT") for r in rows),
          timeout=sum(r["status"]=="TIMEOUT" for r in rows),
          invalid=sum(r["status"]=="INVALID" for r in rows),
          unavailable=sum(r["status"] in ("UNAVAILABLE","UNSUPPORTED") for r in rows),
          par2_total_s=round(sum(r["par2_s"] for r in rows),5),
          par2_mean_s=round(statistics.mean(r["par2_s"] for r in rows),5),
          verified_sat=sum(r["sat_verified"] for r in rows),
          median_solved_wall_s=round(statistics.median([r["total_s"] for r in rows
                 if r["status"] in ("SAT","UNSAT")]),5) if any(r["status"] in ("SAT","UNSAT") for r in rows) else None)
    leader=overview["satcomp26_champion"]
    if leader["unavailable"]==0 and leader["invalid"]==0:
        champ=leader["par2_total_s"]
        for mode in MODES:
            overview[mode]["par2_gain_vs_2026_champion_pct"]=round(
                100*(champ-overview[mode]["par2_total_s"])/champ,3) if champ else None
    else:
        for mode in MODES:overview[mode]["par2_gain_vs_2026_champion_pct"]=None
    report=dict(protocol=PROTO,date="2026-11-04",cases=len(cases),trials=len(allrows),
        official_sample=True,official_ranking=False,official_world_winner="satsuma-iter+kissat",
        source_sha256=expected_sha,cap_s=CAP,repeats=REPS,coverage_by_status={
            status:sum(x["expected"]==status for x in cases) for status in ("SAT","UNSAT")},
        overview=overview,
        limitations=[
            "Unsanctioned retrospective mini-simulation, not submission to SAT Competition 2026",
            "2026 winner source archive built locally when available; no global ranking inferred",
            "Precommitted 14 known R32p GBD candidate IDs (previously used), NOT new blind holdout",
            "Input limited to 24MiB unpacked; selection excludes large/unavailable official CNFs",
            "Two serial repetitions, one CPU per shard, 30-second wall per trial (includes XOR preprocessing)",
            "Official Main 2026 used 5000s, 32GiB and different HoreKa hardware",
            "SAT model verified against original DIMACS; UNSAT compared to official verified label",
            "No externally checked DRAT/LRAT for UNSAT; cannot claim official Main Track eligibility",
            "UNAVAILABLE/UNSUPPORTED/INVALID penalized as 2*timeout; no wins on missing data",
            "PAR2 gain applies only to this sampled, hardware-matched experiment"])
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    dump(out/"report.json",report)
    with (out/"paired.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(allrows[0]));w.writeheader();w.writerows(allrows)
    lines=["# R107C vs SAT Competition 2026 world references",
       "",f"**Unofficial**; {len(cases)} actual SATComp26 original CNFs, {REPS} repeats, {CAP:.0f}s per trial,",
       "preprocessing charged, one CPU at a time. 2026 winner built locally if available.",
       "", "| Solver | Solved / trials | Timeouts | Invalid/unavailable | PAR-2 total (s) | PAR-2 gain vs 2026 winner |",
       "|---|---:|---:|---:|---:|---:|"]
    for mode in MODES:
        r=overview[mode];gain=r["par2_gain_vs_2026_champion_pct"]
        gain_txt=("n/a" if gain is None else f"{gain:+.2f}%")
        lines.append(f'| {mode} | {r["solved"]}/{r["total"]} | {r["timeout"]} | {r["invalid"]+r["unavailable"]} | {r["par2_total_s"]:.2f} | {gain_txt} |')
    lines+=["","**These are not official world ranking or 5000s comparisons.**",
            "SAT outputs verified on original CNFs. Unverified/UNSAT proof limits documented in report.json.",
            "", "Full paired evidence: paired.csv; immutable originals: source manifest and SHA files."]
    (out/"report.md").write_text("\n".join(lines)+"\n")
    print("R107C_WORLD_FINAL",json.dumps(overview,sort_keys=True),flush=True)
    print("\n".join(lines),flush=True)
def main():
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest="cmd",required=True)
    x=sub.add_parser("freeze");x.add_argument("--out",required=True)
    x=sub.add_parser("run");x.add_argument("--sources",required=True);x.add_argument("--built",required=True)
    x.add_argument("--shard",type=int,required=True);x.add_argument("--out",required=True)
    x=sub.add_parser("audit");x.add_argument("--sources",required=True)
    x.add_argument("--combined",required=True);x.add_argument("--out",required=True)
    a=p.parse_args()
    {"freeze":freeze,"run":execute,"audit":audit}[a.cmd](a)
if __name__=="__main__":
    main()
