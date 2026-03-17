"""pytest configuration and fixtures for FoBiS.py tests."""

import json
from pathlib import Path

_PUBLIC = Path(__file__).parent.parent / "docs" / "public"


def pytest_sessionfinish(session, exitstatus):
    """After the test run: write coverage.json and coverage-badge.json to docs/public/."""
    _PUBLIC.mkdir(parents=True, exist_ok=True)
    try:
        import coverage as coverage_lib

        cov = coverage_lib.Coverage()
        cov.load()
        cov.json_report(outfile=str(_PUBLIC / "coverage.json"), pretty_print=True)
        data = json.loads((_PUBLIC / "coverage.json").read_text())
        pct = float(data["totals"]["percent_covered_display"])
    except Exception:
        return

    if pct >= 90:
        color = "brightgreen"
    elif pct >= 75:
        color = "green"
    elif pct >= 60:
        color = "yellow"
    elif pct >= 40:
        color = "orange"
    else:
        color = "red"

    badge = {
        "schemaVersion": 1,
        "label": "coverage",
        "message": f"{pct:.0f}%",
        "color": color,
    }
    (_PUBLIC / "coverage-badge.json").write_text(json.dumps(badge, indent=2))
