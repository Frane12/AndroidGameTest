#!/usr/bin/env python3
"""DRNAS R6: four real policies, matched within each independent category runner.
Design is exploratory, NOT official competition scoring or a world-record claim.
The R5 gate was frozen on prior development data; no R6 threshold fitting.
Generated CNF and public SATLIB source are explicitly separated.
"""
from __future__ import annotations
import argparse, csv, hashlib, json, os, platform, random, resource
import signal, subprocess, sys, time
from collections import defaultdict, Counter
from pathlib import Path
import statistics

PIN_KISSAT = "8af8e56f174b778aef3aa45af9f739b2a5f492c2"
PIN_SATLIB = "fc0e735aff48989326f256121b5ed6fc585858c3"
PIN_STABLE_BLOB = "d280a2ffa28d72aec183323bbea40544d676112d"
CATEGORIES = ("random3","graphcolor","xor","external_satlib")
MODES = ("stable_v1531","monitor","forced_restart25","r7_gate")
CAP = 8
REPEATS = 3
OUT = Path("drnas-r6-results")
ORIGINAL = Path("/tmp/kissat-r6-original/build/kissat")
PATCHED = Path("/tmp/kissat-r6-patched/build/kissat")
STABLE = Path("/tmp/drnas-r6-v1531")
CHECKPOINTS = (100,250,500,1000,2000,4096,8192)
FIELDS = ("category","dataset_type","formula","formula_sha256","source","source_revision",
    "repeat","mode","expected","status","wall_s","cpu_s","par2_s","sat_model_checked",
    "native_unsat_certificate_checked","route","exit_code","runner","seed",
    "early_restarts","early_g","early_p","early_d","gate_eligible","gate_action",
    "switch_at","final_conflicts","final_restarts","trace_points","error")

def sha(buf: bytes) -> str:
    return hashlib.sha256(buf).hexdigest()

def dump(path: Path, obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,indent=2,sort_keys=True)+"\n")

