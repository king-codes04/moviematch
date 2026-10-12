from enum import Enum

from pydantic import BaseModel, Field


class CreateRoom(BaseModel):
    username: str


class JoinRoom(BaseModel):
    username: str


class DecisionType(Enum):
    LIKE = "like"
    SKIP = "skip"
    DISLIKE = "dislike"


class Decision(BaseModel):
    decision: DecisionType


class RoomResponse(BaseModel):
    code: str
    host_id: str
    status: str


class MovieResponse(BaseModel):
    id: int
    title: str
    overview: str | None = None
    poster_path: str | None = None
    release_date: str | None = None
    vote_average: float | None = None
    genre_ids: list[int] | None = Field(default_factory=list)


class MemberMovieResponse(MovieResponse):
    my_decision: str | None = None


class MoviePoolResponse(BaseModel):
    movies: list[MemberMovieResponse]


class DecisionResponse(BaseModel):
    movie_id: int
    decision: str
    duplicate: bool = False
    matched: bool = False
    new_match: bool = False
    match: MovieResponse | None = None


class RoomStateResponse(BaseModel):
    room: RoomResponse
    members: list[str]
    movies: list[MemberMovieResponse]
    matches: list[MovieResponse]