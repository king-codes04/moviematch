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
    assert repo.session_exists(TEST_CODE) == 1

    repo.update_session(TEST_CODE, status="ended")
    assert repo.get_session(TEST_CODE)["status"] == "ended"

    repo.delete_session(TEST_CODE)

    assert repo.session_exists(TEST_CODE) == 0


def test_decision_repository():
    repo = DecisionRepository(redis_client)
    rooms = RoomRepository(redis_client)
    members = MemberRepository(redis_client)
    movies = MovieRepository(redis_client)

    rooms.create_room("user_001", "started", TEST_CODE)
    members.add_member(TEST_CODE, "user_001")
    members.add_member(TEST_CODE, "user_002")
    movies.add_movie(TEST_CODE, {"id": 123, "title": "Example"})

    first = repo.submit_movie_decision(
        TEST_CODE, 123, "user_001", "like"
    )
    second = repo.submit_movie_decision(
        TEST_CODE, 123, "user_002", "skip"
    )
    upgraded = repo.submit_movie_decision(
        TEST_CODE, 123, "user_002", "like"
    )

    assert first == [1, 0]
    assert second == [1, 0]
    assert upgraded == [2, 1]
    assert repo.get_user_decisions(
        TEST_CODE, "user_001", [123]
    ) == {123: "like"}
    assert repo.get_user_decisions(
        TEST_CODE, "user_002", [123]
    ) == {123: "like"}


def test_movie_repository():
    repo = MovieRepository(redis_client)

    movie = {
        "id": 123,
        "title": "Example Movie"
    }

    repo.add_movie(TEST_CODE, movie)
    repo.add_movie(TEST_CODE, movie)

    assert repo.get_movies(TEST_CODE) == [movie]
    assert repo.movie_count(TEST_CODE) == 1
    assert repo.get_movie(TEST_CODE, 123) == movie

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



def test_match_repository_returns_match_by_movie_id():
    repo = MatchRepository(redis_client)
    movie = {"id": 456, "title": "Matched Movie"}

    assert repo.add_match(TEST_CODE, movie) == 1
    assert repo.add_match(TEST_CODE, movie) == 0
    assert repo.get_match(TEST_CODE, 456) == movie
    assert repo.has_match(TEST_CODE, 456)
    assert repo.get_matches(TEST_CODE) == [movie]
