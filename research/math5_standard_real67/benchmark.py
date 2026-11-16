#!/usr/bin/env python3
"""DRNAS MATH5 standard-VeriPB full 67-original source-frozen paired E2E audit.

A *sequential* proof-producing X59 native solver and external checker chain,
not a second solver/portfolio or an in-process C++ VeriPB generator.
Source and executable SHA are pinned from completed GRAND UNIFIED run
43853390060. This is RETROSPECTIVE, not a prospective blind holdout.
No solver result is accepted without original-source model/proof verification.
"""
import argparse
import collections
import hashlib
import json
import os
from pathlib import Path
import random
import statistics
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/"research"/"unified_evidence"))
import benchmark as frozen
sys.path.insert(0,str(ROOT/"research"/"math5"))
import math5_standard_pilot as math5_smoke

OUT=ROOT/"results/math5_veripb_real67"
CAP=frozen.CAP
SHARDS=frozen.SHARDS
REPS=frozen.REPS
ARMS=("X59_MATH5_VERIPB","X59_MATH5","X59_OFF","CORE1_FROZEN",
      "CXX_BDD3","Kissat","CaDiCaL","CryptoMiniSat")
REFS=("Kissat","CaDiCaL","CryptoMiniSat")
STRICT_KINDS={"MODEL","DRAT","FRAT","VERIPB_CAPACITY","VERIPB_MATH5"}
EMITTER=ROOT/"research/math5/emit_veripb_eo_multiplicity.py"
VERIPB=ROOT/"veripb-tool/bin/veripb"
SOURCE_IDS_EXPECTED={
  25:"28b9b934f492f135dd00c3771d7670703daeb2fa03f98cf21ea8b7286958af4e",
  31:"8020990ff906e9b2f7ec72652da7db736d90db4170e104a888454dffa583aa88"
}

def sha(path):
    return frozen.sha(path)

def save(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,sort_keys=True,indent=2)+"\n")

def affinity():
    if hasattr(os,"sched_setaffinity"):
        allowed=os.sched_getaffinity(0)
        os.sched_setaffinity(0,{min(allowed)})
        assert len(os.sched_getaffinity(0))==1

def execute(argv,remaining):
    if remaining<=0:
        return {"returncode":124,"expired":True,"stdout":"","stderr":"","wall_s":0}
    return frozen.execute([str(x) for x in argv],max(.001,remaining))

def proof_preflight():
    # A satisfiable exact-one input and mutated source must be rejected.
    control=math5_smoke.negative_tests()
    # One original-source-supported EO parity contradiction MUST be
    # independently accepted by external VeriPB before any real trials.
    groups=[[1,2,3,4],[1,2,5,6],[3,4,5,6]]
    clauses=[tuple(g) for g in groups]
    import itertools
    for g in groups:
        clauses += [(-a,-b) for a,b in itertools.combinations(g,2)]
    raw=("p cnf 6 "+str(len(clauses))+"\n"+
         "".join(" ".join(map(str,c))+" 0\n" for c in clauses)).encode()
    certificate={"format":"drnas-math5-eo-xor-unit-v1",
        "source_sha256":hashlib.sha256(raw).hexdigest(),
        "exact_one_groups":groups,"xor_rows":[],"root_units":[]}
    with tempfile.TemporaryDirectory(prefix="math5-preflight-") as d:
        root=Path(d);src=root/"original.cnf";cert=root/"proof.json";pb=root/"proof.pbp"
        src.write_bytes(raw);save(cert,certificate)
        run=execute([sys.executable,EMITTER,"--cnf",src,"--certificate",cert,
                     "--output",pb],5.0)
        if run["expired"] or run["returncode"]!=0 or not pb.exists():
            raise RuntimeError("source-grounded EO standard emitter failed "+run["stderr"][-300:])
        check=execute([VERIPB,"--cnf",src,pb],5.0)
        if (check["expired"] or check["returncode"]!=0 or
                "s VERIFIED UNSATISFIABLE" not in check["stdout"]+check["stderr"]):
            raise RuntimeError("external VeriPB rejected MATH5 parity preflight")
    return {"source_and_sat_tamper_controls":control,
            "six_variable_parity_VERIPB":True}

