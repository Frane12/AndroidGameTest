#!/usr/bin/env python3
"""R193 live CaDiCaL hybrid vs pure CaDiCaL vs CryptoMiniSat, SHA-paired.
100 deterministic original R193 CNFs; three caps; three repetitions.
Known external originals reused: NOT blind official holdout.
"""
import argparse, collections, hashlib, json, pathlib, random, re, subprocess, time
import sys
sys.path.insert(0, "research")
import r188_feedback_benchmark as helpers

ROOT = pathlib.Path("r193cms100")
FROZEN = ROOT / "frozen"
MANIFEST_SHA = "9eebc6fc1e8ad3006fc3ecc8b451e1e57d3087932190ba5a91fd60aabf278658"
CAPS = (10, 30, 60)
MODES = ("r193_dual_keep_default", "cadical_default", "cryptominisat")
REPS = 3
SHARDS = 20

def check(ok, message):
    if not ok: raise RuntimeError("R193_CMS100_AUDIT_FAIL " + message)

def sha(p): return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def save(p, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, sort_keys=True, indent=2) + "\n")

def selected():
    check(sha(FROZEN / "manifest.json") == MANIFEST_SHA, "manifest changed")
    m = json.loads((FROZEN / "manifest.json").read_text())
    check(len(m["cases"]) == 102, "expected 102 original cases")
    rows = sorted(m["cases"], key=lambda c: c["sha256"])[:100]
    check(len({x["sha256"] for x in rows}) == 100, "not 100 distinct SHA")
    for x in rows:
        check(sha(FROZEN / (x["id"] + ".cnf")) == x["sha256"], "original CNF mismatch")
    return rows

def run_one(case, mode, cap, rep, cdcl, cms):
    src = FROZEN / (case["id"] + ".cnf")
    order = int(hashlib.sha256(("R193-CMS100:" + case["sha256"] + str(rep) + str(cap)).encode()).hexdigest()[:4],16) % 2
    if mode == "cryptominisat": cmd = [cms, str(src)]
    else:
        arm = "dual_keep_default" if mode == "r193_dual_keep_default" else "default"
        cmd = [cdcl, str(src), str(cap), arm, str(order)]
    t = time.perf_counter()
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, errors="replace", timeout=cap + 2)
        elapsed = time.perf_counter() - t
        out = p.stdout
        if mode == "cryptominisat":
            sm = re.search(r"^s (SATISFIABLE|UNSATISFIABLE|UNKNOWN)\s*$", out, re.M)
            status = {"SATISFIABLE":"SAT","UNSATISFIABLE":"UNSAT","UNKNOWN":"TIMEOUT"}.get(sm.group(1), "TIMEOUT") if sm else "TIMEOUT"
            check(p.returncode in (0,10,20), "CMS crashed: "+p.stderr[-250:])
            if p.returncode in (10,20): check(status == ("SAT" if p.returncode == 10 else "UNSAT"), "CMS exit/status disagreement")
        else:
            check(p.returncode == 0, "CaDiCaL driver failed: "+p.stderr[-250:])
            sm = re.search(r"^R182_STATUS status=(SAT|UNSAT|TIMEOUT)\b", out, re.M)
            check(sm is not None, "CaDiCaL status absent")
            status = sm.group(1)
        if elapsed >= cap: status = "TIMEOUT"
        if status == "SAT":
            assignments = {}
            for line in out.splitlines():
                if line.startswith("v "):
                    for lit in map(int, line[2:].split()):
                        if lit:
                            check(abs(lit) not in assignments or assignments[abs(lit)] == (lit>0), "conflicting model")
                            assignments[abs(lit)] = (lit>0)
            _, original = helpers.gf.dimacs(src)
            helpers.gf.sat_check(original, assignments)
        if status != "TIMEOUT" and case.get("expected") not in (None,"UNKNOWN"):
            check(status == case["expected"], "known outcome mismatch")
    except subprocess.TimeoutExpired:
        elapsed = time.perf_counter() - t
        status = "TIMEOUT"
    return dict(id=case["id"], source_sha256=case["sha256"], cohort=case["cohort"],
                family=case["family"], mode=mode, cap_s=cap, rep=rep, order=order,
                elapsed_s=round(elapsed,6), status=status,
                par2_s=round(2*cap if status=="TIMEOUT" else elapsed,6),
                proof=("SAT_WITNESS_CHECKED" if status=="SAT" else
                       "UNSAT_NO_INDEPENDENT_PROOF" if status=="UNSAT" else "CAP_TIMEOUT"))

