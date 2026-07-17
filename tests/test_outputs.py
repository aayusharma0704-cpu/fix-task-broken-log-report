"""Verifier for the stitched-access-log report task.

The deliverable is a program at /app/process_log.py that reads /app/access.log
and writes /app/report.json. The verifier re-runs that program unchanged against
the shipped sample and against many freshly generated held-out logs, and grades
each report by exact equality against an independent ground truth.

The ground truth is produced by gen_logs.py from the STRUCTURED truth of every
request (canonical client, true UTC instant, true byte size) before the request
is serialized, so it shares no decode path with the solution and cannot inherit
a parsing bug. Held-out logs are generated here at verify time with fixed seeds;
nothing about the expected answer ships in the task image.
"""

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gen_logs  # noqa: E402

PROGRAM = Path("/app/process_log.py")
LOG = Path("/app/access.log")
REPORT = Path("/app/report.json")

# Capture the shipped sample log before any test overwrites /app/access.log.
_SHIPPED_LOG = LOG.read_text() if LOG.exists() else None

HELDOUT_SEEDS = list(range(12))


def _run_on(log_text):
    """Install log_text as /app/access.log, run the solver, return its report."""
    LOG.write_text(log_text)
    if REPORT.exists():
        REPORT.unlink()
    subprocess.run(["python3", str(PROGRAM)], check=True, timeout=60, cwd="/app")
    return json.loads(REPORT.read_text())


def test_program_exists():
    """The agent produced the log-processing program."""
    assert PROGRAM.exists(), "no /app/process_log.py found"


def test_shipped_sample_unmodified():
    """The shipped sample log matches the generator (guards fixture drift)."""
    expected_log, _ = gen_logs.make_sample()
    assert _SHIPPED_LOG == expected_log, "shipped access.log drifted from generator"


def test_sample_report_correct():
    """The solver produces the exact report for the shipped sample log."""
    sample_log, expected = gen_logs.make_sample()
    got = _run_on(sample_log)
    assert got == expected, f"sample report wrong:\n got={got}\n exp={expected}"


def test_generalizes_to_heldout_logs():
    """The same program is correct on many unseen logs from the same platform."""
    failures = []
    for seed in HELDOUT_SEEDS:
        log, expected = gen_logs.make_export(seed)
        got = _run_on(log)
        if got != expected:
            failures.append((seed, got, expected))
    assert not failures, (
        f"{len(failures)}/{len(HELDOUT_SEEDS)} held-out logs wrong; "
        f"first: seed={failures[0][0]} got={failures[0][1]} "
        f"exp={failures[0][2]}"
    )
