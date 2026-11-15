#!/usr/bin/env python3
"""DRNAS SAT reconstruction: 600 unmodified public SATLIB originals.
Freeze sources before any solve. One pinned logical CPU, original-CNF model
checks, DRAT/FRAT-checked UNSAT only, E2E capped verified PAR2.
This is public retrospective evaluation, NOT a blind competition result.
"""
import argparse
import collections
import gzip
import hashlib
import io
import json
import os
import platform
import random
import resource
import signal
import statistics
import subprocess
import tarfile
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / "sat_construct_600_inputs"
OUT = ROOT / "sat_construct_600_results"
CAP = 2.0
SHARDS = 4
ARMS = ("CONSTRUCT", "X59_ON", "X59_OFF", "Kissat", "CaDiCaL", "CMS")
BASE = "https://www.cs.ubc.ca/~hoos/SATLIB/Benchmarks/SAT/"
# Each family has >=100 public original DIMACS files; 100 selected in each.
FAMILIES = (
    ("uf50-218", "RND3SAT/uf50-218.tar.gz", "SAT"),
    ("uuf50-218", "RND3SAT/uuf50-218.tar.gz", "UNSAT"),
    ("uf100-430", "RND3SAT/uf100-430.tar.gz", "SAT"),
    ("uuf100-430", "RND3SAT/uuf100-430.tar.gz", "UNSAT"),
    ("flat30-60", "GCP/flat30-60.tar.gz", "SAT"),
    ("RTI_k3_n100_m429", "BMS/RTI_k3_n100_m429.tar.gz", "SAT"),
)
BIN = {
    "CONSTRUCT": "build/drnas-sat-construct",
    "X59_ON": "build/drnas-sat-native-x59",
    "X59_OFF": "build/drnas-sat-native-x59",
    "Kissat": "build/kissat",
    "CaDiCaL": "build/cadical",
    "CMS": "build/cms",
}
CHECKER = {"DRAT": "build/drat-trim", "FRAT": "build/frat-rs"}

def sha(data):
    return hashlib.sha256(data).hexdigest()

def file_sha(path):
    return sha(Path(path).read_bytes())

def save(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")

def emit(tag, value):
    print(tag + " " + json.dumps(value, sort_keys=True), flush=True)

def parse_cnf(raw):
    """Strict clause-by-clause parse, allowing DIMACS line wrapping."""
    if isinstance(raw, bytes):
        raw = raw.decode("ascii")
    n = m = None
    clauses, clause = [], []
    stop = False
    for line in raw.splitlines():
        tokens = line.split()
        if not tokens:
            continue
        if tokens[0] == "%":
            stop = True
            break
        if tokens[0] == "c":
            continue
        if tokens[0] == "p":
            if n is not None or len(tokens) != 4 or tokens[1] != "cnf":
                raise ValueError("invalid header")
            n, m = map(int, tokens[2:])
            if not (1 <= n <= 15000 and 0 <= m <= 130000):
                raise ValueError("CNF size")
            continue
        if n is None:
            raise ValueError("missing header")
        for tok in tokens:
            value = int(tok)
            if abs(value) > n:
                raise ValueError("literal exceeds header")
            if value:
                clause.append(value)
            else:
                clauses.append(clause)
                clause = []
                if len(clauses) > m:
                    raise ValueError("excess clauses")
    if n is None or clause or len(clauses) != m:
        raise ValueError("incomplete DIMACS")
    return n, clauses

def download(url):
    last = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "DRNAS-SAT-Research/1.0"})
            with urllib.request.urlopen(req, timeout=100) as response:
                blob = response.read(100_000_001)
            if not blob or len(blob) > 100_000_000:
                raise RuntimeError("archive empty or too large")
            return blob
        except Exception as exc:
            last = exc
            time.sleep(2 * (attempt + 1))
    raise RuntimeError("failed to fetch original " + url) from last

