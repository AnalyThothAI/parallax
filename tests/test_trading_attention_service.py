from psycopg.types.json import Jsonb

from gmgn_twitter_intel.pipeline.ingest_service import IngestService
from gmgn_twitter_intel.retrieval.trading_attention_service import TradingAttentionService, _social_is_grounded
from gmgn_twitter_intel.storage.enrichment_repository import EnrichmentRepository
from gmgn_twitter_intel.storage.entity_repository import EntityRepository
from gmgn_twitter_intel.storage.evidence_repository import EvidenceRepository
from gmgn_twitter_intel.storage.signal_repository import SignalRepository
from gmgn_twitter_intel.storage.token_repository import TokenRepository
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import reset_postgres_schema as migrate
from tests.test_postgres_repositories import make_event, make_token_event

TOKEN_ADDRESS = "0xd0667d0618dc9b6d2a0a55f428b47c64bcf00416"


def test_social_grounding_rejects_unbacked_extraction_semantics():
    event = {"content": {"text": "I received CZ's book from Amazon and read it twice."}}
    hallucinated = {
        "subject": "SEC",
        "anchor_terms": [{"term": "SEC", "role": "regulation", "evidence": "SEC"}],
        "token_candidates": [],
    }
    grounded = {
        "subject": "CZ book",
        "anchor_terms": [{"term": "CZ", "role": "person", "evidence": "CZ's book"}],
        "token_candidates": [],
    }

    assert _social_is_grounded(event=event, social=hallucinated) is False
    assert _social_is_grounded(event=event, social=grounded) is True


def test_trading_attention_classifies_direct_token_event(tmp_path):
    conn, evidence, signals, tokens, ingest = _runtime(tmp_path)
    try:
        event = make_token_event(
            "event-direct",
            symbol="DOG",
            address=TOKEN_ADDRESS,
            received_at_ms=10_000,
            author_handle="cz_binance",
        )
        ingest.ingest_event(event, is_watched=True)
        _social_event(
            conn,
            event_id="event-direct",
            extraction_id="extract-direct",
            author_handle="cz_binance",
            received_at_ms=10_000,
            event_type="product_mention",
            subject="DOG launch",
            direction_hint="attention_positive",
            anchor_terms=[{"term": "$DOG", "role": "asset", "evidence": "$DOG"}],
            summary_zh="CZ 提到 DOG，形成直接代币注意力。",
        )

        data = TradingAttentionService(evidence=evidence, signals=signals, tokens=tokens).pulse(
            window="1h",
            scope="all",
            limit=10,
            now_ms=11_000,
        )
    finally:
        conn.close()

    assert data["summary"]["direct_token"] == 1
    item = data["items"][0]
    assert item["kind"] == "direct_token"
    assert item["priority"] in {"hot", "watch"}
    assert item["linked_tokens"][0]["token_id"].startswith("token:eth:")
    assert item["linked_tokens"][0]["symbol"] == "DOG"
    assert item["linked_topics"][0]["label"] == "$DOG"


def test_trading_attention_keeps_keyword_as_topic_without_tokenizing(tmp_path):
    conn, evidence, signals, tokens, _ = _runtime(tmp_path)
    try:
        event = make_event(
            "event-grok",
            author_handle="elonmusk",
            text="Grok is getting spicy",
            received_at_ms=10_000,
        )
        evidence.insert_event(event, is_watched=True)
        _social_event(
            conn,
            event_id="event-grok",
            extraction_id="extract-grok",
            author_handle="elonmusk",
            received_at_ms=10_000,
            event_type="meme_phrase_seed",
            subject="Grok",
            direction_hint="attention_positive",
            anchor_terms=[{"term": "Grok", "role": "keyword", "evidence": "Grok"}],
            summary_zh="Musk 提到 Grok，形成 AI 相关关键词热度。",
        )

        data = TradingAttentionService(evidence=evidence, signals=signals, tokens=tokens).pulse(
            window="1h",
            scope="all",
            limit=10,
            now_ms=11_000,
        )
    finally:
        conn.close()

    item = data["items"][0]
    assert item["kind"] == "topic_heat"
    assert item["linked_tokens"] == []
    assert item["linked_topics"][0]["label"] == "Grok"
    assert item["title"] == "Grok"