def freeze():
    affinity()
    source_manifest=frozen.frozen_sources()
    assert source_manifest["selected"]==67, "did not restore 67 historical frozen originals"
    for idx,expected in SOURCE_IDS_EXPECTED.items():
        source=source_manifest["sources"][idx]
        assert source["id"]==idx and source["sha256"]==expected
    binaries=frozen.pinned()
    result={"protocol":"DRNAS-MATH5-VERIPB-REAL67-RETROSPECTIVE-V1",
        "branch_code_sha":os.environ.get("GITHUB_SHA"),
        "source_manifest_sha256":sha(frozen.DATA/"manifest.json"),
        "frozen_prior_protocol_sha256":sha(frozen.OUT/"protocol.json"),
        "source_count":source_manifest["selected"],"repetitions":REPS,"shards":SHARDS,
        "arms":list(ARMS),"cap_s":CAP,
        "max_proof_bytes":frozen.P["proof_limit_bytes"],
        "one_logical_cpu_per_trial":True,"no_portfolio":True,
        "retrospective_not_new_blind":True,"no_main_promotion":True,
        "m5_proof_compile_sha256":sha(EMITTER),
        "benchmark_code_sha256":sha(HERE/"benchmark.py"),
        "frozen_binary_sha256":binaries,
        "standard_kind_whitelist":sorted(STRICT_KINDS),
        "positive_negative_selftest":proof_preflight()}
    save(OUT/"protocol.json",result)
    print("MATH5_67_READY "+json.dumps(
        {"N":result["source_count"],"arms":len(ARMS),
         "expected_trials":result["source_count"]*REPS*len(ARMS),
         "source_manifest_sha256":result["source_manifest_sha256"],
         "standard_preflight":True},sort_keys=True),flush=True)

def restore():
    affinity()
    sources,old_proto=frozen.restore()
    prespec=json.loads((OUT/"protocol.json").read_text())
    assert prespec["source_count"]==len(sources)==67
    assert prespec["arms"]==list(ARMS) and prespec["cap_s"]==CAP
    assert prespec["source_manifest_sha256"]==sha(frozen.DATA/"manifest.json")
    assert prespec["frozen_prior_protocol_sha256"]==sha(frozen.OUT/"protocol.json")
    assert prespec["m5_proof_compile_sha256"]==sha(EMITTER)
    assert prespec["benchmark_code_sha256"]==sha(HERE/"benchmark.py")
    assert prespec["frozen_binary_sha256"]==frozen.pinned()
    assert prespec["branch_code_sha"]==os.environ.get("GITHUB_SHA")
    assert VERIPB.is_file() and EMITTER.is_file()
    return sources,prespec

