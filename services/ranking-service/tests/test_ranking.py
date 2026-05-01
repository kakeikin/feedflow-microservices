from datetime import datetime, timezone, timedelta
import pytest


def test_interest_match_full_match():
    from app.ranking import compute_interest_match
    tags = ["ai", "backend"]
    interests = [{"tag": "ai", "score": 1.0}, {"tag": "backend", "score": 0.8}]
    score = compute_interest_match(tags, interests)
    assert abs(score - (1.0 + 0.8) / 2) < 0.001


def test_interest_match_partial():
    from app.ranking import compute_interest_match
    tags = ["ai", "sports"]
    interests = [{"tag": "ai", "score": 1.0}]
    score = compute_interest_match(tags, interests)
    assert abs(score - 0.5) < 0.001


def test_interest_match_no_interests():
    from app.ranking import compute_interest_match
    assert compute_interest_match(["ai"], []) == 0.0


def test_interest_match_no_tags():
    from app.ranking import compute_interest_match
    assert compute_interest_match([], [{"tag": "ai", "score": 1.0}]) == 0.0


def test_freshness_very_new_video():
    from app.ranking import compute_freshness
    created_at = datetime.now(timezone.utc) - timedelta(minutes=30)
    assert compute_freshness(created_at) > 0.99


def test_freshness_old_video():
    from app.ranking import compute_freshness
    created_at = datetime.now(timezone.utc) - timedelta(days=8)
    assert compute_freshness(created_at) == 0.0


def test_freshness_midpoint():
    from app.ranking import compute_freshness
    created_at = datetime.now(timezone.utc) - timedelta(hours=84)
    assert abs(compute_freshness(created_at) - 0.5) < 0.02


def test_engagement_net_positive():
    from app.ranking import compute_engagement
    assert abs(compute_engagement(likes=9, skips=1, max_net_engagement=10) - 0.8) < 0.001


def test_engagement_skips_exceed_likes():
    from app.ranking import compute_engagement
    assert compute_engagement(likes=1, skips=5, max_net_engagement=10) == 0.0


def test_engagement_zero_max():
    from app.ranking import compute_engagement
    assert compute_engagement(likes=0, skips=0, max_net_engagement=0) == 0.0


def test_engagement_at_max():
    from app.ranking import compute_engagement
    assert compute_engagement(likes=10, skips=0, max_net_engagement=10) == pytest.approx(1.0)


def test_engagement_equal_likes_and_skips():
    from app.ranking import compute_engagement
    assert compute_engagement(likes=5, skips=5, max_net_engagement=10) == 0.0


def test_completion_quality_passthrough():
    from app.ranking import compute_completion_quality
    assert compute_completion_quality(0.75) == pytest.approx(0.75)


def test_completion_quality_zero():
    from app.ranking import compute_completion_quality
    assert compute_completion_quality(0.0) == 0.0


def test_completion_quality_one():
    from app.ranking import compute_completion_quality
    assert compute_completion_quality(1.0) == pytest.approx(1.0)


def test_final_score_all_ones():
    from app.ranking import compute_final_score
    assert abs(compute_final_score(1.0, 1.0, 1.0, 1.0) - 1.0) < 0.001


def test_final_score_interest_only():
    from app.ranking import compute_final_score
    assert abs(compute_final_score(1.0, 0.0, 0.0, 0.0) - 0.45) < 0.001


def test_final_score_freshness_only():
    from app.ranking import compute_final_score
    assert abs(compute_final_score(0.0, 1.0, 0.0, 0.0) - 0.20) < 0.001


def test_final_score_engagement_only():
    from app.ranking import compute_final_score
    assert abs(compute_final_score(0.0, 0.0, 1.0, 0.0) - 0.20) < 0.001


def test_final_score_completion_only():
    from app.ranking import compute_final_score
    assert abs(compute_final_score(0.0, 0.0, 0.0, 1.0) - 0.15) < 0.001
