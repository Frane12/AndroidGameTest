"""Native capacity guard vs exhaustive scheduling and independent certificates.

Example:
  python test_native_math.py --binary ../../../build/drnas-pcmax \
    --checker ../check_capacity.py --header ../../../src/pcmax_capacity.hpp
All generated files stay in --output (a temporary directory by default).
"""
import argparse
from contextlib import redirect_stdout
import hashlib
import importlib.util
import io
from itertools import product
import json
from pathlib import Path
import subprocess
import shutil
import tempfile
import time

import make_fixtures


def load_checker(path):
    spec = importlib.util.spec_from_file_location("independent_capacity_checker", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.check


def run(args, output):
    started = time.perf_counter()
    header_hash = hashlib.sha256(args.header.read_bytes()).hexdigest()
    binary_hash = hashlib.sha256(args.binary.read_bytes()).hexdigest() if args.binary else None
    output.mkdir(parents=True, exist_ok=True)
    make_fixtures.ROOT = output
    with redirect_stdout(io.StringIO()):
        make_fixtures.main()
    fixture_rows = json.loads((output / "fixtures.json").read_text())["cases"]
    gap_source = Path(__file__).with_name("fractional-gap.cnf")
    gap_target = output / "fixtures" / gap_source.name
    shutil.copyfile(gap_source, gap_target)
    gap_clauses = [tuple(map(int, line.split()[:-1]))
                   for line in gap_target.read_text().splitlines() if line and line[0] not in "cp"]
    gap_groups = [[j * 3 + m + 1 for m in range(3)] for j in range(6)]
    gap_truth = make_fixtures.oracle(54, gap_clauses, gap_groups)
    assert gap_truth["status"] == "UNSAT"
    gap_patterns = [bits for bits in product((0, 1), repeat=6)
                    if sum(bits) <= 1 or (sum(bits) == 2 and (not any(bits[:3]) or not any(bits[3:])))]
    fixture_rows.append(dict(file=str(gap_target), groups=gap_groups, kind="fractional-gap",
                             oracle=gap_truth, machine_count=3, accepted_patterns=gap_patterns))
    harness = output / "native_guard_harness"
    command = ["g++", "-std=c++17", "-O2", "-Wall", "-Wextra", "-Wpedantic",
               "-I", str(args.header.resolve().parent),
               str(Path(__file__).with_name("native_guard_harness.cpp")), "-o", str(harness)]
    compiled = subprocess.run(command, capture_output=True, text=True, timeout=60)
    assert compiled.returncode == 0, compiled.stderr
    assert not compiled.stderr, compiled.stderr
    check = load_checker(args.checker.resolve())
    checks, certificate_checks, supported, native_cli_cases = 0, 0, 0, 0
    rows = []
    for fixture in fixture_rows:
        path = Path(fixture["file"])
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        completed = subprocess.run([str(harness), str(path), digest],
                                   capture_output=True, text=True, timeout=10)
        assert completed.returncode == 0, (path, completed.stdout, completed.stderr)
        native = json.loads(completed.stdout)
        assert not (native["verified"] and fixture["oracle"]["status"] == "SAT"), fixture
        if native["verified"]:
            assert native["certificate"] is not None
            check(raw, native["certificate"])
            certificate_checks += 1
            path.with_suffix(".native-certificate.json").write_text(json.dumps(native["certificate"]) + "\n")
        else:
            assert native["certificate"] is None
        oracle = native["oracle"]
        if fixture["kind"] == "missing-prerequisite":
            assert not native["verified"] and "unsupported" in oracle, (fixture, native)
        elif "unsupported" not in oracle:
            supported += 1
            original_group_by_literal = {literal: j for j, group in enumerate(fixture["groups"])
                                         for literal in group}
            mapping = []
            for group in oracle["groups"]:
                jobs = {original_group_by_literal[literal] for literal in group}
                assert len(jobs) == 1
                mapping.append(jobs.pop())
            assert sorted(mapping) == list(range(len(fixture["groups"])))
            if fixture["kind"] == "fractional-gap":
                assert not native["verified"] and native["reason"] == "no_capacity_contradiction"
                accepted_by_machine = [fixture["accepted_patterns"]] * fixture["machine_count"]
            else:
                capacities = fixture["capacity"] if isinstance(fixture["capacity"], list) else [fixture["capacity"]] * fixture["machine_count"]
                accepted_by_machine = [[bits for bits in product((0, 1), repeat=len(mapping))
                                        if sum(p * bit for p, bit in zip(fixture["durations"], bits)) <= capacity]
                                       for capacity in capacities]
            if not all(oracle["eligible"]):
                assert oracle["positive_uncovered_rejected"]
            for sample in oracle["samples"]:
                weights = sample["weights"]
                assert all(eligible or weights[g] == 0 for g, eligible in enumerate(oracle["eligible"]))
                assert len(sample["maxima"]) == fixture["machine_count"]
                assert sample["exact_verifier_accepts"] == (sum(weights) > sum(sample["maxima"]))
                assert sample["forged_capacity_rejected"]
                for maximum, pattern, accepted in zip(sample["maxima"], sample["patterns"], accepted_by_machine):
                    expected = max(sum(weights[g] * bits[job] for g, job in enumerate(mapping))
                                   for bits in accepted)
                    assert maximum == expected, (fixture, sample, expected)
                    assert len(pattern) == len(set(pattern))
                    assert sum(weights[g] for g in pattern) == maximum
                    chosen_jobs = {mapping[g] for g in pattern}
                    assert tuple(int(j in chosen_jobs) for j in range(len(mapping))) in accepted
                    checks += 1
        record = dict(file=path.name, truth=fixture["oracle"]["status"],
                      kind=fixture["kind"], guard_verified=native["verified"],
                      guard_reason=native["reason"], direct_oracle=oracle)
        if args.binary:
            certificate = path.with_suffix(".cli-certificate.json")
            command = [str(args.binary.resolve()), str(path), "--pcmax-only",
                       "--pcmax-budget-ms", "1000", "--time", "3",
                       "--pcmax-certificate", str(certificate)]
            cli = subprocess.run(command, capture_output=True, text=True, timeout=10)
            assert cli.returncode in (0, 20), (path, cli.returncode, cli.stdout, cli.stderr)
            telemetry = [json.loads(line[len("c PCMAX_CAPACITY "):])
                         for line in cli.stdout.splitlines() if line.startswith("c PCMAX_CAPACITY ")]
            assert len(telemetry) == 1, (path, cli.stdout)
            verified = telemetry[0]["verified"]
            if verified:
                assert fixture["oracle"]["status"] == "UNSAT"
                assert "s UNSATISFIABLE" in cli.stdout and certificate.is_file()
                check(raw, json.loads(certificate.read_text()))
                certificate_checks += 1
            else:
                assert "s UNKNOWN" in cli.stdout and not certificate.exists(), (path, cli.stdout)
            assert verified == native["verified"], (path, cli.stdout, native["reason"])
            native_cli_cases += 1
            record["cli"] = telemetry[0]
        rows.append(record)
    budget_checks = []
    first = fixture_rows[0]
    for budget in ("0", "-1", "nan", "inf", "1e300"):
        completed = subprocess.run([str(harness), first["file"], first["source_sha256"], budget],
                                   capture_output=True, text=True, timeout=10)
        assert completed.returncode == 0, (budget, completed.stderr)
        tested = json.loads(completed.stdout)
        assert not tested["verified"] and tested["reason"] == "invalid_or_exhausted_budget"
        budget_checks.append(budget)
    assert hashlib.sha256(args.header.read_bytes()).hexdigest() == header_hash, "header changed during audit"
    if args.binary:
        assert hashlib.sha256(args.binary.read_bytes()).hexdigest() == binary_hash, "binary changed during audit"
    result = dict(cases=len(rows), supported_pattern_cases=supported,
                  direct_exhaustive_maximum_checks=checks,
                  independently_verified_certificates=certificate_checks,
                  native_cli_cases=native_cli_cases,
                  sat_cases=sum(r["truth"] == "SAT" for r in rows),
                  unsat_cases=sum(r["truth"] == "UNSAT" for r in rows),
                  false_unsat=0, header_sha256=header_hash, binary_sha256=binary_hash,
                  invalid_budget_cases_rejected=budget_checks,
                  elapsed_s=time.perf_counter() - started, rows=rows)
    (output / "native-math-results.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "rows"}, indent=2))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path)
    parser.add_argument("--checker", type=Path, required=True)
    parser.add_argument("--header", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.output:
        run(args, args.output.resolve())
    else:
        with tempfile.TemporaryDirectory(prefix="pcmax-native-math-") as directory:
            run(args, Path(directory))


if __name__ == "__main__":
    main()