def write_csv(path, rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=FIELDS,extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

def emit_cnf(out: Path, name: str, n: int, clauses, expected: str,
             dataset_type: str, source: str, revision: str, metadata=None):
    if n<1 or not clauses:
        raise ValueError("Invalid generated CNF")
    for cl in clauses:
        if not cl or any(x==0 or abs(x)>n for x in cl):
            raise ValueError(f"Invalid clause in {name}")
    raw=(f"p cnf {n} {len(clauses)}\n"+
         "".join(" ".join(map(str,c))+" 0\n" for c in clauses)).encode()
    path=out/name
    path.write_bytes(raw)
    return dict(path=path,formula=name,n=n,clauses=clauses,expected=expected,
        dataset_type=dataset_type,source=source,source_revision=revision,
        formula_sha256=sha(raw),metadata=metadata or {})

def random3_cases(out):
    cases=[]
    for i in range(10):
        seed=710000+i
        rng=random.Random(seed)
        n=185+5*(i%3)
        m=round(4.23*n)
        clauses=[]
        for _ in range(m):
            vs=rng.sample(range(1,n+1),3)
            clauses.append([v if rng.getrandbits(1) else -v for v in vs])
        cases.append(emit_cnf(out,f"rnd3_{i:02d}.cnf",n,clauses,"UNKNOWN",
            "generated","DRNAS R7 frozen deterministic generator","r7-v1",
            {"seed":seed,"density":round(m/n,5),"label":"UNKNOWN, not a proof of UNSAT"}))
    return cases

def graphcolor_cases(out):
    cases=[]
    for i in range(10):
        seed=720000+i
        rng=random.Random(seed)
        V=48+3*(i%4)
        planted=[rng.randrange(3) for _ in range(V)]
        edges=set()
        target=round(2.95*V)
        trials=0
        while len(edges)<target and trials<50000:
            trials+=1
            a,b=rng.sample(range(V),2)
            if planted[a]!=planted[b]:
                edges.add((min(a,b),max(a,b)))
        if len(edges)<target:
            raise RuntimeError("Could not generate planted coloring")
        unsat=bool(i%2)
        if unsat:
            clique=rng.sample(range(V),4)
            for p in range(4):
                for q in range(p+1,4):
                    a,b=clique[p],clique[q]
                    edges.add((min(a,b),max(a,b)))
        def lit(v,c):return 3*v+c+1
        clauses=[]
        for v in range(V):
            clauses.append([lit(v,c) for c in range(3)])
            for c in range(3):
                for d in range(c+1,3):
                    clauses.append([-lit(v,c),-lit(v,d)])
        for a,b in sorted(edges):
            for c in range(3):
                clauses.append([-lit(a,c),-lit(b,c)])
        rng.shuffle(clauses)
        cases.append(emit_cnf(out,f"graph_{i:02d}.cnf",3*V,clauses,
            "UNSAT" if unsat else "SAT","generated",
            "DRNAS R6 planted 3-color / K4 obstruction","r7-v1",
            {"seed":seed,"graph_vertices":V,"edges":len(edges),
             "unsat_construction":"K4" if unsat else None}))
    return cases

def cubic_graph(rng, vertices):
    for attempt in range(500):
        stubs=[v for v in range(vertices) for _ in range(3)]
        rng.shuffle(stubs)
        edges=set()
        valid=True
        for a,b in zip(stubs[::2],stubs[1::2]):
            pair=(min(a,b),max(a,b))
            if a==b or pair in edges:
                valid=False
                break
            edges.add(pair)
        if valid and len(edges)==3*vertices//2:
            return sorted(edges),attempt
    raise RuntimeError("No simple cubic graph from frozen seeds")

def parity_clauses(vars_,rhs):
    out=[]
    width=len(vars_)
    for mask in range(1<<width):
        if (mask.bit_count()&1)==rhs:
            continue
        out.append([(-v if (mask>>j)&1 else v) for j,v in enumerate(vars_)])
    return out

def xor_cases(out):
    cases=[]
    for i in range(10):
        seed=730000+i
        rng=random.Random(seed)
        V=20+2*(i%3)
        edges,attempt=cubic_graph(rng,V)
        n=len(edges)
        edge_index={e:j+1 for j,e in enumerate(edges)}
        assignments={j+1:rng.randrange(2) for j in range(n)}
        rhs=[]
        clauses=[]
        for v in range(V):
            incident=[edge_index[e] for e in edges if v in e]
            if len(incident)!=3:
                raise RuntimeError("Not degree three")
            bit=0
            for k in incident:
                bit^=assignments[k]
            rhs.append(bit)
        unsat=bool(i%2)
        if unsat:
            rhs[rng.randrange(V)]^=1
        for v in range(V):
            incident=[edge_index[e] for e in edges if v in e]
            clauses.extend(parity_clauses(incident,rhs[v]))
        rng.shuffle(clauses)
        cases.append(emit_cnf(out,f"tseitin_{i:02d}.cnf",n,clauses,
            "UNSAT" if unsat else "SAT","generated",
            "DRNAS R6 cubic-graph Tseitin parity","r7-v1",
            {"seed":seed,"vertices":V,"edges":n,"stub_attempt":attempt,
             "xor_total_rhs_parity":sum(rhs)%2,
             "theoretical_unsat_witness":"sum of degree-three vertex equations" if unsat else None}))
    return cases

def normalize_satlib(path):
    raw=path.read_bytes()
    n=m=0
    clauses=[]
    pending=[]
    header=0
    trailer=False
    for line in raw.decode("utf-8").splitlines():
        line=line.strip()
        if not line or line.startswith("c"):
            continue
        if line.startswith("%"):
            trailer=True
            continue
        if trailer:
            if line!="0":
                raise ValueError(f"Unexpected SATLIB trailer {path.name}")
            continue
        if line.startswith("p "):
            words=line.split()
            header+=1
            if header!=1 or len(words)!=4 or words[1]!="cnf":
                raise ValueError("Bad header")
            n,m=map(int,words[2:])
            continue
        if header!=1:
            raise ValueError("Missing header")
        for t in line.split():
            v=int(t)
            if abs(v)>n:
                raise ValueError("Literal outside range")
            if v:
                pending.append(v)
            else:
                clauses.append(pending)
                pending=[]
    if header!=1 or pending or len(clauses)!=m:
        raise ValueError(f"SATLIB clause mismatch {len(clauses)} vs {m}")
    return raw,n,clauses

def external_cases(out):
    root=Path("/tmp/satlib-r6/testdata/satlib")
    choices=([(f"sat-flat125-301/flat125-{i}.cnf","SAT") for i in (13,14,15,16)]+
             [(f"unsat-uniform-50-218/uuf50-0{i}.cnf","UNSAT") for i in (13,14,15)]+
             [(f"sat-uniform-20-91/uf20-0{i}.cnf","SAT") for i in (13,14,15)])
    cases=[]
    for i,(rel,expected) in enumerate(choices):
        raw,n,clauses=normalize_satlib(root/rel)
        case=emit_cnf(out,f"satlib_{i:02d}.cnf",n,clauses,expected,
            "external_prior_public","mitchellh/go-sat SATLIB",PIN_SATLIB,
            {"upstream_relative_path":rel,"raw_source_sha256":sha(raw),
             "previously_available_in_public_SATLIB":True,
             "independent_new_unseen_holdout":False})
        cases.append(case)
    return cases

def get_cases(category,out):
    if category=="random3":return random3_cases(out)
    if category=="graphcolor":return graphcolor_cases(out)
    if category=="xor":return xor_cases(out)
    if category=="external_satlib":return external_cases(out)
    raise ValueError(category)

def extract_tags(output):
    traces=[]
    labels={}
    for line in output.splitlines():
        if not line.startswith("c "):
            continue
        parts=line.split()
        if len(parts)<3:
            continue
        kind=parts[1]
        if kind not in ("R6_TRACE","DRNAS_V177_EARLY","R4_EARLY",
                        "R5_EARLY","DRNAS_V177_SWITCH","DRNAS_V177_FINAL"):
            continue
        values={}
        for token in parts[2:]:
            if "=" in token:
                key,val=token.split("=",1)
                values[key]=val
        if kind=="R6_TRACE":
            traces.append(values)
        else:
            labels[kind]=values
    return traces,labels

def check_witness(case,stdout,payload):
    n=case["n"]
    model=payload.get("model",[]) if payload else []
    if not model:
        model=[]
        for line in stdout.splitlines():
            if line.startswith("v "):
                model.extend(int(v) for v in line.split()[1:] if v!="0")
    assignment={}
    for lit in model:
        if type(lit)!=int or abs(lit)<1 or abs(lit)>n:
            return False
        if abs(lit) in assignment and assignment[abs(lit)]!=(lit>0):
            return False
        assignment[abs(lit)]=lit>0
    return bool(assignment) and all(
        any(assignment.get(abs(lit))==(lit>0) for lit in clause)
        for clause in case["clauses"])

def proof_check(case,payload):
    if not payload or payload.get("status")!="UNSAT":
        return None
    sys.path.insert(0,str(Path("research/tseitin-replay").resolve()))
    from v153_proof_checker import verify_certificate
    return bool(verify_certificate(payload,case["clauses"]))

def run_one(case,rep,mode,runner):
    env=os.environ.copy()
    env.pop("DRNAS_V177_MODE",None)
    env.pop("DRNAS_V177_RULE_FILE",None)
    if mode=="stable_v1531":
        command=[str(STABLE),str(case["path"].resolve()),str(ORIGINAL),"1"]
    else:
        env["DRNAS_V177_MODE"]={
            "monitor":"r5_monitor",
            "forced_restart25":"switch2048",
            "r7_gate":"r5_gate"}[mode]
        command=[str(PATCHED),"-s",str(case["path"].resolve())]
    before=resource.getrusage(resource.RUSAGE_CHILDREN)
    t0=time.perf_counter()
    proc=subprocess.Popen(command,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
        text=True,errors="replace",start_new_session=True)
    try:
        stdout,stderr=proc.communicate(timeout=CAP)
        status={10:"SAT",20:"UNSAT"}.get(proc.returncode,"ERROR")
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid,signal.SIGKILL)
        stdout,stderr=proc.communicate()
        status="TIMEOUT"
    wall=time.perf_counter()-t0
    after=resource.getrusage(resource.RUSAGE_CHILDREN)
    cpu=(after.ru_utime+after.ru_stime)-(before.ru_utime+before.ru_stime)
    payload=None
    for line in stdout.splitlines():
        if line.startswith("DRNAS_HYBRID_RESULT\t"):
            payload=json.loads(line.split("\t",1)[1])
    if payload:
        status=payload.get("status","ERROR").upper()
    traces,labels=extract_tags(stdout+"\n"+stderr)
    early=labels.get("DRNAS_V177_EARLY",{})
    gate=labels.get("R5_EARLY",{})
    switched=labels.get("DRNAS_V177_SWITCH",{})
    finish=labels.get("DRNAS_V177_FINAL",{})
    sat_checked=(check_witness(case,stdout,payload) if status=="SAT" else None)
    proof=(proof_check(case,payload) if status=="UNSAT" and payload else None)
    route=payload.get("path") if payload else (
        "kissat_direct" if "DRNAS_V153_ROUTE\tkissat_direct" in stdout else "kissat_inprocess")
    error=""
    if status=="ERROR":
        error=("solver exit "+str(proc.returncode)+" "+stderr[-240:]).strip()
    if sat_checked is False:
        error="INVALID SAT WITNESS"
    if proof is False:
        error="INVALID NATIVE UNSAT CERTIFICATE"
    if case["expected"]!="UNKNOWN" and status in ("SAT","UNSAT") and status!=case["expected"]:
        error=f"KNOWN ANSWER CONTRADICTION expected {case['expected']} got {status}"
    if mode=="monitor" and switched:
        error="MONITOR ILLEGALLY CHANGED RESTART POLICY"
    if mode=="r7_gate" and gate:
        should = 0.0 < float(gate["p"]) < 35.0
        if int(gate.get("eligible", "-1")) != int(should):
            error = "R7 ELIGIBILITY DOES NOT MATCH OBSERVED 512 SIGNAL"
        if should != (gate.get("action") == "2048"):
            error = "R7 GATE ACTION MISMATCH"
        if switched and not should:
            error = "R7 SWITCH WITHOUT ELIGIBILITY"
    if switched and (int(switched.get("at",0))<2048 or
                     int(switched.get("restart_after",-1))!=25):
        error="INVALID RESTART SWITCH"
    if mode=="r7_gate" and switched and gate.get("action")!="2048":
        error="UNAUTHORIZED GATE SWITCH"
    row=dict(category=case["category"],dataset_type=case["dataset_type"],
        formula=case["formula"],formula_sha256=case["formula_sha256"],
        source=case["source"],source_revision=case["source_revision"],
        repeat=rep,mode=mode,expected=case["expected"],status=status,
        wall_s=round(wall,6),cpu_s=round(cpu,6),
        par2_s=round(wall,6) if status in ("SAT","UNSAT") else 2*CAP,
        sat_model_checked=sat_checked,native_unsat_certificate_checked=proof,
        route=route,exit_code=proc.returncode,runner=runner,
        seed=case["metadata"].get("seed","frozen SATLIB source"),
        early_restarts=gate.get("restarts",early.get("restarts","")),
        early_g=gate.get("g",early.get("g","")),
        early_p=gate.get("p",early.get("p","")),
        early_d=gate.get("d",early.get("d","")),
        gate_eligible=gate.get("eligible",""),gate_action=gate.get("action",""),
        switch_at=switched.get("at",""),final_conflicts=finish.get("conflicts",""),
        final_restarts=finish.get("restarts",""),
        trace_points=len(traces),error=error)
    return row,dict(category=case["category"],formula=case["formula"],
        repeat=rep,mode=mode,points=traces,early=early,gate=gate,
        switch=switched,final=finish)

