from enum import Enum

from pydantic import BaseModel


class CreateRoom(BaseModel):
    username: str


class JoinRoom(BaseModel):
    username: str


class DecisionType(Enum):
    LIKE = "like"
    DISLIKE = "dislike"


class Decision(BaseModel):
    decision: DecisionType

class RoomResponse(BaseModel):
    code:str
    host_id:str
    status:str