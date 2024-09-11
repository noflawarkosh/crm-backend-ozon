from typing import Annotated
from sqlalchemy import text, ForeignKey, JSON, Column
from sqlalchemy.orm import Mapped, mapped_column, relationship
import datetime

from orders.models import Base

pk = Annotated[int, mapped_column(primary_key=True)]
dt = Annotated[datetime.datetime, mapped_column(server_default=text('NOW()'))]


class AdminUserModel(Base):
    __tablename__ = 'admin_user'

    id: Mapped[pk]
    name: Mapped[str]
    surname: Mapped[str]
    fathername: Mapped[str | None]
    username: Mapped[str]
    post: Mapped[str]
    level: Mapped[int]
    password: Mapped[str]
    is_active: Mapped[bool] = mapped_column(default=True)


class AdminSessionModel(Base):
    __tablename__ = 'admin_user_sessions'

    id: Mapped[pk]
    ip: Mapped[str]
    user_agent: Mapped[str]
    token: Mapped[str]
    date: Mapped[dt]
    expires: Mapped[datetime.datetime]

    user_id: Mapped[int] = mapped_column(
        ForeignKey('admin_user.id', ondelete='CASCADE', onupdate='CASCADE')
    )

    admin: Mapped[AdminUserModel] = relationship(lazy=False)


class CrmSettingsModel(Base):
    __tablename__ = 'crm_settings'

    id: Mapped[pk]
    parser_useragent: Mapped[str]
    parser_cookies: Mapped[str]
