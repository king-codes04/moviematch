
from app.schemas.room import DecisionType


class MatchingService:
    def __init__(
        self,
        room_repository,
        member_repository,
        decision_repository,
        movie_repository=None,
        match_repository=None,
        session_repository=None,
    ):
        self.room_repository = room_repository
        self.member_repository = member_repository
        self.decision_repository = decision_repository
        self.movie_repository = movie_repository
        self.match_repository = match_repository
        self.session_repository = session_repository

    def submit_decision(self, code, round_number, user_id, decision):
        room = self.room_repository.get_room(code)

        if not room:
            raise ValueError("Room not found")

        if room.get("status") != "started":
            raise ValueError("Room is not started")

        if not self.member_repository.member_exists(code, user_id):
            raise ValueError("User is not a room member")

        if self.session_repository:
            session = self.session_repository.get_session(code)

            if not session:
                raise ValueError("Session not found")

            if session.get("status") != "started":
                raise ValueError("Session is not started")

            if int(session["current_round"]) != int(round_number):
                raise ValueError("Invalid round number")

        try:
            decision = DecisionType(decision).value
        except (ValueError, TypeError):
            raise ValueError("Invalid decision")

        recorded = self.decision_repository.submit_decision(
            code,
            round_number,
            user_id,
            decision,
        )

        if not recorded:
            raise ValueError("User has already decided")

        return self.evaluate_round(code, round_number)

    def evaluate_round(self, code, round_number):
        members = self.member_repository.get_members(code)
        decisions = self.decision_repository.get_decisions(
            code,
            round_number,
        )

        # Do not advance until every current member has decided.
        if not members.issubset(decisions.keys()):
            return {
                "status": "waiting",
                "round_number": int(round_number),
            }

        like_count = sum(
            decision == DecisionType.LIKE.value
            for decision in decisions.values()
        )
        matched = like_count >= 2

        # Keep compatibility with tests that use only the basic
        # decision-evaluation dependencies.
        if not all((
            self.movie_repository,
            self.match_repository,
            self.session_repository,
        )):
            return {
                "status": "completed",
                "round_number": int(round_number),
                "matched": matched,
                "like_count": like_count,
            }

        session = self.session_repository.get_session(code)

        if not session or session.get("status") != "started":
            raise ValueError("Session is not started")

        if int(session["current_round"]) != int(round_number):
            raise ValueError("Invalid round number")

        movies = self.movie_repository.get_movies(code)

        if not movies:
            self._end_session(code)

            return {
                "status": "ended",
                "round_number": int(round_number),
                "matched": matched,
                "like_count": like_count,
                "matched_movie": None,
                "next_movie": None,
                "next_round": None,
            }

        # Save the completed movie before removing it from the pool.
        completed_movie = movies[0]

        if matched:
            self.match_repository.add_match(code, completed_movie)

        # Remove the movie that every member just decided on.
        self.movie_repository.get_next_movie(code)

        remaining_movies = self.movie_repository.get_movies(code)

        # There is no next round when the pool is exhausted.
        if not remaining_movies:
            self._end_session(code)

            return {
                "status": "ended",
                "round_number": int(round_number),
                "matched": matched,
                "like_count": like_count,
                "matched_movie": completed_movie if matched else None,
                "next_movie": None,
                "next_round": None,
            }

        next_round = int(round_number) + 1

        self.session_repository.update_session(
            code,
            current_round=next_round,
        )

        return {
            "status": "completed",
            "round_number": int(round_number),
            "matched": matched,
            "like_count": like_count,
            "matched_movie": completed_movie if matched else None,
            "next_movie": remaining_movies[0],
            "next_round": next_round,
        }

    def _end_session(self, code):
        self.session_repository.update_session(
            code,
            status="ended",
        )
        self.room_repository.update_status(code, "ended")
