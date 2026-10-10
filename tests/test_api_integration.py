import uuid

import pytest
from fastapi.testclient import TestClient

import app.dependencies as dependencies
from app.main import app
from app.core.redis import redis_client
from app.repositories.room import RoomRepository
from app.repositories.member import MemberRepository
from app.repositories.movie import MovieRepository
from app.repositories.session import SessionRepository
from app.repositories.match import MatchRepository


class FakeMovieService:
    """Provide predictable movies without real TMDB requests."""

    def get_movie_pool(self, pool_size=10):
        return [
            {"id": 101, "title": "Integration Movie One"},
            {"id": 202, "title": "Integration Movie Two"},
        ]


def cleanup_room(code):
    """Remove Redis keys belonging to this test room."""

    keys = [
        f"ROOM:{code}",
        f"ROOM:{code}:MEMBERS",
        f"MOVIES:{code}",
        f"SESSION:{code}",
        f"MATCHES:{code}",
    ]

    keys.extend(
        redis_client.scan_iter(match=f"DECISIONS:{code}:ROUND:*")
    )

    if keys:
        redis_client.delete(*keys)


@pytest.fixture
def integration_client(monkeypatch):
    """Provide a test client and clean up rooms created by each test."""

    created_codes = []

    monkeypatch.setattr(
        dependencies,
        "get_movie_service",
        lambda: FakeMovieService(),
    )

    try:
        with TestClient(app) as client:
            yield client, created_codes
    finally:
        for code in created_codes:
            cleanup_room(code)


def create_room_and_join_member(client, created_codes):
    """Create a room and add a second member through the API."""

    response = client.post(
        "/rooms",
        json={"username": "host_001"},
    )
    assert response.status_code == 201

    code = response.json()["code"]
    created_codes.append(code)

    join_response = client.post(
        f"/rooms/{code}/join",
        json={"username": "member_002"},
    )
    assert join_response.status_code == 200

    return code


def start_room(client, code):
    """Start a room through its HTTP endpoint."""

    response = client.post(
        f"/rooms/{code}/start",
        json={"username": "host_001"},
    )
    assert response.status_code == 200
    return response


def receive_event(websocket, expected_event):
    """Receive one event and verify its event name."""

    event = websocket.receive_json()
    assert event["event"] == expected_event
    assert "data" in event
    return event


def test_http_to_redis_movie_matching_flow(integration_client):
    client, created_codes = integration_client

    # Create a room through HTTP.
    response = client.post(
        "/rooms",
        json={"username": "host_001"},
    )
    assert response.status_code == 201

    code = response.json()["code"]
    created_codes.append(code)

    assert response.json()["status"] == "waiting"
    assert response.json()["host_id"] == "host_001"

    room_repository = RoomRepository(redis_client)
    member_repository = MemberRepository(redis_client)
    movie_repository = MovieRepository(redis_client)
    session_repository = SessionRepository(redis_client)
    match_repository = MatchRepository(redis_client)

    assert room_repository.room_exists(code)
    assert "host_001" in member_repository.get_members(code)
    assert movie_repository.movie_count(code) == 2

    # Join a second member.
    response = client.post(
        f"/rooms/{code}/join",
        json={"username": "member_002"},
    )
    assert response.status_code == 200
    assert "member_002" in member_repository.get_members(code)

    # Start the room.
    response = start_room(client, code)
    assert response.json()["status"] == "started"

    session = session_repository.get_session(code)
    assert session["status"] == "started"
    assert session["current_round"] == "1"

    # First member decides: the round must wait.
    response = client.post(
        f"/rooms/{code}/rounds/1/decision",
        params={"user_id": "host_001"},
        json={"decision": "like"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "waiting"
    assert movie_repository.movie_count(code) == 2
    assert match_repository.match_count(code) == 0

    # Second member likes: a match is recorded and the round advances.
    response = client.post(
        f"/rooms/{code}/rounds/1/decision",
        params={"user_id": "member_002"},
        json={"decision": "like"},
    )
    assert response.status_code == 200

    result = response.json()
    assert result["status"] == "completed"
    assert result["matched"] is True
    assert result["like_count"] == 2
    assert result["next_round"] == 2

    matches = match_repository.get_matches(code)
    assert len(matches) == 1
    assert matches[0]["id"] == 101

    assert movie_repository.movie_count(code) == 1
    session = session_repository.get_session(code)
    assert session["current_round"] == "2"
    assert session["status"] == "started"


def test_member_joined_event_reaches_connected_client(integration_client):
    client, created_codes = integration_client

    response = client.post(
        "/rooms",
        json={"username": "host_001"},
    )
    assert response.status_code == 201

    code = response.json()["code"]
    created_codes.append(code)

    with client.websocket_connect(
        f"/ws/{code}?user_id=host_001"
    ) as websocket:
        response = client.post(
            f"/rooms/{code}/join",
            json={"username": "member_002"},
        )
        assert response.status_code == 200

        event = receive_event(websocket, "member_joined")
        assert event["data"]["username"] == "member_002"


def test_room_started_event_reaches_all_connected_clients(
    integration_client,
):
    client, created_codes = integration_client
    code = create_room_and_join_member(client, created_codes)

    with client.websocket_connect(
        f"/ws/{code}?user_id=host_001"
    ) as host_socket:
        with client.websocket_connect(
            f"/ws/{code}?user_id=member_002"
        ) as member_socket:
            start_room(client, code)

            host_event = receive_event(host_socket, "room_started")
            member_event = receive_event(member_socket, "room_started")

            assert host_event["data"]["status"] == "started"
            assert member_event["data"]["status"] == "started"


def test_matching_round_broadcasts_events_to_all_clients(
    integration_client,
):
    client, created_codes = integration_client
    code = create_room_and_join_member(client, created_codes)

    with client.websocket_connect(
        f"/ws/{code}?user_id=host_001"
    ) as host_socket:
        with client.websocket_connect(
            f"/ws/{code}?user_id=member_002"
        ) as member_socket:
            start_room(client, code)

            receive_event(host_socket, "room_started")
            receive_event(member_socket, "room_started")

            # The first decision must leave the round waiting.
            response = client.post(
                f"/rooms/{code}/rounds/1/decision",
                params={"user_id": "host_001"},
                json={"decision": "like"},
            )
            assert response.status_code == 200
            assert response.json()["status"] == "waiting"

            host_waiting = receive_event(
                host_socket, "decision_waiting"
            )
            member_waiting = receive_event(
                member_socket, "decision_waiting"
            )

            assert host_waiting["data"]["round_number"] == 1
            assert member_waiting["data"]["round_number"] == 1

            # The second decision completes the round and finds a match.
            response = client.post(
                f"/rooms/{code}/rounds/1/decision",
                params={"user_id": "member_002"},
                json={"decision": "like"},
            )
            assert response.status_code == 200
            assert response.json()["matched"] is True

            for websocket in (host_socket, member_socket):
                match_event = receive_event(
                    websocket, "match_found"
                )
                round_event = receive_event(
                    websocket, "round_completed"
                )

                assert match_event["data"]["matched"] is True
                assert match_event["data"]["round_number"] == 1
                assert match_event["data"]["matched_movie"]["id"] == 101
                assert match_event["data"]["next_movie"]["id"] == 202

                assert round_event["data"]["matched"] is True
                assert round_event["data"]["matched_movie"]["id"] == 101
                assert round_event["data"]["next_movie"]["id"] == 202
                assert round_event["data"]["next_round"] == 2
