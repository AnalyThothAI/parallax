from __future__ import annotations

from gmgn_twitter_intel.domains.narrative_intel.repositories.narrative_admission_dirty_target_repository import (
    _NarrativeDirtyTargetRepository,
)


class DiscussionDigestDirtyTargetRepository(_NarrativeDirtyTargetRepository):
    table_name = "discussion_digest_dirty_targets"
    error_label = "discussion digest dirty target"
