from fastapi.testclient import TestClient

from gmgn_twitter_cli.api.app import create_app
from gmgn_twitter_cli.settings import Settings


def test_healthz_and_readyz_return_status(tmp_path):
    app = create_app(
        settings=Settings(
            MONITOR_HANDLES="toly",
            WS_TOKEN="secret",
            EVENT_DB_PATH=str(tmp_path / "events.sqlite3"),
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
