# FeedFlow Microservices

FeedFlow Microservices is the second-generation version of FeedFlow.

The original FeedFlow was a monolithic personalized feed backend. This version redesigns the system into independently deployable services to improve fault isolation, maintainability, and scalability.

Phase 1 focuses on service decomposition, HTTP-based service communication, Docker Compose orchestration, and basic integration testing.

## Services

| Service | Port | Responsibility |
|---|---|---|
| user-service | 8001 | Users and interest profiles |
| video-service | 8002 | Video metadata and stats |
| event-service | 8003 | User interaction events |
| ranking-service | 8004 | Rule-based video scoring |
| feed-service | 8005 | Personalized feed API |

## Run Locally

```bash
docker compose -f infra/docker-compose.yml up --build
```

All services start with their databases. Tables are created automatically on first boot.

## Integration Tests

Assumes Docker Compose is running:
```bash
pytest tests/integration/ -v
```