def test_trading_attention_query_treats_comma_terms_as_alternatives(tmp_path):
    conn, evidence, signals, tokens, _ = _runtime(tmp_path)
    try:
        grok = make_event(
            "event-grok",
            author_handle="elonmusk",
            text="Grok is getting spicy",
            received_at_ms=10_000,
        )
        build = make_event(
            "event-build",
            author_handle="toly",
            text="Solana builders keep shipping",
            received_at_ms=10_100,
        )
        evidence.insert_event(grok, is_watched=True)
        evidence.insert_event(build, is_watched=True)
        _social_event(
            conn,
            event_id="event-grok",
            extraction_id="extract-grok",
            author_handle="elonmusk",
            received_at_ms=10_000,
            event_type="meme_phrase_seed",
            subject="Grok",
            direction_hint="attention_positive",
            anchor_terms=[{"term": "Grok", "role": "keyword", "evidence": "Grok"}],
            summary_zh="Musk 提到 Grok，形成 AI 相关关键词热度。",
        )
        _social_event(
            conn,
            event_id="event-build",
            extraction_id="extract-build",
            author_handle="toly",
            received_at_ms=10_100,
            event_type="ecosystem_boost",
            subject="Solana builders",
            direction_hint="attention_positive",
            anchor_terms=[{"term": "Solana builders", "role": "ecosystem", "evidence": "Solana builders"}],
            summary_zh="Solana builders 继续发货。",
        )

        data = TradingAttentionService(evidence=evidence, signals=signals, tokens=tokens).pulse(
            window="1h",
            scope="all",
            limit=10,
            q="grok, build",
            now_ms=11_000,
        )
    finally:
        conn.close()

    assert {item["event"]["event_id"] for item in data["items"]} == {"event-grok", "event-build"}


def test_trading_attention_classifies_market_structure_and_risk(tmp_path):
    conn, evidence, signals, tokens, _ = _runtime(tmp_path)
    try:
        structure = make_event(
            "event-structure",
            author_handle="traderpow",
            text="Liquidity is moving to majors before the next leg.",
            received_at_ms=10_000,
        )
        risk = make_event(
            "event-risk",
            author_handle="cz_binance",
            text="Exchange risk is elevated today.",
            received_at_ms=10_100,
        )
        evidence.insert_event(structure, is_watched=True)
        evidence.insert_event(risk, is_watched=True)
        _social_event(
            conn,
            event_id="event-structure",
            extraction_id="extract-structure",
            author_handle="traderpow",
            received_at_ms=10_000,
            event_type="market_structure_comment",
            subject="liquidity rotation",
            direction_hint="neutral",
            anchor_terms=[
                {
                    "term": "liquidity rotation",
                    "role": "market_structure",
                    "evidence": "Liquidity is moving",
                }
            ],
            summary_zh="流动性向主流资产移动。",
        )
        _social_event(
            conn,
            event_id="event-risk",
            extraction_id="extract-risk",
            author_handle="cz_binance",
            received_at_ms=10_100,
            event_type="exchange_risk",
            subject="exchange risk",
            direction_hint="risk_negative",
            anchor_terms=[{"term": "Exchange risk", "role": "risk", "evidence": "Exchange risk"}],
            summary_zh="交易所风险升高。",
        )

        data = TradingAttentionService(evidence=evidence, signals=signals, tokens=tokens).pulse(
            window="1h",
            scope="all",
            limit=10,
            now_ms=11_000,
        )
    finally:
        conn.close()

    by_event = {item["event"]["event_id"]: item for item in data["items"]}
    assert by_event["event-structure"]["kind"] == "market_structure"
    assert by_event["event-risk"]["kind"] == "risk_alert"
    assert data["summary"]["market_structure"] == 1
    assert data["summary"]["risk_alert"] == 1


def _runtime(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
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
    )
    return conn, evidence, signals, tokens, ingest


def _social_event(
    conn,
    *,
    event_id: str,
    extraction_id: str,
    author_handle: str,
    received_at_ms: int,
    event_type: str,
    subject: str,
    direction_hint: str,
    anchor_terms: list[dict],
    summary_zh: str,
) -> None:
    conn.execute(
        """
        INSERT INTO social_event_extractions(
          extraction_id, event_id, run_id, author_handle, received_at_ms, schema_version, model_version,
          event_type, source_action, subject, direction_hint, attention_mechanism, impact_hint,
          semantic_novelty_hint, confidence, is_signal_event, anchor_terms_json, token_candidates_json,
          semantic_risks_json, summary_zh, raw_response_json, created_at_ms, updated_at_ms
        )
        VALUES (
          %s, %s, NULL, %s, %s, 'social-event-v2', 'test-model',
          %s, 'posted', %s, %s, 'watched_account_attention', 0.74,
          0.68, 0.88, true, %s, '[]'::jsonb,
          '[]'::jsonb, %s, '{}'::jsonb, %s, %s
        )
        """,
        (
            extraction_id,
            event_id,
            author_handle,
            received_at_ms,
            event_type,
            subject,
            direction_hint,
            Jsonb(anchor_terms),
            summary_zh,
            received_at_ms,
            received_at_ms,
        ),
    )
    conn.commit()
