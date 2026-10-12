import pytest

from app.core.redis import redis_client
from app.repositories.room import RoomRepository
from app.repositories.member import MemberRepository
from app.repositories.movie import MovieRepository
from app.repositories.session import SessionRepository
from app.repositories.decision import DecisionRepository
from app.repositories.match import MatchRepository
from app.services.room import RoomService


class FakeMovieService:
    def get_movie_pool(self, pool_size=10):
        return [
            {
                "id": movie_id,
                "title": f"Movie {movie_id}",
            }
            for movie_id in range(1, pool_size + 1)
        ]


@pytest.fixture
def room_service():
    room_repository = RoomRepository(redis_client)
    member_repository = MemberRepository(redis_client)
    movie_repository = MovieRepository(redis_client)
    session_repository = SessionRepository(redis_client)
    decision_repository = DecisionRepository(redis_client)
    match_repository = MatchRepository(redis_client)
    movie_service = FakeMovieService()

    service = RoomService(
        room_repository=room_repository,
        member_repository=member_repository,
        movie_service=movie_service,
        movie_repository=movie_repository,
        session_repository=session_repository,
        decision_repository=decision_repository,
        match_repository=match_repository,
    )

    yield service

    # Clean up Redis data after each test.
    for pattern in (
        "ROOM:*",
        "MOVIES:*",
        "DECISIONS:*",
        "MATCHES:*",
        "SESSION:*",
    ):
        for key in redis_client.scan_iter(match=pattern):
            redis_client.delete(key)


@pytest.fixture
def room_with_two_members(room_service):
    room = room_service.create_room("host")
    code = room.code

    room_service.join_room(code, "member2")

    return code


def test_create_room(room_service):
    room = room_service.create_room("host")

    assert room.code
    assert room.host_id == "host"
    assert room.status == "waiting"

    stored_room = room_service.room_repository.get_room(room.code)

    assert stored_room["host_id"] == "host"
    assert stored_room["status"] == "waiting"


def test_create_room_adds_host_as_member(room_service):
    room = room_service.create_room("host")

    members = room_service.member_repository.get_members(room.code)

    assert "host" in members


def test_create_room_defers_movie_pool_until_start(room_service):
    room = room_service.create_room("host")

    assert room_service.movie_repository.movie_count(room.code) == 0


def test_get_room_success(room_service):
    created_room = room_service.create_room("host")

    room = room_service.get_room(created_room.code)

    assert room.code == created_room.code
    assert room.host_id == "host"
    assert room.status == "waiting"


def test_get_room_not_found(room_service):
    with pytest.raises(ValueError, match="Room not found"):
        room_service.get_room("MISSING")


def test_movie_pool_is_shared_and_requires_started_room_member(
    room_service,
    room_with_two_members,
):
    code = room_with_two_members

    with pytest.raises(ValueError, match="Room is not started"):
        room_service.get_movie_pool(code, "host")

    room_service.start_room(code, "host")
    host_pool = room_service.get_movie_pool(code, "host")
    member_pool = room_service.get_movie_pool(code, "member2")

    assert [movie["id"] for movie in host_pool] == list(range(1, 11))
    assert [movie["id"] for movie in host_pool] == [
        movie["id"] for movie in member_pool
    ]
    assert host_pool[0]["my_decision"] is None

    with pytest.raises(ValueError, match="not a room member"):
        room_service.get_movie_pool(code, "outsider")


def test_room_state_recovers_pool_decisions_and_matches(
    room_service,
    room_with_two_members,
):
    code = room_with_two_members
    room_service.start_room(code, "host")
    room_service.decision_repository.submit_movie_decision(
        code, 1, "host", "like"
    )

    state = room_service.get_room_state(code, "host")
    member_state = room_service.get_room_state(code, "member2")

    assert state["room"].status == "started"
    assert state["movies"][0]["my_decision"] == "like"
    assert member_state["movies"][0]["my_decision"] is None
    assert state["members"] == ["host", "member2"]


def test_join_room_success(room_service):
    room = room_service.create_room("host")

    result = room_service.join_room(room.code, "member2")

    members = room_service.member_repository.get_members(room.code)

    assert result.code == room.code
    assert "member2" in members


def test_join_room_not_found(room_service):
    with pytest.raises(ValueError, match="Room not found"):
        room_service.join_room("MISSING", "member2")


def test_join_room_rejects_duplicate_member(
    room_service,
    room_with_two_members,
):
    with pytest.raises(ValueError, match="already a member"):
        room_service.join_room(room_with_two_members, "member2")