def standard_trial(source,rep):
    # Same frozen native X59+MATH5 binary/args as existing X59_MATH5 arm.
    # Difference is ONLY the external proof export/verification chain.
    started=time.perf_counter()
    cnf=ROOT/source["path"]
    assert sha(cnf)==source["sha256"],"ORIGINAL_CNF_CHANGED"
    with tempfile.TemporaryDirectory(prefix="drnas-math5-standard67-") as d:
        work=Path(d);drat=work/"fallback.drat";cert=work/"math5.json"
        pb=work/"math5.pbp";meta=work/"math5_meta.json"
        kind=None;status="UNKNOWN";reason=None
        accepted=False;strict=False;critical=False
        solver_s=0;project_checker_s=0;emitter_s=0;veripb_s=0;drat_s=0
        proof_sha=None;proof_size=0;rc=None
        remaining=CAP-(time.perf_counter()-started)
        if remaining>0:
            cmd=frozen.command("X59_MATH5",cnf,drat,cert,work,remaining)
            solved=execute(cmd,remaining)
            rc=solved["returncode"];solver_s=solved["wall_s"]
            status="TIMEOUT" if solved["expired"] else "UNKNOWN"
        else:
            solved={"returncode":124,"expired":True,"stdout":"","stderr":""}
            status="NO_SOLVE_BUDGET"
        if not solved["expired"] and rc in (10,20):
            declared="s SATISFIABLE" if rc==10 else "s UNSATISFIABLE"
            if declared not in solved["stdout"].splitlines():
                status="INVALID_STATUS";critical=True;reason="no native status line"
            elif CAP-(time.perf_counter()-started)<=0:
                status="NO_CHECK_BUDGET"
            elif rc==10:
                kind="MODEL"
                if cert.exists():
                    status="INVALID_SAT_WITH_CERT";critical=True
                elif frozen.model_ok(cnf,solved["stdout"]):
                    accepted=True;strict=True;status="SAT_VERIFIED"
                else:
                    status="INVALID_SAT_MODEL";critical=True
            elif cert.is_file():
                kind="STRUCTURAL_MATH5"
                if drat.exists() and drat.stat().st_size:
                    status="INVALID_MIXED_DRAT_MATH5";critical=True
                else:
                    remaining=CAP-(time.perf_counter()-started)
                    if remaining<=0:status="NO_CHECK_BUDGET"
                    else:
                        chk=execute([sys.executable,frozen.CHECKER,cnf,cert],remaining)
                        project_checker_s+=chk["wall_s"]
                        if chk["expired"]:
                            status="SOURCE_CHECK_TIMEOUT"
                        elif chk["returncode"]!=0 or "UNSAT_MATH5_CERTIFICATE_VERIFIED" not in chk["stdout"]:
                            status="INVALID_MATH5_SOURCE_PROOF";critical=True
                            reason=(chk["stdout"]+chk["stderr"])[-350:]
                        else:
                            accepted=True
                            status="UNSAT_VERIFIED";proof_sha=sha(cert)
                            proof_size=cert.stat().st_size
                            remaining=CAP-(time.perf_counter()-started)
                            if remaining>0:
                                emitted=execute([sys.executable,EMITTER,
                                    "--cnf",cnf,"--certificate",cert,
                                    "--output",pb,"--meta",meta],remaining)
                                emitter_s+=emitted["wall_s"]
                                if emitted["expired"]:
                                    reason="standard emitter timed out; source proof remains checked"
                                elif emitted["returncode"]==2 and not pb.exists():
                                    reason="restricted VeriPB compiler unsupported for this source"
                                elif emitted["returncode"]!=0 or not pb.is_file():
                                    status="INVALID_EMITTER";critical=True
                                    reason=(emitted["stdout"]+emitted["stderr"])[-350:]
                                    accepted=False
                                else:
                                    remaining=CAP-(time.perf_counter()-started)
                                    if remaining>0:
                                        checked=execute([VERIPB,"--cnf",cnf,pb],remaining)
                                        veripb_s+=checked["wall_s"]
                                        if checked["expired"]:
                                            reason="VeriPB external checker reached 8s cap"
                                        elif checked["returncode"]==0 and (
                                            "s VERIFIED UNSATISFIABLE" in checked["stdout"]+checked["stderr"]):
                                            strict=True;kind="VERIPB_MATH5"
                                            proof_sha=sha(pb);proof_size=pb.stat().st_size
                                        else:
                                            status="INVALID_EXTERNAL_VERIPB";critical=True
                                            accepted=False
                                            reason=(checked["stdout"]+checked["stderr"])[-350:]
                            else:reason="no VeriPB export budget after project source checker"
            elif drat.is_file() and drat.stat().st_size:
                kind="DRAT"
                remaining=CAP-(time.perf_counter()-started)
                if remaining>0:
                    chk=execute([ROOT/"build/drat-trim",cnf,drat],remaining)
                    drat_s=chk["wall_s"]
                    if chk["expired"]:status="DRAT_CHECK_TIMEOUT"
                    elif chk["returncode"]==0 and "VERIFIED" in chk["stdout"]+chk["stderr"]:
                        accepted=True;strict=True;status="UNSAT_VERIFIED"
                        proof_sha=sha(drat);proof_size=drat.stat().st_size
                    else:
                        status="INVALID_DRAT";critical=True
                else:status="NO_CHECK_BUDGET"
            else:
                status="UNSAT_UNVERIFIED"
        elif not solved["expired"] and rc not in (0,153,None):
            status="RESOURCE_LIMIT" if rc in (137,-9,-25) else "SOLVER_ERROR"
            critical=status=="SOLVER_ERROR"
            reason=solved["stderr"][-400:]
        elapsed=time.perf_counter()-started
        if elapsed>CAP:
            accepted=False;strict=False
            if not critical:status="E2E_OVER_CAP"
        accepted=bool(accepted and not critical and elapsed<=CAP)
        strict=bool(accepted and strict and kind in STRICT_KINDS)
        return {"id":source["id"],"file_id":source["file_id"],
            "source_sha256":source["sha256"],"family":source["family"],
            "catalog_label":source["catalog_label"],"arm":"X59_MATH5_VERIPB",
            "rep":rep,"rc":rc,"status":status,
            "accepted":accepted,"strict_accepted":strict,
            "certificate_kind":kind,"critical":critical,"reason":reason,
            "solver_s":round(solver_s,6),
            "project_checker_s":round(project_checker_s,6),
            "emitter_s":round(emitter_s,6),
            "veripb_s":round(veripb_s,6),"drat_checker_s":round(drat_s,6),
            "checker_s":round(project_checker_s+emitter_s+veripb_s+drat_s,6),
            "e2e_s":round(elapsed,6),
            "PAR2_s":round(elapsed if accepted else 2*CAP,6),
            "PAR2_strict_s":round(elapsed if strict else 2*CAP,6),
            "proof_sha256":proof_sha,"proof_bytes":proof_size,
            "stats":{}}

