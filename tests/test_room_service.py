
import pytest

from app.core.redis import redis_client
from app.repositories.room import RoomRepository
from app.repositories.member import MemberRepository
from app.services.room import RoomService
from app.schemas.room import RoomResponse


@pytest.fixture
def room_service():
    room_repository = RoomRepository(redis_client)
    member_repository = MemberRepository(redis_client)

    return RoomService(
        room_repository=room_repository,
        member_repository=member_repository
    )


@pytest.fixture
def cleanup():
    """
    Provides a helper to remove test room data after each test.
    """

    created_rooms = []

    def register(code):
        created_rooms.append(code)

    yield register

    room_repository = RoomRepository(redis_client)
    member_repository = MemberRepository(redis_client)

    for code in created_rooms:
        members = member_repository.get_members(code)

        for member_id in members:
            member_repository.remove_member(code, member_id)

        room_repository.delete_room(code)


# --------------------------------------------------
# CREATE ROOM TESTS
# --------------------------------------------------

def test_create_room_success(room_service, cleanup):
    room = room_service.create_room("host-1")
    cleanup(room.code)

    assert isinstance(room, RoomResponse)
    assert room.host_id == "host-1"
    assert room.status == "waiting"
    assert len(room.code) == 6


def test_create_room_generates_unique_codes(room_service, cleanup):
    room1 = room_service.create_room("host-1")
    cleanup(room1.code)

    room2 = room_service.create_room("host-2")
    cleanup(room2.code)

    assert room1.code != room2.code


# --------------------------------------------------
# GET ROOM TESTS
# --------------------------------------------------

def test_get_room_success(room_service, cleanup):
    created = room_service.create_room("host-1")
    cleanup(created.code)

    room = room_service.get_room(created.code)

    assert room.code == created.code
    assert room.host_id == "host-1"
    assert room.status == "waiting"


def test_get_room_not_found(room_service):
    with pytest.raises(ValueError, match="Room not found"):
        room_service.get_room("NOPE99")


# --------------------------------------------------
# JOIN ROOM TESTS
# --------------------------------------------------

def test_join_room_success(room_service, cleanup):
    room = room_service.create_room("host-1")
    cleanup(room.code)

    result = room_service.join_room(room.code, "user-2")

    members = room_service.member_repository.get_members(room.code)

    assert result.code == room.code
    assert "user-2" in members


def test_join_room_not_found(room_service):
    with pytest.raises(ValueError, match="Room not found"):
        room_service.join_room("NOPE99", "user-2")


def test_join_room_duplicate_member(room_service, cleanup):
    room = room_service.create_room("host-1")
    cleanup(room.code)

    with pytest.raises(ValueError, match="already a member"):
        room_service.join_room(room.code, "host-1")


def test_join_full_room(room_service, cleanup):
    room = room_service.create_room("host-1")
    cleanup(room.code)

    room_service.join_room(room.code, "user-2")
    room_service.join_room(room.code, "user-3")

    with pytest.raises(ValueError, match="Room is full"):
        room_service.join_room(room.code, "user-4")


# --------------------------------------------------
# LEAVE ROOM TESTS
# --------------------------------------------------

def test_leave_room_success(room_service, cleanup):
    room = room_service.create_room("host-1")
    cleanup(room.code)

    room_service.join_room(room.code, "user-2")

    result = room_service.leave_room(room.code, "user-2")

    members = room_service.member_repository.get_members(room.code)

    assert result["message"] == "User left the room successfully"
    assert "user-2" not in members


def test_leave_room_host_cancels_room(room_service, cleanup):
    room = room_service.create_room("host-1")
    cleanup(room.code)

    room_service.join_room(room.code, "user-2")

    result = room_service.leave_room(room.code, "host-1")

    assert result["message"] == "Host left. Room has been cancelled"
    assert not room_service.room_repository.room_exists(room.code)


def test_leave_room_not_found(room_service):
    with pytest.raises(ValueError, match="Room does not exist"):
        room_service.leave_room("NOPE99", "user-1")


