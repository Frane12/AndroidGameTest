#!/usr/bin/env python3
"""DRNAS V17.8: official 2026 Main Track instances, parallel shards,
paired serialized comparisons per runner. No outcome-driven instance choice.
External official competition INSTANCES, not official competition scoring.
"""
from __future__ import annotations
import argparse, bz2, csv, gzip, hashlib, io, json, lzma, os, random
import statistics, subprocess, sys, time, urllib.request, zipfile, zlib
from pathlib import Path

PINNED_KISSAT = "8af8e56f174b778aef3aa45af9f739b2a5f492c2"
PINNED_TRACK = "3e2dee7cf5aa643c77bf946280a3c1c520756ef9"
TRACK_URL = f"https://raw.githubusercontent.com/satcompetition/2026/{PINNED_TRACK}/downloads/track_main_2026.uri"
MODES = ("baseline", "fixed25", "fixed50", "switch2048", "predict", "v1531")
TIME_LIMIT = 8.0
REPEATS = 2
SHARDS = 4
MAX_CASES = 4
MAX_ATTEMPTS = 35
COMPRESSED_LIMIT = 12 * 1024 * 1024
RAW_LIMIT = 64 * 1024 * 1024
FROZEN_RULE = "g lt 0.8692513215 1024\n"  # frozen v17.7 result; not fitted on official
ROOT = Path("drnas-v178-official-results")
FIELDS = ("batch", "official_index", "gbd_hash", "sha256", "nvars",
          "nclauses", "repeat", "mode", "status", "seconds", "par2",
          "sat_model_verified", "unsat_proof_verified", "reason")

