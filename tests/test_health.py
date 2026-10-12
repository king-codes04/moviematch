from unittest.mock import Mock

from fastapi.testclient import TestClient

from app.main import app


def test_health_reports_redis_connected(monkeypatch):
    ping = Mock(return_value=True)
    monkeypatch.setattr("app.main.redis_client.ping", ping)

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "healthy",
        "redis": "connected",
    }
    ping.assert_called_once_with()


def test_health_returns_service_unavailable_when_redis_is_down(monkeypatch):
    monkeypatch.setattr(
        "app.main.redis_client.ping",
        Mock(side_effect=ConnectionError("Redis unavailable")),
    )

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 503
    assert response.json() == {
        "detail": {
            "status": "unhealthy",
            "redis": "disconnected",
        }
    }
