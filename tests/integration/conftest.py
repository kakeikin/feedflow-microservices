import httpx
import pytest


def pytest_collection_modifyitems(items):
    """Skip all integration tests if Docker Compose services are not running."""
    try:
        httpx.get("http://localhost:8001/health", timeout=2.0)
    except Exception:
        for item in items:
            item.add_marker(
                pytest.mark.skip(reason="Docker Compose services not running — run: docker compose -f infra/docker-compose.yml up -d")
            )