def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def fetch(url: str, size_limit: int, timeout: int = 9) -> bytes:
    req = urllib.request.Request(url, headers={
        "User-Agent": "DRNAS-SAT-reproducible-research/1.0",
        "Accept-Encoding": "identity"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        data = response.read(size_limit + 1)
    if len(data) > size_limit:
        raise ValueError("compressed byte limit reached")
    return data

def unpack_limited(data: bytes) -> bytes:
    if data.startswith(b"\xfd7zXZ\x00"):
        dec = lzma.LZMADecompressor()
        out = dec.decompress(data, max_length=RAW_LIMIT + 1)
    elif data[:2] == b"\x1f\x8b":
        dec = zlib.decompressobj(16 + zlib.MAX_WBITS)
        out = dec.decompress(data, RAW_LIMIT + 1)
    elif data[:3] == b"BZh":
        dec = bz2.BZ2Decompressor()
        out = dec.decompress(data, max_length=RAW_LIMIT + 1)
    elif data[:4] == b"PK\x03\x04":
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            members = [i for i in archive.infolist()
                       if not i.is_dir() and ".cnf" in i.filename.lower()]
            if len(members) != 1 or members[0].file_size > RAW_LIMIT:
                raise ValueError("archive not single small CNF")
            out = archive.read(members[0])
    else:
        out = data
    if len(out) > RAW_LIMIT:
        raise ValueError("decompressed byte limit reached")
    return out

def dimensions(data: bytes):
    n = m = None
    clauses = 0
    for raw in data.splitlines():
        line = raw.strip()
        if not line or line.startswith(b"c "):
            continue
        if line.startswith(b"p "):
            parts = line.split()
            if len(parts) != 4 or parts[1] != b"cnf" or n is not None:
                raise ValueError("not DIMACS CNF")
            n, m = int(parts[2]), int(parts[3])
            if n <= 0 or m < 0 or n > 3_000_000 or m > 10_000_000:
                raise ValueError("unsupported DIMACS size")
        elif line[:1] == b"%":
            break
        else:
            if n is None:
                raise ValueError("missing DIMACS header")
            clauses += sum(t == b"0" for t in line.split())
    if n is None or clauses != m:
        raise ValueError(f"DIMACS count mismatch: {clauses} vs {m}")
    return n, m

def obtain_shard(batch: int, out: Path):
    uri_data = fetch(TRACK_URL, 100_000)
    uris = uri_data.decode("utf-8").strip().splitlines()
    if len(uris) != 400:
        raise ValueError(f"official 2026 URI listing expected 400, got {len(uris)}")
    (out / "official_track_uri_sha256.txt").write_text(sha(uri_data) + "\n")
    official = []
    failed = []
    for candidate in range(MAX_ATTEMPTS):
        if len(official) >= MAX_CASES:
            break
        # Predeclared index walk: distributes selection across 400 URI IDs.
        index = ((batch + SHARDS * candidate) * 3) % 400
        url = uris[index].replace("http://", "https://", 1)
        gbd_hash = url.rsplit("/", 1)[-1]
        try:
            archived = fetch(url, COMPRESSED_LIMIT)
            raw = unpack_limited(archived)
            n, m = dimensions(raw)
            dest = out / "cnf" / f"official_{index:03d}_{gbd_hash}.cnf"
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(raw)
            item = dict(batch=batch, official_index=index, gbd_hash=gbd_hash,
                        url=url, compressed_sha256=sha(archived), sha256=sha(raw),
                        compressed_bytes=len(archived), cnf_bytes=len(raw),
                        nvars=n, nclauses=m, path=str(dest), origin="SAT Competition 2026 Main Track / GBD")
            official.append(item)
            print("V178_OFFICIAL_DOWNLOADED", json.dumps({k:v for k,v in item.items() if k!="path"}), flush=True)
        except Exception as error:
            failed.append(dict(index=index, gbd_hash=gbd_hash,
                               issue=str(error)[:250]))
            print("V178_OFFICIAL_SKIP", index, str(error)[:150], flush=True)
    payload = dict(track=TRACK_URL, track_commit=PINNED_TRACK,
                   track_uri_sha256=sha(uri_data), selection="fixed modular index order and byte limits only",
                   selection_not_based_on_solver_times=True, download_attempts=len(official)+len(failed),
                   failures=failed, cases=[{k:v for k,v in x.items() if k!="path"} for x in official],
                   modes=MODES, cap_seconds=TIME_LIMIT, repeats=REPEATS,
                   kissat_commit=PINNED_KISSAT,
                   policy_source="V17.7 176xxx dev, frozen prior to 2026 official cases",
                   frozen_rule_sha256=sha(FROZEN_RULE.encode()),
                   official_instances_not_official_competition_ranking=True)
    (out / "manifest.json").write_text(json.dumps(payload, indent=2))
    if not official:
        raise RuntimeError("No small official instances downloaded. See manifest failures.")
    return official

def check_model(path: Path, stdout: str, payload: dict|None) -> bool:
    values = {}
    lits = []
    if payload and isinstance(payload.get("model"), list):
        lits = payload["model"]
    else:
        for raw in stdout.splitlines():
            if raw.startswith("v "):
                lits += [int(t) for t in raw.split()[1:] if t != "0"]
    for lit in lits:
        if not isinstance(lit, int) or lit == 0:
            return False
        v = abs(lit)
        if v in values and values[v] != (lit > 0):
            return False
        values[v] = lit > 0
    if not values:
        return False
    current = []
    checked = 0
    with path.open(encoding="ascii") as file:
        for raw in file:
            line = raw.strip()
            if not line or line.startswith("c ") or line.startswith("p "):
                continue
            if line.startswith("%"):
                break
            for token in line.split():
                lit = int(token)
                if lit:
                    current.append(lit)
                else:
                    checked += 1
                    if not any(values.get(abs(x)) == (x > 0) for x in current):
                        return False
                    current = []
    return checked > 0 and not current

def run_one(case, mode, kissat, drnas, rule):
    path = Path(case["path"])
    env = os.environ.copy()
    env.pop("DRNAS_V177_MODE", None)
    env.pop("DRNAS_V177_RULE_FILE", None)
    if mode == "v1531":
        cmd = [str(drnas), str(path.resolve()), str(kissat.resolve()), "1"]
    else:
        flags = ["--restartint=25"] if mode == "fixed25" else (
            ["--restartint=50"] if mode == "fixed50" else [])
        if mode == "predict":
            env["DRNAS_V177_MODE"] = "predict"
            env["DRNAS_V177_RULE_FILE"] = str(rule.resolve())
        elif mode == "switch2048":
            env["DRNAS_V177_MODE"] = "switch2048"
        cmd = [str(kissat), *flags, "-s", str(path)]
    start = time.perf_counter()
    try:
        process = subprocess.run(cmd, env=env, capture_output=True,
                                 text=True, errors="replace",
                                 check=False, timeout=TIME_LIMIT)
        output = process.stdout + "\n" + process.stderr
        payload = None
        for raw in process.stdout.splitlines():
            if raw.startswith("DRNAS_HYBRID_RESULT\t"):
                payload = json.loads(raw.split("\t", 1)[1])
        if payload:
            status = str(payload.get("status", "ERROR"))
        else:
            status = ("SAT" if "s SATISFIABLE" in output else
                      "UNSAT" if "s UNSATISFIABLE" in output else "ERROR")
        elapsed = time.perf_counter() - start
    except subprocess.TimeoutExpired:
        status, elapsed, output, payload = "TIMEOUT", time.perf_counter() - start, "", None
    reason = ""
    witness = None
    if status == "SAT":
        witness = check_model(path, output, payload)
        if not witness:
            status = "ERROR"
            reason = "SAT witness invalid/missing"
    if status not in ("SAT", "UNSAT", "TIMEOUT"):
        reason = reason or ("invalid solver return/status: " + output[-200:].replace("\n"," "))
    return dict(status=status, seconds=round(elapsed, 6),
                par2=(round(elapsed, 6) if status in ("SAT", "UNSAT") else 2*TIME_LIMIT),
                sat_model_verified=witness, unsat_proof_verified=False,
                reason=reason)

def write_csv(path, rows):
    with path.open("w", newline="") as stream:
        writer=csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

def main_batch(batch: int):
    out = ROOT / f"batch_{batch}"
    out.mkdir(parents=True, exist_ok=True)
    rule = out / "frozen_v177_rule.txt"
    rule.write_text(FROZEN_RULE)
    cases = obtain_shard(batch, out)
    kissat = Path("/tmp/kissat-v178/build/kissat")
    drnas = Path("/tmp/v1531_nohang")
    assert kissat.is_file() and drnas.is_file()
    rows=[]
    for case in cases:
        assert sha(Path(case["path"]).read_bytes()) == case["sha256"]
        for repeat in range(REPEATS):
            order = list(MODES)
            random.Random(178011 + batch*1000 + case["official_index"]*7 + repeat).shuffle(order)
            statuses=[]
            for mode in order:
                result = run_one(case,mode,kissat,drnas,rule)
                row={k:case[k] for k in ("batch","official_index","gbd_hash","sha256","nvars","nclauses")}
                row.update(repeat=repeat,mode=mode,**result)
                rows.append(row)
                statuses.append(row)
                print("V178_OFFICIAL_MEASURE", batch, case["official_index"], repeat,
                      mode,result["status"],result["seconds"],"PAR2",result["par2"],flush=True)
            write_csv(out/"measurements.partial.csv",rows)
            answers={r["status"] for r in statuses if r["status"] in ("SAT","UNSAT")}
            if len(answers)>1:
                raise RuntimeError(f"SAT/UNSAT contradiction for {case['gbd_hash']}: {answers}")
            if any(r["status"]=="ERROR" for r in statuses):
                raise RuntimeError(f"Invalid solver result on official instance {case['gbd_hash']}")
    write_csv(out/"measurements.csv",rows)
    ranking=[]
    for mode in MODES:
        selected=[r for r in rows if r["mode"]==mode]
        ranking.append(dict(mode=mode, attempts=len(selected), solved=sum(r["status"] in ("SAT","UNSAT") for r in selected),
                            par2=round(statistics.mean(r["par2"] for r in selected),6),
                            sum_par2=round(sum(r["par2"] for r in selected),6),
                            sat_witnesses_verified=sum(r["sat_model_verified"] is True for r in selected),
                            unsat_proofs_verified=0))
    ranking.sort(key=lambda x:(x["par2"],-x["solved"]))
    summary=dict(batch=batch,n_cases=len(cases),n_measurements=len(rows),ranking=ranking,
                 correct_sat_witnesses_checked=True,unsat_proofs_independently_checked=False,
                 benchmark_type="Official SAT Competition 2026 Main Track CNFs, independent rerun",
                 not_official_competition_scoring=True)
    (out/"summary.json").write_text(json.dumps(summary,indent=2))
    print("V178_BATCH_AUDIT_PASS",json.dumps(summary),flush=True)

def main_aggregate():
    manifests=[]
    rows=[]
    for batch in range(SHARDS):
        folder=ROOT/f"batch_{batch}"
        man=json.loads((folder/"manifest.json").read_text())
        manifests.append(man)
        with (folder/"measurements.csv").open(newline="") as f:
            rows.extend(csv.DictReader(f))
    if not rows:
        raise RuntimeError("No measured official instances")
    cases={}
    for row in rows:
        k=(int(row["batch"]),row["sha256"])
        cases.setdefault(k,[]).append(row)
    for key,vals in cases.items():
        assert len(vals)==REPEATS*len(MODES),f"incomplete paired comparison {key}"
        assert {(int(x["repeat"]),x["mode"]) for x in vals} == {
            (rep,mode) for rep in range(REPEATS) for mode in MODES}
    output=[]
    base={}
    for key,vals in cases.items():
        base[key]=statistics.mean(float(x["par2"]) for x in vals if x["mode"]=="baseline")
    for mode in MODES:
        subset=[x for x in rows if x["mode"]==mode]
        vals={k:statistics.mean(float(x["par2"]) for x in records if x["mode"]==mode)
              for k,records in cases.items()}
        delta=[base[k]-vals[k] for k in sorted(cases)]
        gen=random.Random(17826)
        bootstrap=sorted(statistics.mean(delta[gen.randrange(len(delta))] for _ in delta)
                         for _ in range(1500))
        output.append(dict(mode=mode,
                           official_instances=len(cases),
                           attempts=len(subset),
                           solved=sum(x["status"] in ("SAT","UNSAT") for x in subset),
                           par2=round(statistics.mean(float(x["par2"]) for x in subset),6),
                           improvement_pct=round(100*(1-sum(vals.values())/sum(base.values())),3),
                           delta_ci95=[round(bootstrap[37],6),round(bootstrap[1461],6)],
                           sat_witnesses=sum(x["sat_model_verified"]=="True" for x in subset),
                           independent_unsat_proofs=0))
    output.sort(key=lambda x:x["par2"])
    result=dict(source_type="official SAT Competition 2026 Main Track instances",
                test_type="independent GitHub Actions replay, not official competition",
                pinned_kissat=PINNED_KISSAT,pinned_track=PINNED_TRACK,
                formula_count=len(cases),total_measurements=len(rows),
                shard_count=SHARDS,cap=TIME_LIMIT,repeats=REPEATS,
                strategies=output,selection_method="predeclared modular hash index and size cap",
                no_unseen_data_fitting=True,unsat_independent_proofs=False,
                caveat="Runner comparisons are paired within shards; official samples size-filtered. CI resamples formulas.")
    (ROOT/"aggregate.json").write_text(json.dumps(result,indent=2))
    print("V178_OFFICIAL_FINAL",json.dumps(result),flush=True)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--batch",type=int)
    ap.add_argument("--aggregate",action="store_true")
    args=ap.parse_args()
    if args.aggregate:main_aggregate()
    elif args.batch in range(SHARDS):main_batch(args.batch)
    else:ap.error("Provide --batch 0..3 or --aggregate")

if __name__=="__main__":
    main()
