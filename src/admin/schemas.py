from datetime import datetime
from pydantic import BaseModel


class FileSchema(BaseModel):
    filename: str
    size: int
    content: bytes
    href: str


class AdminReadSchema(BaseModel):
    id: int
    name: str
    username: str
    fathername: str
    post: str


class AdminReadWPSchema(AdminReadSchema):
    password: str


class AdminSessionCreateSchema(BaseModel):
    token: str
    user_agent: str
    ip: str
    expires: datetime
    user_id: int


class AdminSessionReadSchema(AdminSessionCreateSchema):
    id: int
    date: datetime
