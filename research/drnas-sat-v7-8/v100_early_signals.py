#!/usr/bin/env python3
"""DRNAS V10: identically matched unphased 256-conflict prefix and signal ablation.

Predeclared seven post-prefix policies: never/always/LBD/propagations/jump-
depth/all-three/original LBD+prop. Four known 2026 cases are diagnostic only;
eight frozen additional 2026 cases are excluded from the earlier 66-case
manifests before any V10 solver run. No generalization claim without holdout.
"""
import argparse, csv, hashlib, json, os, random, statistics, subprocess, time
from collections import defaultdict
from pathlib import Path
import official_shortlong_select as src
from official_shortlong_select import REV, SCORES_GIT_BLOB

src.RAW_CAP=96*1024*1024
src.CNF_CAP=96*1024*1024
src.VARIABLE_CAP=1_000_000
src.CLAUSE_CAP=4_000_000
SALT="DRNAS-v100-256-identical-LBD-PROP-JUMP-predeclared-20261031"
KNOWN_PREFIXES=("8117a2ac08","91860f79f0","8d0d8518a4","ee44c3f4")
POLICIES=("v100_late_plain_force","v100_late_phase_force",
          "v100_late_lbd_force","v100_late_prop_force",
          "v100_late_jump_force","v100_late_joint_force",
          "v100_late_legacy_force")
ARMS=POLICIES+("v96_phase_force","ca_plain")
EARLY_KEYS=("stage1","v96_status64","v96_status128","v96_c64",
            "v96_c128","v96_lbd2_64","v96_lbd2_128","v96_lbd4_64",
            "v96_lbd4_128","v96_props64","v96_props128",
            "v96_jump64","v96_jump128","v96_learn64","v96_learn128",
            "v90_learned_256","v90_lbd2_256","v90_lbd4_256",
            "v90_lbd_sum_256","v90_props_256","v90_conflicts_256",
            "v90_jumpdepth_256","v90_jumps_256","v90_backtracks_256",
            "learned_delta","threshold","active_pre","active_256",
            "hints","vars","clauses")
CAP=18.0
REPEATS=2

def save(path,obj):
    Path(path).write_text(json.dumps(obj,indent=2,sort_keys=True)+"\n")

def hash_order(txt):
    return hashlib.sha256((SALT+"/"+txt).encode()).hexdigest()

def label_from_score(status):
    if status=="sat-verified":return "SAT"
    if status=="unsat-verified":return "UNSAT"
    return None

def parse_trace(line):
    return dict(part.split("=",1) for part in line.split("\t")[1:])

def gates(t):
    l=int(t["v90_learned_256"])
    c=int(t["v90_conflicts_256"])
    p=int(t["v90_props_256"])
    j=int(t["v90_jumps_256"])
    d=int(t["v90_jumpdepth_256"])
    lbd=l>=20 and c>0 and 100*int(t["v90_lbd2_256"])>=6*l
    prop=c>=32 and p>=32*c
    jump=j>=20 and d>=2*j
    active=int(t["stage1"])==0
    return {
      "v100_late_plain_force":False,
      "v100_late_phase_force":active,
      "v100_late_lbd_force":active and lbd,
      "v100_late_prop_force":active and prop,
      "v100_late_jump_force":active and jump,
      "v100_late_joint_force":active and lbd and prop and jump,
      "v100_late_legacy_force":active and lbd and prop,
    }

