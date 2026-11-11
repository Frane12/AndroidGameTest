"""MI-LTM2: frozen train/holdout diagnosis of persistent structural memory.

320 independent deterministic original CNF files, 8 families x 40:
192 train, 128 SHA-disjoint holdout; 2 paired seeds per formula.
Train compares native BASE / MI_XOR. Holdout compares BASE / MI_XOR /
LTM_GATE with a read-only policy learned ONLY from training formulas.

No learned clause is imported from a different formula: only advisory
renaming-invariant coarse structural signatures and intervention choices.
UNSAT claims are checked independently by exhaustive enumeration (12 vars);
SAT models are verified against the ORIGINAL CNF.
"""
import hashlib
import json
import random
import statistics
import time
from collections import Counter, defaultdict
from pathlib import Path

from bench_formulas import dimacs, oracle, satisfies, xor_cnf
from memory import Memory, signature
from native_paired import BIN, implied_cnf, parse_model, solve
from probe import probe_cnf

N = 12
PER_FAMILY = 40
TRAIN_PER_FAMILY = 24
REPS = 2
CAP = 2.0
FAMILIES = ("xor_overlap", "xor_chain", "xor_contradiction",
            "xor_cycle_unsat", "xor_incomplete", "random_3sat",
            "mixed_xor", "xor_single")
ROOT = Path("mi_ltm1")
DB = ROOT / "history.sqlite"
REPORT = Path("MI_LTM2_TRAIN_HOLDOUT.json")


def planted_noise(rng, assignment, count, k=3):
    clauses = []
    for _ in range(count):
        vs = rng.sample(range(1, N + 1), k)
        clause = [v if rng.randrange(2) else -v for v in vs]
        if not any(assignment[abs(v)] == (v > 0) for v in clause):
            j = rng.randrange(k)
            v = vs[j]
            clause[j] = v if assignment[v] else -v
        clauses.append(tuple(clause))
    return clauses


def make_case(family, i):
    rng = random.Random(2026111100 + FAMILIES.index(family) * 100003 + i * 997)
    a, b, c, d, e, f = rng.sample(range(1, N + 1), 6)
    p, q, r = (rng.randrange(2) for _ in range(3))
    assignment = {v: bool(rng.randrange(2)) for v in range(1, N + 1)}
    if family == "xor_overlap":
        clauses = xor_cnf([a, b, c], p) + xor_cnf([b, c, d], q)
    elif family == "xor_chain":
        clauses = (xor_cnf([a, b], p) + xor_cnf([b, c], q)
                   + xor_cnf([c, d], r))
    elif family == "xor_contradiction":
        clauses = xor_cnf([a, b, c], p) + xor_cnf([a, b, c], 1-p)
    elif family == "xor_cycle_unsat":
        clauses = (xor_cnf([a, b], p) + xor_cnf([b, c], q)
                   + xor_cnf([a, c], 1-(p^q)))
    elif family == "xor_incomplete":
        clauses = xor_cnf([a, b, c], p)
        del clauses[rng.randrange(len(clauses))]
    elif family == "random_3sat":
        clauses = []
        for _ in range(22):
            vs = rng.sample(range(1, N + 1), 3)
            clauses.append(tuple(v if rng.randrange(2) else -v for v in vs))
    elif family == "mixed_xor":
        p = sum(assignment[v] for v in (a,b,c)) % 2
        q = sum(assignment[v] for v in (b,c,d)) % 2
        clauses = (xor_cnf([a,b,c],p)+xor_cnf([b,c,d],q)
                   + planted_noise(rng,assignment,14))
    elif family == "xor_single":
        clauses = xor_cnf([a,b,c],p)+planted_noise(
            rng,{**assignment, a: bool(p^int(assignment[b])^int(assignment[c]))},9)
    else:
        raise ValueError(family)
    return clauses


def catalog():
    rows = []
    seen = set()
    for family in FAMILIES:
        for i in range(PER_FAMILY):
            clauses = make_case(family, i)
            raw = dimacs(clauses, N)
            sha = hashlib.sha256(raw.encode()).hexdigest()
            if sha in seen:
                raise AssertionError("Repeated original CNF SHA")
            seen.add(sha)
            split = "train" if i < TRAIN_PER_FAMILY else "holdout"
            rows.append(dict(family=family,case=i,split=split,
                             clauses=clauses,raw=raw,sha=sha,
                             signature=signature(clauses)))
    assert len(rows)==320 and sum(x["split"]=="train" for x in rows)==192
    assert len({x["sha"] for x in rows})==320
    return rows


