from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import get_room_service, get_matching_service 
from app.schemas.room import CreateRoom, RoomResponse, JoinRoom, Decision
from app.services.room import RoomService
from  app.services.matching import MatchingService
import anyio
import json

from app.websockets.routes import manager

router = APIRouter(
    prefix="/rooms",
    tags=["Rooms"]
)


@router.post(
    "",
    response_model=RoomResponse,
    status_code=status.HTTP_201_CREATED
)
def create_room(
    data: CreateRoom,
    room_service: RoomService = Depends(get_room_service)
):
    return room_service.create_room(data.username)


@router.get(
    "/{code}",
    response_model=RoomResponse
)
def get_room(
    code: str,
    room_service: RoomService = Depends(get_room_service)
):
    try:
        return room_service.get_room(code)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room not found"
        )


@router.post(
    "/{code}/join",
    response_model=RoomResponse
)
def join_room(
    code: str,
    data: JoinRoom,
    room_service: RoomService = Depends(get_room_service)
):
    try:
        return room_service.join_room(code, data.username)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/{code}/leave")
def leave_room(
    code: str,
    data: JoinRoom,
    room_service: RoomService = Depends(get_room_service)
):
    try:
        return room_service.leave_room(code, data.username)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/{code}/start")
def start_room(
    code: str,
    data: JoinRoom,
    room_service: RoomService = Depends(get_room_service)
):
    try:
        return room_service.start_room(code, data.username)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/{code}/end")
def end_room(
    code: str,
    data: JoinRoom,
    room_service: RoomService = Depends(get_room_service)
):
    try:
        return room_service.end_room(code, data.username)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/{code}/rounds/{round_number}/decision")
def submit_decision(
    code: str,
    round_number: int,
    data: Decision,
    user_id: str,
    matching_service: MatchingService = Depends(
        get_matching_service
    ),
):
    try:
        result = matching_service.submit_decision(
        code=code,
        round_number=round_number,
    user_id=user_id,
    decision=data.decision,
)

        event_by_status = {
    "waiting": "decision_waiting",
    "completed": "round_completed",
    "ended": "session_ended",
}

        event = event_by_status.get(
    result.get("status"),
    "decision_updated",
)

        message = json.dumps({
    "event": event,
    "data": result,
})

        anyio.from_thread.run(
    manager.broadcast,
    code,
    message,
)

        return result
    except ValueError as e:
        message = str(e)

        if message == "Room not found":
            code_status = status.HTTP_404_NOT_FOUND
        elif message == "User is not a room member":
            code_status = status.HTTP_403_FORBIDDEN
        else:
            code_status = status.HTTP_400_BAD_REQUEST

        raise HTTPException(
            status_code=code_status,
            detail=message,
        )