
import anyio
import json

from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import get_room_service, get_matching_service
from app.schemas.room import (
    CreateRoom,
    Decision,
    DecisionResponse,
    JoinRoom,
    MoviePoolResponse,
    MovieResponse,
    RoomResponse,
    RoomStateResponse,
)
from app.services.room import RoomService
from app.services.matching import MatchingService
from app.websockets.routes import manager


router = APIRouter(
    prefix="/rooms",
    tags=["Rooms"],
)


def serialize_data(value):
    """Convert Pydantic models to JSON-compatible data."""
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")

    if hasattr(value, "dict"):
        return value.dict()

    return value


async def broadcast_event(room_code: str, event: str, data):
    """Send a consistently structured event to room members."""
    message = json.dumps({
        "event": event,
        "data": serialize_data(data),
    })

    await manager.broadcast(room_code, message)


def publish_event(room_code: str, event: str, data):
    """Publish an event from a synchronous route."""
    anyio.from_thread.run(
        broadcast_event,
        room_code,
        event,
        data,
    )


def raise_room_error(error: ValueError):
    """Convert service errors to HTTP errors."""
    message = str(error)

    if message == "Room not found":
        code_status = status.HTTP_404_NOT_FOUND
    elif message == "Movie is not in this room's pool":
        code_status = status.HTTP_404_NOT_FOUND
    elif message == "User is not a room member":
        code_status = status.HTTP_403_FORBIDDEN
    elif message.startswith("Decision is already recorded and cannot be changed"):
        code_status = status.HTTP_409_CONFLICT
    elif message == "Room is not started":
        code_status = status.HTTP_409_CONFLICT
    else:
        code_status = status.HTTP_400_BAD_REQUEST

    raise HTTPException(
        status_code=code_status,
        detail=message,
    )


@router.post(
    "",
    response_model=RoomResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_room(
    data: CreateRoom,
    room_service: RoomService = Depends(get_room_service),
):
    return room_service.create_room(data.username)


@router.get(
    "/{code}",
    response_model=RoomResponse,
)
def get_room(
    code: str,
    room_service: RoomService = Depends(get_room_service),
):
    try:
        return room_service.get_room(code)
    except ValueError as error:
        raise_room_error(error)


@router.get(
    "/{code}/state",
    response_model=RoomStateResponse,
)
def get_room_state(
    code: str,
    user_id: str,
    room_service: RoomService = Depends(get_room_service),
):
    try:
        return room_service.get_room_state(code, user_id)
    except ValueError as error:
        raise_room_error(error)


@router.get(
    "/{code}/movies",
    response_model=MoviePoolResponse,
)
def get_movie_pool(
    code: str,
    user_id: str,
    room_service: RoomService = Depends(get_room_service),
):
    try:
        return {"movies": room_service.get_movie_pool(code, user_id)}
    except ValueError as error:
        raise_room_error(error)


@router.post(
    "/{code}/join",
    response_model=RoomResponse,
)
def join_room(
    code: str,
    data: JoinRoom,
    room_service: RoomService = Depends(get_room_service),
):
    try:
        room = room_service.join_room(code, data.username)

        publish_event(
            code,
            "member_joined",
            {
                "username": data.username,
                "room": serialize_data(room),
            },
        )

        return room

    except ValueError as error:
        # Preserve the existing join endpoint's HTTP 400 behavior.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        )


@router.post("/{code}/leave")
def leave_room(
    code: str,
    data: JoinRoom,
    room_service: RoomService = Depends(get_room_service),
):
    try:
        result = room_service.leave_room(code, data.username)

        if "cancelled" in result.get("message", "").lower():
            publish_event(
                code,
                "room_ended",
                {
                    "code": code,
                    "status": "ended",
                    "reason": "cancelled",
                },
            )
        else:
            publish_event(
                code,
                "member_left",
                {"username": data.username},
            )

        return result

    except ValueError as error:
        raise_room_error(error)


@router.post("/{code}/start")
def start_room(
    code: str,
    data: JoinRoom,
    room_service: RoomService = Depends(get_room_service),
):
    try:
        result = room_service.start_room(code, data.username)

        publish_event(
            code,
            "room_started",
            serialize_data(result),
        )

        return result

    except ValueError as error:
        raise_room_error(error)


@router.post("/{code}/end")
def end_room(
    code: str,
    data: JoinRoom,
    room_service: RoomService = Depends(get_room_service),
):
    try:
        result = room_service.end_room(code, data.username)

        publish_event(
            code,
            "room_ended",
            serialize_data(result),
        )

        return result

    except ValueError as error:
        raise_room_error(error)


@router.post(
    "/{code}/movies/{movie_id}/decision",
    response_model=DecisionResponse,
)
def submit_decision(
    code: str,
    movie_id: int,
    data: Decision,
    user_id: str,
    matching_service: MatchingService = Depends(get_matching_service),
):
    try:
        result = matching_service.submit_decision(
            code=code,
            movie_id=movie_id,
            user_id=user_id,
            decision=data.decision,
        )

        if not result["duplicate"]:
            publish_event(
                code,
                "decision_recorded",
                {"movie_id": movie_id},
            )
        if result["new_match"]:
            publish_event(
                code,
                "match_found",
                {"movie": serialize_data(result["match"])},
            )

        return result

    except ValueError as error:
        raise_room_error(error)
