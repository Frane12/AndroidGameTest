#!/usr/bin/env python3
"""DRNAS X4.7 LONG: larger/harder sources, longer caps, full PAR2 and provenance.

Two independent cohorts:
  - 96 synthetically generated original CNFs in six structural families,
    with n≈80..225 and near-threshold planted SAT plus structural PHP UNSAT.
  - 24 retrospective original 2024 SAT Competition CNFs from separate
    normalized filename families selected ONLY by archive-entry size/family.
NO official UNSAT receives verified credit absent an independent proof checker.
Synthetic UNSAT receives credit only for a separately verified strict
pigeonhole constraint subformula that mathematically proves impossibility.

The X46/X47 frozen cost and abstention policies are generated on separate
original source IDs (600000+). Holdout originals are >1000000 (synthetic)
or 2024 source SHA and never enter training or model selection. This is
research/retrospective, NOT globally blind SAT Competition performance.
"""
from __future__ import annotations
import argparse
import bz2
from collections import Counter,defaultdict
import gzip
import hashlib
import itertools
import json
import lzma
import math
import os
from pathlib import Path
import random
import re
import statistics
import subprocess
import tempfile
import time

SYNTH_FAMILIES=("critical3_planted","critical4_planted","xor_planted",
                "graph_coloring_sat","modular3_planted","php_structural_unsat")
ARMS=("CORE","X46_8","X46_128","X46_LEARNED_8","X47_RISKGATE_8")
OFFICIAL_ARCHIVE="https://zenodo.org/records/15095752/files/sat-competition-2024-main-benchmarks.zip?download=1"
N_SHARDS=4

def emit(tag,obj):
    print(tag+" "+json.dumps(obj,sort_keys=True,separators=(",",":")),flush=True)

def rand_for(family,index):
    v=int.from_bytes(hashlib.sha256(f"X47LONG|{family}|{index}|20261113".encode()).digest()[:8],"big")
    return random.Random(v)

def clause_planted(rng,n,target,k):
    vs=rng.sample(range(1,n+1),k)
    c=[v*rng.choice((-1,1)) for v in vs]
    if not any(target[abs(l)]==(l>0) for l in c):
        c[rng.randrange(len(c))]*=-1
    return c