def shard(n, cdcl, cms):
    cases = selected()
    check(0<=n<SHARDS, "shard outside range")
    records = []
    for case in cases[n::SHARDS]:
        for cap in CAPS:
            for rep in range(REPS):
                modes = list(MODES)
                random.Random(case["sha256"] + str(cap) + str(rep)).shuffle(modes)
                for mode in modes:
                    row=run_one(case, mode, cap, rep, cdcl, cms)
                    records.append(row)
                    save(ROOT / ("shard-%02d.json" % n), records)
                    print("R193_CMS100_TRIAL", json.dumps({k:row[k] for k in ("id","mode","cap_s","rep","status","elapsed_s","par2_s")}),flush=True)
    check(len(records)==len(cases[n::SHARDS])*len(CAPS)*REPS*len(MODES),"shard incomplete")
    print("R193_CMS100_SHARD_PASS", n, len(records),flush=True)

def audit():
    cases=selected(); by_sha={c["sha256"]:c for c in cases}
    records=[]
    for n in range(SHARDS):
        p=ROOT / ("shard-%02d.json" % n)
        check(p.is_file(),"missing shard "+str(n))
        part=json.loads(p.read_text())
        check(len(part)==len(cases[n::SHARDS])*len(CAPS)*REPS*len(MODES),"wrong shard rows")
        records.extend(part)
    check(len(records)==100*3*3*3==2700,"wrong total rows")
    paired=collections.defaultdict(dict)
    for row in records:
        check(row["source_sha256"] in by_sha and row["id"]==by_sha[row["source_sha256"]]["id"],"source mismatch")
        k=(row["source_sha256"],row["cap_s"],row["rep"])
        check(row["mode"] not in paired[k],"duplicate measurement")
        check(row["cap_s"] in CAPS and row["rep"] in range(REPS) and row["mode"] in MODES, "bad parameters")
        check(abs(row["par2_s"] - (2*row["cap_s"] if row["status"]=="TIMEOUT" else row["elapsed_s"])) < .00001, "PAR2 mismatch")
        paired[k][row["mode"]]=row
    check(len(paired)==900,"missing pairs")
    for triple in paired.values():
        check(set(triple)==set(MODES),"incomplete matched case")
        check(len({r["status"] for r in triple.values() if r["status"]!="TIMEOUT"})<=1,"contradictory solved statuses")
    result={}
    for group, subset in [("all",cases),("reused_external_original",[c for c in cases if c["cohort"]=="reused_external_original"]),("new_seed_synthetic",[c for c in cases if c["cohort"]=="new_seed_synthetic"]),("reused_synthetic_control",[c for c in cases if c["cohort"]=="reused_synthetic_control"])]:
        result[group]={"formulas":len(subset),"caps":{}}
        for cap in CAPS:
            vals={}
            for mode in MODES:
                rr=[r for c in subset for rep in range(REPS) for r in [paired[(c["sha256"],cap,rep)][mode]]]
                vals[mode]={"solved":sum(r["status"]!="TIMEOUT" for r in rr),"attempts":len(rr),
                            "par2_s":round(sum(r["par2_s"] for r in rr),6)}
            base=vals["cryptominisat"]["par2_s"]
            result[group]["caps"][str(cap)]={"modes":vals,"speedup_vs_CMS":{k:round(base/v["par2_s"],6) if v["par2_s"] else None for k,v in vals.items()}}
    report={"protocol":"R193-CMS100-PAIRED-3CAP-3REP-v1","status":"AUDIT_PASS",
            "source_manifest_sha256":MANIFEST_SHA,"frozen102_reused_subset_not_blind":True,
            "SAT_witnesses_original_checked":True,"UNSAT_independent_proof":False,
            "cases":100,"attempts":len(records),"groups":result}
    save(ROOT/"report.json",report)
    save(ROOT/"all-trials.json",records)
    print("R193_CMS100_FINAL",json.dumps(report,sort_keys=True),flush=True)

if __name__ == "__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("action",choices=("verify","shard","audit"))
    ap.add_argument("--shard",type=int,default=0)
    ap.add_argument("--cdcl",default="r193cms100/r193-driver")
    ap.add_argument("--cms",default="cryptominisat5")
    args=ap.parse_args()
    if args.action=="verify":print("R193_CMS100_VERIFY_PASS",len(selected()))
    elif args.action=="shard":shard(args.shard,args.cdcl,args.cms)
    else:audit()
