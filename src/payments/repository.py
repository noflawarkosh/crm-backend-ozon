from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

from database import async_session_factory
from orders.models import OrdersOrderModel
from payments.models import BalanceBillModel, BalanceSourceModel, BalanceHistoryModel


class PaymentsRepository:
    @classmethod
    async def create_bill(cls, data: dict):
        try:
            async with async_session_factory() as session:

                bill = BalanceBillModel(**data)
                session.add(bill)
                await session.commit()
                await session.refresh(bill)

                return bill.id

        finally:
            await session.close()
