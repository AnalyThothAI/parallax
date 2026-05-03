from fastapi.testclient import TestClient

from gmgn_twitter_intel.api.app import create_app
from gmgn_twitter_intel.settings import Settings


def test_frontend_dist_is_served_without_interfering_with_api(tmp_path):
    settings = Settings(handles=("toly",), ws_token="secret")
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
        asset = client.get("/assets/app.js")
        favicon = client.get("/favicon.svg")
        health = client.get("/healthz")

    assert home.status_code == 200
    assert "text/html" in home.headers["content-type"]
    assert app_route.status_code == 200
    assert asset.status_code == 200
    assert "window.__cockpit" in asset.text
    assert favicon.status_code == 200
    assert favicon.headers["content-type"].startswith("image/svg+xml")
    assert health.text == "ok\n"
