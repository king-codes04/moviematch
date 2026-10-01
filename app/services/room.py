import secrets
import string
from app.schemas.room import RoomResponse
class RoomService:
    def __init__(self, room_repository, member_repository):
        self.room_repository = room_repository
        self.member_repository = member_repository

    def generate_room_code(self):
        characters = string.ascii_uppercase + string.digits

        code = ''.join(
            secrets.choice(characters)  for _ in range(6)
        )
        return code
    
    def create_room(self, host_id):
        code = self.generate_room_code()

        while self.room_repository.room_exists(code):
            code = self.generate_room_code()

        self.room_repository.create_room(
            host_id=host_id,
            status="waiting",
            code=code
        )

        self.member_repository.add_member(
                   code=code,
                   user_id=host_id
               )
        return RoomResponse(
            code=code,
            host_id=host_id,
            status="waiting"
        )

    def get_room(self, code):
        room = self.room_repository.get_room(code)

        if not room:
            raise ValueError("Room not found")



        return RoomResponse(
            code=code,
            host_id=room["host_id"],
            status=room["status"]
        )