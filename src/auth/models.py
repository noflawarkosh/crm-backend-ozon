import datetime
from typing import Annotated
from sqlalchemy import text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base

pk = Annotated[int, mapped_column(primary_key=True)]
dt = Annotated[datetime.datetime, mapped_column(server_default=text('NOW()'))]


# User
class UserModel(Base):
    __tablename__ = 'user'

    id: Mapped[pk]
    name: Mapped[str]
    username: Mapped[str]
    email: Mapped[str]
    telnum: Mapped[str]
    telegram: Mapped[str]
    password: Mapped[str]
    status: Mapped[int]
    media: Mapped[str | None]


# Session
class UserSessionModel(Base):
    __tablename__ = 'user_session'

    id: Mapped[pk]
    token: Mapped[str]
    useragent: Mapped[str]
    ip: Mapped[str]
    created: Mapped[dt]
    expires: Mapped[datetime.datetime]

    # FK
    user_id: Mapped[int] = mapped_column(
        ForeignKey('user.id', ondelete='CASCADE', onupdate='CASCADE')
    )

    # Relationships
    user: Mapped['UserModel'] = relationship(lazy=False)
