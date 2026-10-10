from unittest.mock import AsyncMock

import pytest

from app.websockets.manager import ConnectionManager


class FakeWebSocket:
    def __init__(self):
        self.accept = AsyncMock()
        self.send_text = AsyncMock()


@pytest.mark.anyio
async def test_connect_registers_websocket_in_room():
    # Arrange
    manager = ConnectionManager()
    websocket = FakeWebSocket()
    room_code = "ABC123"

    # Act
    await manager.connect(room_code, websocket)

    # Assert
    assert websocket in manager.active_connections[room_code]
    websocket.accept.assert_awaited_once()



@pytest.mark.anyio
async def test_disconnect_removes_websocket_from_room():
    # Arrange
    manager = ConnectionManager()
    websocket = FakeWebSocket()
    room_code = "ABC123"

    await manager.connect(room_code, websocket)

    # Act
    manager.disconnect(room_code, websocket)

    # Assert
    assert room_code not in manager.active_connections


@pytest.mark.anyio
async def test_broadcast_sends_message_to_all_connections_in_room():
    # Arrange
    manager = ConnectionManager()
    websocket_a = FakeWebSocket()
    websocket_b = FakeWebSocket()
    websocket_other_room = FakeWebSocket()

    await manager.connect("ABC123", websocket_a)
    await manager.connect("ABC123", websocket_b)
    await manager.connect("XYZ789", websocket_other_room)

    message = '{"event": "movie_matched"}'

    # Act
    await manager.broadcast("ABC123", message)

    # Assert
    websocket_a.send_text.assert_awaited_once_with(message)
    websocket_b.send_text.assert_awaited_once_with(message)
    websocket_other_room.send_text.assert_not_awaited()


@pytest.mark.anyio
async def test_broadcast_to_empty_room_does_not_raise_error():
    # Arrange
    manager = ConnectionManager()
    room_code = "EMPTY1"
    message = '{"event": "movie_matched"}'

    # Act
    await manager.broadcast(room_code, message)

    # Assert
    assert room_code not in manager.active_connections



@pytest.mark.anyio
async def test_broadcast_continues_when_one_websocket_fails():
    # Arrange
    manager = ConnectionManager()
    broken_socket = FakeWebSocket()
    healthy_socket = FakeWebSocket()
    room_code = "ABC123"
    message = '{"event": "room_started"}'

    await manager.connect(room_code, broken_socket)
    await manager.connect(room_code, healthy_socket)

    broken_socket.send_text.side_effect = RuntimeError(
        "Connection is closed"
    )

    # Act
    await manager.broadcast(room_code, message)

    # Assert
    broken_socket.send_text.assert_awaited_once_with(message)
    healthy_socket.send_text.assert_awaited_once_with(message)
    assert broken_socket not in manager.active_connections[room_code]
    assert healthy_socket in manager.active_connections[room_code]