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
        decision_repository=None,
        match_repository=None,
    ):
        self.room_repository = room_repository
        self.member_repository = member_repository
        self.movie_service = movie_service
        self.movie_repository = movie_repository
        self.session_repository = session_repository
        self.decision_repository = decision_repository
        self.match_repository = match_repository

    def _delete_room_state(self, code):
        """Remove all Redis data belonging to a cancelled room."""
        client = self.room_repository.client
        keys = [
            f"ROOM:{code}",
            f"ROOM:{code}:MEMBERS",
            f"MOVIES:{code}",
            f"MOVIES:{code}:BY_ID",
            f"SESSION:{code}",
            f"MATCHES:{code}",
            f"MATCHES:{code}:IDS",
            f"MATCHES:{code}:BY_ID",
        ]

        keys.extend(
            client.scan_iter(match=f"DECISIONS:{code}:*")
        )

        if keys:
            client.delete(*keys)

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

    def get_movie_pool(self, code, user_id):
        room = self.room_repository.get_room(code)

        if not room:
            raise ValueError("Room not found")

        if not self.member_repository.member_exists(code, user_id):
            raise ValueError("User is not a room member")

        if room["status"] != "started":
            raise ValueError("Room is not started")

        movies = self.movie_repository.get_movies(code)

        if not movies:
            raise ValueError("Movie pool is unavailable")

        decisions = {}
        if self.decision_repository:
            decisions = self.decision_repository.get_user_decisions(
                code,
                user_id,
                [movie["id"] for movie in movies],
            )

        return [
            {
                **movie,
                "my_decision": decisions.get(movie["id"]),
            }
            for movie in movies
        ]

    def get_room_state(self, code, user_id):
        room = self.room_repository.get_room(code)
        if not room:
            raise ValueError("Room not found")

        if not self.member_repository.member_exists(code, user_id):
            raise ValueError("User is not a room member")

        movies = []
        matches = []
        if room["status"] in {"started", "ended"}:
            movies = self.movie_repository.get_movies(code)
            decisions = {}
            if self.decision_repository:
                decisions = self.decision_repository.get_user_decisions(
                    code,
                    user_id,
                    [movie["id"] for movie in movies],
                )
            movies = [
                {
                    **movie,
                    "my_decision": decisions.get(movie["id"]),
                }
                for movie in movies
            ]
            if self.match_repository:
                matches = self.match_repository.get_matches(code)

        return {
            "room": RoomResponse(
                code=code,
                host_id=room["host_id"],
                status=room["status"],
            ),
            "members": sorted(
                self.member_repository.get_members(code)
            ),
            "movies": movies,
            "matches": matches,
        }

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

            self._delete_room_state(code)

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

        movies = self.movie_service.get_movie_pool(pool_size=10)
        self.movie_repository.add_movies(code=code, movies=movies)

        try:
            if self.session_repository:
                self.session_repository.create_session(
                    code=code,
                    status="started",
                )

            self.room_repository.update_status(code, "started")
        except Exception:
            self.movie_repository.delete_movies(code)
            if self.session_repository:
                self.session_repository.delete_session(code)
            raise

        return {
            "code": code,
            "status": "started",
            "movie_count": len(movies),
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