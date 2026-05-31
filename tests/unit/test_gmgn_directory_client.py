from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from parallax.integrations.gmgn.directory_client import (
    GmgnDirectoryClient,
    GmgnDirectoryEntry,
    GmgnDirectoryError,
)

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures"


def _load(name: str) -> dict:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def test_client_parses_page_and_returns_next_token():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.url.path == "/vas/api/v1/twitter/user/search"
        assert request.url.params["limit"] == "50"
        assert request.url.params["handle"] == ""
        assert request.url.params.get_list("user_tags") == [
            "kol",
            "trader",
            "master",
            "politics",
            "media",
            "companies",
            "founder",
            "exchange",
            "celebrity",
            "binance_square",
            "other",
        ]
        assert "page_token" not in request.url.params
        return httpx.Response(200, json=_load("gmgn_directory_page1.json"))

    client = GmgnDirectoryClient(
        base_url="https://example.test",
        transport=httpx.MockTransport(handler),
    )
    try:
        page = client.fetch_page(page_token=None)
    finally:
        client.close()

    assert page.next_page_token == "Y3o6MTg1NDg="
    assert page.entries == [
        GmgnDirectoryEntry(
            handle="realdonaldtrump",
            gmgn_user_id="107780257626128497",
            user_tags=("politics",),
            platform_followers=19782,
        ),
        GmgnDirectoryEntry(
            handle="cz",
            gmgn_user_id="dxCeCLOM7uOFJKX8EnS3Kw",
            user_tags=("binance_square",),
            platform_followers=18548,
        ),
    ]
    assert len(requests) == 1


def test_client_passes_page_token_on_subsequent_request():
    seen: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.params.get("page_token"))
        return httpx.Response(200, json=_load("gmgn_directory_page2.json"))

    client = GmgnDirectoryClient(
        base_url="https://example.test",
        transport=httpx.MockTransport(handler),
    )
    try:
        page = client.fetch_page(page_token="Y3o6MTg1NDg=")
    finally:
        client.close()

    assert seen == ["Y3o6MTg1NDg="]
    assert page.next_page_token is None
    assert page.entries[0].handle == "elonmusk"
    assert page.entries[0].user_tags == ("founder", "kol")


def test_iter_pages_walks_until_empty_token_and_dedupes_by_handle():
    responses = iter(
        [
            _load("gmgn_directory_page1.json"),
            _load("gmgn_directory_page2.json"),
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=next(responses))

    client = GmgnDirectoryClient(
        base_url="https://example.test",
        transport=httpx.MockTransport(handler),
        sleep_between_pages_seconds=0,
    )
    try:
        entries = list(client.iter_entries(max_pages=10))
    finally:
        client.close()

    handles = [entry.handle for entry in entries]
    assert handles == ["realdonaldtrump", "cz", "elonmusk"]


def test_client_raises_on_non_zero_envelope_code():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"code": 401, "message": "auth required", "data": None})

    client = GmgnDirectoryClient(
        base_url="https://example.test",
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(GmgnDirectoryError, match="auth required"):
            client.fetch_page(page_token=None)
    finally:
        client.close()


def test_iter_entries_dedupes_repeated_handles_across_pages():
    pages = iter(
        [
            {
                "code": 0,
                "reason": "",
                "message": "",
                "data": {
                    "users": [
                        {
                            "handle": "cz",
                            "user_id": "X1",
                            "user_tags": ["kol"],
                            "platform": 2,
                            "followers": 100,
                            "followed": False,
                        },
                        {
                            "handle": "elonmusk",
                            "user_id": "Y1",
                            "user_tags": ["founder"],
                            "platform": 2,
                            "followers": 200,
                            "followed": False,
                        },
                    ],
                    "page_token": "p2",
                },
            },
            {
                "code": 0,
                "reason": "",
                "message": "",
                "data": {
                    "users": [
                        {
                            "handle": "cz",
                            "user_id": "X2",
                            "user_tags": ["kol"],
                            "platform": 2,
                            "followers": 99,
                            "followed": False,
                        },
                        {
                            "handle": "",
                            "user_id": "blank",
                            "user_tags": [],
                            "platform": 2,
                            "followers": 0,
                            "followed": False,
                        },
                        {
                            "handle": "vitalik",
                            "user_id": "V1",
                            "user_tags": ["founder"],
                            "platform": 2,
                            "followers": 50,
                            "followed": False,
                        },
                    ],
                    "page_token": "",
                },
            },
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=next(pages))

    client = GmgnDirectoryClient(
        base_url="https://example.test",
        transport=httpx.MockTransport(handler),
        sleep_between_pages_seconds=0,
    )
    try:
        entries = list(client.iter_entries(max_pages=10))
    finally:
        client.close()

    assert [entry.handle for entry in entries] == ["cz", "elonmusk", "vitalik"]
    assert entries[0].platform_followers == 100  # first observation wins; second cz row is skipped
