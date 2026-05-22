from fastapi import FastAPI
from fastapi.testclient import TestClient

from gmgn_twitter_intel.app.runtime.app import _mount_frontend, create_app
from gmgn_twitter_intel.platform.config.settings import Settings
from tests.postgres_test_utils import postgres_settings_storage, prepare_postgres_database


def test_frontend_dist_is_served_without_interfering_with_api(tmp_path):
    prepare_postgres_database()
    settings = Settings(handles=("toly",), ws_token="secret", storage=postgres_settings_storage())
    settings.set_config_dir(tmp_path / "app-home")
    dist = tmp_path / "dist"
    assets = dist / "assets"
    assets.mkdir(parents=True)
    (dist / "index.html").write_text(
        '<!doctype html><html><head><script type="module" src="/assets/app.js"></script></head></html>',
        encoding="utf-8",
    )
    (dist / "favicon.svg").write_text("<svg></svg>", encoding="utf-8")
    (assets / "app.js").write_text("window.__cockpit = true;", encoding="utf-8")

    app = create_app(settings=settings, start_collector=False, frontend_dist=dist)

    with TestClient(app) as client:
        home = client.get("/")
        app_route = client.get("/app")
        token_route = client.get("/token/CexToken/cex_token%3AZEC")
        signal_lab_route = client.get("/signal-lab")
        news_route = client.get("/news")
        macro_route = client.get("/macro")
        watchlist_route = client.get("/watchlist?handle=toly")
        asset = client.get("/assets/app.js")
        favicon = client.get("/favicon.svg")
        health = client.get("/healthz")
        missing_api = client.get("/api/not-a-route")

    assert home.status_code == 200
    assert "text/html" in home.headers["content-type"]
    assert home.headers["cache-control"] == "no-cache, max-age=0, must-revalidate"
    assert app_route.status_code == 200
    assert token_route.status_code == 200
    assert "text/html" in token_route.headers["content-type"]
    assert signal_lab_route.status_code == 200
    assert "text/html" in signal_lab_route.headers["content-type"]
    assert news_route.status_code == 200
    assert "text/html" in news_route.headers["content-type"]
    assert macro_route.status_code == 200
    assert "text/html" in macro_route.headers["content-type"]
    assert watchlist_route.status_code == 200
    assert "text/html" in watchlist_route.headers["content-type"]
    assert asset.status_code == 200
    assert "window.__cockpit" in asset.text
    assert asset.headers["cache-control"] == "no-cache, max-age=0, must-revalidate"
    assert favicon.status_code == 200
    assert favicon.headers["content-type"].startswith("image/svg+xml")
    assert favicon.headers["cache-control"] == "no-cache, max-age=0, must-revalidate"
    assert health.text == "ok\n"
    assert missing_api.status_code == 404


def test_frontend_dist_serves_browser_routes_for_spa(tmp_path):
    dist = tmp_path / "dist"
    assets = dist / "assets"
    assets.mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><html><body>cockpit</body></html>", encoding="utf-8")
    (assets / "app.js").write_text("window.__cockpit = true;", encoding="utf-8")

    app = FastAPI()
    _mount_frontend(app, frontend_dist=dist)

    with TestClient(app) as client:
        token_route = client.get("/token/CexToken/cex_token%3AZEC")
        signal_lab_route = client.get("/signal-lab")
        news_route = client.get("/news")
        news_detail_route = client.get("/news/story/story_123")
        macro_route = client.get("/macro")
        watchlist_route = client.get("/watchlist?handle=toly")
        missing_api = client.get("/api/not-a-route")

    assert token_route.status_code == 200
    assert "text/html" in token_route.headers["content-type"]
    assert token_route.headers["cache-control"] == "no-cache, max-age=0, must-revalidate"
    assert "cockpit" in token_route.text
    assert signal_lab_route.status_code == 200
    assert "text/html" in signal_lab_route.headers["content-type"]
    assert news_route.status_code == 200
    assert "text/html" in news_route.headers["content-type"]
    assert news_detail_route.status_code == 200
    assert "text/html" in news_detail_route.headers["content-type"]
    assert macro_route.status_code == 200
    assert "text/html" in macro_route.headers["content-type"]
    assert watchlist_route.status_code == 200
    assert "text/html" in watchlist_route.headers["content-type"]
    assert missing_api.status_code == 404
