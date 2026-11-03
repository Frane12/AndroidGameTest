#!/usr/bin/env python3
"""DRNAS R31: consistent XOR gap vs contradictory XOR vs decoy, native CDCL.

Frozen SHA inputs, proof-checked offline complete-XOR reconstruction,
equal-process Kissat policies, matched native CDCL telemetry. GF2 preprocessing
is counted in the solve wall time. Experimental injected root units are
MATHEMATICALLY ENTAILED; no model is trained and no restarts/phases are edited.

Four arms: unmodified Kissat, read-only native monitor, shadow GF2 scan,
GF2-certified added-unit clauses + same read-only native monitor.
Output must not be interpreted as an in-process GF2 plugin.
"""
from __future__ import annotations
import argparse, collections, csv, gzip, hashlib, json, lzma, os, random
import re, statistics, subprocess, tempfile, time
from pathlib import Path
import r30_passive_monitor as r30

PROTO="DRNAS-R31-CONSISTENT-ROOT-GF2-VS-CDCL-20261103-v1"
SALT="DRNAS-R31-CONSISTENT-BRIDGE-NOV03-2026-SHA-FROZEN-V1"
PIN=r30.UPSTREAM
FAMILIES=("consistent_visible","consistent_hidden","consistent_mixed",
          "consistent_conditional","root_unsat","xor_decoy","planted_random3")
NUM_PER=4
OFFICIAL_N=2
REPS=2
SHARDS=4
CAP=4.0
MODES=("clean","passive","GF2_shadow","GF2_units")
MAX_PROCESS_BYTES=8*1024*1024
MAX_VARS=1024
MAX_CLAUSES=10000

def check(cond,msg):
    if not cond:raise RuntimeError("R31_PROOF_OR_BENCHMARK_ERROR "+str(msg))
def digest(content):
    if isinstance(content,Path):content=content.read_bytes()
    return hashlib.sha256(content).hexdigest()
def rng_of(family,idx):
    return random.Random(int(digest((SALT+"/"+family+"/"+str(idx)).encode()),16))
def planted_clause(rng,vs,truth,k=3):
    v=rng.sample(vs,k)
    cl=[x if rng.getrandbits(1) else -x for x in v]
    if not any((l>0)==bool(truth[abs(l)]) for l in cl):cl[0]*=-1
    return cl
def make_case(family,idx):
    rng=rng_of(family,idx)
    if family=="planted_random3":
        n=220+20*(idx%2)
        truth={i:rng.getrandbits(1) for i in range(1,n+1)}
        clauses=[planted_clause(rng,list(truth),truth) for _ in range(int(n*4.18))]
        return n,clauses,"SAT",truth
    copies=8+4*(idx%2)
    clauses=[];truth={}
    for g in range(copies):
        x,y,z,w=4*g+1,4*g+2,4*g+3,4*g+4
        choice=rng.getrandbits(1)
        zval=rng.getrandbits(1) if family=="consistent_conditional" else 0
        truth.update({x:choice,y:choice,z:zval,w:1^zval})
        clauses+=r30.xor_clauses([x,y,z],0)
        clauses+=r30.xor_clauses([x,y,w],1)
        if family!="consistent_conditional":clauses.append([-z])
    if family=="root_unsat":
        # First gadget has z=0, so the original XORs imply w=1;
        # this unit creates a genuine GF2 root contradiction.
        clauses.append([-4])
    if family=="xor_decoy":
        # Delete one forbidden assignment from each parity block.
        # Keep all unit clauses and ensure every parity block is incomplete.
        trimmed=[];groups={}
        for cl in clauses:
            if len(cl)==3:
                key=tuple(sorted(abs(v) for v in cl))
                groups.setdefault(key,[]).append(cl)
            else:trimmed.append(cl)
        for cc in groups.values():
            check(len(cc)==4,"Expected complete XOR3 block before decoy removal")
            trimmed+=cc[:3]
        clauses=trimmed
    n=4*copies
    if family=="consistent_hidden":
        transformed=[]
        for cl in clauses:
            if len(cl)==3:
                random_cl=list(cl);rng.shuffle(random_cl)
                n+=1
                transformed.extend([[random_cl[0],n],[-n]+random_cl[1:]])
                truth[n]=0 if (random_cl[0]>0)==bool(truth[abs(random_cl[0])]) else 1
                # With (a v t) AND (!t v b v c), when a=false, t=true;
                # when a=true and (b v c)=true, t=false is valid.
            else:transformed.append(cl)
        clauses=transformed
    hard=family in ("consistent_visible","consistent_hidden",
                    "consistent_mixed","consistent_conditional","root_unsat")
    if hard:
        extra_n=130+(idx%2)*30
        random_vars=list(range(n+1,n+extra_n+1))
        for v in random_vars:truth[v]=rng.getrandbits(1)
        n+=extra_n
        # Planted 3-SAT background: recognizable XOR is a subset of the formula.
        # All noise clauses are satisfied by the known witness (except root UNSAT).
        for _ in range(int(extra_n*3.9)):
            clauses.append(planted_clause(rng,random_vars,truth))
        if family in ("consistent_mixed","consistent_hidden","consistent_visible"):
            for j in range(110):
                bridge=4*(j%copies+1)
                others=rng.sample(random_vars,2)
                # Negative bridge literal is false when known implied w=1.
                cl=[-bridge]+[v if rng.getrandbits(1) else -v for v in others]
                if not any((l>0)==bool(truth[abs(l)]) for l in cl):
                    cl[1]*=-1
                clauses.append(cl)
    rng.shuffle(clauses)
    if family!="root_unsat":
        check(all(any((l>0)==bool(truth[abs(l)]) for l in c) for c in clauses),
              "Known SAT model fails "+family)
    return n,clauses,"UNSAT" if family=="root_unsat" else "SAT",truth
