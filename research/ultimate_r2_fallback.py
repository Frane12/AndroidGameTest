#!/usr/bin/env python3
"""Ultimate R2 fallback after the UNMODIFIED R153 exact GF(2) router.

R153 is run first. Only its genuine fallback enters here. Source CNF stays
byte-identical. R166x IPASIR-UP certified rows/units are independently replayed
against the original CNF before any optional live GF(2)->CDCL activation.
"""
import contextlib, hashlib, json, os, pathlib, signal, subprocess, sys, tempfile, time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import r157_source_certified_xor as cert
import r166x_certified_gauss as gauss

ROOT = pathlib.Path("ultimate_r2")
NATIVE = ROOT / "r166x-native"
EMPTY = ROOT / "empty.tsv"
ALLOWED = {"clean", "shadow", "live"}
def need(ok, msg):
    if not ok: raise RuntimeError("ULTIMATE_R2_FAIL_CLOSED " + str(msg))
def source_sha(p): return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()

def cheap_probe(source):
    """Source-only, proof-free XOR eligibility hint; full replay remains mandatory."""
    if source.stat().st_size > 8_000_000 or source.stat().st_size < 300:
        return False, "size_gate"
    groups = {}
    clause = []
    # DIMACS permits clauses across lines and multiple clauses on one line.
    with source.open("r", errors="replace") as fh:
        for line in fh:
            if line.lstrip().startswith(("c", "p", "%")):
                continue
            for tok in line.split():
                try:
                    lit = int(tok)
                except ValueError:
                    return False, "invalid_dimacs_token"
                if lit:
                    if len(clause) <= 6:
                        clause.append(lit)  # 7th literal marks an oversize clause
                    continue
                if 2 <= len(clause) <= 6 and len({abs(x) for x in clause}) == len(clause):
                    a = sorted(clause, key=abs)
                    vs = tuple(abs(x) for x in a)
                    mask = sum(1 << i for i, x in enumerate(a) if x < 0)
                    masks = groups.setdefault(vs, set())
                    if mask not in masks:
                        masks.add(mask)
                        k = len(vs)
                        if len(masks) >= (1 << (k - 1)):
                            for parity in (0, 1):
                                if all(j in masks for j in range(1 << k)
                                       if j.bit_count() % 2 == parity):
                                    return True, "source_complete_xor"
                    if len(groups) >= 5000:
                        return False, "probe_group_cap"
                clause = []
    return False, "no_source_complete_xor"

class PreparationBudgetExceeded(Exception):
    """Cost-only abstention. Never treat this as a GF2 proof failure."""
    pass

def _preparation_alarm(_signum, _frame):
    raise PreparationBudgetExceeded("GF2 certification exceeded wall-time budget")

@contextlib.contextmanager
def preparation_budget(seconds):
    """Bound certification and replay; Linux CI only, no solver proof mutation."""
    if seconds <= 0:
        raise PreparationBudgetExceeded("no preparation budget")
    if not hasattr(signal, "setitimer"):
        raise PreparationBudgetExceeded("wall timer unsupported; abstain safely")
    previous = signal.signal(signal.SIGALRM, _preparation_alarm)
    try:
        signal.setitimer(signal.ITIMER_REAL, seconds)
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)

