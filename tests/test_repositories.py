from app.core.redis import redis_client

from app.repositories.room import RoomRepository
from app.repositories.member import MemberRepository
from app.repositories.session import SessionRepository
from app.repositories.decision import DecisionRepository
from app.repositories.movie import MovieRepository
from app.repositories.match import MatchRepository
import pytest

TEST_CODE = "TEST123"


def cleanup():
    keys = redis_client.keys(f"*{TEST_CODE}*")

    if keys:
        redis_client.delete(*keys)
        
@pytest.fixture(autouse=True)
def clean_test_data():
    cleanup()
    yield
    cleanup()

def test_room_repository():
    repo = RoomRepository(redis_client)

    repo.create_room("user_001", "waiting", TEST_CODE)

    room = repo.get_room(TEST_CODE)

    assert room["host_id"] == "user_001"
    assert room["status"] == "waiting"
    assert repo.room_exists(TEST_CODE) == 1

    repo.update_room(TEST_CODE, "started")

    assert repo.get_room(TEST_CODE)["status"] == "started"

    repo.delete_room(TEST_CODE)

    assert repo.room_exists(TEST_CODE) == 0


def test_member_repository():
    repo = MemberRepository(redis_client)

    repo.add_member(TEST_CODE, "user_001")
    repo.add_member(TEST_CODE, "user_002")

    members = repo.get_members(TEST_CODE)

    assert members == {"user_001", "user_002"}
    assert repo.member_exists(TEST_CODE, "user_001")

    repo.remove_member(TEST_CODE, "user_001")

    assert not repo.member_exists(TEST_CODE, "user_001")


def test_session_repository():
    repo = SessionRepository(redis_client)

    repo.create_session(TEST_CODE, "started")

    session = repo.get_session(TEST_CODE)

    assert session["status"] == "started"
    assert session["current_round"] == "0"
    assert repo.session_exists(TEST_CODE) == 1

    repo.update_session(TEST_CODE, current_round=1)

    assert repo.get_session(TEST_CODE)["current_round"] == "1"

    repo.delete_session(TEST_CODE)

    assert repo.session_exists(TEST_CODE) == 0


def test_decision_repository():
    repo = DecisionRepository(redis_client)

    repo.submit_decision(TEST_CODE, 1, "user_001", "like")
    repo.submit_decision(TEST_CODE, 1, "user_002", "dislike")

    decisions = repo.get_decisions(TEST_CODE, 1)

    assert decisions == {
        "user_001": "like",
        "user_002": "dislike"
    }

    assert repo.get_user_decision(TEST_CODE, 1, "user_001") == "like"
    assert repo.has_decided(TEST_CODE, 1, "user_001") is True

    repo.delete_round_decisions(TEST_CODE, 1)

    assert repo.get_decisions(TEST_CODE, 1) == {}


def test_movie_repository():
    repo = MovieRepository(redis_client)

    movie = {
        "id": 123,
        "title": "Example Movie"
    }

    repo.add_movie(TEST_CODE, movie)

    assert repo.get_movies(TEST_CODE) == [movie]
    assert repo.movie_count(TEST_CODE) == 1

    next_movie = repo.get_next_movie(TEST_CODE)

    assert next_movie == movie
    assert repo.movie_count(TEST_CODE) == 0

    assert repo.get_next_movie(TEST_CODE) is None

    repo.delete_movies(TEST_CODE)


def test_match_repository():
    repo = MatchRepository(redis_client)

    movie = {
        "id": 456,
        "title": "Matched Movie"
    }

    repo.add_match(TEST_CODE, movie)

    assert repo.get_matches(TEST_CODE) == [movie]
    assert repo.match_count(TEST_CODE) == 1

    repo.delete_matches(TEST_CODE)

    assert repo.get_matches(TEST_CODE) == []



def test_duplicate_decision_is_not_overwritten():
    repo = DecisionRepository(redis_client)

    first = repo.submit_decision(
        TEST_CODE, 1, "emanuel", "like"
    )

    second = repo.submit_decision(
        TEST_CODE, 1, "emanuel", "dislike"
    )

    assert first == 1
    assert second == 0

    assert repo.get_user_decision(
        TEST_CODE, 1, "emanuel"
    ) == "like"