def test_join_room_rejects_full_room(
    room_service,
    room_with_two_members,
):
    code = room_with_two_members
    room_service.join_room(code, "member3")

    with pytest.raises(ValueError, match="Room is full"):
        room_service.join_room(code, "member4")


def test_join_room_rejects_started_room(
    room_service,
    room_with_two_members,
):
    code = room_with_two_members
    room_service.start_room(code, "host")

    with pytest.raises(
        ValueError,
        match="not accepting new members",
    ):
        room_service.join_room(code, "member3")


def test_leave_room_success(
    room_service,
    room_with_two_members,
):
    code = room_with_two_members

    result = room_service.leave_room(code, "member2")

    members = room_service.member_repository.get_members(code)

    assert result["message"] == "User left the room successfully"
    assert "member2" not in members
    assert "host" in members


def test_leave_room_not_found(room_service):
    with pytest.raises(ValueError, match="Room does not exist"):
        room_service.leave_room("MISSING", "host")


def test_leave_room_rejects_non_member(
    room_service,
    room_with_two_members,
):
    with pytest.raises(ValueError, match="not a member"):
        room_service.leave_room(room_with_two_members, "outsider")


def test_host_leaving_cancels_room(
    room_service,
    room_with_two_members,
):
    code = room_with_two_members

    result = room_service.leave_room(code, "host")

    assert result["message"] == "Host left. Room has been cancelled"
    assert not room_service.room_repository.room_exists(code)
    assert room_service.movie_repository.movie_count(code) == 0


def test_host_leaving_removes_decision_history(
    room_service,
    room_with_two_members,
):
    code = room_with_two_members
    room_service.member_repository.client.hset(
        f"DECISIONS:{code}:ROUND:1",
        mapping={"host": "like"},
    )

    room_service.leave_room(code, "host")

    assert not room_service.room_repository.room_exists(code)
    assert not list(
        room_service.room_repository.client.scan_iter(
            match=f"DECISIONS:{code}:ROUND:*"
        )
    )


def test_leave_room_rejects_active_room(
    room_service,
    room_with_two_members,
):
    code = room_with_two_members
    room_service.start_room(code, "host")

    with pytest.raises(ValueError, match="active room"):
        room_service.leave_room(code, "member2")


def test_start_room_success(
    room_service,
    room_with_two_members,
):
    code = room_with_two_members

    result = room_service.start_room(code, "host")

    assert result == {
        "code": code,
        "status": "started",
        "movie_count": 10,
    }

    room = room_service.room_repository.get_room(code)

    assert room["status"] == "started"
    assert room_service.movie_repository.movie_count(code) == 10


def test_start_room_initializes_session(
    room_service,
    room_with_two_members,
):
    # Arrange
    code = room_with_two_members

    # Act
    room_service.start_room(code, "host")

    session = room_service.session_repository.get_session(code)

    # Assert
    assert session["status"] == "started"
    assert session == {"status": "started"}


def test_start_room_not_found(room_service):
    with pytest.raises(ValueError, match="Room not found"):
        room_service.start_room("MISSING", "host")


def test_start_room_rejects_non_host(
    room_service,
    room_with_two_members,
):
    with pytest.raises(ValueError, match="Only the host can start"):
        room_service.start_room(room_with_two_members, "member2")


def test_start_room_requires_two_members(room_service):
    room = room_service.create_room("host")

    with pytest.raises(
        ValueError,
        match="At least 2 members are required",
    ):
        room_service.start_room(room.code, "host")


def test_start_room_rejects_already_started_room(
    room_service,
    room_with_two_members,
):
    code = room_with_two_members
    room_service.start_room(code, "host")

    with pytest.raises(
        ValueError,
        match="already started or ended",
    ):
        room_service.start_room(code, "host")


def test_end_room_success(
    room_service,
    room_with_two_members,
):
    code = room_with_two_members
    room_service.start_room(code, "host")

    result = room_service.end_room(code, "host")

    assert result == {
        "code": code,
        "status": "ended",
    }

    room = room_service.room_repository.get_room(code)

    assert room["status"] == "ended"


def test_end_room_not_found(room_service):
    with pytest.raises(ValueError, match="Room not found"):
        room_service.end_room("MISSING", "host")


def test_end_room_rejects_non_host(
    room_service,
    room_with_two_members,
):
    code = room_with_two_members
    room_service.start_room(code, "host")

    with pytest.raises(ValueError, match="Only the host can end"):
        room_service.end_room(code, "member2")


def test_end_room_requires_active_room(
    room_service,
    room_with_two_members,
):
    with pytest.raises(
        ValueError,
        match="Only an active room can be ended",
    ):
        room_service.end_room(room_with_two_members, "host")