def main():
    need(len(sys.argv) == 2, "usage: fallback original.cnf")
    src = pathlib.Path(sys.argv[1]).resolve()
    need(src.is_file() and NATIVE.is_file(), "missing source/native")
    need(EMPTY.is_file() and EMPTY.stat().st_size == 0, "empty control TSV missing")
    mode = os.environ.get("ULTIMATE_R2_MODE", "clean")
    need(mode in ALLOWED, "unknown mode")
    deadline = int(os.environ["ULTIMATE_R2_DEADLINE_NS"])
    sha = source_sha(src)
    rows, units = EMPTY, None
    eligible = False; reason = "clean_ablation"; prep_s = 0.
    selected = derived = implied = 0
    started = time.monotonic()
    if mode != "clean":
        yes = False
        try:
            probe_budget_s = min(1.2 - (time.monotonic() - started),
                                 (deadline - time.monotonic_ns()) / 1e9 - 1.5)
            with preparation_budget(probe_budget_s):
                yes, reason = cheap_probe(src)
        except PreparationBudgetExceeded:
            reason = "probe_budget_preempted"
        if yes and (deadline - time.monotonic_ns()) > 2_000_000_000:
            with tempfile.TemporaryDirectory(prefix="ultimate-r2-certs-") as t:
                d = pathlib.Path(t)
                src_tsv, evidence_path = d/"r157.tsv", d/"r157-proof.json"
                # Include cheap probing in the same fixed 1.2s preparation budget.
                # A cost veto means ordinary CDCL fallback, never altered proofs.
                budget_s = min(1.2 - (time.monotonic() - started),
                               (deadline - time.monotonic_ns()) / 1e9 - 1.5)
                if budget_s > 0:
                    try:
                        with preparation_budget(budget_s):
                            ev = cert.extract(src, src_tsv, evidence_path, max_rows=64)
                            need(ev["source_sha256"] == sha, "R157 original SHA drift")
                            selected = ev["selected_rows"]
                            if selected >= 4 and ev["usable_residual_linked_equations"] >= 4:
                                extra = gauss.prepare(src, ev, d/"gauss", max_derived=48)
                                need(gauss.replay(src, ev, extra["certificate"],
                                                  extra["tsv"], extra["units_tsv"]),
                                     "R166x certified replay failed")
                                need(extra["source_sha256"] == sha, "Gaussian SHA drift")
                                prep_s = time.monotonic() - started
                                derived = extra["derived_short_rows"]
                                implied = extra["derived_units"]
                                if prep_s <= 1.2 and (deadline - time.monotonic_ns()) > 1_500_000_000:
                                    eligible = True
                                    reason = "source_certified_live" if mode == "live" else "source_certified_shadow"
                                    rows, units = pathlib.Path(extra["tsv"]), pathlib.Path(extra["units_tsv"])
                                else:
                                    reason = "prep_cost_or_deadline_veto"
                            else:
                                prep_s = time.monotonic() - started
                                reason = "insufficient_residual_xor"
                    except PreparationBudgetExceeded:
                        eligible = False
                        rows, units = EMPTY, None
                        derived = implied = 0
                        prep_s = time.monotonic() - started
                        reason = "prep_budget_preempted"
                else:
                    prep_s = time.monotonic() - started
                    reason = "prep_cost_or_deadline_veto"
                # Native must run *before* temp certificate files are deleted.
                return execute(src, sha, mode, reason, eligible, rows, units,
                               selected, derived, implied, prep_s, deadline)
        else:
            prep_s = time.monotonic() - started
    return execute(src, sha, mode, reason, eligible, rows, units,
                   selected, derived, implied, prep_s, deadline)

def execute(src, sha, mode, reason, eligible, rows, units,
            selected, derived, implied, prep_s, deadline):
    remaining = (deadline - time.monotonic_ns()) / 1e9
    print("ULTIMATE_R2_GATE " + json.dumps(dict(mode=mode,reason=reason,
        eligible=eligible,source_sha256=sha,source_rows=selected,
        derived_rows=derived,derived_units=implied,
        prep_s=round(prep_s,6)), sort_keys=True), flush=True)
    if remaining < 1.0:
        print("ULTIMATE_R2_TIMEOUT preprocessor_budget_exhausted", flush=True)
        return 0
    cmd = [str(NATIVE.resolve()),
           "gauss_cooldown" if mode=="live" and eligible else "clean",
           str(src), str(rows.resolve()), str(min(120.,remaining))]
    if mode=="live" and eligible and units is not None:
        cmd.append(str(units.resolve()))
    # Stream native progress so a forced timeout cannot erase all telemetry.
    sys.stdout.flush()
    try:
        proc=subprocess.run(cmd,timeout=remaining+0.5)
    except subprocess.TimeoutExpired:
        print("ULTIMATE_R2_TIMEOUT watchdog",flush=True);return 0
    need(proc.returncode in (0,10,20), "native CDCL failure " + str(proc.returncode))
    return proc.returncode

if __name__=="__main__":
    try: sys.exit(main())
    except Exception as e:
        print("ULTIMATE_R2_FATAL "+str(e),file=sys.stderr,flush=True)
        sys.exit(78)
