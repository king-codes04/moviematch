
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
            secrets.choice(characters) for _ in range(6)
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

    def join_room(self, code, user_id):
        room = self.room_repository.get_room(code)

        if not room:
            raise ValueError("Room not found")

        if room["status"] != "waiting":
            raise ValueError("Room is not accepting new members")

        if self.member_repository.member_exists(code, user_id):
            raise ValueError("User is already a member")

        members = self.member_repository.get_members(code)

        if len(members) >= 3:
            raise ValueError("Room is full")

        self.member_repository.add_member(code, user_id)

        return RoomResponse(
            code=code,
            host_id=room["host_id"],
            status=room["status"]
        )

    def leave_room(self, code, user_id):
        room = self.room_repository.get_room(code)

        if not room:
            raise ValueError("Room does not exist")

        if not self.member_repository.member_exists(code, user_id):
            raise ValueError("User is not a member of this room")

        if room["status"] != "waiting":
            raise ValueError("Cannot leave an active room")

        if room["host_id"] == user_id:
            members = self.member_repository.get_members(code)

            for member_id in members:
                self.member_repository.remove_member(code, member_id)

            self.room_repository.delete_room(code)

            return {
                "message": "Host left. Room has been cancelled"
            }

        self.member_repository.remove_member(code, user_id)

        return {
            "message": "User left the room successfully"
        }

    def start_room(self, code, user_id):
        room = self.room_repository.get_room(code)

        if not room:
            raise ValueError("Room not found")

        if not self.member_repository.member_exists(code, user_id):
            raise ValueError("User is not a member of this room")

        if room["host_id"] != user_id:
            raise ValueError("Only the host can start the room")

        if room["status"] != "waiting":
            raise ValueError("Room has already started or ended")

        members = self.member_repository.get_members(code)

        if len(members) < 2:
            raise ValueError("At least 2 members are required to start")

        self.room_repository.update_room(code, "started")

        return {
            "message": "Room started successfully",
            "code": code,
            "status": "started"
        }

    def end_room(self, code, user_id):
        room = self.room_repository.get_room(code)

        if not room:
            raise ValueError("Room not found")

        if not self.member_repository.member_exists(code, user_id):
            raise ValueError("User is not a member of this room")

        if room["host_id"] != user_id:
            raise ValueError("Only the host can end the room")

        if room["status"] != "started":
            raise ValueError("Only an active room can be ended")

        self.room_repository.update_room(code, "ended")

        return {
            "message": "Room ended successfully",
            "code": code,
            "status": "ended"
        }