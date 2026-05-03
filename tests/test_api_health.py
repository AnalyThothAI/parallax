from fastapi.testclient import TestClient

from gmgn_twitter_intel.api.app import _build_runtime, _readiness_payload, create_app
from gmgn_twitter_intel.settings import CollectorConfig, Settings


def test_healthz_and_readyz_return_status(tmp_path):
    settings = Settings(
        handles=("toly",),
        ws_token="secret",
    )
    settings.set_config_dir(tmp_path / "app-home")
    app = create_app(
        settings=settings,
        start_collector=False,
    )

    with TestClient(app) as client:
        health = client.get("/healthz")
        ready = client.get("/readyz")

    assert health.status_code == 200
    assert health.text == "ok\n"
    assert ready.status_code == 200
    assert ready.json()["collector"]["frames_received"] == 0
    assert ready.json()["store"].endswith("twitter_intel.sqlite3")
    assert ready.json()["db"]["write_probe"] is True
    assert ready.json()["enrichment"]["llm_configured"] is False
    assert ready.json()["enrichment"]["worker_running"] is False
    assert ready.json()["enrichment"]["job_counts"]["pending"] == 0
    assert "provider_status" not in ready.json()


def test_readiness_marks_started_collector_without_frames_unhealthy(tmp_path):
    class RunningTask:
        def done(self):
            return False

    settings = Settings(
        handles=("toly",),
        ws_token="secret",
        collector=CollectorConfig(stale_timeout=10),
    )
    settings.set_config_dir(tmp_path / "app-home")
    runtime = _build_runtime(settings, start_collector=False)
    runtime.start_collector = True
    runtime.collector_task = RunningTask()
    runtime.collector.status.started_at_ms = 1_000

    try:
        payload, status_code = _readiness_payload(runtime, now_ms=12_001)
    finally:
        runtime.evidence.close()
        runtime.read_evidence.close()

    assert status_code == 503
    assert payload["ok"] is False
    assert "no_upstream_frames" in payload["reasons"]
