class RoomRepository:
    def __init__(self, client):
        self.client = client

    def create_room(self, host_id, status, code):
        self.client.hset(
            f"ROOM:{code}",
            mapping={
                "host_id": host_id,
                "status": status
            }
        )

    def get_room(self, code):
        return self.client.hgetall(f"ROOM:{code}")

    def room_exists(self, code):
        return self.client.exists(f"ROOM:{code}")

    def update_room(self, code, status):
        self.client.hset(
            f"ROOM:{code}",
            mapping={"status": status}
        )

    def delete_room(self, code):
        return self.client.delete(f"ROOM:{code}")