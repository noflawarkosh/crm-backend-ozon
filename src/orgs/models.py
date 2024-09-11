from typing import Annotated
from sqlalchemy import text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
import datetime

from auth.models import Base

pk = Annotated[int, mapped_column(primary_key=True)]
dt = Annotated[datetime.datetime, mapped_column(server_default=text('NOW()'))]


# Organization
class OrganizationModel(Base):
    __tablename__ = 'organization'

    id: Mapped[pk]
    title: Mapped[str]
    inn: Mapped[str]
    status: Mapped[int]
    created_at: Mapped[dt]
    is_competitor: Mapped[bool] = mapped_column(default=False)
    balance_limit: Mapped[int | None] = mapped_column(default=-1000)

    server_id: Mapped[int | None] = mapped_column(
        ForeignKey('orders_server.id', ondelete='CASCADE', onupdate='CASCADE')
    )
    level_id: Mapped[int | None] = mapped_column(
        ForeignKey('balance_prices.id')
    )

    # FK
    owner_id: Mapped[int] = mapped_column(
        ForeignKey('user.id', ondelete='CASCADE', onupdate='CASCADE')
    )

    # Relationships
    owner: Mapped['UserModel'] = relationship(lazy='noload')
    level: Mapped['BalancePricesModel'] = relationship(lazy='noload')
    server: Mapped['PickerServerModel'] = relationship(lazy='noload')


# Membership
class OrganizationMembershipModel(Base):
    __tablename__ = 'organization_membership'

    id: Mapped[pk]
    date: Mapped[dt]
    level: Mapped[int]
    status: Mapped[int]

    # FK
    user_id: Mapped[int] = mapped_column(
        ForeignKey('user.id', ondelete='CASCADE', onupdate='CASCADE')
    )
    org_id: Mapped[int] = mapped_column(
        ForeignKey('organization.id', ondelete='CASCADE', onupdate='CASCADE')
    )
    invitation_id: Mapped[int | None] = mapped_column(
        ForeignKey('organization_invitation.id', ondelete='CASCADE', onupdate='CASCADE')
    )

    # Relationships
    user: Mapped['UserModel'] = relationship(lazy='noload')
    invitation: Mapped['OrganizationInvitationModel'] = relationship(lazy='noload')
    organization: Mapped['OrganizationModel'] = relationship(lazy='noload')


# Invitation
class OrganizationInvitationModel(Base):
    __tablename__ = 'organization_invitation'

    id: Mapped[pk]
    code: Mapped[str]
    level: Mapped[int]
    created: Mapped[dt]
    expires: Mapped[datetime.datetime | None]
    amount: Mapped[int | None]

    # FK
    org_id: Mapped[int] = mapped_column(ForeignKey('organization.id', ondelete='CASCADE', onupdate='CASCADE'))
    usages: Mapped[list['OrganizationMembershipModel']] = relationship(
        primaryjoin="OrganizationInvitationModel.id == OrganizationMembershipModel.invitation_id",
        lazy='noload'
    )
