import secrets
import string

from app.schemas.room import RoomResponse


class RoomService:
    def __init__(
        self,
        room_repository,
        member_repository,
        movie_service,
        movie_repository,
        session_repository=None,
    ):
        self.room_repository = room_repository
        self.member_repository = member_repository
        self.movie_service = movie_service
        self.movie_repository = movie_repository
        self.session_repository = session_repository

    def generate_room_code(self):
        characters = string.ascii_uppercase + string.digits
        return "".join(
            secrets.choice(characters) for _ in range(6)
        )

    def create_room(self, host_id):
        code = self.generate_room_code()

        while self.room_repository.room_exists(code):
            code = self.generate_room_code()

        try:
            self.room_repository.create_room(
                host_id=host_id,
                status="waiting",
                code=code,
            )

            self.member_repository.add_member(
                code=code,
                user_id=host_id,
            )

            movies = self.movie_service.get_movie_pool(
                pool_size=10
            )

            self.movie_repository.add_movies(
                code=code,
                movies=movies,
            )

        except Exception:
            self.movie_repository.delete_movies(code)

            if hasattr(self.member_repository, "delete_members"):
                self.member_repository.delete_members(code)
            else:
                for member_id in self.member_repository.get_members(code):
                    self.member_repository.remove_member(
                        code, member_id
                    )

            self.room_repository.delete_room(code)
            raise

        return RoomResponse(
            code=code,
            host_id=host_id,
            status="waiting",
        )

    def get_room(self, code):
        room = self.room_repository.get_room(code)

        if not room:
            raise ValueError("Room not found")

        return RoomResponse(
            code=code,
            host_id=room["host_id"],
            status=room["status"],
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

        self.member_repository.add_member(
            code=code,
            user_id=user_id,
        )

        return RoomResponse(
            code=code,
            host_id=room["host_id"],
            status=room["status"],
        )

    def leave_room(self, code, user_id):
        room = self.room_repository.get_room(code)

        if not room:
            raise ValueError("Room does not exist")

        if room["status"] != "waiting":
            raise ValueError("Cannot leave an active room")

        if not self.member_repository.member_exists(code, user_id):
            raise ValueError("User is not a member")

        if room["host_id"] == user_id:
            members = self.member_repository.get_members(code)

            for member_id in members:
                self.member_repository.remove_member(
                    code, member_id
                )

            self.movie_repository.delete_movies(code)

            if self.session_repository:
                self.session_repository.delete_session(code)

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

        if room["host_id"] != user_id:
            if not self.member_repository.member_exists(
                code, user_id
            ):
                raise ValueError("User is not a member")

            raise ValueError("Only the host can start")

        if room["status"] != "waiting":
            raise ValueError("Room is already started or ended")

        members = self.member_repository.get_members(code)

        if len(members) < 2:
            raise ValueError(
                "At least 2 members are required to start"
            )

        if self.session_repository:
            self.session_repository.create_session(
                code=code,
                status="started",
                current_round=1,
            )

        self.room_repository.update_status(code, "started")

        return {
            "code": code,
            "status": "started",
        }

    def end_room(self, code, user_id):
        room = self.room_repository.get_room(code)

        if not room:
            raise ValueError("Room not found")

        if room["host_id"] != user_id:
            if not self.member_repository.member_exists(
                code, user_id
            ):
                raise ValueError("User is not a member")

            raise ValueError("Only the host can end")

        if room["status"] != "started":
            raise ValueError("Only an active room can be ended")

        self.room_repository.update_status(code, "ended")

        if self.session_repository:
            self.session_repository.update_session(
                code,
                status="ended",
            )

        return {
            "code": code,
            "status": "ended",
        }