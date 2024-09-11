from sqlalchemy import update, and_, func

from auth.models import UserSessionModel
from database import async_session_factory


class AuthRepository:

    @classmethod
    async def expire_sessions(cls, user_id: int, exclude_token: str = None):
        try:
            async with async_session_factory() as session:

                query = update(UserSessionModel)

                if exclude_token:
                    query = query.where(
                        and_(
                            UserSessionModel.token != exclude_token,
                            UserSessionModel.user_id == user_id
                        )
                    )
                else:
                    query = query.where(UserSessionModel.user_id == user_id)

                query = query.values(expires=func.now())

                await session.execute(query)
                await session.commit()

        finally:
            await session.close()
