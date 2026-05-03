import io
import json
import tempfile
import time
import unittest
from pathlib import Path
from threading import RLock
from unittest.mock import patch

import yaml

from gmgn_twitter_intel.cli import main
from gmgn_twitter_intel.models import Author, Content, Source, TwitterEvent
from gmgn_twitter_intel.pipeline.ingest_service import IngestService
from gmgn_twitter_intel.pipeline.llm_enrichment import EnrichmentResult, NarrativeItem, TokenCandidate
from gmgn_twitter_intel.pipeline.narrative_token_linker import NarrativeTokenLinker
from gmgn_twitter_intel.storage.enrichment_repository import EnrichmentRepository
from gmgn_twitter_intel.storage.entity_repository import EntityRepository
from gmgn_twitter_intel.storage.evidence_repository import EvidenceRepository
from gmgn_twitter_intel.storage.signal_repository import SignalRepository
from gmgn_twitter_intel.storage.sqlite_client import connect_sqlite
from gmgn_twitter_intel.storage.sqlite_schema import migrate
from gmgn_twitter_intel.storage.token_repository import TokenRepository

PEPE = "0x6982508145454ce325ddbe47a25d4ec3d2311933"


def make_event(
    event_id: str,
    received_at_ms: int | None = None,
    text: str = f"$PEPE Solana XDP mainnet base stablecoin {PEPE}",
) -> TwitterEvent:
    received_at_ms = received_at_ms if received_at_ms is not None else int(time.time() * 1000)
    return TwitterEvent(
        event_id=event_id,
        source=Source(
            provider="gmgn",
            transport="direct_ws",
            coverage="public_stream",
            channel="twitter_monitor_basic",
        ),
        action="tweet",
        original_action=None,
        tweet_id=event_id,
        internal_id=event_id,
        timestamp=received_at_ms // 1000,
        received_at_ms=received_at_ms,
        author=Author(handle="toly", name="toly", avatar=None, followers=100, tags=[]),
        content=Content(text=text, media=[]),
        reference=None,
        unfollow_target=None,
        avatar_change=None,
        bio_change=None,
        matched_handles=["toly"],
        raw=None,
    )


def seed_sqlite(db_path: Path) -> None:
    conn = connect_sqlite(db_path, read_only=False)
    try:
        migrate(conn)
        evidence = EvidenceRepository(conn)
        entities = EntityRepository(conn)
        signals = SignalRepository(conn)
        enrichment = EnrichmentRepository(conn)
        tokens = TokenRepository(conn)
        ingest = IngestService(
            evidence=evidence,
            entities=entities,
            signals=signals,
            enrichment=enrichment,
            tokens=tokens,
            write_lock=RLock(),
        )
        ingest.ingest_event(make_event("event-1"), is_watched=True)
        job = enrichment.claim_next_job(now_ms=int(time.time() * 1000))
        assert job is not None
        event = evidence.events_by_ids(["event-1"])["event-1"]
        enrichment.complete_job(
            job=job,
            event=event,
            result=EnrichmentResult(
                summary="Watched account discussed Solana XDP and PEPE.",
                token_candidates=[
                    TokenCandidate(
                        symbol="SOL",
                        project_name="Solana",
                        chain=None,
                        address=None,
                        evidence="Solana XDP",
                        confidence=0.9,
                    ),
                ],
                narratives=[
                    NarrativeItem(
                        label="solana_scaling",
                        description="Solana scaling and XDP readiness",
                        seed_family="solana_scaling",
                        trigger_terms=["Solana", "XDP"],
                        market_interpretation="Market may look for Solana scaling tokens.",
                        evidence="Solana XDP",
                        confidence=0.86,
                    ),
                ],
                stance="informational",
                intent="technical_commentary",
                confidence=0.9,
                raw_response={"ok": True},
            ),
            provider="test",
            model="test-model",
            request={"event_id": "event-1"},
        )
        seed = enrichment.upsert_narrative_seed(
            event_id="event-1",
            narrative_label="solana_scaling",
            seed_family="solana_scaling",
            seed_terms=["solana", "xdp"],
            market_interpretation="Market may look for Solana scaling tokens.",
            stance="informational",
            intent="technical_commentary",
            confidence=0.86,
            source_weight=0.6,
            novelty_status="new_global",
            received_at_ms=event["received_at_ms"],
            author_handle="toly",
            evidence="Solana XDP",
            summary="Watched account discussed Solana XDP and PEPE.",
        )
        NarrativeTokenLinker(
            evidence=evidence,
            signals=signals,
            enrichment=enrichment,
            tokens=tokens,
        ).link_seed(seed=seed, window="1h")
    finally:
        conn.close()


