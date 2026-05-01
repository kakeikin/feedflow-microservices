from datetime import datetime, timezone


def compute_interest_match(video_tags: list[str], user_interests: list[dict]) -> float:
    """0.0–1.0: weighted fraction of video tags matched by user interest scores."""
    if not video_tags or not user_interests:
        return 0.0
    interest_map = {i["tag"]: i["score"] for i in user_interests}
    matched = sum(interest_map.get(tag, 0.0) for tag in video_tags)
    return matched / len(video_tags)


def compute_freshness(created_at: datetime) -> float:
    """0.0–1.0: linear decay — 1.0 when brand new, 0.0 at 7 days (168h) old."""
    now = datetime.now(timezone.utc)
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    age_hours = (now - created_at).total_seconds() / 3600
    return max(0.0, 1.0 - age_hours / 168.0)


def compute_engagement(likes: int, skips: int, max_net_engagement: int) -> float:
    """0.0–1.0: (likes - skips) normalized to the max net engagement in the candidate set."""
    net = likes - skips
    if net <= 0 or max_net_engagement == 0:
        return 0.0
    return min(1.0, net / max_net_engagement)


def compute_completion_quality(completion_rate: float) -> float:
    """0.0–1.0: video completion rate as reported by VideoStats."""
    return max(0.0, min(1.0, completion_rate))


def compute_final_score(
    interest_match: float,
    freshness: float,
    engagement: float,
    completion_quality: float,
) -> float:
    """Weighted combination: 0.45 interest + 0.20 freshness + 0.20 engagement + 0.15 completion."""
    return round(
        0.45 * interest_match
        + 0.20 * freshness
        + 0.20 * engagement
        + 0.15 * completion_quality,
        4,
    )