def run_shard(category):
    directory=OUT/category
    directory.mkdir(parents=True,exist_ok=True)
    cases=get_cases(category,directory)
    if len(cases)!=10 or len({c["formula_sha256"] for c in cases})!=10:
        raise RuntimeError("Freeze violation: not exactly ten distinct inputs")
    historical = set(Path("experiments/drnas_v16/r7_prior_sha256.txt").read_text().split())
    for c in cases:
        c["category"] = category
        c["metadata"]["matches_historical_sha256"] = c["formula_sha256"] in historical
        if category != "external_satlib" and c["metadata"]["matches_historical_sha256"]:
            raise RuntimeError("Generated input matches historical normalized SHA256: " + c["formula"])
        degrees = [0] * c["n"]
        for clause in c["clauses"]:
            for lit in clause:
                degrees[abs(lit)-1] += 1
        avg = sum(degrees) / len(degrees)
        if avg:
            ordered = sorted(degrees)
            gini = sum((2*i-len(ordered)-1)*d for i,d in enumerate(ordered,1))/(len(ordered)*sum(ordered))
            cv = (sum((d-avg)**2 for d in degrees)/len(degrees))**0.5 / avg
        else:
            gini = cv = None
        c["metadata"]["degree_gini"] = gini
        c["metadata"]["degree_cv"] = cv
    runner=os.environ.get("RUNNER_NAME","unknown")+" / "+platform.processor()
    manifest=dict(category=category,dataset_type=cases[0]["dataset_type"],
        kissat_pin=PIN_KISSAT,satlib_pin=PIN_SATLIB,stable_blob=PIN_STABLE_BLOB,
        cap_seconds=CAP,repeats=REPEATS,modes=MODES,
        freeze="4 strategies fixed before R7 evaluation; R7 threshold <35 was selected after exploratory R6 and is not pre-registered on R6",
        official_competition=False,external_fully_unseen=False,
        independent_kissat_unsat_certificates=False,
        source_commit=os.environ.get("GITHUB_SHA","local"),
        runner=runner,platform=platform.platform(),
        lscpu=subprocess.run(["lscpu"],text=True,capture_output=True).stdout,
        executables={k:sha(p.read_bytes()) for k,p in
           [("kissat_original",ORIGINAL),("kissat_r6",PATCHED),("v1531",STABLE)]},
        cases=[{k:(str(v) if isinstance(v,Path) else v)
            for k,v in c.items() if k!="clauses"} for c in cases])
    dump(directory/"manifest.json",manifest)
    rows=[]
    traces=[]
    for case in cases:
        for repeat in range(REPEATS):
            order=list(MODES)
            random.Random(640000+int(case["formula_sha256"][:12],16)+repeat).shuffle(order)
            for mode in order:
                row,trace=run_one(case,repeat,mode,runner)
                rows.append(row)
                traces.append(trace)
                write_csv(directory/"measurements.partial.csv",rows)
                with (directory/"traces.partial.jsonl").open("a") as f:
                    f.write(json.dumps(trace,sort_keys=True)+"\n")
                print("R7_MEASURE",category,case["formula"],repeat,mode,
                    row["status"],"par2=",row["par2_s"],
                    "trace=",row["trace_points"],"switch=",row["switch_at"],
                    "gate=",row["gate_eligible"],flush=True)
                if row["error"]:
                    dump(directory/"error.json",row)
                    raise RuntimeError(row["error"])
        actual={r["status"] for r in rows if r["formula"]==case["formula"] and
                r["status"] in ("SAT","UNSAT")}
        if len(actual)>1:
            raise RuntimeError("SOLVER DISAGREEMENT "+case["formula"]+str(actual))
    if len(rows)!=120:
        raise RuntimeError("Incomplete strategy matrix")
    write_csv(directory/"measurements.csv",rows)
    (directory/"traces.jsonl").write_text("".join(
        json.dumps(t,sort_keys=True)+"\n" for t in traces))
    (directory/"summary.json").write_text(json.dumps(summarize(rows),indent=2)+"\n")
    print("R7_SHARD_COMPLETE",category,len(rows),flush=True)