def write_runtime_config(home: Path, *, db_path: Path, ws_token: str | None = None, llm: bool = False) -> Path:
    app_home = home / ".gmgn-twitter-intel"
    app_home.mkdir(parents=True, exist_ok=True)
    payload = {
        "handles": ["toly", "traderpow"],
        "storage": {"sqlite_path": str(db_path)},
    }
    if ws_token is not None:
        payload["ws_token"] = ws_token
    if llm:
        payload["llm"] = {"provider": "openai", "api_key": "sk-test", "model": "gpt-test"}
    path = app_home / "config.yaml"
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


class CliTests(unittest.TestCase):
    def test_config_prints_effective_runtime_settings(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            db_path = home / ".gmgn-twitter-intel" / "twitter_intel.sqlite3"
            write_runtime_config(home, db_path=db_path, ws_token="secret", llm=True)
            stdout = io.StringIO()
            with patch.dict("os.environ", {"HOME": str(home)}, clear=False):
                exit_code = main(["config"], stdout=stdout)

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["handles"], ["toly", "traderpow"])
        self.assertEqual(payload["data"]["handle_count"], 2)
        self.assertTrue(payload["data"]["api"]["ws_token_configured"])
        self.assertTrue(payload["data"]["enrichment"]["llm_configured"])
        self.assertEqual(payload["data"]["enrichment"]["model"], "gpt-test")
        self.assertEqual(payload["data"]["enrichment"]["provider"], "openai")
        self.assertTrue(payload["data"]["store"]["sqlite_path"].endswith("twitter_intel.sqlite3"))
        self.assertNotIn("embed" + "ding_dim", payload["data"]["store"])

    def test_recent_search_token_flow_narratives_and_alerts_use_sqlite_runtime_store(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            db_path = home / ".gmgn-twitter-intel" / "twitter_intel.sqlite3"
            write_runtime_config(home, db_path=db_path)
            seed_sqlite(db_path)
            conn = connect_sqlite(db_path, read_only=False)
            try:
                seed_id = EnrichmentRepository(conn).narrative_seeds(
                    window_ms=86_400_000,
                    limit=1,
                )[0]["seed_id"]
            finally:
                conn.close()
            stdout = io.StringIO()
            with patch.dict("os.environ", {"HOME": str(home)}, clear=False):
                recent_code = main(["recent", "--limit", "5"], stdout=stdout)
                search_code = main(["search", "--symbol", "PEPE", "--limit", "5"], stdout=stdout)
                token_flow_code = main(["token-flow", "--window", "5m", "--limit", "5"], stdout=stdout)
                narrative_flow_code = main(["narrative-flow", "--window", "1h", "--limit", "5"], stdout=stdout)
                alerts_code = main(["account-alerts", "--window", "24h", "--limit", "5"], stdout=stdout)
                narratives_code = main(["account-narratives", "--window", "24h", "--limit", "5"], stdout=stdout)
                jobs_code = main(["enrichment-jobs", "--limit", "5"], stdout=stdout)
                seeds_code = main(["narrative-seeds", "--window", "24h", "--limit", "5"], stdout=stdout)
                token_links_code = main(
                    ["narrative-token-flow", "--seed-id", seed_id, "--window", "1h", "--limit", "5"],
                    stdout=stdout,
                )
                frontier_code = main(["attention-frontier", "--window", "1h", "--limit", "5"], stdout=stdout)

        lines = [json.loads(line) for line in stdout.getvalue().splitlines()]
        self.assertEqual(
            [
                recent_code,
                search_code,
                token_flow_code,
                narrative_flow_code,
                alerts_code,
                narratives_code,
                jobs_code,
                seeds_code,
                token_links_code,
                frontier_code,
            ],
            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        )
        self.assertEqual(lines[0]["data"]["events"][0]["event_id"], "event-1")
        self.assertEqual(lines[1]["data"]["items"][0]["event"]["event_id"], "event-1")
        self.assertEqual(lines[2]["data"]["items"][0]["flow"]["mentions"], 1)
        self.assertEqual(lines[2]["data"]["items"][0]["signal"]["decision"], "discard")
        self.assertEqual(lines[3]["data"]["items"][0]["narrative_label"], "solana_scaling")
        self.assertEqual(
            {item["alert_type"] for item in lines[4]["data"]["items"]},
            {"account_token"},
        )
        self.assertEqual(lines[5]["data"]["items"][0]["narrative_label"], "solana_scaling")
        self.assertEqual(lines[6]["data"]["counts"]["done"], 1)
        self.assertEqual(lines[7]["data"]["items"][0]["seed"]["seed_id"], seed_id)
        self.assertEqual(lines[7]["data"]["items"][0]["seed"]["narrative_label"], "solana_scaling")
        self.assertEqual(lines[8]["data"]["seed"]["seed_id"], seed_id)
        self.assertGreaterEqual(len(lines[8]["data"]["links"]), 1)
        self.assertEqual(lines[9]["data"]["items"][0]["seed"]["narrative_label"], "solana_scaling")

    def test_obsolete_runtime_commands_are_not_registered(self):
        parser_help = main(["embed"], stdout=io.StringIO())

        self.assertEqual(parser_help, 2)

    def test_unsupported_narrative_link_windows_are_not_registered(self):
        self.assertEqual(main(["narrative-token-flow", "--seed-id", "seed", "--window", "1m"], stdout=io.StringIO()), 2)
        self.assertEqual(main(["attention-frontier", "--window", "1m"], stdout=io.StringIO()), 2)

    def test_ops_rebuild_windows_reconstructs_materialized_signal_windows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            db_path = home / ".gmgn-twitter-intel" / "twitter_intel.sqlite3"
            write_runtime_config(home, db_path=db_path)
            seed_sqlite(db_path)
            conn = connect_sqlite(db_path, read_only=False)
            try:
                conn.execute("DELETE FROM token_windows")
                conn.commit()
            finally:
                conn.close()

            stdout = io.StringIO()
            with patch.dict("os.environ", {"HOME": str(home)}, clear=False):
                rebuild_code = main(["ops", "rebuild-windows", "--window", "5m"], stdout=stdout)
                flow_code = main(["token-flow", "--window", "5m", "--limit", "5"], stdout=stdout)

        lines = [json.loads(line) for line in stdout.getvalue().splitlines()]
        self.assertEqual([rebuild_code, flow_code], [0, 0])
        self.assertNotIn("backfill", lines[0]["data"])
        self.assertGreater(lines[0]["data"]["rebuilt"], 0)
        self.assertEqual(lines[1]["data"]["items"][0]["flow"]["mentions"], 1)

    def test_ops_rebuild_narrative_links_reconstructs_seed_links(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            db_path = home / ".gmgn-twitter-intel" / "twitter_intel.sqlite3"
            write_runtime_config(home, db_path=db_path)
            seed_sqlite(db_path)
            conn = connect_sqlite(db_path, read_only=False)
            try:
                conn.execute("DELETE FROM narrative_token_links")
                conn.commit()
            finally:
                conn.close()

            stdout = io.StringIO()
            with patch.dict("os.environ", {"HOME": str(home)}, clear=False):
                rebuild_code = main(["ops", "rebuild-narrative-links", "--window", "1h"], stdout=stdout)
                frontier_code = main(["attention-frontier", "--window", "1h", "--limit", "5"], stdout=stdout)

        lines = [json.loads(line) for line in stdout.getvalue().splitlines()]
        self.assertEqual([rebuild_code, frontier_code], [0, 0])
        self.assertEqual(lines[0]["data"]["seeds_scanned"], 1)
        self.assertGreaterEqual(lines[0]["data"]["links_upserted"], 1)
        self.assertEqual(lines[1]["data"]["items"][0]["seed"]["narrative_label"], "solana_scaling")

def test_recent_defaults_to_runtime_sqlite_store_without_ws_token(tmp_path, monkeypatch):
    app_home = tmp_path / ".gmgn-twitter-intel"
    db_path = app_home / "twitter_intel.sqlite3"
    write_runtime_config(tmp_path, db_path=db_path)
    seed_sqlite(db_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    stdout = io.StringIO()

    exit_code = main(["recent", "--limit", "5"], stdout=stdout)

    payload = json.loads(stdout.getvalue())
    assert exit_code == 0
    assert payload["data"]["events"][0]["event_id"] == "event-1"


def test_init_creates_runtime_config(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    stdout = io.StringIO()

    exit_code = main(["init"], stdout=stdout)

    payload = json.loads(stdout.getvalue())
    assert exit_code == 0
    assert payload["data"]["created"] is True
    assert (tmp_path / ".gmgn-twitter-intel" / "config.yaml").is_file()


if __name__ == "__main__":
    unittest.main()