def run_arm(case, arm, rep, models, tmpdir, allowed):
    assert arm in ("BASE","MI_XOR","LTM_GATE")
    start = time.perf_counter()
    # Charge structural fingerprint computation to LTM_GATE per-case E2E.
    sig = signature(case["clauses"]) if arm=="LTM_GATE" else case["signature"]
    memory_match = allowed is not None and sig in allowed["seen"]
    action = "BASE"
    if arm=="MI_XOR":
        action = "MI_XOR"
    elif arm=="LTM_GATE" and memory_match and sig in allowed["positive"]:
        action = "MI_XOR"
    added = []
    probe_s = 0.0
    if action=="MI_XOR":
        probestart = time.perf_counter()
        report = probe_cnf(case["raw"])
        probe_s = time.perf_counter()-probestart
        for con in report["consequences"]:
            assert all((sum(int(model[v]) for v in con["variables"]) & 1)==con["rhs"]
                       for model in models), ("Invalid inferred XOR",case["sha"],con)
            added.extend(implied_cnf(con))
        added = list(dict.fromkeys(c for c in added if c not in set(case["clauses"])))
    filename=tmpdir / ("current_%s_%d.cnf"%(arm,rep))
    filename.write_text(dimacs(case["clauses"]+added,N))
    seed = int.from_bytes(hashlib.sha256(
        (case["sha"]+"/"+str(rep)).encode()).digest()[:8],"big")
    rc,output,child_s=solve(filename,seed,CAP)
    e2e = time.perf_counter()-start
    expected = 10 if models else 20
    if rc not in (0,expected):
        raise AssertionError(("Native mismatch",case["sha"],arm,rc,expected))
    if rc==10:
        model=parse_model(output)
        assert len(model)==N and satisfies(case["clauses"],model),(
            "Invalid original CNF SAT witness",case["sha"])
    solved = rc==expected
    return dict(family=case["family"],case=case["case"],sha256=case["sha"],
                split=case["split"],rep=rep,arm=arm,action=action,
                signature=sig,memory_match=bool(memory_match),
                solved=solved,status=("SAT_CHECKED" if rc==10 else
                "UNSAT_EXHAUSTIVE" if rc==20 else "UNKNOWN"),
                e2e_s=round(e2e,7),
                par2_s=round(e2e if solved else 2*CAP,7),
                probe_s=round(probe_s,7),added_clauses=len(added),
                independent_lrat=False,one_cpu=True)


def summarize(rows):
    summary={}
    for arm in sorted(set(x["arm"] for x in rows)):
        grp=[x for x in rows if x["arm"]==arm]
        summary[arm]=dict(trials=len(grp),solved=sum(x["solved"] for x in grp),
                          PAR2_s=round(sum(x["par2_s"] for x in grp),6),
                          E2E_s=round(sum(x["e2e_s"] for x in grp),6),
                          median_ms=round(statistics.median(x["e2e_s"] for x in grp)*1000,4),
                          matched=sum(x["memory_match"] for x in grp),
                          activated=sum(x["action"]=="MI_XOR" for x in grp),
                          new_clauses=sum(x["added_clauses"] for x in grp))
    return summary


def learn(db, train):
    # Only genuine verified paired train results can enter the persistent DB.
    lookup={(x["sha256"],x["rep"],x["arm"]):x for x in train}
    for item in train:
        if item["arm"]!="MI_XOR":
            continue
        base=lookup[(item["sha256"],item["rep"],"BASE")]
        db.record(cohort="training_rep_%d"%item["rep"],
                  formula_sha=item["sha256"],signature=item["signature"],
                  arm="MI_XOR",baseline_e2e=base["e2e_s"],
                  candidate_e2e=item["e2e_s"],
                  baseline_solved=base["solved"],candidate_solved=item["solved"],
                  cap_s=CAP,verified=True,probe_s=item["probe_s"])


def freeze_policy(db, train_cases):
    # An exact-SHA holdout filter is defense-in-depth, in addition to split.
    train_shas={x["sha"] for x in train_cases}
    seen={}
    positive={}
    for sig in sorted({x["signature"] for x in train_cases}):
        records=db.db.execute(
            "SELECT formula_sha,baseline_e2e,candidate_e2e,baseline_solved,"
            "candidate_solved,cap_s FROM observations "
            "WHERE signature=? AND verified=1 AND arm='MI_XOR'",(sig,)).fetchall()
        vals=defaultdict(list)
        for sha,bt,ct,bs,cs,cap in records:
            if sha in train_shas:
                vals[sha].append((bt if bs else 2*cap)-(ct if cs else 2*cap))
        if not vals:
            continue
        improvements=[statistics.mean(v) for v in vals.values()]
        mean=statistics.mean(improvements)
        wins=sum(x>0 for x in improvements)
        seen[sig]=dict(training_formulas=len(vals),mean_PAR2_saving_s=round(mean,8),
                       wins=wins,losses=sum(x<0 for x in improvements))
        # Cost-aware, conservative activation: at least 8 SHA-distinct
        # examples, 70% wins, and >= 0.3ms *mean* improvement.
        if len(vals)>=8 and wins/len(vals)>=.7 and mean>=.0003:
            positive[sig]=dict(seen[sig],recommended="MI_XOR")
    return dict(seen=seen,positive=positive,training_shas=sorted(train_shas),
                learning_rule="8 distinct SHA, >=70% paired wins, mean gain >=0.3ms")


