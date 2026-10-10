from app.core.redis import redis_client
from app.clients.tmdb import TMDBClient

from app.repositories.room import RoomRepository
from app.repositories.member import MemberRepository
from app.repositories.decision import DecisionRepository
from app.repositories.movie import MovieRepository
from app.repositories.match import MatchRepository
from app.repositories.session import SessionRepository

from app.services.movie import MovieService
from app.services.room import RoomService
from app.services.matching import MatchingService


def get_movie_service():
    tmdb_client = TMDBClient()

    return MovieService(
        tmdb_client=tmdb_client,
    )


def get_room_service():
    room_repository = RoomRepository(redis_client)
    member_repository = MemberRepository(redis_client)
    movie_repository = MovieRepository(redis_client)
    session_repository = SessionRepository(redis_client)

    movie_service = get_movie_service()

    return RoomService(
        room_repository=room_repository,
        member_repository=member_repository,
        movie_service=movie_service,
        movie_repository=movie_repository,
        session_repository=session_repository,
    )


def get_matching_service():
    room_repository = RoomRepository(redis_client)
    member_repository = MemberRepository(redis_client)
    decision_repository = DecisionRepository(redis_client)
    movie_repository = MovieRepository(redis_client)
    match_repository = MatchRepository(redis_client)
    session_repository = SessionRepository(redis_client)

    return MatchingService(
        room_repository=room_repository,
        member_repository=member_repository,
        decision_repository=decision_repository,
        movie_repository=movie_repository,
        match_repository=match_repository,
        session_repository=session_repository,
    )