def trial(source,arm,rep):
    return (standard_trial(source,rep) if arm=="X59_MATH5_VERIPB"
            else frozen.trial(source,arm,rep))

def shard(index):
    assert 0<=index<SHARDS
    sources,_=restore()
    subset=[s for s in sources if s["id"]%SHARDS==index]
    assert subset
    folder=OUT/f"shard-{index}"
    folder.mkdir(parents=True,exist_ok=False)
    rows=[]
    for source in subset:
        for rep in range(REPS):
            order=list(ARMS)
            rng=random.Random(f"{frozen.P['selection_seed']}:standard-pbp:{source['id']}:{rep}")
            rng.shuffle(order)
            present={}
            for arm in order:
                row=trial(source,arm,rep)
                rows.append(row)
                with (folder/"trials.jsonl").open("a") as fd:
                    fd.write(json.dumps(row,sort_keys=True)+"\n")
                    fd.flush()
                present[arm]={"accepted":row["accepted"],
                              "strict":row["strict_accepted"],
                              "status":row["status"],
                              "PAR2_strict_s":row["PAR2_strict_s"]}
            # Progress is deliberately compact; all trials are immutable in JSONL.
            print("MATH5_67_SOURCE "+json.dumps(
                {"source_id":source["id"],"rep":rep,"arms":present},sort_keys=True),flush=True)
    assert len(rows)==len(subset)*REPS*len(ARMS)
    summary={arm:{"strict":sum(r["strict_accepted"] for r in rows if r["arm"]==arm),
                  "source":sum(r["accepted"] for r in rows if r["arm"]==arm),
                  "strict_PAR2_s":round(sum(r["PAR2_strict_s"] for r in rows if r["arm"]==arm),6)}
             for arm in ARMS}
    print("MATH5_67_SHARD "+json.dumps(
        {"shard":index,"source_count":len(subset),"trials":len(rows),
         "summary":summary},sort_keys=True),flush=True)

def bootstraps(byid,best,kind):
    rng=random.Random(20261116 if kind=="strict" else 20261117)
    families=collections.defaultdict(list)
    for src in byid["sources"]:
        families[src["family"]].append(src["id"])
    out={}
    values=byid["values"][kind]
    for arm in ARMS:
        if arm in REFS:continue
        changes={i:values[i][best]-values[i][arm] for i in values}
        group_sums=[sum(changes[i] for i in ids) for ids in families.values()]
        sample_count=4000
        samples=sorted(sum(group_sums[rng.randrange(len(group_sums))]
                     for _ in range(len(group_sums))) for _ in range(sample_count))
        out[arm]={"reference":best,"families":len(group_sums),
             "delta_sum_per_source_mean_s":round(sum(changes.values()),6),
             "family_cluster_95_s":[round(samples[int(.025*sample_count)],6),
                                     round(samples[int(.975*sample_count)],6)],
             "wins":sum(v>0.0001 for v in changes.values()),
             "losses":sum(v< -0.0001 for v in changes.values()),
             "ties":sum(abs(v)<=0.0001 for v in changes.values())}
    return out