def main():
    assert BIN.exists(), "First build the native ATLAS15 solver"
    rows=catalog()
    train_cases=[r for r in rows if r["split"]=="train"]
    test_cases=[r for r in rows if r["split"]=="holdout"]
    assert not ({x["sha"] for x in train_cases}&{x["sha"] for x in test_cases})
    ROOT.mkdir(exist_ok=True)
    # May restore previous trained history from Actions cache; never insert
    # a holdout record, including after evaluation.
    db=Memory(DB)
    trials=[]
    from tempfile import TemporaryDirectory
    with TemporaryDirectory() as tmp:
        tmpdir=Path(tmp)
        for i,case in enumerate(train_cases):
            models=list(oracle(case["clauses"],N))
            for rep in range(REPS):
                order=("BASE","MI_XOR") if rep%2==0 else ("MI_XOR","BASE")
                for arm in order:
                    trials.append(run_arm(case,arm,rep,models,tmpdir,None))
            if (i+1)%48==0:
                print("MI_LTM2_TRAIN_PROGRESS",i+1,"/",len(train_cases),flush=True)
        learn(db,trials)
        frozen=freeze_policy(db,train_cases)
        # Write frozen JSON BEFORE any holdout trial is executed.
        policy_path=ROOT/"policy_frozen.json"
        policy_path.write_text(json.dumps(frozen,sort_keys=True,indent=2))
        db.close()
        readonly=Memory(DB,readonly=True)
        # Refuse any accidental policy mutation while evaluating.
        assert readonly.readonly
        loaded=json.loads(policy_path.read_text())
        assert loaded==frozen
        print("MI_LTM2_LEARNING",json.dumps({
            "train_formulas":len(train_cases),
            "recognized_signatures":len(frozen["seen"]),
            "positive_signatures":len(frozen["positive"]),
            "training_observations":len([x for x in trials if x["arm"]=="MI_XOR"])
        }),flush=True)
        for i,case in enumerate(test_cases):
            models=list(oracle(case["clauses"],N))
            for rep in range(REPS):
                # Rotate order; same original SHA and native seed per arm.
                order=("BASE","MI_XOR","LTM_GATE") if rep%2==0 else (
                    "LTM_GATE","MI_XOR","BASE")
                for arm in order:
                    trials.append(run_arm(case,arm,rep,models,tmpdir,loaded))
            if (i+1)%32==0:
                print("MI_LTM2_HOLDOUT_PROGRESS",i+1,"/",len(test_cases),flush=True)
        readonly.close()
    train=[x for x in trials if x["split"]=="train"]
    holdout=[x for x in trials if x["split"]=="holdout"]
    summary=dict(train=summarize(train),holdout=summarize(holdout))
    match_unique={x["sha256"] for x in holdout if x["memory_match"] and
                  x["arm"]=="LTM_GATE"}
    report=dict(formulas=len(rows),train_formulas=len(train_cases),
                holdout_formulas=len(test_cases),reps=REPS,cap_s=CAP,
                families=list(FAMILIES),source_SHA_disjoint=True,
                one_CPU=True,independent_unsat="exhaustive 12-variable enumeration",
                LRAT=False,policy_frozen_before_holdout=True,
                structural_matches_unique=len(match_unique),
                trained_signatures=len(frozen["seen"]),
                activated_signatures=len(frozen["positive"]),
                summary=summary,training_policy=frozen,trial_records=trials,
                limitations=("Coarse signature collisions are possible; positive"
                " training results do not certify future speedup. Tiny 12-var"
                " formulas can be dominated by Python/process startup costs."))
    REPORT.write_text(json.dumps(report,sort_keys=True,indent=2))
    print("MI_LTM2_FINAL",json.dumps({
        "summary":summary,"matched_holdout_formulas":len(match_unique),
        "trained_signatures":len(frozen["seen"]),
        "positive_signatures":len(frozen["positive"]),
        "train":len(train_cases),"holdout":len(test_cases)
    },sort_keys=True),flush=True)


if __name__=="__main__":
    main()
