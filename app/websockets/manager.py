from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[str, set[WebSocket]] = {}

    async def connect(self, room_code: str, websocket: WebSocket):
        await websocket.accept()

        if room_code not in self.active_connections:
            self.active_connections[room_code] = set()

        self.active_connections[room_code].add(websocket)
    
    def disconnect(self, room_code: str, websocket: WebSocket):
        connections = self.active_connections.get(room_code)

        if connections is None:
            return

        connections.discard(websocket)

    
    async def broadcast(self, room_code: str, message: str):
        connections = self.active_connections.get(room_code)

        if not connections:
            return

        for websocket in connections.copy():
            await websocket.send_text(message)

