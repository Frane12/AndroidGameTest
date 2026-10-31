"""Compare the normal CLI's decision and witness to exhaustive truth tables."""
import itertools
import random
import subprocess
import sys
import tempfile
from pathlib import Path


def check(exe):
    rng = random.Random(990012)
    cases = [(0, []), (0, [[]]), (5, [[1, 1], [-3, -3]]),
             (4, [[1, 3], [-1, -3], [4], [-4]]),
             (3, [[1, 2, 3], [-1, -2, -3]]),
             (5, [[1], [-1, -1, 2], [-2, -1, 3], [-3]]),
             (5, [[-1], [1, 1, -2], [2, 1, -3], [3]])]
    for route in range(4):
        for _ in range(60):
            n = rng.randint(2, 8)
            clauses = []
            for _ in range(rng.randrange(1, 30)):
                width = rng.randint(1, 2 if route == 2 else 5)
                c = [-rng.randint(1, n) for _ in range(width)]
                if route < 2:
                    if rng.randrange(2):
                        c[0] = -c[0]
                    if route == 1:
                        c = [-v for v in c]
                else:
                    c = [v if rng.randrange(2) else -v for v in c]
                clauses.append(c)
            cases.append((n, clauses))
    routes = set()
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "case.cnf"
        for n, clauses in cases:
            path.write_text(f"p cnf {n} {len(clauses)}\n" +
                            "".join(" ".join(map(str, c)) + " 0\n" for c in clauses))
            oracle = any(all(any(bits[abs(v) - 1] == (v > 0) for v in c) for c in clauses)
                         for bits in itertools.product((False, True), repeat=n))
            result = subprocess.run([exe, str(path)], capture_output=True, text=True, timeout=5)
            assert result.returncode == (10 if oracle else 20), (n, clauses, result.stderr)
            lines = result.stdout.splitlines()
            route, = [l.split()[2] for l in lines if l.startswith("c route ")]
            routes.add(route)
            if oracle:
                model, = [[int(x) for x in l.split()[1:]] for l in lines if l.startswith("v ")]
                assert model[-1] == 0 and sorted(abs(v) for v in model[:-1]) == list(range(1, n + 1))
                true_lits = set(model[:-1])
                assert all(any(v in true_lits for v in c) for c in clauses)
        path.write_text("p cnf 2 1\n3 0\n")
        assert subprocess.run([exe, str(path)], capture_output=True).returncode == 1
    assert routes == {"horn", "dual-horn", "2sat", "single96"}, routes
    print(f"PASS all {len(cases)} truth-table checks, full SAT models, and invalid input rejection")


if __name__ == "__main__":
    check(sys.argv[1])