def freeze():
    if INPUT.exists():
        raise RuntimeError("input freeze directory exists; do not silently reselect")
    (INPUT / "cnf").mkdir(parents=True)
    items, archive_log, used = [], [], set()
    for family, suffix, label in FAMILIES:
        url = BASE + suffix
        blob = download(url)
        archive_log.append(dict(family=family, url=url, sha256=sha(blob), bytes=len(blob)))
        choices = []
        with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tar:
            for item in tar:
                name = item.name
                lower = name.lower()
                if not item.isfile() or not (lower.endswith(".cnf") or lower.endswith(".cnf.gz")):
                    continue
                if item.size > 2_000_000:
                    continue
                payload = tar.extractfile(item)
                if payload is None:
                    continue
                raw = payload.read(2_000_001)
                if len(raw) > 2_000_000:
                    continue
                if lower.endswith(".gz"):
                    raw = gzip.decompress(raw)
                if len(raw) > 2_000_000:
                    continue
                try:
                    n, clauses = parse_cnf(raw)
                except (ValueError, UnicodeError, OSError):
                    continue
                identity = sha(raw)
                if identity in used:
                    continue
                # Stable selection by filename only, never solver outcome.
                rank = sha((family + "/" + name).encode())
                choices.append((rank, name, raw, identity, n, len(clauses)))
        choices.sort(key=lambda x: (x[0], x[1]))
        if len(choices) < 100:
            raise RuntimeError("not enough valid original sources in " + family +
                               ": " + str(len(choices)))
        for _, name, raw, identity, n, m in choices[:100]:
            if identity in used:
                raise RuntimeError("duplicate SHA across frozen sources")
            used.add(identity)
            ix = len(items)
            rel = f"cnf/{ix:03d}-{identity[:16]}.cnf"
            (INPUT / rel).write_bytes(raw)
            items.append(dict(id=ix, family=family, catalog_label=label,
                              path=rel, source_member=name, sha256=identity,
                              vars=n, clauses=m, bytes=len(raw)))
        emit("CONSTRUCT600_FREEZE_FAMILY", dict(
            family=family, valid_available=len(choices), selected=100,
            archive_sha256=sha(blob)))
    assert len(items) == 600 and len(used) == 600
    manifest = dict(protocol="drnas-construct-real600-v1",
                    selection="first100_sha256_family_and_archive_member_name",
                    retrospective_public_suite=True, blind_holdout=False,
                    cap_s=CAP, shards=SHARDS, arms=ARMS,
                    one_logical_cpu_per_solver=True, original_CNF_only=True,
                    seed=20261115, sources=items, archives=archive_log)
    save(INPUT / "manifest.json", manifest)
    emit("CONSTRUCT600_FROZEN", dict(
        sources=len(items), families=len(FAMILIES),
        manifest_sha256=file_sha(INPUT / "manifest.json")))

def cpu_pin():
    affinity = os.sched_getaffinity(0)
    selected = min(affinity)
    os.sched_setaffinity(0, {selected})
    if len(os.sched_getaffinity(0)) != 1:
        raise RuntimeError("CPU pinning failed")
    return selected

def validate_inputs():
    manifest_path = INPUT / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    if (len(manifest["sources"]) != 600 or
            len({item["sha256"] for item in manifest["sources"]}) != 600 or
            tuple(manifest["arms"]) != ARMS):
        raise RuntimeError("frozen source manifest invalid")
    for item in manifest["sources"]:
        path = INPUT / item["path"]
        if file_sha(path) != item["sha256"]:
            raise RuntimeError("source SHA mismatch: " + str(path))
        n, clauses = parse_cnf(path.read_bytes())
        if (n, len(clauses)) != (item["vars"], item["clauses"]):
            raise RuntimeError("source header changed")
    return manifest

def command(arm, cnf, proof):
    if arm == "CONSTRUCT":
        return [str(ROOT / BIN[arm]), str(cnf), "--max-ms", "25", "--stats"]
    if arm in ("X59_ON", "X59_OFF"):
        cmd = [str(ROOT / BIN[arm]), str(cnf), "--mode", "core",
               "--time", str(CAP), "--proof", str(proof), "--stats"]
        if arm == "X59_ON":
            cmd += ["--sat-construct-ms", "25"]
        return cmd
    if arm == "Kissat":
        return [str(ROOT / BIN[arm]), str(cnf), str(proof)]
    if arm == "CaDiCaL":
        return [str(ROOT / BIN[arm]), "-q", "--no-binary", str(cnf), str(proof)]
    if arm == "CMS":
        return [str(ROOT / BIN[arm]), "--threads=1", "--verb=0",
                "--frat=" + str(proof), str(cnf)]
    raise ValueError(arm)

