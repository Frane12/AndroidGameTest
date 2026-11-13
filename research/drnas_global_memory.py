#!/usr/bin/env python3
"""DRNAS Global Memory v1: durable evidence registry, not an automatic model trainer.

Imports GitHub Actions run metadata and compatible result artifacts, links the
existing X47 30K SQLite learning archive and keeps all evaluation/holdout
observations out of the explicitly eligible training view. Idempotent by
GitHub run/artifact IDs and original CNF SHA; never confuses repetitions
with independent problems or workflow-reported verification with new proofs.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sqlite3
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile

REPO = "Frane12/AndroidGameTest"
DB_VERSION = "DRNAS-GLOBAL-MEMORY-v1"
SHA_RE = re.compile(r"[0-9a-fA-F]{64}")
MAX_ZIP_BYTES = 18 * 1024 * 1024
MAX_MEMBER_BYTES = 5 * 1024 * 1024
ARTIFACT_HINTS = re.compile(
    r"drnas|x4[0-9]|ltm|sat|solver|bench|summary|result|trial|report|r(?:28|29|153|160|190|194)",
    re.IGNORECASE,
)
REPORT_NAMES = {
    "report.json", "summary.json", "final_summary.json", "training_report.json",
    "cost_report.json", "guard_report.json", "php5_aggregate.json",
    "php5_detailed_summary.json", "fast5_summary.json",
    "x47_long_summary.json", "x47_hard4_final_summary.json",
    "x47long_final_report.json", "manifest.json", "protocol.json",
}
UTC = lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")


def emit(name, value):
    print(name + " " + json.dumps(value, separators=(",", ":"), sort_keys=True), flush=True)


def create_schema(db):
    db.executescript("""
        PRAGMA journal_mode=DELETE;
        PRAGMA foreign_keys=ON;
        CREATE TABLE IF NOT EXISTS meta (
          key TEXT PRIMARY KEY, value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS runs (
          run_id INTEGER PRIMARY KEY, name TEXT, path TEXT, source_branch TEXT,
          head_sha TEXT, created_at TEXT, updated_at TEXT, status TEXT,
          conclusion TEXT, html_url TEXT, source_event TEXT
        );
        CREATE TABLE IF NOT EXISTS artifacts (
          artifact_id INTEGER PRIMARY KEY, run_id INTEGER, name TEXT,
          size_bytes INTEGER, created_at TEXT, expired INTEGER,
          import_state TEXT NOT NULL DEFAULT 'pending',
          detail TEXT, last_attempt_at TEXT
        );
        CREATE INDEX IF NOT EXISTS artifacts_pending ON artifacts(import_state,created_at);
        CREATE TABLE IF NOT EXISTS sources (
          sha256 TEXT PRIMARY KEY, family TEXT, dataset TEXT,
          first_run INTEGER, cert_claim TEXT, first_seen_at TEXT
        );
        CREATE TABLE IF NOT EXISTS observations (
          artifact_id INTEGER NOT NULL, run_id INTEGER,
          source_sha TEXT NOT NULL, arm TEXT NOT NULL, rep INTEGER NOT NULL,
          family TEXT, cohort TEXT, status TEXT, verified_claim INTEGER,
          par2_s REAL, e2e_s REAL, conflicts INTEGER, decisions INTEGER,
          role TEXT NOT NULL DEFAULT 'holdout', cert_claim TEXT,
          model_sha TEXT, guard_sha TEXT, source_id TEXT, member TEXT,
          PRIMARY KEY(artifact_id,source_sha,arm,rep)
        );
        CREATE INDEX IF NOT EXISTS observations_sha ON observations(source_sha);
        CREATE INDEX IF NOT EXISTS observations_run ON observations(run_id);
        CREATE TABLE IF NOT EXISTS reports (
          artifact_id INTEGER NOT NULL, path TEXT NOT NULL, run_id INTEGER,
          content_sha TEXT NOT NULL, kind TEXT, json_payload TEXT NOT NULL,
          PRIMARY KEY(artifact_id,path)
        );
        CREATE TABLE IF NOT EXISTS legacy_experiences (
          source_sha TEXT PRIMARY KEY, namespace TEXT NOT NULL, split TEXT NOT NULL,
          family TEXT, payload TEXT NOT NULL, original_run TEXT,
          imported_from TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS legacy_splits ON legacy_experiences(split,namespace);
        CREATE TABLE IF NOT EXISTS legacy_checkpoints (
          namespace TEXT NOT NULL, checkpoint_id INTEGER NOT NULL,
          cycle INTEGER, accepted INTEGER, tune_cost INTEGER,
          model_json TEXT NOT NULL,
          PRIMARY KEY(namespace,checkpoint_id)
        );
        CREATE TABLE IF NOT EXISTS sealed_reports (
          namespace TEXT NOT NULL, report_id INTEGER NOT NULL,
          json_payload TEXT NOT NULL,
          PRIMARY KEY(namespace,report_id)
        );
        CREATE TABLE IF NOT EXISTS model_registry (
          namespace TEXT PRIMARY KEY, run_id TEXT, source_commit TEXT, stage TEXT,
          model_hash TEXT, model_json TEXT, claimed_deployment_allowed INTEGER,
          promotion_status TEXT, reason TEXT
        );
        CREATE VIEW IF NOT EXISTS eligible_training AS
          SELECT e.source_sha,e.namespace,e.family,e.payload
          FROM legacy_experiences AS e
          WHERE e.split='train'
            AND NOT EXISTS (
              SELECT 1 FROM observations o
              WHERE o.source_sha=e.source_sha AND o.role!='train'
            );
        """)
    db.execute("INSERT OR IGNORE INTO meta VALUES (?,?)", ("schema_version", DB_VERSION))


def sha256(b):
    return hashlib.sha256(b).hexdigest()


def valid_sha(s):
    return isinstance(s, str) and SHA_RE.fullmatch(s) is not None


def safe_num(x, integer=False):
    if isinstance(x, bool) or x is None:
        return None
    try:
        y = int(x) if integer else float(x)
        if not math.isfinite(y) or y < 0 or y > 1e13:
            return None
        return y
    except (TypeError, ValueError, OverflowError):
        return None


class Github:
    """REST reader: only bearer-authenticated github.com API calls."""
    def __init__(self, token, repo=REPO):
        if not token:
            raise ValueError("GitHub actions read token required")
        self.token = token
        self.root = "https://api.github.com/repos/" + repo + "/actions"

    def json(self, path):
        req = urllib.request.Request(
            self.root + path,
            headers={
                "Authorization": "Bearer " + self.token,
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "drnas-global-memory",
            },
        )
        with urllib.request.urlopen(req, timeout=45) as h:
            return json.load(h)

    def artifact_zip(self, artifact_id):
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None

        api = self.root + f"/artifacts/{artifact_id}/zip"
        req = urllib.request.Request(
            api,
            headers={
                "Authorization": "Bearer " + self.token,
                "Accept": "application/vnd.github+json",
                "User-Agent": "drnas-global-memory",
            },
        )
        opener = urllib.request.build_opener(NoRedirect())
        try:
            with opener.open(req, timeout=45) as h:
                raise RuntimeError("Expected signed GitHub archive redirect")
        except urllib.error.HTTPError as exc:
            if exc.code not in (301, 302, 303, 307, 308):
                raise
            target = exc.headers.get("Location", "")
        u = urllib.parse.urlparse(target)
        if u.scheme != "https" or not u.hostname:
            raise ValueError("Artifact redirect is not HTTPS")
        # Never forward the GitHub bearer token to the signed blob URL.
        req = urllib.request.Request(target, headers={"User-Agent": "drnas-global-memory"})
        with urllib.request.urlopen(req, timeout=90) as h:
            payload = h.read(MAX_ZIP_BYTES + 1)
        if len(payload) > MAX_ZIP_BYTES:
            raise ValueError("Artifact ZIP download exceeds cap")
        return payload


def import_run_metadata(db, gh, page_limit):
    seen = 0
    for page in range(1, page_limit + 1):
        data = gh.json(f"/runs?per_page=100&page={page}")
        arr = data.get("workflow_runs", [])
        for r in arr:
            db.execute("""
                INSERT INTO runs VALUES (?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(run_id) DO UPDATE SET
                    status=excluded.status,conclusion=excluded.conclusion,
                    updated_at=excluded.updated_at,
                    name=excluded.name,head_sha=excluded.head_sha
                """, (
                    r["id"], r.get("name"), r.get("path"), r.get("head_branch"),
                    r.get("head_sha"), r.get("created_at"), r.get("updated_at"),
                    r.get("status"), r.get("conclusion"), r.get("html_url"),
                    r.get("event"),
                ))
        seen += len(arr)
        if not arr or len(arr) < 100:
            break
        if page % 20 == 0:
            db.commit()
            emit("DRNAS_GLOBAL_RUN_SCAN", {"pages": page, "runs_seen": seen})
    return seen


def import_artifact_metadata(db, gh, page_limit, initial):
    # On a first full backfill, scan old pages. Subsequent runs refresh page 1
    # and continue any unfinished older page range. IDs guarantee idempotency.
    prior = int(get_meta(db, "artifact_next_page", "1"))
    if initial:
        pages = range(1, page_limit + 1)
    else:
        pages = [1, 2, 3] + list(range(max(4, prior), max(4, prior) + max(0, page_limit - 3)))
    seen = 0
    end = False
    for page in pages:
        data = gh.json(f"/artifacts?per_page=100&page={page}")
        arr = data.get("artifacts", [])
        for a in arr:
            parent = a.get("workflow_run") or {}
            db.execute("""
                INSERT INTO artifacts(
                  artifact_id,run_id,name,size_bytes,created_at,expired,
                  import_state,detail,last_attempt_at
                ) VALUES (?,?,?,?,?,?, 'pending',NULL,NULL)
                ON CONFLICT(artifact_id) DO UPDATE SET
                  expired=excluded.expired,name=excluded.name,
                  size_bytes=excluded.size_bytes
                """, (
                    a["id"], parent.get("id"), a.get("name"),
                    a.get("size_in_bytes"), a.get("created_at"),
                    int(bool(a.get("expired"))),
                ))
        seen += len(arr)
        if not arr or len(arr) < 100:
            end = True
            break
    if end:
        set_meta(db, "artifact_next_page", "1")
        set_meta(db, "artifact_full_scan_complete", "1")
    else:
        set_meta(db, "artifact_next_page", str(max(pages) + 1))
    return seen


def role_for_manifest(manifest):
    # Artifacts are untrusted experimental observations: never grant them
    # permission to influence training based on self-declared split labels.
    return "holdout" if isinstance(manifest, dict) else "unknown"


def import_report(db, artifact_id, run_id, path, obj):
    if not isinstance(obj, (dict, list)):
        return 0
    payload = json.dumps(obj, sort_keys=True, separators=(",", ":"))
    if len(payload) > MAX_MEMBER_BYTES:
        return 0
    db.execute("""
      INSERT OR IGNORE INTO reports VALUES (?,?,?,?,?,?)
      """, (artifact_id, path, run_id, sha256(payload.encode()),
            PurePosixPath(path).name, payload))
    return 1


def import_pair_rows(db, artifact_id, run_id, member_path, rows, manifest):
    info = {
        x.get("sha256"): x
        for x in manifest.get("originals", [])
        if isinstance(x, dict) and valid_sha(x.get("sha256"))
    }
    model_sha = manifest.get("frozen_logistic_sha256")
    guard_sha = manifest.get("frozen_risk_guard_sha256")
    cohort = manifest.get("cohort")
    role = role_for_manifest(manifest)
    count = 0
    for line in rows.splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if not isinstance(row, dict):
            continue
        source = row.get("sha256")
        arm = row.get("arm")
        rep = row.get("rep")
        if not valid_sha(source) or not isinstance(arm, str) or not arm or len(arm) > 96:
            continue
        if not isinstance(rep, int) or isinstance(rep, bool) or rep < 0 or rep > 100000:
            continue
        source = source.lower()
        meta = info.get(source, {})
        claimed = bool(row.get("verified") is True)
        status = str(row.get("status", "UNKNOWN"))[:48]
        par2 = safe_num(row.get("PAR2"))
        if par2 is None:
            par2 = safe_num(row.get("PAR2_verified_s"))
        family = str(row.get("family") or meta.get("family") or "")[:128]
        cert = str(meta.get("cert") or "NOT_INDEPENDENTLY_REVALIDATED")[:128]
        db.execute("""
          INSERT OR IGNORE INTO sources VALUES (?,?,?,?,?,?)
          """, (source, family, str(cohort or "")[:128], run_id, cert, UTC()))
        cur = db.execute("""
          INSERT OR IGNORE INTO observations VALUES (
            ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?
          )
          """, (
            artifact_id, run_id, source, arm, rep, family,
            str(cohort or "")[:128], status, int(claimed),
            par2, safe_num(row.get("solver_e2e_s")),
            safe_num(row.get("conflicts"), integer=True),
            safe_num(row.get("decisions"), integer=True),
            role, cert,
            model_sha if valid_sha(model_sha) else None,
            guard_sha if valid_sha(guard_sha) else None,
            str(row.get("source_id"))[:128], member_path,
          ))
        count += cur.rowcount
    return count


def import_zip(db, artifact_id, run_id, payload):
    reports = 0
    trial_rows = 0
    with zipfile.ZipFile(io.BytesIO(payload)) as z:
        content = {}
        for member in z.infolist():
            if member.is_dir() or member.file_size > MAX_MEMBER_BYTES:
                continue
            path = PurePosixPath(member.filename)
            if ".." in path.parts or path.is_absolute():
                continue
            name = path.name.lower()
            if (name in REPORT_NAMES or name == "trials.jsonl"):
                try:
                    content[str(path)] = z.read(member).decode("utf-8")
                except (UnicodeError, ValueError, RuntimeError):
                    continue
        manifests = {}
        for path, value in content.items():
            if PurePosixPath(path).name.lower() != "manifest.json":
                continue
            try:
                manifest = json.loads(value)
                if isinstance(manifest, dict):
                    manifests[str(PurePosixPath(path).parent)] = manifest
            except ValueError:
                continue
        for path, value in content.items():
            if path.endswith(".json") and PurePosixPath(path).name.lower() in REPORT_NAMES:
                try:
                    reports += import_report(db, artifact_id, run_id, path, json.loads(value))
                except ValueError:
                    pass
            if PurePosixPath(path).name.lower() != "trials.jsonl":
                continue
            parent = str(PurePosixPath(path).parent)
            manifest = manifests.get(parent)
            if manifest and isinstance(manifest.get("originals"), list):
                trial_rows += import_pair_rows(db, artifact_id, run_id, path, value, manifest)
    return reports, trial_rows


def ingest_artifacts(db, gh, budget):
    successes = failures = skipped = rows_imported = reports_imported = 0
    entries = db.execute("""
        SELECT artifact_id,run_id,name,size_bytes,expired
        FROM artifacts WHERE import_state='pending'
        ORDER BY created_at DESC,artifact_id DESC
    """).fetchall()
    for artifact_id, run_id, name, size, expired in entries:
        if expired:
            state, detail = "expired", "GitHub artifact expired"
        elif not ARTIFACT_HINTS.search(name or ""):
            state, detail = "unrelated", "Non-benchmark archive name"
        elif size is None or size > MAX_ZIP_BYTES:
            state, detail = "oversized", "ZIP exceeds 18 MiB safety cap"
        elif successes + failures >= budget:
            continue
        else:
            try:
                binary = gh.artifact_zip(artifact_id)
                reports, trials = import_zip(db, artifact_id, run_id, binary)
                state = "parsed" if reports or trials else "unsupported"
                detail = f"reports={reports},observations={trials}"
                reports_imported += reports
                rows_imported += trials
                successes += 1
            except (urllib.error.HTTPError, urllib.error.URLError, ValueError,
                    TimeoutError, OSError, zipfile.BadZipFile) as e:
                failures += 1
                state, detail = "retry", (type(e).__name__ + ": " + str(e))[:300]
            except Exception as e:
                failures += 1
                state, detail = "retry", ("Unexpected " + type(e).__name__ + ": " + str(e))[:300]
        db.execute("""
          UPDATE artifacts SET import_state=?,detail=?,last_attempt_at=?
          WHERE artifact_id=?
          """, (state, detail, UTC(), artifact_id))
        if state in ("expired", "oversized", "unrelated"):
            skipped += 1
        if (successes + failures) % 20 == 0 and (successes + failures) > 0:
            db.commit()
            emit("DRNAS_GLOBAL_IMPORT_PROGRESS", {
                "attempted": successes + failures, "trial_rows": rows_imported,
                "reports": reports_imported,
            })
    return dict(downloaded=successes, errors=failures, skipped=skipped,
                trial_rows=rows_imported, reports=reports_imported)


def get_meta(db, key, fallback=None):
    r = db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return r[0] if r else fallback


def set_meta(db, key, value):
    db.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (key, str(value)))


def import_legacy(db, archive, latest_path):
    if not archive.exists():
        return {"state": "not_available", "reason": "Original X47 archive not found"}
    binary = archive.read_bytes()
    digest = sha256(binary)
    if get_meta(db, "legacy_x47_archive_sha") == digest:
        return {"state": "unchanged", "source_sha": digest}
    with tempfile.TemporaryDirectory(prefix="drnas-legacy-") as td:
        destination = Path(td) / "legacy.sqlite"
        destination.write_bytes(gzip.decompress(binary))
        old = sqlite3.connect(f"file:{destination}?mode=ro", uri=True)
        experience_count = 0
        for source, proto, split, family, raw in old.execute(
            "SELECT sha,protocol,split,regime,payload FROM experiences"
        ):
            if not valid_sha(source) or split not in ("train", "validation"):
                continue
            try:
                item = json.loads(raw)
            except ValueError:
                continue
            meta = item.get("meta") if isinstance(item, dict) else None
            if not isinstance(meta, dict) or meta.get("split") != split:
                continue
            namespace = str(meta.get("namespace") or proto or "legacy-x47")
            db.execute("""
              INSERT OR IGNORE INTO legacy_experiences VALUES (?,?,?,?,?,?,?)
              """, (source.lower(), namespace, split, family, raw,
                    "43361933084", "X47_LONG_30K_original_learning_db"))
            experience_count += 1
        checkpoints = 0
        for ident, cycle, model, tune_cost, accepted in old.execute(
            "SELECT id,cycle,model,tune_cost,accepted FROM checkpoints"
        ):
            db.execute("""
              INSERT OR IGNORE INTO legacy_checkpoints VALUES (?,?,?,?,?,?)
              """, ("X47-LONG-30K-v1", ident, cycle, accepted, tune_cost, model))
            checkpoints += 1
        sealed = 0
        for ident, payload in old.execute("SELECT id,payload FROM sealed_tests"):
            db.execute("""
              INSERT OR IGNORE INTO sealed_reports VALUES (?,?,?)
              """, ("X47-LONG-30K-v1", ident, payload))
            sealed += 1
        old.close()
    if latest_path.exists():
        model_note = json.loads(latest_path.read_text())
        m = model_note.get("model", {})
        packed = json.dumps(m, sort_keys=True, separators=(",", ":"))
        # Existing completed holdout failed overall success despite tiny audit
        # progress: retain model but NEVER automatically deploy from ingestion.
        db.execute("""
          INSERT OR REPLACE INTO model_registry VALUES (?,?,?,?,?,?,?,?,?)
          """, (
            model_note.get("namespace", "X47-LONG-30K-v1"),
            model_note.get("run"), model_note.get("source_commit"),
            model_note.get("stage"), sha256(packed.encode()), packed,
            int(bool(m.get("deployment_allowed"))), "evidence_only",
            "Deployment requires future independent held-out validation; "
            "past 30K holdout did not pass overall performance success",
          ))
    set_meta(db, "legacy_x47_archive_sha", digest)
    return dict(state="imported", source_sha=digest,
                experiences=experience_count, checkpoints=checkpoints,
                sealed_reports=sealed)


def stats(db, sync):
    count = lambda query: db.execute(query).fetchone()[0]
    artifact_states = dict(db.execute(
        "SELECT import_state,COUNT(*) FROM artifacts GROUP BY import_state"
    ).fetchall())
    return {
        "protocol": DB_VERSION, "updated_at": UTC(),
        "github_repo": REPO,
        "runs_indexed": count("SELECT COUNT(*) FROM runs"),
        "artifacts_indexed": count("SELECT COUNT(*) FROM artifacts"),
        "artifact_states": artifact_states,
        "report_documents": count("SELECT COUNT(*) FROM reports"),
        "observation_rows": count("SELECT COUNT(*) FROM observations"),
        "independent_observation_sources": count(
            "SELECT COUNT(DISTINCT source_sha) FROM observations"
        ),
        "reported_verified_trials": count(
            "SELECT COUNT(*) FROM observations WHERE verified_claim=1"
        ),
        "legacy_train_sources": count(
            "SELECT COUNT(*) FROM legacy_experiences WHERE split='train'"
        ),
        "legacy_validation_sources": count(
            "SELECT COUNT(*) FROM legacy_experiences WHERE split='validation'"
        ),
        "eligible_training_sources": count("SELECT COUNT(*) FROM eligible_training"),
        "sealed_legacy_reports": count("SELECT COUNT(*) FROM sealed_reports"),
        "stored_model_versions": count("SELECT COUNT(*) FROM model_registry")
            + count("SELECT COUNT(*) FROM legacy_checkpoints"),
        "promoted_models": 0,
        "artifact_scan_complete": get_meta(db, "artifact_full_scan_complete", "0") == "1",
        "new_this_sync": sync,
        "safety": {
            "benchmark_artifacts": "evidence_only; never train automatically",
            "legacy_training": "only explicit original split=train and no holdout source overlap",
            "claim_verification": "workflow-reported claims, not an independent reproof",
            "promotion": "disabled until fresh locked validation clears acceptance criteria",
        },
    }


def store_database(db, raw_path, compressed_path):
    db.commit()
    db.close()
    compressed_path.parent.mkdir(parents=True, exist_ok=True)
    with raw_path.open("rb") as source, compressed_path.open("wb") as target:
        with gzip.GzipFile(fileobj=target, mode="wb", compresslevel=7, mtime=0) as sink:
            shutil.copyfileobj(source, sink)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--store", type=Path, required=True)
    p.add_argument("--summary", type=Path, required=True)
    p.add_argument("--legacy", type=Path, required=True)
    p.add_argument("--legacy-latest", type=Path, required=True)
    p.add_argument("--run-pages", type=int, default=100)
    p.add_argument("--artifact-pages", type=int, default=150)
    p.add_argument("--max-downloads", type=int, default=100)
    args = p.parse_args()
    args.store.parent.mkdir(parents=True, exist_ok=True)
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    if any(x < 1 for x in (args.run_pages, args.artifact_pages, args.max_downloads)):
        p.error("scan pages and download budget must be positive")
    with tempfile.TemporaryDirectory(prefix="drnas-global-") as temp:
        raw = Path(temp) / "global.sqlite"
        existed = args.store.exists()
        if existed:
            raw.write_bytes(gzip.decompress(args.store.read_bytes()))
        db = sqlite3.connect(raw)
        create_schema(db)
        gh = Github(os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN"))
        legacy = import_legacy(db, args.legacy, args.legacy_latest)
        seen_runs = import_run_metadata(db, gh, args.run_pages)
        seen_artifacts = import_artifact_metadata(db, gh, args.artifact_pages, not existed)
        db.commit()
        imported = ingest_artifacts(db, gh, args.max_downloads)
        summary = stats(db, {
            "run_records_scanned": seen_runs,
            "artifact_records_scanned": seen_artifacts,
            "legacy": legacy,
            "artifact_import": imported,
        })
        set_meta(db, "last_sync_utc", summary["updated_at"])
        args.summary.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
        # Keep status with the immutable raw evidence in the data-only branch.
        (args.store.parent / "latest.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n"
        )
        store_database(db, raw, args.store)
    emit("DRNAS_GLOBAL_MEMORY_SYNC", summary)


if __name__ == "__main__":
    main()
