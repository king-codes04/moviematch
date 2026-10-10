
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from app.dependencies import get_room_service, get_matching_service
from app.services.room import RoomService
from app.services.matching import MatchingService
from app.websockets.manager import ConnectionManager

router = APIRouter(tags=["WebSockets"])
manager = ConnectionManager()


@router.websocket("/ws/{code}")
async def room_websocket(
    websocket: WebSocket,
    code: str,
    user_id: str,
    room_service: RoomService = Depends(get_room_service),
    matching_service: MatchingService = Depends(get_matching_service),
):
    try:
        room_service.get_room(code)
    except ValueError:
        await websocket.close(code=1008, reason="Room not found")
        return

    if not matching_service.member_repository.member_exists(code, user_id):
        await websocket.close(
            code=1008,
            reason="User is not a room member",
        )
        return

    await manager.connect(code, websocket)

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(code, websocket)
