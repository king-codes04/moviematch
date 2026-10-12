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
        f"MOVIES:{code}:BY_ID",
        f"SESSION:{code}",
        f"MATCHES:{code}",
        f"MATCHES:{code}:IDS",
        f"MATCHES:{code}:BY_ID",
    ]

    keys.extend(
        redis_client.scan_iter(match=f"DECISIONS:{code}:*")
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


def test_http_to_redis_independent_movie_pool_flow(integration_client):
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
    assert movie_repository.movie_count(code) == 0

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
    assert response.json()["movie_count"] == 2

    session = session_repository.get_session(code)
    assert session["status"] == "started"
    assert movie_repository.movie_count(code) == 2

    # Both members recover the same room pool, with private decision state.
    host_state = client.get(
        f"/rooms/{code}/state",
        params={"user_id": "host_001"},
    ).json()
    member_state = client.get(
        f"/rooms/{code}/state",
        params={"user_id": "member_002"},
    ).json()
    assert [movie["id"] for movie in host_state["movies"]] == [101, 202]
    assert host_state["movies"] == member_state["movies"]

    # A member can decide on another movie without waiting for this one.
    response = client.post(
        f"/rooms/{code}/movies/101/decision",
        params={"user_id": "host_001"},
        json={"decision": "like"},
    )
    assert response.status_code == 200
    assert response.json()["duplicate"] is False
    assert movie_repository.movie_count(code) == 2
    assert match_repository.match_count(code) == 0

    response = client.post(
        f"/rooms/{code}/movies/202/decision",
        params={"user_id": "host_001"},
        json={"decision": "skip"},
    )
    assert response.status_code == 200
    assert response.json()["decision"] == "skip"
    assert movie_repository.movie_count(code) == 2

    upgraded = client.post(
        f"/rooms/{code}/movies/202/decision",
        params={"user_id": "host_001"},
        json={"decision": "like"},
    )
    assert upgraded.status_code == 200
    assert upgraded.json()["decision"] == "like"
    assert upgraded.json()["duplicate"] is False

    upgrade_retry = client.post(
        f"/rooms/{code}/movies/202/decision",
        params={"user_id": "host_001"},
        json={"decision": "like"},
    )
    assert upgrade_retry.status_code == 200
    assert upgrade_retry.json()["duplicate"] is True

    # The second distinct like finds a match while leaving the pool intact.
    response = client.post(
        f"/rooms/{code}/movies/101/decision",
        params={"user_id": "member_002"},
        json={"decision": "like"},
    )
    assert response.status_code == 200

    result = response.json()
    assert result["matched"] is True
    assert result["new_match"] is True

    matches = match_repository.get_matches(code)
    assert len(matches) == 1
    assert matches[0]["id"] == 101

    assert movie_repository.movie_count(code) == 2
    state = client.get(
        f"/rooms/{code}/state",
        params={"user_id": "member_002"},
    ).json()
    assert len(state["matches"]) == 1
    assert state["movies"][0]["my_decision"] == "like"


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


def test_decision_retries_conflicts_and_validation(integration_client):
    client, created_codes = integration_client
    code = create_room_and_join_member(client, created_codes)
    start_room(client, code)

    first = client.post(
        f"/rooms/{code}/movies/101/decision",
        params={"user_id": "host_001"},
        json={"decision": "like"},
    )
    assert first.status_code == 200
    assert first.json()["duplicate"] is False

    retry = client.post(
        f"/rooms/{code}/movies/101/decision",
        params={"user_id": "host_001"},
        json={"decision": "like"},
    )
    assert retry.status_code == 200
    assert retry.json()["duplicate"] is True

    conflict = client.post(
        f"/rooms/{code}/movies/101/decision",
        params={"user_id": "host_001"},
        json={"decision": "skip"},
    )
    assert conflict.status_code == 409

    outsider = client.post(
        f"/rooms/{code}/movies/101/decision",
        params={"user_id": "outsider"},
        json={"decision": "like"},
    )
    assert outsider.status_code == 403

    invalid_movie = client.post(
        f"/rooms/{code}/movies/999/decision",
        params={"user_id": "member_002"},
        json={"decision": "like"},
    )
    assert invalid_movie.status_code == 404
    assert MatchRepository(redis_client).match_count(code) == 0


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


def test_movie_match_broadcasts_events_to_all_clients(
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

            response = client.post(
                f"/rooms/{code}/movies/101/decision",
                params={"user_id": "host_001"},
                json={"decision": "like"},
            )
            assert response.status_code == 200
            for websocket in (host_socket, member_socket):
                decision_event = receive_event(
                    websocket, "decision_recorded"
                )
                assert decision_event["data"] == {"movie_id": 101}

            response = client.post(
                f"/rooms/{code}/movies/101/decision",
                params={"user_id": "member_002"},
                json={"decision": "like"},
            )
            assert response.status_code == 200
            assert response.json()["matched"] is True

            for websocket in (host_socket, member_socket):
                decision_event = receive_event(
                    websocket, "decision_recorded"
                )
                assert decision_event["data"] == {"movie_id": 101}
                match_event = receive_event(websocket, "match_found")
                assert match_event["data"]["movie"]["id"] == 101