def run_cmd(cmd, folder, limit):
    """One pinned process, bounded file/memory, wall time and CPU usage."""
    folder.mkdir(exist_ok=False)
    sout, serr = folder / "stdout.txt", folder / "stderr.txt"
    env = dict(os.environ, OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1",
               MKL_NUM_THREADS="1", OPENBLAS_CORETYPE="generic")
    env["LD_LIBRARY_PATH"] = str(ROOT / "build/cms-libs/usr/lib/x86_64-linux-gnu")
    def limits():
        resource.setrlimit(resource.RLIMIT_FSIZE, (64 << 20, 64 << 20))
        resource.setrlimit(resource.RLIMIT_AS, (3 << 30, 3 << 30))
    started = time.perf_counter()
    with sout.open("w") as out, serr.open("w") as err:
        proc = subprocess.Popen(cmd, stdout=out, stderr=err,
                                env=env, preexec_fn=limits, start_new_session=True)
        expired = False
        while True:
            pid, status, usage = os.wait4(proc.pid, os.WNOHANG)
            if pid:
                break
            if time.perf_counter() - started >= limit:
                expired = True
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                _, status, usage = os.wait4(proc.pid, 0)
                break
            time.sleep(.002)
        rc = os.waitstatus_to_exitcode(status)
    return dict(rc=rc, expired=expired,
                elapsed=time.perf_counter() - started,
                cpu=usage.ru_utime + usage.ru_stime,
                rss=usage.ru_maxrss,
                stdout=sout.read_text(errors="replace"),
                stderr=serr.read_text(errors="replace"))

def model_ok(path, stdout):
    """Independent original-CNF check; all declared variables assigned."""
    assignments = {}
    try:
        for row in stdout.splitlines():
            if not row.startswith("v "):
                continue
            for token in row[2:].split():
                lit = int(token)
                if not lit:
                    continue
                v = abs(lit)
                if v in assignments and assignments[v] != (lit > 0):
                    return False
                assignments[v] = lit > 0
        n, clauses = parse_cnf(path.read_bytes())
        return (len(assignments) == n and all(
            1 <= v <= n for v in assignments) and
            all(any(assignments[abs(lit)] == (lit > 0) for lit in clause)
                for clause in clauses))
    except (ValueError, KeyError, UnicodeError):
        return False

def trial(source, arm, shard, temp):
    cnf = INPUT / source["path"]
    if file_sha(cnf) != source["sha256"]:
        raise RuntimeError("source drift")
    folder = temp / f"trial-{source['id']:03d}-{arm}"
    folder.mkdir()
    proof = folder / ("proof.frat" if arm == "CMS" else "proof.drat")
    began = time.perf_counter()
    p = run_cmd(command(arm, cnf, proof), folder / "run", CAP)
    status, proof_kind, checker_s = "UNKNOWN", None, 0.
    if p["expired"]:
        status = "TIMEOUT"
    elif p["rc"] == 10:
        if "s SATISFIABLE" not in p["stdout"].splitlines():
            status = "INVALID_STATUS"
        elif not model_ok(cnf, p["stdout"]):
            status = "INVALID_SAT_MODEL"
        else:
            status, proof_kind = "SAT_VERIFIED", "MODEL"
    elif p["rc"] == 20:
        if "s UNSATISFIABLE" not in p["stdout"].splitlines():
            status = "INVALID_STATUS"
        elif not proof.exists() or not proof.stat().st_size:
            status = "UNSAT_UNVERIFIED"
        else:
            kind = "FRAT" if arm == "CMS" else "DRAT"
            if kind == "FRAT":
                check = [str(ROOT / CHECKER[kind]), "elab",
                         str(proof), str(cnf), "-v"]
            else:
                check = [str(ROOT / CHECKER[kind]), str(cnf), str(proof)]
            remains = CAP - (time.perf_counter() - began)
            if remains > .002:
                c = run_cmd(check, folder / "check", remains)
                checker_s = c["elapsed"]
                if (not c["expired"] and c["rc"] == 0 and
                        "VERIFIED" in c["stdout"]):
                    status, proof_kind = "UNSAT_VERIFIED", kind
                else:
                    status = "CHECK_TIMEOUT" if c["expired"] else "UNSAT_UNVERIFIED"
            else:
                status = "CHECK_BUDGET_EXHAUSTED"
    elif p["rc"] not in (0, 153):
        status = "RESOURCE_LIMIT" if p["rc"] in (-9, -25, 137) else "SOLVER_ERROR"
    elapsed = time.perf_counter() - began
    accepted = status in ("SAT_VERIFIED", "UNSAT_VERIFIED") and elapsed <= CAP
    if not accepted and status in ("SAT_VERIFIED", "UNSAT_VERIFIED"):
        status, proof_kind = "CHECK_BUDGET_EXHAUSTED", None
    critical = status in ("INVALID_SAT_MODEL", "INVALID_STATUS", "SOLVER_ERROR")
    if accepted and (("SAT" if status == "SAT_VERIFIED" else "UNSAT") !=
                     source["catalog_label"]):
        critical = True
    method = None
    for line in p["stderr"].splitlines():
        if line.startswith(("SAT_NATIVE_STATS ", "SAT_CONSTRUCT_STATS ")):
            try:
                meta = json.loads(line.split(" ", 1)[1])
                method = meta.get("method")
            except ValueError:
                pass
    return dict(id=source["id"], sha256=source["sha256"],
                family=source["family"], expected=source["catalog_label"],
                shard=shard, arm=arm, status=status, accepted=accepted,
                certificate=proof_kind, method=method,
                solver_s=round(p["elapsed"], 6),
                checker_s=round(checker_s, 6),
                e2e_s=round(elapsed, 6),
                solver_cpu_s=round(p["cpu"], 6), maxrss_kib=p["rss"],
                PAR2_s=round(elapsed if accepted else 2 * CAP, 6),
                rc=p["rc"], critical=critical,
                error_tail=p["stderr"][-500:] if critical else None)