def summarize(rows):
    result={}
    for mode in MODES:
        subset=[r for r in rows if r["mode"]==mode]
        if not subset:
            continue
        result[mode]=dict(n=len(subset),
            solved=sum(r["status"] in ("SAT","UNSAT") for r in subset),
            timeout=sum(r["status"]=="TIMEOUT" for r in subset),
            sum_par2=round(sum(float(r["par2_s"]) for r in subset),6),
            median_par2=statistics.median(float(r["par2_s"]) for r in subset),
            trace_512=sum(bool(str(r["early_g"])) for r in subset),
            switched=sum(bool(str(r["switch_at"])) for r in subset))
    if result.get("monitor"):
        baseline=result["monitor"]["sum_par2"]
        for mode in MODES:
            if mode in result:
                result[mode]["speedup_vs_monitor"]=round(
                    baseline/result[mode]["sum_par2"],6)
    if result.get("stable_v1531"):
        baseline=result["stable_v1531"]["sum_par2"]
        for mode in MODES:
            if mode in result:
                result[mode]["speedup_vs_stable_v1531"]=round(
                    baseline/result[mode]["sum_par2"],6)
    return result

def aggregate():
    root=Path("drnas-r6-download")
    rows=[]
    traces=[]
    manifests=[]
    for category in CATEGORIES:
        folder=root/f"r6-{category}"
        if not folder.exists():
            raise RuntimeError("Missing shard "+str(folder))
        with (folder/"measurements.csv").open(newline="") as f:
            part=list(csv.DictReader(f))
        if len(part)!=120:
            raise RuntimeError("Partial shard "+category)
        rows.extend(part)
        traces.extend(json.loads(line) for line in (folder/"traces.jsonl").read_text().splitlines())
        manifests.append(json.loads((folder/"manifest.json").read_text()))
    assert len(rows)==480 and len(traces)==480
    assert len({(r["category"],r["formula"],r["repeat"],r["mode"]) for r in rows})==480
    for r in rows:
        if r["error"]:
            raise RuntimeError("Invalid run "+str(r))
    groups=defaultdict(list)
    for r in rows:
        groups[(r["category"],r["formula"],r["repeat"])].append(r)
    if len(groups)!=120 or any(len(z)!=4 for z in groups.values()):
        raise RuntimeError("Incomplete paired group")
    for key,grp in groups.items():
        if len({r["runner"] for r in grp})!=1:
            raise RuntimeError("Paired runs crossed runners: "+str(key))
        statuses={r["status"] for r in grp if r["status"] in ("SAT","UNSAT")}
        if len(statuses)>1:
            raise RuntimeError("SAT/UNSAT disagreement "+str(key))
    by_trace={(t["category"],t["formula"],str(t["repeat"]),t["mode"]):t for t in traces}
    pairs=[]
    patterns=defaultdict(list)
    deviations=[]
    for key,grp in groups.items():
        d={r["mode"]:r for r in grp}
        base=d["monitor"]
        bt=by_trace.get((*key,"monitor"),{})
        # Prefix evidence is from read-only monitoring, never from the outcome.
        gate=bt.get("gate",{})
        signal=(gate.get("eligible") if gate else "missing")
        if gate:
            restart=float(gate["restarts"]); glue=float(gate["g"])
            propagation=float(gate["p"]); decisions=float(gate["d"])
            signal_classes=[
                "gate_eligible" if signal=="1" else "gate_ineligible",
                "restart_le20" if restart<=20 else "restart_gt20",
                "glue_lt0965" if glue<0.965 else "glue_ge0965",
                "prop_lt35" if propagation<35 else "prop_ge35",
                "decisions_le215" if decisions<=2.15 else "decisions_gt215"]
        else:
            signal_classes=["missing_512_checkpoint"]
        metrics={m:float(d[m]["par2_s"]) for m in MODES}
        trace_map={m:by_trace.get((*key,m),{}).get("points",[]) for m in
            ("monitor","forced_restart25","r7_gate")}
        for m in ("forced_restart25","r7_gate"):
            # Compare only checkpoints at or below 2000, before the action at 2048.
            base_pre={int(float(p["conflict"])):p for p in trace_map["monitor"]
                      if int(float(p["conflict"]))<=2000}
            trial_pre={int(float(p["conflict"])):p for p in trace_map[m]
                      if int(float(p["conflict"]))<=2000}
            for checkpoint in sorted(set(base_pre)&set(trial_pre)):
                b,t=base_pre[checkpoint],trial_pre[checkpoint]
                fields=("restarts","decisions","propagations","learned","glue")
                if any(b.get(f)!=t.get(f) for f in fields):
                    deviations.append(dict(case=key,mode=m,checkpoint=checkpoint,
                        baseline=b,trial=t))
        for mode in ("forced_restart25","r7_gate"):
            ratio=metrics["monitor"]/metrics[mode]
            verdict=("gain" if ratio>1.03 else "regression" if ratio<0.97 else "neutral")
            row=dict(category=key[0],formula=key[1],repeat=key[2],
                mode=mode,monitor_par2=metrics["monitor"],treatment_par2=metrics[mode],
                speedup=round(ratio,6),verdict=verdict,early_gate=signal,
                intervention_applied=bool(d[mode]["switch_at"]))
            pairs.append(row)
            for feature in signal_classes:
                patterns[(mode,feature)].append(row)
    out=OUT/"aggregate"
    out.mkdir(parents=True,exist_ok=True)
    write_csv(out/"measurements.csv",rows)
    with (out/"traces.jsonl").open("w") as f:
        for t in traces:f.write(json.dumps(t,sort_keys=True)+"\n")
    with (out/"paired.csv").open("w",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=tuple(pairs[0]))
        writer.writeheader();writer.writerows(pairs)
    pattern_rows=[]
    for (mode,signal),sub in sorted(patterns.items()):
        pattern_rows.append(dict(mode=mode,signal_class=signal,
            paired_attempts=len(sub),
            intervention_applied=sum(x["intervention_applied"] for x in sub),
            gains=sum(x["verdict"]=="gain" for x in sub),
            regressions=sum(x["verdict"]=="regression" for x in sub),
            neutral=sum(x["verdict"]=="neutral" for x in sub),
            sum_monitor_par2=round(sum(x["monitor_par2"] for x in sub),6),
            sum_treatment_par2=round(sum(x["treatment_par2"] for x in sub),6)))
    with (out/"patterns.csv").open("w",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=tuple(pattern_rows[0]))
        writer.writeheader();writer.writerows(pattern_rows)
    categories={cat:summarize([r for r in rows if r["category"]==cat])
                for cat in CATEGORIES}
    report=dict(total_measurements=len(rows),unique_formulas=40,
        repeats=REPEATS,strategies=MODES,
        categories=categories,overall=summarize(rows),
        early_prefix_mismatch_count=len(deviations),
        early_prefix_mismatches=deviations[:12],
        pattern_groups=pattern_rows,
        caution="Exploratory data, generated and prior public SATLIB; no official ranking; no independent Kissat UNSAT certificate validation",
        reference_pins=[PIN_KISSAT,PIN_STABLE_BLOB,PIN_SATLIB],
        manifests=manifests)
    dump(out/"results.json",report)
    summary=["# DRNAS SAT R7 — four-policy paired measurement",
      "40 formula x 4 modes x 3 repeats = 480 attempts.",
      "A: stable V15.3.1, B: read-only in-process monitor, C: forced restart at 2048, D: R7 early propagation gate p<35.",
      "All comparisons within category are on the same GitHub-hosted runner.",
      "A vs B includes architecture/preprocessing differences; C/D vs B are controlled interventions.",
      "Generated cases and previously public SATLIB are NOT an unseen official holdout.",
      "No official ranking; Kissat UNSAT outputs do not carry independent proof certification.",
      "",
      "| Category | Mode | Solved | PAR-2 (s) | Speedup vs monitor |",
      "|---|---|---:|---:|---:|"]
    for cat,stats in categories.items():
        for mode,item in stats.items():
            summary.append(f"| {cat} | {mode} | {item['solved']}/{item['n']} | {item['sum_par2']:.5f} | {item.get('speedup_vs_monitor',0):.4f}x |")
    summary.extend(["","## Early-signal association with changes (exploratory)",
        "| Mode | Early feature (overlapping groups) | Pairs | Applied | Gains | Regressions |",
        "|---|---|---:|---:|---:|---:|"])
    for p in pattern_rows:
        summary.append(f"| {p['mode']} | {p['signal_class']} | {p['paired_attempts']} | {p['intervention_applied']} | {p['gains']} | {p['regressions']} |")
    summary.append(f"\nPrefix comparison mismatches: {len(deviations)} (review determinism and instrumentation before interpreting effects).")
    (out/"results.md").write_text("\n".join(summary)+"\n")
    print("\n".join(summary),flush=True)

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--category",choices=CATEGORIES)
    parser.add_argument("--aggregate",action="store_true")
    args=parser.parse_args()
    if args.aggregate:
        aggregate()
    elif args.category:
        run_shard(args.category)
    else:
        parser.error("Provide --category or --aggregate")