def freeze(args):
    older=json.loads(Path(args.v96).read_text())
    known=[]
    for prefix in KNOWN_PREFIXES:
        candidates=[x for x in older["known_diagnostic"] if x["id"].startswith(prefix)]
        assert len(candidates)==1,prefix
        known.append({**candidates[0],"group":"known_2026_diagnostic"})
    excluded=set(older["prior_54_excluded"])
    excluded|={x["id"] for x in older["new_prospective"]}
    excluded|={x["id"] for x in older["known_diagnostic"]}
    assert len(excluded)==66,len(excluded)
    with Path(args.scores).open(newline="",encoding="utf8") as f:
        records=[x for x in csv.DictReader(f) if x["solverid"]=="biere_cadical3[main]"]
    assert len(records)==400
    groups=defaultdict(list)
    for row in records:
        label=label_from_score(row["status"])
        ident=row["instanceid"]
        if label is None or ident in excluded:continue
        t=float(row["runtime"])
        band=("fast" if 0<t<5 else "medium" if 5<=t<=45 else "")
        if band:
            groups[label+"_"+band].append(row)
    accepted=[];attempts=[];selected=set()
    for key in ("SAT_fast","UNSAT_fast","SAT_medium","UNSAT_medium"):
        for row in sorted(groups[key],key=lambda x:hash_order(key+x["instanceid"])):
            if sum(x["stratum"]==key for x in accepted)>=2:break
            ident=row["instanceid"]
            if ident in selected:continue
            try:
                info=src.download_and_features(ident)
                selected.add(ident)
                accepted.append({**info,"group":"new_2026_holdout",
                    "official_label":label_from_score(row["status"]),
                    "stratum":key,"official_ca3_s":float(row["runtime"])})
                attempts.append({"id":ident,"status":"accepted","stratum":key})
                print("V100_FROZEN_ACCEPT",ident,key,flush=True)
            except Exception as exc:
                attempts.append({"id":ident,"status":"reject","stratum":key,
                                 "reason":str(exc)[:250]})
                print("V100_REJECT",ident,key,str(exc)[:90],flush=True)
        if sum(x["stratum"]==key for x in accepted)<2:
            raise RuntimeError("Missing 2 valid CNFs for predeclared stratum "+key)
    assert len(accepted)==8
    accepted.sort(key=lambda x:hash_order("selected/"+x["id"]))
    assert len({c["id"] for c in known+accepted})==12
    save(args.out,dict(protocol=SALT,known=known,holdout=accepted,
        cases=known+accepted,arms=ARMS,cap=CAP,repeats=REPEATS,
        excluded_previous_ids=sorted(excluded),attempts=attempts,
        source_commit=REV,source_scores_git_blob=SCORES_GIT_BLOB,
        precommitted_gates={
          "lbd":"learned>=20 and LBD2>=6% of learned",
          "prop":"conflicts>=32 and >=32 propagations per conflict",
          "jump":"jumps>=20 and mean jump-depth>=2",
          "joint":"LBD AND propagation AND jump",
          "legacy":"LBD AND propagation",
        },limitations=[
          "Four known selected diagnostic cases do not establish generalization",
          "Eight new cases exclude earlier 54+12 2026 manifests, not an exhaustive global repo audit",
          "Official reference times used only for stratified preselection, NEVER routing",
          "Class quotas and capped input size introduce selection bias",
          "Two fixed-seed repeated orders and 18s caps, not official competition rules",
          "SAT model check by solver; UNSAT certificates not separately verified"]))
    print("V100_FROZEN",len(known),len(accepted),len(attempts),flush=True)

