
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from app.dependencies import (
    get_room_service,
    get_matching_service,
)
from app.main import app
from app.websockets.routes import manager


@pytest.fixture
def client():
    # Arrange: create fake services for each test.
    room_service = Mock()
    room_service.get_room.return_value = {
        "code": "ABC123",
        "host_id": "user-1",
        "status": "waiting",
    }

    matching_service = Mock()
    matching_service.member_repository.member_exists.return_value = True

    # Replace real dependencies with our fake services.
    app.dependency_overrides[get_room_service] = (
        lambda: room_service
    )
    app.dependency_overrides[get_matching_service] = (
        lambda: matching_service
    )

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        # Cleanup: prevent overrides leaking into other tests.
        app.dependency_overrides.pop(get_room_service, None)
        app.dependency_overrides.pop(get_matching_service, None)


def test_websocket_endpoint_accepts_existing_room(client):
    # Act: connect as a valid room member.
    with client.websocket_connect(
        "/ws/ABC123?user_id=user-1"
    ) as websocket:
        # Assert: the connection was accepted.
        assert websocket is not None


def test_websocket_disconnect_removes_connection(client):
    # Arrange
    room_code = "ABC123"

    # Act: connect, then disconnect by leaving the context.
    with client.websocket_connect(
        f"/ws/{room_code}?user_id=user-1"
    ):
        assert room_code in manager.active_connections
        assert len(manager.active_connections[room_code]) == 1

    # Assert: the connection has been removed.
    assert (
        room_code not in manager.active_connections
        or len(manager.active_connections[room_code]) == 0
    )


def test_websocket_rejects_non_member(client):
    # Arrange: configure the fake membership check to reject the user.
    matching_service = app.dependency_overrides[
        get_matching_service
    ]()
    matching_service.member_repository.member_exists.return_value = False

    # Act + Assert: the server rejects the connection.
    with pytest.raises(Exception):
        with client.websocket_connect(
            "/ws/ABC123?user_id=outsider"
        ):
            pass

    # Assert: the rejected user was never registered.
    assert (
        "ABC123" not in manager.active_connections
        or len(manager.active_connections["ABC123"]) == 0
    )
