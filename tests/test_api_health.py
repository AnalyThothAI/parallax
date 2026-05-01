from fastapi.testclient import TestClient

from gmgn_twitter_intel.api.app import create_app
from gmgn_twitter_intel.settings import Settings


def test_healthz_and_readyz_return_status(tmp_path, monkeypatch):
    monkeypatch.setenv("GMGN_TWITTER_HOME", str(tmp_path / "app-home"))
    app = create_app(
        settings=Settings(
            handles=("toly",),
            ws_token="secret",
        ),
        start_collector=False,
    )

    with TestClient(app) as client:
        health = client.get("/healthz")
        ready = client.get("/readyz")

    assert health.status_code == 200
    assert health.text == "ok\n"
    assert ready.status_code == 200
    assert ready.json()["collector"]["frames_received"] == 0
    assert "store_counts" not in ready.json()
    assert "entity_backlog" not in ready.json()
    assert "embedding_backlog" not in ready.json()
    assert ready.json()["provider_status"]["sentiment"] == "none"
