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
    """Provides predictable movies without making real TMDB requests."""

    def get_movie_pool(self, pool_size=10):
        return [
            {"id": 101, "title": "Integration Movie One"},
            {"id": 202, "title": "Integration Movie Two"},
        ]


def cleanup_room(code):
    """Remove Redis data created by this integration test."""

    keys = [
        f"ROOM:{code}",
        f"ROOM:{code}:MEMBERS",
        f"MOVIES:{code}",
        f"SESSION:{code}",
        f"MATCHES:{code}",
    ]

    decision_keys = list(
        redis_client.scan_iter(
            match=f"DECISIONS:{code}:ROUND:*"
        )
    )
    keys.extend(decision_keys)

    if keys:
        redis_client.delete(*keys)


@pytest.fixture
def integration_client(monkeypatch):
    """Provide an API test client and clean up every room created."""

    created_codes = []

    # get_room_service() calls this function directly.
    # Patch it in the module where the function is defined.
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


def test_http_to_redis_movie_matching_flow(integration_client):
    client, created_codes = integration_client

    # 1. Create a room through the HTTP API.
    create_response = client.post(
        "/rooms",
        json={"username": "host_001"},
    )

    assert create_response.status_code == 201

    room_data = create_response.json()
    actual_code = room_data["code"]

    # Track the real generated room code for reliable cleanup.
    created_codes.append(actual_code)

    assert room_data["status"] == "waiting"
    assert room_data["host_id"] == "host_001"

    # 2. Confirm the room and movie pool exist in Redis.
    room_repository = RoomRepository(redis_client)
    member_repository = MemberRepository(redis_client)
    movie_repository = MovieRepository(redis_client)
    session_repository = SessionRepository(redis_client)
    match_repository = MatchRepository(redis_client)

    assert room_repository.room_exists(actual_code)
    assert "host_001" in member_repository.get_members(actual_code)
    assert movie_repository.movie_count(actual_code) == 2

    # 3. Join the room through the HTTP API.
    join_response = client.post(
        f"/rooms/{actual_code}/join",
        json={"username": "member_002"},
    )

    assert join_response.status_code == 200
    assert "member_002" in member_repository.get_members(actual_code)

    # 4. Start the room through the HTTP API.
    start_response = client.post(
        f"/rooms/{actual_code}/start",
        json={"username": "host_001"},
    )

    assert start_response.status_code == 200
    assert room_repository.get_room(actual_code)["status"] == "started"

    session = session_repository.get_session(actual_code)
    assert session["status"] == "started"
    assert session["current_round"] == "1"

    # 5. First member likes the current movie.
    first_decision = client.post(
        f"/rooms/{actual_code}/rounds/1/decision",
        params={"user_id": "host_001"},
        json={"decision": "like"},
    )

    assert first_decision.status_code == 200
    assert first_decision.json()["status"] == "waiting"
    assert movie_repository.movie_count(actual_code) == 2
    assert match_repository.match_count(actual_code) == 0

    # 6. Second member likes it too, completing the round.
    second_decision = client.post(
        f"/rooms/{actual_code}/rounds/1/decision",
        params={"user_id": "member_002"},
        json={"decision": "like"},
    )

    assert second_decision.status_code == 200

    result = second_decision.json()

    assert result["status"] == "completed"
    assert result["matched"] is True
    assert result["like_count"] == 2
    assert result["next_round"] == 2

    # 7. Verify the match and round progression in Redis.
    matches = match_repository.get_matches(actual_code)

    assert len(matches) == 1
    assert matches[0]["id"] == 101

    assert movie_repository.movie_count(actual_code) == 1

    updated_session = session_repository.get_session(actual_code)
    assert updated_session["current_round"] == "2"
    assert updated_session["status"] == "started"
