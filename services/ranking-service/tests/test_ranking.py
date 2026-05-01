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
    score = compute_freshness(created_at)
    assert score > 0.99


def test_freshness_old_video():
    from app.ranking import compute_freshness
    created_at = datetime.now(timezone.utc) - timedelta(days=8)
    score = compute_freshness(created_at)
    assert score == 0.0


def test_freshness_midpoint():
    from app.ranking import compute_freshness
    created_at = datetime.now(timezone.utc) - timedelta(hours=84)  # half of 168h
    score = compute_freshness(created_at)
    assert abs(score - 0.5) < 0.02


def test_popularity_normalized():
    from app.ranking import compute_popularity
    assert abs(compute_popularity(50, 100) - 0.5) < 0.001


def test_popularity_all_zero():
    from app.ranking import compute_popularity
    assert compute_popularity(0, 0) == 0.0


def test_popularity_max():
    from app.ranking import compute_popularity
    assert compute_popularity(100, 100) == 1.0


def test_final_score_all_ones():
    from app.ranking import compute_final_score
    score = compute_final_score(1.0, 1.0, 1.0)
    assert abs(score - 1.0) < 0.001


def test_final_score_interest_only():
    from app.ranking import compute_final_score
    score = compute_final_score(1.0, 0.0, 0.0)
    assert abs(score - 0.60) < 0.001


def test_final_score_freshness_only():
    from app.ranking import compute_final_score
    score = compute_final_score(0.0, 1.0, 0.0)
    assert abs(score - 0.25) < 0.001


def test_final_score_popularity_only():
    from app.ranking import compute_final_score
    score = compute_final_score(0.0, 0.0, 1.0)
    assert abs(score - 0.15) < 0.001
