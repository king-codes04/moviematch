import pytest

from app.schemas.room import DecisionType
from app.services.matching import MatchingService


# ----------------------------
# Fake repositories
# ----------------------------

class FakeRoomRepository:
    def __init__(self, room=None):
        self.room = room

    def get_room(self, code):
        return self.room

    def update_status(self, code, status):
        if self.room is not None:
            self.room["status"] = status


class FakeMemberRepository:
    def __init__(self, members=None):
        self.members = set(members or [])

    def member_exists(self, code, user_id):
        return user_id in self.members

    def get_members(self, code):
        return self.members.copy()


class FakeDecisionRepository:
    def __init__(self):
        self.decisions = {}

    def submit_decision(self, code, round_number, user_id, decision):
        key = (code, round_number)
        round_decisions = self.decisions.setdefault(key, {})

        # A member cannot overwrite an existing decision.
        if user_id in round_decisions:
            return 0

        round_decisions[user_id] = decision
        return 1

    def get_decisions(self, code, round_number):
        return self.decisions.get(
            (code, round_number), {}
        ).copy()


class FakeMovieRepository:
    def __init__(self, movies=None):
        self.movies = list(movies or [])

    def add_movies(self, code, movies):
        self.movies = list(movies)

    def get_movies(self, code):
        return self.movies.copy()

    def get_next_movie(self, code):
        if not self.movies:
            return None
        return self.movies.pop(0)

    def movie_count(self, code):
        return len(self.movies)


class FakeMatchRepository:
    def __init__(self):
        self.matches = []

    def add_match(self, code, movie):
        self.matches.append(movie)

    def get_matches(self, code):
        return self.matches.copy()


class FakeSessionRepository:
    def __init__(self, session=None):
        self.session = dict(
            session
            if session is not None
            else {
                "status": "started",
                "current_round": 1,
            }
        )

    def get_session(self, code):
        return self.session.copy()

    def create_session(self, code, status, current_round=0):
        self.session = {
            "status": status,
            "current_round": str(current_round),
        }

    def update_session(self, code, **fields):
        self.session.update({
            key: str(value) if key == "current_round" else value
            for key, value in fields.items()
        })


# ----------------------------
# Test setup helper
# ----------------------------

def make_service(
    room=None,
    members=None,
    decisions=None,
    lifecycle=False,
    movies=None,
):
    room_repository = FakeRoomRepository(
        room if room is not None else {
            "host_id": "user_001",
            "status": "started",
        }
    )

    member_repository = FakeMemberRepository(
        members if members is not None else {
            "user_001",
            "user_002",
        }
    )

    decision_repository = (
        decisions if decisions is not None
        else FakeDecisionRepository()
    )

    movie_repository = None
    match_repository = None
    session_repository = None

    if lifecycle:
        movie_repository = FakeMovieRepository(movies)
        match_repository = FakeMatchRepository()
        session_repository = FakeSessionRepository()

    service = MatchingService(
        room_repository=room_repository,
        member_repository=member_repository,
        decision_repository=decision_repository,
        movie_repository=movie_repository,
        match_repository=match_repository,
        session_repository=session_repository,
    )

    return service, decision_repository


# ----------------------------
# Validation tests
# ----------------------------

def test_submit_decision_rejects_missing_room():
    service, _ = make_service(room={})

    with pytest.raises(ValueError, match="Room not found"):
        service.submit_decision(
            "TEST123", 1, "user_001", "like"
        )


def test_submit_decision_rejects_room_not_started():
    service, _ = make_service(
        room={
            "host_id": "user_001",
            "status": "waiting",
        }
    )

    with pytest.raises(ValueError, match="Room is not started"):
        service.submit_decision(
            "TEST123", 1, "user_001", "like"
        )


def test_submit_decision_rejects_non_member():
    service, _ = make_service(
        members={"user_001", "user_002"}
    )

    with pytest.raises(
        ValueError,
        match="User is not a room member",
    ):
        service.submit_decision(
            "TEST123", 1, "outsider", "like"
        )


def test_submit_decision_rejects_invalid_decision():
    service, _ = make_service()

    with pytest.raises(ValueError, match="Invalid decision"):
        service.submit_decision(
            "TEST123", 1, "user_001", "maybe"
        )


def test_submit_decision_rejects_duplicate_vote():
    service, _ = make_service()

    service.submit_decision(
        "TEST123", 1, "user_001", "like"
    )

    with pytest.raises(
        ValueError,
        match="User has already decided",
    ):
        service.submit_decision(
            "TEST123", 1, "user_001", "dislike"
        )


# ----------------------------
# Waiting and matching tests
# ----------------------------

def test_round_waits_until_every_member_decides():
    service, _ = make_service(
        members={"user_001", "user_002", "user_003"}
    )

    result = service.submit_decision(
        "TEST123", 1, "user_001", "like"
    )

    assert result == {
        "status": "waiting",
        "round_number": 1,
    }


def test_two_likes_produce_a_match():
    service, _ = make_service()

    service.submit_decision(
        "TEST123", 1, "user_001", "like"
    )

    result = service.submit_decision(
        "TEST123", 1, "user_002", "like"
    )

    assert result["status"] == "completed"
    assert result["round_number"] == 1
    assert result["matched"] is True
    assert result["like_count"] == 2


def test_one_like_does_not_produce_a_match():
    service, _ = make_service()

    service.submit_decision(
        "TEST123", 1, "user_001", "like"
    )

    result = service.submit_decision(
        "TEST123", 1, "user_002", "dislike"
    )

    assert result["status"] == "completed"
    assert result["matched"] is False
    assert result["like_count"] == 1