def shard_run(shard):
    if not 0 <= shard < SHARDS:
        raise ValueError("invalid shard")
    cpu = cpu_pin()
    manifest = validate_inputs()
    out = OUT / f"shard-{shard}"
    out.mkdir(parents=True, exist_ok=False)
    binary_shas = {name: file_sha(ROOT / p) for name, p in BIN.items()}
    for path in CHECKER.values():
        binary_shas[path] = file_sha(ROOT / path)
    save(out / "protocol.json", dict(cpu=cpu, cap_s=CAP,
         shard=shard, manifest_sha256=file_sha(INPUT / "manifest.json"),
         binaries=binary_shas, platform=platform.platform()))
    counts = collections.Counter()
    with (out / "trials.jsonl").open("w") as stream, tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        sources = [x for x in manifest["sources"] if x["id"] % SHARDS == shard]
        for i, source in enumerate(sources):
            arms = list(ARMS)
            random.Random(20261115 + source["id"]).shuffle(arms)
            for arm in arms:
                row = trial(source, arm, shard, tmp)
                stream.write(json.dumps(row, sort_keys=True) + "\n")
                stream.flush()
                counts[(arm, row["status"])] += 1
                if row["critical"]:
                    emit("CONSTRUCT600_CRITICAL", row)
                # No raw run logs in Actions. Keep per-source JSONL as artifact.
                import shutil
                shutil.rmtree(tmp / f"trial-{source['id']:03d}-{arm}")
            if (i + 1) % 25 == 0:
                emit("CONSTRUCT600_PROGRESS", dict(shard=shard,
                     sources_complete=i+1, total_sources=len(sources)))
    emit("CONSTRUCT600_SHARD_COMPLETE", dict(shard=shard, cpu=cpu,
         sources=len(sources), trials=sum(counts.values()),
         statuses={f"{a}:{s}": count for (a, s), count in sorted(counts.items())}))

