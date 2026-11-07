#!/usr/bin/env python3
"""TK focused C1 follow-up: one pre-exposed source, same binary and seed."""
import hashlib, json, pathlib, random, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import ultimate_t2_benchmark as t

SHA = "f512310ff59312431ced5edd09a473ebe1c11e6f2dc3baccf3cfde68dc493827"
ID = "61fee64c8fc7f05b97a2bc14c0c2bf41"
MODES = ("t_clean", "c1_lazy_shadow", "c1_lazy_cooldown")
CAP = 45.0
REPS = 3

def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    path = pathlib.Path("ultimate_ta/frozen") / (ID + ".cnf")
    if not path.is_file() or digest(path) != SHA:
        raise RuntimeError("source file missing or hash mismatch")
    root = pathlib.Path("tk-focus")
    root.mkdir(exist_ok=True)
    rows = []
    for rep in range(REPS):
        order = list(MODES)
        random.Random("TK-focus-v1-" + str(rep)).shuffle(order)
        for mode in order:
            status, elapsed, out, gate, native, killed, started, snapshots = t.run_one(path, mode, CAP, SHA)
            if status == "SAT":
                t.prior.helper.gf.sat_check(t.prior.helper.gf.dimacs(path)[1], t.prior.model(out))
                proof = "SAT_WITNESS_CHECKED"
            elif status == "UNSAT":
                if b"R28_ROUTE certified_xor_contradiction" in out:
                    if not t.prior.prior.replay_gf2_unsat(path,out):
                        raise RuntimeError("GF2 replay failed")
                    proof = "GF2_REPLAY"
                else:
                    proof = "UNSAT_NO_INDEPENDENT_LRAT"
            else:
                proof = "TIMEOUT"
            (root / f"{rep}-{mode}.log").write_bytes(out)
            record = dict(rep=rep, mode=mode, sha256=SHA, status=status, proof=proof,
                          elapsed_s=round(min(elapsed,CAP),6),
                          par2_s=round(CAP*2 if status=="TIMEOUT" else elapsed,6),
                          watchdog=killed, gate=gate, native_started=started,
                          native_terminal=native or None, snapshots=snapshots,
                          snapshots_missing=not bool(snapshots))
            rows.append(record)
            (root / "trials.json").write_text(json.dumps(rows,indent=2)+"\n")
            print("TK_TRIAL " + json.dumps(record,sort_keys=True), flush=True)
    if len(rows)!=9 or len({(x["rep"],x["mode"]) for x in rows})!=9:
        raise RuntimeError("missing or duplicate paired mode")
    truth={x["status"] for x in rows if x["status"]!="TIMEOUT"}
    if len(truth)>1:
        raise RuntimeError("contradictory solved outcomes")
    summary={mode:dict(attempts=sum(x["mode"]==mode for x in rows),
                       solved=sum(x["status"]!="TIMEOUT" for x in rows if x["mode"]==mode),
                       par2_s=round(sum(x["par2_s"] for x in rows if x["mode"]==mode),6),
                       with_snapshots=sum(bool(x["snapshots"]) for x in rows if x["mode"]==mode),
                       activated=sum(x["native_started"]==mode for x in rows if x["mode"]==mode))
             for mode in MODES}
    report=dict(status="TK_FOCUS_AUDIT_PASS", scope="one pre-exposed source; fixed seed 11; not blind",
                source_sha256=SHA, cap_s=CAP, repetitions=REPS, summary=summary,
                warning="Timeout counters can be incomplete; UNSAT may lack independent proof.")
    (root/"report.json").write_text(json.dumps(report,indent=2)+"\n")
    print("TK_FINAL "+json.dumps(report,sort_keys=True),flush=True)

if __name__=="__main__":
    main()
