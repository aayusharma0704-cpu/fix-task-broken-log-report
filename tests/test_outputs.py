import json
from pathlib import Path


def test_report_exists():
    """The agent produced a report file."""
    assert Path("/app/report.json").exists(), "no report.json found"


def test_report_valid_json():
    """The report file is valid JSON."""
    content = Path("/app/report.json").read_text()
    assert content.strip(), "report.json is empty"
    json.loads(content)


def test_report_values():
    """The report contains the correct summary values."""
    data = json.loads(Path("/app/report.json").read_text())
    assert data.get("total_requests") == 6, f"expected 6 total_requests, got {data.get('total_requests')}"
    assert data.get("unique_ips") == 3, f"expected 3 unique_ips, got {data.get('unique_ips')}"
    assert data.get("top_path") == "/index.html", f"expected top_path '/index.html', got {data.get('top_path')}"