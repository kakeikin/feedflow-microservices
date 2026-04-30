import pytest
from pydantic import ValidationError


def test_user_create_valid():
    from app.schemas import UserCreate
    user = UserCreate(email="test@example.com", display_name="Test")
    assert user.email == "test@example.com"
    assert user.display_name == "Test"


def test_user_create_missing_email():
    from app.schemas import UserCreate
    with pytest.raises(ValidationError):
        UserCreate(display_name="Test")


def test_interest_create_valid():
    from app.schemas import InterestCreate
    interest = InterestCreate(tag="ai", score=0.9)
    assert interest.tag == "ai"
    assert interest.score == 0.9


def test_interest_create_missing_tag():
    from app.schemas import InterestCreate
    with pytest.raises(ValidationError):
        InterestCreate(score=0.9)