def make_synthetic(family,index):
    rng=rand_for(family,index)
    clauses=[]
    cert="SAT_CONSTRUCTED_CHECK_WITNESS"
    if family.startswith("critical"):
        k=3 if family=="critical3_planted" else 4
        n=100+(index%75) if k==3 else 85+(index%75)
        target=[False]+[bool(rng.randrange(2)) for _ in range(n)]
        density=rng.uniform(4.05,4.65) if k==3 else rng.uniform(8.6,10.5)
        clauses.extend(clause_planted(rng,n,target,k) for _ in range(round(n*density)))
    elif family=="xor_planted":
        n=95+(index%75)
        target=[False]+[bool(rng.randrange(2)) for _ in range(n)]
        for _ in range(n+rng.randrange(1,15)):
            vs=rng.sample(range(1,n+1),3)
            rhs=sum(int(target[x]) for x in vs)%2
            for bits in itertools.product((0,1),repeat=3):
                if sum(bits)%2!=rhs:
                    clauses.append([-v if bit else v for v,bit in zip(vs,bits)])
        clauses.extend(clause_planted(rng,n,target,3) for _ in range(2*n))
    elif family=="graph_coloring_sat":
        nodes=30+(index%31)
        n=nodes*3
        target=[rng.randrange(3) for _ in range(nodes)]
        var=lambda v,c:3*v+c+1
        for v in range(nodes):
            lits=[var(v,c) for c in range(3)]
            clauses.append(lits)
            for x,y in itertools.combinations(lits,2):
                clauses.append([-x,-y])
        edge_prob=rng.uniform(.22,.52)
        for v,w in itertools.combinations(range(nodes),2):
            if target[v]!=target[w] and rng.random()<edge_prob:
                for c in range(3):clauses.append([-var(v,c),-var(w,c)])
        target=[False]+[target[(v-1)//3]==(v-1)%3 for v in range(1,n+1)]
    elif family=="modular3_planted":
        n=108+(index%73)
        target=[False]+[bool(rng.randrange(2)) for _ in range(n)]
        modules=[list(range(k+1,min(n+1,k+12))) for k in range(0,n,11)]
        for block in modules:
            if len(block)<3:continue
            for _ in range(round(4.5*len(block))):
                vs=rng.sample(block,3)
                c=[x*rng.choice((-1,1)) for x in vs]
                if not any(target[abs(l)]==(l>0) for l in c):c[0]*=-1
                clauses.append(c)
        clauses.extend(clause_planted(rng,n,target,3) for _ in range(n*2))
    elif family=="php_structural_unsat":
        # True strict pigeonhole UNSAT core, independently rechecked against
        # original CNF. Additional satisfiable auxiliaries vary the instance.
        holes=5+(index%4);pigeons=holes+1
        core_vars=holes*pigeons
        aux=28+(index%17)
        n=core_vars+aux
        var=lambda p,h:p*holes+h+1
        for p in range(pigeons):
            clauses.append([var(p,h) for h in range(holes)])
        for h in range(holes):
            for p,q in itertools.combinations(range(pigeons),2):
                clauses.append([-var(p,h),-var(q,h)])
        aux_assignment={v:bool(rng.randrange(2)) for v in range(core_vars+1,n+1)}
        for _ in range(5*aux):
            vs=rng.sample(range(core_vars+1,n+1),3)
            clause=[v*rng.choice((-1,1)) for v in vs]
            if not any(aux_assignment[abs(l)]==(l>0) for l in clause):
                clause[0]*=-1
            clauses.append(clause)
        target=None;cert="PHP_STRUCTURAL_CORE"
    else:raise ValueError("unknown source family "+family)
    normalized=sorted({tuple(sorted(set(c),key=lambda z:(abs(z),z<0)))
                       for c in clauses if not any(-lit in c for lit in c)})
    if target is not None and not all(any(target[abs(l)]==(l>0) for l in c) for c in normalized):
        raise AssertionError("planted SAT witness invalid")
    if cert=="PHP_STRUCTURAL_CORE":
        cnf_set=set(normalized)
        for p in range(pigeons):
            assert tuple(range(p*holes+1,(p+1)*holes+1)) in cnf_set
        for h in range(holes):
            for p,q in itertools.combinations(range(pigeons),2):
                a,b=var(p,h),var(q,h)
                assert tuple(sorted((-a,-b),key=lambda z:(abs(z),z<0))) in cnf_set
        assert pigeons>holes
    content=f"p cnf {n} {len(normalized)}\n"+"".join(
        " ".join(map(str,c))+" 0\n" for c in normalized)
    return {"kind":"synthetic","family":family,"source_id":index,
            "nvars":n,"nclauses":len(normalized),"cert":cert,
            "clauses":normalized,"content":content,
            "sha256":hashlib.sha256(content.encode()).hexdigest(),
            "filename":f"{family}_{index}.cnf"}

def official_family(filename):
    name=Path(filename).name.lower()
    name=re.sub(r"\.cnf(?:\.(?:xz|gz|bz2))?$","",name)
    name=name.replace(".sanitized","")
    name=re.sub(r"\d+","#",name)
    return re.sub(r"[_\-.]+","-",name).strip("-")

def official_sources(count):
    # Indexed by uncompressed archive member size and family, NOT outcomes.
    # Archive access is only in an isolated CI job; failure must not mask
    # the separate synthetic benchmark.
    from remotezip import RemoteZip
    with RemoteZip(OFFICIAL_ARCHIVE,timeout=95) as z:
        pool=sorted([x for x in z.infolist() if not x.is_dir()
            and x.filename.lower().endswith((".cnf",".cnf.xz",".cnf.gz",".cnf.bz2"))
            and 50000<=x.file_size<=800000],key=lambda x:(x.file_size,x.filename))
        by_family={}
        for member in pool:
            fam=official_family(member.filename)
            if fam not in by_family:by_family[fam]=member
        family_pick=list(by_family.values())
        # Stratified by source size so the trial is not exclusively easy
        # or exclusively huge. Do not inspect outcomes for selection.
        if len(family_pick)<count:
            raise RuntimeError(f"official archive has {len(family_pick)} eligible families, need {count}")
        # Predefined extra candidate reserve: keep the source selection
        # independent of solver outcomes even when a candidate is too large,
        # not valid DIMACS, or inaccessible through a ranged request.
        count_candidates=min(len(family_pick),max(5*count,80))
        picked=[family_pick[min(len(family_pick)-1,
                 round((j+.5)*len(family_pick)/count_candidates))]
                for j in range(count_candidates)]
        random.Random(20261113).shuffle(picked)  # size-stratified, outcome-blind
        out=[]
        for member in picked:
            if len(out)>=count:break
            try:
                data=z.read(member)
            except (OSError,ValueError,EOFError) as error:
                emit("X47_OFFICIAL_SKIP",{"entry":member.filename,
                    "reason":"archive_range_read_failed","error":str(error)[:90]})
                continue
            if member.filename.endswith(".xz"):data=lzma.decompress(data)
            elif member.filename.endswith(".gz"):data=gzip.decompress(data)
            elif member.filename.endswith(".bz2"):data=bz2.decompress(data)
            if not(100<=len(data)<=18000000):
                continue
            try:text=data.decode("ascii")
            except UnicodeError:continue
            sha=hashlib.sha256(data).hexdigest()
            header=[line.split() for line in text.splitlines() if line.lstrip().startswith("p cnf ")]
            if len(header)!=1 or len(header[0])!=4:continue
            try:n=int(header[0][2]);clauses=int(header[0][3])
            except ValueError:continue
            if n<1 or n>30000 or clauses<1 or clauses>900000:continue
            out.append({"kind":"official_retrospective","family":official_family(member.filename),
                "source_id":len(out),"nvars":n,"nclauses":clauses,
                "cert":"OFFICIAL_UNSAT_UNVERIFIED","content":text,
                "archive_path":member.filename,"archive_url":OFFICIAL_ARCHIVE,
                "sha256":sha,"filename":f"official_{i:02d}.cnf"})
        if len(out)<count:
            raise RuntimeError(f"only {len(out)}/{count} official bounded sources matched, no solver outcome filtering")
        if len({x["sha256"] for x in out})!=count:
            raise AssertionError("duplicate official original SHA")
        return out

def parse_output_model(stdout,nvars):
    lines=[line.strip() for line in stdout.splitlines() if line.startswith("s ")]
    if lines!=["s SATISFIABLE"]:return None
    model={}
    for line in stdout.splitlines():
        if line.startswith("v ") or line.startswith("v\t"):
            for tok in line[1:].split():
                lit=int(tok)
                if lit==0:continue
                if not(1<=abs(lit)<=nvars):return None
                if abs(lit) in model and model[abs(lit)]!=(lit>0):return None
                model[abs(lit)]=(lit>0)
    if len(model)!=nvars:return None
    return model

def verify_model_on_original_text(source,stdout):
    model=parse_output_model(stdout,source["nvars"])
    if model is None:return False
    # Multi-line clauses / multiple clauses per line supported.
    total=0;seen=False;clause_sat=False
    for line in source["content"].splitlines():
        line=line.strip()
        if not line or line.startswith(("c","p","%")):continue
        for token in line.split():
            if token in ("c","%"):break
            x=int(token)
            if x==0:
                total+=1
                if not clause_sat:return False
                seen=False;clause_sat=False
            else:
                if not 1<=abs(x)<=source["nvars"]:return False
                clause_sat|=(model[abs(x)]==(x>0))
                seen=True
    return not seen and total==source["nclauses"]

def run_one(binary,cnf,source,arm,cap,checkpoint,model,guard):
    command=[str(binary),str(cnf),"--mode","core","--time",str(max(.3,cap-.12)),
             "--branch-at",str(checkpoint),"--stats"]
    if arm in ("X46_8","X46_128","X46_LEARNED_8","X47_RISKGATE_8"):
        count=128 if arm=="X46_128" else 8
        command+=["--x46-conflicts",str(count),"--x46-probe-ms","2.5"]
    if arm in ("X46_LEARNED_8","X47_RISKGATE_8"):
        command+=["--x46-model",str(model)]
    if arm=="X47_RISKGATE_8":
        command+=["--x47-guard",str(guard)]
    started=time.monotonic()
    try:
        proc=subprocess.run(command,capture_output=True,text=True,timeout=cap+.7)
        solve_wall=time.monotonic()-started
    except subprocess.TimeoutExpired:
        return {"arm":arm,"status":"TIMEOUT","verified":False,"PAR2":2*cap,
                "solver_e2e_s":cap,"check_s":0.0,"reached":False,
                "decisions":None,"conflicts":None,"probe_wall_ms":None,
                "probe_triggered":False,"probe_skipped":False,
                "actual_flip":False,"pre_state_digest":None}
    if proc.returncode not in (0,10,20):
        raise RuntimeError(f"native crash {proc.returncode}: {proc.stderr[-1000:]}")
    stats=[json.loads(line[len("X41_STATS "):]) for line in proc.stderr.splitlines()
           if line.startswith("X41_STATS ")]
    chk=[json.loads(line[len("X45_COMPARE "):]) for line in proc.stderr.splitlines()
          if line.startswith("X45_COMPARE ")]
    p=[json.loads(line[len("X46_PROBE "):]) for line in proc.stderr.splitlines()
       if line.startswith("X46_PROBE ")]
    if len(stats)!=1 or len(chk)!=1 or len(p)!=int(arm!="CORE"):
        raise AssertionError("missing native benchmark telemetry")
    stats,pre=stats[0],chk[0]
    probe=p[0] if p else None
    status={0:"UNKNOWN",10:"SAT",20:"UNSAT"}[proc.returncode]
    check_t=time.monotonic()
    verified=False;cert_kind="NOT_SOLVED"
    if status=="SAT":
        verified=verify_model_on_original_text(source,proc.stdout)
        cert_kind="ORIGINAL_CNF_SAT_WITNESS" if verified else "BAD_SAT_WITNESS"
        if not verified:raise AssertionError("invalid SAT witness from original CNF")
    elif status=="UNSAT":
        if source["cert"]=="PHP_STRUCTURAL_CORE":
            verified=True
            cert_kind="INDEPENDENT_PHP_PIGEONHOLE_CERT"
        else:
            cert_kind="UNSAT_NO_INDEPENDENT_CERT"
    check_elapsed=time.monotonic()-check_t
    e2e=solve_wall+check_elapsed
    reached=bool(pre["reached"])
    if reached and not pre["pre_state_digest"]:
        raise AssertionError("empty matched prefix identity")
    if probe and reached:
        if probe["pre_state_digest"]!=pre["pre_state_digest"]:
            raise AssertionError("pre-probe vs checkpoint hash mismatch")
        if arm=="X47_RISKGATE_8" and not probe.get("x47_enabled",False):
            raise AssertionError("X47 risk model not active")
    if source["cert"]=="PHP_STRUCTURAL_CORE" and status=="SAT":
        raise AssertionError("SAT on independently proved PHP UNSAT source")
    if source["cert"]=="SAT_CONSTRUCTED_CHECK_WITNESS" and status=="UNSAT":
        raise AssertionError("UNSAT on guaranteed SAT source")
    # No unverified (esp. official UNSAT) can contribute "solved".
    cost=round(e2e if verified and e2e<=cap else 2*cap,7)
    return {"arm":arm,"status":status,"certification":cert_kind,
         "verified":verified,"PAR2":cost,"solver_e2e_s":round(solve_wall,7),
         "check_s":round(check_elapsed,7),"reached":reached,
         "decisions":stats["decisions"],"conflicts":stats["conflicts"],
         "probe_wall_ms":probe.get("probe_pair_wall_ms") if probe else 0,
         "probe_triggered":bool(probe and probe["triggered"]),
         "probe_skipped":bool(probe and probe["skipped"]),
         "actual_flip":bool(reached and pre["actual_literal"]==-pre["baseline_literal"]),
         "pre_state_digest":pre["pre_state_digest"] if reached else None,
         "prefix_conflicts":pre["prefix_conflicts"] if reached else None,
         "prefix_decision_literal":pre["baseline_literal"] if reached else None}

def source_interval(records,arm,draws=1900):
    bysource=defaultdict(lambda:defaultdict(list))
    for r in records:bysource[r["sha256"]][r["arm"]].append(r["PAR2"])
    sha=sorted(bysource)
    if not sha:return [None,None]
    rng=random.Random(471119)
    values=[]
    for _ in range(draws):
        ids=[sha[rng.randrange(len(sha))] for _ in sha]
        b=sum(sum(bysource[id]["CORE"]) for id in ids)
        a=sum(sum(bysource[id][arm]) for id in ids)
        values.append((b-a)/b if b else 0.)
    values.sort()
    return [round(values[int(.025*(draws-1))],5),
            round(values[int(.975*(draws-1))],5)]

def summary(rows,arms=ARMS):
    total={}
    for arm in arms:
        xx=[r for r in rows if r["arm"]==arm]
        total[arm]={"trials":len(xx),
          "verified":sum(r["verified"] for r in xx),
          "SAT_verified":sum(r["verified"] and r["status"]=="SAT" for r in xx),
          "UNSAT_verified":sum(r["verified"] and r["status"]=="UNSAT" for r in xx),
          "UNSAT_unverified":sum(r["status"]=="UNSAT" and not r["verified"] for r in xx),
          "timeouts_unknown":sum(r["status"] in ("UNKNOWN","TIMEOUT") for r in xx),
          "PAR2_verified_s":round(sum(r["PAR2"] for r in xx),6),
          "e2e_s":round(sum(r["solver_e2e_s"]+r["check_s"] for r in xx),6),
          "conflicts":sum(r["conflicts"] or 0 for r in xx),
          "decisions":sum(r["decisions"] or 0 for r in xx),
          "probes_triggered":sum(r["probe_triggered"] for r in xx),
          "probe_skips":sum(r["probe_skipped"] for r in xx),
          "probe_wall_s":round(sum(r["probe_wall_ms"] or 0 for r in xx)/1000,6),
          "flips":sum(r["actual_flip"] for r in xx)}
    return total

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--binary",type=Path,default=Path("build/drnas-x47"))
    ap.add_argument("--out",type=Path,required=True)
    ap.add_argument("--cohort",choices=("synthetic","official"),required=True)
    ap.add_argument("--shard",type=int,default=0)
    ap.add_argument("--shards",type=int,default=N_SHARDS)
    ap.add_argument("--synthetic-count",type=int,default=96)
    ap.add_argument("--official-count",type=int,default=24)
    ap.add_argument("--source-offset",type=int,default=1100000)
    ap.add_argument("--cap",type=float,default=6.0)
    ap.add_argument("--repeats",type=int,default=2)
    ap.add_argument("--model",type=Path,required=True)
    ap.add_argument("--guard",type=Path,required=True)
    args=ap.parse_args()
    if args.shard<0 or args.shard>=args.shards or args.cap<2 or args.repeats<2:
        raise ValueError("invalid shard, cap or repeats")
    if args.source_offset<1000000:raise ValueError("refuse reuse of old training sources")
    args.out.mkdir(parents=True,exist_ok=False)
    if hasattr(os,"sched_setaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    model=args.model.resolve();guard=args.guard.resolve()
    model_sha=hashlib.sha256(model.read_bytes()).hexdigest()
    guard_sha=hashlib.sha256(guard.read_bytes()).hexdigest()
    if args.cohort=="synthetic":
        if args.synthetic_count%len(SYNTH_FAMILIES):
            raise ValueError("synthetic source count not divisible by families")
        per=args.synthetic_count//len(SYNTH_FAMILIES)
        cases=[make_synthetic(f,args.source_offset+j)
               for f in SYNTH_FAMILIES for j in range(per)]
        # Round-robin inside each family => four shards contain six categories.
        cases=[x for i,x in enumerate(cases) if i%args.shards==args.shard]
    else:
        if args.shards!=1 or args.shard!=0:raise ValueError("official uses one job")
        cases=official_sources(args.official_count)
    if len({x["sha256"] for x in cases})!=len(cases):
        raise AssertionError("repeated original CNF SHA")
    manifest={"cohort":args.cohort,"shard":args.shard,"shards":args.shards,
        "original_sources":len(cases),"repeats":args.repeats,"cap_s":args.cap,
        "checkpoint":"4th decision only",
        "frozen_logistic_sha256":model_sha,"frozen_risk_guard_sha256":guard_sha,
        "arms":ARMS,"formula_source_not_selected_by_solver_outcome":True,
        "not_globally_blind":True,"proof_policy":"original-CNF SAT witness; PHP strict core theorem; official UNSAT unverified",
        "originals":[{k:v for k,v in x.items() if k in (
            "kind","family","source_id","nvars","nclauses","cert","sha256","archive_path","archive_url","filename")}
             for x in cases]}
    (args.out/"manifest.json").write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n")
    records=[]
    checkpoint=4
    with tempfile.TemporaryDirectory(prefix="x47-long-") as td:
        cnf=Path(td)/"original.cnf"
        for i,source in enumerate(cases):
            cnf.write_text(source["content"])
            if hashlib.sha256(cnf.read_bytes()).hexdigest()!=source["sha256"]:
                raise AssertionError("original CNF mutation")
            for rep in range(args.repeats):
                arms=list(ARMS)
                offset=(i+rep)%len(arms)
                arms=arms[offset:]+arms[:offset]
                checks=[]
                for arm in arms:
                    obj=run_one(args.binary.resolve(),cnf,source,arm,
                                args.cap,checkpoint,model,guard)
                    obj.update({"sha256":source["sha256"],"family":source["family"],
                        "source_id":source["source_id"],"cohort":args.cohort,
                        "shard":args.shard,"rep":rep,"checkpoint":checkpoint})
                    records.append(obj)
                    checks.append(obj)
                    emit("X47_LONG_TRIAL",{k:obj[k] for k in (
                        "source_id","family","rep","arm","status","verified","PAR2",
                        "conflicts","decisions","probe_triggered","probe_wall_ms")})
                seen={r["status"] for r in checks if r["verified"]}
                if len(seen)>1:raise AssertionError("contradictory independently verified answers")
                if all(r["reached"] for r in checks):
                    digests={r["pre_state_digest"] for r in checks}
                    phase={r["prefix_decision_literal"] for r in checks}
                    counters={r["prefix_conflicts"] for r in checks}
                    if len(digests)!=1 or len(phase)!=1 or len(counters)!=1:
                        raise AssertionError("different state BEFORE intervention")
                elif any(r["reached"] for r in checks):
                    raise AssertionError("different pre-intervention reachability")
            emit("X47_LONG_PROGRESS",{"completed":i+1,"total":len(cases),
                "cohort":args.cohort,"shard":args.shard})
    if model_sha!=hashlib.sha256(model.read_bytes()).hexdigest() or (
        guard_sha!=hashlib.sha256(guard.read_bytes()).hexdigest()):
        raise AssertionError("holdout changed frozen model/guard")
    with (args.out/"trials.jsonl").open("w") as f:
        for row in records:f.write(json.dumps(row,sort_keys=True)+"\n")
    by_family={fam:summary([r for r in records if r["family"]==fam])
               for fam in sorted({r["family"] for r in records})}
    totals=summary(records)
    report={"cohort":args.cohort,"shard":args.shard,
        "original_sources":len(cases),"total_trials":len(records),
        "all_unique_SHA":True,"model_unchanged":True,
        "source_cluster_N":len(cases),
        "all_arms":totals,"family":by_family,
        "relative_verified_PAR2_vs_CORE":{
            arm:{"relative_reduction":round(
                (totals["CORE"]["PAR2_verified_s"]-totals[arm]["PAR2_verified_s"])/
                totals["CORE"]["PAR2_verified_s"],6),
                "formula_cluster_CI95":source_interval(records,arm)}
            for arm in ARMS[1:]},
        "caveats":[
            "Official 2024 benchmark is retrospective and previously used, not globally blind.",
            "Official UNSAT has no independent proof checker in this workflow and earns PAR2 penalty.",
            "Original CNFs, not repeats or arms, are independent source units.",
            "All end-to-end runtimes include actual probing and SAT witness checker overhead.",
            "The X47 frozen risk gate may choose no probes; that is NOT a learned solver speedup."
        ]}
    (args.out/"report.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    emit("X47_LONG_FINAL",{
        "cohort":args.cohort,"shard":args.shard,"sources":len(cases),
        "solved":{arm:{key:x[key] for key in (
            "verified","SAT_verified","UNSAT_verified","UNSAT_unverified","timeouts_unknown",
            "PAR2_verified_s","conflicts","probe_wall_s","flips")}
            for arm,x in totals.items()},
        "comparisons":report["relative_verified_PAR2_vs_CORE"]})

if __name__=="__main__":
    main()