def encode(n,clauses):
    return (f"p cnf {n} {len(clauses)}\n" +
            "".join(" ".join(map(str,c))+" 0\n" for c in clauses)).encode()
def freeze(dest,official):
    out=Path(dest);out.mkdir(parents=True,exist_ok=True)
    cases=[]
    for family in FAMILIES:
        for idx in range(NUM_PER):
            n,clauses,truth=0,[],None
            n,clauses,expected,truth=make_case(family,idx)
            data=encode(n,clauses)
            name=f"{family}_{idx:02d}.cnf"
            (out/name).write_bytes(data)
            cases.append(dict(file=name,family=family,expected=expected,
                              vars=n,clauses=len(clauses),bytes=len(data),
                              sha256=digest(data),source="R31_new_frozen_generator"))
    if official:
        src=Path(official)
        archive=json.loads((src/"manifest.json").read_text())
        check(archive["protocol"]=="DRNAS-R28-AND-XOR-PHASE-AB-AUDIT-20261103-v1",
              "Unknown official original-source archive")
        selected=[x for x in archive["cases"] if x["role"]=="previously_measured_development"][:OFFICIAL_N]
        check(len(selected)==OFFICIAL_N,"Missing GBD original controls")
        for i,x in enumerate(selected):
            source=src/x["path"]
            check(digest(source)==x["sha256"],"Original GBD SHA mismatch")
            data=source.read_bytes()
            if data.startswith(b"\xfd7zXZ\x00"):data=lzma.decompress(data)
            if data.startswith(b"\x1f\x8b"):data=gzip.decompress(data)
            check(b"p cnf " in data[:2048],"Original GBD DIMACS missing")
            name=f"official_gbd_{i:02d}.cnf"
            (out/name).write_bytes(data)
            cases.append(dict(file=name,family="official_gbd_2026",
                              expected=x["expected"],vars=None,clauses=None,
                              bytes=len(data),sha256=digest(data),
                              original_sha256=x["sha256"],source=x["source"]))
    check(len(cases)==len(FAMILIES)*NUM_PER+(OFFICIAL_N if official else 0),
          "Wrong case count")
    check(len({x["sha256"] for x in cases})==len(cases),"Duplicate SHA input")
    manifest=dict(protocol=PROTO,salt=SALT,source_commit=PIN,
                  cap_s=CAP,repeats=REPS,shards=SHARDS,modes=MODES,
                  original_cases=OFFICIAL_N if official else 0,cases=cases,
                  caveats=["Genuine original GBD controls were previously seen in R28/R30",
                           "All new XOR and non-XOR cohorts are synthetic SHA-frozen",
                           "Certified root units are injected in a temporary DIMACS copy only",
                           "No learned-XOR clause extraction and no solver-policy intervention",
                           "R30 native snapshot is an export projection, not a fully equivalent CDCL internal trail",
                           "Root-BPC and exact GF2 soundness checked by a separate original-CNF logic audit",
                           "A root UNSAT XOR contradiction suppresses individual-unit signal",
                           "All timings include external GF2 scan and temporary file write for injection",
                           "Native counters are from the same read-only instrumented Kissat process",
                           "At 4-second timeout true completion time is unknown"])
    (out/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
    (out/"cnf.sha256").write_text("".join(x["sha256"]+"  "+x["file"]+"\n" for x in cases))
    print("R31_FROZEN",len(cases),digest(out/"manifest.json"),flush=True)

def prove_resolution(original,n):
    occurs=[[[],[]] for _ in range(n+1)]
    for idx,cl in enumerate(original):
        for lit in cl:occurs[abs(lit)][int(lit<0)].append(idx)
    used=set();resolved=[];steps=[]
    for v in range(1,n+1):
        pos,neg=occurs[v]
        if len(pos)!=1 or len(neg)!=1:continue
        p,q=pos[0],neg[0]
        if p in used or q in used:continue
        a,b=original[p],original[q]
        if not ((len(a)==2 and 2<=len(b)<=6) or
                (len(b)==2 and 2<=len(a)<=6)):continue
        combined={lit for parent in (a,b) for lit in parent if abs(lit)!=v}
        if len(combined)<2 or len(combined)>6 or any(-x in combined for x in combined):
            continue
        derived=tuple(sorted(combined,key=lambda lit:(abs(lit),lit<0)))
        # Independent proof against the exact two original source clauses.
        check(v in a and -v in b and
              set(derived)==set(a+b)-{v,-v},
              "Resolution parent/certificate mismatch")
        used.update((p,q));resolved.append(list(derived))
        steps.append(dict(eliminate=v,positive_parent=p,negative_parent=q,
                          resolvent=list(derived)))
    return [cl for i,cl in enumerate(original) if i not in used]+resolved,steps

def verified_equations(transformed):
    equations=r30.extract_equations(transformed)
    original_support={tuple(sorted(cl,key=lambda lit:(abs(lit),lit<0))) for cl in transformed}
    for bits,rhs,vars_list in equations:
        vs=tuple(vars_list)
        check(bits==sum(1<<(v-1) for v in vs),"XOR bitset incorrect")
        if len(vs)==1:
            unit=vs[0] if rhs else -vs[0]
            check((unit,) in original_support,"Missing proven unit clause")
        else:
            check(2<=len(vs)<=6 and len(set(vs))==len(vs),
                  "Invalid parity support")
            for mask in range(1<<len(vs)):
                if mask.bit_count()%2==rhs:continue
                clause=tuple(sorted((-v if mask>>i&1 else v for i,v in enumerate(vs)),
                                    key=lambda lit:(abs(lit),lit<0)))
                check(clause in original_support,"Incomplete parity block")
    return equations

def gf2_certified_root(eqs,root_assign):
    # Append original-CNF BCP-derived root units as sound equations.
    all_eq=[(bits,rhs,tuple(vs)) for bits,rhs,vs in eqs]
    all_eq += [(1<<(v-1),val,(v,)) for v,val in sorted(root_assign.items())]
    basis={}
    contradiction=False;bad_proof=0
    for idx,(bits,rhs,_vs) in enumerate(all_eq):
        row=bits;value=rhs;proof=1<<idx
        while row:
            p=(row&-row).bit_length()-1
            if p not in basis:
                basis[p]=(row,value,proof);break
            x,y,z=basis[p];row^=x;value^=y;proof^=z
        if not row and value:
            contradiction=True;bad_proof=proof
            break
    if contradiction:
        row=0;rhs=0
        for i,(bits,val,_vs) in enumerate(all_eq):
            if bad_proof>>i&1:row^=bits;rhs^=val
        check(row==0 and rhs==1,"GF2 root contradiction witness invalid")
        return dict(signal="ROOT_GF2_UNSAT",extra={},rank=len(basis),
                    equations=len(eqs),contradiction_proof=bad_proof.bit_count())
    for p in sorted(basis,reverse=True):
        br,bv,bproof=basis[p]
        for q in list(basis):
            if q==p:continue
            qr,qv,qproof=basis[q]
            if qr & (1<<p):basis[q]=(qr^br,qv^bv,qproof^bproof)
    units={}
    for row,rhs,proof in basis.values():
        if row.bit_count()!=1:continue
        v=row.bit_length()
        if v in root_assign:continue
        # Independent proof check via XOR of exactly the source equations.
        check(proof.bit_count()>=1,"Unit has no proof")
        xorbits=0;xorval=0
        for k,(bits,val,_vs) in enumerate(all_eq):
            if proof>>k&1:xorbits^=bits;xorval^=val
        check(xorbits==row and xorval==rhs,
              "Derived GF2 unit not mathematically entailed")
        units[v]=(rhs,proof.bit_count())
    return dict(signal="CONSISTENT_EXTRA_UNITS" if units else "CONSISTENT_NO_UNITS",
                extra=units,rank=len(basis),equations=len(eqs),contradiction_proof=0)

def structure(original_file):
    parsed,meta=r30.parse_dimacs(original_file)
    if parsed is None:
        return dict(signal="INPUT_GUARD",guard=meta.get("guard"),
                    units=[],covered=0,proofs=[],structure_time=None),None
    n,original=parsed
    transformed,steps=prove_resolution(original,n)
    equations=verified_equations(transformed)
    root,root_conflict=r30.bcp(original,{})
    if root_conflict:
        return dict(signal="ROOT_BCP_CONFLICT",guard="none",units=[],
                    covered=0,proofs=[],structure_time=None),dict(n=n,clauses=original,eq=equations)
    state=gf2_certified_root(equations,root)
    extras=[dict(literal=v if val else -v,rows=k)
            for v,(val,k) in sorted(state["extra"].items())]
    record=dict(signal=state["signal"],guard="none",units=extras,
                root_bcp_units=len(root),resolution_steps=len(steps),
                complete_GF2_equations=len(equations),gf2_rank=state["rank"],
                contradiction_proof_rows=state["contradiction_proof"],
                covered=len(transformed),proofs=steps[:5],structure_time=None)
    return record,dict(n=n,clauses=original,eq=equations)
def projection_gap(t,context):
    if not t["complete"]:return dict(kind="NO_VALID_SNAPSHOT")
    if context is None:return dict(kind="INPUT_GUARD")
    assignment={}
    for ext,level,reason in t["trail"]:
        v=abs(ext);val=int(ext>0)
        if v in assignment and assignment[v]!=val:
            return dict(kind="TRAIL_CONFLICT")
        assignment[v]=val
    closed,conflict=r30.bcp(context["clauses"],assignment)
    if conflict:return dict(kind="ORIGINAL_BCP_BRANCH_CONFLICT")
    result=r30.rank_units(context["eq"],closed)
    if result["contradiction"]:
        return dict(kind="GF2_BRANCH_CONFLICT",units=0)
    return dict(kind="CONSISTENT_GAP" if result["extra_units"] else "NO_GAP",
                units=len(result["extra_units"]),
                extra=[v if val else -v for v,val in sorted(result["extra_units"].items())])
def parse_final(stdout):
    m=re.findall(r"c R31_FINAL status=(\d+) conflict=(\d+) decisions=(\d+) restarts=(\d+) propagations=(\d+) learned=(\d+)",stdout)
    check(len(m)<=1,"Duplicate native final telemetry")
    if not m:return None
    a=list(map(int,m[0]))
    return dict(zip(("solver_status","conflicts","decisions","restarts","propagations","learned"),a))
def attempt(mode,binaries,path,truth_label):
    start=time.monotonic()
    structural=None;context=None;temp=None;solver_input=path
    if mode in ("GF2_shadow","GF2_units"):
        start_struct=time.monotonic()
        structural,context=structure(path)
        structural["structure_time"]=round(time.monotonic()-start_struct,6)
        if mode=="GF2_units" and structural["signal"]=="CONSISTENT_EXTRA_UNITS":
            # Original CNF + mathematical consequences, NOT altered solver policy.
            # All units were independently re-derived above from complete blocks.
            temp=tempfile.TemporaryDirectory(prefix="drnas-r31-")
            solver_input=Path(temp.name)/"with_certified_root_units.cnf"
            _n,clauses=context["n"],context["clauses"]
            units=[x["literal"] for x in structural["units"]]
            check(not ({abs(u) for u in units}&
                       {abs(cl[0]) for cl in clauses if len(cl)==1}),
                  "Already-root clause counted as novel")
            solver_input.write_bytes(encode(_n,clauses+[[v] for v in units]))
            structural["derived_input_sha256"]=digest(solver_input)
    cmd=[str(binaries["clean"] if mode=="clean" else binaries["passive"]),str(solver_input)]
    elapsed_prep=time.monotonic()-start
    try:
        if elapsed_prep>=CAP:raise subprocess.TimeoutExpired(cmd,CAP)
        p=subprocess.run(cmd,capture_output=True,text=True,errors="replace",timeout=CAP-elapsed_prep)
        elapsed=time.monotonic()-start
        check(p.returncode in (10,20),"Solver error "+mode+" "+p.stderr[-400:])
        status="SAT" if p.returncode==10 else "UNSAT"
        check(not truth_label or status==truth_label.upper(),
              "Expected label mismatch "+mode)
        stdout=p.stdout
        if status=="SAT" and context is not None:
            check(r30.model_valid(stdout,context["clauses"],context["n"]),
                  "SAT model violates original clauses")
        verified="SAT_on_original_checked" if status=="SAT" and context else "reference_label_only"
    except subprocess.TimeoutExpired as e:
        elapsed=time.monotonic()-start
        stdout=e.stdout or b""
        if isinstance(stdout,bytes):stdout=stdout.decode(errors="replace")
        status="TIMEOUT";verified="not_applicable"
    finally:
        if temp:temp.cleanup()
    final=parse_final(stdout) if mode!="clean" else None
    if final and status!="TIMEOUT":
        check(final["solver_status"]==(10 if status=="SAT" else 20),
              "Native final status mismatches result")
    snapshots=r30.parse_traces(stdout) if mode!="clean" else []
    for t in snapshots:t["r31_classification"]=projection_gap(t,context)
    record=dict(status=status,seconds=round(elapsed,6),
                par2=round(elapsed,6) if status!="TIMEOUT" else 2*CAP,
                verification=verified,structure=structural,
                final=final,snapshots=snapshots)
    return record

def measure(a):
    root=Path(a.inputs);m=json.loads((root/"manifest.json").read_text())
    check(m["protocol"]==PROTO and m["modes"]==list(MODES)
          and m["cap_s"]==CAP and m["repeats"]==REPS,"Frozen manifest drift")
    check(0<=a.shard<SHARDS,"Shard index")
    if hasattr(os,"sched_getaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    binaries={name:Path(getattr(a,name)).resolve() for name in ("clean","passive")}
    check(all(p.is_file() for p in binaries.values()),"Missing native binaries")
    output=Path(a.outdir);output.mkdir(parents=True,exist_ok=True)
    meta=dict(shard=a.shard,manifest_sha256=digest(root/"manifest.json"),
              binary_sha256={k:digest(v) for k,v in binaries.items()})
    (output/"meta.json").write_text(json.dumps(meta,indent=2)+"\n")
    results=[]
    for case in m["cases"][a.shard::SHARDS]:
        path=(root/case["file"]).resolve()
        check(digest(path)==case["sha256"],"CNF SHA drift "+case["file"])
        preliminary,ctx=structure(path)
        print("R31_STATIC",case["file"],preliminary["signal"],
              "units",len(preliminary["units"]),"equations",
              preliminary.get("complete_GF2_equations",0),flush=True)
        for rep in range(REPS):
            order=list(MODES)
            random.Random(int(digest((case["sha256"]+"order"+str(rep)).encode()),16)).shuffle(order)
            for mode in order:
                attempt_result=attempt(mode,binaries,path,case["expected"])
                row=dict(file=case["file"],family=case["family"],repeat=rep,mode=mode,
                         **attempt_result)
                results.append(row)
                (output/"trials.json").write_text(json.dumps(results,indent=1)+"\n")
                print("R31_TRIAL",a.shard,case["file"],rep,mode,row["status"],
                      row["seconds"],"conflicts",row["final"]["conflicts"] if row["final"] else "censored",
                      "signal",preliminary["signal"],flush=True)
        outcomes={r["status"] for r in results if r["file"]==case["file"]}-{"TIMEOUT"}
        check(len(outcomes)<=1,"Contradictory SAT outcomes")
    print("R31_SHARD_COMPLETE",a.shard,len(results),flush=True)

def aggregate(a):
    root=Path(a.inputs);manifest=json.loads((root/"manifest.json").read_text())
    rows=[];binary_sha=set()
    for shard in range(SHARDS):
        folder=Path(a.combined)/f"r31-shard-{shard}"/"results"
        meta=json.loads((folder/"meta.json").read_text())
        check(meta["shard"]==shard and meta["manifest_sha256"]==digest(root/"manifest.json"),
              "Shard provenance mismatch")
        binary_sha.add(json.dumps(meta["binary_sha256"],sort_keys=True))
        shard_rows=json.loads((folder/"trials.json").read_text())
        check(len(shard_rows)==len(manifest["cases"][shard::SHARDS])*REPS*len(MODES),
              "Missing shard attempt")
        rows+=shard_rows
    check(len(binary_sha)==1 and len(rows)==len(manifest["cases"])*REPS*len(MODES),
          "Incomplete attempts or binary drift")
    summary={}
    groups=["ALL"]+list(FAMILIES)+(["official_gbd_2026"] if manifest["original_cases"] else [])
    for fam in groups:
        selected=[c for c in manifest["cases"] if fam=="ALL" or c["family"]==fam]
        d={}
        for mode in MODES:
            arr=[x for x in rows if x["mode"]==mode and (fam=="ALL" or x["family"]==fam)]
            check(len(arr)==len(selected)*REPS,"Incomplete strategy family")
            solved=sum(all(x["status"]!="TIMEOUT" for x in arr if x["file"]==c["file"])
                       for c in selected)
            native=[x["final"]["conflicts"] for x in arr if x["final"] is not None]
            d[mode]=dict(PAR2_sum=round(sum(x["par2"] for x in arr),6),
                         solved_cases=solved,timeout_trials=sum(x["status"]=="TIMEOUT" for x in arr),
                         total_native_conflicts=sum(native) if native else None,
                         native_finished=len(native),
                         snapshots=sum(len(x["snapshots"]) for x in arr))
        shadow=[x for x in rows if x["mode"]=="GF2_shadow" and
                (fam=="ALL" or x["family"]==fam)]
        tags=collections.Counter(x["structure"]["signal"] for x in shadow)
        d["signals"]=dict(tags)
        d["novel_proven_units_total"]=sum(len(x["structure"]["units"]) for x in shadow)
        d["consistent_gap_snapshots"]=sum(t["r31_classification"]["kind"]=="CONSISTENT_GAP"
                                         for x in shadow for t in x["snapshots"])
        d["branch_contradiction_snapshots"]=sum(t["r31_classification"]["kind"]=="GF2_BRANCH_CONFLICT"
                                                 for x in shadow for t in x["snapshots"])
        base=d["GF2_shadow"]["PAR2_sum"]
        inj=d["GF2_units"]["PAR2_sum"]
        d["paired_GF2_injection_gain_pct"]=round(100*(base-inj)/max(base,1e-9),3)
        summary[fam]=d
        print("R31_SUMMARY",fam,json.dumps(d,sort_keys=True),flush=True)
    case_rows=[]
    for c in manifest["cases"]:
        data=[x for x in rows if x["file"]==c["file"]]
        s=next(x["structure"] for x in data if x["mode"]=="GF2_shadow")
        med={m:round(statistics.median(x["par2"] for x in data if x["mode"]==m),6)
             for m in MODES}
        confl={}
        for m in MODES:
            native=[x["final"]["conflicts"] for x in data if x["mode"]==m and x["final"]]
            confl[m]=statistics.median(native) if len(native)==REPS else None
        case_rows.append(dict(file=c["file"],family=c["family"],SHA=c["sha256"],
                              signal=s["signal"],proven_units=len(s["units"]),
                              literals=[z["literal"] for z in s["units"]],
                              median_PAR2=med,median_native_conflicts=confl))
    final=dict(protocol=PROTO,manifest_SHA=digest(root/"manifest.json"),
               binary_SHA=json.loads(next(iter(binary_sha))),
               summary=summary,per_case=case_rows,rows=rows,
               warnings=["Controlled root-unit experiment on synthetic sources and two previously seen official GBD cases",
                         "Not a scientific proof of general SAT speedup or real-time in-process model",
                         "Both shadow and injection start the same read-only instrumented pinned Kissat",
                         "Native conflict counts for timeout attempts are censored (no final count)",
                         "Only proof-verified complete parity CNF and root BCP can generate injected units",
                         "GF2 contradiction signals suppress unit counts and never trigger unit injection"])
    Path(a.output).write_text(json.dumps(final,indent=2)+"\n")
    report=["# DRNAS R31 — consistent GF(2) gap vs contradiction controlled test",
            f"{len(manifest['cases'])} frozen formulas, two repeats, four arms: {len(rows)} trials.",
            "4s timeout, PAR2 penalty 8s; same CPU, pinned Kissat, standalone shadow preprocessing.",
            "**All injected unit clauses were independently justified by complete XOR blocks and root BCP.**",
            "Shadow and injected arms use the SAME unmodified-policy R31 native monitor.",
            "", "| Family | Clean PAR2 | Passive PAR2 | GF2 shadow PAR2 | GF2 injected PAR2 | Inject gain vs shadow |",
            "|---|---:|---:|---:|---:|---:|"]
    for fam,d in summary.items():
        report.append("| "+fam+" | "+" | ".join(f"{d[m]['PAR2_sum']:.4f}" for m in MODES)+
                      f" | {d['paired_GF2_injection_gain_pct']:+.2f}% |")
    report+=["","## Formula-level classification","| Formula | Signal | Novel units | Shadow PAR2 | Inject PAR2 | Native shadow conflicts | Native injected conflicts |",
             "|---|---|---:|---:|---:|---:|---:|"]
    for x in case_rows:
        m=x["median_PAR2"];c=x["median_native_conflicts"]
        report.append(f"| {x['file']} | {x['signal']} | {x['proven_units']} | "
                      f"{m['GF2_shadow']:.4f} | {m['GF2_units']:.4f} | "
                      f"{c['GF2_shadow'] if c['GF2_shadow'] is not None else 'timeout'} | "
                      f"{c['GF2_units'] if c['GF2_units'] is not None else 'timeout'} |")
    Path(a.report).write_text("\n".join(report)+"\n")
    with Path(a.csv).open("w",newline="") as f:
        w=csv.writer(f)
        w.writerow(["file","family","signal","certified_units","clean_PAR2","passive_PAR2",
                    "shadow_PAR2","units_PAR2","shadow_conflicts","units_conflicts"])
        for x in case_rows:
            p=x["median_PAR2"];c=x["median_native_conflicts"]
            w.writerow([x["file"],x["family"],x["signal"],x["proven_units"],
                        p["clean"],p["passive"],p["GF2_shadow"],p["GF2_units"],
                        c["GF2_shadow"],c["GF2_units"]])
    print("R31_COMPLETE_PROOF_AUDIT",len(rows),"runs",len(case_rows),"cases",flush=True)

def preflight(a):
    root=Path(a.inputs)
    for name,expected in [("consistent_visible_00.cnf","CONSISTENT_EXTRA_UNITS"),
                          ("consistent_hidden_00.cnf","CONSISTENT_EXTRA_UNITS"),
                          ("root_unsat_00.cnf","ROOT_GF2_UNSAT"),
                          ("xor_decoy_00.cnf","CONSISTENT_NO_UNITS"),
                          ("planted_random3_00.cnf","CONSISTENT_NO_UNITS"),
                          ("consistent_conditional_00.cnf","CONSISTENT_NO_UNITS")]:
        res,context=structure(root/name)
        print("R31_PREFLIGHT",name,res["signal"],"units",len(res["units"]),
              "eq",res.get("complete_GF2_equations",0),flush=True)
        check(res["signal"]==expected,"Wrong expected research signal on "+name)
        if res["signal"]=="CONSISTENT_EXTRA_UNITS":
            check(len(res["units"])>=8,"Too few independently proven units")
    print("R31_MATH_PREFLIGHT_PASS",flush=True)
def main():
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest="mode",required=True)
    x=sub.add_parser("freeze");x.add_argument("--out",required=True);x.add_argument("--official")
    x=sub.add_parser("preflight");x.add_argument("--inputs",required=True)
    x=sub.add_parser("measure")
    for arg in ("inputs","clean","passive","outdir"):x.add_argument("--"+arg,required=True)
    x.add_argument("--shard",required=True,type=int)
    x=sub.add_parser("aggregate")
    for arg in ("inputs","combined","output","report","csv"):x.add_argument("--"+arg,required=True)
    a=p.parse_args()
    if a.mode=="freeze":freeze(a.out,a.official)
    elif a.mode=="preflight":preflight(a)
    elif a.mode=="measure":measure(a)
    else:aggregate(a)
if __name__=="__main__":main()
