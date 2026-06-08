from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ACTIVE_DIRS = (
    ROOT / "docs" / "superpowers" / "specs" / "active",
    ROOT / "docs" / "superpowers" / "plans" / "active",
)
ALLOWLIST = {
    "2026-06-07-news-market-wide-notification-hard-cut-cn.md",
    "2026-06-07-news-market-wide-notification-hard-cut-plan-cn.md",
}
FORBIDDEN = (
    "analysis_admission_status == admitted",
    "analysis_admission_status = 'admitted'",
    "analysis_not_admitted",
    "non_crypto_subject",
    "no_crypto_native_evidence",
    "provider_evidence_only",
    "not delete `analysis_admission_*`",
    "不删除 `analysis_admission_*`",
    "不能 brief/notify",
)


def test_active_news_specs_do_not_define_legacy_crypto_gate() -> None:
    offenders: list[str] = []
    for directory in ACTIVE_DIRS:
        for path in sorted(directory.glob("*news*.md")):
            if path.name in ALLOWLIST:
                continue
            text = path.read_text(encoding="utf-8")
            offenders.extend(f"{path.relative_to(ROOT)} contains {token}" for token in FORBIDDEN if token in text)
    assert offenders == []
