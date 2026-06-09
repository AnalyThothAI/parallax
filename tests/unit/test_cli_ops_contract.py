from __future__ import annotations

from parallax.app.surfaces.cli.commands import ops


def test_narrative_intel_rebuild_helpers_are_removed() -> None:
    assert not hasattr(ops, "_run_narrative_intel_rebuild")
    assert not hasattr(ops, "_cleanup_narrative_backlog")
    assert not hasattr(ops, "MentionSemanticsWorker")
    assert not hasattr(ops, "TokenDiscussionDigestWorker")
