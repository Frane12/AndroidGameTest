"""Three known 2026 checks, kept separate from the generated prospective test."""
import os
from pathlib import Path
import random
import sys
import tempfile

from benchmark import run
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "drnas-sat-v7-8"))
from official_shortlong_select import download_and_features

CASES = (
    ("ee44c3f464238366729bf2cb16eb412a", "SAT", "d4dfdc97e6b6ee325628cb8ea1a35a3fe03c3e3f07a2ef5683a78b0baa1826d3"),
    ("2b35377a7b95f24449a3b607b61fff05", "SAT", "aa490f53e57c5119ac846f54dd2567d200824610ecdc92cae99098c5b0e5c1d4"),
    ("0be1e12a8e7282d1a4e389bb90f6dbc7", "UNSAT", "d63fa30fbe7003f7a2eff5939ab29c6064819d818115b630f57228cc86eedce1"),
)


def main():
    exe = str(Path(sys.argv[1]).resolve())
    os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    rows = ["| 2026 case | Repeat | Mode | Route | Status | Wall s (cap 15) |",
            "|---|---:|---|---|---|---:|"]
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "case.cnf"
        for case, label, digest in CASES:
            info = download_and_features(case, path)
            assert info["sha256"] == digest
            for rep in range(2):
                modes = ["auto", "single96"]
                random.Random(f"99/{case}/{rep}").shuffle(modes)
                for mode in modes:
                    status, value, route = run(exe, path, mode, 15)
                    assert status in (label, "TIMEOUT"), (case, mode, status)
                    elapsed = ">15" if status == "TIMEOUT" else f"{value:.6f}"
                    rows.append(f"| {case[:12]} | {rep + 1} | {mode} | {route} | {status} | {elapsed} |")
    summary = "\n".join(rows)
    print(summary)
    Path("official.md").write_text(summary + "\n")


if __name__ == "__main__":
    main()
