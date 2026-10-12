
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

    def submit_decision(self, code, movie_id, user_id, decision):
        try:
            decision = DecisionType(decision).value
        except (ValueError, TypeError):
            raise ValueError("Invalid decision")

        if decision == DecisionType.DISLIKE.value:
            decision = DecisionType.SKIP.value

        result_code, match_created = self.decision_repository.submit_movie_decision(
            code,
            movie_id,
            user_id,
            decision,
        )

        errors = {
            -1: "Room not found",
            -2: "User is not a room member",
            -3: "Movie is not in this room's pool",
            -4: "Decision is already recorded and cannot be changed from like to skip",
            -5: "Room is not started",
        }
        if result_code in errors:
            raise ValueError(errors[result_code])

        duplicate = result_code == 0
        matched = bool(match_created) or self.match_repository.has_match(
            code,
            movie_id,
        )
        match = (
            self.match_repository.get_match(code, movie_id)
            if matched
            else None
        )

        return {
            "movie_id": int(movie_id),
            "decision": decision,
            "duplicate": duplicate,
            "matched": matched,
            "new_match": result_code == 2,
            "match": match,
        }
