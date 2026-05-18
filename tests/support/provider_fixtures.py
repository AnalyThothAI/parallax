from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PROVIDER_FRAMES = Path(__file__).resolve().parents[1] / "contract" / "provider_frames"


def load_provider_fixture(name: str) -> Any:
    path = PROVIDER_FRAMES / name
    return json.loads(path.read_text(encoding="utf-8"))
