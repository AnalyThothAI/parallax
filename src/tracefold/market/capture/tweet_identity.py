from __future__ import annotations

from tracefold.market.capture.twitter_event import TwitterEvent


def logical_dedup_key(event: TwitterEvent) -> str:
    if event.tweet_id:
        return f"tweet:{event.tweet_id}"
    return f"event:{event.event_id}"


def canonical_tweet_url(event: TwitterEvent) -> str | None:
    if not event.tweet_id or not event.author.handle:
        return None
    return f"https://x.com/{event.author.handle.lstrip('@')}/status/{event.tweet_id}"
