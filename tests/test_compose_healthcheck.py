from pathlib import Path


def test_container_healthcheck_uses_liveness_endpoint():
    compose_yaml = Path("compose.yaml").read_text()

    assert "http://127.0.0.1:8765/healthz" in compose_yaml
    assert "http://127.0.0.1:8765/readyz" not in compose_yaml