def report():
    manifest = validate_inputs()
    rows = []
    for ix in range(SHARDS):
        path = OUT / f"shard-{ix}" / "trials.jsonl"
        rows.extend(json.loads(s) for s in path.read_text().splitlines())
    expected = {(s["id"], a) for s in manifest["sources"] for a in ARMS}
    observed = [(r["id"], r["arm"]) for r in rows]
    if len(observed) != len(set(observed)) or set(observed) != expected:
        raise RuntimeError(f"incomplete/duplicate matrix {len(observed)} / {len(expected)}")
    if any(r["sha256"] != manifest["sources"][r["id"]]["sha256"] for r in rows):
        raise RuntimeError("source SHA mismatch during trials")
    totals, by_family = {}, {}
    for arm in ARMS:
        subset = [r for r in rows if r["arm"] == arm]
        sat = [r for r in subset if r["expected"] == "SAT"]
        totals[arm] = dict(trials=len(subset), verified_sat=sum(
            r["status"] == "SAT_VERIFIED" and r["accepted"] for r in subset),
            verified_unsat=sum(r["status"] == "UNSAT_VERIFIED" and r["accepted"] for r in subset),
            PAR2_all_s=round(sum(r["PAR2_s"] for r in subset), 6),
            PAR2_sat_s=round(sum(r["PAR2_s"] for r in sat), 6),
            SAT_sources=len(sat), statuses=dict(collections.Counter(r["status"] for r in subset)),
            methods=dict(collections.Counter(str(r["method"]) for r in subset
                                               if r["method"])))
        for fam, _, _ in FAMILIES:
            rr = [r for r in subset if r["family"] == fam]
            by_family[f"{arm}:{fam}"] = dict(
                accepted=sum(r["accepted"] for r in rr),
                SAT=sum(r["status"] == "SAT_VERIFIED" and r["accepted"] for r in rr),
                UNSAT=sum(r["status"] == "UNSAT_VERIFIED" and r["accepted"] for r in rr),
                PAR2_s=round(sum(r["PAR2_s"] for r in rr), 6))
    criticals = [r for r in rows if r["critical"]]
    for source in manifest["sources"]:
        verdicts = {r["status"] for r in rows if r["id"] == source["id"]
                    and r["accepted"]}
        if "SAT_VERIFIED" in verdicts and "UNSAT_VERIFIED" in verdicts:
            criticals.append(dict(id=source["id"], reason="verified SAT/UNSAT conflict"))
    summary = dict(status="COMPLETE" if not criticals else "CRITICAL",
        sources=600, trials=len(rows), verified_sources=600,
        categories=[x[0] for x in FAMILIES], cap_s=CAP,
        manifest_sha256=file_sha(INPUT / "manifest.json"), arms=totals,
        by_family=by_family, critical_count=len(criticals), criticals=criticals,
        retrospective_public_suite=True, not_blind=True,
        repetitions=1, no_automatic_promotion=True,
        scoring="E2E verified PAR2, timeout/unverified=2*cap",
        caveat="Standalone constructor deliberately never proves UNSAT; compare SAT-only separately.")
    save(OUT / "summary.json", summary)
    lines = ["# DRNAS SAT reconstruction: SATLIB REAL600", "",
        "600 public, unmodified CNFs; 100 per family; 400 catalog SAT / 200 catalog UNSAT.",
        "Retrospective public suite, NOT a blind benchmark. One logical CPU per solver.",
        "Every SAT model independently checked on the original DIMACS.",
        "Only independently checked DRAT/FRAT UNSAT is scored as verified.",
        "E2E cap 2 s, PAR2 failure penalty 4 s. One attempt per source/arm.",
        "", "| Solver | Verified SAT | Verified UNSAT | PAR2 all (s) | PAR2 SAT-only (s) |",
        "|---|---:|---:|---:|---:|"]
    for arm in ARMS:
        t = totals[arm]
        lines.append(f"| {arm} | {t['verified_sat']} | {t['verified_unsat']} | {t['PAR2_all_s']:.3f} | {t['PAR2_sat_s']:.3f} |")
    lines.extend(["", f"Critical problems: {len(criticals)}",
        "No promotion to main and no claim of general superiority.",
        "Full source manifest, SHA-256, per-trial metrics and family breakdown are retained."])
    (OUT / "README.md").write_text("\n".join(lines) + "\n")
    emit("CONSTRUCT600_FINAL", dict(status=summary["status"],
         sources=600, trials=len(rows), critical=len(criticals), arms=totals))
    if criticals:
        raise RuntimeError("critical verified/model errors: see summary.json")

def selftest():
    sat = b"c tiny SAT\np cnf 2 3\n1 2 0\n-1 2 0\n1 -2 0\n"
    unsat = b"p cnf 1 2\n1 0\n-1 0\n"
    for b in (sat, unsat):
        assert parse_cnf(b)[0] > 0
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "a.cnf"
        p.write_bytes(sat)
        assert model_ok(p, "s SATISFIABLE\nv 1 2 0\n")
        assert not model_ok(p, "s SATISFIABLE\nv -1 -2 0\n")
        p.write_bytes(unsat)
        assert not model_ok(p, "s SATISFIABLE\nv 1 0\n")
    emit("CONSTRUCT600_SELFTEST", dict(status="PASS"))

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=("selftest", "freeze", "shard", "report"))
    ap.add_argument("--index", type=int, default=None)
    args = ap.parse_args()
    if args.action == "selftest":
        selftest()
    elif args.action == "freeze":
        freeze()
    elif args.action == "shard":
        shard_run(args.index)
    elif args.action == "report":
        report()