def test_leave_room_non_member(room_service, cleanup):
    room = room_service.create_room("host-1")
    cleanup(room.code)

    with pytest.raises(ValueError, match="not a member"):
        room_service.leave_room(room.code, "stranger")


def test_leave_active_room(room_service, cleanup):
    room = room_service.create_room("host-1")
    cleanup(room.code)

    room_service.join_room(room.code, "user-2")
    room_service.start_room(room.code, "host-1")

    with pytest.raises(ValueError, match="Cannot leave an active room"):
        room_service.leave_room(room.code, "user-2")


# --------------------------------------------------
# START ROOM TESTS
# --------------------------------------------------

def test_start_room_success(room_service, cleanup):
    room = room_service.create_room("host-1")
    cleanup(room.code)

    room_service.join_room(room.code, "user-2")

    result = room_service.start_room(room.code, "host-1")

    assert result["status"] == "started"

    updated_room = room_service.get_room(room.code)

    assert updated_room.status == "started"


def test_start_room_not_found(room_service):
    with pytest.raises(ValueError, match="Room not found"):
        room_service.start_room("NOPE99", "host-1")


def test_start_room_non_member(room_service, cleanup):
    room = room_service.create_room("host-1")
    cleanup(room.code)

    with pytest.raises(ValueError, match="not a member"):
        room_service.start_room(room.code, "stranger")


def test_start_room_non_host(room_service, cleanup):
    room = room_service.create_room("host-1")
    cleanup(room.code)

    room_service.join_room(room.code, "user-2")

    with pytest.raises(ValueError, match="Only the host"):
        room_service.start_room(room.code, "user-2")


def test_start_room_insufficient_members(room_service, cleanup):
    room = room_service.create_room("host-1")
    cleanup(room.code)

    with pytest.raises(ValueError, match="At least 2 members"):
        room_service.start_room(room.code, "host-1")


def test_start_already_started_room(room_service, cleanup):
    room = room_service.create_room("host-1")
    cleanup(room.code)

    room_service.join_room(room.code, "user-2")
    room_service.start_room(room.code, "host-1")

    with pytest.raises(ValueError, match="already started or ended"):
        room_service.start_room(room.code, "host-1")


# --------------------------------------------------
# END ROOM TESTS
# --------------------------------------------------

def test_end_room_success(room_service, cleanup):
    room = room_service.create_room("host-1")
    cleanup(room.code)

    room_service.join_room(room.code, "user-2")
    room_service.start_room(room.code, "host-1")

    result = room_service.end_room(room.code, "host-1")

    assert result["message"] == "Room ended successfully"
    assert result["code"] == room.code
    assert result["status"] == "ended"

    updated_room = room_service.get_room(room.code)

    assert updated_room.status == "ended"


def test_end_room_not_found(room_service):
    with pytest.raises(ValueError, match="Room not found"):
        room_service.end_room("NOPE99", "host-1")


def test_end_room_non_member(room_service, cleanup):
    room = room_service.create_room("host-1")
    cleanup(room.code)

    room_service.join_room(room.code, "user-2")
    room_service.start_room(room.code, "host-1")

    with pytest.raises(ValueError, match="not a member"):
        room_service.end_room(room.code, "stranger")


def test_end_room_non_host(room_service, cleanup):
    room = room_service.create_room("host-1")
    cleanup(room.code)

    room_service.join_room(room.code, "user-2")
    room_service.start_room(room.code, "host-1")

    with pytest.raises(ValueError, match="Only the host"):
        room_service.end_room(room.code, "user-2")


def test_end_room_before_starting(room_service, cleanup):
    room = room_service.create_room("host-1")
    cleanup(room.code)

    with pytest.raises(ValueError, match="Only an active room"):
        room_service.end_room(room.code, "host-1")


def test_end_room_twice(room_service, cleanup):
    room = room_service.create_room("host-1")
    cleanup(room.code)

    room_service.join_room(room.code, "user-2")
    room_service.start_room(room.code, "host-1")
    room_service.end_room(room.code, "host-1")

    with pytest.raises(ValueError, match="Only an active room"):
        room_service.end_room(room.code, "host-1")