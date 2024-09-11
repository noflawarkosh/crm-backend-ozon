from sqlalchemy import select, and_, func, tuple_, update
from sqlalchemy.orm import selectinload

from database import async_session_factory

from orgs.models import (
    OrganizationModel,
    OrganizationInvitationModel,
    OrganizationMembershipModel
)


class MembershipRepository:

    @classmethod
    async def read_current(cls, user_id: int, org_id: int) -> OrganizationMembershipModel:

        try:
            async with async_session_factory() as session:

                query = (
                    select(OrganizationMembershipModel)
                    .where(
                        and_(
                            OrganizationMembershipModel.user_id == user_id,
                            OrganizationMembershipModel.org_id == org_id
                        )
                    )
                    .order_by(OrganizationMembershipModel.date.desc())
                    .limit(1)
                )

                db_response = await session.execute(query)
                current = db_response.unique().scalars().one_or_none()

                return current

        finally:
            await session.close()

    @classmethod
    async def read_memberships_of_user(cls, user_id: int) -> list[OrganizationMembershipModel]:

        try:
            async with async_session_factory() as session:

                subquery = select(
                    OrganizationMembershipModel.user_id,
                    OrganizationMembershipModel.org_id,
                    func.max(OrganizationMembershipModel.date)
                ).where(
                    OrganizationMembershipModel.user_id == user_id
                ).group_by(
                    OrganizationMembershipModel.user_id,
                    OrganizationMembershipModel.org_id
                ).alias()

                query = select(OrganizationMembershipModel).where(
                    OrganizationMembershipModel.user_id == user_id
                ).where(
                    tuple_(
                        OrganizationMembershipModel.user_id,
                        OrganizationMembershipModel.org_id,
                        OrganizationMembershipModel.date
                    ).in_(subquery)
                ).options(selectinload(OrganizationMembershipModel.organization))

                db_response = await session.execute(query)
                memberships = db_response.unique().scalars().all()

                return memberships

        finally:
            await session.close()

    @classmethod
    async def read_memberships_of_organization(cls, org_id: int) -> list[OrganizationMembershipModel]:

        try:
            async with async_session_factory() as session:

                subquery = (
                    select(
                        func.max(OrganizationMembershipModel.date).label("max_date")
                    )
                    .where(OrganizationMembershipModel.org_id == org_id)
                    .group_by(OrganizationMembershipModel.user_id)
                    .subquery()
                )

                query = (
                    select(OrganizationMembershipModel)
                    .where(
                        and_(
                            OrganizationMembershipModel.org_id == org_id,
                            OrganizationMembershipModel.date == subquery.c.max_date
                        )
                    )
                    .options(
                        selectinload(OrganizationMembershipModel.user),
                    )
                    .order_by(OrganizationMembershipModel.status.asc())
                )

                db_response = await session.execute(query)
                result = db_response.unique().scalars().all()

                return result
        finally:
            await session.close()
