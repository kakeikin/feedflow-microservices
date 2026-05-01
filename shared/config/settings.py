# Reference: env var patterns used across services
#
# Database services:
#   DATABASE_URL — postgresql+asyncpg://user:pass@host:port/db
#
# Ranking service:
#   USER_SERVICE_URL  — http://user-service:8001
#   VIDEO_SERVICE_URL — http://video-service:8002
#
# Feed service:
#   VIDEO_SERVICE_URL    — http://video-service:8002
#   RANKING_SERVICE_URL  — http://ranking-service:8004