def aggregate():
    sources,_=restore()
    all_rows=[]
    for shard_id in range(SHARDS):
        path=OUT/f"shard-{shard_id}"/"trials.jsonl"
        if not path.exists():raise RuntimeError("MISSING_SHARD "+str(shard_id))
        all_rows.extend(json.loads(x) for x in path.read_text().splitlines())
    n=len(sources)
    expected={(id,rep,arm) for id in range(n) for rep in range(REPS) for arm in ARMS}
    observed={(r["id"],r["rep"],r["arm"]) for r in all_rows}
    if not (len(all_rows)==len(expected)==len(observed) and observed==expected):
        raise RuntimeError("INCOMPLETE_OR_DUPLICATE_FROZEN_MATRIX")
    source_map={src["id"]:src for src in sources}
    issues=[]
    for r in all_rows:
        src=source_map[r["id"]]
        if r["source_sha256"]!=src["sha256"] or r["family"]!=src["family"]:
            issues.append({"id":r["id"],"problem":"source_identity_mismatch"})
        if r["critical"]:issues.append({"id":r["id"],"arm":r["arm"],
                                        "status":r["status"],"reason":r.get("reason")})
        if r["strict_accepted"] and (not r["accepted"] or r["certificate_kind"] not in STRICT_KINDS):
            issues.append({"id":r["id"],"arm":r["arm"],"problem":"invalid_standard_scoring"})
    for id in range(n):
        good=[r for r in all_rows if r["id"]==id and r["accepted"]]
        if (any(r["status"]=="SAT_VERIFIED" for r in good) and
            any(r["status"]=="UNSAT_VERIFIED" for r in good)):
            issues.append({"id":id,"problem":"contradictory_original_source_certifications"})
    total={}
    by_type={}
    for arm in ARMS:
        rr=[r for r in all_rows if r["arm"]==arm]
        total[arm]={"attempts":len(rr),
            "verified":sum(r["accepted"] for r in rr),
            "strict_verified":sum(r["strict_accepted"] for r in rr),
            "verified_sat":sum(r["status"]=="SAT_VERIFIED" and r["accepted"] for r in rr),
            "verified_unsat":sum(r["status"]=="UNSAT_VERIFIED" and r["accepted"] for r in rr),
            "veripb_math5":sum(r["certificate_kind"]=="VERIPB_MATH5"
                              and r["strict_accepted"] for r in rr),
            "source_PAR2_s":round(sum(r["PAR2_s"] for r in rr),6),
            "strict_PAR2_s":round(sum(r["PAR2_strict_s"] for r in rr),6),
            "statuses":dict(collections.Counter(r["status"] for r in rr)),
            "certificate_kinds":dict(collections.Counter(
                r["certificate_kind"] for r in rr if r["accepted"]))}
    best_strict=min(REFS,key=lambda arm:total[arm]["strict_PAR2_s"])
    best_source=min(REFS,key=lambda arm:total[arm]["source_PAR2_s"])
    per_id={"sources":sources,"values":{}}
    for track,column in (("strict","PAR2_strict_s"),("source","PAR2_s")):
        per_id["values"][track]={id:{arm:statistics.mean(
            r[column] for r in all_rows if r["id"]==id and r["arm"]==arm)
            for arm in ARMS} for id in range(n)}
    result={"status":"FAIL" if issues else "COMPLETE",
        "retrospective_not_blind":True,"no_auto_promotion":True,
        "source_count":n,"repetitions":REPS,
        "total_attempts":len(all_rows),"cap_s":CAP,
        "reference_best_strict":best_strict,"reference_best_source":best_source,
        "totals":total,"critical":issues,
        "paired_family_strict":bootstraps(per_id,best_strict,"strict"),
        "paired_family_source":bootstraps(per_id,best_source,"source"),
        "standard_veripb_originals":sorted({r["id"] for r in all_rows
             if r["arm"]=="X59_MATH5_VERIPB" and
                r["certificate_kind"]=="VERIPB_MATH5" and r["strict_accepted"]}),
        "proof_sha256":sha(EMITTER),
        "note":"Same 67 retrospective SAT2026 originals, frozen binaries, 8 s end-to-end, 1 logical CPU/trial. New MATH5 path uses external standard VeriPB. Custom structural proof acceptance remains a separate score. Not prospective blind generalization."}
    save(OUT/"final.json",result)
    compact={"status":result["status"],"N":n,"trials":len(all_rows),
             "best_strict_reference":best_strict,"totals":total,
             "standard_veripb_originals":result["standard_veripb_originals"],
             "paired_family_strict":result["paired_family_strict"],
             "critical_count":len(issues)}
    print("MATH5_67_FINAL "+json.dumps(compact,sort_keys=True),flush=True)
    if issues:raise SystemExit(1)

if __name__=="__main__":
    args=argparse.ArgumentParser()
    args.add_argument("action",choices=("prepare","shard","report"))
    args.add_argument("--index",type=int)
    a=args.parse_args()
    if a.action=="prepare":freeze()
    elif a.action=="shard":shard(a.index)
    else:aggregate()
