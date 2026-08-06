"""Runs a rendered suite against a live target and collects structured results.

The executor shells out to pytest rather than importing and running tests
in-process. Two reasons, both about Phase 4: it will run the same suite N times
and compare, and a fresh process per run means no state leaks between runs to
be mistaken for flakiness. It also keeps the tool honest about the boundary —
specforge never imports the service under test, so it needs none of the
service's dependencies.
"""
import json
import os
import subprocess
import sys
import tempfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class TestResult:
    test_id: str
    outcome: str  # passed | failed | skipped
    duration: float
    longrepr: str | None = None

    @property
    def failed(self) -> bool:
        return self.outcome == "failed"


@dataclass
class RunResult:
    """One execution of the whole suite."""

    results: list[TestResult] = field(default_factory=list)
    exit_code: int = 0
    stdout: str = ""

    @property
    def counts(self) -> dict[str, int]:
        return dict(Counter(r.outcome for r in self.results))

    @property
    def failures(self) -> list[TestResult]:
        return [r for r in self.results if r.failed]

    @property
    def total(self) -> int:
        return len(self.results)


def run_suite(
    generated_dir: Path,
    base_url: str,
    *,
    quiet: bool = True,
) -> RunResult:
    """Execute the rendered suite and return per-test outcomes.

    A non-zero exit code is normal here — a failing generated test is a finding
    to triage, not an error in the executor.
    """
    generated_dir = Path(generated_dir)
    if not (generated_dir / "test_suite.py").is_file():
        raise FileNotFoundError(f"no rendered suite in {generated_dir} (run `render` first)")

    with tempfile.TemporaryDirectory() as tmp:
        results_path = Path(tmp) / "results.jsonl"
        env_extra = {
            "SPECFORGE_BASE_URL": base_url,
            "SPECFORGE_RESULTS": str(results_path),
        }
        # Passing the directory explicitly means `testpaths` from any enclosing
        # pyproject.toml is ignored, so the generated suite is collected on its
        # own terms wherever it lives.
        cmd = [
            sys.executable,
            "-m",
            "pytest",
            str(generated_dir),
            "-p",
            "no:cacheprovider",
            "-q" if quiet else "-v",
        ]

        proc = subprocess.run(
            cmd,
            env={**os.environ, **env_extra},
            capture_output=True,
            text=True,
            check=False,
        )

        results: list[TestResult] = []
        if results_path.is_file():
            for line in results_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                raw = json.loads(line)
                results.append(
                    TestResult(
                        test_id=raw["test_id"],
                        outcome=raw["outcome"],
                        duration=raw["duration"],
                        longrepr=raw.get("longrepr"),
                    )
                )

    return RunResult(
        results=sorted(results, key=lambda r: r.test_id),
        exit_code=proc.returncode,
        stdout=proc.stdout + proc.stderr,
    )
