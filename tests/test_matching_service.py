from concurrent.futures import ThreadPoolExecutor
import uuid

import pytest

from app.core.redis import redis_client
from app.repositories.decision import DecisionRepository
from app.repositories.match import MatchRepository
from app.repositories.member import MemberRepository
from app.repositories.movie import MovieRepository
from app.repositories.room import RoomRepository
from app.schemas.room import DecisionType
from app.services.matching import MatchingService


MOVIES = [
    {"id": 101, "title": "Movie One"},
    {"id": 202, "title": "Movie Two"},
]


@pytest.fixture
def matching_context():
    code = f"MS{uuid.uuid4().hex[:6].upper()}"
    room_repository = RoomRepository(redis_client)
    member_repository = MemberRepository(redis_client)
    movie_repository = MovieRepository(redis_client)
    decision_repository = DecisionRepository(redis_client)
    match_repository = MatchRepository(redis_client)

    room_repository.create_room("host", "started", code)
    for user_id in ("host", "member", "third"):
        member_repository.add_member(code, user_id)
    movie_repository.add_movies(code, MOVIES)

    service = MatchingService(
        room_repository=room_repository,
        member_repository=member_repository,
        decision_repository=decision_repository,
        movie_repository=movie_repository,
        match_repository=match_repository,
    )

    try:
        yield code, service, movie_repository, match_repository
    finally:
        keys = list(redis_client.scan_iter(match=f"ROOM:{code}*"))
        keys.extend(redis_client.scan_iter(match=f"MOVIES:{code}*"))
        keys.extend(redis_client.scan_iter(match=f"DECISIONS:{code}:*"))
        keys.extend(redis_client.scan_iter(match=f"MATCHES:{code}*"))
        if keys:
            redis_client.delete(*set(keys))


def test_member_can_decide_on_different_movies_without_waiting(
    matching_context,
):
    code, service, movies, matches = matching_context

    first = service.submit_decision(code, 101, "host", "like")
    second = service.submit_decision(code, 202, "member", "skip")

    assert first["decision"] == "like"
    assert first["matched"] is False
    assert second["decision"] == "skip"
    assert second["duplicate"] is False
    assert movies.get_movies(code) == MOVIES
    assert matches.get_matches(code) == []


def test_two_distinct_likes_create_one_match(matching_context):
    code, service, _, matches = matching_context

    first = service.submit_decision(code, 101, "host", "like")
    second = service.submit_decision(code, 101, "member", "like")

    assert first["matched"] is False
    assert second["matched"] is True
    assert second["new_match"] is True
    assert second["match"] == MOVIES[0]
    assert matches.get_matches(code) == [MOVIES[0]]


def test_same_decision_retry_is_idempotent_and_conflict_is_rejected(
    matching_context,
):
    code, service, _, matches = matching_context

    first = service.submit_decision(code, 101, "host", "like")
    retry = service.submit_decision(code, 101, "host", "like")

    assert first["duplicate"] is False
    assert retry["duplicate"] is True
    assert retry["decision"] == "like"
    assert matches.get_matches(code) == []

    with pytest.raises(ValueError, match="cannot be changed"):
        service.submit_decision(code, 101, "host", "skip")


def test_skip_can_be_upgraded_to_like_but_never_counts_retries_twice(
    matching_context,
):
    code, service, _, matches = matching_context

    skipped = service.submit_decision(code, 101, "host", "skip")
    upgraded = service.submit_decision(code, 101, "host", "like")
    retry = service.submit_decision(code, 101, "host", "like")

    assert skipped["decision"] == "skip"
    assert upgraded["decision"] == "like"
    assert upgraded["duplicate"] is False
    assert upgraded["matched"] is False
    assert retry["duplicate"] is True
    assert matches.get_matches(code) == []

    with pytest.raises(ValueError, match="cannot be changed"):
        service.submit_decision(code, 101, "host", "skip")


def test_skip_to_like_upgrade_can_create_a_match_once(matching_context):
    code, service, _, matches = matching_context

    service.submit_decision(code, 101, "host", "skip")
    service.submit_decision(code, 101, "member", "like")
    upgraded = service.submit_decision(code, 101, "host", "like")

    assert upgraded["matched"] is True
    assert upgraded["new_match"] is True
    assert upgraded["match"] == MOVIES[0]
    assert matches.get_matches(code) == [MOVIES[0]]


def test_third_member_like_does_not_duplicate_a_match(matching_context):
    code, service, _, matches = matching_context

    service.submit_decision(code, 101, "host", "like")
    service.submit_decision(code, 101, "member", "like")
    result = service.submit_decision(code, 101, "third", "like")

    assert result["matched"] is True
    assert result["new_match"] is False
    assert matches.match_count(code) == 1


def test_concurrent_second_likes_create_one_match(matching_context):
    code, service, _, matches = matching_context

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(
            lambda user_id: service.submit_decision(
                code, 101, user_id, "like"
            ),
            ("host", "member"),
        ))

    assert sum(result["new_match"] for result in results) == 1
    assert matches.get_matches(code) == [MOVIES[0]]


@pytest.mark.parametrize(
    ("user_id", "movie_id", "decision", "message"),
    [
        ("outsider", 101, "like", "not a room member"),
        ("host", 999, "like", "not in this room's pool"),
        ("host", 101, "maybe", "Invalid decision"),
    ],
)
def test_invalid_decisions_are_rejected(
    matching_context,
    user_id,
    movie_id,
    decision,
    message,
):
    code, service, _, _ = matching_context

    with pytest.raises(ValueError, match=message):
        service.submit_decision(code, movie_id, user_id, decision)


def test_decisions_are_rejected_for_waiting_rooms(matching_context):
    code, service, _, _ = matching_context
    service.room_repository.update_status(code, "waiting")

    with pytest.raises(ValueError, match="Room is not started"):
        service.submit_decision(code, 101, "host", DecisionType.LIKE)


def test_legacy_dislike_value_is_stored_as_skip(matching_context):
    code, service, _, _ = matching_context

    result = service.submit_decision(code, 101, "host", "dislike")

    assert result["decision"] == "skip"