def test_no_likes_does_not_produce_a_match():
    service, _ = make_service()

    service.submit_decision(
        "TEST123", 1, "user_001", "dislike"
    )

    result = service.submit_decision(
        "TEST123", 1, "user_002", "dislike"
    )

    assert result["status"] == "completed"
    assert result["matched"] is False
    assert result["like_count"] == 0


def test_string_and_enum_decisions_are_accepted():
    service, _ = make_service()

    service.submit_decision(
        "TEST123", 1, "user_001", DecisionType.LIKE
    )

    result = service.submit_decision(
        "TEST123", 1, "user_002", DecisionType.DISLIKE
    )

    assert result["status"] == "completed"
    assert result["matched"] is False


# ----------------------------
# Direct evaluation tests
# ----------------------------

def test_evaluate_round_waits_for_missing_decision():
    service, decisions = make_service(
        members={"user_001", "user_002"}
    )

    decisions.submit_decision(
        "TEST123", 1, "user_001", "like"
    )

    result = service.evaluate_round("TEST123", 1)

    assert result == {
        "status": "waiting",
        "round_number": 1,
    }


def test_evaluate_round_counts_only_likes():
    service, decisions = make_service(
        members={"user_001", "user_002", "user_003"}
    )

    decisions.submit_decision(
        "TEST123", 1, "user_001", "like"
    )
    decisions.submit_decision(
        "TEST123", 1, "user_002", "like"
    )
    decisions.submit_decision(
        "TEST123", 1, "user_003", "dislike"
    )

    result = service.evaluate_round("TEST123", 1)

    assert result["status"] == "completed"
    assert result["like_count"] == 2
    assert result["matched"] is True


def test_decisions_from_another_round_are_not_counted():
    service, decisions = make_service()

    decisions.submit_decision(
        "TEST123", 1, "user_001", "like"
    )
    decisions.submit_decision(
        "TEST123", 2, "user_002", "like"
    )

    result = service.evaluate_round("TEST123", 1)

    assert result["status"] == "waiting"


# ----------------------------
# Full matching lifecycle tests
# ----------------------------

def test_matching_movie_is_saved_and_next_round_starts():
    movies = [
        {"id": 101, "title": "Movie One"},
        {"id": 102, "title": "Movie Two"},
    ]

    service, _ = make_service(
        lifecycle=True,
        movies=movies,
    )

    service.submit_decision(
        "TEST123", 1, "user_001", "like"
    )

    result = service.submit_decision(
        "TEST123", 1, "user_002", "like"
    )

    assert result["status"] == "completed"
    assert result["matched"] is True
    assert result["next_round"] == 2

    assert service.match_repository.get_matches(
        "TEST123"
    ) == [movies[0]]

    assert service.movie_repository.get_movies(
        "TEST123"
    ) == [movies[1]]

    assert service.session_repository.get_session(
        "TEST123"
    )["current_round"] == "2"


def test_unmatched_movie_is_not_saved():
    movies = [
        {"id": 101, "title": "Movie One"},
        {"id": 102, "title": "Movie Two"},
    ]

    service, _ = make_service(
        lifecycle=True,
        movies=movies,
    )

    service.submit_decision(
        "TEST123", 1, "user_001", "like"
    )

    result = service.submit_decision(
        "TEST123", 1, "user_002", "dislike"
    )

    assert result["matched"] is False
    assert service.match_repository.get_matches("TEST123") == []
    assert service.movie_repository.get_movies("TEST123") == [movies[1]]


def test_round_does_not_advance_until_every_member_decides():
    movies = [
        {"id": 101, "title": "Movie One"},
        {"id": 102, "title": "Movie Two"},
    ]

    service, _ = make_service(
        lifecycle=True,
        members={"user_001", "user_002", "user_003"},
        movies=movies,
    )

    result = service.submit_decision(
        "TEST123", 1, "user_001", "like"
    )

    assert result["status"] == "waiting"
    assert service.movie_repository.get_movies("TEST123") == movies
    assert int(service.session_repository.get_session(
        "TEST123"
    )["current_round"]) == 1


def test_final_movie_ends_session_and_room():
    movies = [
        {"id": 101, "title": "Final Movie"},
    ]

    service, _ = make_service(
        lifecycle=True,
        movies=movies,
    )

    service.submit_decision(
        "TEST123", 1, "user_001", "like"
    )

    result = service.submit_decision(
        "TEST123", 1, "user_002", "like"
    )

    assert result["status"] == "ended"
    assert result["matched"] is True
    assert service.match_repository.get_matches("TEST123") == movies
    assert service.movie_repository.get_movies("TEST123") == []
    assert service.session_repository.get_session(
        "TEST123"
    )["status"] == "ended"
    assert service.room_repository.get_room(
        "TEST123"
    )["status"] == "ended"


def test_submit_decision_rejects_wrong_session_round():
    service, _ = make_service(lifecycle=True)

    with pytest.raises(ValueError, match="Invalid round number"):
        service.submit_decision(
            "TEST123", 2, "user_001", "like"
        )


def test_submit_decision_rejects_missing_session():
    service, _ = make_service(lifecycle=True)
    service.session_repository.session = {}

    with pytest.raises(ValueError, match="Session not found"):
        service.submit_decision(
            "TEST123", 1, "user_001", "like"
        )
