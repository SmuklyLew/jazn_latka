"""Job reports preserve the distinction between no error and an error code."""
import json

from tools.jazn_run_studio.core import Job


def test_job_report_encodes_absent_error_as_json_null() -> None:
    job = Job("probe:gateway", state="succeeded", returncode=0)
    report = json.loads(json.dumps(job.snapshot()))
    assert report["error"] is None
    assert report["state"] == "succeeded"


def test_job_report_preserves_failure_code() -> None:
    job = Job("probe:gateway", state="failed", error="service_not_ready")
    report = json.loads(json.dumps(job.snapshot()))
    assert report["error"] == "service_not_ready"
    assert report["state"] == "failed"
