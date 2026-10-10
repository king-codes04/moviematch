import pytest
from unittest.mock import Mock

from fastapi.testclient import TestClient

from app.websockets.routes import manager
from app.main import app
from app.dependencies import (
    get_room_service,
    get_matching_service,
)


# ----------------------------
# Fake services
# ----------------------------

class FakeRoomService:
    def __init__(self):
        self.rooms = {}
        self.members = {}
        self.statuses = {}

    def create_room(self, username):
        code = "TEST01"

        room = {
            "code": code,
            "host_id": username,
            "status": "waiting",
        }

        self.rooms[code] = room
        self.members[code] = {username}
        self.statuses[code] = "waiting"

        return room

    def get_room(self, code):
        if code not in self.rooms:
            raise ValueError("Room not found")

        return self.rooms[code]

    def join_room(self, code, username):
        if code not in self.rooms:
            raise ValueError("Room not found")

        if self.statuses[code] != "waiting":
            raise ValueError("Room is not accepting new members")

        if username in self.members[code]:
            raise ValueError("User is already a member")

        if len(self.members[code]) >= 3:
            raise ValueError("Room is full")

        self.members[code].add(username)

        return self.rooms[code]

    def leave_room(self, code, username):
        if code not in self.rooms:
            raise ValueError("Room does not exist")

        if username not in self.members[code]:
            raise ValueError("User is not a member")

        if self.rooms[code]["host_id"] == username:
            del self.rooms[code]
            del self.members[code]
            del self.statuses[code]

            return {
                "message": "Host left. Room has been cancelled"
            }

        self.members[code].remove(username)

        return {
            "message": "User left the room successfully"
        }

    def start_room(self, code, username):
        if code not in self.rooms:
            raise ValueError("Room not found")

        if self.rooms[code]["host_id"] != username:
            raise ValueError("Only the host can start")

        if len(self.members[code]) < 2:
            raise ValueError(
                "At least 2 members are required to start"
            )

        self.statuses[code] = "started"
        self.rooms[code]["status"] = "started"

        return {
            "code": code,
            "status": "started",
        }

    def end_room(self, code, username):
        if code not in self.rooms:
            raise ValueError("Room not found")

        if self.rooms[code]["host_id"] != username:
            raise ValueError("Only the host can end")

        if self.statuses[code] != "started":
            raise ValueError("Only an active room can be ended")

        self.statuses[code] = "ended"
        self.rooms[code]["status"] = "ended"

        return {
            "code": code,
            "status": "ended",
        }


class FakeMatchingService:
    def __init__(self):
        self.calls = []

        # The WebSocket endpoint uses this repository
        # to verify room membership.
        self.member_repository = Mock()
        self.member_repository.member_exists.return_value = True

    def submit_decision(
        self,
        code,
        round_number,
        user_id,
        decision,
    ):
        # Decision is a DecisionType enum in the route.
        # Store its string value for our assertions.
        decision_value = getattr(decision, "value", decision)

        self.calls.append({
            "code": code,
            "round_number": round_number,
            "user_id": user_id,
            "decision": decision_value,
        })

        return {
            "status": "waiting",
            "round_number": round_number,
        }


# ----------------------------
# Fixtures
# ----------------------------

@pytest.fixture
def api_services():
    room_service = FakeRoomService()
    matching_service = FakeMatchingService()

    app.dependency_overrides[get_room_service] = (
        lambda: room_service
    )
    app.dependency_overrides[get_matching_service] = (
        lambda: matching_service
    )

    try:
        with TestClient(app) as client:
            yield client, room_service, matching_service
    finally:
        app.dependency_overrides.pop(get_room_service, None)
        app.dependency_overrides.pop(get_matching_service, None)


# ----------------------------
# Basic endpoints
# ----------------------------

def test_welcome_endpoint():
    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert response.json() == "hello"


def test_create_room(api_services):
    client, _, _ = api_services

    response = client.post(
        "/rooms",
        json={"username": "user_001"},
    )

    assert response.status_code == 201
    assert response.json() == {
        "code": "TEST01",
        "host_id": "user_001",
        "status": "waiting",
    }


# ----------------------------
# Room route tests
# ----------------------------

def test_get_existing_room(api_services):
    client, room_service, _ = api_services
    room_service.create_room("user_001")

    response = client.get("/rooms/TEST01")

    assert response.status_code == 200
    assert response.json()["code"] == "TEST01"


def test_get_missing_room_returns_404(api_services):
    client, _, _ = api_services

    response = client.get("/rooms/MISSING")

    assert response.status_code == 404


def test_join_room(api_services):
    client, room_service, _ = api_services
    room_service.create_room("user_001")

    response = client.post(
        "/rooms/TEST01/join",
        json={"username": "user_002"},
    )

    assert response.status_code == 200
    assert "user_002" in room_service.members["TEST01"]


def test_join_missing_room_returns_400(api_services):
    client, _, _ = api_services

    response = client.post(
        "/rooms/MISSING/join",
        json={"username": "user_002"},
    )

    assert response.status_code == 400


def test_leave_room(api_services):
    client, room_service, _ = api_services
    room_service.create_room("user_001")
    room_service.join_room("TEST01", "user_002")

    response = client.post(
        "/rooms/TEST01/leave",
        json={"username": "user_002"},
    )

    assert response.status_code == 200
    assert "user_002" not in room_service.members["TEST01"]


def test_start_room(api_services):
    client, room_service, _ = api_services
    room_service.create_room("user_001")
    room_service.join_room("TEST01", "user_002")

    response = client.post(
        "/rooms/TEST01/start",
        json={"username": "user_001"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "started"


def test_end_room(api_services):
    client, room_service, _ = api_services
    room_service.create_room("user_001")
    room_service.join_room("TEST01", "user_002")
    room_service.start_room("TEST01", "user_001")

    response = client.post(
        "/rooms/TEST01/end",
        json={"username": "user_001"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ended"


# ----------------------------
# Decision route tests
# ----------------------------

def test_submit_decision(api_services):
    client, _, matching_service = api_services

    response = client.post(
        "/rooms/TEST01/rounds/1/decision?user_id=user_001",
        json={"decision": "like"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "waiting",
        "round_number": 1,
    }

    assert matching_service.calls == [{
        "code": "TEST01",
        "round_number": 1,
        "user_id": "user_001",
        "decision": "like",
    }]


def test_invalid_decision_returns_422(api_services):
    client, _, matching_service = api_services

    response = client.post(
        "/rooms/TEST01/rounds/1/decision?user_id=user_001",
        json={"decision": "maybe"},
    )

    assert response.status_code == 422
    assert matching_service.calls == []


def test_decision_missing_user_id_returns_422(api_services):
    client, _, matching_service = api_services

    response = client.post(
        "/rooms/TEST01/rounds/1/decision",
        json={"decision": "like"},
    )

    assert response.status_code == 422
    assert matching_service.calls == []


def test_submit_decision_broadcasts_result_to_room(api_services):
    client, room_service, _ = api_services
    room_service.create_room("user_001")

    with client.websocket_connect(
        "/ws/TEST01?user_id=user_001"
    ) as websocket:
        response = client.post(
            "/rooms/TEST01/rounds/1/decision?user_id=user_001",
            json={"decision": "like"},
        )

        assert response.status_code == 200
        assert response.json() == {
            "status": "waiting",
            "round_number": 1,
        }

        message = websocket.receive_json()

        assert message == {
            "event": "decision_waiting",
            "data": {
                "status": "waiting",
                "round_number": 1,
            },
        }
