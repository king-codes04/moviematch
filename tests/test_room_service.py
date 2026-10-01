from app.core.redis import redis_client
from app.repositories.room import RoomRepository
from app.repositories.member import MemberRepository
from app.services.room import RoomService
from app.schemas.room import RoomResponse


def test_create_room_success():
    # Arrange
    room_repository = RoomRepository(redis_client)
    member_repository = MemberRepository(redis_client)

    room_service = RoomService(
        room_repository,
        member_repository
    )

    host_id = "test_user_001"

    # Act
    response = room_service.create_room(host_id)

    # Assert
    assert isinstance(response, RoomResponse)
    assert len(response.code) == 6
    assert response.host_id == host_id
    assert response.status == "waiting"

    room = room_repository.get_room(response.code)

    assert room["host_id"] == host_id
    assert room["status"] == "waiting"

    assert member_repository.member_exists(
        response.code,
        host_id
    )


def test_create_room_generates_unique_codes():
    # Arrange
    room_repository = RoomRepository(redis_client)
    member_repository = MemberRepository(redis_client)

    room_service = RoomService(
        room_repository,
        member_repository
    )

    host_1 = "test_user_001"
    host_2 = "test_user_002"

    # Act
    room1 = room_service.create_room(host_1)
    room2 = room_service.create_room(host_2)

    # Assert
    assert room1.code != room2.code


def test_get_room_success():
    # Arrange
    room_repository = RoomRepository(redis_client)
    member_repository = MemberRepository(redis_client)

    room_service = RoomService(
        room_repository,
        member_repository
    )

    host_id = "test_user_003"

    created_room = room_service.create_room(host_id)

    # Act
    response = room_service.get_room(created_room.code)

    # Assert
    assert isinstance(response, RoomResponse)
    assert response.code == created_room.code
    assert response.host_id == host_id
    assert response.status == "waiting"