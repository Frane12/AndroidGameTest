#!/usr/bin/env python3
"""C13 easy: 12 deterministic planted SAT instances, 6 C13 arms, 3 repeats."""
import collections, hashlib, json, pathlib, random, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import c13_ablation as c13

OUT = pathlib.Path("easy_out")
SRC = pathlib.Path("easy_sources")
c13.SOURCE = SRC
c13.CAP = 10.0
c13.PROTO = "C13-EASY-PLANTED12-6ARM-3REP-10S-v1"
ARMS = c13.ARMS

def generate():
    SRC.mkdir(exist_ok=True)
    cases = []
    for idx in range(12):
        n = [160, 240, 360, 480][idx // 3]
        ratio = [3.8, 4.2, 4.6][idx % 3]
        m = round(n * ratio)
        rng = random.Random(202611090000 + idx)
        assignment = [False] + [bool(rng.getrandbits(1)) for _ in range(n)]
        clauses = []
        for _ in range(m):
            variables = rng.sample(range(1, n + 1), 3)
            signs = [bool(rng.getrandbits(1)) for _ in range(3)]
            if not any(sign == assignment[v] for v, sign in zip(variables, signs)):
                k = rng.randrange(3)
                signs[k] = assignment[variables[k]]
            clause = [v if sign else -v for v, sign in zip(variables, signs)]
            assert any(assignment[abs(lit)] == (lit > 0) for lit in clause)
            clauses.append(clause)
        text = "p cnf %d %d\n" % (n, m) + "".join(" ".join(map(str, clause)) + " 0\n" for clause in clauses)
        name = "planted-%02d.cnf" % idx
        path = SRC / name
        path.write_text(text, encoding="ascii")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        cases.append(dict(gbd="planted-%02d" % idx, sha256=digest, filename=name,
                          status="SAT", nvars=n, nclauses=m, bytes=path.stat().st_size,
                          generation_seed=202611090000 + idx, clause_width=3, ratio=ratio))
    assert len({x["sha256"] for x in cases}) == 12
    return cases

def shard(i):
    assert 0 <= i < 4
    OUT.mkdir(exist_ok=True)
    cases = generate()
    rows = []
    for idx, x in enumerate(cases):
        if idx % 4 != i:
            continue
        for rep in range(3):
            order_seed = int(hashlib.sha256((x["sha256"] + "|" + str(rep)).encode()).hexdigest()[:8], 16)
            order = list(ARMS)
            random.Random(order_seed).shuffle(order)
            for position, arm in enumerate(order):
                row = c13.trial(x, arm, rep, position, order_seed)
                row["source_kind"] = "synthetic_planted_3sat"
                row["source_original_SHA_verified"] = True
                row["case_variables"] = x["nvars"]
                row["case_ratio"] = x["ratio"]
                rows.append(row)
                print("C13_EASY_TRIAL " + json.dumps(row, sort_keys=True), flush=True)
    assert len(rows) == 54
    (OUT / ("shard-%d.json" % i)).write_text(json.dumps(rows, sort_keys=True))
    print("C13_EASY_SHARD_PASS %d %d" % (i, len(rows)), flush=True)

def audit():
    cases = generate()
    bysha = {x["sha256"]: x for x in cases}
    rows = []
    for i in range(4):
        part = json.loads((OUT / ("shard-%d.json" % i)).read_text())
        assert len(part) == 54
        rows += part
    assert len(rows) == 216
    keys = set()
    for row in rows:
        assert row["source_sha256"] in bysha and row["arm"] in ARMS and row["rep"] in range(3)
        key = (row["source_sha256"], row["arm"], row["rep"])
        assert key not in keys
        keys.add(key)
        assert row["status"] in ("SAT", "TIMEOUT")
        assert row["status"] != "SAT" or row["SAT_original_witness_verified"]
        assert row["PAR2_s"] == 20.0 if row["status"] == "TIMEOUT" else row["PAR2_s"] == row["wall_s"]
    scores = {}
    for arm in ARMS:
        group = [r for r in rows if r["arm"] == arm]
        scores[arm] = dict(solved=sum(r["status"] == "SAT" for r in group),
                           attempts=len(group), par2_s=round(sum(r["PAR2_s"] for r in group), 6))
    report = dict(protocol=c13.PROTO, source_kind="synthetic_planted_3sat",
                  independent_solver_seeds=False, sources=cases, scores=scores, rows=rows,
                  cap_s=10, no_official_or_blind_holdout_claim=True)
    OUT.mkdir(exist_ok=True)
    (OUT / "report.json").write_text(json.dumps(report, sort_keys=True, indent=2))
    print("C13_EASY_FINAL " + json.dumps(scores, sort_keys=True), flush=True)

if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "shard":
        shard(int(sys.argv[2]))
    elif len(sys.argv) == 2 and sys.argv[1] == "audit":
        audit()
    else:
        raise SystemExit("usage: c13_easy_planted.py shard <0..3> | audit")
