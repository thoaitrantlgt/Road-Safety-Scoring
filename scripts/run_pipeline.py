from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


STEPS = [
    ("alignment", ["scripts/alignment.py", "--config", "configs/scope.json"]),
    ("features", ["scripts/features.py", "--config", "configs/features.json"]),
    ("scoring", ["scripts/scoring.py", "--config", "configs/scoring.json"]),
    ("visualization", ["scripts/visualization.py", "--config", "configs/visualization.json"]),
    ("deliverables", ["scripts/package_outputs.py", "--config", "configs/package.json"]),
]


def run_step(name: str, command: list[str]) -> None:
    print(f"\n== {name} ==")
    subprocess.run([sys.executable, *command], cwd=Path.cwd(), check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the full road safety scoring pipeline.")
    parser.add_argument(
        "--from-step",
        choices=[name for name, _ in STEPS],
        default="alignment",
        help="Start from a specific step.",
    )
    args = parser.parse_args()
    start_index = [name for name, _ in STEPS].index(args.from_step)
    for name, command in STEPS[start_index:]:
        run_step(name, command)


if __name__ == "__main__":
    main()
