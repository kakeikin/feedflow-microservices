import pytest
from app.mapping import EVENT_DELTA_MAP, EventDelta


def test_watch_delta():
    d = EVENT_DELTA_MAP["watch"]
    assert d.views_delta == 0
    assert d.likes_delta == 0
    assert d.skips_delta == 0
    assert d.use_completion_rate is False
    assert d.interest_delta == pytest.approx(0.02)


def test_like_delta():
    d = EVENT_DELTA_MAP["like"]
    assert d.views_delta == 0
    assert d.likes_delta == 1
    assert d.skips_delta == 0
    assert d.use_completion_rate is False
    assert d.interest_delta == pytest.approx(0.10)


def test_skip_delta():
    d = EVENT_DELTA_MAP["skip"]
    assert d.views_delta == 0
    assert d.likes_delta == 0
    assert d.skips_delta == 1
    assert d.use_completion_rate is False
    assert d.interest_delta == pytest.approx(-0.08)


def test_complete_delta():
    d = EVENT_DELTA_MAP["complete"]
    assert d.views_delta == 1
    assert d.likes_delta == 0
    assert d.skips_delta == 0
    assert d.use_completion_rate is True
    assert d.interest_delta == pytest.approx(0.06)


def test_share_delta():
    d = EVENT_DELTA_MAP["share"]
    assert d.views_delta == 0
    assert d.likes_delta == 0
    assert d.skips_delta == 0
    assert d.use_completion_rate is False
    assert d.interest_delta == pytest.approx(0.08)


def test_comment_delta():
    d = EVENT_DELTA_MAP["comment"]
    assert d.views_delta == 0
    assert d.likes_delta == 0
    assert d.skips_delta == 0
    assert d.use_completion_rate is False
    assert d.interest_delta == pytest.approx(0.04)


def test_all_six_event_types_present():
    assert set(EVENT_DELTA_MAP.keys()) == {"watch", "like", "skip", "complete", "share", "comment"}
