import httpx

SERVICES = {
    "user-service": "http://localhost:8001",
    "video-service": "http://localhost:8002",
    "event-service": "http://localhost:8003",
    "ranking-service": "http://localhost:8004",
    "feed-service": "http://localhost:8005",
}


def test_all_services_healthy():
    for name, base_url in SERVICES.items():
        response = httpx.get(f"{base_url}/health", timeout=5.0)
        assert response.status_code == 200, f"{name} returned {response.status_code}"
        data = response.json()
        assert data["status"] == "ok", f"{name} status was {data.get('status')}"