def run(args):
    manifest=json.loads(Path(args.manifest).read_text())
    assert manifest["protocol"]==SALT and 0<=args.shard<6
    cases=manifest["cases"][2*args.shard:2*args.shard+2]
    assert len(cases)==2
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    core=min(os.sched_getaffinity(0))
    os.sched_setaffinity(0,{core})
    rows=[]
    exe=str(Path(args.exe).resolve())
    for c in cases:
        fn=out/(c["id"]+".cnf")
        chk=src.download_and_features(c["id"],fn)
        assert chk["sha256"]==c["sha256"]
        assert chk["features"]==c["features"]
        for rep in range(REPEATS):
            seed=(100101+829*rep+int(c["sha256"][:8],16))%(2**32)
            shuffled=list(ARMS);random.Random(seed^9961).shuffle(shuffled)
            for mode in shuffled:
                t0=time.monotonic();early={};final={};err=""
                try:
                    p=subprocess.run([exe,mode,str(fn),str(seed)],
                         capture_output=True,text=True,timeout=CAP,check=False)
                    sec=time.monotonic()-t0
                    if p.returncode:
                        raise RuntimeError("process exit="+str(p.returncode)+
                                           " "+p.stderr[-280:])
                    es=[x for x in p.stdout.splitlines()
                        if x.startswith("DRNAS_EARLY\t")]
                    fs=[x for x in p.stdout.splitlines()
                        if x.startswith("DRNAS_CAUSAL\t")]
                    if len(fs)!=1:raise RuntimeError("No unique DRNAS_CAUSAL final")
                    final=parse_trace(fs[0])
                    early=parse_trace(es[0]) if len(es)==1 else {}
                    status=final["answer"]
                    if final["mode"]!=mode or status!=c["official_label"]:
                        raise RuntimeError("Wrong mode or incorrect SAT/UNSAT")
                except subprocess.TimeoutExpired as exc:
                    status="TIMEOUT";sec=CAP
                    stdout=exc.stdout or b""
                    if isinstance(stdout,bytes):stdout=stdout.decode("utf8","replace")
                    es=[x for x in stdout.splitlines() if x.startswith("DRNAS_EARLY\t")]
                    early=parse_trace(es[-1]) if es else {}
                except Exception as exc:
                    err=str(exc);status="ERROR";sec=time.monotonic()-t0
                if mode in POLICIES and not early:
                    raise RuntimeError("Missing checkpoint trace "+c["id"]+" "+mode)
                if status=="ERROR":
                    raise RuntimeError(c["id"]+" "+mode+" "+err)
                if early and early.get("mode")!=mode:
                    raise RuntimeError("Checkpoint label mismatch")
                row=dict(id=c["id"],group=c["group"],sha256=c["sha256"],
                    seed=seed,rep=rep,cap=CAP,mode=mode,status=status,
                    wall_s=round(sec,6),early=early,final=final,error=err)
                rows.append(row)
                print("V100_TRIAL",c["id"][:10],rep,mode,status,
                    round(sec,3),"LBD2",early.get("v90_lbd2_256","NA"),
                    "PROP",early.get("v90_props_256","NA"),
                    "JUMP",early.get("v90_jumpdepth_256","NA"),flush=True)
        fn.unlink(missing_ok=True)
    assert len(rows)==len(cases)*len(ARMS)*REPEATS==36
    save(out/"raw.json",rows)
    save(out/"meta.json",{"shard":args.shard,"cases":[c["id"] for c in cases],
                           "rows":len(rows),"core":core})
    print("V100_SHARD_PASS",args.shard,len(rows),flush=True)

