import uuid

from app.core.redis import redis_client
from app.repositories.decision import DecisionRepository
from app.repositories.match import MatchRepository
from app.repositories.member import MemberRepository
from app.repositories.movie import MovieRepository
from app.repositories.room import RoomRepository
from app.repositories.session import SessionRepository
from app.services.matching import MatchingService
from app.services.room import RoomService


class FakeMovieService:
    def get_movie_pool(self, pool_size=10):
        return [
            {"id": 101, "title": "Integration Test Movie One"},
            {"id": 202, "title": "Integration Test Movie Two"},
        ]


def cleanup_test_room(client, code):
    keys = list(client.scan_iter(match=f"ROOM:{code}*"))
    keys.extend(client.scan_iter(match=f"MOVIES:{code}*"))
    keys.extend(client.scan_iter(match=f"SESSION:{code}"))
    keys.extend(client.scan_iter(match=f"DECISIONS:{code}:*"))
    keys.extend(client.scan_iter(match=f"MATCHES:{code}*"))
    if keys:
        client.delete(*set(keys))


def test_complete_independent_movie_pool_flow(monkeypatch):
    code = f"IT{uuid.uuid4().hex[:6].upper()}"
    room_repository = RoomRepository(redis_client)
    member_repository = MemberRepository(redis_client)
    movie_repository = MovieRepository(redis_client)
    session_repository = SessionRepository(redis_client)
    decision_repository = DecisionRepository(redis_client)
    match_repository = MatchRepository(redis_client)

    room_service = RoomService(
        room_repository=room_repository,
        member_repository=member_repository,
        movie_service=FakeMovieService(),
        movie_repository=movie_repository,
        session_repository=session_repository,
        decision_repository=decision_repository,
        match_repository=match_repository,
    )
    matching_service = MatchingService(
        room_repository=room_repository,
        member_repository=member_repository,
        decision_repository=decision_repository,
        movie_repository=movie_repository,
        match_repository=match_repository,
        session_repository=session_repository,
    )
    monkeypatch.setattr(room_service, "generate_room_code", lambda: code)

    try:
        room = room_service.create_room("host")
        assert room.status == "waiting"
        assert movie_repository.movie_count(code) == 0

        room_service.join_room(code, "member")
        room_service.start_room(code, "host")
        assert movie_repository.movie_count(code) == 2

        host_pool = room_service.get_movie_pool(code, "host")
        member_pool = room_service.get_movie_pool(code, "member")
        assert [item["id"] for item in host_pool] == [101, 202]
        assert [item["id"] for item in host_pool] == [
            item["id"] for item in member_pool
        ]

        host_like = matching_service.submit_decision(
            code, 101, "host", "like"
        )
        member_skip = matching_service.submit_decision(
            code, 202, "member", "skip"
        )
        assert not host_like["matched"]
        assert member_skip["decision"] == "skip"
        assert movie_repository.movie_count(code) == 2

        match = matching_service.submit_decision(
            code, 101, "member", "like"
        )
        assert match["new_match"]
        assert match["match"]["id"] == 101
        assert match_repository.get_matches(code) == [
            {"id": 101, "title": "Integration Test Movie One"}
        ]

        state = room_service.get_room_state(code, "host")
        assert state["room"].status == "started"
        assert state["movies"][0]["my_decision"] == "like"
        assert state["matches"] == match_repository.get_matches(code)

        room_service.end_room(code, "host")
        ended_state = room_service.get_room_state(code, "member")
        assert ended_state["room"].status == "ended"
        assert len(ended_state["matches"]) == 1
    finally:
        cleanup_test_room(redis_client, code)
