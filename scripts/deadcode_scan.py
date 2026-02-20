#!/usr/bin/env python3
"""Run dead-code checks and write reproducible report artifacts."""

from __future__ import annotations

import argparse
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TARGETS = ("function_app.py", "src", "tests")
EXCLUDES = (
    ".venv/",
    ".python_packages/",
    "node_modules/",
    "ui/.next/",
    "playwright-report/",
    "test-results/",
    "artifacts/",
    "archive/",
    "_archive/",
    "tmp/",
    "logs/",
)
IGNORE_DECORATORS = (
    "@app.route",
    "@app.function_name",
)


@dataclass
class CheckResult:
    name: str
    command: list[str]
    output: str
    returncode: int
    findings: int
    missing_tool: bool = False


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def _count_ruff_findings(output: str) -> int:
    return sum(1 for line in output.splitlines() if re.match(r"^[^:]+:\d+:\d+:", line))


def _count_vulture_findings(output: str) -> int:
    return sum(1 for line in output.splitlines() if re.search(r":\d+:\s+unused ", line))


def _format_cmd(command: Iterable[str]) -> str:
    return " ".join(shlex.quote(p) for p in command)


def _run_ruff(targets: list[str]) -> CheckResult:
    command = [sys.executable, "-m", "ruff", "check", *targets, "--select", "F401,F841", "--output-format", "concise"]
    proc = _run(command)
    combined = (proc.stdout + proc.stderr).strip()
    missing = "No module named ruff" in combined
    return CheckResult(
        name="ruff",
        command=command,
        output=combined,
        returncode=proc.returncode,
        findings=0 if missing else _count_ruff_findings(combined),
        missing_tool=missing,
    )


def _run_vulture(targets: list[str], min_confidence: int) -> CheckResult:
    command = [
        sys.executable,
        "-m",
        "vulture",
        *targets,
        "--exclude",
        ",".join(EXCLUDES),
        "--ignore-decorators",
        ",".join(IGNORE_DECORATORS),
        "--min-confidence",
        str(min_confidence),
        "--sort-by-size",
    ]
    proc = _run(command)
    combined = (proc.stdout + proc.stderr).strip()
    missing = "No module named vulture" in combined
    return CheckResult(
        name="vulture",
        command=command,
        output=combined,
        returncode=proc.returncode,
        findings=0 if missing else _count_vulture_findings(combined),
        missing_tool=missing,
    )


def _write_reports(out_dir: Path, results: list[CheckResult]) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%SZ")

    for result in results:
        raw_file = out_dir / f"{result.name}-{ts}.txt"
        raw_file.write_text(result.output + "\n", encoding="utf-8")

    md_file = out_dir / f"deadcode-report-{ts}.md"
    lines = [
        "# Dead Code Scan Report",
        "",
        f"- Timestamp (UTC): `{ts}`",
        f"- Repository root: `{ROOT}`",
        "",
        "| check | findings | return_code | tool_status |",
        "|---|---:|---:|---|",
    ]
    for result in results:
        status = "missing" if result.missing_tool else "ok"
        lines.append(f"| {result.name} | {result.findings} | {result.returncode} | {status} |")
    lines.extend(["", "## Commands"])
    lines.extend([f"- `{_format_cmd(result.command)}`" for result in results])
    lines.extend(["", "## Notes", "- `ruff` reports unused imports and unused local variables.", "- `vulture` reports likely unused functions/methods/branches and should be reviewed conservatively before removal."])
    md_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return md_file


def main() -> int:
    parser = argparse.ArgumentParser(description="Run dead-code checks and write reports.")
    parser.add_argument("--out-dir", default="tmp/deadcode", help="Output directory for report artifacts.")
    parser.add_argument(
        "--targets",
        nargs="+",
        default=list(DEFAULT_TARGETS),
        help="Paths to scan.",
    )
    parser.add_argument(
        "--min-confidence",
        type=int,
        default=80,
        help="Vulture confidence threshold (0-100).",
    )
    parser.add_argument(
        "--fail-on-findings",
        action="store_true",
        help="Exit with non-zero code if any finding or missing tool is detected.",
    )
    args = parser.parse_args()

    results = [
        _run_ruff(args.targets),
        _run_vulture(args.targets, args.min_confidence),
    ]
    report_path = _write_reports(Path(args.out_dir), results)

    print(f"Dead-code report written: {report_path}")
    for result in results:
        state = "MISSING TOOL" if result.missing_tool else "OK"
        print(f"[{result.name}] findings={result.findings} return_code={result.returncode} status={state}")
        if result.output:
            print(f"[{result.name}] output:\n{result.output}\n")

    has_findings = any(r.findings > 0 for r in results)
    has_missing_tool = any(r.missing_tool for r in results)
    if args.fail_on_findings and (has_findings or has_missing_tool):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
