"""MI-LTM3.1 delayed intervention experiment on SHA-disjoint harder SAT CNFs.

This is a *restart-based* prototype, not an in-process CDCL callback.
A bounded native preflight solves the original CNF first. Only an UNKNOWN
preflight may trigger fresh source-certified XOR inference, followed by a
fresh CDCL solve. Thus no CDCL trail/learned clauses are carried forward.
All arms use identical preflight time and one logical CPU.
"""
import hashlib
import json
import random
import statistics
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"mi_ltm1"))
from native_paired import BIN,parse_model,implied_cnf
from probe import probe_cnf
from design import dimacs,satisfies,opportunity_key
from experiment import independently_audit_inferences
from strict_runner import run_strict
from xor_multistep import closure,audit_provenance

OUT=ROOT/"mi_ltm31"
CAP=2.0
PREFLIGHT=.025
MAX_PROBE=.012
REPS=2
FAMILIES=("hard_planted_3sat","hard_planted_xor_mix")
PER_FAMILY=48
TRAIN_PER_FAMILY=24
ARMS=("STAGED_CONTROL","DELAYED_XOR","DELAYED_CHAIN")


def make_case(family,index,training_generation):
    split="train" if index<TRAIN_PER_FAMILY else "holdout"
    generation=training_generation if split=="train" else 0
    seed=int.from_bytes(hashlib.sha256(
        ("LTM31-v1/%s/%d/%d"%(family,index,generation)).encode()
    ).digest()[:8],"big")
    rng=random.Random(seed)
    n=(128,160,192)[index%3]
    model={i:bool(rng.getrandbits(1)) for i in range(1,n+1)}
    clauses=[]
    def planted_clause():
        vs=rng.sample(range(1,n+1),3)
        clause=[v if rng.getrandbits(1) else -v for v in vs]
        if not any(model[abs(v)]==(v>0) for v in clause):
            j=rng.randrange(3)
            clause[j]=vs[j] if model[vs[j]] else -vs[j]
        return tuple(clause)
    def xor3(vs):
        rhs=sum(model[v] for v in vs)%2
        return [tuple(-v if mask&(1<<j) else v
                      for j,v in enumerate(vs))
                for mask in range(8) if mask.bit_count()%2!=rhs]
    if family=="hard_planted_xor_mix":
        for _ in range(n//2):
            clauses.extend(xor3(rng.sample(range(1,n+1),3)))
        count=int(3.45*n)
    else:
        count=int(4.26*n)
    for _ in range(count):
        clauses.append(planted_clause())
    assert satisfies(clauses,model)
    raw=dimacs(n,clauses)
    return dict(family=family,index=index,split=split,
                n=n,clauses=clauses,model=model,raw=raw,
                sha=hashlib.sha256(raw.encode()).hexdigest())


def cohort(generation):
    cases=[make_case(f,i,generation)
           for f in FAMILIES for i in range(PER_FAMILY)]
    assert len({x["sha"] for x in cases})==len(cases)
    return cases


def verify_result(case,rc,stdout):
    if rc==10:
        model=parse_model(stdout)
        if len(model)!=case["n"] or not satisfies(case["clauses"],model):
            raise AssertionError("Invalid SAT model on original source CNF")
        return "SAT_ORIGINAL_VERIFIED"
    if rc==20:
        raise AssertionError("Native UNSAT contradicts planted SAT witness")
    return "UNKNOWN"


def intervention(case,kind):
    """Derive only after preflight UNKNOWN, with full original-CNF proof audit."""
    t0=time.perf_counter()
    report=probe_cnf(case["raw"],max_clauses=10000,
                     max_rows=96,max_width=3)
    extra=[]
    chain_ops=0
    if report["status"]=="diagnostic_only":
        independently_audit_inferences(case["clauses"],report)
        candidates=list(report["consequences"])
        if kind=="DELAYED_CHAIN" and report["xor_equations"]:
            more=closure(report["xor_equations"],max_rows=96,
                         max_steps=6000,budget_s=.005)
            chain_ops=more["elimination_ops"]
            seen={(tuple(x["variables"]),x["rhs"]) for x in candidates}
            for item in more["consequences"]:
                if not audit_provenance(report["xor_equations"],item):
                    raise AssertionError("Bad multistep XOR provenance")
                key=(tuple(item["variables"]),item["rhs"])
                if key not in seen:
                    seen.add(key)
                    candidates.append(item)
        independently_audit_inferences(
            case["clauses"],dict(report,consequences=candidates))
        existing={frozenset(c) for c in case["clauses"]}
        for con in sorted(candidates,key=lambda c:len(c["variables"])):
            for cl in implied_cnf(con):
                key=frozenset(cl)
                if key in existing:
                    continue
                extra.append(tuple(cl))
                existing.add(key)
                if len(extra)>=48:
                    break
            if len(extra)>=48:
                break
    elapsed=time.perf_counter()-t0
    if elapsed>MAX_PROBE or report["status"]!="diagnostic_only":
        return [],elapsed,chain_ops,"probe_abstained"
    return extra,elapsed,chain_ops,"derived" if extra else "no_new_clauses"


def run_case(case,rep,arm,tmp):
    start=time.perf_counter()
    seed=int.from_bytes(hashlib.sha256(
        ("%s/%d"%(case["sha"],rep)).encode()).digest()[:8],"big")
    original=tmp/("original_%s.cnf"%case["sha"][:20])
    original.write_text(case["raw"])
    # All arms pay exactly the same preflight budget; no hindsight on holdout.
    rc,stdout,first_s,first_reason=run_strict(
        BIN,original,seed,min(PREFLIGHT,CAP-(time.perf_counter()-start)))
    first_status=verify_result(case,rc,stdout)
    activated=False
    extra=[]
    probe_s=0.0
    chain_ops=0
    decision="preflight_solved" if first_status!="UNKNOWN" else "preflight_unknown"
    if first_status=="UNKNOWN" and arm!="STAGED_CONTROL":
        activated=True
        extra,probe_s,chain_ops,decision=intervention(case,arm)
    status=first_status
    second_s=0.0
    second_reason="not_needed"
    if status=="UNKNOWN":
        remaining=CAP-(time.perf_counter()-start)
        if remaining>.01:
            candidate=tmp/("candidate_%s_%d_%s.cnf"%
                           (case["sha"][:16],rep,arm))
            candidate.write_text(dimacs(case["n"],case["clauses"]+extra))
            # Same original SHA-derived seed; restart, NOT CDCL resume.
            rc2,stdout2,second_s,second_reason=run_strict(
                BIN,candidate,seed,remaining)
            status=verify_result(case,rc2,stdout2)
    elapsed=time.perf_counter()-start
    if elapsed>CAP:
        status="UNKNOWN"
        decision="E2E_budget_exhausted"
    solved=status=="SAT_ORIGINAL_VERIFIED"
    return dict(family=case["family"],index=case["index"],split=case["split"],
                sha256=case["sha"],rep=rep,arm=arm,solved=solved,
                status=status,verified=solved,
                preflight_status=first_status,
                preflight_s=round(first_s,7),
                preflight_reason=first_reason,
                restart_s=round(second_s,7),
                restart_reason=second_reason,
                triggered=activated,decision=decision,
                added_clauses=len(extra),chain_ops=chain_ops,
                probe_s=round(probe_s,7),
                E2E_s=round(elapsed,7),
                PAR2_s=round(elapsed if solved else 2*CAP,7),
                one_logical_cpu=True,
                independent_LRAT=False,
                original_CNF_witness_verified=solved)


def summary(rows):
    result={}
    for arm in ARMS:
        items=[x for x in rows if x["arm"]==arm]
        if not items:
            continue
        result[arm]=dict(trials=len(items),
                         solved=sum(x["solved"] for x in items),
                         UNKNOWN=sum(not x["solved"] for x in items),
                         PAR2_s=round(sum(x["PAR2_s"] for x in items),6),
                         E2E_s=round(sum(x["E2E_s"] for x in items),6),
                         median_ms=round(statistics.median(
                             x["E2E_s"] for x in items)*1000,4),
                         preflight_solved=sum(
                             x["preflight_status"]!="UNKNOWN" for x in items),
                         activated=sum(x["triggered"] for x in items),
                         added_clauses=sum(x["added_clauses"] for x in items),
                         probe_s=round(sum(x["probe_s"] for x in items),6),
                         chain_ops=sum(x["chain_ops"] for x in items))
    return result


def paired(rows,a,b):
    index={(x["sha256"],x["rep"],x["arm"]):x for x in rows}
    keys={(x["sha256"],x["rep"]) for x in rows if x["arm"]==a}
    diffs=[index[sha,rep,a]["PAR2_s"]-index[sha,rep,b]["PAR2_s"]
           for sha,rep in keys]
    return dict(pairs=len(diffs),
                b_faster=sum(d>0 for d in diffs),
                a_faster=sum(d<0 for d in diffs),
                ties=sum(d==0 for d in diffs),
                median_saving_s=round(statistics.median(diffs),7))


def run(*, generation, smoke=False):
    if not BIN.exists():
        raise FileNotFoundError(BIN)
    cases=cohort(generation)
    if smoke:
        cases=[next(x for x in cases if x["family"]==family and
                    x["split"]==split)
               for family in FAMILIES for split in ("train","holdout")]
    rows=[]
    with TemporaryDirectory() as td:
        tmp=Path(td)
        for count,case in enumerate(cases,1):
            for rep in range(REPS):
                arms=ARMS if rep%2==0 else tuple(reversed(ARMS))
                for arm in arms:
                    rows.append(run_case(case,rep,arm,tmp))
            if count%12==0 or count==len(cases):
                print("MI_LTM31_PROGRESS",count,len(cases),flush=True)
    train=[x for x in rows if x["split"]=="train"]
    holdout=[x for x in rows if x["split"]=="holdout"]
    report=dict(project="MI-LTM3.1 delayed restart diagnostic",
                training_generation=generation,
                train_source_count=sum(x["split"]=="train" for x in cases),
                holdout_source_count=sum(x["split"]=="holdout" for x in cases),
                repeats=REPS,cap_s=CAP,preflight_cap_s=PREFLIGHT,
                source_SHA_disjoint=True,
                one_logical_cpu=True,
                no_training_on_holdout=True,
                training_policy="pre-registered fixed UNKNOWN trigger; no fitted policy",
                warning=("Restart-based diagnostic, NOT live CDCL trail trigger. "
                         "Planted SAT only; UNSAT comparisons not measured. "
                         "Source-XOR proof audit, but no LRAT. "
                         "Repeat holdout runs are not fresh blind tests."),
                summary=dict(train=summary(train),holdout=summary(holdout)),
                paired_holdout={
                    arm:paired(holdout,"STAGED_CONTROL",arm)
                    for arm in ("DELAYED_XOR","DELAYED_CHAIN")},
                by_family={f:summary([x for x in holdout if x["family"]==f])
                           for f in FAMILIES},
                trials=rows)
    OUT.mkdir(exist_ok=True)
    filename=ROOT/("MI_LTM31_SMOKE.json" if smoke else "MI_LTM31_FINAL.json")
    filename.write_text(json.dumps(report,indent=2,sort_keys=True))
    print("MI_LTM31_FINAL",json.dumps({
        "smoke":smoke,
        "summary":report["summary"],
        "paired_holdout":report["paired_holdout"],
        "by_family":report["by_family"],
        "warning":report["warning"]},sort_keys=True),flush=True)


if __name__=="__main__":
    import argparse,os
    parser=argparse.ArgumentParser()
    parser.add_argument("--smoke",action="store_true")
    parser.add_argument("--generation",type=int,
                        default=int(os.environ.get("GITHUB_RUN_NUMBER","1")))
    args=parser.parse_args()
    run(generation=args.generation,smoke=args.smoke)
