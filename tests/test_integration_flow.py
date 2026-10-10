
import uuid

import pytest

from app.core.redis import redis_client

from app.repositories.room import RoomRepository
from app.repositories.member import MemberRepository
from app.repositories.movie import MovieRepository
from app.repositories.session import SessionRepository
from app.repositories.decision import DecisionRepository
from app.repositories.match import MatchRepository

from app.services.room import RoomService
from app.services.matching import MatchingService


class FakeMovieService:
    """Supplies predictable movies without making TMDB requests."""

    def get_movie_pool(self, pool_size=10):
        return [
            {
                "id": 101,
                "title": "Integration Test Movie One",
            },
            {
                "id": 202,
                "title": "Integration Test Movie Two",
            },
        ]


def cleanup_test_room(client, code):
    """Delete only Redis keys belonging to this test room."""

    keys = [
        f"ROOM:{code}",
        f"ROOM:{code}:MEMBERS",
        f"MOVIES:{code}",
        f"SESSION:{code}",
        f"MATCHES:{code}",
    ]

    decision_keys = list(
        client.scan_iter(
            match=f"DECISIONS:{code}:ROUND:*"
        )
    )

    keys.extend(decision_keys)

    if keys:
        client.delete(*keys)


def test_complete_movie_matching_flow(monkeypatch):
    # ARRANGE: create a unique room code and real repositories.
    code = f"IT{uuid.uuid4().hex[:4].upper()}"

    room_repository = RoomRepository(redis_client)
    member_repository = MemberRepository(redis_client)
    movie_repository = MovieRepository(redis_client)
    session_repository = SessionRepository(redis_client)
    decision_repository = DecisionRepository(redis_client)
    match_repository = MatchRepository(redis_client)

    movie_service = FakeMovieService()

    room_service = RoomService(
        room_repository=room_repository,
        member_repository=member_repository,
        movie_service=movie_service,
        movie_repository=movie_repository,
        session_repository=session_repository,
    )

    matching_service = MatchingService(
        room_repository=room_repository,
        member_repository=member_repository,
        decision_repository=decision_repository,
        movie_repository=movie_repository,
        match_repository=match_repository,
        session_repository=session_repository,
    )

    # Make room creation use our unique test code.
    monkeypatch.setattr(
        room_service,
        "generate_room_code",
        lambda: code,
    )

    try:
        # ACT 1: host creates a room.
        room = room_service.create_room("host_001")

        # ASSERT 1: room and initial movie pool exist in Redis.
        assert room.code == code
        assert room.status == "waiting"
        assert room_repository.get_room(code)["host_id"] == "host_001"
        assert member_repository.get_members(code) == {"host_001"}
        assert movie_repository.movie_count(code) == 2

        # ACT 2: another member joins.
        room_service.join_room(code, "member_002")

        # ASSERT 2: both members are stored in Redis.
        assert member_repository.get_members(code) == {
            "host_001",
            "member_002",
        }

        # ACT 3: host starts the session.
        result = room_service.start_room(code, "host_001")

        # ASSERT 3: room and session are active.
        assert result["status"] == "started"
        assert room_repository.get_room(code)["status"] == "started"

        session = session_repository.get_session(code)
        assert session["status"] == "started"
        assert int(session["current_round"]) == 1

        # ACT 4: the host likes the first movie.
        first_decision = matching_service.submit_decision(
            code=code,
            round_number=1,
            user_id="host_001",
            decision="like",
        )

        # ASSERT 4: wait because the other member has not decided.
        assert first_decision == {
            "status": "waiting",
            "round_number": 1,
        }

        assert movie_repository.movie_count(code) == 2
        assert match_repository.match_count(code) == 0
        assert int(
            session_repository.get_session(code)["current_round"]
        ) == 1

        # ACT 5: the second member likes the same movie.
        second_decision = matching_service.submit_decision(
            code=code,
            round_number=1,
            user_id="member_002",
            decision="like",
        )

        # ASSERT 5: the first movie matches and round 2 begins.
        assert second_decision["status"] == "completed"
        assert second_decision["matched"] is True
        assert second_decision["like_count"] == 2
        assert second_decision["next_round"] == 2

        assert match_repository.get_matches(code) == [
            {
                "id": 101,
                "title": "Integration Test Movie One",
            }
        ]

        assert movie_repository.movie_count(code) == 1
        assert int(
            session_repository.get_session(code)["current_round"]
        ) == 2

        # ACT 6: both members dislike the second movie.
        third_decision = matching_service.submit_decision(
            code=code,
            round_number=2,
            user_id="host_001",
            decision="dislike",
        )

        # The service must wait for the other member again.
        assert third_decision["status"] == "waiting"

        fourth_decision = matching_service.submit_decision(
            code=code,
            round_number=2,
            user_id="member_002",
            decision="dislike",
        )

        # ASSERT 6: no match is created; the session ends.
        assert fourth_decision["status"] == "ended"
        assert fourth_decision["matched"] is False
        assert fourth_decision["like_count"] == 0

        assert match_repository.match_count(code) == 1
        assert movie_repository.movie_count(code) == 0

        assert session_repository.get_session(code)["status"] == "ended"
        assert room_repository.get_room(code)["status"] == "ended"

    finally:
        # CLEANUP: remove this test's Redis data, even if an assertion fails.
        cleanup_test_room(redis_client, code)
