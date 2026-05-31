from __future__ import annotations

from pathlib import Path

TOKEN_IMAGE_MAGIC_POLICY_RETRY_MIGRATION = Path(
    "src/parallax/platform/db/alembic/versions/20260531_0134_token_image_magic_policy_retry.py"
)


def test_token_image_magic_policy_retry_migration_requeues_prior_media_type_mismatches() -> None:
    text = TOKEN_IMAGE_MAGIC_POLICY_RETRY_MIGRATION.read_text()

    for statement in (
        'revision = "20260531_0134"',
        'down_revision = "20260531_0133"',
        "UPDATE token_image_assets",
        "status = 'error'",
        "media_type = NULL",
        "public_url = NULL",
        "last_error = 'image_magic_media_type_policy_repaired: prior_media_type_mismatch'",
        "next_refresh_at_ms = 0",
        "WHERE status = 'unsupported'",
        "last_error = 'unsupported_image_bytes: media_type_mismatch'",
        "ANALYZE token_image_assets",
    ):
        assert statement in text