def audit(args):
    m=json.loads(Path(args.manifest).read_text())
    assert m["protocol"]==SALT and m["arms"]==list(ARMS)
    rows=[]
    for shard in range(6):
        base=Path(args.combined)/("v100-shard-"+str(shard))/"results"
        meta=json.loads((base/"meta.json").read_text())
        assert meta["shard"]==shard and meta["rows"]==36
        assert meta["cases"]==[c["id"] for c in m["cases"][2*shard:2*shard+2]]
        rows.extend(json.loads((base/"raw.json").read_text()))
    assert len(rows)==216,len(rows)
    ids={c["id"]:c for c in m["cases"]}
    assert len(ids)==12
    seen=set();by_pair=defaultdict(dict)
    for r in rows:
        key=(r["id"],r["rep"],r["mode"])
        assert key not in seen and r["id"] in ids
        seen.add(key)
        c=ids[r["id"]]
        assert r["sha256"]==c["sha256"] and r["group"]==c["group"]
        assert r["status"] in ("SAT","UNSAT","TIMEOUT") and not r["error"]
        if r["status"]!="TIMEOUT":
            assert r["status"]==c["official_label"]
        assert r["cap"]==CAP
        by_pair[(r["id"],r["rep"])][r["mode"]]=r
    same_prefix=0
    activation={x:0 for x in POLICIES}
    signal_examples=[]
    for c in m["cases"]:
        for rep in range(REPEATS):
            rr=by_pair[(c["id"],rep)]
            assert set(rr)==set(ARMS)
            traces=[rr[name]["early"] for name in POLICIES]
            assert all(x and all(k in x for k in EARLY_KEYS) for x in traces)
            first=traces[0]
            for t in traces[1:]:
                assert all(t[k]==first[k] for k in EARLY_KEYS),\
                    ("Not identical 256-conflict prefix",c["id"],rep)
                same_prefix+=1
            gate=gates(first)
            for name in POLICIES:
                row=rr[name]
                expected=gate[name]
                actual=bool(int(row["early"]["v100_will_apply"]))
                assert actual==expected,("Incorrect predeclared early gate",c["id"],name)
                activation[name]+=actual
                if row["status"]!="TIMEOUT":
                    assert bool(int(row["final"]["v91_phase_applied"]))==actual
                    assert bool(int(row["final"]["v100_will_apply"]))==actual
            signal_examples.append(dict(id=c["id"],rep=rep,group=c["group"],
                learned=int(first["v90_learned_256"]),
                lbd2=int(first["v90_lbd2_256"]),
                propagations=int(first["v90_props_256"]),
                conflicts=int(first["v90_conflicts_256"]),
                jumps=int(first["v90_jumps_256"]),
                jump_depth_sum=int(first["v90_jumpdepth_256"]),
                activations={k:int(v) for k,v in gate.items()}))
    cohorts={}
    for group in ("known_2026_diagnostic","new_2026_holdout","all"):
        records=[r for r in rows if group=="all" or r["group"]==group]
        by_arm={}
        for mode in ARMS:
            part=[r for r in records if r["mode"]==mode]
            scores=[2*CAP if r["status"]=="TIMEOUT" else r["wall_s"] for r in part]
            by_arm[mode]=dict(solved=sum(r["status"]!="TIMEOUT" for r in part),
                n=len(part),mean_PAR2_s=statistics.mean(scores))
        cohorts[group]=by_arm
    cases=[]
    for c in m["cases"]:
        rr=[r for r in rows if r["id"]==c["id"]]
        stats={}
        for mode in ARMS:
            part=[r for r in rr if r["mode"]==mode]
            stats[mode]=statistics.mean(
                2*CAP if r["status"]=="TIMEOUT" else r["wall_s"] for r in part)
        oracle=min(stats["v100_late_plain_force"],stats["v100_late_phase_force"])
        cases.append(dict(id=c["id"],group=c["group"],PAR2=stats,
            late_phase_benefit_s=stats["v100_late_plain_force"]-
                                 stats["v100_late_phase_force"],
            oracle_plain_vs_always=oracle))
    report=dict(protocol=SALT,trials=len(rows),cases=cases,cohorts=cohorts,
                identical_prefix_pairs=same_prefix,gate_activations=activation,
                early_signals=signal_examples,limitations=m["limitations"])
    save(args.out,report)
    lines=["# DRNAS V10 — Identical-prefix signal ablation","",
        "216 scheduled matched attempts = 12 CNFs × 9 arms × 2 repeats.",
        "All seven V10 arms share exactly the same FIRST 256 conflicts.",
        "Predeclared before benchmark: LBD, propagation rate, mean jump depth,",
        "their AND combination and original LBD+propagation joint rule.",
        "Verified equal early traces: "+str(same_prefix)+" independent pairwise checks.",
        "No historical or official leaderboard claim.","",
        "## Gate activation counts (of 24 case/repeat pairs)",""]
    for name,n in activation.items():lines.append("- "+name+": "+str(n)+"/24")
    for group in ("known_2026_diagnostic","new_2026_holdout","all"):
        lines.extend(["","## "+group,"",
            "| Method | Solved | Mean PAR2 s (lower is better) |",
            "|---|---:|---:|"])
        for mode,v in cohorts[group].items():
            lines.append("| "+mode+" | "+str(v["solved"])+"/"+str(v["n"])+
                         " | "+format(v["mean_PAR2_s"],".4f")+" |")
    lines.extend(["","## Per-instance performance: positive phase benefit means late phases help"])
    for c in cases:
        lines.append("- "+c["id"][:12]+" "+c["group"]+
            " phase benefit: "+format(c["late_phase_benefit_s"],"+.3f")+
            " s; LBD gate: "+format(c["PAR2"]["v100_late_lbd_force"],".3f")+
            ", prop gate: "+format(c["PAR2"]["v100_late_prop_force"],".3f")+
            ", jump gate: "+format(c["PAR2"]["v100_late_jump_force"],".3f")+
            ", joint: "+format(c["PAR2"]["v100_late_joint_force"],".3f"))
    lines.extend(["","Eight holdout CNFs exclude 66 prior official 2026 identifiers only.",
        "SAT/UNSAT labels are from the official 2026 scoreboard;",
        "UNSAT proofs were not independently checked."])
    Path(args.md).write_text("\n".join(lines)+"\n")
    print("\n".join(lines),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    sub=p.add_subparsers(dest="cmd",required=True)
    for mode,params in (("freeze",("v96","scores","out")),
                        ("run",("manifest","exe","out")),
                        ("audit",("manifest","combined","out","md"))):
        a=sub.add_parser(mode)
        for name in params:a.add_argument("--"+name,required=True)
        if mode=="run":a.add_argument("--shard",type=int,required=True)
    args=p.parse_args()
    {"freeze":freeze,"run":run,"audit":audit}[args.cmd](args)
